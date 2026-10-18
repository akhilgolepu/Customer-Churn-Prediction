# Customer Churn Predictor

A churn-scoring service for telecom-style retention workflows: a FastAPI backend that scores a
customer record with a calibrated CatBoost model and explains the score with SHAP, a React dashboard
for what-if analysis, and the operational plumbing around the model (versioned registry, promotion
gate, shadow/canary rollout with automatic rollback, JWT roles, audit log, CI/CD).

**Read this first.** The model itself is ordinary: it ties a logistic-regression baseline on the
public IBM Telco dataset (see [Results](#results)). The part of this project that carries weight is
the engineering and the evaluation discipline around it. Everything below says what was measured,
how to reproduce it, and what was not verified.

| Area | Status |
|---|---|
| Model quality | Test ROC-AUC 0.846 (95% CI 0.824 to 0.868). **Does not beat logistic regression**: CV difference -0.0008 (95% CI -0.0034 to +0.0018); LightGBM is no better either ([comparison](docs/model_comparison.md)). |
| Challenger | CatBoost stays active; logistic regression runs as a standing challenger in the shadow slot, scored on every request. Test: AUC difference +0.0010 (95% CI -0.0041 to +0.0059), decisions differ for 3.4% of customers ([ADR 0001](docs/decisions/0001-catboost-active-logreg-challenger.md)). |
| Evaluation hygiene | 60/20/20 train/validation/test split; early stopping, calibration and threshold use validation only; test reported once ([`train.py`](model/training/train.py), [`evaluate.py`](model/training/evaluate.py), [`params.yaml`](params.yaml)). |
| Calibration | Served score is a calibrated probability: test Brier 0.135, ECE 0.018 ([reliability diagram](docs/reliability_diagram.png)). Achieved by dropping the class weight; Platt/isotonic did not improve on it. |
| Decision threshold | Default **0.38**, chosen on validation from a stated cost assumption; closed-form break-even 0.371. Its gain over an untuned 0.50 cut-off is **not statistically distinguishable** on test (+$716 per 1,000, 95% CI -$421 to +$1,888): [details](#decision-threshold). |
| Promotion gate | `POST /models/promote` runs `ModelValidationGate`; blockers give HTTP 409, admin override requires a reason and is audit-logged. |
| Auth | Seeded passwords come from environment variables; production refuses to start with defaults. The frontend ships only the public analyst/viewer demo logins, no admin credentials. |
| Slices / model card | Calibration holds in every slice; seniors have lower within-group AUC ([model card](docs/model_card.md), [slices](docs/slice_metrics.md)). |
| Load test | Done on the **previous** (class-weighted) model: 135 req/s, p95 41 ms at 20 users on one worker, 2 vCPU ([details](docs/loadtest_results.md)). Not re-run on the calibrated model or with the challenger attached (every request now scores two models); not measured on the deployed host. |
| Shadow/canary + rollback | Exercised end to end with a healthy and a degraded candidate, including a gate refusal ([transcript](docs/demo_shadow_rollback.md)). |
| Training/serving parity | Guarded by a test that runs in CI ([`test_feature_parity.py`](backend/tests/test_feature_parity.py)). |
| Live backend | **Not deployed yet.** Render Blueprint and a verification script are included; fill in the URL below once deployed. |
| Live frontend | Vercel (needs `VITE_API_URL` pointing at a live backend to work). |
| Database in the default/deployed mode | **SQLite**, ephemeral on Render. Postgres code paths exist but are not the deployed mode and were not exercised here. |

Live URLs: _backend: TODO after deploy_ , _frontend: TODO_ (run `scripts/verify_deployment.py` against
them before putting them on a resume; see [Deployment](#deployment)).

---

## Results

Dataset: IBM Telco Customer Churn, 7,043 rows, 26.54% churn, 11 blank `TotalCharges` values (all
tenure 0). Split: stratified 60/20/20, seed 42 (4,225 / 1,409 / 1,409 rows). The test rows are exactly
the historical 80/20 test split. Model: CatBoost (depth 4, learning rate 0.03, L2 10, no class weight,
299 trees chosen by early stopping on validation). All settings live in `params.yaml`.

```bash
python model/training/train.py              # fit on train, early-stop + calibrate on validation
python model/training/evaluate.py           # CV comparison, test once, reliability, slices (~4 min)
python model/training/threshold_analysis.py # cost-based threshold on calibrated validation scores
```

Cross-validation on train+validation (5 stratified folds, 5,634 rows), mean with 95% interval:

| Model | ROC-AUC | PR-AUC | Brier | Log loss |
|---|---|---|---|---|
| Dummy (predict base rate) | 0.500 | 0.265 | 0.195 | 0.579 |
| Logistic regression (one-hot + scaling) | 0.848 [0.837, 0.859] | 0.665 [0.640, 0.689] | 0.134 [0.129, 0.139] | 0.413 [0.401, 0.426] |
| CatBoost, no class weight (shipped recipe) | 0.848 [0.835, 0.860] | 0.667 [0.640, 0.694] | 0.134 [0.129, 0.139] | 0.414 [0.400, 0.427] |
| CatBoost, balanced class weight (old recipe) | 0.849 [0.837, 0.862] | 0.669 [0.639, 0.700] | 0.160 [0.153, 0.167] | 0.478 [0.463, 0.493] |
| LightGBM | 0.845 [0.831, 0.859] | 0.661 [0.638, 0.685] | 0.136 [0.130, 0.141] | 0.418 [0.402, 0.434] |

Held-out test split, scored once (1,409 rows): shipped artifact ROC-AUC 0.8464, PR-AUC 0.6655,
Brier 0.1350, log loss 0.4138; logistic regression refit on train+validation 0.8449 / 0.6492 / 0.1365 /
0.4165. Full tables, including the paired bootstraps: [docs/model_comparison.md](docs/model_comparison.md).

What this does and does not say:

- **Nothing beats logistic regression.** Paired bootstrap on pooled out-of-fold scores, CatBoost minus
  logistic regression: ROC-AUC -0.0008 [-0.0034, +0.0018], Brier +0.0002 [-0.0011, +0.0013]. LightGBM:
  ROC-AUC -0.0038 [-0.0076, -0.0001]. CatBoost stays because the serving, SHAP and canary code are built
  around it, not because it scores better, and logistic regression is kept running next to it as a live
  challenger (see [below](#active-model-and-standing-challenger)).
- **The score is a calibrated probability.** The old recipe's balanced class weight (2.77) bought no
  ranking (+0.0010 [-0.0016, +0.0037] AUC) and pushed scores up (Brier +0.026, ECE 0.146 on test), so it
  was dropped. Calibration was then chosen on validation by 5-fold cross-fitting (lowest log loss among
  identity, Platt and isotonic): identity 0.4218, Platt 0.4222, isotonic 0.4704. The unweighted model
  needed no correction (Platt fit a = 0.980, b = 0.014), so the shipped calibration file is the
  identity. Test ECE 0.018 ([diagram](docs/reliability_diagram.png)).
- **No test-set tuning.** The previous model was early-stopped on the same rows it was evaluated on;
  that is fixed. The test fingerprint is recorded in `model/artifacts/training_metadata.json`.
- **One public, widely used dataset.** Nothing here is validated against real retention outcomes. See
  the [model card](docs/model_card.md) for intended use, slices and limitations.

## Decision threshold

`POST /predict` uses `DECISION_THRESHOLD` (default **0.38**) when the request does not pass
`?threshold=`. The value comes from `model/training/threshold_analysis.py`, which:

1. scores the validation split and calibrates it out of fold (each row by a calibrator that did not see it),
2. picks the grid threshold with the highest expected net benefit on those scores (the test split is
   never used to pick it),
3. reports the closed-form break-even threshold next to it, and
4. reports everything once on the held-out test split.

**Stated assumptions** (not measured business data; edit `params.yaml` -> `threshold`): contacting a
customer costs an offer cost; a contacted churner is saved with some probability; a saved customer is
worth 12 months of the mean churner's monthly charge ($74.86, computed on train+validation only) times
a margin.

With a calibrated probability p, contacting pays off when `p x save_rate x value > offer_cost`, so the
break-even threshold is `offer_cost / (save_rate x value)`. Two scenarios are reported on purpose:

| Scenario | Offer cost | Save rate | Value of saved customer | Empirical (validation) | Closed form |
|---|---:|---:|---:|---:|---:|
| `margin_with_incentive` (**primary**) | $50 | 30% | $449.16 (12 x $74.86 x 50%) | **0.38** | 0.371 |
| `revenue_cheap` | $20 | 30% | $898.32 (12 x $74.86) | 0.06 | 0.074 |

Net benefit per 1,000 customers on the held-out split (primary scenario):

| Policy | Flagged | Precision | Recall | Net benefit |
|---|---:|---:|---:|---:|
| Contact nobody | 0% | n/a | 0 | $0 |
| Contact everybody | 100% | 0.265 | 1.00 | -$14,233 |
| Threshold 0.50 | 20.4% | 0.667 | 0.513 | $8,142 |
| Threshold 0.62 (previous default) | 11.4% | 0.752 | 0.324 | $5,858 |
| Threshold 0.38 (new default) | 31.4% | 0.580 | 0.687 | **$8,858** |
| Closed form 0.371 | 32.0% | 0.581 | 0.701 | $9,052 |

- **Gain over the untuned baseline is not significant.** Against a plain 0.50 cut-off, 0.38 earns
  +$716 per 1,000 customers on test (95% bootstrap CI -$421 to +$1,888). With 1,409 test rows that is
  indistinguishable from zero; the curve is flat between roughly 0.35 and 0.50. What the analysis
  establishes is the *region* of good thresholds under the stated economics, not a precise optimum.
- 0.62 (the previous default) is not a fair baseline: it was tuned on the old class-weighted model's
  upward-biased scores. On calibrated scores it flags too few customers; 0.38 beats it by +$2,999 per
  1,000 (95% CI +$1,431 to +$4,682), which mostly measures that mismatch.
- **Empirical vs closed form.** The closed-form threshold assumes perfectly calibrated scores and an
  infinite sample; the empirical one maximises a step function on 1,409 validation rows. The net-benefit
  curve is flat around the optimum (validation: $8,732 at 0.35, $9,392 at 0.40, $8,843 at 0.45 per 1,000),
  so the two differ by about one grid step and are indistinguishable on test (closed form minus empirical
  +$194, 95% CI -$71 to +$506). Calibration is what makes the closed form usable at all: on the old
  weighted scores it would have pointed at the wrong place.
- In the cheap-outreach scenario contacting almost everyone is right (empirical 0.06, closed form 0.074).
  **The right threshold is a business decision**, and it moves a lot with the economics (validation-chosen
  threshold, closed form, and test net benefit per 1,000 at the empirical threshold):

| Offer cost | Save rate | Empirical | Closed form | Model $/1,000 | Contact-everyone $/1,000 |
|---:|---:|---:|---:|---:|---:|
| $25 | 10% | 0.52 | 0.557 | $1,057 | -$13,078 |
| $25 | 30% | 0.24 | 0.186 | $18,313 | $10,767 |
| $25 | 50% | 0.06 | 0.111 | $40,470 | $34,612 |
| $50 | 10% | 0.94 (grid edge: contact nobody) | 1.113 (> 1: never contact) | $0 | -$38,078 |
| $50 | 30% | **0.38** | 0.371 | $8,858 | -$14,233 |
| $50 | 50% | 0.25 | 0.223 | $26,861 | $9,612 |
| $100 | 10% | 0.94 (grid edge) | 2.226 (> 1: never contact) | $0 | -$88,078 |
| $100 | 30% | 0.72 | 0.742 | $739 | -$64,233 |
| $100 | 50% | 0.38 | 0.445 | $9,522 | -$40,388 |

Override per request (`?threshold=0.4`) or per deployment (`DECISION_THRESHOLD=0.4`). `params.yaml`
`evaluation.decision_threshold` must equal the API default (a test enforces it). The UI's
low/medium/high risk tiers use fixed cut-offs (0.33 / 0.66) and are independent of this threshold.

## Active model and standing challenger

Because the two models tie, the simpler one is not thrown away: `train.py` also trains logistic
regression on the same split (calibration chosen the same way; identity won again) and exports it as
JSON (`model/artifacts/logreg_challenger.json`: coefficients, imputation medians, scaling and one-hot
weights, scored with numpy, no pickles). At startup the API attaches it to the shadow slot whenever no
other candidate is being tested (`CHALLENGER_ENABLED=true`, default), so every `/predict` also returns
the challenger's `shadowProbability` and `GET /api/v1/system/canary` counts how often the two disagree
on live traffic. Shipped artifacts on the test split (`python model/training/evaluate.py`):

| | ROC-AUC | PR-AUC | Brier | Log loss |
|---|---:|---:|---:|---:|
| CatBoost (active) | 0.8464 | 0.6655 | 0.1350 | 0.4138 |
| Logistic regression (challenger) | 0.8454 | 0.6517 | 0.1361 | 0.4159 |
| Active minus challenger [95% CI] | +0.0010 [-0.0041, +0.0059] | +0.0138 [-0.0024, +0.0297] | -0.0011 [-0.0034, +0.0010] | -0.0022 [-0.0082, +0.0041] |

Their decisions differ at threshold 0.38 for 3.4% of test customers (Spearman 0.985). Promoting the
challenger is one gated `POST /models/promote`; `/explain` then returns exact linear log-odds
contributions instead of TreeSHAP. Shadow-testing another candidate displaces the challenger until the
next startup; a challenger rejected by the canary is not re-attached. Rationale and trade-offs:
[ADR 0001](docs/decisions/0001-catboost-active-logreg-challenger.md).

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
[`docs/demo_shadow_rollback.md`](docs/demo_shadow_rollback.md)) drives the real HTTP routes with
replayed held-out customer rows: a routine retrain (v2, test AUC 0.847) shadows at 2.2% disagreement
(9 of 400) and passes the gate; a degraded retrain (v3, trained on permuted labels) is refused by the
gate with a 409, then put in shadow and rolled back automatically after 60 compared requests at 33.3%
disagreement, with v2 still serving.

```bash
python model/training/build_demo_candidates.py   # writes model/artifacts/demo/ (git-ignored)
python scripts/demo_shadow_rollback.py --out docs/demo_shadow_rollback.md
```

The degraded candidate's test AUC is 0.642, not 0.5. This was checked, not assumed
([docs/permutation_check.md](docs/permutation_check.md), `python model/training/permutation_check.py`):
across 20 models trained on independently permuted labels, AUC against the true test labels averaged
0.529 with SD 0.125 (range 0.241 to 0.735), while the same scores re-assigned to random rows give SD
0.021 (theory: 0.017). Each permuted model's AUC tracks the correlation of its scores with the real
model's scores (Pearson r = 0.977 over the 20 runs). A model fitted to noise learns no churn signal but
is still a function of tenure, charges and contract, which are strongly predictive, so by chance it can
rank churners above or below chance (here a Platt fit on the permuted labels flipped its sign). It is
far below the healthy model either way, which is what the gate and canary need.

Running the original demo exposed two real defects in the canary code, fixed earlier and covered by
regression tests:

1. **Inflated disagreement rate.** Disagreements were counted on every request but divided by the
   number of requests served by the shadow (only `CANARY_TRAFFIC_PERCENT` of traffic), so the rate
   could exceed 100%. The rate is now measured over all compared requests.
2. **Rollback hit the wrong model.** Automatic rollback called the manual `rollback()`, which demotes
   the *active* model. It now calls `abort_canary()`, which rejects the shadow candidate and leaves the
   active model alone.

The demo output is not fully deterministic: which requests are served by the canary depends on random
prediction ids. The disagreement counts and pass/fail outcome depend only on the two models and the
replayed rows.

## Bugs found during the evaluation/safety pass

Each is fixed and has a regression test.

1. **Test-split leakage in the old training run.** The shipped model was early-stopped on the 20% split
   it was evaluated on. Now early stopping uses the validation split (`train.py`).
2. **Promotion was not gated.** `ModelValidationGate` existed but `POST /models/promote` never called it.
   Now it does (`test_promotion_gate.py`).
3. **Validation errors from custom validators returned 500.** The 422 handler put the raw `ValueError`
   from pydantic's error context into the JSON response, which cannot be serialised. Fixed with
   `jsonable_encoder` (`test_override_requires_a_reason`).
4. **Password changes did not take effect.** `AuthService` cached each user record, including the
   password hash, for `CACHE_TTL_SECONDS` (and in Redis when enabled), so a replaced password kept
   working. The cache was removed (`test_changed_password_takes_effect_immediately`).
5. **Production checks could never fire on Render.** `render.yaml` did not set `ENVIRONMENT`, so a deployed
   API ran as `development`. The Blueprint now sets `ENVIRONMENT=production`.
6. **Registry and runtime diverged after a restart.** The registry persists (SQLite file or Postgres)
   but the runtime always started from the default artifact, so after a promotion and a restart the API
   reported v2 as active while serving v1. Startup now loads the registry's active and shadow artifacts;
   an unloadable active artifact aborts startup (`test_restart_serves_the_registry_active_model`).
7. Minor: the threshold analysis valued a saved customer with the mean monthly charge of churners over
   the whole dataset, test labels included. It now uses train+validation only.

## Architecture

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

The Postgres path exists (SQLAlchemy models, repositories, Alembic migrations `0001`, `0002`) but has
not been run as part of this verification; only SQLite was exercised. On a free Render instance the
SQLite file also sits on an ephemeral disk and resets on every deploy.

## API

Interactive docs at `/docs`. Auth is JWT with roles `admin`, `analyst`, `viewer`.

- Auth: `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `GET /api/v1/auth/me`
- Predictions: `POST /api/v1/predictions/predict` (**no auth required**, rate limited per IP),
  `POST .../explain` (no auth), `GET .../history`, `POST .../recommend`, `POST .../feedback`,
  `POST .../outcome`, `GET .../feedback/summary`
- Models (admin): `GET /api/v1/models`, `POST .../register`, `POST .../shadow`, `POST .../promote`
  (validation gate; `override_gate` + `override_reason` optional), `POST .../rollback`
- System: `GET /api/v1/system/health`, `/ready`, `/metrics`, `/monitoring`, `/canary`
- Jobs: `POST /api/v1/jobs/batch-score`, `/reports`, `/retrain`, `GET /api/v1/jobs`, `/{id}`, `/{id}/download`
- Legacy unauthenticated `POST /predict` and `POST /explain` for older clients.

`/predict` and `/explain` are limited to `PREDICT_RATE_LIMIT_PER_MINUTE` (default 30) per client IP.

## Run locally

Requirements: Python 3.13, Node 18+. The training CSV is tracked with DVC and is not in git: run
`dvc pull`, or place the IBM Telco CSV at `data/Telco-Customer-Churn.csv`. The API itself does not
need it, except for model promotion (the gate's evaluation data); training scripts, the load test and
the demo do.

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
`requirements.txt` is the full pinned environment (training, MLOps, docs tooling; note it is saved as
UTF-16); the API only needs `requirements-runtime.txt`.

### Tests

```powershell
$env:PYTHONPATH = (Get-Location).Path
$env:MLFLOW_ALLOW_FILE_STORE = "true"
pip install -r requirements.txt     # tests need the full set (mlflow, pytest, httpx)
pytest -q backend/tests
```

Last run (Python 3.13, dataset present): **105 passed, 7 skipped**. The 7 skips are Evidently drift
tests, skipped because Evidently is not installed in this environment; I have not run them. CI does not
have the DVC-tracked CSV, so the tests that replay dataset rows skip there; the feature-parity, canary,
gate, auth, calibration, challenger, registry, settings and CORS tests do not need it.

### Reproducing the other measurements

```powershell
python model/training/train.py                       # model + calibration + training_metadata.json
python model/training/evaluate.py                    # docs/model_comparison.md, slice_metrics.md, reliability_diagram.png, evaluation.json, metrics.json
python model/training/threshold_analysis.py          # docs/threshold_analysis.json
python model/training/build_demo_candidates.py       # healthy + degraded demo models
python model/training/permutation_check.py           # 20 permuted-label models -> docs/permutation_check.md (~3 min)
python scripts/demo_shadow_rollback.py               # gate + shadow -> rollback demo
bash loadtest/run_loadtest.sh 20 5 60s               # Locust (needs `pip install locust`; use Git Bash/WSL on Windows)
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

CI (`.github/workflows/ci.yml`) lints, byte-compiles and runs the tests. CD (`cd.yml`) runs behind a
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
`SCHEDULE_RETRAINING_ENABLED`. See `backend/.env.example`.

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
- `backend/.env` and `frontend/.env` are tracked in git. They contain only local development values,
  but the frontend one (`VITE_API_URL=http://127.0.0.1:8000`) is picked up by a Vercel build that does
  not set the variable. Untrack both (`git rm --cached backend/.env frontend/.env`) and copy from the
  `.env.example` files instead.

## Limitations

- Telco is a public benchmark, not real retention data; there are no measured business outcomes.
- The model does not beat a logistic-regression baseline (see Results).
- The threshold and its gain depend on assumed economics; the real values should replace the
  assumptions in `params.yaml` before any real use.
- The promotion gate's default evaluation data overlaps the training data; with real data it should be
  recent labelled outcomes that no candidate was trained on.
- The retraining job (`services/retraining_service.py`) still uses its own simpler recipe (80/20 split,
  no calibration file); its candidates are served uncalibrated and must pass the gate to be promoted.
- The shadow/canary demo uses synthetic candidates and replayed historical rows, not live drift.
- Load test numbers come from one VM with the load generator on the same host, on the previous model;
  `/explain` was not tested; nothing was measured on the deployed instance.
- Default storage is SQLite with in-memory prediction history and audit log. Postgres was not
  exercised.
- The backend had not been deployed or verified on Render at the time of writing.
