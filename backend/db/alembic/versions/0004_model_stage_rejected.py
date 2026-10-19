"""Allow stage 'rejected' on model_versions.

Revision ID: 0004_model_stage_rejected
Revises: 0003_event_default_partitions
Create Date: 2026-10-18

The automatic canary rollback marks the failing shadow candidate 'rejected', but
the Postgres CHECK constraint only allowed candidate/shadow/active/archived, so on
Postgres the rollback raised (and the prediction path swallowed the error): the
bad candidate stayed in the shadow slot and no audit event was written.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0004_model_stage_rejected"
down_revision = "0003_event_default_partitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE model_versions DROP CONSTRAINT IF EXISTS model_versions_stage_check")
    op.execute(
        "ALTER TABLE model_versions ADD CONSTRAINT model_versions_stage_check "
        "CHECK (stage IN ('candidate', 'shadow', 'active', 'archived', 'rejected'))"
    )


def downgrade() -> None:
    op.execute("UPDATE model_versions SET stage = 'archived' WHERE stage = 'rejected'")
    op.execute("ALTER TABLE model_versions DROP CONSTRAINT IF EXISTS model_versions_stage_check")
    op.execute(
        "ALTER TABLE model_versions ADD CONSTRAINT model_versions_stage_check "
        "CHECK (stage IN ('candidate', 'shadow', 'active', 'archived'))"
    )
