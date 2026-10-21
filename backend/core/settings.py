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

    model_path: str = str(
        Path(__file__).resolve().parents[2] / "models" / "catboost_churn.cbm"
    )

    secret_key: str = "change-me-in-production"

    # Seeded user passwords (ADMIN_PASSWORD, ANALYST_PASSWORD, VIEWER_PASSWORD).
    # Unset is only allowed when ENVIRONMENT=development, where insecure,
    # publicly known defaults are used; any other environment refuses to start
    # (see services/auth_service.py).
    admin_password: str | None = None
    analyst_password: str | None = None
    viewer_password: str | None = None
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
    schedule_retraining_enabled: bool = True
    schedule_retrain_poll_seconds: int = 1800
    schedule_retrain_force_interval_seconds: int = 86400
    schedule_retrain_cooldown_seconds: int = 21600

    input_drift_alert_threshold: float = 0.20
    prediction_drift_alert_threshold: float = 0.15
    min_outcomes_for_performance_tracking: int = 20
    minimum_recall_threshold: float = 0.55

    # Default decision threshold applied when a request does not pass ?threshold=.
    # 0.38 is the net-benefit optimum on out-of-fold calibrated validation scores
    # under the primary cost scenario in ml/training/threshold_analysis.py
    # (reports/evaluation/threshold_analysis.json); the closed-form break-even is 0.371. The
    # served score is a calibrated probability. Keep params.yaml
    # evaluation.decision_threshold equal to this (enforced by a test).
    decision_threshold: float = Field(default=0.38, ge=0.0, le=1.0)

    # Promotion gate (services/promotion_gate.py). The default evaluation set is
    # the full Telco CSV, which overlaps training data: it is a sanity gate, not
    # an unbiased estimate.
    promotion_eval_data_path: str = str(
        Path(__file__).resolve().parents[2] / "data" / "Telco-Customer-Churn.csv"
    )
    promotion_min_auc: float = 0.75
    # Floors at decision_threshold; guardrails well below the measured operating
    # point (test: precision 0.58, recall 0.69 at 0.38), not targets.
    promotion_min_precision: float = 0.40
    promotion_min_recall: float = 0.40
    promotion_min_f1: float = 0.45
    promotion_max_auc_drop: float = 0.02

    # Standing challenger: a logistic-regression model (ml/linear_model.py)
    # kept in the shadow slot whenever no other candidate is being tested. It is
    # scored on every request; with CANARY_ENABLED it also serves that share of
    # traffic. Relative paths resolve against the repository root.
    challenger_enabled: bool = True
    challenger_artifact_path: str = "models/logreg_challenger.json"
    challenger_version: str = "logreg-challenger"

    # GET /metrics (Prometheus). Public unless METRICS_TOKEN is set, then it needs
    # "Authorization: Bearer <token>" (Prometheus: authorization.credentials).
    metrics_token: str | None = None

    canary_enabled: bool = False
    canary_traffic_percent: int = 10
    canary_min_samples: int = 100
    canary_max_disagreement_rate: float = 0.35
    canary_rollback_cooldown_seconds: int = 600
    sqlite_path: str = str((Path(__file__).resolve().parents[1] / "data" / "app.db"))

    database_backend: str = "sqlite"
    postgres_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/churn"
    default_org_id: str = "00000000-0000-0000-0000-000000000001"
    run_postgres_migrations_on_startup: bool = True

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
    
    # Must be passed by its validation alias: allowed_origins is declared with
    # validation_alias="ALLOWED_ORIGINS_INTERNAL", so Settings(allowed_origins=...)
    # was silently ignored and ALLOWED_ORIGINS never took effect.
    return Settings(ALLOWED_ORIGINS_INTERNAL=allowed_origins)  # type: ignore[call-arg]  # pydantic validation_alias
