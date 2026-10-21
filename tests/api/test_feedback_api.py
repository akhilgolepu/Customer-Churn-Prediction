"""Feedback / outcome endpoints persist and summarise (runs on SQLite and Postgres)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from core.settings import get_settings

PAYLOAD = {
    "MonthlyCharges": 85.0, "tenure": 5, "TotalCharges": 425.0, "SeniorCitizen": 0, "Partner": "Yes",
    "Dependents": "No", "PhoneService": "Yes", "MultipleLines": "No", "InternetService": "Fiber optic",
    "OnlineSecurity": "No", "OnlineBackup": "No", "DeviceProtection": "No", "TechSupport": "No",
    "StreamingTV": "Yes", "StreamingMovies": "No", "Contract": "Month-to-month", "PaperlessBilling": "Yes",
    "PaymentMethod": "Electronic check",
}


def test_feedback_and_outcome_round_trip(tmp_path, monkeypatch):
    """Regression (Postgres): feedback_events had no event_at default, so every
    feedback/outcome insert failed with a NOT NULL violation."""
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("CHALLENGER_ENABLED", "false")
    get_settings.cache_clear()
    try:
        from app_factory import create_app

        with TestClient(create_app()) as client:
            tok = client.post("/api/v1/auth/login", json={"username": "analyst", "password": "analyst123"}).json()
            h = {"Authorization": f"Bearer {tok['access_token']}"}
            pid = client.post("/api/v1/predictions/predict", json=PAYLOAD).json()["predictionId"]

            fb = client.post("/api/v1/predictions/feedback", json={"prediction_id": pid, "useful": True, "comment": "ok"}, headers=h)
            assert fb.status_code == 200, fb.text
            oc = client.post("/api/v1/predictions/outcome", json={"prediction_id": pid, "actual_churn": True}, headers=h)
            assert oc.status_code == 200, oc.text
            summary = client.get("/api/v1/predictions/feedback/summary", headers=h)
            assert summary.status_code == 200, summary.text
            body = summary.json()
            assert body["total_feedback"] == 1 and body["useful_count"] == 1
            assert body["outcomes_recorded"] == 1
    finally:
        get_settings.cache_clear()
