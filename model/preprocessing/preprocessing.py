from typing import List
import json 
import os
import pandas as pd

FEATURE_LIST_PATH = os.path.join("G:\\23881A66E2\\Projects\\Customer_Churn_Predictor\\model\\artifacts\\feature_list.json")
CAT_COLS_PATH = os.path.join("G:\\23881A66E2\\Projects\\Customer_Churn_Predictor\\model\\artifacts\\cat_columns.json")

def load_artifacts(feature_list_path: str = FEATURE_LIST_PATH, 
                   cat_cols_path: str = CAT_COLS_PATH):
    """Load feature list and categorical columns from JSON files.
    

    Returns
    -------
    feature_list : List[str]
    cat_cols : List[str]
    """


    with open(feature_list_path, "r") as f:
        feature_list = json.load(f)
        
    with open(cat_cols_path, "r") as f:
        cat_cols = json.load(f)
        
    return feature_list, cat_cols


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
        max_tenure = int(df['tenure'].max())
    except Exception:
        max_tenure = 72

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
    sample_path = os.path.join("G:\\23881A66E2\\Projects\\Customer_Churn_Predictor\\data\\Telco-Customer-Churn.csv")
    if os.path.exists(sample_path):
        df_sample = pd.read_csv(sample_path)
        print("Loaded sample data, preprocessing...")
        df_p = preprocess(df_sample)
        features, cats = load_artifacts()
        df_ready = prepare_for_model(df_p, feature_list=features)
        print("Prepared dataframe shape:", df_ready.shape)
    else:
        print("No sample data found at:", sample_path)
