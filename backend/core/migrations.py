from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def run_postgres_migrations(postgres_url: str) -> None:
    """Run Alembic migrations to head for Postgres environments."""
    project_root = Path(__file__).resolve().parents[1]
    alembic_ini = project_root / "db" / "alembic.ini"

    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(config, "head")
