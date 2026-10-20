# Engineering log: bugs found and fixed

Every defect found while hardening this project, in the order the passes found them. Each was fixed;
where code changed there is a regression test (named in brackets or in the text). Numbers and claims
here come from commands described in the README.

## Canary demo (verification pass before the evaluation work)

1. **Inflated disagreement rate.** Disagreements were counted on every request but divided by the
   number of requests served by the shadow (only `CANARY_TRAFFIC_PERCENT` of traffic), so the rate
   could exceed 100%. The rate is now measured over all compared requests.
2. **Rollback hit the wrong model.** Automatic rollback called the manual `rollback()`, which demotes
   the *active* model. It now calls `abort_canary()`, which rejects the shadow candidate and leaves the
   active model alone.

## Evaluation and safety pass

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

## MLOps pass

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

## Packaging and audit pass (2026-10-20)

1. **The dashboard header showed numbers nobody measured**: "Validation: AUC 0.84 / F1 0.73" and
   "Last trained: Mar 2026" were hard-coded in `Dashboard.tsx`; no command in the repo produces that
   F1 (it depends on a threshold that is not stated). It now shows the measured test ROC-AUC (0.846).
   [`test_dashboard_states_the_measured_test_auc`]
2. **The README quoted "2.97% decision disagreement in the load test"**, which no committed output
   backs. Replaced with the offline 3.4% from `docs/evaluation.json` and the live metric's name; the
   load-test CSVs behind the throughput numbers are now committed in `docs/loadtest/`.
   [`test_load_numbers_match_the_committed_locust_csvs`]
3. **`dvc.lock` was stale on `main`**: Tier 3 edited pipeline dependencies (`common.py`,
   `dataset_registry.py`, the dataset catalog) without re-running DVC, so `dvc status` reported every
   stage as changed. `dvc repro` re-ran in 5 min 12 s; every report, the threshold analysis and the
   golden predictions came out byte-identical, and the model differs only in CatBoost's random
   `model_guid`. The README's "reproduce byte for byte" was too strong for the `.cbm` file and is
   reworded.
4. **The README said the whole suite passed on Postgres**, but CI has no dataset and skips the
   full-dataset check there too. The counts now say what CI reports.
5. **Three requirement files could drift** (and a fourth, `requirements-mlops.txt`, was unpinned and
   unused). Replaced by one pinned `requirements.txt` of direct dependencies, cut from a 232-line
   environment freeze that included unused packages (Celery, Litestar, Flask, Graphene).
   [`test_every_imported_package_is_declared`]
6. `docker-compose.yml` hard-coded `ALLOWED_ORIGINS`, so the frontend could not be opened on any origin
   other than `http://localhost:5173`; it is now overridable, with the same default.

