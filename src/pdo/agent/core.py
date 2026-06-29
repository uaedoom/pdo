"""The agent core.

``Agent`` coordinates the other components and runs the ReAct-style loop:
call the model with tools → if it requests tools, execute them and feed results
back → repeat until the model returns a final answer. It holds no business logic
of its own; routing, planning, execution and review live in their own modules.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from ..config import Config
from ..llm import LLMClient
from ..tools.registry import ToolRegistry
from .executor import Executor
from .memory import MemoryStore
from .messages import Message
from .planner import Planner
from .reviewer import Reviewer
from .router import Router

logger = logging.getLogger(__name__)

# Hard cap on tool round-trips per turn, to bound cost and avoid infinite loops.
MAX_TOOL_ITERATIONS = 8
# How many past turns of conversation to include as context.
HISTORY_WINDOW = 20
# When the active message list grows beyond this, summarise the overflow…
SUMMARIZE_THRESHOLD = 24
# …keeping this many of the most recent messages verbatim.
SUMMARIZE_KEEP = 10


def _load_system_prompt() -> str:
    path = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Could not read system prompt at %s; using a minimal fallback", path)
        return "You are PDO, a careful and helpful terminal AI agent."


class Agent:
    """Drives a single conversation: plan, call tools, review, respond."""

    def __init__(
        self,
        config: Config,
        llm: LLMClient,
        registry: ToolRegistry,
        memory: MemoryStore,
        *,
        on_token: Callable[[str], None] | None = None,
        on_tool: Callable[[str, dict], None] | None = None,
        on_tool_result: Callable[[str, str], None] | None = None,
        planning: bool = True,
    ) -> None:
        self._config = config
        self._llm = llm
        self._registry = registry
        self._memory = memory
        policy = {
            **{name: "deny" for name in getattr(config, "deny_tools", [])},
            **{name: "ask" for name in getattr(config, "ask_tools", [])},
        }
        self._executor = Executor(registry, policy=policy)
        self._router = Router()
        self._planner = Planner(llm)
        self._reviewer = Reviewer()
        self._on_token = on_token or (lambda _token: None)
        self._on_tool = on_tool or (lambda _name, _args: None)
        self._on_tool_result = on_tool_result or (lambda _name, _result: None)
        self._planning = planning
        self._system_prompt = _load_system_prompt()
        # Running token totals for the session (shown in the UI footer).
        self._usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def token_usage(self) -> dict[str, int]:
        """Return cumulative token usage for the session."""
        return dict(self._usage)

    def set_llm(self, llm: LLMClient) -> None:
        """Swap the active language model (used by the ``/models`` command)."""
        self._llm = llm
        self._planner = Planner(llm)

    def run_turn(self, user_input: str) -> str:
        """Process one user turn and return the final (also streamed) answer."""
        decision = self._router.route(user_input)

        plan: list[str] = []
        if self._planning and decision.should_plan:
            plan = self._planner.plan(user_input)

        self._memory.add_message("user", user_input)
        self._maybe_summarize()
        messages = self._build_messages(plan)
        tools = self._registry.schemas() if decision.expose_tools else None

        final = ""
        for _ in range(MAX_TOOL_ITERATIONS):
            response = self._llm.complete(
                messages, tools=tools, stream=True, on_token=self._on_token
            )
            if response.usage:
                for key in self._usage:
                    self._usage[key] += response.usage.get(key, 0)
            messages.append(
                Message.assistant(content=response.content or None, tool_calls=response.tool_calls)
            )

            if not response.tool_calls:
                final = response.content or ""
                break

            for call in response.tool_calls:
                self._on_tool(call.name, _safe_args(call.arguments))
                tool_message = self._executor.execute(call)
                self._on_tool_result(call.name, tool_message.content or "")
                messages.append(tool_message)
        else:
            final = final or "Reached the tool-iteration limit before finishing the task."

        final = self._reviewer.review(user_input, final)
        self._memory.add_message("assistant", final)
        return final

    def _build_messages(self, plan: list[str]) -> list[Message]:
        """Assemble the message list: system prompt, summary, plan, history."""
        messages = [Message.system(self._system_prompt)]
        summary = self._memory.summary()
        if summary:
            messages.append(Message.system("Summary of earlier conversation:\n" + summary))
        if plan:
            messages.append(Message.system("Suggested plan:\n" + "\n".join(plan)))
        # Only conversational turns are persisted; within-turn tool messages are
        # kept locally in `messages` during the loop, not across turns.
        for entry in self._memory.history(limit=HISTORY_WINDOW):
            if entry["role"] in ("user", "assistant"):
                messages.append(Message(role=entry["role"], content=entry["content"]))
        return messages

    def _maybe_summarize(self) -> None:
        """Compress old turns into the session summary to keep context bounded."""
        messages = self._memory.history()
        if len(messages) <= SUMMARIZE_THRESHOLD:
            return
        older = messages[:-SUMMARIZE_KEEP]
        recent = messages[-SUMMARIZE_KEEP:]
        summary = self._summarize(self._memory.summary(), older)
        if summary:
            self._memory.set_summary(summary)
            self._memory.replace_messages(recent)

    def _summarize(self, previous: str, older: list[dict]) -> str:
        """Produce an updated running summary (best-effort; empty on failure)."""
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in older)
        prompt = (
            f"Existing summary (may be empty):\n{previous or '(none)'}\n\n"
            f"New conversation turns to fold in:\n{convo}\n\n"
            "Write an updated summary."
        )
        try:
            response = self._llm.complete(
                [
                    Message.system(
                        "You compress a conversation into a concise summary that "
                        "preserves key facts, decisions, file paths and the user's "
                        "goals. Reply with only the summary."
                    ),
                    Message.user(prompt),
                ],
                tools=None,
                stream=False,
            )
        except Exception:  # noqa: BLE001 — summarisation is best-effort
            logger.exception("Summarisation failed; keeping full history")
            return ""
        return (response.content or "").strip()


def _safe_args(raw: str) -> dict:
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}
