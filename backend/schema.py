from pydantic import BaseModel

class PredictionRequest(BaseModel):
    MonthlyCharges: float
    tenure: int
    TotalCharges: float
    SeniorCitizen: int
    Contract: str
    InternetService: str
    PaymentMethod: str
    PhoneService: str
    MultipleLines: str
    OnlineSecurity: str
    OnlineBackup: str
    DeviceProtection: str
    TechSupport: str
    StreamingTV: str
    StreamingMovies: str
    Partner: str
    Dependents: str
    PaperlessBilling: str

class PredictionResponse(BaseModel):
    probability: float
    isChurn: bool
