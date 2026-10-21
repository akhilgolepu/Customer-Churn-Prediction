"""Generate the synthetic CI sample: data/ci_sample.csv (+ golden predictions).

Why synthetic: the IBM Telco CSV has no clear data license (IBM's repository
license covers its code), so real rows are not committed. These 500 rows are
generated from a fixed seed with simple, documented rules:

  * category frequencies: fixed constants below (rounded aggregate shares of
    the Telco data; no individual row is copied);
  * consistency: no phone service <=> MultipleLines "No phone service", no
    internet <=> every add-on "No internet service" (ml/data_schema.py);
  * MonthlyCharges = base + per-service prices + noise; TotalCharges ~= tenure x
    MonthlyCharges (blank at tenure 0, as in the real data);
  * Churn ~ Bernoulli(shipped model's probability). The labels therefore say
    nothing about real-world accuracy; they only make the file a valid
    training-schema input.

data/ci_sample_golden.json stores the shipped model's calibrated probabilities
for every row; tests/ml/test_ci_sample.py fails if serving output drifts.

Usage:
    python scripts/ci/make_ci_sample.py            # rewrite both files
    python scripts/ci/make_ci_sample.py --golden   # only refresh golden predictions (after retraining)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from ml.calibration import load_for_model  # noqa: E402
from ml.data_schema import INTERNET_ADDONS, TRAINING_SCHEMA, validate_frame  # noqa: E402
from ml.preprocessing.preprocessing import load_artifacts, prepare_for_model, preprocess  # noqa: E402

SAMPLE = REPO_ROOT / "data" / "ci_sample.csv"
GOLDEN = REPO_ROOT / "data" / "ci_sample_golden.json"
MODEL = REPO_ROOT / "models" / "catboost_churn.cbm"
N_ROWS, SEED = 500, 2026

SHARES = {
    "gender": (["Female", "Male"], [0.50, 0.50]),
    "SeniorCitizen": ([0, 1], [0.84, 0.16]),
    "Partner": (["Yes", "No"], [0.48, 0.52]),
    "Dependents": (["Yes", "No"], [0.30, 0.70]),
    "PhoneService": (["Yes", "No"], [0.90, 0.10]),
    "InternetService": (["DSL", "Fiber optic", "No"], [0.34, 0.44, 0.22]),
    "Contract": (["Month-to-month", "One year", "Two year"], [0.55, 0.21, 0.24]),
    "PaperlessBilling": (["Yes", "No"], [0.59, 0.41]),
    "PaymentMethod": (["Electronic check", "Mailed check", "Bank transfer (automatic)", "Credit card (automatic)"],
                      [0.34, 0.23, 0.22, 0.21]),
}
ADDON_YES_SHARE = 0.40  # among internet customers
MULTILINE_YES_SHARE = 0.47  # among phone customers


def generate(rng: np.random.Generator) -> pd.DataFrame:
    df = pd.DataFrame({col: rng.choice(values, N_ROWS, p=p) for col, (values, p) in SHARES.items()})
    df.insert(0, "customerID", [f"SYN-{i:04d}" for i in range(N_ROWS)])
    # tenure depends on contract: longer contracts, longer tenure
    scale = df["Contract"].map({"Month-to-month": 12, "One year": 35, "Two year": 55})
    df["tenure"] = np.clip(np.round(rng.exponential(1.0, N_ROWS) * scale), 0, 72).astype(int)
    df["MultipleLines"] = np.where(df["PhoneService"] == "No", "No phone service",
                                   np.where(rng.random(N_ROWS) < MULTILINE_YES_SHARE, "Yes", "No"))
    for col in INTERNET_ADDONS:
        df[col] = np.where(df["InternetService"] == "No", "No internet service",
                           np.where(rng.random(N_ROWS) < ADDON_YES_SHARE, "Yes", "No"))
    base = df["InternetService"].map({"DSL": 45.0, "Fiber optic": 70.0, "No": 20.0})
    addons = sum((df[c] == "Yes").astype(float) for c in INTERNET_ADDONS) * 5.0
    lines = (df["MultipleLines"] == "Yes") * 5.0
    df["MonthlyCharges"] = np.round(base + addons + lines + rng.normal(0, 2.5, N_ROWS), 2).clip(18.25, None)
    total = df["tenure"] * df["MonthlyCharges"] * rng.uniform(0.95, 1.05, N_ROWS)
    df["TotalCharges"] = np.where(df["tenure"] == 0, np.nan, np.round(total, 2))
    return df


def score(df: pd.DataFrame) -> np.ndarray:
    from catboost import CatBoostClassifier

    features, cats = load_artifacts()
    x = prepare_for_model(preprocess(df.drop(columns=["customerID", "gender", "Churn"], errors="ignore")), features)
    for c in cats:
        x[c] = x[c].astype(str)
    model = CatBoostClassifier()
    model.load_model(str(MODEL))
    return load_for_model(MODEL).transform(model.predict_proba(x)[:, 1])


def write_golden(df: pd.DataFrame) -> None:
    p = score(df)
    GOLDEN.write_text(json.dumps({
        "model": "models/catboost_churn.cbm",
        "note": "Calibrated P(churn) of the shipped model per row of data/ci_sample.csv. Regenerate with "
                "`python scripts/ci/make_ci_sample.py --golden` after retraining.",
        "probabilities": [round(float(v), 10) for v in p],
    }, indent=1), encoding="utf-8")


def main(golden_only: bool) -> None:
    if golden_only:
        df = pd.read_csv(SAMPLE)
    else:
        rng = np.random.default_rng(SEED)
        df = generate(rng)
        df["Churn"] = np.where(rng.random(N_ROWS) < score(df), "Yes", "No")
        errors = validate_frame(df, TRAINING_SCHEMA)
        if errors:
            raise SystemExit("Generated sample fails TRAINING_SCHEMA: " + "; ".join(errors))
        df.to_csv(SAMPLE, index=False)
    write_golden(df)
    print(f"rows={len(df)} churn_rate={(df['Churn'] == 'Yes').mean():.3f} -> {SAMPLE.name}, {GOLDEN.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", action="store_true")
    main(ap.parse_args().golden)
