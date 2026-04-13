# MLOps 100% Milestone Goals

Date: 2026-04-11

## Objective

Build this Customer Churn Predictor into a fully production-grade MLOps system with complete lifecycle coverage: data, training, deployment, monitoring, governance, and continuous improvement.

## 1. What We Have Achieved (Mapped to `mlops_concepts.md`)

### Achieved (Done)

1. Problem framing and ML system design (business objective, churn task, evaluation focus).
2. Data preprocessing and feature engineering pipeline in place (including engineered fields like TotalServices and TechIssueRisk).
3. Train/validation/test workflow implemented in the training notebook.
4. Model training and hyperparameter search implemented.
5. Model evaluation implemented (classification metrics and ROC-AUC).
6. Model packaging and artifact loading implemented.
7. Model registry workflow implemented (candidate/shadow/active/promote/rollback logic in backend services).
8. Deployment strategy implemented via API-based serving (FastAPI endpoints).
9. Batch inference pipeline implemented (CSV upload + batch scoring jobs).
10. Real-time inference pipeline implemented (predict/explain API endpoints).
11. Prediction logging foundation implemented (durable prediction persistence in Postgres mode).
12. Data drift and concept/performance monitoring foundation implemented (monitoring service + metrics payload generation).
13. Feedback loop integration implemented (feedback and outcome event capture).
14. Rollback mechanism implemented for model version transitions.
15. Security and access control implemented (JWT + role-based authorization).
16. Model explainability implemented (SHAP-based explain endpoint).
17. Basic observability implemented (health/ready/metrics endpoints, structured logging, request IDs, latency headers).
18. Artifact management foundation implemented (local/object-storage capable paths and batch report handling).
19. Governance schema foundation implemented (audit logs, soft deletes, timestamps, org scoping).
20. Permanent database migration to durable repositories started (Postgres repositories for predictions/jobs/feedback/model registry/monitoring + startup migration runner).
21. Reproducible pipeline bundle serializer implemented (model + preprocessing + manifest checksums).
22. Runtime artifact verification implemented for bundled model loading.
23. Automated regression test suite implemented and CI-enforced (sample->preprocess->predict + API schema/latency).
24. Automated security workflow implemented (pip-audit, Bandit, npm audit, Gitleaks, CodeQL).

### In Progress (Partially Done)

1. Data ingestion automation (currently available data source and manual workflow; not yet fully automated connectors).
2. Data validation checks (basic checks exist, but no dedicated validation framework with enforceable gates).
3. Model validation pre-deployment checks (partial through service logic; not yet formalized as strict promotion gates).
4. Monitoring and alerting (metrics exist; production alert routing and dashboards need completion).
5. Reproducibility and lineage (some traceability exists, but no full dataset->run->model lineage stack).
6. Promotion governance (promotion still not blocked by model-quality/fairness/memory gates).

## 2. What We Still Need To Reach 100% MLOps

### Phase A: Data and Reproducibility (High Priority)

1. Implement data versioning with DVC for raw and processed datasets.
2. Add formal data validation pipeline (schema, missingness, drift checks) with fail-fast rules.
3. Add deterministic, config-driven preprocessing/training pipeline scripts (not only notebook-driven).
4. Add full lineage tracking: dataset version -> feature config -> model version -> deployment.

### Phase B: Experimentation and Model Governance

1. Integrate MLflow for experiment tracking (params, metrics, artifacts, run metadata).
2. Define strict model validation gates before promotion (minimum ROC-AUC/F1 + business KPI thresholds).
3. Expand registry metadata (owner, approval state, validation report, data version references).
4. Add formal approval workflow for model promotion decisions.
5. Enforce promotion policy in service layer so non-compliant candidates cannot be promoted.

### Phase C: CI/CD and Runtime Automation

1. Add GitHub Actions CI pipeline:
   - lint/type checks
   - unit/integration/API tests
   - migration checks
   - security scans
2. Add CD pipeline for backend/frontend deploy with environment-specific checks.
3. Add automated retraining pipeline (scheduled and drift-triggered).
4. Add orchestrator for recurring workflows (Airflow or Prefect).
5. Convert security workflow findings into explicit branch protection requirements.

### Phase D: Monitoring, Drift, and Alerts

1. Integrate Evidently AI for production drift reports (data + concept drift).
2. Add monitoring dashboards for:
   - model quality metrics
   - API latency/error rates
   - data drift signals
3. Configure alerting channels (email/Slack/PagerDuty).
4. Add model performance backtesting on recent labeled outcomes.
5. Publish a model validation report artifact for each candidate version.

### Phase E: Reliability, Security, and Compliance

1. Add containerization and runtime standardization with Docker.
2. Add backup/restore drills for Postgres and artifact storage.
3. Implement PII policy:
   - masking/encryption
   - retention policy
   - deletion policy
4. Harden secrets management and key rotation strategy.
5. Add load/performance tests and scaling policies.

### Phase F: Advanced Release Strategies

1. Implement canary deployment for model releases.
2. Implement A/B testing framework for candidate vs active model.
3. Add automatic rollback triggers on KPI degradation.
4. Add signed release manifests for production model bundles.

## 3. Software Stack (Current and Planned)

### Currently Used

1. FastAPI (model serving API, auth, routing).
2. Python (core ML and backend runtime).
3. CatBoost (model training/inference).
4. SHAP (explainability).
5. PostgreSQL (transactional persistence in durable mode).
6. SQLite (fallback/local mode).
7. Redis (cache/rate limit support, optional by env).
8. Render (backend deployment platform).
9. Vercel (frontend deployment platform).
10. React + TypeScript + Vite (frontend application).
11. Alembic + SQLAlchemy (schema management and ORM).
12. Object storage adapters (S3/Azure/local strategy support in codebase).
13. GitHub Actions workflows for CI, CD, and security scanning.

### Planned / To Integrate for 100% MLOps

1. MLflow (experiment tracking and model lifecycle metadata).
2. Evidently AI (drift and monitoring reports).
3. DVC (dataset and artifact versioning).
4. GitHub Actions (CI/CD automation).
5. Airflow or Prefect (pipeline orchestration).
6. Docker (environment consistency and deploy portability).
7. Optional observability stack (Prometheus + Grafana, or managed equivalent).
8. Optional incident/alert stack (Slack/PagerDuty integrations).
9. Fairness evaluation framework and bias reporting.

## 4. Definition of 100% Milestone (Exit Criteria)

A 100% MLOps milestone is achieved when all below are true:

1. Every model version is traceable to exact data and experiment runs.
2. Promotion to production is fully gated by automated validation checks.
3. Retraining, drift detection, and deployment are automated workflows.
4. Production monitoring and alerting are active and actionable.
5. Backups, rollback, and recovery procedures are tested and documented.
6. Security/compliance controls for PII and secrets are enforced.
7. CI/CD reliably validates and ships both application and ML updates.
8. Security and model-quality gates are mandatory for promotion and deployment.

## 5. Immediate Next 10 Execution Goals (Recommended Order)

1. Integrate MLflow run tracking into training and promotion flow.
2. Implement strict pre-promotion model validation gate service.
3. Add fairness and memory validation checks to candidate policy.
4. Add drift reports with Evidently AI and persist report artifacts.
5. Add alerting integration for drift/performance/latency failures.
6. Implement automated retraining trigger policy.
7. Add Airflow/Prefect job orchestration for scheduled pipelines.
8. Add Dockerized backend runtime profile for deployment consistency.
9. Run backup/restore drill and publish runbook.
10. Enforce branch protection on CI + security workflow success.
