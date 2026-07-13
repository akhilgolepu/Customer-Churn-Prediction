from fastapi import APIRouter, Depends, Query

from core.dependencies import (
    get_feedback_service,
    get_prediction_service,
    get_recommendation_service,
    require_roles,
)
from schemas.feedback import FeedbackCreateRequest, FeedbackSummaryResponse, OutcomeCreateRequest
from schemas.prediction import ExplainResponse, HistoryResponse, PredictionRequest, PredictionResponse
from schemas.recommendations import RecommendationRequest, RecommendationResponse

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post("/predict", response_model=PredictionResponse)
async def predict(
    payload: PredictionRequest,
    threshold: float = Query(default=0.5, ge=0.0, le=1.0),
    prediction_service=Depends(get_prediction_service),
):
    return await prediction_service.predict(payload, threshold=threshold)


@router.post("/explain", response_model=ExplainResponse)
async def explain(
    payload: PredictionRequest,
    prediction_service=Depends(get_prediction_service),
):
    return await prediction_service.explain(payload)


@router.get("/history", response_model=HistoryResponse)
def history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_churn: bool | None = Query(default=None),
    prediction_service=Depends(get_prediction_service),
    _=Depends(require_roles("admin", "analyst", "viewer")),
):
    return prediction_service.history(page=page, page_size=page_size, is_churn=is_churn)


@router.post("/recommend", response_model=RecommendationResponse)
async def recommend(
    payload: RecommendationRequest,
    recommendation_service=Depends(get_recommendation_service),
    _=Depends(require_roles("admin", "analyst")),
):
    return await recommendation_service.recommend(customer=payload.customer, budget=payload.budget)


@router.post("/feedback", response_model=FeedbackSummaryResponse)
def add_feedback(
    payload: FeedbackCreateRequest,
    feedback_service=Depends(get_feedback_service),
    _=Depends(require_roles("admin", "analyst", "viewer")),
):
    feedback_service.add_feedback(
        prediction_id=payload.prediction_id,
        useful=payload.useful,
        comment=payload.comment,
    )
    return feedback_service.summary()


@router.post("/outcome", response_model=FeedbackSummaryResponse)
def add_outcome(
    payload: OutcomeCreateRequest,
    feedback_service=Depends(get_feedback_service),
    _=Depends(require_roles("admin", "analyst")),
):
    feedback_service.add_outcome(
        prediction_id=payload.prediction_id,
        actual_churn=payload.actual_churn,
        notes=payload.notes,
    )
    return feedback_service.summary()


@router.get("/feedback/summary", response_model=FeedbackSummaryResponse)
def feedback_summary(
    feedback_service=Depends(get_feedback_service),
    _=Depends(require_roles("admin", "analyst", "viewer")),
):
    return feedback_service.summary()
