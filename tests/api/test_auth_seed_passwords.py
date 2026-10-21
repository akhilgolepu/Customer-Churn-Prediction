"""Seeded user passwords come from the environment; production refuses defaults."""

from __future__ import annotations

import pytest

from core.settings import Settings, get_settings
from services.auth_service import DEV_DEFAULT_PASSWORDS, InsecureConfigurationError, resolve_seed_passwords

STRONG = {"admin_password": "a-Very-long-admin-secret", "analyst_password": "demo-analyst", "viewer_password": "demo-viewer"}


def _settings(**kwargs) -> Settings:
    return Settings(**kwargs)


def test_development_falls_back_to_labelled_insecure_defaults():
    assert resolve_seed_passwords(_settings(environment="development")) == DEV_DEFAULT_PASSWORDS


def test_development_uses_environment_values_when_set():
    resolved = resolve_seed_passwords(_settings(environment="development", **STRONG))
    assert resolved == {"admin": STRONG["admin_password"], "analyst": "demo-analyst", "viewer": "demo-viewer"}


def test_production_refuses_to_start_without_passwords():
    with pytest.raises(InsecureConfigurationError, match="ADMIN_PASSWORD is not set"):
        resolve_seed_passwords(_settings(environment="production", secret_key="s" * 32))


@pytest.mark.parametrize("user", ["admin", "analyst", "viewer"])
def test_production_refuses_published_default_passwords(user):
    values = {**STRONG, f"{user}_password": DEV_DEFAULT_PASSWORDS[user]}
    with pytest.raises(InsecureConfigurationError, match=f"{user.upper()}_PASSWORD is the published development default"):
        resolve_seed_passwords(_settings(environment="production", secret_key="s" * 32, **values))


def test_production_refuses_default_secret_key():
    with pytest.raises(InsecureConfigurationError, match="SECRET_KEY"):
        resolve_seed_passwords(_settings(environment="production", **STRONG))


def test_production_accepts_explicit_values():
    resolved = resolve_seed_passwords(_settings(environment="production", secret_key="s" * 32, **STRONG))
    assert resolved["admin"] == STRONG["admin_password"]


def test_app_refuses_to_start_in_production_with_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    for var in ("ADMIN_PASSWORD", "ANALYST_PASSWORD", "VIEWER_PASSWORD", "SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    try:
        from app_factory import create_app

        with pytest.raises(InsecureConfigurationError):
            create_app()
    finally:
        get_settings.cache_clear()


def test_changed_password_takes_effect_immediately(monkeypatch):
    """Regression: user records (with password hashes) were cached for
    CACHE_TTL_SECONDS, so a replaced password kept working after a restart of
    the auth service within the same process / Redis."""
    from core.exceptions import UnauthorizedError
    from services.auth_service import AuthService

    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    get_settings.cache_clear()
    try:
        AuthService().login("admin", "admin123")  # old password works and would have been cached
        monkeypatch.setenv("ADMIN_PASSWORD", "rotated-admin-secret")
        get_settings.cache_clear()
        rotated = AuthService()
        with pytest.raises(UnauthorizedError):
            rotated.login("admin", "admin123")
        assert rotated.login("admin", "rotated-admin-secret")["access_token"]
    finally:
        get_settings.cache_clear()


def test_frontend_does_not_ship_admin_credentials():
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "frontend" / "src"
    offenders = [
        str(p.relative_to(src))
        for p in src.rglob("*")
        if p.suffix in {".ts", ".tsx", ".js", ".jsx"} and DEV_DEFAULT_PASSWORDS["admin"] in p.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_login_uses_the_environment_password(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ADMIN_PASSWORD", "env-admin-secret")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    get_settings.cache_clear()
    try:
        from app_factory import create_app

        with TestClient(create_app()) as client:
            bad = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
            good = client.post("/api/v1/auth/login", json={"username": "admin", "password": "env-admin-secret"})
        assert bad.status_code == 401
        assert good.status_code == 200
    finally:
        get_settings.cache_clear()
