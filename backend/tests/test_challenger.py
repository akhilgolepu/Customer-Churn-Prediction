"""Logistic-regression challenger: JSON export, serving, shadow attachment, restart sync."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import services.model_registry_service as registry_module
from core.settings import get_settings
from model.linear_model import LinearChurnModel
from repositories.model_registry_repository import ModelRegistryRepository
from repositories.sqlite_store import SQLiteStore
from services.model_registry_service import ModelRegistryService
from tests.test_promotion_gate import _labelled_csv

REPO_ROOT = Path(__file__).resolve().parents[2]
CHALLENGER = "model/artifacts/logreg_challenger.json"


def _features(csv_path):
    from model.preprocessing.preprocessing import load_artifacts, prepare_for_model, preprocess

    df = pd.read_csv(csv_path)
    y = (df.pop("Churn") == "Yes").astype(int)
    features, cats = load_artifacts()
    x = prepare_for_model(preprocess(df), features)
    for c in cats:
        x[c] = x[c].astype(str)
    return x, y, cats


def _fitted(tmp_path):
    import sys

    sys.path.insert(0, str(REPO_ROOT / "model" / "training"))
    from common import fit_logistic_regression

    _labelled_csv(tmp_path / "d.csv", n=600)
    x, y, cats = _features(tmp_path / "d.csv")
    x.loc[x.index[:5], "TotalCharges"] = np.nan  # exercise median imputation
    pipe = fit_logistic_regression(x, y, cats, {"C": 1.0, "max_iter": 2000})
    return pipe, x


def test_json_export_reproduces_sklearn(tmp_path):
    pipe, x = _fitted(tmp_path)
    linear = LinearChurnModel.from_sklearn(pipe, x)
    again = LinearChurnModel.load(linear.save(tmp_path / "lr.json"))
    np.testing.assert_allclose(again.predict_proba(x), pipe.predict_proba(x)[:, 1], atol=1e-12)


def test_unseen_category_level_is_ignored_like_sklearn(tmp_path):
    pipe, x = _fitted(tmp_path)
    linear = LinearChurnModel.from_sklearn(pipe, x)
    row = x.iloc[:1].copy()
    row["PaymentMethod"] = "Crypto"  # never seen in training
    np.testing.assert_allclose(linear.predict_proba(row), pipe.predict_proba(row)[:, 1], atol=1e-12)


def test_explanations_add_up_to_the_logit(tmp_path):
    pipe, x = _fitted(tmp_path)
    linear = LinearChurnModel.from_sklearn(pipe, x)
    row = x.iloc[[3]]
    p = linear.predict_proba(row)[0]
    contributions = linear.explain(row)
    assert len(contributions) == x.shape[1]
    assert np.log(p / (1 - p)) == pytest.approx(linear._base_logit() + contributions.sum(), abs=1e-9)


def test_shipped_challenger_artifact_is_served_as_shadow_and_active():
    from model_loader import ModelRuntimeManager

    from tests.test_calibration import _row

    manager = ModelRuntimeManager(REPO_ROOT / "model" / "artifacts" / "catboost_churn.cbm")
    manager.set_shadow_model(CHALLENGER)
    x = _row()
    shadow = manager.predict_shadow(x)
    assert 0.0 < shadow < 1.0
    assert manager.state()["shadow_model_kind"] == "logistic_regression"

    manager.set_active_model(CHALLENGER)
    assert manager.predict_active(x) == pytest.approx(shadow)
    assert len(manager.explain_active(x)) == x.shape[1]
    assert manager.state()["active_model_kind"] == "logistic_regression"


# --- registry: challenger attachment and restart sync ------------------------


def _service(tmp_path, monkeypatch, active_calls=None, shadow_calls=None, fail_on=None):
    def switch_active(path):
        if fail_on and path == fail_on:
            raise RuntimeError("cannot load")
        (active_calls if active_calls is not None else []).append(path)

    def switch_shadow(path):
        if fail_on and path == fail_on:
            raise RuntimeError("cannot load")
        (shadow_calls if shadow_calls is not None else []).append(path)

    monkeypatch.setattr(registry_module, "switch_active_model", switch_active)
    monkeypatch.setattr(registry_module, "switch_shadow_model", switch_shadow)
    repo = ModelRegistryRepository(store=SQLiteStore(str(tmp_path / "r.db")), default_artifact_path="model/a.cbm")
    return ModelRegistryService(repo=repo, validation_reports_dir=tmp_path / "rep"), repo


def test_challenger_attaches_once_when_shadow_slot_is_free(tmp_path, monkeypatch):
    service, repo = _service(tmp_path, monkeypatch)
    first = service.ensure_challenger(CHALLENGER, "logreg-challenger", {"val_roc_auc": 0.84})
    second = service.ensure_challenger(CHALLENGER, "logreg-challenger")
    assert first is not None and first == second
    assert repo.state()[1] == first
    assert sum(v.artifact_path == CHALLENGER for v in repo.list_versions()) == 1


def test_challenger_does_not_displace_a_candidate_under_test(tmp_path, monkeypatch):
    service, repo = _service(tmp_path, monkeypatch)
    cand = service.register_candidate("v2", {}, "model/b.cbm")
    service.start_shadow_test(cand["id"])
    assert service.ensure_challenger(CHALLENGER, "logreg-challenger") is None
    assert repo.state()[1] == cand["id"]


def test_rejected_challenger_is_not_reattached(tmp_path, monkeypatch):
    service, repo = _service(tmp_path, monkeypatch)
    service.ensure_challenger(CHALLENGER, "logreg-challenger")
    service.abort_canary("disagreement too high")
    assert service.ensure_challenger(CHALLENGER, "logreg-challenger") is None
    assert repo.state()[1] is None


def test_restart_serves_the_registry_active_model(tmp_path, monkeypatch):
    """Regression: after a promotion and a restart the registry reported v2 as
    active while the runtime served the default artifact."""

    class PassGate:
        def evaluate(self, *args):
            return {"promotion_allowed": True, "blockers": []}

    service, repo = _service(tmp_path, monkeypatch)
    service._promotion_gate = PassGate()
    v2 = service.register_candidate("v2", {}, "model/b.cbm")
    service.promote_candidate(v2["id"])

    active_calls: list = []
    restarted, _ = _service(tmp_path, monkeypatch, active_calls=active_calls)
    restarted.sync_runtime()
    assert active_calls == ["model/b.cbm"]


def test_restart_fails_loudly_when_active_artifact_is_missing(tmp_path, monkeypatch):
    service, repo = _service(tmp_path, monkeypatch, fail_on="model/a.cbm")
    with pytest.raises(RuntimeError, match="could not be loaded"):
        service.sync_runtime()


def test_restart_rejects_an_unloadable_shadow(tmp_path, monkeypatch):
    service, repo = _service(tmp_path, monkeypatch)
    cand = service.register_candidate("v2", {}, "model/gone.cbm")
    service.start_shadow_test(cand["id"])
    restarted, repo2 = _service(tmp_path, monkeypatch, fail_on="model/gone.cbm")
    restarted.sync_runtime()
    assert repo2.state()[1] is None
    assert repo2.get(cand["id"]).status == "rejected"


# --- app integration ---------------------------------------------------------


def test_app_scores_every_request_with_the_challenger(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SCHEDULE_RETRAINING_ENABLED", "false")
    get_settings.cache_clear()
    try:
        from app_factory import create_app

        payload = {
            "MonthlyCharges": 85.0, "tenure": 5, "TotalCharges": 425.0, "SeniorCitizen": 0, "Partner": "Yes",
            "Dependents": "No", "PhoneService": "Yes", "MultipleLines": "No", "InternetService": "Fiber optic",
            "OnlineSecurity": "No", "OnlineBackup": "No", "DeviceProtection": "No", "TechSupport": "No",
            "StreamingTV": "Yes", "StreamingMovies": "No", "Contract": "Month-to-month", "PaperlessBilling": "Yes",
            "PaymentMethod": "Electronic check",
        }
        with TestClient(create_app()) as client:
            tok = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).json()
            h = {"Authorization": f"Bearer {tok['access_token']}"}
            reg = client.get("/api/v1/models", headers=h).json()
            shadow = next(v for v in reg["versions"] if v["id"] == reg["shadow_model_id"])
            assert shadow["version"] == "logreg-challenger"
            assert shadow["metrics"]["val_roc_auc"] > 0.8

            body = client.post("/api/v1/predictions/predict", json=payload).json()
            assert 0.0 < body["shadowProbability"] < 1.0
            canary = client.get("/api/v1/system/canary", headers=h).json()
            assert canary["compared_samples"] >= 1
    finally:
        get_settings.cache_clear()
        import model_loader

        model_loader.switch_shadow_model(None)
