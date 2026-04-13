from typing import List
import json
import os
from pathlib import Path
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ARTIFACT_DIR = _REPO_ROOT / "model" / "artifacts"

FEATURE_LIST_PATH = _ARTIFACT_DIR / "feature_list.json"
CAT_COLS_PATH = _ARTIFACT_DIR / "cat_columns.json"
PREPROCESSING_SPEC_PATH = _ARTIFACT_DIR / "preprocessing_spec.json"


def load_artifacts(
    feature_list_path: str | Path = FEATURE_LIST_PATH,
    cat_cols_path: str | Path = CAT_COLS_PATH,
):
    """Load feature list and categorical columns from JSON files.
    

    Returns
    -------
    feature_list : List[str]
    cat_cols : List[str]
    """

    feature_list_path = Path(feature_list_path)
    cat_cols_path = Path(cat_cols_path)

    with feature_list_path.open("r", encoding="utf-8") as f:
        feature_list = json.load(f)

    with cat_cols_path.open("r", encoding="utf-8") as f:
        cat_cols = json.load(f)

    return feature_list, cat_cols


def build_preprocessing_spec() -> dict:
    """Return a stable, serializable preprocessing specification.

    This spec is packaged with model artifacts to make preprocessing behavior
    versioned and reproducible across environments.
    """

    return {
        "schema_version": "1.0.0",
        "module": "model.preprocessing.preprocessing",
        "engineered_features": {
            "TotalServices": {
                "type": "count_yes",
                "source_columns": [
                    "OnlineSecurity",
                    "OnlineBackup",
                    "DeviceProtection",
                    "TechSupport",
                    "StreamingTV",
                    "StreamingMovies",
                ],
            },
            "IsFiberCustomer": {
                "type": "equals",
                "source_column": "InternetService",
                "value": "Fiber optic",
                "true_as": 1,
                "false_as": 0,
            },
            "IsMonthToMonth": {
                "type": "equals",
                "source_column": "Contract",
                "value": "Month-to-month",
                "true_as": 1,
                "false_as": 0,
            },
            "TechIssueRisk": {
                "type": "and",
                "conditions": [
                    {"column": "InternetService", "operator": "!=", "value": "No"},
                    {"column": "TechSupport", "operator": "==", "value": "No"},
                ],
                "true_as": 1,
                "false_as": 0,
            },
            "PaymentRisk": {
                "type": "equals",
                "source_column": "PaymentMethod",
                "value": "Electronic check",
                "true_as": 1,
                "false_as": 0,
            },
            "HasPhoneAndInternet": {
                "type": "and",
                "conditions": [
                    {"column": "PhoneService", "operator": "==", "value": "Yes"},
                    {"column": "InternetService", "operator": "!=", "value": "No"},
                ],
                "true_as": 1,
                "false_as": 0,
            },
            "TenureGroup": {
                "type": "cut",
                "source_column": "tenure",
                "bins": [0, 6, 12, 24, 48, "MAX_TENURE"],
                "labels": ["0-6", "6-12", "12-24", "24-48", "48+"],
                "right": True,
                "include_lowest": True,
            },
        },
    }


def save_preprocessing_spec(output_path: str | Path = PREPROCESSING_SPEC_PATH) -> Path:
    """Persist preprocessing specification as JSON and return the file path."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    spec = build_preprocessing_spec()
    with path.open("w", encoding="utf-8") as fp:
        json.dump(spec, fp, indent=2)
    return path


def preprocess(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Apply the same preprocessing steps as in training.
    
    - Create Engineered Features: TotalServices, IsFiberCustomer, IsMonthToMonth,
    TechIssueRisk, PaymentRisk, HasPhoneAndInternet, TenureGroup  

    Parameters
    ----------
    raw_df : pd.DataFrame
        Raw input dataframe.

    Returns
    -------
    pd.DataFrame
        Preprocessed dataframe with new features.  
    """

    df = raw_df.copy()
    service_cols = [
        "OnlineSecurity", "OnlineBackup", "DeviceProtection",
        "TechSupport", "StreamingTV", "StreamingMovies"
    ]

    df["TotalServices"] = (df[service_cols] == "Yes").sum(axis=1)

    df["IsFiberCustomer"] = (df["InternetService"] == "Fiber optic").astype(int)
    df["IsMonthToMonth"] = (df["Contract"] == "Month-to-month").astype(int)
    df["TechIssueRisk"] = ((df["InternetService"] != "No") & (df["TechSupport"] == "No")).astype(int)
    df["PaymentRisk"] = (df["PaymentMethod"] == "Electronic check").astype(int)
    df["HasPhoneAndInternet"] = ((df["PhoneService"] == "Yes") & (df["InternetService"] != "No")).astype(int)

    try:
        max_tenure = int(df["tenure"].max())
    except Exception:
        max_tenure = 72

    # Ensure the final bin edge is always greater than 48 so bins remain monotonic
    # even when small samples contain only low-tenure customers.
    max_tenure = max(max_tenure, 49)

    tenure_bins = [0, 6, 12, 24, 48, max_tenure]
    tenure_labels = ["0-6", "6-12", "12-24", "24-48", "48+"]

    df["TenureGroup"] = pd.cut(
        df["tenure"],
        bins=tenure_bins,
        labels=tenure_labels,
        right=True,
        include_lowest=True
    )

    return df


def prepare_for_model(df: pd.DataFrame, feature_list: List[str]) -> pd.DataFrame:
    """Prepare dataframe exactly ordered as feature_list and with missing columns handled.
    
    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe after preprocessing.
    feature_list : List[str]
        If provided, will reorder and add muissing columns filled with 0/NaN.
        If None, the function will try to load artifacts/feature_list.json

    Returns
    -------
    pd.DataFrame
        Dataframe ready for model input.

    """

    df_proc = df.copy()

    if feature_list is None:
        feature_list, _ = load_artifacts()
    
    if feature_list is None:
        raise ValueError("feature_list is not provided and could not be loaded from artifacts.")
    
    for col in feature_list:
        if col not in df_proc.columns:
            df_proc[col] = 0
    
    df_proc = df_proc[feature_list]

    return df_proc

if __name__ == "__main__":
    sample_path = _REPO_ROOT / "data" / "Telco-Customer-Churn.csv"
    if os.path.exists(sample_path):
        df_sample = pd.read_csv(sample_path)
        print("Loaded sample data, preprocessing...")
        df_p = preprocess(df_sample)
        features, cats = load_artifacts()
        df_ready = prepare_for_model(df_p, feature_list=features)
        spec_path = save_preprocessing_spec()
        print("Prepared dataframe shape:", df_ready.shape)
        print("Saved preprocessing spec:", spec_path)
    else:
        print("No sample data found at:", sample_path)
