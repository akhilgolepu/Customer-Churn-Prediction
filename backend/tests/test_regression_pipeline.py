from __future__ import annotations

from pathlib import Path
import time

import pandas as pd
from fastapi.testclient import TestClient

from app_factory import create_app
from model_loader import predict_proba
from model.preprocessing.preprocessing import load_artifacts, prepare_for_model, preprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DATASET = REPO_ROOT / "data" / "Telco-Customer-Churn.csv"

# Keep thresholds practical to avoid CI flakiness while still guarding regressions.
PREPROCESS_LATENCY_SECONDS = 2.0
MODEL_PREDICT_LATENCY_SECONDS = 2.0
API_PREDICT_LATENCY_SECONDS = 6.0


def _load_sample_payload() -> dict:
    df = pd.read_csv(SAMPLE_DATASET)
    row = df.iloc[0]
    return {
        "MonthlyCharges": float(row["MonthlyCharges"]),
        "tenure": int(row["tenure"]),
        "TotalCharges": float(row["TotalCharges"]),
        "SeniorCitizen": int(row["SeniorCitizen"]),
        "Partner": str(row["Partner"]),
        "Dependents": str(row["Dependents"]),
        "PhoneService": str(row["PhoneService"]),
        "MultipleLines": str(row["MultipleLines"]),
        "InternetService": str(row["InternetService"]),
        "OnlineSecurity": str(row["OnlineSecurity"]),
        "OnlineBackup": str(row["OnlineBackup"]),
        "DeviceProtection": str(row["DeviceProtection"]),
        "TechSupport": str(row["TechSupport"]),
        "StreamingTV": str(row["StreamingTV"]),
        "StreamingMovies": str(row["StreamingMovies"]),
        "Contract": str(row["Contract"]),
        "PaperlessBilling": str(row["PaperlessBilling"]),
        "PaymentMethod": str(row["PaymentMethod"]),
    }


def _login_token(client: TestClient, username: str = "analyst", password: str = "analyst123") -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "access_token" in body
    return str(body["access_token"])


def test_sample_preprocess_predict_regression_schema_and_latency() -> None:
    payload = _load_sample_payload()
    raw_df = pd.DataFrame([payload])

    start_preprocess = time.perf_counter()
    engineered_df = preprocess(raw_df)
    feature_list, _ = load_artifacts()
    model_df = prepare_for_model(engineered_df, feature_list)
    preprocess_elapsed = time.perf_counter() - start_preprocess

    assert preprocess_elapsed < PREPROCESS_LATENCY_SECONDS
    assert list(model_df.columns) == feature_list
    assert model_df.shape[0] == 1

    start_predict = time.perf_counter()
    probability = float(predict_proba(model_df))
    predict_elapsed = time.perf_counter() - start_predict

    assert predict_elapsed < MODEL_PREDICT_LATENCY_SECONDS
    assert 0.0 <= probability <= 1.0


def test_api_predict_regression_schema_and_latency() -> None:
    payload = _load_sample_payload()
    app = create_app()

    with TestClient(app) as client:
        token = _login_token(client)

        start_api = time.perf_counter()
        response = client.post(
            "/api/v1/predictions/predict?threshold=0.5",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        api_elapsed = time.perf_counter() - start_api

    assert api_elapsed < API_PREDICT_LATENCY_SECONDS
    assert response.status_code == 200, response.text

    body = response.json()
    assert isinstance(body.get("predictionId"), str)
    assert isinstance(body.get("probability"), float)
    assert isinstance(body.get("isChurn"), bool)
    assert 0.0 <= float(body["probability"]) <= 1.0
