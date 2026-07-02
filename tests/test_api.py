"""Tests for the embedding API (pdo.run_agent) with a mocked LLM."""
from __future__ import annotations

import pdo
from pdo.llm import LLMClient, LLMResponse


class FakeLLM(LLMClient):
    def complete(self, messages, tools=None, *, stream=False, on_token=None):
        if on_token:
            on_token("hi from api")
        return LLMResponse(content="hi from api")


def test_run_agent_is_lazily_exported():
    assert callable(pdo.run_agent)


def test_run_agent_with_injected_llm(monkeypatch, tmp_path):
    monkeypatch.setattr("pdo.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("PDO_HOME", str(tmp_path))

    answer = pdo.run_agent("say hi", llm=FakeLLM())

    assert answer == "hi from api"


def test_run_agent_overrides_config(monkeypatch, tmp_path):
    monkeypatch.setattr("pdo.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("PDO_HOME", str(tmp_path))

    captured = {}

    class SpyClient:
        def __init__(self, api_key, model, temperature, base_url):
            captured.update(model=model, base_url=base_url, temperature=temperature)

        def complete(self, messages, tools=None, *, stream=False, on_token=None):
            return LLMResponse(content="ok")

    monkeypatch.setattr("pdo.api.OpenAIClient", SpyClient)
    answer = pdo.run_agent(
        "x", model="my-model", base_url="http://localhost:1234/v1", temperature=0.7
    )

    assert answer == "ok"
    assert captured == {
        "model": "my-model",
        "base_url": "http://localhost:1234/v1",
        "temperature": 0.7,
    }
