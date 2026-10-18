"""Locust load test for POST /api/v1/predictions/predict.

Each simulated user posts a real customer row sampled from the Telco dataset
so the model sees realistic feature variety (not one cached payload).

Run against a local server (see loadtest/run_loadtest.sh):
    locust -f loadtest/locust_predict.py --headless -u 20 -r 5 -t 60s \
        --host http://127.0.0.1:8000 --csv loadtest/results/predict

NOTE: the API rate-limits /predict per client IP (PREDICT_RATE_LIMIT_PER_MINUTE,
default 30). A load test from one IP would measure the limiter, not the model,
so start the server under test with PREDICT_RATE_LIMIT_PER_MINUTE set high.
"""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd
from locust import HttpUser, between, task

DATA = Path(__file__).resolve().parents[1] / "data" / "Telco-Customer-Churn.csv"

_FIELDS = [
    "MonthlyCharges", "tenure", "TotalCharges", "SeniorCitizen", "Partner", "Dependents",
    "PhoneService", "MultipleLines", "InternetService", "OnlineSecurity", "OnlineBackup",
    "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies", "Contract",
    "PaperlessBilling", "PaymentMethod",
]


def _load_payloads() -> list[dict]:
    df = pd.read_csv(DATA)
    df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce").fillna(0.0)
    rows = []
    for rec in df[_FIELDS].to_dict(orient="records"):
        rec["MonthlyCharges"] = float(rec["MonthlyCharges"])
        rec["TotalCharges"] = float(rec["TotalCharges"])
        rec["tenure"] = int(rec["tenure"])
        rec["SeniorCitizen"] = int(rec["SeniorCitizen"])
        rows.append(rec)
    return rows


PAYLOADS = _load_payloads()


class PredictUser(HttpUser):
    # Short think time: this is a throughput/latency probe, not a UI simulation.
    wait_time = between(0.05, 0.2)

    @task
    def predict(self) -> None:
        payload = random.choice(PAYLOADS)
        with self.client.post(
            "/api/v1/predictions/predict",
            json=payload,
            name="POST /api/v1/predictions/predict",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:120]}")
            elif "probability" not in resp.json():
                resp.failure("missing probability in response")
