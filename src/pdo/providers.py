"""Known LLM providers for the ``/models`` picker.

All three providers expose an OpenAI-compatible chat API, so PDO reaches them
through the same :class:`pdo.llm.OpenAIClient` — only the ``base_url`` and the
API key differ. Adding a provider is just another entry in ``PROVIDERS``.

The model lists are a curated starting point, not an exhaustive catalogue; the
picker always offers a "custom model id" option so any model the provider
supports can be used.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    """Connection details and suggested models for one provider."""

    key: str  # short internal id, e.g. "openai"
    label: str  # human label shown in the menu
    env_key: str  # environment variable holding the API key
    base_url: str | None  # OpenAI-compatible endpoint (None = OpenAI default)
    models: list[str] = field(default_factory=list)


PROVIDERS: dict[str, Provider] = {
    "openai": Provider(
        key="openai",
        label="OpenAI",
        env_key="OPENAI_API_KEY",
        base_url=None,
        models=[
            "gpt-4.1-mini",
            "gpt-4.1",
            "gpt-4.1-nano",
            "gpt-4o",
            "gpt-4o-mini",
            "o4-mini",
        ],
    ),
    "anthropic": Provider(
        key="anthropic",
        label="Anthropic (Claude)",
        env_key="ANTHROPIC_API_KEY",
        # Anthropic's OpenAI-compatibility endpoint.
        base_url="https://api.anthropic.com/v1/",
        models=[
            "claude-sonnet-4-5",
            "claude-opus-4-1",
            "claude-3-7-sonnet-latest",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
        ],
    ),
    "openrouter": Provider(
        key="openrouter",
        label="OpenRouter",
        env_key="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
        models=[
            "openai/gpt-4.1-mini",
            "anthropic/claude-3.7-sonnet",
            "anthropic/claude-3.5-sonnet",
            "google/gemini-flash-1.5",
            "meta-llama/llama-3.3-70b-instruct",
            "deepseek/deepseek-chat",
        ],
    ),
    "ollama": Provider(
        key="ollama",
        label="Ollama (local)",
        env_key="OLLAMA_API_KEY",  # unused; a local server needs no key
        # OpenAI-compatible local endpoint. Override with OLLAMA_BASE_URL.
        base_url="http://localhost:11434/v1",
        models=[
            "llama3.2",
            "llama3.1",
            "qwen2.5",
            "mistral",
            "gemma2",
            "phi4",
            "deepseek-r1",
        ],
    ),
}
