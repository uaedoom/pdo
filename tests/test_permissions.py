"""Tests for the per-tool permission policy in the executor."""
from __future__ import annotations

from typing import Any

from pdo.agent.executor import Executor
from pdo.agent.messages import ToolCall
from pdo.tools.base import Tool
from pdo.tools.registry import ToolRegistry


class _EchoTool(Tool):
    name = "echo"
    description = "Echo."
    parameters = {"type": "object", "properties": {}}

    def run(self, **_: Any) -> str:
        return "ran"


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_EchoTool())
    return registry


def _call() -> ToolCall:
    return ToolCall(id="1", name="echo", arguments="{}")


def test_allow_runs_tool():
    msg = Executor(_registry()).execute(_call())
    assert msg.content == "ran"


def test_deny_blocks_tool():
    msg = Executor(_registry(), policy={"echo": "deny"}).execute(_call())
    assert "disabled" in msg.content


def test_ask_declined_cancels():
    executor = Executor(_registry(), policy={"echo": "ask"}, confirm=lambda _p: False)
    assert "not approved" in executor.execute(_call()).content


def test_ask_approved_runs():
    executor = Executor(_registry(), policy={"echo": "ask"}, confirm=lambda _p: True)
    assert executor.execute(_call()).content == "ran"
