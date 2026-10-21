from __future__ import annotations

from core.settings import get_settings


def test_allowed_origins_env_var_is_honoured(monkeypatch):
    """Regression: ALLOWED_ORIGINS used to be ignored (alias without populate_by_name)."""
    monkeypatch.setenv("ALLOWED_ORIGINS", '["https://app.example.com", "https://staging.example.com"]')
    get_settings.cache_clear()
    try:
        assert get_settings().allowed_origins == ["https://app.example.com", "https://staging.example.com"]
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example.com, https://b.example.com")
        get_settings.cache_clear()
        assert get_settings().allowed_origins == ["https://a.example.com", "https://b.example.com"]
    finally:
        get_settings.cache_clear()
