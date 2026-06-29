"""Tests for configuration loading and validation."""
from __future__ import annotations

import pytest

from pdo.config import ConfigError, load_config


def test_missing_api_key_raises_friendly_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Prevent a stray .env on the machine from satisfying the requirement.
    monkeypatch.setattr("pdo.config.load_dotenv", lambda *a, **k: None)

    with pytest.raises(ConfigError) as exc:
        load_config()
    assert "OPENAI_API_KEY" in str(exc.value)


def test_defaults_are_applied(monkeypatch):
    monkeypatch.setattr("pdo.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("TEMPERATURE", raising=False)

    config = load_config()
    assert config.openai_model == "gpt-4.1-mini"
    assert config.temperature == 0.2


def test_base_url_defaults_to_none(monkeypatch):
    monkeypatch.setattr("pdo.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert load_config().openai_base_url is None


def test_base_url_is_read_for_openrouter(monkeypatch):
    monkeypatch.setattr("pdo.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-or-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    assert load_config().openai_base_url == "https://openrouter.ai/api/v1"


def test_invalid_temperature_raises(monkeypatch):
    monkeypatch.setattr("pdo.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TEMPERATURE", "not-a-number")

    with pytest.raises(ConfigError):
        load_config()
