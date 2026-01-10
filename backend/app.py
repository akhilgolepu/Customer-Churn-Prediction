from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from schema import PredictionRequest
from model_loader import predict_proba
from feature_engineering import engineer_features


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

    probability = predict_proba(df)
    is_churn = probability >= CHURN_THRESHOLD

    return {
        "probability": probability,
        "isChurn": is_churn
    }