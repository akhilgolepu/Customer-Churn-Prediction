"""Shared data validation (model/data_schema.py): training data, requests, batch files."""

from __future__ import annotations

import asyncio
import itertools
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from model.data_schema import (
    FEATURE_SCHEMA,
    INTERNET_ADDONS,
    TRAINING_SCHEMA,
    consistency_errors,
    load_raw_training_csv,
    validate_frame,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FULL_DATA = REPO_ROOT / "data" / "Telco-Customer-Churn.csv"

GOOD = {
    "customerID": "0001-A", "gender": "Female", "SeniorCitizen": 0, "Partner": "Yes", "Dependents": "No",
    "tenure": 5, "PhoneService": "Yes", "MultipleLines": "No", "InternetService": "Fiber optic",
    "OnlineSecurity": "No", "OnlineBackup": "Yes", "DeviceProtection": "No", "TechSupport": "No",
    "StreamingTV": "Yes", "StreamingMovies": "No", "Contract": "Month-to-month", "PaperlessBilling": "Yes",
    "PaymentMethod": "Electronic check", "MonthlyCharges": 85.0, "TotalCharges": 425.0, "Churn": "No",
}
REQUEST_FIELDS = [k for k in GOOD if k not in ("customerID", "gender", "Churn")]


def _frame(*overrides) -> pd.DataFrame:
    rows = []
    for i, ov in enumerate(overrides):
        rows.append({**GOOD, "customerID": f"{i:04d}-A", **ov})
    return pd.DataFrame(rows)


def test_good_rows_pass_both_schemas():
    df = _frame({}, {"PhoneService": "No", "MultipleLines": "No phone service"})
    assert validate_frame(df, TRAINING_SCHEMA) == []
    assert validate_frame(df[REQUEST_FIELDS], FEATURE_SCHEMA) == []


@pytest.mark.skipif(not FULL_DATA.exists(), reason="full dataset is DVC-tracked")
def test_full_training_csv_passes():
    assert validate_frame(load_raw_training_csv(FULL_DATA), TRAINING_SCHEMA) == []


@pytest.mark.parametrize(
    "override, expected",
    [
        ({"MultipleLines": "Maybe"}, "column MultipleLines: failed isin"),
        ({"tenure": -1}, "column tenure: failed greater_than_or_equal_to(0)"),
        ({"MonthlyCharges": 0.0}, "column MonthlyCharges: failed greater_than(0)"),
        ({"SeniorCitizen": 2}, "column SeniorCitizen: failed isin"),
        ({"PhoneService": "No"}, "PhoneService='No' must coincide with MultipleLines"),
        ({"InternetService": "No"}, "InternetService='No' must coincide with OnlineSecurity"),
        ({"OnlineSecurity": "No internet service"}, "InternetService='No' must coincide"),
        ({"TotalCharges": None}, "blank TotalCharges is only allowed at tenure 0"),
        ({"Churn": "maybe"}, "column Churn: failed isin"),
        ({"tenure": 500}, "column tenure: failed less_than_or_equal_to(120)"),
    ],
)
def test_malformed_training_rows_are_reported(override, expected):
    errors = validate_frame(_frame({}, override), TRAINING_SCHEMA)
    assert any(expected in e and e.startswith("row 1") for e in errors), errors
    assert not any(e.startswith("row 0") for e in errors), "the good row must not be flagged"


def test_blank_total_charges_allowed_at_tenure_zero():
    assert validate_frame(_frame({"tenure": 0, "TotalCharges": None}), TRAINING_SCHEMA) == []


def test_duplicate_ids_and_unexpected_columns_fail_training_schema():
    dup = _frame({}, {})
    dup.loc[1, "customerID"] = dup.loc[0, "customerID"]
    assert any("customerID" in e for e in validate_frame(dup, TRAINING_SCHEMA))
    extra = _frame({}).assign(Surprise=1)
    assert any("Surprise" in e for e in validate_frame(extra, TRAINING_SCHEMA))
    missing = _frame({}).drop(columns=["Contract"])
    assert any("Contract" in e for e in validate_frame(missing, TRAINING_SCHEMA))


def test_scalar_and_pandera_rules_agree_on_every_service_combination():
    """consistency_errors (requests) and the pandera checks (training/batch)
    come from one rule table; check they agree on all 2*3 * 3*3^6 combinations."""
    rows = []
    for phone, lines in itertools.product(["Yes", "No"], ["Yes", "No", "No phone service"]):
        for internet in ["DSL", "No"]:
            for addons in itertools.product(["Yes", "No", "No internet service"], repeat=len(INTERNET_ADDONS)):
                rows.append({**GOOD, "PhoneService": phone, "MultipleLines": lines, "InternetService": internet,
                             **dict(zip(INTERNET_ADDONS, addons))})
    frame = pd.DataFrame(rows)[REQUEST_FIELDS].reset_index(drop=True)
    pandera_bad = {int(e.split(":")[0].split()[1]) for e in validate_frame(frame, FEATURE_SCHEMA, max_errors=10**6)
                   if e.startswith("row ")}
    scalar_bad = {i for i, r in enumerate(rows) if consistency_errors(r)}
    assert len(rows) == 6 * 2 * 3 ** 6
    assert pandera_bad == scalar_bad
    assert 0 < len(scalar_bad) < len(rows)


# --- API ---------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from core.settings import get_settings

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("CHALLENGER_ENABLED", "false")
    get_settings.cache_clear()
    from app_factory import create_app

    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def _payload(**overrides):
    return {k: GOOD[k] for k in REQUEST_FIELDS} | overrides


def test_predict_rejects_inconsistent_services_with_422(client):
    r = client.post("/api/v1/predictions/predict", json=_payload(InternetService="No"))
    assert r.status_code == 422
    assert "InternetService='No' must coincide" in str(r.json()["details"])
    ok = client.post("/api/v1/predictions/predict", json=_payload())
    assert ok.status_code == 200


def test_explain_and_legacy_predict_use_the_same_check(client):
    bad = _payload(PhoneService="No")  # MultipleLines still "No"
    assert client.post("/api/v1/predictions/explain", json=bad).status_code == 422
    assert client.post("/predict", json=bad).status_code == 422


def _run_batch(client, frame: pd.DataFrame) -> dict:
    job_service = client.app.state.job_service
    job_service._object_storage = None
    job = SimpleNamespace(payload={"csv": frame.to_csv(index=False)})
    return asyncio.run(job_service._run_batch_scoring(job))


def test_batch_file_reports_every_bad_row(client):
    frame = pd.DataFrame([_payload(), _payload(tenure=-3), _payload(InternetService="No"), _payload(Contract="Weekly")])
    with pytest.raises(ValueError) as exc:
        _run_batch(client, frame)
    message = str(exc.value)
    assert message.startswith("Batch file failed validation")
    assert "row 1, column tenure" in message
    assert "row 2: InternetService='No' must coincide" in message
    assert "row 3, column Contract" in message
    assert "row 0" not in message


def test_valid_batch_file_is_scored(client):
    result = _run_batch(client, pd.DataFrame([_payload(), _payload(tenure=40, Contract="Two year")]))
    assert result["rows"] == 2
