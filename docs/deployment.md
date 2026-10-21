# Deployment, API and configuration

How the live demo is deployed (Render + Vercel), the API surface, environment variables and
security notes. Local and Docker runs are in [mlops.md](mlops.md#running-locally).

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
   Memory: the API container used 247 MiB after a predict and an explain (`docker stats`, 2026-10-20),
   within a 512 MB free instance. The Docker image does not contain the training CSV, so promotions on
   the deployed API are blocked by the gate unless `PROMOTION_EVAL_DATA_PATH` points at a labelled file
   (or an admin overrides with a reason).
2. **Vercel**: project root `frontend`, environment variables `VITE_API_URL=https://<your-api>.onrender.com`,
   `VITE_DEMO_ANALYST_PASSWORD` and `VITE_DEMO_VIEWER_PASSWORD` (same values as on Render; they are
   compiled into the public JavaScript). There is no admin variable: admin signs in by typing the
   password.
3. **Verify end to end** (stdlib only, no installs):
   ```bash
   python scripts/verify_deployment.py https://<your-api>.onrender.com --origin https://<your-app>.vercel.app --password <viewer demo password>
   ```
   It retries the health check for up to 3 minutes while a sleeping free instance wakes (`--wake`),
   then checks readiness, CORS preflight for your frontend origin, login, predict, explain and an
   authenticated route, and exits non-zero on the first failure. Last run against the live demo: 7/7 as analyst and as viewer
   on 2026-10-20.

CI is described in [docs/mlops.md](mlops.md#ci). CD (`cd.yml`) runs behind a
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

