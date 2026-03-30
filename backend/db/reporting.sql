-- Reporting readiness: materialized views + analytics schema.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.kpi_daily_prediction_summary AS
SELECT
    org_id,
    DATE_TRUNC('day', prediction_at) AS day,
    COUNT(*) AS total_predictions,
    AVG(probability) AS avg_probability,
    AVG(risk_score) AS avg_risk_score,
    SUM(CASE WHEN is_churn THEN 1 ELSE 0 END) AS predicted_churn_count
FROM predictions
WHERE deleted_at IS NULL
GROUP BY org_id, DATE_TRUNC('day', prediction_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_kpi_daily_prediction_summary_unique
ON analytics.kpi_daily_prediction_summary (org_id, day);

CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.kpi_daily_feedback_summary AS
SELECT
    org_id,
    DATE_TRUNC('day', event_at) AS day,
    COUNT(*) FILTER (WHERE event_type = 'feedback') AS feedback_events,
    COUNT(*) FILTER (WHERE event_type = 'outcome') AS outcome_events
FROM feedback_events
WHERE deleted_at IS NULL
GROUP BY org_id, DATE_TRUNC('day', event_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_kpi_daily_feedback_summary_unique
ON analytics.kpi_daily_feedback_summary (org_id, day);

-- Refresh examples (run from cron/Airflow):
-- REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.kpi_daily_prediction_summary;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.kpi_daily_feedback_summary;

-- ETL landing tables for BI tools (star schema starter)
CREATE TABLE IF NOT EXISTS analytics.fact_predictions (
    id UUID PRIMARY KEY,
    org_id UUID NOT NULL,
    model_version_id UUID NOT NULL,
    prediction_at TIMESTAMPTZ NOT NULL,
    probability DOUBLE PRECISION NOT NULL,
    risk_score DOUBLE PRECISION NOT NULL,
    risk_tier TEXT NOT NULL,
    is_churn BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics.fact_feedback_events (
    id UUID PRIMARY KEY,
    org_id UUID NOT NULL,
    prediction_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
