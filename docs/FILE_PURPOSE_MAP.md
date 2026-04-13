# File Purpose Map

Date: 2026-04-11
Project: Customer Churn Predictor

## Root

- README.md: Project overview, setup, and deployment notes.
- package.json, package-lock.json: Root Node scripts/dependencies.
- requirements.txt: Root Python requirements (lightweight/meta usage).
- .gitignore: Git exclusions for generated artifacts and local state.
- .dvc/, .dvcignore: DVC repository metadata and ignore rules.

## Backend

### Entry and runtime wiring

- backend/app.py: ASGI entrypoint for FastAPI.
- backend/app_factory.py: Central app composition (settings, repos, services, routers, middleware).
- backend/requirements.txt: Backend Python dependencies.
- backend/.env.example: Environment template.
- backend/.env: Local environment values.

### Core

- backend/core/settings.py: Typed runtime configuration and env parsing.
- backend/core/security.py: JWT/password/security helpers.
- backend/core/dependencies.py: FastAPI dependency providers.
- backend/core/exceptions.py: Custom exception types.
- backend/core/exception_handlers.py: Global error response mapping.
- backend/core/logging_config.py: Structured logging setup.
- backend/core/metrics.py: Request metrics primitives.
- backend/core/cache.py: Redis/local cache abstraction.
- backend/core/migrations.py: Startup migration runner.

### Database and migrations

- backend/db/base.py: SQLAlchemy declarative base.
- backend/db/session.py: Postgres engine/session factory.
- backend/db/models.py: ORM models (tenancy, predictions, jobs, feedback, audit, model registry).
- backend/db/bootstrap.py: Baseline org/roles initialization for Postgres mode.
- backend/db/postgres_schema.sql: Transactional schema SQL blueprint.
- backend/db/reporting.sql: Analytics/materialized-view SQL.
- backend/db/alembic.ini: Alembic config.
- backend/db/alembic/env.py: Migration execution environment.
- backend/db/alembic/versions/0001_initial_schema.py: Initial migration.
- backend/db/alembic/versions/0002_job_runs_and_indexes.py: Durable jobs/indexes migration.

### API layer

- backend/routers/api_v1/auth.py: Login/refresh/profile endpoints.
- backend/routers/api_v1/predictions.py: Predict/explain/history/feedback endpoints.
- backend/routers/api_v1/jobs.py: Batch/retrain/report jobs endpoints.
- backend/routers/api_v1/models.py: Model lifecycle endpoints.
- backend/routers/api_v1/system.py: Health/readiness/metrics/monitoring endpoints.
- backend/routers/legacy.py: Legacy compatibility routes.

### Business services

- backend/services/auth_service.py: Authentication/token logic.
- backend/services/prediction_service.py: Prediction and explanation orchestration.
- backend/services/recommendation_service.py: Recommendation generation logic.
- backend/services/job_service.py: Async jobs queue/worker and schedulers.
- backend/services/feedback_service.py: Feedback/outcome orchestration.
- backend/services/monitoring_service.py: Drift/performance snapshot logic.
- backend/services/model_registry_service.py: Candidate/shadow/promote/rollback operations.
- backend/services/audit_service.py: Audit event logging facade.

### Persistence repositories

- backend/repositories/\*\_repository.py: Data-access implementations.
- backend/repositories/postgres\_\*.py: Postgres durable repositories.
- backend/repositories/sqlite_store.py + non-postgres repositories: SQLite/local mode repositories.

### Middleware and schemas

- backend/middleware/\*.py: Request context, rate limits, size limits, security headers.
- backend/schemas/\*.py: Pydantic request/response models.

### Model and storage integration

- backend/feature_engineering.py: Inference-time feature transformation.
- backend/model_loader.py: Model loading/inference/explain/model switch.
- backend/storage/adapters.py, backend/storage/factory.py: Object storage abstraction and provider wiring.

## Frontend

### App shell and pages

- client/src/main.tsx: React bootstrap.
- client/src/App.tsx: Top-level app shell.
- client/src/pages/Dashboard.tsx: Primary product UI page.

### UI components

- client/src/components/ChurnForm.tsx: Input form and validation UX.
- client/src/components/PredictionCard.tsx: Prediction and explanation output card.
- client/src/components/Charts.tsx: Visualization panels.
- client/src/components/ui/\*.tsx: Shared UI primitives (KPI, Section, Toggle, Toast, etc.).

### Frontend services/types

- client/src/services/api.ts: API client calls and env-based base URL handling.
- client/src/services/analytics.ts: Client-side telemetry/event hooks.
- client/src/types/\*.ts: Type contracts for form and prediction structures.

### Frontend config

- client/package.json: Frontend scripts/dependencies.
- client/vite.config.ts: Vite configuration.
- client/eslint.config.js: Lint rules.
- client/tsconfig\*.json: TypeScript project configuration.

## Data and DVC

- data/Telco-Customer-Churn.csv.dvc: DVC pointer for the core dataset.
- data/Telco-Customer-Churn.csv: Local dataset file managed via DVC.
- data/test_batch.csv: Sample batch-scoring input.
- data/dataset_catalog.json: Dataset registry metadata.
- data/dataset_report.md: Dataset profiling/report summary.
- data/external/README.md: Notes for external dataset usage.

## Model development

- model/training/training.ipynb: Main experimentation/training notebook.
- model/training/dataset_registry.py: Dataset registration/report helper logic.
- model/training/build_dataset_report.py: Dataset report generation script.
- model/preprocessing/preprocessing.py: Preprocessing utilities.
- model/artifacts/catboost_churn.cbm: Trained model artifact.
- model/artifacts/cat_columns.json, feature_list.json: Inference schema artifacts.

## Documentation and MLOps planning

- docs/PROJECT_STRUCTURE.md: Recommended repo layout and hygiene conventions.
- docs/mlops/mlops_concepts.md: MLOps capability reference.
- docs/mlops/mlops_100_percent_milestone_goals.md: 100% milestone plan.
- docs/mlops/mlops_implementation_tracker.md: Progress tracker by capability.

## Generated or local-only artifacts (not core source)

- .venv/: Local Python environment.
- client/node_modules/: Installed frontend dependencies.
- backend/data/app.db: Local SQLite runtime DB.
- **pycache**/ and .ipynb_checkpoints/: Generated caches.
- .git/: Git metadata.
