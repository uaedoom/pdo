# Build Prompt — PDO for macOS (SwiftUI / Xcode)

Paste everything below the line into your Claude coding agent (e.g. Claude Code or
the Anthropic API) to build a native macOS version of PDO. It re-creates the
Python PDO agent as a polished SwiftUI desktop app.

---

You are a **senior macOS / Swift engineer**. Build a production-quality, native
**macOS desktop application called PDO ("Python Do" → here "Plan. Do.")** — an
AI agent that reasons, plans, and safely executes real tasks on the user's Mac
through a beautiful chat-style GUI (not a terminal). Build it incrementally as a
clean, well-architected Xcode project a developer can open, run, and extend.

**Philosophy:** Think. Plan. Do. PDO is an intelligent agent: understand the
goal → reason → plan → decide if tools are needed → execute tools safely →
review → respond. Never use a tool unless it improves the answer; plain
conversation stays a plain reply.

## Platform & stack (do not deviate)

- **Swift 5.9+ (target Swift 6 concurrency)**, **SwiftUI**, **macOS 14 (Sonoma)+**.
- **Xcode 15/16** project. Use **async/await** and **actors** for concurrency;
  `URLSession` for networking with **streaming via SSE** (`URLSession.bytes`).
- **No third-party dependencies unless necessary.** If Markdown rendering needs
  one, use a small SwiftPM package (e.g. swift-markdown / MarkdownUI) and isolate
  it behind a protocol. Everything else: standard library + system frameworks.
- **Architecture:** Clean Architecture + MVVM + SOLID. Small files, one
  responsibility per type. Split the **core** (engine, no UI) from the **app**
  (SwiftUI). Prefer a local Swift Package `PDOCore` for the engine, with the app
  target depending on it; this keeps the core testable and UI-free.
- Use `Codable` for all data. Use `Sendable`/actors to keep state safe.

## Critical technical decisions (follow these)

1. **Tool calling:** Use the LLM provider's **native function/tool-calling API**.
   Each tool exposes a JSON schema (name, description, parameters). The model
   selects tools; PDO executes them and feeds results back in a ReAct loop until
   done. **Never parse tool calls out of free text.**
2. **LLM abstraction:** Define an `LLMClient` protocol. Ship one implementation,
   `OpenAICompatibleClient`, that targets any OpenAI-compatible Chat Completions
   endpoint. The core depends only on the protocol.
3. **Providers:** Support **OpenAI, Anthropic (via its OpenAI-compatible
   endpoint), OpenRouter, local Ollama, and any custom base URL** — all through
   the single `OpenAICompatibleClient` by changing `baseURL` + API key. Let the
   user switch provider/model at runtime and fetch the live model list from the
   provider's `/models` endpoint.
4. **Secrets:** Store API keys in the **macOS Keychain**, never in plists or
   UserDefaults. Read non-secret config from a settings store.
5. **Streaming:** Stream assistant tokens into the UI live. Show a "thinking"
   state until the first token. Track and display token usage per session.
6. **Concurrency:** The agent loop runs off the main actor; UI updates are
   published to the main actor via `@MainActor` view models / `@Observable`.

## macOS capabilities & sandbox (important)

PDO runs shell commands and reads/writes files, so:

- **Default build: App Sandbox OFF** (a power-user/developer tool). Document this
  clearly. Provide a second, sandboxed configuration that uses
  **security-scoped bookmarks** (`NSOpenPanel` to grant folder access) for users
  who want sandboxing — gate filesystem tools on granted bookmarks in that mode.
- Run shell commands with **`Process`** (`/bin/zsh -lc "<command>"`), capturing
  stdout/stderr with `Pipe`, with a timeout. Stream output where practical.
- Add entitlements as needed (e.g. `com.apple.security.network.client`). If
  sandboxed, also `com.apple.security.files.user-selected.read-write`.
- Spawn MCP servers and Ollama checks via `Process` too.

## Agent workflow & components (mirror the Python design, keep it thin)

- **AgentCore (actor):** coordinates a turn. Runs the ReAct loop: build messages
  → call `LLMClient` (streaming, with tool schemas) → if tool calls, execute via
  `ToolExecutor`, append results, repeat (cap ~8 iterations) → review → return.
- **Router (thin):** the model is the real router via tool-calling; optionally
  flag multi-step tasks for a quick plan.
- **Planner (thin):** optional, for multi-step goals; produces a short step list.
- **ToolExecutor:** runs tool calls, validates JSON args, enforces the permission
  policy, wraps everything in error handling (a tool error never crashes the
  loop), and writes an audit log.
- **Reviewer (thin):** sanity-check the final answer (non-empty, etc.).
- **MemoryStore:** named **sessions** (separate files), durable **facts** &
  **preferences**, and **auto-summarisation** of long histories to bound context.
- **Messages:** `Message` / `ToolCall` models with OpenAI (de)serialisation.

## Tools (protocol-based, auto-registered)

Define a `Tool` protocol: `name`, `description`, JSON `parameters` schema, and
`func run(_ args: JSON) async -> String`. A `ToolRegistry` holds them; the core
never references concrete tools. Ship:

- **Filesystem:** read, write, append, edit-by-exact-match, list, make directory.
  Sandbox writes to a working directory by default; confirm to write outside it
  or overwrite (and, in sandbox mode, require a security-scoped bookmark).
- **Shell:** run command with a **dangerous-command detector** (denylist + regex
  for `rm -rf`, `sudo`, `shutdown`, disk ops, etc.) that requires an explicit
  confirmation dialog.
- **Web:** web_fetch (URL → readable text), web_search (e.g. DuckDuckGo HTML),
  http_request (any REST call).
- **Code/data:** run a code snippet (Process), query SQLite.
- **Search:** glob files, grep file contents.
- **Memory:** save, search, delete facts.
- **Codebase retrieval:** a `codebase_search` tool backed by a local **BM25
  lexical index** of the chosen project folder — chunk source/doc files into
  ~40-line overlapping chunks, tokenize identifiers (split snake_case /
  camelCase / acronyms), rank with BM25, and return top snippets with
  ``path:line`` references. Add a "(Re)build index" action in the UI. Lexical on
  purpose: no embeddings endpoint required, works fully offline.
- **Sub-agents:** a `delegate_task` tool that spawns a **fresh child agent**
  (same tools minus delegation, ephemeral memory, depth-capped at 2) to run a
  self-contained subtask and return only its final answer. Fold the child's
  token usage into the session totals and surface its tool activity in the
  timeline (indented/nested).

**Extensibility (must allow without touching the core):**
- **Plugins:** load extra tools at runtime from an app-support `plugins`
  directory (e.g. bundled scripts, or AppleScript/JXA/Python via Process).
- **Skills:** Markdown prompt templates that become commands (`/review`, etc.).
- **MCP client:** connect Model Context Protocol servers over **stdio**
  (newline-delimited JSON-RPC 2.0): launch each server via `Process`, do the
  `initialize` handshake, `tools/list`, and `tools/call`; register each remote
  tool as `mcp_<server>_<tool>`. Read servers from an `mcp.json`
  (`{ "mcpServers": { name: { command, args, env } } }`). Before sending tool
  args, **strip blank/junk optional arguments** (drop empty strings, strings
  with no alphanumerics like " "/"/", and empty arrays for non-required params) —
  small models pad optional params and break servers like Canva.
- **PDO as an MCP server (stretch goal):** a headless mode (menu-bar toggle or
  `PDO.app/Contents/MacOS/PDO --serve`) that speaks MCP over stdio and exposes
  one `run_task` tool backed by the full agent, so Claude Desktop/Code can drive
  the app. In this mode stdout carries only JSON-RPC and all interactive
  confirmations are auto-denied.

## Safety & control (required)

- Confirmation dialogs for destructive shell commands and risky filesystem ops.
- **Per-tool permission policy:** allow / ask / deny, configurable in Settings
  and applied in `ToolExecutor`.
- Structured **audit log** of every tool call (Application Support / Logs).
- Wrap all tool execution in error handling; log failures; never crash the loop.

## User interface (SwiftUI, polished, macOS-native)

A real Mac app, not a terminal emulator:

- **Main window:** a left **sidebar** listing sessions (new / rename / delete /
  switch), and a main **chat view**.
- **Chat view:** streamed assistant messages rendered as **Markdown** (code
  blocks with syntax styling, copy buttons); user messages; and an inline
  **tool-activity timeline** (e.g. "● Ran shell …" with expandable result, like
  Claude/Codex). A "thinking" indicator before the first token.
- **Composer:** multi-line input (⏎ sends, ⇧⏎ newline), a **slash-command menu**
  (filterable popover) for `/help /models /tools /mcp /theme /sessions /export`
  etc., and **`@file` references** (file picker / drag-and-drop attaches file
  contents). **Images too:** dropping/attaching a png/jpg/gif/webp sends it as a
  base64 ``image_url`` content part so vision-capable models can see it — show a
  thumbnail chip in the composer and in the sent message.
- **Pixel-art PDO logo** on an onboarding/empty state and the about box. Provide
  it both as the classic block-character art and as an `Asset Catalog` image. The
  classic art (reuse this exactly):

  ```
  ████████  ██████    ████████
  ██    ██  ██    ██  ██    ██
  ████████  ██    ██  ██    ██
  ██        ██    ██  ██    ██
  ██        ██████    ████████
  ```

- **Toolbar / status bar:** current model + provider (with a quick **model
  picker** that fetches live models), live **token usage**, and a stop button to
  **cancel** the running turn.
- **Settings window (tabs):** Providers & API keys (Keychain), default model,
  temperature, theme, permission policy, MCP servers (edit `mcp.json` from a UI),
  plugins/skills folders, data location.
- **Themes:** several accent themes; light/dark following the system appearance.
- **Menu bar & shortcuts:** New Session (⌘N), Send, Cancel (⌘.), Settings (⌘,),
  Export conversation (to Markdown), etc.

## Persistence

- Store sessions, summaries, facts, preferences, logs, plugins, skills, and
  `mcp.json` under `~/Library/Application Support/PDO/` (create on first run).
- Use `Codable` + JSON files (or SwiftData if it simplifies the sidebar) — keep
  it simple and inspectable. Keys go to Keychain only.

## Configuration

- First-run onboarding: pick a provider, paste an API key (stored in Keychain),
  choose a model. Friendly error states if a key is missing or a request fails.
- Sensible defaults; never hardcode the model — make it user-selectable.

## Testing & quality

- **XCTest** unit tests for: the tool registry, at least one filesystem tool, the
  dangerous-command detector, the MCP arg-cleaning, the message (de)serialisation,
  and the agent loop with a **mocked `LLMClient`** (no network, no API key).
- Swift concurrency-safe (no data races); pass the Swift 6 strict-concurrency
  checks where feasible.
- Use `os.Logger` for structured logging.

## Project structure (suggested)

```
PDO.xcodeproj (or PDO.xcworkspace)
  PDO/                      # app target (SwiftUI)
    PDOApp.swift
    Views/                 # ChatView, SidebarView, Composer, SettingsView, Onboarding…
    ViewModels/            # ChatViewModel (@MainActor @Observable), SessionsViewModel…
    Resources/             # Assets.xcassets (pixel logo), system prompt
  PDOCore/ (SwiftPM)        # engine, no UI — unit-testable
    Sources/PDOCore/
      Agent/               # AgentCore, Router, Planner, Reviewer, Executor, Memory, Messages
      LLM/                 # LLMClient protocol, OpenAICompatibleClient, streaming/SSE
      Tools/               # Tool protocol, Registry, Filesystem, Shell, Web, Code, Data, Search, Memory
      MCP/                 # MCPClient (stdio JSON-RPC), MCPTool
      Providers/           # provider catalog + model listing
      Config/              # settings, Keychain, paths
    Tests/PDOCoreTests/
  README.md, LICENSE (MIT), CHANGELOG.md
```

## Execution rules for you (the agent)

- Implement **working code — no placeholders, no TODO stubs**. After each module,
  keep the project **building and runnable**.
- Build incrementally in this order: (1) Xcode project + PDOCore package + models
  & `LLMClient` with streaming; (2) a minimal chat UI that talks to a provider;
  (3) tool protocol + registry + filesystem/shell tools + executor + ReAct loop;
  (4) sessions/memory + summarisation; (5) settings + Keychain + model picker;
  (6) web/code/data/search tools; (7) permissions + audit log; (8) plugins +
  skills; (9) MCP client; (10) sub-agents (`delegate_task`) + BM25 codebase
  index/`codebase_search`; (11) image attachments (vision) + themes, slash menu,
  @file, export, polish; (12) the `--serve` MCP-server mode; (13) tests
  throughout.
- Do not rewrite completed modules unnecessarily; preserve compatibility.
- Match macOS Human Interface Guidelines; the app should feel native and refined.
- Provide a short README with build/run steps, the sandbox note, and how to add
  tools / MCP servers.

Deliver a coherent, polished, professional macOS app. Start now with step (1):
scaffold the Xcode project and the `PDOCore` package, define `Message`,
`ToolCall`, `LLMClient`, and a streaming `OpenAICompatibleClient`, plus a
mocked-client unit test — then continue through the list.
