from pydantic import BaseModel, Field
from typing import Literal

YesNo = Literal["Yes", "No"]
YesNoPhone = Literal["Yes", "No", "No phone service"]
YesNoInternet = Literal["Yes", "No", "No internet service"]


class PredictionRequest(BaseModel):
    MonthlyCharges: float = Field(..., ge=0, description="Average monthly billing amount")
    tenure: int = Field(..., ge=0, description="Months the customer has been with the company")
    TotalCharges: float = Field(..., ge=0, description="Total amount billed to the customer")
    SeniorCitizen: Literal[0, 1] = Field(..., description="1 if the customer is a senior citizen")

    Partner: YesNo
    Dependents: YesNo

    PhoneService: YesNo
    MultipleLines: YesNoPhone

    InternetService: Literal["No", "DSL", "Fiber optic"]
    OnlineSecurity: YesNoInternet
    OnlineBackup: YesNoInternet
    DeviceProtection: YesNoInternet
    TechSupport: YesNoInternet
    StreamingTV: YesNoInternet
    StreamingMovies: YesNoInternet

    Contract: Literal["Month-to-month", "One year", "Two year"]
    PaperlessBilling: YesNo
    PaymentMethod: Literal[
        "Electronic check",
        "Mailed check",
        "Bank transfer (automatic)",
        "Credit card (automatic)",
    ]


class PredictionResponse(BaseModel):
    probability: float
    isChurn: bool

