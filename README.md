<h1 align="center">PDO — Python Do</h1>

<div align="center">
<pre>
████████  ██████    ████████
██    ██  ██    ██  ██    ██
████████  ██    ██  ██    ██
██        ██    ██  ██    ██
██        ██████    ████████
</pre>
</div>

<p align="center"><b>Think. Plan. Do.</b><br/><sub>The same pixel-art logo greets you on every launch.</sub></p>

<p align="center">
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg">
  <img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-blue.svg">
  <img alt="Open Source" src="https://img.shields.io/badge/Open%20Source-%E2%9D%A4-red.svg">
</p>

> **PDO is free and open source** (MIT licensed). Contributions are welcome —
> see [CONTRIBUTING.md](CONTRIBUTING.md). Star the repo if you find it useful! ⭐

PDO is a terminal-first AI agent that completes real tasks — it doesn't just
answer questions. Give it a goal and it reasons about it, plans the steps,
decides whether tools are needed, executes them **safely**, reviews the result,
and replies clearly. When a plain answer is enough, it just answers; it never
reaches for a tool it doesn't need.

```
you ▸ list all markdown files in this repo and summarise the README
🔧 run_shell(command='find . -name "*.md"')
🔧 read_file(path='README.md')
PDO Here are the Markdown files… and a three-line summary of the README…
```

---

## Features

- **ReAct-style agent loop** built on the LLM's **native function/tool calling** —
  the model picks tools and arguments; PDO executes them and feeds results back
  until the task is done. Tool calls are never parsed out of free text.
- **Many providers** — OpenAI, Anthropic, OpenRouter, local **Ollama**, or any
  OpenAI-compatible endpoint. Switch provider and model at runtime with `/models`
  (live model listing). The core depends only on an `LLMClient` interface.
- **18 built-in tools** — filesystem (read / write / append / **edit** / list /
  mkdir), shell (dangerous-command guard), code search (**glob** / **grep**),
  **git**, **web search & fetch**, **HTTP**, **Python exec**, **SQLite**, and
  long-term memory (save / search / delete).
- **Extensible** three ways without touching the core:
  - **Plugins** — drop a `Tool` subclass in `<PDO_HOME>/plugins/` (or ship one via
    the `pdo.plugins` entry-point group).
  - **Skills** — Markdown prompt recipes become slash commands (`/review`, …).
  - **MCP** — connect any Model Context Protocol server; its tools appear as
    `mcp__<server>__<tool>`.
- **Conversation management** — named **sessions** (`/new`, `/resume`), automatic
  **summarisation** of long history, `@file` references (text **and images** for
  vision models), and `/export`.
- **Sub-agents** — a `delegate_task` tool spawns a fresh child agent for
  self-contained subtasks, keeping the main context small on big jobs.
- **Codebase search** — `/index` builds a local BM25 index of your project; the
  agent then uses `codebase_search` to find relevant code with `path:line` refs
  (no embeddings API needed — works fully offline).
- **Safety & control** — typed confirmation for destructive commands, working-dir
  write sandbox, per-tool **permission policies**, and a structured **audit log**.
- **Polished terminal UX** — pixel-art splash, a bordered input box with slash
  autocomplete, Markdown rendering, a thinking spinner, color **themes**, and a
  live token-usage footer.
- **Scriptable** — one-shot mode (`pdo "prompt"`), `--json` output, and a Docker
  image.
- **Tested & CI-ready** — a `pytest` suite that mocks the LLM (no API key needed)
  and a GitHub Actions workflow.

---

## Installation

> [!IMPORTANT]
> **PDO requires Python 3.12+.** Create the virtual environment with a 3.12
> interpreter explicitly — don't rely on the system `python3` (macOS ships 3.9,
> which will not work).

```bash
# 1. Clone
git clone https://github.com/uaedoom/pdo.git
cd pdo

# 2. Create a virtual environment WITH Python 3.12+
python3.12 -m venv .venv          # macOS (Homebrew): brew install python@3.12
source .venv/bin/activate         # Windows: .venv\Scripts\activate

# 3. Upgrade pip, then install (editable, with dev extras)
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

This installs the `pdo` console command. Verify with `python --version`
(should be 3.12.x) and `pdo --version`.

### Notes for users / troubleshooting

- **`ERROR: ... Directory cannot be installed in editable mode` / "requires a
  setuptools-based build"** — your virtual environment is on an old Python (and
  old pip). Recreate it with Python 3.12 and upgrade pip:
  ```bash
  deactivate; rm -rf .venv
  python3.12 -m venv .venv && source .venv/bin/activate
  python -m pip install --upgrade pip
  pip install -e ".[dev]"
  ```
- **No `python3.12`?** Install it first: macOS `brew install python@3.12`,
  Ubuntu `sudo apt install python3.12 python3.12-venv`.
- **Not yet on PyPI** — install by cloning as above (`pip install pdo` isn't
  available yet).
- **Tested on macOS and Linux.** Windows should work but is less tested.
- Runtime data (memory, sessions, logs) lives in `~/.pdo` if you set
  `PDO_HOME=~/.pdo`; otherwise it defaults to the package directory.

---

## Quick Start

```bash
# Set your API key (or copy .env.example to .env and fill it in)
export OPENAI_API_KEY=sk-...

# Optionally choose a model (gpt-4.1-mini is the default)
export OPENAI_MODEL=gpt-4.1-mini

# Run it interactively
pdo

# …or one-shot (great for scripts / pipes)
pdo "list all markdown files and summarise the README"
pdo --json "what is 2+2"          # machine-readable output
pdo --version
```

Interactive mode gives you a prompt; type a goal, or a slash command (`/help`).
Replies render as Markdown, with a thinking spinner and a Codex-style activity
log. Switch colors live with `/theme green` (or set `PDO_THEME`).

### Configuration

All configuration is read from the environment (a `.env` file is auto-loaded):

| Variable          | Default          | Description                                   |
| ----------------- | ---------------- | --------------------------------------------- |
| `OPENAI_API_KEY`  | *(required)*     | Your API key (OpenAI **or** OpenRouter, etc.). |
| `OPENAI_MODEL`    | `gpt-4.1-mini`   | Model to use.                                 |
| `OPENAI_BASE_URL` | *(OpenAI)*       | API endpoint. Set to use an OpenAI-compatible provider. |
| `TEMPERATURE`     | `0.2`            | Sampling temperature (0–2).                   |
| `PDO_HOME`        | package dir      | Where memory and logs are stored (e.g. `~/.pdo`). |

PDO fails fast with a friendly message if `OPENAI_API_KEY` is missing.

### Using OpenRouter (or other OpenAI-compatible APIs)

PDO talks to any OpenAI-compatible endpoint — just point `OPENAI_BASE_URL` at it
and use that provider's key and model names. For [OpenRouter](https://openrouter.ai):

```bash
export OPENAI_API_KEY=sk-or-...                     # your OpenRouter key
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
export OPENAI_MODEL=openai/gpt-4.1-mini             # any OpenRouter model id
pdo
```

The same pattern works for local servers (e.g. Ollama/LM Studio at
`http://localhost:11434/v1`). The model must support **tool/function calling**
for PDO's agent loop to use tools.

---

## Example Usage

```text
you ▸ build a minimal Flask API in ./hello-api
you ▸ explain this repository
you ▸ fix this Python error: <paste traceback>
you ▸ list all markdown files
you ▸ create a README for this project
```

### Terminal commands

| Command     | What it does                          |
| ----------- | ------------------------------------- |
| `/help`     | Show available commands               |
| `/models`   | Switch provider & model (OpenAI / Anthropic / OpenRouter / Ollama) |
| `/tools`    | List registered tools                 |
| `/mcp`      | Show connected MCP servers and their tools |
| `/theme`    | Change the color theme (e.g. `/theme green`) |
| `/export`   | Save the conversation to a Markdown file |
| `/sessions` | List saved conversation sessions      |
| `/new`      | Start a new session (e.g. `/new feature-x`) |
| `/resume`   | Switch to another session (e.g. `/resume default`) |
| `/memory`   | Show saved facts and preferences      |
| `/history`  | Show recent conversation history      |
| `/clear`    | Clear the current session's history   |
| `/version`  | Show the PDO version                  |
| `/exit`     | Quit                                  |

### Switching models at runtime

Type `/models` to pick a provider (OpenAI, Anthropic, or OpenRouter) and a model
interactively — the change applies immediately for the rest of the session. If a
key for the chosen provider isn't in your environment, PDO prompts for one and
keeps it in memory for the session only (never written to disk). Set
`ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` in your `.env` to skip the prompt.

---

## Project Structure

```
pdo/
├─ pyproject.toml          # Packaging + console script (pdo = pdo.main:main)
├─ requirements.txt        # Convenience mirror of runtime deps
├─ .env.example            # Sample configuration
├─ .github/workflows/ci.yml
├─ src/pdo/
│  ├─ main.py              # Terminal entry point + REPL + slash commands
│  ├─ config.py            # Env-based config, validated with pydantic
│  ├─ llm.py               # LLMClient interface + OpenAI implementation
│  ├─ logging_setup.py     # Rotating file logging for the `pdo` namespace
│  ├─ agent/
│  │  ├─ core.py           # Coordinates components; runs the ReAct loop
│  │  ├─ planner.py        # Breaks a goal into steps (thin, advisory)
│  │  ├─ router.py         # Plain chat vs. tool use (thin; model decides)
│  │  ├─ executor.py       # Runs approved tool calls, safely
│  │  ├─ reviewer.py       # Sanity-checks the final answer
│  │  ├─ memory.py         # Local JSON memory store
│  │  └─ messages.py       # Message/ToolCall dataclasses
│  ├─ tools/
│  │  ├─ base.py           # Tool base class + confirmation helper
│  │  ├─ registry.py       # The single tool registry + auto-registration
│  │  ├─ filesystem.py     # read / write / append / list / mkdir
│  │  ├─ shell.py          # run command + dangerous-command detector
│  │  └─ memory.py         # save / search / delete memory tools
│  ├─ prompts/system.md    # The system prompt
│  ├─ data/                # Runtime JSON state (memory.json, history.json)
│  └─ logs/                # Rotating logs (pdo.log)
├─ tests/                  # pytest suite (LLM is mocked)
└─ docs/                   # Architecture notes
```

> **Where is my data?** By default PDO stores `memory.json`, `history.json` and
> logs inside the installed package directory so a fresh clone works immediately.
> Set `PDO_HOME=~/.pdo` to keep that state in your home directory instead.

---

## Adding New Tools

A tool is a small class. Subclass `Tool`, declare a JSON parameter schema, and
decorate it with `@register_tool` — that's it. The agent picks it up
automatically; you never touch the core.

```python
# src/pdo/tools/clock.py
from datetime import datetime
from typing import Any

from .base import Tool
from .registry import register_tool


@register_tool
class CurrentTimeTool(Tool):
    name = "current_time"
    description = "Return the current local date and time."
    parameters = {"type": "object", "properties": {}}

    def run(self, **_: Any) -> str:
        return datetime.now().isoformat(timespec="seconds")
```

For a built-in tool, add the module to the lazy import in
`tools/registry.py:get_registry`. For tools that perform sensitive actions,
accept an injectable `confirm` callback (see `tools/filesystem.py`) so they can
be tested deterministically and prompt the user when needed.

### Plugins (no fork required)

You don't have to edit PDO to add a tool. PDO **auto-discovers plugins** on
startup from two places:

1. **A plugins directory** — drop a `.py` file defining a `Tool` subclass into
   your plugins folder (run `/tools` to see its path; default
   `<PDO_HOME>/plugins`). The `@register_tool` decorator is optional there — PDO
   finds `Tool` subclasses automatically. A ready-made example lives in
   [`examples/plugins/current_time_tool.py`](examples/plugins/current_time_tool.py):

   ```bash
   mkdir -p ~/.pdo/plugins        # if you run with PDO_HOME=~/.pdo
   cp examples/plugins/current_time_tool.py ~/.pdo/plugins/
   pdo                            # the `current_time` tool is now available
   ```

2. **Installed packages** — a third-party package can advertise tools via the
   `pdo.plugins` entry-point group. Each entry point may resolve to a `Tool`
   subclass or a `register(registry)` callable:

   ```toml
   # in the plugin package's pyproject.toml
   [project.entry-points."pdo.plugins"]
   my_tool = "my_package.tools:MyTool"
   ```

A broken plugin is logged and skipped — it never crashes PDO.

### Skills (reusable prompt commands)

Drop a Markdown file in your skills directory (`<PDO_HOME>/skills/`) and it
becomes a slash command named after the file. An optional first line
`description: …` (or `# Title`) sets the menu text, and `{{args}}` interpolates
whatever you type after the command. Example
[`examples/skills/review.md`](examples/skills/review.md) becomes `/review`:

```bash
mkdir -p ~/.pdo/skills
cp examples/skills/review.md ~/.pdo/skills/
pdo            # now type:  /review the auth module
```

### Referencing files with `@`

In any message, mention a file with `@path` and PDO inlines its contents for the
model — e.g. `explain @src/pdo/main.py` or `fix the bug in @app.py`.

**Images too:** `@screenshot.png` (png/jpg/gif/webp) attaches the image itself,
so vision-capable models can see it — e.g. `what's wrong in this UI? @shot.png`.

### Multi-line input

Press **Enter** to send. Press **Option/Alt+Enter** (⌥⏎) to insert a newline and
compose a multi-line message before sending.

### MCP servers (Model Context Protocol)

PDO is an MCP client: connect any MCP server and its tools become available to
the agent automatically (named `mcp__<server>__<tool>`). Declare servers in
`<PDO_HOME>/mcp.json` using the standard format (see
[`examples/mcp.json`](examples/mcp.json)):

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    }
  }
}
```

Servers start on launch (over the stdio transport); run `/mcp` to see what's
connected. A server that fails to start is reported and skipped — it never
crashes PDO. No extra Python dependencies are required.

---

## Roadmap

**v1 (this release) — done**
- Native tool-calling agent loop; multi-provider (OpenAI / Anthropic / OpenRouter
  / Ollama); 18 built-in tools; plugins, skills, and MCP client; named sessions +
  auto-summary; permission policies + audit log; themed TUI with one-shot/JSON
  modes; tests + CI; Docker.

**Next**
- Multi-line input and image/vision input.
- Sub-agents (delegate subtasks) and retrieval (RAG over large codebases).
- A JSON-RPC / SDK mode so other apps can embed PDO.

Each of these arrives as a new `Tool` (or `LLMClient`) — by design, none require
changes to the core.

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for setup,
coding standards, and how to add tools. Please run `ruff check .` and `pytest`
before opening a pull request.

---

## License

[MIT](LICENSE) © PDO Contributors
