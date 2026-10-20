# ADR 0003: SQLite by default, Postgres as a tested option

Status: accepted

## Context

The live demo runs on a free Render web service: one instance, no managed database, an
ephemeral disk. The codebase also has a full Postgres path (SQLAlchemy models,
repositories, Alembic migrations), which had never been run until the MLOps pass, when
it needed six fixes to work (see the [engineering log](../engineering_log.md)).

## Decision

`DATABASE_BACKEND=sqlite` is the default, including the deployed demo. In that mode the
model registry, feedback and monitoring snapshots live in a SQLite file; prediction
history, the audit log and batch jobs live in memory. `DATABASE_BACKEND=postgres` switches
every repository to Postgres; the same test suite runs against both backends in CI.

## Why

- Zero operational cost for a demo: no database to provision, pay for or secure, and the
  API starts from the Docker image alone.
- The Postgres path is not a promise on paper: the full test suite (in CI), the rollback demo
  and a restart check pass on Postgres 16, so switching is a configuration change.

## Consequences

- On the free Render instance, history, the audit log and registry changes reset on every
  deploy or restart. That is acceptable for a demo and stated in the README.
- In-memory state is per process. With several uvicorn workers each worker has its own
  prediction history and audit log in SQLite mode (the live monitor then sees one worker's
  share); Postgres fixes that. Two things stay per process even on Postgres: the canary
  counters, and the loaded models. A promote, shadow or rollback call switches the model only
  in the worker that handled it; the other workers keep serving the previous model until they
  restart (startup loads what the registry says). The deployed demo runs one worker; a
  multi-worker deployment needs a shared model-version signal (for example, each worker
  re-syncing from the registry on a short interval) before model changes are safe.
- The Postgres event tables currently use a DEFAULT partition; monthly partitions and
  retention are not managed yet.
