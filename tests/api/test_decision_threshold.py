from __future__ import annotations

from fastapi.testclient import TestClient

from app_factory import create_app
from core.settings import get_settings
from tests.api.test_regression_pipeline import _load_sample_payload


def test_predict_uses_configured_default_threshold_when_not_supplied() -> None:
    payload = _load_sample_payload()
    default_threshold = get_settings().decision_threshold

    with TestClient(create_app()) as client:
        response = client.post("/api/v1/predictions/predict", json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["isChurn"] == (body["probability"] >= default_threshold)

        # An explicit threshold still wins over the configured default.
        strict = client.post("/api/v1/predictions/predict?threshold=1.0", json=payload)
        assert strict.status_code == 200, strict.text
        assert strict.json()["isChurn"] is False
