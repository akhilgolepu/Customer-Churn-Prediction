"""Live drift monitor (services/monitoring_service.py) via the API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from core.settings import get_settings

ADDONS = ["OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies"]
BASE = {
    "MonthlyCharges": 70.0, "tenure": 20, "TotalCharges": 1400.0, "SeniorCitizen": 0, "Partner": "Yes",
    "Dependents": "No", "PhoneService": "Yes", "MultipleLines": "No", "InternetService": "DSL",
    "Contract": "One year", "PaperlessBilling": "Yes", "PaymentMethod": "Mailed check",
}


def test_total_services_signal_reflects_the_requests(tmp_path, monkeypatch):
    """Regression: TotalServices is engineered, not in the stored request, so the
    monitor never found it and always reported 0 (no drift could ever fire)."""
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("CHALLENGER_ENABLED", "false")
    monkeypatch.setenv("PREDICT_RATE_LIMIT_PER_MINUTE", "100000")
    get_settings.cache_clear()
    try:
        from app_factory import create_app

        with TestClient(create_app()) as client:
            for value in ["No"] * 20 + ["Yes"] * 20:
                r = client.post("/api/v1/predictions/predict", json={**BASE, **{a: value for a in ADDONS}})
                assert r.status_code == 200, r.text
            tok = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).json()
            snap = client.get("/api/v1/system/monitoring",
                              headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
        row = next(r for r in snap["input_drift"] if r["metric"] == "TotalServices")
        assert row["baseline"] == 0.0
        assert row["recent"] == 6.0
        assert row["alert"] is True
        assert any("TotalServices" in a for a in snap["alerts"])
    finally:
        get_settings.cache_clear()


def test_monitor_watches_the_latest_window_not_the_first():
    """Regression: the monitor read page 1 of the SQLite-mode history (oldest first),
    so after 5,000 predictions it never saw new traffic again."""
    from types import SimpleNamespace

    from repositories.prediction_repository import PredictionHistoryItem, PredictionRepository
    from services.monitoring_service import MonitoringService

    repo = PredictionRepository()
    for i in range(6000):
        addon = "Yes" if i >= 5000 else "No"  # only the newest 1,000 change
        repo.add(PredictionHistoryItem(id=str(i), created_at=float(i), probability=0.3, is_churn=False,
                                       threshold=0.38, inputs={**BASE, **{a: addon for a in ADDONS}}))
    assert [item.id for item in repo.recent(3)] == ["5997", "5998", "5999"]

    monitor = MonitoringService(
        prediction_repo=repo,
        feedback_repo=SimpleNamespace(list_outcomes=lambda: []),
        monitoring_repo=SimpleNamespace(save_snapshot=lambda payload: None),
    )
    row = next(r for r in monitor.snapshot()["input_drift"] if r["metric"] == "TotalServices")
    assert row["baseline"] == 0.0 and row["recent"] > 0 and row["alert"] is True

