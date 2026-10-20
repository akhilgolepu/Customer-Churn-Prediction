# MLOps details

Model lifecycle, pipeline, validation, CI, drift, observability, Postgres and developer tooling. See also [architecture.md](architecture.md).

## Model lifecycle: candidate, gate, shadow, canary, rollback

```
register (candidate) -> shadow (scored on every request, canary % served to users)
        -> promote: validation gate must pass (or an audited admin override) -> active, previous archived
        -> canary disagreement above limit while in shadow => automatic rollback: candidate rejected
        -> manual rollback to the last archived model at any time
```

- **Promotion gate.** `POST /api/v1/models/promote` scores the candidate (and the current active model)
  on a labelled CSV (`PROMOTION_EVAL_DATA_PATH`, default the Telco CSV) and runs `ModelValidationGate`:
  ROC-AUC >= 0.75, precision/recall/F1 floors at the decision threshold (0.40 / 0.40 / 0.45), single-row
  latency, schema and missing-data checks, plus non-inferiority: the candidate may not be more than 0.02
  AUC below the active model. Any blocker returns **409 `promotion_blocked`** with the blockers in
  `details`, and an audit event `model_promotion_blocked`. A missing evaluation file is itself a blocker
  (fail closed). `{"override_gate": true, "override_reason": "..."}` promotes anyway and records
  `model_promotion_gate_overridden` with the actor, reason and blockers. Every gate run is written to
  `backend/data/validation_reports/`. Caveat: the default evaluation CSV overlaps the training data, so
  the gate catches broken or regressed models; it is not an unbiased estimate. Automatic promotion from
  the retraining job goes through the same gate.
- The shadow model scores every request. A configurable percentage (`CANARY_TRAFFIC_PERCENT`) of
  responses is actually served from the shadow model; those users see the candidate until rollback.
- Disagreement is the share of compared requests where active and shadow land on different sides of
  the decision threshold. When it exceeds `CANARY_MAX_DISAGREEMENT_RATE` after `CANARY_MIN_SAMPLES`
  compared requests, the canary is rolled back: the candidate is marked `rejected`, unloaded, the
  canary is disabled, and the active model is left alone. Canary is **off by default**
  (`CANARY_ENABLED=false`).
- Each artifact carries its own calibration (`<model>.calibration.json` next to a `.cbm`, or
  `model/calibration.json` inside a pipeline bundle, covered by the bundle's SHA-256 manifest).
  Artifacts without one serve their raw score.

The demo (`scripts/demo_shadow_rollback.py`, transcript in
[`docs/demo_shadow_rollback.md`](demo_shadow_rollback.md)) drives the real HTTP routes with
replayed held-out customer rows: a routine retrain (v2, test AUC 0.847) shadows at 2.2% disagreement
(9 of 400) and passes the gate; a degraded retrain (v3, trained on permuted labels) is refused by the
gate with a 409, then put in shadow and rolled back automatically after 60 compared requests at 33.3%
disagreement, with v2 still serving.

```bash
python model/training/build_demo_candidates.py   # writes model/artifacts/demo/ (git-ignored)
python scripts/demo_shadow_rollback.py --out docs/demo_shadow_rollback.md
```

The degraded candidate's test AUC is 0.642, not 0.5. This was checked, not assumed
([docs/permutation_check.md](permutation_check.md), `python model/training/permutation_check.py`):
across 20 models trained on independently permuted labels, AUC against the true test labels averaged
0.529 with SD 0.125 (range 0.241 to 0.735), while the same scores re-assigned to random rows give SD
0.021 (theory: 0.017). Each permuted model's AUC tracks the correlation of its scores with the real
model's scores (Pearson r = 0.977 over the 20 runs). A model fitted to noise learns no churn signal but
is still a function of tenure, charges and contract, which are strongly predictive, so by chance it can
rank churners above or below chance (here a Platt fit on the permuted labels flipped its sign). It is
far below the healthy model either way, which is what the gate and canary need.

Running the original demo exposed two canary bugs (an inflated disagreement rate and a rollback
that demoted the healthy model); both are in the [engineering log](engineering_log.md).

The demo output is not fully deterministic: which requests are served by the canary depends on random
prediction ids. The disagreement counts and pass/fail outcome depend only on the two models and the
replayed rows.

## MLOps: pipeline, validation, CI, drift, observability, Postgres

### Reproducible pipeline (DVC + MLflow)

`dvc repro` rebuilds everything from the raw CSV; `dvc.yaml` declares the stages and their
dependencies, `params.yaml` the settings, `dvc.lock` the hashes of the last run, and `metrics.json`
the headline test metrics (`dvc metrics show`).

| Stage | Command | Outputs |
|---|---|---|
| `validate_data` | `model/training/validate_data.py` | `reports/data_validation.json` (fails the pipeline on bad data) |
| `train` | `model/training/train.py` | CatBoost + calibration, logistic-regression challenger, `training_metadata.json`; logs the run to MLflow and registers both models |
| `evaluate` | `model/training/evaluate.py` | model comparison, slices, reliability diagram, `metrics.json`; logs test metrics to MLflow, linked to the training run |
| `threshold_analysis` | `model/training/threshold_analysis.py` | `docs/threshold_analysis.json` |
| `ci_golden` | `scripts/make_ci_sample.py --golden` | golden predictions for the CI sample |
| `dataset_report` | `model/training/build_dataset_report.py` | `data/dataset_report.md` |

`dvc repro -f` (all stages forced) ran end to end in 5 min 10 s (`dvc repro -f`, all stages forced; a later `dvc repro` that re-ran the five
changed stages took 7 min 16 s) on this machine and reproduced every
generated document byte for byte (the `.cbm` file's bytes differ between runs; every prediction derived
from it, and so every report, is identical).

MLflow: local store `sqlite:///mlflow.db` with artifacts in `mlartifacts/` (both git-ignored;
`MLFLOW_TRACKING_URI` overrides). `train.py` registers `churn-catboost` and `churn-logreg-challenger`;
the API loads registered models by URI, so `POST /api/v1/models/register` accepts
`"artifact_path": "models:/churn-catboost/1"` (needs `mlflow` installed; the slim API image does not
have it, so use a file or object-storage path there).

There is **no DVC remote**: `.dvc/config` is empty, so `dvc pull` cannot work. Place the IBM Telco CSV
at `data/Telco-Customer-Churn.csv` yourself.

### Data validation (pandera)

`model/data_schema.py` holds one rule table rendered two ways:

- **pandera schemas** for the training data (`TRAINING_SCHEMA`: value domains, unique `customerID`,
  `Churn` label, blank `TotalCharges` only at tenure 0, sanity ranges, no unexpected columns; used by
  the `validate_data` stage and by `load_dataset`) and for batch-scoring files (`FEATURE_SCHEMA`; a bad
  file now fails with every bad row listed instead of the first one).
- **the same cross-field rules in plain Python** inside the `/predict` request model: "no phone service"
  must coincide with `MultipleLines="No phone service"`, and "no internet" with all six add-ons saying
  "No internet service". Inconsistent requests get a 422 (the model never saw such rows; the
  frontend's form never sends them). Pandera costs about 24 ms per call even for one row (57 ms for all
  7,043 rows), too much for a request whose p95 is in the tens of milliseconds, hence the plain-Python
  rendering; a test checks both agree on all 8,748 service combinations.

The full dataset passes the training schema. Malformed-row tests: `backend/tests/test_data_validation.py`.

### CI

`.github/workflows/ci.yml`, jobs run in parallel:

| Job | What it does |
|---|---|
| Backend Checks | ruff, mypy (non-strict, `backend/`), validates the CI sample against the training schema, full test suite with coverage (summary in the job page, `coverage.xml` uploaded) |
| Backend Tests on Postgres | same suite with `DATABASE_BACKEND=postgres` against a Postgres 16 service container (migrations run on startup) |
| API Image Build, Smoke Test and Scan | builds the Docker image, starts it, calls health and `/predict`, scans with Trivy (fails on fixable CRITICAL, lists HIGH) |
| Frontend Checks | eslint, type-check and build |

Plus `security.yml` (Bandit, pip-audit, CodeQL, Gitleaks), Dependabot (`.github/dependabot.yml`: pip,
npm, GitHub Actions, Docker; weekly), and `.pre-commit-config.yaml` (ruff, mypy and file hygiene
checks; none rewrite files).

**CI runs the real model.** The served artifact is in git, and `data/ci_sample.csv` is a committed
500-row sample, so the tests that used to skip without the DVC dataset now run. The sample is
**synthetic** (`scripts/make_ci_sample.py`, fixed seed): the IBM Telco CSV has no clear data license
(IBM's repository license covers its code), so real rows are not committed. Category shares are
rounded aggregate constants, the consistency rules hold, and `Churn` is drawn from the shipped model's
own probabilities, so the sample says nothing about real accuracy. Its job is
`data/ci_sample_golden.json`: the shipped model's calibrated output for all 500 rows, checked through
the training preprocessing and through the HTTP `/predict` path (`test_ci_sample.py`). Any change to
preprocessing, serving feature engineering, the artifact or a library version that moves a prediction
by more than 1e-6 fails CI. It also showed that tenure-0 rows (blank `TotalCharges` in training, 0.0
in requests) score identically: no skew.

### Drift: live monitor, Evidently, retraining trigger

`python scripts/demo_drift.py --out docs/demo_drift.md` ([transcript](demo_drift.md)) replays 300
held-out rows, then 300 rows with tenure x 0.3 and MonthlyCharges x 1.3 (TotalCharges recomputed):

| Signal (live monitor) | Baseline half | Shifted half | Relative change | Alert |
|---|---:|---:|---:|---|
| tenure | 32.28 | 9.65 | -0.701 | yes |
| MonthlyCharges | 65.75 | 87.02 | +0.323 | yes |
| TotalCharges | 2,222 | 897 | -0.596 | yes |
| mean served churn probability | 0.273 | 0.392 | +0.432 | yes |

On baseline-only traffic nothing fired and the scheduler did nothing. After the shift, Evidently's
Kolmogorov-Smirnov tests flagged exactly the three shifted features (p = 1.4e-42, 1.2e-17, 5.2e-11)
and none of the 15 unshifted ones, and one scheduler poll enqueued a retraining job with reason
`drift_alert`; the job completed and registered a candidate.

The live monitor (`GET /api/v1/system/monitoring`) compares the mean of each numeric input and of the
served score between the older and newer half of the latest 5,000 predictions; the scheduler polls it
(`SCHEDULE_RETRAIN_POLL_SECONDS`) and enqueues a retraining job on alerts. Evidently
(`services/drift_detector.py`) adds per-feature statistical tests on demand. The retrained candidate is
registered but not promoted: the retraining job still uses its own older recipe and pre-check (see
Limitations).

### Observability (Prometheus + Grafana)

`GET /metrics` (public unless `METRICS_TOKEN` is set) exposes:

| Metric | Type |
|---|---|
| `churn_http_request_duration_seconds{method,route,status}` | histogram, route templates, timed in the outermost middleware |
| `churn_predictions_total{served_by,decision}` | counter (active vs shadow-served, churn vs stay) |
| `churn_prediction_score` | histogram of the served probability |
| `churn_canary_disagreement_rate`, `churn_canary_compared_requests`, `churn_canary_disagreements` | gauges, read from the canary at scrape time |
| `churn_canary_rollbacks_total` | counter |
| `churn_model_info{slot,version,kind,calibration}` | which model is active and which is in shadow |

With several workers set `PROMETHEUS_MULTIPROC_DIR` (prometheus_client multiprocess mode; `tasks.py
loadtest --workers 2` does). `docker compose --profile observability up --build` adds Prometheus
(:9090, scraping every 5 s) and Grafana (:3000, anonymous read-only, dashboard provisioned from
`observability/grafana/dashboards/churn-api.json`).

Screenshots from this machine (Docker Desktop, canary at 20% for the demo):

- [during a load test](img/grafana_loadtest.png): 2,022 compared requests, live
  CatBoost-vs-challenger disagreement 2.97% (3.4% offline on the test split).
- [right after the rollback demo](img/grafana_rollback.png): v2 active (Platt-calibrated), the
  degraded v3's disagreement at 33.3% over 60 compared requests, one rollback, the gate's 409 in the
  error panel. Transcript: [docs/demo_shadow_rollback_live.md](demo_shadow_rollback_live.md).

### Postgres

`DATABASE_BACKEND=postgres` now works and is tested: the whole suite passes on SQLite and on Postgres 16
(the full suite, also in CI), the rollback demo passes against the API container on Postgres
([transcript](demo_shadow_rollback_postgres.md)), and predictions, audit events, the registry and
batch jobs are persisted (checked in the tables; after a container restart the API still serves the
promoted v2). Getting there meant fixing six defects in a path that had never been run (see the
[engineering log](engineering_log.md)). Run it with `DATABASE_BACKEND=postgres docker compose --profile postgres up --build`.

### Developer experience

`tasks.py` is a cross-platform task runner (Windows has no `make`); the `Makefile` delegates to it:

```bash
python tasks.py setup [--frontend]     # .venv + requirements.txt + requirements-dev.txt (+ npm ci)
python tasks.py test | lint | train | demo | loadtest | up [--observability] | down
make setup test lint train demo loadtest up down   # same, where make exists
```

`.devcontainer/devcontainer.json`: Python 3.13, Node 20, Docker CLI against the host daemon;
`postCreateCommand` runs `tasks.py setup --frontend`.

Checked from a fresh `git clone` of the pushed branch (no dataset, no venv): `python tasks.py setup`
took 6 min 27 s, then `python tasks.py test` gave 149 passed, 1 skipped (the full-dataset check) and
`python tasks.py lint` was clean. **`python tasks.py up` from that clone was not verified**: Docker Hub
pulls hung on this machine at the time. The same compose file built and ran from the working copy
(API, Prometheus, Grafana, Postgres), but the **frontend container was never built** in this pass.
The frontend image now gets `VITE_API_URL` as a build argument (default `http://localhost:8000`)
instead of relying on the committed `frontend/.env`, which the security notes say to untrack.

## Code notes

- **Frontend** `frontend/`: React + TypeScript + Vite, Tailwind, Recharts.
- **Backend** `backend/`: FastAPI. Routers in `routers/api_v1`, services in `services/`, repositories
  in `repositories/`, request/response schemas in `schemas/`.
- **Training** `model/training/`: `common.py` (data, split, model recipes, metrics), `train.py`,
  `evaluate.py`, `threshold_analysis.py`, all driven by `params.yaml`. `model/calibration.py` fits
  calibrators with scikit-learn and applies them with numpy only (JSON, no pickles).
- **Shared feature contract** `model/preprocessing/preprocessing.py` (training) and
  `backend/feature_engineering.py` (serving). The two must stay identical; a past mismatch in
  `TotalServices` and `TechIssueRisk` skewed live predictions. `test_feature_parity.py` runs ~1,000
  synthetic customers (every tenure-bucket boundary, internet/phone/contract/payment combinations)
  through both paths and fails on any difference, so it runs in CI without the dataset. I checked that
  it fails when the serving code miscounts `TotalServices`.
- **Model runtime** `backend/model_loader.py`: hot-swappable active and shadow CatBoost models with
  their calibration, pipeline bundles verified by SHA-256 manifest.

Prediction path: engineer features, score active (calibrated), score shadow (if any), pick the served
variant, record the prediction and an audit event.

### Storage: what persists

| Data | SQLite mode (default) | Postgres mode (`DATABASE_BACKEND=postgres`) |
|---|---|---|
| Model registry, feedback, monitoring | SQLite file | Postgres (Alembic migrations) |
| Prediction history | **In memory**, lost on restart | Postgres |
| Audit log | **In memory**, lost on restart | Postgres |
| Batch jobs | **In memory** | Postgres |

Postgres mode runs Alembic migrations `0001` to `0004` on startup and is covered by the full test suite
and the rollback demo (see [Postgres](#postgres)). On a free Render instance the SQLite file sits on an
ephemeral disk and resets on every deploy.
