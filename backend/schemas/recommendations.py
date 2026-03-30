from pydantic import BaseModel, Field

from schemas.prediction import PredictionRequest


class RecommendationRequest(BaseModel):
    customer: PredictionRequest
    budget: float = Field(default=100.0, ge=0)


class RecommendedAction(BaseModel):
    key: str
    label: str
    rationale: str
    expected_impact_score: float
    confidence: float
    estimated_cost: float
    impact_per_budget: float


class RecommendationResponse(BaseModel):
    prediction_id: str
    probability: float
    risk_tier: str
    actions: list[RecommendedAction]
    selected_actions: list[RecommendedAction]
    total_selected_cost: float
    total_expected_impact: float
