from pydantic import BaseModel

class PredictionRequest(BaseModel):
    MonthlyCharges: float
    tenure: int
    TotalCharges: float
    SeniorCitizen: int
    Contract: str
    InternetService: str
    PaymentMethod: str

class PredictionResponse(BaseModel):
    proibability: float
    isChurn: bool
