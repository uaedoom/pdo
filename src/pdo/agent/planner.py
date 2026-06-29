"""Lightweight planner.

For multi-step requests the planner asks the model for a short, ordered list of
concrete steps. The plan is advisory: it is injected as context to keep the
agent focused, not enforced as a rigid script. This stays thin on purpose —
v1 does not build a planning framework.
"""
from __future__ import annotations

import logging

from ..llm import LLMClient
from .messages import Message

logger = logging.getLogger(__name__)

_PLAN_SYSTEM_PROMPT = (
    "You are a planning assistant. Break the user's goal into a short, ordered "
    "list of concrete, actionable steps (at most six). Reply with only the "
    "numbered list — no preamble, no commentary."
)


class Planner:
    """Turns a goal into a short list of steps using the LLM."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def plan(self, goal: str) -> list[str]:
        """Return a list of step strings, or an empty list on failure."""
        messages = [Message.system(_PLAN_SYSTEM_PROMPT), Message.user(goal)]
        try:
            response = self._llm.complete(messages, tools=None, stream=False)
        except Exception:  # noqa: BLE001 — planning is best-effort
            logger.exception("Planning step failed; continuing without a plan")
            return []
        return [line.strip() for line in (response.content or "").splitlines() if line.strip()]
