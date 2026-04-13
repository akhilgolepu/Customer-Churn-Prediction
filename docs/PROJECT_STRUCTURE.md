# Project Structure (MLOps-Oriented)

Date: 2026-04-08

## Recommended Top-Level Layout

```text
Customer_Churn_Predictor/
  backend/                 # API, services, repositories, db migrations, storage adapters
  client/                  # React frontend
  data/                    # source datasets (version this via DVC in next phase)
  model/                   # model artifacts + training notebooks/scripts
  docs/
    mlops/                 # MLOps plans, trackers, milestones
    PROJECT_STRUCTURE.md   # this file
  README.md
  package.json
  requirements.txt
```

## What Lives Where

1. `backend/`

- FastAPI app, domain services, repositories, migrations.
- Production runtime and operational controls.

2. `client/`

- UI, pages, components, API client.

3. `data/`

- Raw and intermediate datasets (to be tracked by DVC).

4. `model/`

- Training work and exported model artifacts.

5. `docs/mlops/`

- Planning and governance docs:
  - `mlops_concepts.md`
  - `mlops_100_percent_milestone_goals.md`
  - `mlops_implementation_tracker.md`

## Cleanup Rules

1. Do not keep generated caches in repo:

- `__pycache__/`
- `.ipynb_checkpoints/`
- `node_modules/`

2. Do not keep ad-hoc scratch docs in root.

- Keep planning/governance under `docs/mlops/`.

3. Keep environment-specific secrets local only.

- Use `.env.example` for templates.

## Next Structural Improvements (Optional)

1. Add `ops/` for deployment manifests/runbooks.
2. Add `pipelines/` for retraining and orchestration scripts.
3. Add `tests/` split by backend, integration, and ML validation.
