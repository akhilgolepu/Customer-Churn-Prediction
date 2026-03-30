-- PostgreSQL transactional schema (v2)
-- Covers organizations, users/roles, predictions, simulations, model registry,
-- feedback/audit events, soft deletes, and partition-ready event tables.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Shared helpers
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Core identity and tenancy
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    pii_ciphertext BYTEA,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS user_org_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    user_id UUID NOT NULL REFERENCES users(id),
    role_id UUID NOT NULL REFERENCES roles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    UNIQUE (org_id, user_id, role_id)
);

-- Model registry
CREATE TABLE IF NOT EXISTS model_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    version_tag TEXT NOT NULL,
    stage TEXT NOT NULL CHECK (stage IN ('candidate', 'shadow', 'active', 'archived')),
    framework TEXT NOT NULL DEFAULT 'catboost',
    artifact_uri TEXT NOT NULL,
    feature_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    activated_at TIMESTAMPTZ,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    UNIQUE (org_id, version_tag)
);

CREATE TABLE IF NOT EXISTS model_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version_id UUID NOT NULL REFERENCES model_versions(id),
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    split_name TEXT NOT NULL DEFAULT 'validation',
    measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

-- Inference and simulation
CREATE TABLE IF NOT EXISTS predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    requested_by UUID REFERENCES users(id),
    model_version_id UUID NOT NULL REFERENCES model_versions(id),
    shadow_model_version_id UUID REFERENCES model_versions(id),
    request_id TEXT,
    raw_input JSONB NOT NULL,
    engineered_snapshot JSONB NOT NULL,
    probability DOUBLE PRECISION NOT NULL,
    shadow_probability DOUBLE PRECISION,
    risk_score DOUBLE PRECISION NOT NULL,
    risk_tier TEXT NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    is_churn BOOLEAN NOT NULL,
    prediction_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS simulation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    prediction_id UUID NOT NULL REFERENCES predictions(id),
    scenario_name TEXT NOT NULL,
    changed_fields JSONB NOT NULL,
    baseline_probability DOUBLE PRECISION NOT NULL,
    simulated_probability DOUBLE PRECISION NOT NULL,
    delta_probability DOUBLE PRECISION NOT NULL,
    selected_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    run_by UUID REFERENCES users(id),
    run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

-- High-volume event tables partitioned by month
CREATE TABLE IF NOT EXISTS feedback_events (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    prediction_id UUID NOT NULL REFERENCES predictions(id),
    actor_user_id UUID REFERENCES users(id),
    event_type TEXT NOT NULL CHECK (event_type IN ('feedback', 'outcome')),
    payload JSONB NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    PRIMARY KEY (id, event_at)
) PARTITION BY RANGE (event_at);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id),
    actor_user_id UUID REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,
    request_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    event_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    PRIMARY KEY (id, event_at)
) PARTITION BY RANGE (event_at);

-- Example monthly partitions (create per month in migrations/jobs)
CREATE TABLE IF NOT EXISTS feedback_events_2026_03 PARTITION OF feedback_events
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE IF NOT EXISTS audit_logs_2026_03 PARTITION OF audit_logs
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

-- Governance and performance indexes
CREATE INDEX IF NOT EXISTS idx_predictions_org_time ON predictions (org_id, prediction_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_org_risk ON predictions (org_id, risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_sim_runs_org_time ON simulation_runs (org_id, run_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_versions_org_stage ON model_versions (org_id, stage);
CREATE INDEX IF NOT EXISTS idx_feedback_events_org_time ON feedback_events (org_id, event_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_org_time ON audit_logs (org_id, event_at DESC);

-- Touch updated_at automatically
DO $$
DECLARE t RECORD;
BEGIN
    FOR t IN
        SELECT table_name
        FROM information_schema.columns
        WHERE column_name = 'updated_at'
            AND table_schema = 'public'
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%I_set_updated_at ON %I;', t.table_name, t.table_name);
        EXECUTE format('CREATE TRIGGER trg_%I_set_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at();', t.table_name, t.table_name);
    END LOOP;
END $$;
