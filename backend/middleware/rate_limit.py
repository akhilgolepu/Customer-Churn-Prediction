from fastapi import Request
from fastapi.responses import JSONResponse

from core.cache import cache_client
from core.settings import get_settings


async def rate_limit_middleware(request: Request, call_next):
    settings = get_settings()
    path = request.url.path
    if path.endswith("/predict") or path.endswith("/explain"):
        ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:{ip}:{path}"
        hits = cache_client.incr_with_expiry(key, ttl_seconds=60)
        if hits > settings.predict_rate_limit_per_minute:
            return JSONResponse(
                status_code=429,
                content={
                    "code": "rate_limited",
                    "message": "Too many requests",
                    "request_id": getattr(request.state, "request_id", None),
                },
            )
    return await call_next(request)
