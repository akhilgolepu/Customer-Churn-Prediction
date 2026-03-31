"""Add durable job_runs table and governance indexes.

Revision ID: 0002_job_runs_and_indexes
Revises: 0001_initial_schema
Create Date: 2026-03-31
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0002_job_runs_and_indexes"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS job_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id),
            created_by UUID REFERENCES users(id),
            job_type TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
            attempts INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            idempotency_key TEXT UNIQUE,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            result JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at TIMESTAMPTZ
        )
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS idx_job_runs_org_time ON job_runs (org_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_job_runs_org_status ON job_runs (org_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_job_runs_org_type ON job_runs (org_id, job_type)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_job_runs_org_type")
    op.execute("DROP INDEX IF EXISTS idx_job_runs_org_status")
    op.execute("DROP INDEX IF EXISTS idx_job_runs_org_time")
    op.execute("DROP TABLE IF EXISTS job_runs CASCADE")
