"""Tests for Phase-2 additions: CLI args, themes, and markdown config."""
from __future__ import annotations

from pdo import theme
from pdo.config import load_config
from pdo.main import _parse_args


def test_parse_args_one_shot_prompt():
    args = _parse_args(["hello", "world"])
    assert args.prompt == ["hello", "world"]
    assert not args.json


def test_parse_args_flags():
    args = _parse_args(["--json", "--no-markdown", "--theme", "green", "hi"])
    assert args.json is True
    assert args.no_markdown is True
    assert args.theme == "green"
    assert args.prompt == ["hi"]


def test_parse_args_version():
    assert _parse_args(["--version"]).version is True


def test_theme_switching():
    assert theme.set_theme("green")
    assert theme.current_theme() == "green"
    assert theme.accent() == "green"
    assert theme.accent_ansi() == "ansigreen"
    # Unknown theme is rejected and leaves the current one unchanged.
    assert not theme.set_theme("not-a-theme")
    assert theme.current_theme() == "green"
    theme.set_theme("cyan")  # reset for other tests


def test_markdown_config_from_env(monkeypatch):
    monkeypatch.setattr("pdo.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    monkeypatch.setenv("PDO_MARKDOWN", "0")
    assert load_config().render_markdown is False

    monkeypatch.setenv("PDO_MARKDOWN", "1")
    assert load_config().render_markdown is True
