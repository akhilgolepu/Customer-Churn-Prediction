import asyncio
import logging
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.exception_handlers import register_exception_handlers
from core.logging_config import configure_logging
from core.settings import get_settings
from middleware.rate_limit import rate_limit_middleware
from middleware.request_context import request_context_middleware
from middleware.request_size_limit import request_size_limit_middleware
from middleware.security_headers import security_headers_middleware
from model_loader import MODEL_PATH
from db.base import Base
from db.bootstrap import ensure_postgres_baseline
from db.session import PostgresSessionFactory
from repositories.feedback_repository import FeedbackRepository
from repositories.job_repository import JobRepository
from repositories.model_registry_repository import ModelRegistryRepository
from repositories.monitoring_repository import MonitoringRepository
from repositories.prediction_repository import PredictionRepository
from repositories.postgres_feedback_repository import PostgresFeedbackRepository
from repositories.postgres_job_repository import PostgresJobRepository
from repositories.postgres_model_registry_repository import PostgresModelRegistryRepository
from repositories.postgres_monitoring_repository import PostgresMonitoringRepository
from repositories.postgres_prediction_repository import PostgresPredictionRepository
from repositories.sqlite_store import SQLiteStore
from routers.api_v1.auth import router as auth_router
from routers.api_v1.jobs import router as jobs_router
from routers.api_v1.models import router as models_router
from routers.api_v1.predictions import router as predictions_router
from routers.api_v1.system import router as system_router
from routers.legacy import router as legacy_router
from services.auth_service import AuthService
from services.feedback_service import FeedbackService
from services.job_service import JobService, SchedulerService
from services.model_registry_service import ModelRegistryService
from services.monitoring_service import MonitoringService
from services.prediction_service import PredictionService
from services.recommendation_service import RecommendationService
from storage.factory import build_object_storage


@dataclass
class AppState:
    auth_service: AuthService
    prediction_service: PredictionService
    job_service: JobService
    scheduler_service: SchedulerService
    recommendation_service: RecommendationService
    feedback_service: FeedbackService
    monitoring_service: MonitoringService
    model_registry_service: ModelRegistryService
    worker_task: asyncio.Task | None = None
    quality_task: asyncio.Task | None = None
    drift_task: asyncio.Task | None = None


app_state: AppState


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(title=settings.app_name)

    effective_org_id = settings.default_org_id
    if settings.database_backend.lower() == "postgres":
        session_factory = PostgresSessionFactory(settings.postgres_url)
        effective_org_id = ensure_postgres_baseline(session_factory, settings.default_org_id)
        Base.metadata.create_all(bind=session_factory.engine)
        feedback_repo = PostgresFeedbackRepository(session_factory=session_factory, org_id=effective_org_id)
        monitoring_repo = PostgresMonitoringRepository(session_factory=session_factory, org_id=effective_org_id)
        model_registry_repo = PostgresModelRegistryRepository(
            session_factory=session_factory,
            org_id=effective_org_id,
            default_artifact_path=str(MODEL_PATH),
        )
        prediction_repo = PostgresPredictionRepository(session_factory=session_factory, org_id=effective_org_id)
        job_repo = PostgresJobRepository(session_factory=session_factory, org_id=effective_org_id)
    else:
        prediction_repo = PredictionRepository()
        job_repo = JobRepository()
        store = SQLiteStore(settings.sqlite_path)
        feedback_repo = FeedbackRepository(store=store)
        monitoring_repo = MonitoringRepository(store=store)
        model_registry_repo = ModelRegistryRepository(store=store, default_artifact_path=str(MODEL_PATH))

    auth_service = AuthService()
    prediction_service = PredictionService(repo=prediction_repo)
    recommendation_service = RecommendationService(prediction_service=prediction_service)
    feedback_service = FeedbackService(repo=feedback_repo)
    monitoring_service = MonitoringService(
        prediction_repo=prediction_repo,
        feedback_repo=feedback_repo,
        monitoring_repo=monitoring_repo,
    )
    model_registry_service = ModelRegistryService(repo=model_registry_repo)
    object_storage = build_object_storage()
    job_service = JobService(repo=job_repo, prediction_service=prediction_service, object_storage=object_storage)
    scheduler_service = SchedulerService(job_service=job_service)

    global app_state
    app_state = AppState(
        auth_service=auth_service,
        prediction_service=prediction_service,
        job_service=job_service,
        scheduler_service=scheduler_service,
        recommendation_service=recommendation_service,
        feedback_service=feedback_service,
        monitoring_service=monitoring_service,
        model_registry_service=model_registry_service,
    )

    app.state.auth_service = auth_service
    app.state.prediction_service = prediction_service
    app.state.job_service = job_service
    app.state.recommendation_service = recommendation_service
    app.state.feedback_service = feedback_service
    app.state.monitoring_service = monitoring_service
    app.state.model_registry_service = model_registry_service

    app.middleware("http")(request_context_middleware)
    app.middleware("http")(request_size_limit_middleware)
    app.middleware("http")(rate_limit_middleware)
    app.middleware("http")(security_headers_middleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=settings.strict_cors,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    )

    register_exception_handlers(app)

    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(predictions_router, prefix=settings.api_prefix)
    app.include_router(jobs_router, prefix=settings.api_prefix)
    app.include_router(models_router, prefix=settings.api_prefix)
    app.include_router(system_router, prefix=settings.api_prefix)
    app.include_router(legacy_router)

    @app.on_event("startup")
    async def startup_event() -> None:
        logging.getLogger(__name__).info("Application startup complete")
        app_state.worker_task = asyncio.create_task(job_service.worker_loop())
        app_state.quality_task = asyncio.create_task(scheduler_service.quality_check_loop())
        app_state.drift_task = asyncio.create_task(scheduler_service.drift_report_loop())

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        for task in [app_state.worker_task, app_state.quality_task, app_state.drift_task]:
            if task:
                task.cancel()

    return app
