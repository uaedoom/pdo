"""Tests for the agent loop, using a mocked LLM (no API key, no network)."""
from __future__ import annotations

from pdo.agent.core import Agent
from pdo.agent.memory import MemoryStore
from pdo.agent.messages import ToolCall
from pdo.config import Config
from pdo.llm import LLMClient, LLMResponse
from pdo.tools.registry import get_registry


class FakeLLM(LLMClient):
    """Returns canned responses in order; records the messages it received."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def complete(self, messages, tools=None, *, stream=False, on_token=None):
        self.calls.append(list(messages))
        response = self._responses.pop(0)
        if on_token and response.content:
            on_token(response.content)
        return response


def _config():
    return Config(openai_api_key="test-key")


def test_plain_conversation_returns_text(tmp_path):
    store = MemoryStore(tmp_path)
    llm = FakeLLM([LLMResponse(content="Hello there!")])
    agent = Agent(_config(), llm, get_registry(), store, planning=False)

    answer = agent.run_turn("hi")

    assert answer == "Hello there!"
    assert store.history()[-1]["content"] == "Hello there!"
    assert store.history()[-2]["content"] == "hi"


def test_tool_call_loop_executes_tool_and_continues(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data.txt").write_text("the answer is 42")

    store = MemoryStore(tmp_path / "mem")
    tool_call = ToolCall(id="call_1", name="read_file", arguments='{"path": "data.txt"}')
    llm = FakeLLM(
        [
            LLMResponse(tool_calls=[tool_call]),
            LLMResponse(content="The file says: the answer is 42."),
        ]
    )
    agent = Agent(_config(), llm, get_registry(), store, planning=False)

    answer = agent.run_turn("what's in data.txt?")

    assert "42" in answer
    # Two round-trips: one that asked for the tool, one that produced the answer.
    assert len(llm.calls) == 2
    # The second call must include the tool result the executor fed back.
    tool_messages = [m for m in llm.calls[1] if m.role == "tool"]
    assert tool_messages and "the answer is 42" in tool_messages[0].content


def test_empty_answer_is_replaced_by_reviewer(tmp_path):
    store = MemoryStore(tmp_path)
    llm = FakeLLM([LLMResponse(content="")])
    agent = Agent(_config(), llm, get_registry(), store, planning=False)

    answer = agent.run_turn("...")
    assert answer  # reviewer substitutes a non-empty fallback
