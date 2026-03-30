from fastapi import Request
from fastapi.responses import JSONResponse

from core.settings import get_settings


async def request_size_limit_middleware(request: Request, call_next):
    settings = get_settings()
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.max_request_size_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "code": "payload_too_large",
                "message": "Request payload exceeds allowed size",
                "request_id": getattr(request.state, "request_id", None),
            },
        )
    return await call_next(request)
