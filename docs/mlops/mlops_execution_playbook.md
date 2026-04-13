# MLOps Execution Playbook

Date: 2026-04-11
Project: Customer Churn Predictor

## Why This Document Exists

This playbook explains:

1. How the project works end-to-end right now.
2. The correct order to operate and evolve the system safely.
3. What to do next to avoid breaking production while increasing MLOps maturity.

## System Overview

The project is a full-stack churn prediction system with ML lifecycle controls.

Core runtime pieces:

1. Frontend dashboard (`client`) for input collection and results visualization.
2. FastAPI backend (`backend`) for auth, prediction, explainability, jobs, and model lifecycle APIs.
3. Model runtime loader that can load:
   - direct model artifact (`.cbm`)
   - bundled pipeline artifact (`.zip` with manifest/checksum)
4. Persistence layer:
   - Postgres (durable mode)
   - SQLite (fallback/dev mode)
5. CI/CD and security automation:
   - CI checks
   - CD workflow (approval-gated)
   - security workflow

## End-to-End Runtime Flow

1. User submits customer features from frontend.
2. Backend authenticates and authorizes request.
3. Backend applies inference feature engineering.
4. Model runtime predicts churn probability.
5. Optional SHAP explainability computes top drivers.
6. Prediction and outcomes are logged for monitoring.
7. Registry state controls candidate/shadow/active model lifecycle.

## Artifact and Model Lifecycle Flow

### A. Build Artifacts

1. Train model and produce base artifacts:
   - `model/artifacts/catboost_churn.cbm`
   - `model/artifacts/feature_list.json`
   - `model/artifacts/cat_columns.json`
2. Build pipeline bundle:
   - command: `python -m model.preprocessing.pipeline_bundle --version <version>`
   - output: `model/artifacts/bundles/churn_pipeline_<version>_<timestamp>.zip`

### B. Register Candidate

1. Register bundle path in model registry via API.
2. Candidate appears in registry list with metadata.

### C. Validate Candidate (Must Be Formalized as Gate)

1. Run regression tests (schema + latency).
2. Run quality validation (AUC/recall thresholds).
3. Run fairness and memory checks.
4. Promote only if all checks pass.

### D. Promote and Observe

1. Shadow test candidate.
2. Promote to active model.
3. Monitor performance/drift and alert signals.
4. Roll back if degradation is detected.

## Correct Implementation Order (Practical Roadmap)

Follow this order to reduce risk and avoid rework.

### Step 1: Lock Reproducibility

1. Keep DVC dataset lineage up to date.
2. Keep pipeline bundle manifest checksums mandatory.
3. Add MLflow run tracking to connect data -> run -> model -> deploy.

### Step 2: Lock Promotion Governance

1. Add strict pre-promotion gate service.
2. Include pass/fail thresholds for quality, fairness, latency, memory.
3. Block promote endpoint when gates fail.

### Step 3: Lock Operational Safety

1. Keep CI as required check.
2. Keep Security workflow as required check.
3. Add branch protection so merges require both.

### Step 4: Lock Monitoring and Retraining Loop

1. Add Evidently drift reports as scheduled artifacts.
2. Add alert routing for drift/performance regressions.
3. Add orchestrated retraining only after monitoring signals are reliable.

### Step 5: Lock Release Reliability

1. Add canary rollout strategy.
2. Add automatic rollback triggers.
3. Validate backup/restore and disaster recovery runbooks.

## What Is Already Working Well

1. Registry lifecycle operations exist (candidate, shadow, promote, rollback).
2. Regression tests now run automatically in CI.
3. Security scanning is automated in a dedicated workflow.
4. Bundled pipeline artifact format is implemented and runtime-verifiable.

## What Is Still Missing for 100%

1. Strict model-quality promotion blocker in service layer.
2. Fairness acceptance tests and reporting.
3. Memory acceptance tests under controlled load.
4. Full lineage tracking with experiment system integration.
5. Drift dashboard + alert routing + automated retraining orchestration.

## Operating Rules (Do Not Skip)

1. Never promote a candidate without automated validation evidence.
2. Never deploy bypassing CI + security checks.
3. Never change preprocessing behavior without updating bundle and validation tests.
4. Always keep artifact path/version metadata linked to deploy event.

## Suggested Weekly Cadence

1. Monday: data/model drift review + backlog triage.
2. Midweek: implement one governance or validation hardening increment.
3. Friday: run release-readiness checklist and publish status update.

## Quick Release Checklist

1. Candidate bundle built and registered.
2. CI regression tests pass.
3. Security workflow passes.
4. Validation report passes thresholds.
5. Promotion approved and tracked.
6. Post-release monitoring reviewed.
