import time
import uuid

from fastapi import Request

from core.metrics import metrics_store, now_ms


async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    started = now_ms()
    response = await call_next(request)
    latency = now_ms() - started
    is_error = response.status_code >= 400
    metrics_store.observe_request(latency_ms=latency, is_error=is_error)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = str(round(latency, 2))
    response.headers["X-Response-Timestamp"] = str(int(time.time()))
    return response
