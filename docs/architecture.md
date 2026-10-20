# Architecture

## System

```mermaid
flowchart LR
    subgraph Offline["Offline: training (dvc repro)"]
        CSV[(Telco CSV)] --> V[validate_data<br/>pandera]
        V --> T[train<br/>CatBoost + LR challenger<br/>calibration on validation]
        T --> E[evaluate<br/>CV, bootstrap, slices]
        T --> TH[threshold_analysis<br/>cost-based, validation]
        T --> ML[(MLflow registry<br/>churn-catboost,<br/>churn-logreg-challenger)]
        T --> ART[(model/artifacts<br/>.cbm / .json +<br/>calibration.json)]
    end

    subgraph API["FastAPI service (Render, Docker)"]
        MW[middleware: timing, request id,<br/>size limit, rate limit, CORS]
        PR[prediction service<br/>feature engineering]
        RT[model runtime<br/>active + shadow,<br/>calibrated scores]
        CN[canary<br/>disagreement, auto-rollback]
        REG[registry service<br/>promotion gate]
        MON[monitoring + scheduler<br/>drift alerts, retrain trigger]
        DB[(SQLite default /<br/>Postgres: registry, predictions,<br/>audit, jobs, feedback)]
        MW --> PR --> RT
        PR --> CN
        CN -- rollback --> REG
        REG --> RT
        PR --> DB
        REG --> DB
        MON --> DB
    end

    FE[React frontend<br/>Vercel] -->|HTTPS, JWT| MW
    ART -->|bundled in image /<br/>file, s3, models:/ URI| RT
    ML -.->|models:/name/version| REG
    PROM[Prometheus] -->|GET /metrics| MW
    PROM --> GRAF[Grafana dashboard]
    GH[GitHub Actions<br/>CI: tests on SQLite + Postgres,<br/>image scan] -->|on main: deploy hooks| API
    GH -->|deploy hook| FE
```

The model artifacts ship inside the API image, so the service needs no training data
to serve. Training, evaluation and the threshold analysis run offline and write their
outputs back into the repository (`dvc.lock` records the hashes).

## A prediction request

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API (/api/v1/predictions/predict)
    participant F as feature_engineering
    participant R as model runtime
    participant K as canary
    participant S as store (SQLite/Postgres)
    C->>A: customer record (JSON)
    A->>A: pydantic: types, domains, cross-field rules (422 if inconsistent)
    A->>F: engineer 7 features (same contract as training, parity-tested)
    F->>R: feature row
    R-->>A: active P(churn) (CatBoost, calibrated)
    R-->>A: shadow P(churn) (challenger or candidate), if any
    A->>K: record both, decide which one to serve (CANARY_TRAFFIC_PERCENT)
    K-->>A: served variant, rollback flag
    Note over A,K: disagreement over limit -> abort_canary(): reject the shadow,<br/>active model untouched
    A->>S: prediction history + audit event
    A-->>C: probability, decision at DECISION_THRESHOLD (0.38), shadowProbability
```

## Model lifecycle

| Step | Endpoint / code | Guard |
|---|---|---|
| Train | `dvc repro` (`model/training/train.py`) | data validation stage, test split never used for selection |
| Register | `POST /api/v1/models/register` (file, s3, az or `models:/` path) | admin role |
| Shadow / canary | `POST /api/v1/models/shadow` | disagreement-based automatic rollback ([ADR 0002](decisions/0002-canary-disagreement-over-compared-requests.md)) |
| Promote | `POST /api/v1/models/promote` | promotion gate: 409 on blockers, audited override ([ADR 0005](decisions/0005-promotion-gate-fails-closed.md)) |
| Roll back | `POST /api/v1/models/rollback` | restores the last archived model |
| Restart | app startup | runtime loads what the registry says; refuses to start if the active artifact is missing |

The standing logistic-regression challenger occupies the shadow slot whenever no other
candidate is being tested ([ADR 0001](decisions/0001-catboost-active-logreg-challenger.md)).

## Code map

| Path | Role |
|---|---|
| `backend/routers/api_v1/` | HTTP routes (auth, predictions, models, jobs, system) |
| `backend/services/` | prediction, registry + promotion gate, canary, monitoring, drift (Evidently), jobs/scheduler, retraining, auth |
| `backend/repositories/` | SQLite and Postgres implementations of the same repository interfaces |
| `backend/model_loader.py` | runtime: CatBoost and linear adapters, calibration, bundles, MLflow URIs |
| `backend/core/prometheus.py` | `/metrics` |
| `backend/db/alembic/` | Postgres migrations `0001` to `0004` |
| `model/` | shared feature contract, calibration, linear model export, data schema, MLflow helpers |
| `model/training/` | `train.py`, `evaluate.py`, `threshold_analysis.py`, `second_dataset.py`, `permutation_check.py` |
| `scripts/` | demos (`demo_all.py`, rollback, drift), CI sample generator, deployment check |
| `observability/` | Prometheus config, Grafana provisioning and dashboard |

## How I would run this with real data

This project runs on a public benchmark with no outcomes. With a real customer base,
these are the parts that would change, in order of importance.

**Outcome labels.** Churn has to be defined before anything is trained: for example
"cancels or does not renew within 90 days of the scoring date". That definition
fixes the label delay (a prediction made today is labelled about 90 days later),
which in turn decides how fresh any evaluation can be. Training rows must be built
"as of" the scoring date, using only data available then, or the model learns from
the future. Outcomes would flow back through `POST /predictions/outcome` (or a
nightly batch join), keyed by prediction id, so every score can later be paired with
what happened.

**A control group, or the threshold means nothing.** The cost model assumes a save
rate for contacted churners. That number can only be measured with a randomised
holdout: some high-risk customers are deliberately not contacted. Without it, a
falling churn rate cannot be separated from the campaign's effect, and the threshold
analysis keeps resting on an assumed 30%. I would hold out about 10% of flagged
customers per cycle, and re-run `threshold_analysis.py` with measured offer costs,
save rates and margins.

**Retraining cadence.** Scheduled monthly retraining via the DVC pipeline (not the
simplified `retraining_service.py`), with drift alerts only bringing a run forward.
Each run trains on a rolling window, is evaluated on the most recent fully labelled
month (a time-based split, not a random one), passes the promotion gate against the
current model on that same month, then spends at least a week in shadow before
promotion. The gate's evaluation data would be that recent labelled month, not the
training CSV.

**Monitoring.** Four layers, from fastest to slowest signal:

1. Service health: latency, errors, throughput (`/metrics`, Grafana).
2. Input and score drift: the live monitor and Evidently, as in the demo. These fire
   immediately but only say "the population changed", not "the model got worse".
3. Calibration and ranking on labelled outcomes: once labels arrive, the realised
   churn rate per score band against the predicted probability, and AUC per month.
   This is the signal that should trigger retraining.
4. Business outcome: churn rate and retained revenue in the contacted group vs the
   holdout, per campaign. This is the only measure of whether the system is worth
   running.

**Data and governance.** Postgres instead of SQLite (persistent prediction history
and audit log, already supported and tested), monthly partitions for the event
tables, per-slice monitoring for the groups in the model card (seniors had lower
within-group AUC here), and a review of whether age-related features may be used
in retention decisions at all.
