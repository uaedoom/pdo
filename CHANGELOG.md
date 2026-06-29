# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-06-29

### Added
- MCP (Model Context Protocol) client: connect stdio MCP servers via
  `<PDO_HOME>/mcp.json`; their tools register automatically as
  `mcp__<server>__<tool>`. New `/mcp` command. Dependency-free, synchronous.
- Named conversation sessions: `/sessions`, `/new`, `/resume` (each stored
  separately); legacy flat history is migrated automatically.
- Automatic summarisation of long conversations to keep context bounded.
- Per-tool permission policy via `PDO_DENY_TOOLS` / `PDO_ASK_TOOLS`
  (block a tool, or require confirmation before it runs).
- `@file` references: mention `@path` in a message to inline a file's contents.
- Skills: drop a `.md` file in `<PDO_HOME>/skills/` to create a reusable slash
  command (e.g. `review.md` → `/review`), with `{{args}}` interpolation.
- Token usage tracking shown live in the input footer.
- Ctrl-C cancels the current turn instead of quitting.
- Structured audit log of every tool call (`<PDO_HOME>/logs/audit.log`).
- Runtime provider/model switching via `/models` (OpenAI, Anthropic, OpenRouter,
  Ollama) with live model listing and a type-to-search / numbered picker.
- Plugin auto-discovery: tools in `<PDO_HOME>/plugins/` or advertised via the
  `pdo.plugins` entry-point group load automatically.
- New tools: `git`, `web_search`, `web_fetch`, `http_request`, `python_exec`,
  `sqlite_query`, `glob_files`, `search_files`, `edit_file`.
- Pixel-art startup splash and a Codex-style bordered input box with slash-command
  autocomplete and a status footer.
- One-shot mode (`pdo "prompt"`), `--json` output, `--version`, `--help`,
  `--theme`, and `--no-markdown` flags.
- Markdown rendering of replies, a "thinking" spinner, color themes (`/theme`,
  `PDO_THEME`), and conversation export (`/export`).
- Graceful fallback when a model doesn't support tool calling.
- `OPENAI_BASE_URL` support for any OpenAI-compatible endpoint.
- Dockerfile.

## [0.1.0] - 2026-06-29

### Added
- Initial release of PDO (Python Do).
- ReAct-style agent loop using the LLM's native function/tool calling.
- `LLMClient` interface with an OpenAI implementation; streaming output.
- Single tool registry with auto-registration via the `@register_tool` decorator.
- Built-in tools:
  - Filesystem: `read_file`, `write_file`, `append_file`, `list_directory`,
    `create_directory` (sandboxed to the working directory by default).
  - Shell: `run_shell` with a configurable dangerous-command detector and typed
    confirmation.
  - Memory: `memory_save`, `memory_search`, `memory_delete`.
- Local JSON memory store for facts, preferences, and conversation history.
- Thin orchestration: planner, router, executor, reviewer.
- Environment-based configuration validated with `pydantic`.
- Rotating file logging.
- Terminal commands: `/help`, `/tools`, `/memory`, `/history`, `/clear`,
  `/version`, `/exit`.
- `pytest` test suite (LLM mocked) and a GitHub Actions CI workflow.
- Packaging via `pyproject.toml` with a `pdo` console-script entry point.

[Unreleased]: https://github.com/uaedoom/pdo/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/uaedoom/pdo/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/uaedoom/pdo/releases/tag/v0.1.0
