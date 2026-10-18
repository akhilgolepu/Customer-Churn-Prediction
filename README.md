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
| Pipeline | `dvc repro` rebuilds data validation, training, evaluation and the threshold analysis from the raw CSV; runs are logged to MLflow and both models registered; reports reproduce byte for byte ([details](#reproducible-pipeline-dvc--mlflow)). |
| Data validation | One pandera rule table for training data and batch files, the same rules in the `/predict` request model ([details](#data-validation-pandera)). |
| CI | ruff, mypy, tests with coverage (74%) on SQLite **and** Postgres, image build + smoke test + Trivy scan; golden predictions on a committed synthetic sample pin the real model's output ([details](#ci)). |
| Drift | Shifted traffic fires the live monitor's alerts and Evidently's tests and triggers a retraining job ([transcript](docs/demo_drift.md)). |
| Observability | `/metrics` for Prometheus; compose profile with Prometheus + a provisioned Grafana dashboard ([screenshots](#observability-prometheus--grafana)). |
| Load test | Final code, challenger attached: 20 users, 1 worker: p95 25 ms with `/explain` in the mix; capacity about 178 req/s (1 worker) and 290 req/s (2 workers) on a 16-thread desktop ([details](docs/loadtest_results.md)). Not measured on the deployed host. |
| Shadow/canary + rollback | Exercised end to end with a healthy and a degraded candidate, including a gate refusal ([transcript](docs/demo_shadow_rollback.md)). |
| Training/serving parity | Guarded by a test that runs in CI ([`test_feature_parity.py`](backend/tests/test_feature_parity.py)). |
| Live backend | **Not deployed yet.** Render Blueprint and a verification script are included; fill in the URL below once deployed. |
| Live frontend | Vercel (needs `VITE_API_URL` pointing at a live backend to work). |
| Database | **SQLite** by default (ephemeral on Render). **Postgres works and is tested**: full suite and the rollback demo pass on Postgres 16; six Postgres defects were found and fixed on the way ([details](#postgres)). |

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

`python scripts/demo_drift.py --out docs/demo_drift.md` ([transcript](docs/demo_drift.md)) replays 300
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

- [during a load test](docs/img/grafana_loadtest.png): 2,022 compared requests, live
  CatBoost-vs-challenger disagreement 2.97% (3.4% offline on the test split).
- [right after the rollback demo](docs/img/grafana_rollback.png): v2 active (Platt-calibrated), the
  degraded v3's disagreement at 33.3% over 60 compared requests, one rollback, the gate's 409 in the
  error panel. Transcript: [docs/demo_shadow_rollback_live.md](docs/demo_shadow_rollback_live.md).

### Postgres

`DATABASE_BACKEND=postgres` now works and is tested: the whole suite passes on SQLite and on Postgres 16
(150 tests each, also in CI), the rollback demo passes against the API container on Postgres
([transcript](docs/demo_shadow_rollback_postgres.md)), and predictions, audit events, the registry and
batch jobs are persisted (checked in the tables; after a container restart the API still serves the
promoted v2). Getting there meant fixing six defects in a path that had never been run (see the bug
list). Run it with `DATABASE_BACKEND=postgres docker compose --profile postgres up --build`.

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

## Bugs found during the MLOps pass

Each is fixed and covered by a regression test (named in brackets) unless noted.

Drift and monitoring

1. **The Evidently drift module never ran.** `requirements.txt` pins Evidently 0.7.21, which moved the
   API the code imported (`evidently.report`) under `evidently.legacy`; the import failed, a flag
   silently disabled the module, and its 7 tests wrapped `ImportError` in `pytest.skip`, so they were
   always skipped. (The README blamed a missing install.) Ported to the 0.7 legacy API; the tests now
   run and skip only explicitly. [`test_drift_detection.py`]
2. **Even with Evidently, no drifted feature would have been reported.** The parser looked for a dict
   key and a list that do not exist in Evidently's output, and the summary counted every column as
   drifted (`drift_share` always 1.0). One skipped test also asserted an alert for perfect predictions
   (AUC 1.0); it now uses degraded scores. [`test_detect_drift_present`, `test_performance_drift_detection`]
3. **The live monitor's `TotalServices` signal was always 0.** It is an engineered feature, not part of
   the stored request, so it was never found. [`test_total_services_signal_reflects_the_requests`]
4. **The live monitor froze after 5,000 predictions in SQLite mode** (it read the oldest page of the
   history) **and swapped its windows on Postgres** (newest-first ordering, so drift deltas had the
   wrong sign). Both repositories now provide `recent()`. [`test_monitor_watches_the_latest_window_not_the_first`]
5. **A "scheduled" retrain fired 30 minutes after every restart**, drift or not: the last-retrain
   timestamp started at 0, so the 24-hour interval had always elapsed. [`test_no_retrain_shortly_after_startup_without_drift`]

Postgres (`DATABASE_BACKEND=postgres` had never been run)

6. **The API could not start unless launched from `backend/`**: Alembic's `script_location` was
   relative to the working directory. (Startup on Postgres in every test.)
7. **Running the migrations silenced the application's loggers** (`fileConfig` defaults to
   `disable_existing_loggers=True`, and migrations run inside API startup).
8. **Every repository read failed with `DetachedInstanceError`**: sessions expired objects on commit
   and the repositories read them afterwards. (`expire_on_commit=False`; whole suite on Postgres.)
9. **Every prediction failed after March 2026**: `audit_logs` and `feedback_events` are partitioned by
   month but only March 2026 partitions were ever created, and every prediction writes an audit event.
   Migration `0003` adds DEFAULT partitions.
10. **Monitoring snapshots, feedback and outcomes failed with a NOT NULL violation**: `event_at` had no
    default although the ORM declared one. Migration `0003` adds it. [`test_feedback_and_outcome_round_trip`]
11. **Automatic canary rollback silently failed**: the `stage` CHECK constraint did not allow
    `rejected`, the prediction path swallowed the exception, and the bad candidate stayed in shadow.
    Migration `0004`; the failure is now logged. [`test_abort_canary_through_the_app_on_the_configured_backend`]

Packaging and runtime

12. **A locally built image refused to start**: `.dockerignore` did not exclude `backend/data/*.db`, so
    the local registry (and local predictions) were baked into the image, and the registry stored the
    seed model as an absolute Windows path, which does not exist in a Linux container. The seed is now
    repo-relative, old absolute paths are mapped onto the checkout, and local state is excluded.
    [`test_app_starts_with_a_registry_seeded_on_another_machine`]
13. **`model_validation_service` was imported under two module names** (`backend.services...` in the
    registry, gate and some tests, `services...` elsewhere), so it existed twice in memory and a patch
    or `isinstance` check on one copy would miss the other. Found by mypy, which also flagged ORM
    timestamp columns typed as `str`.
14. **The retraining job wrote into the repository** (`catboost_info/` in the working directory, models
    and bundles under `model/artifacts/`). `RETRAINING_OUTPUT_DIR` redirects them; CatBoost no longer
    writes training logs.

Test and tooling hygiene

15. The rate limiter's in-memory counters leaked between tests (a 500-request test made later tests
    fail with 429); `conftest.py` now resets them.
16. The venv had pandas 3.0.2 while the lock pins 2.2.3. Aligned to the lock and re-ran the pipeline:
    every generated report was byte-identical under both versions.
17. My own `tasks.py loadtest` left uvicorn's worker processes running on Windows (`terminate()`
    stops only the parent); it now stops the whole process tree.

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

Postgres mode runs Alembic migrations `0001` to `0004` on startup and is covered by the full test suite
and the rollback demo (see [Postgres](#postgres)). On a free Render instance the SQLite file sits on an
ephemeral disk and resets on every deploy.

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
`requirements.txt` is the full pinned environment (training, MLOps, docs tooling; note it is saved as
UTF-16); the API only needs `requirements-runtime.txt`.

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

Last run (Python 3.13): **150 passed, 0 skipped** on SQLite and **150 passed** on Postgres 16; line
coverage 74% of `backend/` and `model/` (tests excluded). Without the DVC dataset only
`test_full_training_csv_passes` skips; everything else uses the committed synthetic sample.

### Reproducing the other measurements

```powershell
dvc repro                                            # validate -> train -> evaluate -> threshold -> golden predictions (or: python tasks.py train)
python model/training/permutation_check.py           # 20 permuted-label models -> docs/permutation_check.md (~3 min)
python tasks.py demo                                 # demo candidates, rollback demo, drift demo -> docs/
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

CI is described [above](#ci). CD (`cd.yml`) runs behind a
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
  no calibration file) and its own pre-check with `ModelValidationGate`'s default thresholds (recall >=
  0.65 at a 0.5 cut-off), which differ from the promotion gate's; in the drift demo its candidate failed
  that pre-check. Moving retraining onto `train.py` (or `dvc repro`) is the obvious next step.
- The shadow/canary and drift demos use synthetic candidates, replayed historical rows and an
  artificial shift, not live traffic.
- Load test numbers come from one desktop with the load generator on the same host; nothing was
  measured on the deployed instance. At 20 users the throughput figure is set by the load generator.
- Default storage is SQLite with in-memory prediction history and audit log. Postgres has a DEFAULT
  partition for the event tables but no monthly partition management or retention yet.
- The API image is 2.08 GB, and Trivy lists 8 HIGH vulnerabilities with available fixes in Python
  packages (0 CRITICAL; starlette, python-multipart, setuptools, urllib3 and others); upgrading
  Starlette means a FastAPI upgrade, left to Dependabot.
- The devcontainer was written but not built here.
- The backend had not been deployed or verified on Render at the time of writing.
