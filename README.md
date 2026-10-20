# Customer Churn Predictor

A churn-scoring service for telecom-style retention work: a FastAPI backend that returns a
calibrated churn probability and its explanation, a React dashboard for what-if analysis, and the
machinery a model needs in production: a versioned registry, a fail-closed promotion gate, shadow
scoring with canary auto-rollback, drift monitoring, Prometheus metrics, and CI that tests the real
model on SQLite and Postgres.

**Live:** [app](https://customer-churn-prediction-alpha-one.vercel.app) (sign in as Analyst or
Viewer; those demo passwords are public by design) · [API docs](https://customer-churn-prediction-4pvg.onrender.com/docs).
The free Render instance sleeps when idle; the first request can take about a minute.

**Read this first.** The model is ordinary: on the IBM Telco data it ties a logistic-regression
baseline. What this project shows is the evaluation discipline and the engineering around the
model. Every number below comes from a command in this repository, listed next to it; what was not
verified is said plainly.

## Status

| Area | Status |
|---|---|
| Model quality | Test ROC-AUC 0.846 (95% CI 0.824 to 0.868). **Does not beat logistic regression** on Telco (CV difference -0.0008, 95% CI -0.0034 to +0.0018). On a second, bank dataset CatBoost **does** win (+0.109) ([results](docs/results.md), [second dataset](docs/second_dataset.md)). |
| Evaluation | 60/20/20 split; early stopping, calibration and threshold chosen on validation; test reported once. |
| Calibration | Served score is a probability: test ECE 0.018 (0.146 for the old class-weighted model) ([reliability diagram](docs/reliability_diagram.png)). |
| Decision threshold | 0.38 from stated economics (closed-form break-even 0.371); its gain over 0.50 is **not** statistically significant, and the docs say so ([ADR 0004](docs/decisions/0004-cost-based-threshold.md)). |
| Model lifecycle | Promotion gate (409 + audited override), standing logistic-regression challenger in shadow, canary auto-rollback, runtime synced to the registry on restart ([demo](docs/demo_all.md)). |
| Pipeline | `dvc repro`: pandera validation, training, evaluation, threshold analysis; MLflow tracking and registry; outputs reproduce byte for byte ([MLOps](docs/mlops.md)). |
| CI | Lint, mypy, 192 tests (152 behavioural, plus checks that docs links and README numbers match the outputs) with coverage on SQLite **and** Postgres, golden predictions of the real model, image build + smoke test + Trivy, Gitleaks/CodeQL/Bandit. |
| Monitoring | Live drift alerts, Evidently tests, retraining trigger ([drift demo](docs/demo_drift.md)); `/metrics` + Grafana dashboard ([screenshots](docs/mlops.md#observability-prometheus--grafana)). |
| Load | About 290 req/s with 2 workers, 178 with 1 (16-thread desktop); p95 18 to 25 ms at 20 users ([load test](docs/loadtest_results.md)). Not measured on the deployed host. |
| Deployment | Render (API, `ENVIRONMENT=production`, SQLite) + Vercel (frontend). `verify_deployment.py` 7/7 on 2026-10-19; published default passwords are rejected. |
| Database | SQLite by default; **Postgres supported and tested** (six defects fixed to get there). |
| Docs | [Architecture](docs/architecture.md) (incl. how I'd run this with real data), [decisions](docs/decisions/), [model card](docs/model_card.md), [engineering log](docs/engineering_log.md). |

## Highlights (each reproducible)

- **Tested whether boosting earns its keep, and reported the answer either way.** On Telco,
  CatBoost ties logistic regression (CV ROC-AUC difference -0.0008, 95% CI -0.0034 to +0.0018); on
  a 10,000-customer bank dataset it wins by +0.109 (95% CI +0.099 to +0.120), and adding two
  non-linear features to the logistic regression cuts that to +0.0225, about four-fifths of the gap.
  `python model/training/evaluate.py` · `python model/training/second_dataset.py`
- **Served calibrated probabilities with a cost-based decision rule.** Dropping a class weight took
  test calibration error (ECE) from 0.146 to 0.018; the threshold (0.38) is chosen on validation
  data from stated economics and matches the closed-form break-even (0.371).
  `python model/training/evaluate.py` · `python model/training/threshold_analysis.py`
- **Built a model lifecycle that refuses bad models automatically.** A candidate trained on
  shuffled labels is blocked by the promotion gate (HTTP 409) and, once shadowed, rolled back by the
  canary after 60 requests at 33.3% disagreement, while a healthy retrain (2.2%) is promoted.
  `python scripts/demo_all.py`
- **Made an untested Postgres mode work and kept it working.** Six defects fixed (one made every
  prediction fail after March 2026); 192 tests run on SQLite and Postgres in CI, and golden
  predictions on a committed 500-row sample pin the real model's output to 1e-6.
  `pytest backend/tests` (and with `DATABASE_BACKEND=postgres`)
- **Measured capacity instead of quoting a load generator's ceiling.** About 290 req/s with 2
  uvicorn workers vs 178 with 1 at saturation, p95 18 ms at 20 users; Prometheus metrics and a
  provisioned Grafana dashboard.
  `python tasks.py loadtest --users 100 --workers 2`

## Results in brief

| | ROC-AUC | Brier | Notes |
|---|---:|---:|---|
| CatBoost, served (test, n = 1,409) | 0.8464 | 0.1350 | calibrated; ECE 0.018 |
| Logistic regression challenger, in shadow (test) | 0.8454 | 0.1361 | trained on the same split; decisions differ for 3.4% of customers |
| CatBoost minus logistic regression, 5-fold CV | -0.0008 [-0.0034, +0.0018] | +0.0002 [-0.0011, +0.0013] | paired bootstrap, 5,634 rows |
| Same comparison on bank data (CV) | +0.109 [+0.099, +0.120] | | trees win; non-linear LR closes most of it |

Full tables, slices, the threshold economics and its sensitivity:
[docs/results.md](docs/results.md), [docs/model_comparison.md](docs/model_comparison.md),
[docs/slice_metrics.md](docs/slice_metrics.md), [docs/second_dataset.md](docs/second_dataset.md).

## Questions an interviewer is likely to ask

**Why serve CatBoost if logistic regression ties it?** On this dataset the accuracy argument is
gone, and the repo says so. CatBoost stays for native categoricals, exact TreeSHAP explanations and
the existing serving code; logistic regression runs next to it on every request as a challenger, so
the gap is measured on live traffic (2.97% decision disagreement in the load test). On the bank
dataset the choice reverses: CatBoost is clearly better. [ADR 0001](docs/decisions/0001-catboost-active-logreg-challenger.md)

**How do you know the test numbers are not tuned?** Early stopping, the calibration method and the
threshold are chosen on a separate validation split; the test split is scored once by
`evaluate.py`. The original model had been early-stopped on its own test split; that was the first
thing fixed. Byte-identical reruns (`dvc repro -f`) show the outputs are not hand-edited.

**Is 0.38 really better than 0.5?** Not measurably: +$716 per 1,000 customers on test with a 95%
interval of -$421 to +$1,888. The analysis finds a flat region of good thresholds under assumed
costs; the save rate it depends on can only be measured with a randomised holdout group.
[ADR 0004](docs/decisions/0004-cost-based-threshold.md)

**What does the canary actually detect?** Divergence, not correctness: the share of requests where
the candidate and the active model fall on different sides of the threshold. A better model also
disagrees, so the limit sits above what two equally good models produce; whether a candidate is
better needs labelled outcomes, which is the promotion gate's job.
[ADR 0002](docs/decisions/0002-canary-disagreement-over-compared-requests.md)

**How would you know the model is getting worse without labels?** You partly can't. Input and score
drift fire immediately but only say the population changed; calibration and AUC on outcomes that
arrive later are the real signal, and campaign results against a holdout are the business signal.
[Architecture: real data](docs/architecture.md#how-i-would-run-this-with-real-data)

**Why is the degraded demo model's AUC 0.64 and not 0.5?** A model trained on shuffled labels is
still a function of predictive features, so it can correlate with churn by accident. Twenty
permuted-label models averaged 0.529 with SD 0.125, against SD 0.021 for label-independent scores.
[docs/permutation_check.md](docs/permutation_check.md)

**Why is the CI data synthetic?** The Telco CSV has no clear licence, so real rows are not
committed. The 500-row sample keeps the consistency rules and gets labels from the model itself; it
says nothing about accuracy. Its job is to pin the shipped model's predictions so any change in
preprocessing, serving or library versions fails CI.

**What is the worst bug you found?** Postgres mode had never run: `audit_logs` only had a March 2026
partition, so every prediction (each writes an audit event) would have failed from April. That and
five more fixes are in the [engineering log](docs/engineering_log.md).

**Is the model fair?** Calibration holds in every slice checked, but seniors have lower within-group
AUC (0.781 vs 0.849), and an age-related feature is a model input. Whether that is acceptable is a
policy decision the [model card](docs/model_card.md) flags rather than answers.

**What breaks if you scale this out?** With several workers the loaded model and canary counters
are per process: a promote call switches only the worker that handled it until the others restart.
The demo deployment runs one worker; [ADR 0003](docs/decisions/0003-sqlite-by-default.md) describes
what a multi-worker setup needs.

## Selected bugs

Every bug found while hardening the project is fixed, has a regression test where code changed, and
is written up in [docs/engineering_log.md](docs/engineering_log.md) (26 entries). Four that say the
most about the project:

- **The original model was evaluated on its own early-stopping data.** Its tree count was chosen on
  the same 20% split its test metrics came from. The rebuilt pipeline early-stops, calibrates and picks
  the threshold on a separate validation split and touches the test split once.
- **After a promotion and a restart, the API served a different model than the registry reported.**
  The registry persists; the runtime always booted the default artifact. Startup now loads what the
  registry says and refuses to start if the active model cannot be loaded.
- **The Postgres mode had never run, and could not have.** Six defects stood between the code and a
  working deployment, the worst being that `audit_logs` only had a March 2026 partition, so every
  prediction (each writes an audit event) failed from April on. The suite now runs on Postgres in CI.
- **The drift detector looked tested but never executed.** A dependency upgrade broke its import, a flag
  silently disabled it, and its tests turned the `ImportError` into a skip; its result parsing was also
  wrong. It is now ported, and its tests fail instead of skipping.

## API

Interactive docs at `/docs`. Auth is JWT with roles `admin`, `analyst`, `viewer`.

- Auth: `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `GET /api/v1/auth/me`
- Predictions: `POST /api/v1/predictions/predict` (**no auth required**, rate limited per IP),
  `POST .../explain` (no auth), `GET .../history`, `POST .../recommend`, `POST .../feedback`,
  `POST .../outcome`, `GET .../feedback/summary`
- Models (admin): `GET /api/v1/models`, `POST .../register`, `POST .../shadow`, `POST .../promote`
  (validation gate; `override_gate` + `override_reason` optional), `POST .../rollback`
- System: `GET /api/v1/system/health`, `/ready`, `/metrics` (admin, legacy text), `/monitoring`, `/canary`
- Prometheus: `GET /metrics` (public unless `METRICS_TOKEN` is set)
- Jobs: `POST /api/v1/jobs/batch-score`, `/reports`, `/retrain`, `GET /api/v1/jobs`, `/{id}`, `/{id}/download`
- Legacy unauthenticated `POST /predict` and `POST /explain` for older clients.

`/predict` and `/explain` are limited to `PREDICT_RATE_LIMIT_PER_MINUTE` (default 30) per client IP.

## Run locally

Requirements: Python 3.13, Node 18+ (Docker for `up`). The training CSV is not in git and there is no
DVC remote, so place the IBM Telco CSV at `data/Telco-Customer-Churn.csv` yourself. The API and the
tests do not need it (tests use the committed synthetic sample); model promotion (the gate's evaluation
data), training and the demos do.

```bash
python tasks.py setup --frontend   # or: make setup
python tasks.py up                 # API http://localhost:8000/docs, frontend http://localhost:5173
```

Or by hand:

```powershell
# backend (from repo root)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --app-dir backend --host 127.0.0.1 --port 8000 --reload

# frontend
cd frontend; npm install; npm run dev
```

Locally (`ENVIRONMENT=development`, the default) the seeded users fall back to INSECURE, published
passwords `admin/admin123`, `analyst/analyst123`, `viewer/viewer123`, with a warning in the log. Set
`ADMIN_PASSWORD`, `ANALYST_PASSWORD` and `VIEWER_PASSWORD` to override them.

Or `docker compose up --build` (frontend http://localhost:5173, API http://localhost:8000).
`requirements.txt` is the full pinned environment (training, MLOps, docs tooling) and is what CI tests;
the API image installs `requirements-runtime.txt`, whose pins must match it. Dependabot (minor/patch
only) updates both; `requirements.txt` used to be UTF-16, which Dependabot could not read, so its
runtime bumps were never tested.

### Tests

```powershell
$env:PYTHONPATH = (Get-Location).Path
$env:MLFLOW_ALLOW_FILE_STORE = "true"
pip install -r requirements.txt -r requirements-dev.txt
pytest -q backend/tests                      # or: python tasks.py test (adds coverage)
$env:DATABASE_BACKEND = "postgres"           # same suite against Postgres (docker compose --profile postgres up -d postgres)
$env:POSTGRES_URL = "postgresql+psycopg://churn:churn@localhost:5432/churn"
pytest -q backend/tests
```

Last run (Python 3.13): **192 passed, 0 skipped** on SQLite and **192 passed** on Postgres 16 (CI job
"Backend Tests on Postgres"); line
coverage 74% of `backend/` and `model/` (tests excluded). Without the DVC dataset only
`test_full_training_csv_passes` skips; everything else uses the committed synthetic sample.

### Reproducing the other measurements

```powershell
dvc repro                                            # validate -> train -> evaluate -> threshold -> golden predictions (or: python tasks.py train)
python model/training/second_dataset.py             # bank churn dataset (downloads from OpenML) -> docs/second_dataset.md (~7 min)
python model/training/permutation_check.py           # 20 permuted-label models -> docs/permutation_check.md (~3 min)
python tasks.py demo                                 # end-to-end demo: predict, explain, gate, rollback, drift -> docs/demo_all.md
python tasks.py loadtest --users 20 --workers 1      # Locust; see docs/loadtest_results.md for the five configurations
python scripts/demo_shadow_rollback.py --base-url http://localhost:8000 --delay 0.05   # against a running server
```

## Deployment

The backend reads the model from `model/` (outside `backend/`), so it must be built from the
**repository root**. Setting Render's "Root Directory" to `backend/` (as earlier drafts of this
README said) leaves the model out of the build and the service fails to start.

1. **Render**: New > Blueprint > pick this repo; `render.yaml` defines a Docker web service built from
   `backend/Dockerfile` with context `.`, health check `/api/v1/system/health`, `ENVIRONMENT=production`,
   a generated `SECRET_KEY` and `ADMIN_PASSWORD`, and SQLite. Set `ALLOWED_ORIGINS` to the exact Vercel
   URL, and `ANALYST_PASSWORD` / `VIEWER_PASSWORD` to the public demo passwords you also give Vercel. In
   production the API refuses to start if any of these is unset or a published default. The Dockerfile
   honours Render's `PORT`. A free instance sleeps when idle (the first request can take a minute).
   Check Render's current free-tier memory limit: the API used about 320 MB resident in testing, which
   is tight on a 512 MB instance. The Docker image does not contain the training CSV, so promotions on
   the deployed API are blocked by the gate unless `PROMOTION_EVAL_DATA_PATH` points at a labelled file
   (or an admin overrides with a reason).
2. **Vercel**: project root `frontend`, environment variables `VITE_API_URL=https://<your-api>.onrender.com`,
   `VITE_DEMO_ANALYST_PASSWORD` and `VITE_DEMO_VIEWER_PASSWORD` (same values as on Render; they are
   compiled into the public JavaScript). There is no admin variable: admin signs in by typing the
   password.
3. **Verify end to end** (stdlib only, no installs):
   ```bash
   python scripts/verify_deployment.py https://<your-api>.onrender.com --origin https://<your-app>.vercel.app --password <viewer demo password> --timeout 120
   ```
   It checks health, readiness, CORS preflight for your frontend origin, login, predict, explain and an
   authenticated route, and exits non-zero on the first failure. Paste its output and the two URLs into
   the table at the top of this file only after it passes.

CI is described in [docs/mlops.md](docs/mlops.md#ci). CD (`cd.yml`) runs behind a
GitHub `production` environment, optionally promotes a model, triggers the Render deploy hook, waits
for readiness and triggers the Vercel hook. The approval gate only works if required reviewers are set
on that environment in the repository settings. Secrets: `RENDER_DEPLOY_HOOK_URL`,
`VERCEL_DEPLOY_HOOK_URL`, optionally `BACKEND_HEALTHCHECK_URL`, and `BACKEND_API_URL` +
`BACKEND_ADMIN_TOKEN` for model promotion (which now goes through the gate).

### Configuration (environment variables)

`ENVIRONMENT` (`development`|`production`), `SECRET_KEY`, `ADMIN_PASSWORD`, `ANALYST_PASSWORD`,
`VIEWER_PASSWORD`, `ALLOWED_ORIGINS` (JSON list or comma-separated), `DECISION_THRESHOLD`,
`PROMOTION_EVAL_DATA_PATH`, `PROMOTION_MIN_AUC`, `PROMOTION_MIN_PRECISION`, `PROMOTION_MIN_RECALL`,
`PROMOTION_MIN_F1`, `PROMOTION_MAX_AUC_DROP`, `CHALLENGER_ENABLED`, `CHALLENGER_ARTIFACT_PATH`,
`CHALLENGER_VERSION`, `DATABASE_BACKEND` (`sqlite`|`postgres`), `POSTGRES_URL`,
`REDIS_ENABLED`/`REDIS_URL`, `OBJECT_STORAGE_PROVIDER` (`none`|`local`|`s3`|`azure`) and its bucket
settings, `CANARY_ENABLED`, `CANARY_TRAFFIC_PERCENT`, `CANARY_MIN_SAMPLES`,
`CANARY_MAX_DISAGREEMENT_RATE`, `CANARY_ROLLBACK_COOLDOWN_SECONDS`, `PREDICT_RATE_LIMIT_PER_MINUTE`,
`SCHEDULE_RETRAINING_ENABLED`, `METRICS_TOKEN`, `PROMETHEUS_MULTIPROC_DIR`, `RETRAINING_OUTPUT_DIR`,
`MLFLOW_TRACKING_URI`. See `backend/.env.example`.

## Security notes

- **Admin credentials are not public any more.** Seeded passwords come from `ADMIN_PASSWORD`,
  `ANALYST_PASSWORD` and `VIEWER_PASSWORD`. Only with `ENVIRONMENT=development` do they fall back to the
  published defaults (`admin123` etc., logged as insecure); any other environment refuses to start
  without explicit values or with a published default, and also refuses the default `SECRET_KEY`.
- **The analyst and viewer demo logins are public by design.** The frontend's one-click logins use
  `VITE_DEMO_ANALYST_PASSWORD` / `VITE_DEMO_VIEWER_PASSWORD`, which are compiled into the JavaScript.
  Anyone can sign in as analyst or viewer on the live demo; analysts can run batch jobs and submit
  feedback. Do not describe this as production-grade authentication.
- Passwords are hashed with PBKDF2-SHA256; tokens are signed JWTs.
- `backend/.env` and `frontend/.env` are no longer tracked (they held only local development values,
  but a Vercel build without `VITE_API_URL` picked up the frontend one's `http://127.0.0.1:8000`). Copy
  the `.env.example` files instead; both names are git-ignored. They remain in the git history.

## Limitations

- Telco is a public benchmark, not real retention data; there are no measured business outcomes.
- On Telco the model does not beat a logistic-regression baseline (on the bank dataset it does); see
  [docs/results.md](docs/results.md) and [docs/second_dataset.md](docs/second_dataset.md).
- The threshold and its gain depend on assumed economics; the real values should replace the
  assumptions in `params.yaml` before any real use.
- The promotion gate's default evaluation data overlaps the training data; with real data it should be
  recent labelled outcomes that no candidate was trained on.
- The retraining job (`services/retraining_service.py`) still uses its own simpler recipe (80/20 split,
  no calibration file) and its own pre-check with `ModelValidationGate`'s default thresholds (recall >=
  0.65 at a 0.5 cut-off), which differ from the promotion gate's; in the drift demo its candidate failed
  that pre-check. Moving retraining onto `train.py` (or `dvc repro`) is the obvious next step.
- The shadow/canary and drift demos use synthetic candidates, replayed historical rows and an
  artificial shift, not live traffic.
- Load test numbers come from one desktop with the load generator on the same host; nothing was
  measured on the deployed instance. At 20 users the throughput figure is set by the load generator.
- Default storage is SQLite with in-memory prediction history and audit log. Postgres has a DEFAULT
  partition for the event tables but no monthly partition management or retention yet.
- The API image is 2.08 GB. Trivy (CI on `main`, after the Starlette 1.8 upgrade) lists 6 HIGH
  vulnerabilities with available fixes, all in Python packages (python-multipart, setuptools, urllib3),
  0 CRITICAL and none in OS packages; upgrading them is open work.
- The loaded models and the canary counters live in each process. With several uvicorn workers a
  promote, shadow or rollback call switches only the worker that handled it until the others restart;
  the deployment runs one worker ([ADR 0003](docs/decisions/0003-sqlite-by-default.md)).
- The devcontainer was written but not built here.
- The live backend runs on a free Render instance with SQLite on an ephemeral disk: prediction history,
  the audit log and registry changes reset on every deploy or restart, and promotions there are blocked
  by the gate (no labelled evaluation data in the image) unless an admin overrides with a reason.
