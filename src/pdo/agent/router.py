"""Thin router.

The real routing happens inside the model: it decides — via native tool
calling — whether any tool is needed. So this router always offers the tools and
just adds one cheap heuristic on top: should we spend a planning call before the
main loop? That is reserved for clearly multi-step task requests.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Verbs that typically signal a "do something" request rather than a chat.
_TASK_HINTS = re.compile(
    r"\b(build|create|make|generate|write|implement|set\s?up|install|run|fix|"
    r"refactor|delete|remove|deploy|configure|scaffold|add|migrate|convert)\b",
    re.IGNORECASE,
)


@dataclass
class RouteDecision:
    """The router's verdict for a single turn."""

    expose_tools: bool
    should_plan: bool


class Router:
    """Decides whether tools are offered and whether to pre-plan."""

    def route(self, user_input: str) -> RouteDecision:
        text = user_input.strip()
        # Plan only for substantial, task-shaped requests; trivial one-liners
        # ("list files") don't benefit from a separate planning round-trip.
        should_plan = bool(_TASK_HINTS.search(text)) and len(text.split()) >= 4
        return RouteDecision(expose_tools=True, should_plan=should_plan)
