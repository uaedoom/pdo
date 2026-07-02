"""Tests for the delegate_task sub-agent tool (mocked LLM, no network)."""
from __future__ import annotations

from pdo.agent.core import Agent
from pdo.agent.memory import MemoryStore
from pdo.agent.messages import ToolCall
from pdo.config import Config
from pdo.llm import LLMClient, LLMResponse
from pdo.tools.base import Tool
from pdo.tools.registry import ToolRegistry


class FakeLLM(LLMClient):
    """Returns canned responses in order (shared by parent and child agents)."""

    def __init__(self, responses):
        self._responses = list(responses)

    def complete(self, messages, tools=None, *, stream=False, on_token=None):
        response = self._responses.pop(0)
        if on_token and response.content:
            on_token(response.content)
        return response


class EchoTool(Tool):
    name = "echo"
    description = "Echo."
    parameters = {"type": "object", "properties": {}}

    def run(self, **_):
        return "echoed"


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(EchoTool())
    return registry


def _config() -> Config:
    return Config(openai_api_key="test-key")


def test_top_level_agent_registers_delegate_tool(tmp_path):
    registry = _registry()
    Agent(_config(), FakeLLM([]), registry, MemoryStore(tmp_path), planning=False)
    assert registry.has("delegate_task")


def test_delegation_runs_child_and_returns_answer(tmp_path):
    registry = _registry()
    delegate_call = ToolCall(
        id="c1", name="delegate_task", arguments='{"task": "count the files"}'
    )
    llm = FakeLLM(
        [
            # Parent turn 1: asks to delegate.
            LLMResponse(tool_calls=[delegate_call]),
            # Child turn: answers directly.
            LLMResponse(
                content="child result: 3 files",
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            ),
            # Parent turn 2: final answer using the tool result.
            LLMResponse(content="There are 3 files."),
        ]
    )
    agent = Agent(_config(), llm, registry, MemoryStore(tmp_path), planning=False)

    answer = agent.run_turn("how many files are there? delegate it")

    assert answer == "There are 3 files."
    # The child's token usage is folded into the parent's totals.
    assert agent.token_usage()["total_tokens"] == 15
    # The parent's session history contains only the parent turn, not child noise.
    roles = [m["role"] for m in MemoryStore(tmp_path).history()]
    assert roles == ["user", "assistant"]


def test_child_registry_excludes_delegate_tool(tmp_path):
    registry = _registry()
    # Child answers immediately; capture which tools it was offered.
    offered: list[list[str]] = []

    class SpyLLM(LLMClient):
        def complete(self, messages, tools=None, *, stream=False, on_token=None):
            offered.append([t["function"]["name"] for t in (tools or [])])
            return LLMResponse(content="done")

    agent = Agent(_config(), SpyLLM(), registry, MemoryStore(tmp_path), planning=False)
    result = agent.run_subtask("do something")

    assert result == "done"
    assert offered and "delegate_task" not in offered[0]
    assert "echo" in offered[0]


def test_depth_cap_refuses_deep_delegation(tmp_path):
    registry = _registry()
    agent = Agent(
        _config(), FakeLLM([]), registry, MemoryStore(tmp_path), planning=False, depth=2
    )
    assert "maximum delegation depth" in agent.run_subtask("go deeper")


def test_failed_subtask_reports_error_not_crash(tmp_path):
    class BoomLLM(LLMClient):
        def complete(self, messages, tools=None, *, stream=False, on_token=None):
            raise RuntimeError("boom")

    registry = _registry()
    agent = Agent(_config(), BoomLLM(), registry, MemoryStore(tmp_path), planning=False)
    result = agent.run_subtask("anything")
    assert result.startswith("Error: sub-agent failed")
