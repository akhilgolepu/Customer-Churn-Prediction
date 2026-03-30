from fastapi import APIRouter, Query

from schemas.prediction import ExplainResponse, PredictionRequest, PredictionResponse

router = APIRouter(tags=["legacy"])


@router.post("/predict", response_model=PredictionResponse)
async def legacy_predict(
    payload: PredictionRequest,
    threshold: float = Query(default=0.5, ge=0.0, le=1.0),
):
    # Compatibility endpoint for existing frontend clients.
    from app_factory import app_state

    return await app_state.prediction_service.predict(payload, threshold)


@router.post("/explain", response_model=ExplainResponse)
async def legacy_explain(payload: PredictionRequest):
    from app_factory import app_state

    return await app_state.prediction_service.explain(payload)
