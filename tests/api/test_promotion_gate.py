"""POST /api/v1/models/promote runs the validation gate: pass, block, override."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import services.model_registry_service as registry_module
from core.settings import get_settings
from services.promotion_gate import PromotionGate

RNG_SEED = 0
CATEGORIES = {
    "gender": ["Female", "Male"],
    "Partner": ["Yes", "No"],
    "Dependents": ["Yes", "No"],
    "PhoneService": ["Yes", "No"],
    "MultipleLines": ["Yes", "No", "No phone service"],
    "InternetService": ["DSL", "Fiber optic", "No"],
    "OnlineSecurity": ["Yes", "No", "No internet service"],
    "OnlineBackup": ["Yes", "No", "No internet service"],
    "DeviceProtection": ["Yes", "No", "No internet service"],
    "TechSupport": ["Yes", "No", "No internet service"],
    "StreamingTV": ["Yes", "No", "No internet service"],
    "StreamingMovies": ["Yes", "No", "No internet service"],
    "Contract": ["Month-to-month", "One year", "Two year"],
    "PaperlessBilling": ["Yes", "No"],
    "PaymentMethod": ["Electronic check", "Mailed check", "Bank transfer (automatic)", "Credit card (automatic)"],
}


def _labelled_csv(path, n=400):
    """Synthetic rows in the raw Telco schema. Labels alternate so both classes exist."""
    rng = np.random.default_rng(RNG_SEED)
    frame = pd.DataFrame({col: rng.choice(values, n) for col, values in CATEGORIES.items()})
    frame.insert(0, "customerID", [f"C{i:05d}" for i in range(n)])
    frame["SeniorCitizen"] = rng.integers(0, 2, n)
    frame["tenure"] = rng.integers(0, 73, n)
    frame["MonthlyCharges"] = rng.uniform(18, 120, n).round(2)
    frame["TotalCharges"] = (frame["MonthlyCharges"] * frame["tenure"]).round(2)
    frame["Churn"] = np.where(np.arange(n) % 4 == 0, "Yes", "No")
    frame.to_csv(path, index=False)
    return (frame["Churn"] == "Yes").astype(int).to_numpy()


def _scorer_from(scores_by_artifact: dict):
    """scorer(artifact) -> predict_fn; predict_fn returns the fixed scores for full-frame calls."""

    def scorer(artifact):
        scores = scores_by_artifact[artifact]

        def predict_fn(frame):
            return scores[: len(frame)]

        return predict_fn

    return scorer


def _good(y):
    rng = np.random.default_rng(1)
    return np.clip(0.15 + 0.6 * y + rng.normal(0, 0.1, len(y)), 0.01, 0.99)


def _random(y):
    return np.random.default_rng(2).uniform(0.01, 0.99, len(y))


def _gate(eval_path, scores):
    return PromotionGate(
        eval_data_path=eval_path,
        decision_threshold=0.38,
        min_auc=0.75,
        min_precision=0.40,
        min_recall=0.40,
        min_f1=0.45,
        max_auc_drop=0.02,
        scorer=_scorer_from(scores),
    )


# --- gate logic (real ModelValidationGate, stubbed model scores) -------------


def test_gate_passes_a_good_candidate(tmp_path):
    y = _labelled_csv(tmp_path / "eval.csv")
    result = _gate(tmp_path / "eval.csv", {"cand": _good(y), "act": _good(y)}).evaluate("v2", "cand", "act")
    assert result["promotion_allowed"] is True, result["blockers"]
    assert result["eval_rows"] == len(y)
    assert any(c["name"] == "ROC AUC Score" and c["status"] == "passed" for c in result["checks"])


def test_gate_blocks_a_model_without_signal(tmp_path):
    y = _labelled_csv(tmp_path / "eval.csv")
    result = _gate(tmp_path / "eval.csv", {"cand": _random(y), "act": _good(y)}).evaluate("v3", "cand", "act")
    assert result["promotion_allowed"] is False
    assert "Model quality metrics below thresholds" in result["blockers"]
    assert any("below the active model" in b for b in result["blockers"])


def test_gate_blocks_a_regression_against_the_active_model(tmp_path):
    y = _labelled_csv(tmp_path / "eval.csv")
    active = np.clip(0.05 + 0.9 * y, 0.01, 0.99)  # perfect ranking
    candidate = _good(y).copy()
    candidate[y == 0] = np.where(np.arange((y == 0).sum()) % 6 == 0, 0.9, candidate[y == 0])  # still > 0.75 AUC
    result = _gate(tmp_path / "eval.csv", {"cand": candidate, "act": active}).evaluate("v2", "cand", "act")
    assert result["candidate"]["roc_auc"] >= 0.75
    assert result["promotion_allowed"] is False
    assert any("below the active model" in b for b in result["blockers"])


def test_gate_fails_closed_without_evaluation_data(tmp_path):
    result = _gate(tmp_path / "missing.csv", {}).evaluate("v2", "cand", "act")
    assert result["promotion_allowed"] is False
    assert "No labelled evaluation data" in result["blockers"][0]


def test_gate_blocks_an_unloadable_artifact(tmp_path):
    _labelled_csv(tmp_path / "eval.csv")
    result = _gate(tmp_path / "eval.csv", {}).evaluate("v2", "does-not-exist.cbm", None)
    assert result["promotion_allowed"] is False
    assert "could not be loaded" in result["blockers"][0]


# --- HTTP route --------------------------------------------------------------


class StubGate:
    def __init__(self, allowed: bool):
        self.allowed = allowed
        self.calls = []

    def evaluate(self, version, candidate_artifact, active_artifact):
        self.calls.append((version, candidate_artifact, active_artifact))
        return {
            "promotion_allowed": self.allowed,
            "blockers": [] if self.allowed else ["Model quality metrics below thresholds"],
            "warnings": [],
            "candidate": {"roc_auc": 0.84 if self.allowed else 0.50},
            "active": {"roc_auc": 0.84},
            "eval_rows": 400,
        }


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SCHEDULE_RETRAINING_ENABLED", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(registry_module, "switch_active_model", lambda path: None)
    monkeypatch.setattr(registry_module, "switch_shadow_model", lambda path: None)
    from app_factory import create_app

    with TestClient(create_app()) as c:
        c.app.state.model_registry_service.validation_reports_dir = tmp_path / "reports"
        yield c
    get_settings.cache_clear()


def _admin(client):
    tok = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _register(client, headers, version="v2"):
    body = {"version": version, "metrics": {}, "artifact_path": f"models/{version}.cbm"}
    return client.post("/api/v1/models/register", json=body, headers=headers).json()


def _audit_records(client):
    """(action, metadata) for every audit event, from the in-memory (SQLite mode)
    or the Postgres audit repository."""
    repo = client.app.state.audit_service._repo
    if hasattr(repo, "_records"):
        return [(r.action, r.metadata) for r in repo._records]
    from sqlalchemy import select

    from db.models import AuditLog

    with client.app.state.postgres_session_factory.session_scope() as session:
        rows = session.execute(select(AuditLog).order_by(AuditLog.event_at)).scalars().all()
        return [(r.action, r.metadata_json) for r in rows]


def _audit_actions(client):
    return [action for action, _ in _audit_records(client)]


def test_app_wires_a_real_promotion_gate(client):
    assert isinstance(client.app.state.model_registry_service._promotion_gate, PromotionGate)


def test_promote_passes_when_gate_allows(client):
    gate = StubGate(allowed=True)
    client.app.state.model_registry_service._promotion_gate = gate
    h = _admin(client)
    cand = _register(client, h)

    r = client.post("/api/v1/models/promote", json={"candidate_model_id": cand["id"]}, headers=h)

    assert r.status_code == 200, r.text
    assert r.json()["active_model_id"] == cand["id"]
    assert r.json()["validation"]["promotion_allowed"] is True
    assert gate.calls and gate.calls[0][1] == cand["artifact_path"]
    assert "model_promoted" in _audit_actions(client)


def test_promote_is_refused_with_409_when_gate_blocks(client):
    client.app.state.model_registry_service._promotion_gate = StubGate(allowed=False)
    h = _admin(client)
    before = client.get("/api/v1/models", headers=h).json()["active_model_id"]
    cand = _register(client, h)

    r = client.post("/api/v1/models/promote", json={"candidate_model_id": cand["id"]}, headers=h)

    assert r.status_code == 409, r.text
    body = r.json()
    assert body["code"] == "promotion_blocked"
    assert body["details"]["blockers"] == ["Model quality metrics below thresholds"]
    assert client.get("/api/v1/models", headers=h).json()["active_model_id"] == before
    assert "model_promotion_blocked" in _audit_actions(client)
    assert "model_promoted" not in _audit_actions(client)


def test_override_requires_a_reason(client):
    client.app.state.model_registry_service._promotion_gate = StubGate(allowed=False)
    h = _admin(client)
    cand = _register(client, h)
    r = client.post("/api/v1/models/promote", json={"candidate_model_id": cand["id"], "override_gate": True}, headers=h)
    assert r.status_code == 422


def test_override_promotes_and_is_audit_logged(client):
    client.app.state.model_registry_service._promotion_gate = StubGate(allowed=False)
    h = _admin(client)
    cand = _register(client, h)

    r = client.post(
        "/api/v1/models/promote",
        json={"candidate_model_id": cand["id"], "override_gate": True, "override_reason": "hotfix approved by on-call"},
        headers=h,
    )

    assert r.status_code == 200, r.text
    assert r.json()["validation"]["overridden"] is True
    records = _audit_records(client)
    override = next(meta for action, meta in records if action == "model_promotion_gate_overridden")
    assert override["override_reason"] == "hotfix approved by on-call"
    assert override["actor"] == "admin"
    assert override["blockers"] == ["Model quality metrics below thresholds"]
    promoted = next(meta for action, meta in records if action == "model_promoted")
    assert promoted["gate_overridden"] is True


def test_promote_still_requires_admin(client):
    tok = client.post("/api/v1/auth/login", json={"username": "analyst", "password": "analyst123"}).json()["access_token"]
    r = client.post("/api/v1/models/promote", json={"candidate_model_id": "x"}, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
