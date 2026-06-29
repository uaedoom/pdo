# PDO Architecture

This document explains how PDO is put together and why. The guiding principles
are Clean Architecture and SOLID: the core depends on **interfaces**, details
(the OpenAI client, specific tools) plug into them, and each module has one job.

## The turn lifecycle

```
User goal
   │
   ▼
Router        decide: offer tools? pre-plan? (thin — the model is the real router)
   │
   ▼
Planner       (optional) break a multi-step goal into ordered steps
   │
   ▼
Agent loop ──► LLM.complete(messages, tools)         (ReAct)
   │             │
   │             ├─ returns tool calls ─► Executor.run ─► tool result ─┐
   │             │                                                     │
   │             └─ returns final text ◄──────────── loop until done ◄─┘
   ▼
Reviewer      sanity-check the final answer
   │
   ▼
Memory        persist the turn; reply streamed to the terminal
```

The loop is **ReAct-style**: the model decides, via native tool calling, whether
to use a tool. PDO executes the requested tools, appends their results to the
conversation, and calls the model again until it produces a final answer (capped
by `MAX_TOOL_ITERATIONS`).

## Key boundaries

### `LLMClient` (in `llm.py`)
The only thing the agent knows about language models. `OpenAIClient` is the v1
implementation. Adding Anthropic, a local model, etc. means writing a new class —
the agent never changes. The client is the only place that knows the provider's
message and tool-call wire format.

### `Tool` + `ToolRegistry` (in `tools/`)
A tool declares a `name`, `description`, JSON `parameters` schema, and a `run`
method. Tools auto-register via `@register_tool`. The registry is the single
place the agent looks up tools; the agent never imports a concrete tool. This is
the extension seam for **all** future capabilities (Git, web search, databases,
MCP, …).

### `MemoryStore` (in `agent/memory.py`)
A deliberately simple JSON store (facts, preferences, history). No database, no
embeddings in v1. It is exposed to the model through the memory tools and to the
app through a process-wide singleton, so both see the same data.

## Why the orchestration is thin

Planner, router, executor, and reviewer are intentionally small. The model is
capable of deciding when to use tools, so PDO leans on that rather than building
a heavyweight planning/routing framework. Each component is a clear extension
point: richer planning, smarter routing, or stronger review can grow in place
without disturbing the loop.

## Safety model

- **Dangerous-command detection** (`tools/shell.py`) is a pure function over a
  denylist plus regex patterns, so it is easy to test and extend. Anything it
  flags requires a typed `y` confirmation.
- **Filesystem sandboxing** confines writes to the working directory by default;
  writing outside it or overwriting a file prompts the user.
- **Resilience**: the executor wraps every tool call. A failing or unknown tool
  returns an error string that is fed back to the model; the loop never crashes.

## Configuration & logging

Configuration is read from the environment and validated with `pydantic` at
startup (`config.py`). Logging is sent to a rotating file under the logs
directory and scoped to the `pdo` namespace so it never pollutes stdout, which is
reserved for the interactive session.
