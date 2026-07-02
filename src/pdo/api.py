"""Embedding API: drive the PDO agent from Python.

Example::

    from pdo import run_agent

    answer = run_agent("list the markdown files here and summarise the README")

Configuration comes from the environment / ``.env`` exactly like the CLI
(``OPENAI_API_KEY``, ``OPENAI_BASE_URL``, ``OPENAI_MODEL``, …), with keyword
overrides for scripts. Each call uses an ephemeral memory, so it never touches
your interactive sessions.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from .agent.core import Agent
from .agent.memory import MemoryStore
from .config import load_config
from .llm import LLMClient, OpenAIClient
from .tools.registry import get_registry


def run_agent(
    prompt: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    planning: bool = False,
    llm: LLMClient | None = None,
) -> str:
    """Run one task through the PDO agent and return its final answer.

    Args:
        prompt: the task or question.
        model / api_key / base_url / temperature: override the env config.
        planning: enable the pre-planning step for multi-step tasks.
        llm: supply a custom :class:`~pdo.llm.LLMClient` (e.g. a mock in tests
            or another provider implementation); overrides the other LLM args.
    """
    config = load_config()
    if model:
        config.openai_model = model
    if api_key:
        config.openai_api_key = api_key
    if base_url is not None:
        config.openai_base_url = base_url
    if temperature is not None:
        config.temperature = temperature

    if llm is None:
        llm = OpenAIClient(
            api_key=config.openai_api_key,
            model=config.openai_model,
            temperature=config.temperature,
            base_url=config.openai_base_url,
        )

    memory = MemoryStore(Path(tempfile.mkdtemp(prefix="pdo-api-")))
    agent = Agent(config, llm, get_registry(), memory, planning=planning)
    return agent.run_turn(prompt)
