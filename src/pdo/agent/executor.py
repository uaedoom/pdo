"""Executes the tool calls requested by the model.

Every call is wrapped in exception handling and argument validation: a failing
or unknown tool returns an error string that is fed back to the model, so a
single bad tool call never crashes the agent loop.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

from ..config import get_logs_dir
from ..tools.base import default_confirm
from ..tools.registry import ToolRegistry
from .messages import Message, ToolCall

logger = logging.getLogger(__name__)


class Executor:
    """Runs a single :class:`ToolCall` against the registry.

    ``policy`` maps a tool name to ``"deny"`` (blocked) or ``"ask"`` (requires
    confirmation). Tools not listed are allowed. ``confirm`` is the callback used
    for ``"ask"`` decisions.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        policy: dict[str, str] | None = None,
        confirm: Callable[[str], bool] | None = None,
    ) -> None:
        self._registry = registry
        self._policy = policy or {}
        self._confirm = confirm or default_confirm

    def execute(self, call: ToolCall) -> Message:
        """Execute ``call`` and return a tool-result message for the model."""
        result = self._run(call)
        self._audit(call.name, call.arguments, result)
        return Message.tool(content=result, tool_call_id=call.id, name=call.name)

    def _audit(self, name: str, arguments: str, result: str) -> None:
        """Append a structured record of the tool call to the audit log."""
        try:
            entry = {
                "ts": time.time(),
                "tool": name,
                "args": arguments,
                "result_preview": (result or "")[:200],
            }
            with (get_logs_dir() / "audit.log").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001 — auditing must never break a tool call
            logger.debug("Could not write audit log", exc_info=True)

    def _run(self, call: ToolCall) -> str:
        if not self._registry.has(call.name):
            return f"Error: unknown tool {call.name!r}."

        decision = self._policy.get(call.name, "allow")
        if decision == "deny":
            logger.info("Tool %r blocked by policy", call.name)
            return f"Error: tool {call.name!r} is disabled by the current permission policy."
        if decision == "ask" and not self._confirm(
            f"Allow tool {call.name}({call.arguments})?"
        ):
            return "Cancelled: tool call was not approved by the user."

        try:
            args = json.loads(call.arguments or "{}")
            if not isinstance(args, dict):
                raise ValueError("tool arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Bad arguments for tool %r: %s", call.name, exc)
            return f"Error: could not parse arguments for {call.name}: {exc}"

        try:
            tool = self._registry.get(call.name)
            logger.info("Executing tool %r with args %s", call.name, args)
            return tool.run(**args)
        except Exception as exc:  # noqa: BLE001 — keep the loop alive on any tool error
            logger.exception("Tool %r raised", call.name)
            return f"Error: tool {call.name!r} failed: {exc}"
