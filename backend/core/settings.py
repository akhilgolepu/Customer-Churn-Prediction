from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Customer Churn Predictor"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    secret_key: str = "change-me-in-production"
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    jwt_algorithm: str = "HS256"

    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
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
    def parse_allowed_origins(cls, value: Any) -> list[str]:
        # Handle missing or None values
        if value is None or (isinstance(value, str) and not value.strip()):
            return ["http://localhost:5173"]
        
        if isinstance(value, list):
            return value
        
        if isinstance(value, str):
            stripped = value.strip()
            # Try to parse as JSON array
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except json.JSONDecodeError:
                    pass
            # Fall back to comma-separated list
            return [item.strip() for item in stripped.split(",") if item.strip()]
        
        return ["http://localhost:5173"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
