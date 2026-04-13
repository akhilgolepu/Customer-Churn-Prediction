from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.exceptions import ForbiddenError, UnauthorizedError
from services.auth_service import AuthUser

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(request: Request):
    return request.app.state.auth_service


def get_prediction_service(request: Request):
    return request.app.state.prediction_service


def get_job_service(request: Request):
    return request.app.state.job_service


def get_recommendation_service(request: Request):
    return request.app.state.recommendation_service


def get_feedback_service(request: Request):
    return request.app.state.feedback_service


def get_monitoring_service(request: Request):
    return request.app.state.monitoring_service


def get_model_registry_service(request: Request):
    return request.app.state.model_registry_service


def get_canary_service(request: Request):
    return request.app.state.canary_service


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth_service=Depends(get_auth_service),
) -> AuthUser:
    if not credentials:
        raise UnauthorizedError("Missing bearer token")
    return auth_service.get_user_from_access_token(credentials.credentials)


def require_roles(*roles: str):
    def _checker(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if roles and user.role not in roles:
            raise ForbiddenError("Insufficient role")
        return user

    return _checker
