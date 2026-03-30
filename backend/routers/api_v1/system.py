from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from core.dependencies import get_monitoring_service, require_roles
from core.metrics import metrics_store
from schemas.common import MessageResponse
from schemas.monitoring import MonitoringResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=MessageResponse)
def health():
    return {"message": "ok"}


@router.get("/ready", response_model=MessageResponse)
def ready():
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
