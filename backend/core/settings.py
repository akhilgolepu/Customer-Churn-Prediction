from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_allowed_origins(value: str) -> list[str]:
    """Parse ALLOWED_ORIGINS from string (JSON array or comma-separated)"""
    if not value or not value.strip():
        return ["http://localhost:5173"]
    
    stripped = value.strip()
    
    # Try to parse as JSON array
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
    
    # Fall back to comma-separated list
    return [item.strip() for item in stripped.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Customer Churn Predictor"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    secret_key: str = "change-me-in-production"
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    jwt_algorithm: str = "HS256"

    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"],
        validation_alias="ALLOWED_ORIGINS_INTERNAL"  # Skip env parsing, handle manually
    )
    max_request_size_bytes: int = 2_000_000
    strict_cors: bool = True

    predict_rate_limit_per_minute: int = 30

    dependency_timeout_seconds: float = 3.0
    dependency_retry_count: int = 2
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_recovery_seconds: int = 15

    batch_worker_retry_count: int = 3
    schedule_quality_check_seconds: int = 900
    schedule_drift_report_seconds: int = 1800

    input_drift_alert_threshold: float = 0.20
    prediction_drift_alert_threshold: float = 0.15
    min_outcomes_for_performance_tracking: int = 20
    minimum_recall_threshold: float = 0.55
    sqlite_path: str = str((Path(__file__).resolve().parents[1] / "data" / "app.db"))

    database_backend: str = "sqlite"
    postgres_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/churn"
    default_org_id: str = "00000000-0000-0000-0000-000000000001"

    redis_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300

    object_storage_provider: str = "none"
    object_storage_bucket: str = ""
    object_storage_prefix: str = ""
    object_storage_local_path: str = str((Path(__file__).resolve().parents[1] / "data" / "objects"))
    azure_blob_account_url: str = ""
    azure_blob_credential: str = ""
    batch_upload_prefix: str = "batch/uploads"
    batch_report_prefix: str = "batch/reports"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def validate_allowed_origins(cls, value: Any) -> list[str]:
        # If value is already a list, just return it
        if isinstance(value, list):
            return value
        # Otherwise, parse as string
        if isinstance(value, str):
            return _parse_allowed_origins(value)
        return ["http://localhost:5173"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Manually handle ALLOWED_ORIGINS to avoid Pydantic env parsing errors
    allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    allowed_origins = _parse_allowed_origins(allowed_origins_raw) if allowed_origins_raw else ["http://localhost:5173"]
    
    return Settings(allowed_origins=allowed_origins)
