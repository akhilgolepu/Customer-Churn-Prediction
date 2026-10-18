"""Default partitions and event_at defaults for the partitioned event tables.

Revision ID: 0003_event_default_partitions
Revises: 0002_job_runs_and_indexes
Create Date: 2026-10-18

audit_logs and feedback_events are range-partitioned by event_at, but 0001 only
created March 2026 partitions and nothing created later months, so from April
2026 on every audit/feedback insert failed ("no partition of relation found").
A DEFAULT partition catches every row; monthly partitions can be added later for
retention/performance.

The same tables declared event_at NOT NULL without a default, while the ORM
models (db/models.py) declare server_default=now(); the monitoring-snapshot and
feedback/outcome inserts rely on it and failed with a NOT NULL violation.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0003_event_default_partitions"
down_revision = "0002_job_runs_and_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE IF NOT EXISTS audit_logs_default PARTITION OF audit_logs DEFAULT")
    op.execute("CREATE TABLE IF NOT EXISTS feedback_events_default PARTITION OF feedback_events DEFAULT")
    op.execute("ALTER TABLE audit_logs ALTER COLUMN event_at SET DEFAULT now()")
    op.execute("ALTER TABLE feedback_events ALTER COLUMN event_at SET DEFAULT now()")


def downgrade() -> None:
    op.execute("ALTER TABLE feedback_events ALTER COLUMN event_at DROP DEFAULT")
    op.execute("ALTER TABLE audit_logs ALTER COLUMN event_at DROP DEFAULT")
    op.execute("DROP TABLE IF EXISTS feedback_events_default")
    op.execute("DROP TABLE IF EXISTS audit_logs_default")
