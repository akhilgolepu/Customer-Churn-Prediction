from fastapi import APIRouter, Depends

from core.dependencies import get_auth_service, get_current_user
from schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, auth_service=Depends(get_auth_service)):
    return auth_service.login(payload.username, payload.password)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, auth_service=Depends(get_auth_service)):
    return auth_service.refresh(payload.refresh_token)


@router.get("/me", response_model=UserInfo)
def me(current_user=Depends(get_current_user)):
    return {"username": current_user.username, "role": current_user.role}
