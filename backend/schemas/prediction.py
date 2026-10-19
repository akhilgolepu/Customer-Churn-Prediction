from typing import Literal

from pydantic import BaseModel, Field, model_validator

from model.data_schema import consistency_errors

YesNo = Literal["Yes", "No"]
YesNoPhone = Literal["Yes", "No", "No phone service"]
YesNoInternet = Literal["Yes", "No", "No internet service"]


class PredictionRequest(BaseModel):
    MonthlyCharges: float = Field(..., ge=0)
    tenure: int = Field(..., ge=0)
    TotalCharges: float = Field(..., ge=0)
    SeniorCitizen: Literal[0, 1]

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

    @model_validator(mode="after")
    def _consistent_services(self):
        # Same rule table as the pandera schemas (model/data_schema.py); plain
        # Python here because pandera adds ~24 ms per call.
        errors = consistency_errors(self.model_dump())
        if errors:
            raise ValueError("; ".join(errors))
        return self


class PredictionResponse(BaseModel):
    predictionId: str
    probability: float
    isChurn: bool
    activeProbability: float | None = None
    shadowProbability: float | None = None
    variant: str | None = None


class Driver(BaseModel):
    feature: str
    value: str | int | float | None
    impact: float


class ExplainResponse(BaseModel):
    top_drivers: list[Driver]


class HistoryRecord(BaseModel):
    id: str
    created_at: float
    probability: float
    isChurn: bool
    threshold: float


class BatchDownloadResponse(BaseModel):
    filename: str
    content_type: str


class HistoryResponse(BaseModel):
    items: list[HistoryRecord]
    page: int
    page_size: int
    total: int
