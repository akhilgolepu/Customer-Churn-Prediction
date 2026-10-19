from fastapi import APIRouter, Depends

from core.dependencies import get_canary_service, get_model_registry_service, require_roles
from schemas.model_registry import (
    ModelMutationResponse,
    ModelRegistryResponse,
    PromoteModelRequest,
    RegisterModelRequest,
    RollbackRequest,
    ShadowTestRequest,
)

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=ModelRegistryResponse)
def list_models(
    model_registry_service=Depends(get_model_registry_service),
    _=Depends(require_roles("admin", "analyst", "viewer")),
):
    return model_registry_service.list_registry()


@router.post("/register")
def register_model(
    payload: RegisterModelRequest,
    model_registry_service=Depends(get_model_registry_service),
    _=Depends(require_roles("admin")),
):
    return model_registry_service.register_candidate(
        version=payload.version,
        metrics=payload.metrics,
        artifact_path=payload.artifact_path,
    )


@router.post("/shadow", response_model=ModelMutationResponse)
def start_shadow(
    payload: ShadowTestRequest,
    model_registry_service=Depends(get_model_registry_service),
    canary_service=Depends(get_canary_service),
    _=Depends(require_roles("admin")),
):
    result = model_registry_service.start_shadow_test(payload.candidate_model_id)
    # New candidate -> fresh canary counters (and re-enable if configured on).
    canary_service.reset()
    return result


@router.post("/promote", response_model=ModelMutationResponse)
def promote(
    payload: PromoteModelRequest,
    model_registry_service=Depends(get_model_registry_service),
    user=Depends(require_roles("admin")),
):
    # 409 promotion_blocked when the validation gate has blockers (see promotion_gate.py).
    return model_registry_service.promote_candidate(
        payload.candidate_model_id,
        override_gate=payload.override_gate,
        override_reason=payload.override_reason,
        actor=user.username,
    )


@router.post("/rollback", response_model=ModelMutationResponse)
def rollback(
    payload: RollbackRequest,
    model_registry_service=Depends(get_model_registry_service),
    _=Depends(require_roles("admin")),
):
    return model_registry_service.rollback(target_model_id=payload.target_model_id)
