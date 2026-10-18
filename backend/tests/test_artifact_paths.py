"""Registry artifact paths must survive moving the database between machines/containers."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.settings import get_settings
from repositories.model_registry_repository import ModelRegistryRepository
from repositories.sqlite_store import SQLiteStore

REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL = REPO_ROOT / "model" / "artifacts" / "catboost_churn.cbm"


@pytest.mark.parametrize("foreign", [
    r"G:\other\machine\repo\model\artifacts\catboost_churn.cbm",
    "/home/someone/repo/model/artifacts/catboost_churn.cbm",
])
def test_foreign_absolute_paths_resolve_to_this_checkout(foreign):
    from model_loader import ModelRuntimeManager

    manager = ModelRuntimeManager(MODEL)
    assert manager._resolve_artifact(foreign) == MODEL.resolve()


def test_unknown_paths_are_not_rewritten():
    from model_loader import ModelRuntimeManager

    manager = ModelRuntimeManager(MODEL)
    with pytest.raises(RuntimeError, match="not found"):
        manager.set_shadow_model("/nowhere/at/all/model.cbm")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("CHALLENGER_ENABLED", "false")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def _admin(client):
    tok = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}


def test_registry_seed_uses_a_repo_relative_path(env):
    from app_factory import create_app

    with TestClient(create_app()) as client:
        reg = client.get("/api/v1/models", headers=_admin(client)).json()
    seed = next(v for v in reg["versions"] if v["id"] == reg["active_model_id"])
    assert seed["artifact_path"] == "model/artifacts/catboost_churn.cbm"


def test_app_starts_with_a_registry_seeded_on_another_machine(env):
    """Regression: a registry seeded with an absolute Windows path (the old seed)
    made a Linux container refuse to start once startup synced the runtime."""
    ModelRegistryRepository(
        store=SQLiteStore(str(env / "app.db")),
        default_artifact_path=r"G:\23881A66E2\Projects\Customer_Churn_Predictor\model\artifacts\catboost_churn.cbm",
    )
    from app_factory import create_app

    with TestClient(create_app()) as client:
        assert client.get("/api/v1/system/health").status_code == 200
