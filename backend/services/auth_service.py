from dataclasses import dataclass
import logging

from core.cache import cache_client
from core.exceptions import UnauthorizedError
from core.settings import get_settings
from core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password


logger = logging.getLogger(__name__)

# INSECURE, publicly known defaults. Used only when ENVIRONMENT=development and
# the corresponding *_PASSWORD variable is unset.
DEV_DEFAULT_PASSWORDS = {"admin": "admin123", "analyst": "analyst123", "viewer": "viewer123"}
INSECURE_DEFAULT_SECRET_KEY = "change-me-in-production"
_ROLES = {"admin": "admin", "analyst": "analyst", "viewer": "viewer"}


class InsecureConfigurationError(RuntimeError):
    pass


def resolve_seed_passwords(settings) -> dict[str, str]:
    """Passwords for the seeded users, from settings / environment.

    Outside ENVIRONMENT=development every password must be set explicitly and
    must not be one of the published development defaults.
    """
    configured = {
        "admin": settings.admin_password,
        "analyst": settings.analyst_password,
        "viewer": settings.viewer_password,
    }
    is_dev = settings.environment.strip().lower() == "development"
    problems = []
    resolved = {}
    for user, password in configured.items():
        if password:
            if not is_dev and password == DEV_DEFAULT_PASSWORDS[user]:
                problems.append(f"{user.upper()}_PASSWORD is the published development default")
            resolved[user] = password
        elif is_dev:
            logger.warning("%s_PASSWORD not set; using the INSECURE development default", user.upper())
            resolved[user] = DEV_DEFAULT_PASSWORDS[user]
        else:
            problems.append(f"{user.upper()}_PASSWORD is not set")
    if not is_dev and settings.secret_key == INSECURE_DEFAULT_SECRET_KEY:
        problems.append("SECRET_KEY is the published default")
    if problems:
        raise InsecureConfigurationError(
            f"Refusing to start with ENVIRONMENT={settings.environment}: " + "; ".join(problems)
        )
    return resolved


@dataclass
class AuthUser:
    username: str
    role: str


class AuthService:
    def __init__(self) -> None:
        settings = get_settings()
        # Seed users; passwords come from the environment (resolve_seed_passwords).
        self._users = {
            user: {"password_hash": hash_password(password), "role": _ROLES[user]}
            for user, password in resolve_seed_passwords(settings).items()
        }
        self._cache_ttl = settings.cache_ttl_seconds

    def _get_user_record(self, username: str) -> dict | None:
        # Not cached: the records are already in memory, and caching them kept a
        # replaced password valid until the TTL expired (and put password hashes
        # into Redis when it is enabled).
        return self._users.get(username)

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
