from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import os
from typing import Any

from jose import JWTError, jwt

from core.exceptions import UnauthorizedError
from core.settings import get_settings

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return base64.b64encode(salt + derived).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    raw = base64.b64decode(password_hash.encode("utf-8"))
    salt, stored = raw[:16], raw[16:]
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(stored, derived)


def _create_token(subject: str, role: str, expires_delta: timedelta, token_type: str) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "exp": datetime.now(tz=timezone.utc) + expires_delta,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, role: str) -> str:
    settings = get_settings()
    return _create_token(subject, role, timedelta(minutes=settings.access_token_minutes), "access")


def create_refresh_token(subject: str, role: str) -> str:
    settings = get_settings()
    return _create_token(subject, role, timedelta(days=settings.refresh_token_days), "refresh")


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise UnauthorizedError("Invalid token") from exc

    if expected_type and payload.get("type") != expected_type:
        raise UnauthorizedError("Invalid token type")
    return payload
