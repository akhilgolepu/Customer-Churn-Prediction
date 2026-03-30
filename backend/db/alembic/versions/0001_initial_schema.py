"""Initial schema from SQL blueprint.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-03-30
"""

from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def _read_sql(file_name: str) -> str:
    root = Path(__file__).resolve().parents[3]
    return (root / "db" / file_name).read_text(encoding="utf-8")


def upgrade() -> None:
    op.execute(_read_sql("postgres_schema.sql"))
    op.execute(_read_sql("reporting.sql"))


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS feedback_events CASCADE")
    op.execute("DROP TABLE IF EXISTS simulation_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS predictions CASCADE")
    op.execute("DROP TABLE IF EXISTS model_metrics CASCADE")
    op.execute("DROP TABLE IF EXISTS model_versions CASCADE")
    op.execute("DROP TABLE IF EXISTS user_org_roles CASCADE")
    op.execute("DROP TABLE IF EXISTS roles CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS organizations CASCADE")
