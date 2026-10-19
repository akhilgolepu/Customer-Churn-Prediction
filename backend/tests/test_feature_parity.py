"""Training/serving feature parity.

The training pipeline (model.preprocessing.preprocess) works on a DataFrame; the
API (backend.feature_engineering.engineer_features) works on one request. They
must produce identical model inputs. A past mismatch in TotalServices and
TechIssueRisk silently skewed live predictions, so this guards it.

Uses synthetic rows (no dataset needed), so it also runs in CI where the
DVC-tracked CSV is absent.
"""

from __future__ import annotations

import itertools

import pandas as pd

from feature_engineering import engineer_features
from model.preprocessing.preprocessing import load_artifacts, prepare_for_model, preprocess
from schemas.prediction import PredictionRequest

TENURES = [0, 1, 6, 7, 12, 13, 24, 25, 48, 49, 72]  # every TenureGroup boundary, both sides
INTERNET = ["No", "DSL", "Fiber optic"]
SERVICE_VALUES = {"No": ["No internet service"], "DSL": ["Yes", "No"], "Fiber optic": ["Yes", "No"]}


def _rows() -> list[dict]:
    rows = []
    for tenure, internet, phone, contract, payment in itertools.product(
        TENURES,
        INTERNET,
        ["Yes", "No"],
        ["Month-to-month", "One year", "Two year"],
        ["Electronic check", "Mailed check"],
    ):
        for support in SERVICE_VALUES[internet]:
            other = SERVICE_VALUES[internet][0]
            rows.append(
                {
                    "MonthlyCharges": 55.5,
                    "tenure": tenure,
                    "TotalCharges": 55.5 * max(tenure, 1),
                    "SeniorCitizen": tenure % 2,
                    "Partner": "Yes" if tenure % 3 == 0 else "No",
                    "Dependents": "No",
                    "PhoneService": phone,
                    "MultipleLines": "No phone service" if phone == "No" else "No",
                    "InternetService": internet,
                    "OnlineSecurity": other,
                    "OnlineBackup": support,
                    "DeviceProtection": other,
                    "TechSupport": support,
                    "StreamingTV": support,
                    "StreamingMovies": other,
                    "Contract": contract,
                    "PaperlessBilling": "Yes",
                    "PaymentMethod": payment,
                }
            )
    return rows


def test_serving_features_match_training_features_for_edge_cases() -> None:
    rows = _rows()
    feature_list, _ = load_artifacts()

    training = prepare_for_model(preprocess(pd.DataFrame(rows)), feature_list).reset_index(drop=True).astype(str)
    serving = pd.concat(
        [engineer_features(PredictionRequest(**row))[feature_list] for row in rows],
        ignore_index=True,
    ).astype(str)

    assert list(training.columns) == list(serving.columns) == feature_list
    mismatched = [
        (column, int((training[column] != serving[column]).sum()))
        for column in feature_list
        if not training[column].equals(serving[column])
    ]
    assert not mismatched, f"training/serving skew in: {mismatched}"
    assert len(rows) > 500  # make sure the grid actually exercised something
