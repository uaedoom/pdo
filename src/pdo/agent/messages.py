"""Message and tool-call data structures.

These dataclasses are the in-memory representation of a conversation. They know
how to serialise themselves into the shape the OpenAI chat API expects, which
keeps that provider-specific detail out of the rest of the agent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A single tool invocation requested by the model.

    ``arguments`` is the raw JSON string exactly as returned by the model; it is
    only parsed at execution time so a malformed payload can be reported as a
    tool error rather than crashing the loop.
    """

    id: str
    name: str
    arguments: str = "{}"

    def to_openai(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


@dataclass
class Message:
    """A single chat message.

    A message may be a plain text turn, an assistant turn that requests tool
    calls, or a tool-result turn. The optional fields capture those variants
    without needing subclasses.
    """

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None  # set on tool-result messages
    name: str | None = None  # tool name, set on tool-result messages

    def to_openai(self) -> dict[str, Any]:
        """Serialise to the dict shape expected by the OpenAI chat API."""
        data: dict[str, Any] = {"role": self.role}

        # An assistant message that only requests tool calls legitimately has
        # ``content == None``; every other role needs a string content field.
        if self.content is not None:
            data["content"] = self.content
        elif self.role != "assistant":
            data["content"] = ""

        if self.tool_calls:
            data["tool_calls"] = [tc.to_openai() for tc in self.tool_calls]
        if self.tool_call_id is not None:
            data["tool_call_id"] = self.tool_call_id
        if self.role == "tool" and self.name:
            data["name"] = self.name
        return data

    # Convenience constructors keep call sites readable. ----------------------
    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role="user", content=content)

    @classmethod
    def assistant(
        cls, content: str | None = None, tool_calls: list[ToolCall] | None = None
    ) -> Message:
        return cls(role="assistant", content=content, tool_calls=tool_calls or [])

    @classmethod
    def tool(cls, content: str, tool_call_id: str, name: str) -> Message:
        return cls(role="tool", content=content, tool_call_id=tool_call_id, name=name)
