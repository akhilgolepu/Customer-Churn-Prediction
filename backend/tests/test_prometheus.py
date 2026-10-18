"""GET /metrics: Prometheus exposition of latency, predictions, scores, canary and model identity."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from core.settings import get_settings

PAYLOAD = {
    "MonthlyCharges": 85.0, "tenure": 5, "TotalCharges": 425.0, "SeniorCitizen": 0, "Partner": "Yes",
    "Dependents": "No", "PhoneService": "Yes", "MultipleLines": "No", "InternetService": "Fiber optic",
    "OnlineSecurity": "No", "OnlineBackup": "No", "DeviceProtection": "No", "TechSupport": "No",
    "StreamingTV": "Yes", "StreamingMovies": "No", "Contract": "Month-to-month", "PaperlessBilling": "Yes",
    "PaymentMethod": "Electronic check",
}


@pytest.fixture()
def make_client(tmp_path, monkeypatch):
    def _make(**env):
        monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        from app_factory import create_app

        return TestClient(create_app())

    yield _make
    get_settings.cache_clear()
    import model_loader

    model_loader.switch_shadow_model(None)


def _samples(text: str) -> list:
    return [s for fam in text_string_to_metric_families(text) for s in fam.samples]


def _value(samples, name, **labels) -> float:
    return sum(s.value for s in samples if s.name == name and all(s.labels.get(k) == v for k, v in labels.items()))


def test_metrics_track_predictions_latency_and_models(make_client):
    with make_client(CHALLENGER_ENABLED="true") as client:
        before = _samples(client.get("/metrics").text)
        for _ in range(3):
            assert client.post("/api/v1/predictions/predict", json=PAYLOAD).status_code == 200
        client.get("/api/v1/jobs/does-not-exist")  # 401/404 path with a template
        r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    after = _samples(r.text)

    served = _value(after, "churn_predictions_total") - _value(before, "churn_predictions_total")
    assert served == 3
    assert _value(after, "churn_prediction_score_count") - _value(before, "churn_prediction_score_count") == 3
    latency = _value(after, "churn_http_request_duration_seconds_count",
                     route="/api/v1/predictions/predict", method="POST", status="200")
    assert latency >= 3
    assert any(s.labels.get("route") == "/api/v1/jobs/{job_id}" for s in after
               if s.name == "churn_http_request_duration_seconds_count")

    # Standing challenger in the shadow slot: every request compared, model identities exposed.
    assert _value(after, "churn_canary_compared_requests") >= 3
    assert _value(after, "churn_model_info", slot="active", kind="catboost") == 1
    assert _value(after, "churn_model_info", slot="shadow", kind="logistic_regression",
                  version="logreg-challenger") == 1


def test_metrics_token_protects_the_endpoint(make_client):
    with make_client(METRICS_TOKEN="s3cret-scrape-token", CHALLENGER_ENABLED="false") as client:
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        ok = client.get("/metrics", headers={"Authorization": "Bearer s3cret-scrape-token"})
    assert ok.status_code == 200 and "churn_predictions_total" in ok.text
