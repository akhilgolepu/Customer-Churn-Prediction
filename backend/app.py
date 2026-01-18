from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from schema import PredictionRequest, PredictionResponse
from model_loader import predict_proba, explain
from feature_engineering import engineer_features
import numpy as np
import math


app = FastAPI(title="Customer Churn Predictor")

CHURN_THRESHOLD = 0.5

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/predict", response_model=PredictionResponse)
def predict(data: PredictionRequest):
    df = engineer_features(data)

    probability = float(predict_proba(df))
    is_churn = probability >= CHURN_THRESHOLD

    return {
        "probability": probability,
        "isChurn": is_churn
    }

@app.post("/explain")
def explain_prediction(data: PredictionRequest):
    df = engineer_features(data)
    shap_values = explain(df)

    features = df.columns.tolist()
    row = df.iloc[0]

    def to_json_value(v):
        try:
            if isinstance(v, np.generic):
                v = v.item()
            elif isinstance(v, np.ndarray):
                v = v.tolist()
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return None
            return v
        except Exception:
            return str(v)

    values = [to_json_value(row[f]) for f in features]

    drivers = []

    shap_list = [float(s) for s in np.array(shap_values).ravel().tolist()]

    for f, v, s in zip(features, values, shap_list):
        drivers.append({
            "feature": f,
            "value": v,
            "impact": float(s)
        })
    
    drivers = sorted(drivers, key=lambda x: abs(x["impact"]), reverse=True)

    return {
        "top_drivers": drivers[:5]
    }
