"""Test that long history is auto-summarised (with a mocked LLM)."""
from __future__ import annotations

from pdo.agent.core import SUMMARIZE_KEEP, Agent
from pdo.agent.memory import MemoryStore
from pdo.config import Config
from pdo.llm import LLMClient, LLMResponse
from pdo.tools.registry import get_registry


class _FakeLLM(LLMClient):
    def __init__(self, responses):
        self._responses = list(responses)

    def complete(self, messages, tools=None, *, stream=False, on_token=None):
        response = self._responses.pop(0)
        if on_token and response.content:
            on_token(response.content)
        return response


def test_long_history_is_summarised(tmp_path):
    store = MemoryStore(tmp_path)
    for i in range(30):  # well over SUMMARIZE_THRESHOLD
        store.add_message("user" if i % 2 == 0 else "assistant", f"message {i}")

    # First complete() call is the summariser; second is the actual turn reply.
    llm = _FakeLLM([LLMResponse(content="CONDENSED SUMMARY"), LLMResponse(content="answer")])
    agent = Agent(Config(openai_api_key="x"), llm, get_registry(), store, planning=False)

    answer = agent.run_turn("new question")

    assert answer == "answer"
    assert store.summary() == "CONDENSED SUMMARY"
    # Recent messages kept verbatim + the just-added user/assistant pair.
    assert len(store.history()) <= SUMMARIZE_KEEP + 2
