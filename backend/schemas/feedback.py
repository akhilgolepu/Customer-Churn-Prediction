from pydantic import BaseModel, Field


class FeedbackCreateRequest(BaseModel):
    prediction_id: str = Field(min_length=1)
    useful: bool
    comment: str | None = None


class OutcomeCreateRequest(BaseModel):
    prediction_id: str = Field(min_length=1)
    actual_churn: bool
    notes: str | None = None


class FeedbackSummaryResponse(BaseModel):
    total_feedback: int
    useful_count: int
    not_useful_count: int
    useful_ratio: float
    outcomes_recorded: int
