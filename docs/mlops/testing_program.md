# Formal Testing Program

## Objective

Catch model-service regressions automatically on every push and pull request.

## Test Levels

1. Unit-level behavior checks

- Preprocessing feature engineering correctness.
- Feature ordering and schema alignment with model artifacts.

2. Pipeline regression checks

- Flow: load sample -> preprocess -> model predict.
- Assert output probability range and schema alignment.
- Assert latency budget for preprocessing and model inference.

3. API integration checks

- Authenticate via login endpoint.
- Execute prediction endpoint with realistic payload.
- Assert response schema and latency budget.

## CI Gates

Backend CI gate includes:

- Lint (`ruff check`).
- Python compile/syntax validation (`compileall`).
- Regression tests (`pytest backend/tests`).
- App factory smoke test.
- Data pipeline report validation.

Security workflow includes:

- Python dependency audit (`pip-audit`).
- Python static security scan (`bandit`).
- Node dependency audit (`npm audit --audit-level=high`).
- Secret scanning (`gitleaks`).
- CodeQL analysis (`python`, `javascript`).

A change is considered deploy-ready only when all backend checks pass.

## Current Regression Suite

Test file:

- `backend/tests/test_regression_pipeline.py`

Automated checks:

- `test_sample_preprocess_predict_regression_schema_and_latency`
- `test_api_predict_regression_schema_and_latency`

## Latency Budgets (initial)

- Preprocess: < 2.0s
- Model predict: < 2.0s
- API predict: < 6.0s

Budgets are intentionally conservative initially and should be tightened with historical CI data.

## Next Hardening Steps

1. Add deterministic golden samples with expected probability ranges per model version.
2. Add explain endpoint regression checks (top drivers schema and stable cardinality).
3. Add model quality gate tests (AUC/recall thresholds) for candidate promotion.
4. Add fairness and memory acceptance tests with explicit fail thresholds.
5. Mark CI and Security workflows as required branch checks in repository settings.
