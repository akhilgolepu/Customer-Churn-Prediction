import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from schema import PredictionRequest, PredictionResponse
from model_loader import predict_proba, explain
from feature_engineering import engineer_features
import numpy as np
import math
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Customer Churn Predictor")

_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
allowed_origins = [o.strip() for o in _raw_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/predict", response_model=PredictionResponse)
def predict(
    data: PredictionRequest,
    threshold: float = Query(default=0.5, ge=0.0, le=1.0, description="Churn classification threshold"),
):
    try:
        df = engineer_features(data)
        probability = float(predict_proba(df))
        is_churn = probability >= threshold
        return {"probability": probability, "isChurn": is_churn}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/explain")
def explain_prediction(data: PredictionRequest):
    try:
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
        shap_list = [float(s) for s in np.array(shap_values).ravel().tolist()]

        drivers = [
            {"feature": f, "value": v, "impact": float(s)}
            for f, v, s in zip(features, values, shap_list)
        ]
        drivers = sorted(drivers, key=lambda x: abs(x["impact"]), reverse=True)

        return {"top_drivers": drivers[:5]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

