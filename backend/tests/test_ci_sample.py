"""Committed synthetic sample (data/ci_sample.csv): runs in CI without the DVC dataset.

Golden predictions pin the shipped model's calibrated output on 500 rows, both
through the training-side preprocessing and through the HTTP serving path, so a
change in preprocessing, feature engineering, the artifact or a library version
that moves predictions fails CI. See scripts/make_ci_sample.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from model.data_schema import TRAINING_SCHEMA, validate_frame

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "data" / "ci_sample.csv"
GOLDEN = json.loads((REPO_ROOT / "data" / "ci_sample_golden.json").read_text(encoding="utf-8"))["probabilities"]
REQUEST_FIELDS = [
    "MonthlyCharges", "tenure", "TotalCharges", "SeniorCitizen", "Partner", "Dependents", "PhoneService",
    "MultipleLines", "InternetService", "OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport",
    "StreamingTV", "StreamingMovies", "Contract", "PaperlessBilling", "PaymentMethod",
]


def _sample() -> pd.DataFrame:
    df = pd.read_csv(SAMPLE)
    df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce")
    return df


def test_sample_is_valid_training_data():
    df = _sample()
    assert len(df) == 500 == len(GOLDEN)
    assert validate_frame(df, TRAINING_SCHEMA) == []


def test_shipped_model_reproduces_golden_predictions():
    from model_loader import ModelRuntimeManager

    from model.preprocessing.preprocessing import load_artifacts, prepare_for_model, preprocess

    df = _sample()
    features, cats = load_artifacts()
    x = prepare_for_model(preprocess(df.drop(columns=["customerID", "gender", "Churn"])), features)
    for c in cats:
        x[c] = x[c].astype(str)
    manager = ModelRuntimeManager(REPO_ROOT / "model" / "artifacts" / "catboost_churn.cbm")
    p = manager.load_scorer(str(REPO_ROOT / "model" / "artifacts" / "catboost_churn.cbm"))(x)
    np.testing.assert_allclose(p, GOLDEN, atol=1e-6)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from core.settings import get_settings

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("CHALLENGER_ENABLED", "false")
    monkeypatch.setenv("PREDICT_RATE_LIMIT_PER_MINUTE", "100000")
    get_settings.cache_clear()
    from app_factory import create_app

    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def test_http_predict_matches_golden_on_every_row(client):
    """Serving path (pydantic request -> backend/feature_engineering.py -> runtime)
    must give the same probability as training-side preprocessing."""
    df = _sample()
    # The API requires a number; tenure-0 rows have blank TotalCharges in training
    # data. CatBoost treats a missing value as below every value, so 0.0 must give
    # the identical prediction; including these rows checks that there is no skew.
    df["TotalCharges"] = df["TotalCharges"].fillna(0.0)
    served = []
    for _, row in df[REQUEST_FIELDS].iterrows():
        payload = {k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}
        r = client.post("/api/v1/predictions/predict", json=payload)
        assert r.status_code == 200, r.text
        served.append(r.json()["probability"])
    np.testing.assert_allclose(served, GOLDEN, atol=1e-6)
