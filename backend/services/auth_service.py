from dataclasses import dataclass

from core.cache import cache_client
from core.exceptions import UnauthorizedError
from core.settings import get_settings
from core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password


@dataclass
class AuthUser:
    username: str
    role: str


class AuthService:
    def __init__(self) -> None:
        # Seed users. In production, move to DB/secret store.
        self._users = {
            "admin": {"password_hash": hash_password("admin123"), "role": "admin"},
            "analyst": {"password_hash": hash_password("analyst123"), "role": "analyst"},
            "viewer": {"password_hash": hash_password("viewer123"), "role": "viewer"},
        }
        self._cache_ttl = get_settings().cache_ttl_seconds

    def _get_user_record(self, username: str) -> dict | None:
        cache_key = f"auth:user:{username}"
        cached = cache_client.get_json(cache_key)
        if cached is not None:
            return cached

        record = self._users.get(username)
        if record is not None:
            cache_client.set_json(cache_key, record, self._cache_ttl)
        return record

    def login(self, username: str, password: str) -> dict[str, str]:
        record = self._get_user_record(username)
        if not record or not verify_password(password, record["password_hash"]):
            raise UnauthorizedError("Invalid username or password")

        role = record["role"]
        return {
            "access_token": create_access_token(subject=username, role=role),
            "refresh_token": create_refresh_token(subject=username, role=role),
            "token_type": "bearer", # nosec B105
        }

    def refresh(self, refresh_token: str) -> dict[str, str]:
        cache_key = f"auth:refresh:{refresh_token}"
        payload = cache_client.get_json(cache_key)
        if payload is None:
            payload = decode_token(refresh_token, expected_type="refresh")
            cache_client.set_json(cache_key, payload, self._cache_ttl)
        subject = str(payload.get("sub"))
        role = str(payload.get("role"))
        return {
            "access_token": create_access_token(subject=subject, role=role),
            "refresh_token": create_refresh_token(subject=subject, role=role),
            "token_type": "bearer", # nosec B105
        }

    def get_user_from_access_token(self, token: str) -> AuthUser:
        cache_key = f"auth:access:{token}"
        payload = cache_client.get_json(cache_key)
        if payload is None:
            payload = decode_token(token, expected_type="access")
            cache_client.set_json(cache_key, payload, self._cache_ttl)
        return AuthUser(username=str(payload.get("sub")), role=str(payload.get("role")))
