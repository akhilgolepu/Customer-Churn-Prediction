from __future__ import annotations

import sys
from pathlib import Path


# Ensure both repository root and backend directory are importable in tests.
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

for path in (str(REPO_ROOT), str(BACKEND_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_in_memory_cache():
    """The rate limiter and auth caches live in a process-wide in-memory store keyed
    by client IP; without a reset, one test's requests count against the next."""
    from core.cache import cache_client

    cache_client._local_rate_hits.clear()
    cache_client._local_kv.clear()
    yield
    cache_client._local_rate_hits.clear()
    cache_client._local_kv.clear()


@pytest.fixture(autouse=True)
def _clean_postgres():
    """With DATABASE_BACKEND=postgres the per-test SQLITE_PATH isolation does not
    apply, so empty every table (except Alembic's) before each test."""
    import os

    if os.environ.get("DATABASE_BACKEND", "sqlite").lower() != "postgres":
        yield
        return
    from sqlalchemy import create_engine, text

    from core.settings import get_settings

    engine = create_engine(get_settings().postgres_url)
    with engine.begin() as conn:
        tables = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
        )).scalars().all()
        if tables:
            conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))
    engine.dispose()
    yield

