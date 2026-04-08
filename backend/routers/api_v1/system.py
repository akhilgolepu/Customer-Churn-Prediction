from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from core.cache import cache_client
from core.dependencies import get_monitoring_service, require_roles
from core.exceptions import AppError
from core.metrics import metrics_store
from core.settings import get_settings
from schemas.common import MessageResponse
from schemas.monitoring import MonitoringResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=MessageResponse)
def health():
    return {"message": "ok"}


@router.get("/ready", response_model=MessageResponse)
def ready(request: Request):
    settings = get_settings()

    if settings.database_backend.lower() == "postgres":
        session_factory = getattr(request.app.state, "postgres_session_factory", None)
        if session_factory is None:
            raise AppError(code="not_ready", message="Postgres session factory unavailable", status_code=503)

        try:
            with session_factory.session_scope() as session:
                session.execute(text("SELECT 1"))
        except Exception as exc:
            raise AppError(code="not_ready", message=f"Database not ready: {exc}", status_code=503)

    if settings.redis_enabled:
        redis_client = cache_client.redis_client
        if redis_client is None:
            raise AppError(code="not_ready", message="Redis client unavailable", status_code=503)
        try:
            redis_client.ping()
        except Exception as exc:
            raise AppError(code="not_ready", message=f"Redis not ready: {exc}", status_code=503)

    return {"message": "ready"}


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(_=Depends(require_roles("admin"))):
    snapshot = metrics_store.snapshot()
    avg_latency = (snapshot.total_latency_ms / snapshot.request_count) if snapshot.request_count else 0.0
    body = "\n".join(
        [
            "# TYPE app_requests_total counter",
            f"app_requests_total {snapshot.request_count}",
            "# TYPE app_errors_total counter",
            f"app_errors_total {snapshot.error_count}",
            "# TYPE app_avg_latency_ms gauge",
            f"app_avg_latency_ms {avg_latency:.2f}",
        ]
    )
    return body


@router.get("/monitoring", response_model=MonitoringResponse)
def monitoring(
    monitoring_service=Depends(get_monitoring_service),
    _=Depends(require_roles("admin", "analyst")),
):
    return monitoring_service.snapshot()
