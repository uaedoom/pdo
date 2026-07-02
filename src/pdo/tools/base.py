"""The ``Tool`` base class and shared confirmation helper.

Every tool subclasses :class:`Tool`, declares a JSON parameter schema, and is
executed by the agent through the registry. The agent never imports a concrete
tool, which is what keeps new tools a pure add-on.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from rich.console import Console

logger = logging.getLogger(__name__)

_console = Console()


# Process-wide confirmation override. Non-interactive modes (e.g. `pdo --serve`,
# where stdin/stdout carry JSON-RPC) install a handler here so confirmation can
# never block on, or write to, the protocol streams.
_confirm_override: Any = None


def set_confirm_override(handler) -> None:
    """Replace interactive confirmation globally (None restores the default)."""
    global _confirm_override
    _confirm_override = handler


def default_confirm(prompt: str) -> bool:
    """Ask the user to type ``y`` to approve a sensitive action.

    Returns ``False`` on EOF/Ctrl-C so that "no answer" always means "do not
    proceed". Tools accept this as an injectable dependency so tests can supply
    a deterministic callback instead of blocking on real input.
    """
    if _confirm_override is not None:
        return bool(_confirm_override(prompt))
    _console.print(f"[yellow]{prompt}[/yellow]")
    try:
        answer = _console.input("Type 'y' to confirm: ")
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() == "y"


def truncate(text: str, limit: int = 4000) -> str:
    """Cap tool output so a single result can't overwhelm the model context."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated {len(text) - limit} more characters]"


class ToolError(RuntimeError):
    """Raised by a tool to signal a recoverable failure to the agent."""


class Tool(ABC):
    """Base class for all tools.

    Subclasses set the class attributes ``name``, ``description`` and
    ``parameters`` (a JSON Schema object) and implement :meth:`run`.
    """

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def to_openai_schema(self) -> dict[str, Any]:
        """Return the function/tool schema in the shape the model expects."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    def run(self, **kwargs: Any) -> str:
        """Execute the tool and return a string result for the model.

        Implementations should return a human/model-readable string even on
        failure (e.g. ``"Error: ..."``); raising is acceptable too — the
        executor wraps every call — but returning is preferred for clarity.
        """
