"""LLM abstraction.

The core agent depends only on the :class:`LLMClient` interface, never on a
concrete provider. ``OpenAIClient`` is the single implementation shipped in v1;
adding another provider (Anthropic, a local model, etc.) means writing a new
class here without touching the agent.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .agent.messages import Message, ToolCall

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when a request to the language model fails."""


def _looks_like_tools_unsupported(exc: Exception) -> bool:
    """Heuristic: does this provider error mean the model can't use tools?

    Covers messages like "<model> does not support tools" returned by Ollama and
    similar OpenAI-compatible endpoints for tool-less models.
    """
    message = str(exc).lower()
    return "tool" in message and ("support" in message or "not supported" in message)


@dataclass
class LLMResponse:
    """A normalised model response: free-text content and/or tool calls."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Token usage for this call, if the provider reported it.
    usage: dict[str, int] | None = None


class LLMClient(ABC):
    """Provider-agnostic chat interface used by the agent."""

    @abstractmethod
    def complete(
        self,
        messages: Sequence[Message],
        tools: list[dict[str, Any]] | None = None,
        *,
        stream: bool = False,
        on_token: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        """Send ``messages`` to the model and return its response.

        Args:
            messages: the conversation so far.
            tools: JSON tool schemas the model may call, or ``None`` to disable
                tool calling for this request.
            stream: when ``True``, emit content tokens via ``on_token`` as they
                arrive (the full response is still returned at the end).
            on_token: callback invoked with each content token while streaming.
        """


class OpenAIClient(LLMClient):
    """OpenAI implementation of :class:`LLMClient` using native tool calling."""

    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        # ``client`` is injectable so tests can pass a fake without importing
        # the SDK or hitting the network. ``base_url`` targets any OpenAI-
        # compatible endpoint (OpenRouter, a local server, …); None = OpenAI.
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url)
        self._client = client
        self._model = model
        self._temperature = temperature
        # Some models (e.g. small local Ollama models) reject tool schemas. Once
        # we learn that, we stop sending tools to avoid repeated failed requests.
        self._supports_tools = True

    def complete(
        self,
        messages: Sequence[Message],
        tools: list[dict[str, Any]] | None = None,
        *,
        stream: bool = False,
        on_token: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [m.to_openai() for m in messages],
            "temperature": self._temperature,
        }
        if tools and self._supports_tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            return self._request(kwargs, stream, on_token)
        except Exception as exc:  # noqa: BLE001 — normalise every provider error
            # Degrade gracefully when the model doesn't support tool calling:
            # drop the tools and retry once as a plain chat request.
            if "tools" in kwargs and _looks_like_tools_unsupported(exc):
                logger.warning("Model %r does not support tools; retrying without them", self._model)
                self._supports_tools = False
                kwargs.pop("tools", None)
                kwargs.pop("tool_choice", None)
                try:
                    return self._request(kwargs, stream, on_token)
                except Exception as retry_exc:  # noqa: BLE001
                    logger.exception("LLM request failed (no-tools retry)")
                    raise LLMError(f"LLM request failed: {retry_exc}") from retry_exc
            logger.exception("LLM request failed")
            raise LLMError(f"LLM request failed: {exc}") from exc

    def _request(
        self, kwargs: dict[str, Any], stream: bool, on_token: Callable[[str], None] | None
    ) -> LLMResponse:
        if stream:
            return self._complete_stream(kwargs, on_token)
        return self._complete_once(kwargs)

    def _complete_once(self, kwargs: dict[str, Any]) -> LLMResponse:
        response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "{}")
            for tc in (message.tool_calls or [])
        ]
        return LLMResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            usage=_usage_to_dict(getattr(response, "usage", None)),
        )

    def _complete_stream(
        self, kwargs: dict[str, Any], on_token: Callable[[str], None] | None
    ) -> LLMResponse:
        # include_usage asks the API to emit a final usage chunk while streaming;
        # some OpenAI-compatible endpoints reject it, so fall back without it.
        try:
            stream = self._client.chat.completions.create(
                **kwargs, stream=True, stream_options={"include_usage": True}
            )
        except TypeError:
            stream = self._client.chat.completions.create(**kwargs, stream=True)

        content_parts: list[str] = []
        # Tool-call deltas arrive in fragments keyed by ``index``; accumulate
        # them until the stream completes.
        tool_acc: dict[int, dict[str, str]] = {}
        usage = None

        for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            text = getattr(delta, "content", None)
            if text:
                content_parts.append(text)
                if on_token:
                    on_token(text)

            for tc in getattr(delta, "tool_calls", None) or []:
                slot = tool_acc.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments

        tool_calls = [
            ToolCall(
                id=slot["id"] or f"call_{index}",
                name=slot["name"],
                arguments=slot["arguments"] or "{}",
            )
            for index, slot in sorted(tool_acc.items())
            if slot["name"]
        ]
        return LLMResponse(
            content="".join(content_parts), tool_calls=tool_calls, usage=_usage_to_dict(usage)
        )


def _usage_to_dict(usage: Any) -> dict[str, int] | None:
    """Normalise a provider usage object into a plain dict, if present."""
    if usage is None:
        return None
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }
