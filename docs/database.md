# Database Architecture Notes

## Shadow Model (Current State)

- Active model id: 87b88c59-4e6c-4554-a274-fdfb9685f54e (v1)
- Shadow model id: dd1dfda5-ae41-472e-b396-e10d3d3ba752 (v2-shadow)
- Shadow artifact URI: model/artifacts/catboost_churn.cbm
- Active and shadow currently resolve to the same artifact file on disk.

## Recommended Runtime Stack

- PostgreSQL: system-of-record for transactional/domain data.
- Redis: cache hot reads, rate-limit counters, session/token acceleration, short-lived queue coordination.
- Object storage (S3/Azure Blob): model artifacts, batch uploads, generated reports.

## Data-Model Principles Implemented in SQL

- Multi-tenant boundary via org_id across business tables.
- Role model: users, organizations, roles, and user_org_roles join table.
- Prediction lineage captured with raw_input + engineered_snapshot + model_version_id.
- Immutable audit/event intent via append-only partitioned event tables.
- Soft deletes via deleted_at and full created_at/updated_at timestamps.

## Indexing and Partitioning

- Time + org + risk_score indexes included for operational queries.
- Partition strategy by month on feedback_events and audit_logs.
- Add a migration/job each month to create next partitions.

## PII Handling Policy (baseline)

- Encrypt sensitive profile fields (pii_ciphertext / app-level envelope encryption).
- Mask sensitive columns in app/API logs.
- Implement retention windows by table class:
  - audit/event logs: long retention with legal policy.
  - raw prediction payloads: minimum viable retention for explainability/compliance.
- Add right-to-erasure workflow using tombstone + selective redaction where legally required.

## Backup and Restore Drills

- Daily full backup + PITR WAL archival.
- Quarterly restore drill into isolated environment.
- Validate checksum and app-level smoke tests after restore.

## Reporting Readiness

- Materialized views for daily KPI dashboards in analytics schema.
- ETL into analytics.fact\_\* tables for BI tooling and stable semantic layer.
