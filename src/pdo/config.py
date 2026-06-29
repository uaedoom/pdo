"""Application configuration.

All configuration comes from environment variables (optionally loaded from a
``.env`` file) and is validated at startup with ``pydantic``. We deliberately do
not depend on ``pydantic-settings`` to keep the dependency surface small; reading
the environment by hand is trivial and keeps the failure messages friendly.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator


class ConfigError(RuntimeError):
    """Raised when configuration is missing or invalid.

    The message is intended to be shown directly to the user, so it must be
    human-friendly rather than a stack trace.
    """


class Config(BaseModel):
    """Validated runtime configuration."""

    openai_api_key: str = Field(..., min_length=1)
    openai_model: str = Field(default="gpt-4.1-mini", min_length=1)
    # Optional override of the API endpoint. Set this to use an OpenAI-compatible
    # provider such as OpenRouter, a local model server, etc. None = OpenAI.
    openai_base_url: str | None = Field(default=None)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    # Render assistant replies as Markdown (vs. raw token streaming).
    render_markdown: bool = Field(default=True)
    # Accent color theme name (see pdo.theme.THEMES).
    theme: str = Field(default="cyan")
    # Per-tool permission policy: tools that are blocked, or require confirmation.
    deny_tools: list[str] = Field(default_factory=list)
    ask_tools: list[str] = Field(default_factory=list)

    @field_validator("openai_api_key", "openai_model")
    @classmethod
    def _strip(cls, value: str) -> str:
        return (value or "").strip()


def load_config() -> Config:
    """Load and validate configuration from the environment.

    Raises:
        ConfigError: if required values are missing or invalid. The message is
            safe to print directly to the terminal.
    """
    load_dotenv()  # no-op if there is no .env file

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "OPENAI_API_KEY is not set.\n\n"
            "Set it before running PDO, for example:\n"
            "  export OPENAI_API_KEY=sk-...\n\n"
            "or copy .env.example to .env and fill it in."
        )

    raw_temperature = os.getenv("TEMPERATURE", "0.2") or "0.2"
    try:
        temperature = float(raw_temperature)
    except ValueError as exc:
        raise ConfigError(
            f"TEMPERATURE must be a number between 0 and 2 (got {raw_temperature!r})."
        ) from exc

    markdown_raw = os.getenv("PDO_MARKDOWN", "1").strip().lower()
    render_markdown = markdown_raw not in ("0", "false", "no", "off")

    def _csv(name: str) -> list[str]:
        return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]

    try:
        return Config(
            openai_api_key=api_key,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "").strip() or None,
            temperature=temperature,
            render_markdown=render_markdown,
            theme=os.getenv("PDO_THEME", "cyan").strip() or "cyan",
            deny_tools=_csv("PDO_DENY_TOOLS"),
            ask_tools=_csv("PDO_ASK_TOOLS"),
        )
    except ValidationError as exc:
        # Surface the first, most relevant validation problem in plain language.
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first["loc"])
        raise ConfigError(f"Invalid configuration for {field}: {first['msg']}.") from exc


# --- Filesystem locations -------------------------------------------------- #
#
# Runtime state (the JSON memory store and rotating logs) lives under a single
# "home" directory. By default that is the installed package directory so a
# freshly cloned repo "just works"; set PDO_HOME to relocate it (e.g. ~/.pdo).


def get_home_dir() -> Path:
    """Return the base directory for PDO runtime state."""
    env = os.getenv("PDO_HOME")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent


def get_data_dir() -> Path:
    """Return (creating if needed) the directory holding JSON state files."""
    path = get_home_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_logs_dir() -> Path:
    """Return (creating if needed) the directory holding log files."""
    path = get_home_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_plugins_dir() -> Path:
    """Return (creating if needed) the directory scanned for user tool plugins.

    Drop a ``.py`` file defining a ``Tool`` subclass here and PDO loads it on
    startup. Defaults to ``<home>/plugins`` (override the home with ``PDO_HOME``).
    """
    path = get_home_dir() / "plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_mcp_config_path() -> Path:
    """Return the path to the MCP servers config file (``<home>/mcp.json``)."""
    return get_home_dir() / "mcp.json"


def get_skills_dir() -> Path:
    """Return (creating if needed) the directory scanned for user skills.

    Each ``.md`` file becomes a reusable slash command (e.g. ``review.md`` →
    ``/review``). Defaults to ``<home>/skills``.
    """
    path = get_home_dir() / "skills"
    path.mkdir(parents=True, exist_ok=True)
    return path
