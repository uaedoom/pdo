"""Terminal entry point.

Wires the configuration, LLM client, tool registry, memory and agent together,
then runs an interactive REPL. ``main`` is registered as the ``pdo`` console
script in ``pyproject.toml``.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import time
from pathlib import Path

from rich.align import Align
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .agent.core import Agent
from .agent.memory import MemoryStore, get_memory_store
from .banner import render_logo
from .config import (
    Config,
    ConfigError,
    get_mcp_config_path,
    get_plugins_dir,
    get_skills_dir,
    load_config,
)
from .llm import LLMError, OpenAIClient
from .logging_setup import configure_logging
from .mcp import active_servers, load_mcp_config, start_servers
from .providers import PROVIDERS, Provider
from .skills import Skill, load_skills
from .theme import accent, accent_ansi, current_theme, set_theme, theme_names
from .tools.base import truncate
from .tools.registry import ToolRegistry, get_registry, plugin_tool_names

# Pattern for @file references in user input, e.g. "explain @src/pdo/main.py".
_FILE_REF = re.compile(r"@([^\s]+)")

# API keys entered interactively via /models, kept in memory for the session
# only (never written to disk).
_SESSION_KEYS: dict[str, str] = {}

# prompt_toolkit powers the interactive prompt (slash-command autocomplete). It
# is optional at import time so the module still loads if it is unavailable; the
# REPL falls back to a plain prompt in that case.
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.shortcuts import CompleteStyle
    from prompt_toolkit.styles import Style

    _HAVE_PTK = True

    class _SlashCompleter(Completer):
        """Suggest slash commands, but only while the line is a ``/`` command.

        Plain text (anything not starting with ``/``, or once a space is typed)
        yields no completions, so the menu never pops up for normal messages.
        """

        def __init__(self, commands: dict[str, str]) -> None:
            self._commands = commands

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if not text.startswith("/") or " " in text:
                return
            for name, desc in self._commands.items():
                if name.startswith(text.lower()):
                    yield Completion(name, start_position=-len(text), display_meta=desc)

except ImportError:  # pragma: no cover - exercised only without the optional dep
    _HAVE_PTK = False

# Friendly past-tense verbs for the tool-activity log (Codex/Claude-Code style).
_TOOL_VERBS: dict[str, str] = {
    "run_shell": "Ran",
    "read_file": "Read",
    "write_file": "Wrote",
    "append_file": "Updated",
    "list_directory": "Explored",
    "create_directory": "Created",
    "memory_save": "Saved",
    "memory_search": "Searched",
    "memory_delete": "Deleted",
}

console = Console()
logger = logging.getLogger("pdo.main")

# Single source of truth for the slash commands: name -> description. Used for
# both the autocomplete menu and the /help panel so they never drift apart.
_COMMANDS: dict[str, str] = {
    "/help": "Show this help",
    "/models": "Switch provider and model (OpenAI / Anthropic / OpenRouter / Ollama)",
    "/tools": "List available tools",
    "/mcp": "Show connected MCP servers and their tools",
    "/theme": "Change the color theme (e.g. /theme green)",
    "/export": "Save the conversation to a Markdown file",
    "/sessions": "List saved conversation sessions",
    "/new": "Start a new conversation session (e.g. /new feature-x)",
    "/resume": "Switch to another session (e.g. /resume default)",
    "/memory": "Show saved facts and preferences",
    "/history": "Show recent conversation history",
    "/clear": "Clear the current session's history",
    "/version": "Show the PDO version",
    "/exit": "Quit PDO",
}

def _help_text(commands: dict[str, str]) -> str:
    rows = "\n".join(
        f"  [{accent()}]{name}[/{accent()}]   {desc}" for name, desc in commands.items()
    )
    return (
        "[bold]Commands[/bold]\n"
        + rows
        + "\n\nType [bold]/[/bold] to see this menu inline. Reference files with "
        "[bold]@path[/bold]. Anything else is sent to the agent."
    )


# Theme for the prompt_toolkit input: subtle footer + a tidy completion menu.
_PTK_STYLE = {
    "bottom-toolbar": "fg:#9aa0a6 bg:#1b1b1b",
    "completion-menu.completion": "bg:#23252b fg:#c8ccd4",
    "completion-menu.completion.current": "bg:#3a3d44 fg:#ffffff bold",
    "completion-menu.meta.completion": "bg:#23252b fg:#7f868f",
    "completion-menu.meta.completion.current": "bg:#3a3d44 fg:#c8ccd4",
}


def _short_cwd() -> str:
    """Return the current directory with $HOME collapsed to ``~`` (like a shell)."""
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    if cwd == home:
        return "~"
    if cwd.startswith(home + os.sep):
        return "~" + cwd[len(home):]
    return cwd


def _make_prompt_session(config: Config, agent: Agent, commands: dict[str, str]):
    """Build the boxed input session with slash autocomplete and a status footer.

    Returns ``None`` when prompt_toolkit is unavailable or output isn't a TTY,
    signalling the REPL to use a plain prompt instead.
    """
    if not _HAVE_PTK or not sys.stdout.isatty():
        return None

    completer = _SlashCompleter(commands)

    def bottom_toolbar():
        # Read live each time so /models and token counts update immediately.
        total = agent.token_usage().get("total_tokens", 0)
        tokens = f"  ·  {total:,} tok" if total else ""
        return HTML(
            f"  pdo  ·  <b>{config.openai_model}</b>  ·  {_short_cwd()}{tokens}"
            "  ·  ⌥⏎ newline  "
        )

    # Enter submits; Alt/Option+Enter (ESC then Enter) inserts a newline so
    # multi-line prompts can be composed without sending.
    bindings = KeyBindings()

    @bindings.add("escape", "enter")
    def _insert_newline(event):
        event.current_buffer.insert_text("\n")

    # complete_while_typing makes the dropdown appear immediately on "/".
    # Single-column menu (one command per line) with the descriptions; reserve
    # extra rows so the list isn't clipped — scroll the rest with the arrow keys.
    return PromptSession(
        completer=completer,
        complete_while_typing=True,
        complete_style=CompleteStyle.COLUMN,
        reserve_space_for_menu=14,
        bottom_toolbar=bottom_toolbar,
        key_bindings=bindings,
        style=Style.from_dict(_PTK_STYLE),
    )


def _read_input(session) -> str:
    """Read one line of input inside a bordered box, or plain as a fallback."""
    if session is None:
        return console.input("[bold blue]you ▸[/bold blue] ").strip()

    width = shutil.get_terminal_size((80, 24)).columns
    inner = max(width - 2, 8)
    # Top/bottom borders are printed around the live prompt line; the right edge
    # of the box is the right-aligned prompt (rprompt), which stays put as you type.
    console.print(f"[grey42]╭{'─' * inner}╮[/grey42]")
    try:
        text = session.prompt(
            HTML(
                f"<ansibrightblack>│</ansibrightblack> "
                f"<{accent_ansi()}><b>› </b></{accent_ansi()}>"
            ),
            rprompt=HTML("<ansibrightblack>│</ansibrightblack>"),
            # Continuation rows (after Alt+Enter) keep the box's left border.
            prompt_continuation=HTML("<ansibrightblack>│</ansibrightblack>   "),
        )
    finally:
        console.print(f"[grey42]╰{'─' * inner}╯[/grey42]")
    return text.strip()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pdo",
        description="PDO (Python Do) — a terminal-first AI agent. Think. Plan. Do.",
    )
    parser.add_argument("prompt", nargs="*", help="Run a single prompt and exit (one-shot mode).")
    parser.add_argument("--version", action="store_true", help="Print the version and exit.")
    parser.add_argument("--json", action="store_true", help="One-shot: print the reply as JSON.")
    parser.add_argument("--no-markdown", action="store_true", help="Disable Markdown rendering.")
    parser.add_argument("--theme", metavar="NAME", help=f"Color theme: {', '.join(theme_names())}.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run PDO. Returns a process exit code. Supports one-shot and interactive modes."""
    args = _parse_args(argv)
    if args.version:
        print(f"PDO {__version__}")
        return 0

    try:
        config = load_config()
    except ConfigError as exc:
        console.print(Panel(str(exc), title="Configuration error", border_style="red"))
        return 1

    # CLI flags override environment config.
    if args.no_markdown:
        config.render_markdown = False
    if args.theme:
        config.theme = args.theme
    set_theme(config.theme)

    configure_logging()
    registry = get_registry()
    store = get_memory_store()

    try:
        llm = OpenAIClient(
            api_key=config.openai_api_key,
            model=config.openai_model,
            temperature=config.temperature,
            base_url=config.openai_base_url,
        )
    except Exception as exc:  # noqa: BLE001 — show a friendly message, don't traceback
        console.print(f"[red]Failed to initialise the LLM client:[/red] {exc}")
        return 1

    mcp_servers = _init_mcp(registry, quiet=args.prompt and args.json)
    try:
        # One-shot mode: run a single prompt and exit (great for scripts/pipes).
        if args.prompt:
            return _run_once(config, llm, registry, store, " ".join(args.prompt), args.json)

        agent = _build_agent(config, llm, registry, store)
        skills = load_skills(get_skills_dir())
        _show_splash(config)
        return _repl(agent, registry, store, config, skills)
    finally:
        for server in mcp_servers:
            server.stop()


def _init_mcp(registry: ToolRegistry, quiet: bool = False):
    """Start MCP servers from mcp.json and register their tools (best-effort)."""
    try:
        servers_config = load_mcp_config(get_mcp_config_path())
    except Exception:  # noqa: BLE001
        logger.exception("Could not load MCP config")
        return []
    if not servers_config:
        return []

    servers, summary = start_servers(registry, servers_config)
    if not quiet:
        for name, count, error in summary:
            if error:
                console.print(f"[yellow]MCP {name}: {error}[/yellow]")
            else:
                console.print(f"[dim]MCP {name}: connected ({count} tool(s))[/dim]")
    return servers


def _run_once(
    config: Config,
    llm: OpenAIClient,
    registry: ToolRegistry,
    store: MemoryStore,
    prompt: str,
    as_json: bool,
) -> int:
    """Run a single prompt non-interactively and print the result."""
    agent = _build_agent(config, llm, registry, store, quiet=True)
    try:
        expanded, images = _expand_file_refs(prompt)
        answer = agent.run_turn(expanded, images=images)
    except Exception as exc:  # noqa: BLE001
        if as_json:
            print(json.dumps({"error": str(exc)}))
        else:
            console.print(f"[red]Error:[/red] {exc}")
        return 1

    if as_json:
        print(json.dumps({"model": config.openai_model, "response": answer}))
    elif config.render_markdown:
        console.print(Markdown(answer))
    else:
        print(answer)
    return 0


def _build_agent(
    config: Config,
    llm: OpenAIClient,
    registry: ToolRegistry,
    store: MemoryStore,
    *,
    quiet: bool = False,
) -> Agent:
    """Create an agent whose streaming output is rendered to the terminal.

    ``quiet`` suppresses all live output (used by one-shot mode). When Markdown
    rendering is on, tokens aren't streamed — the final reply is rendered as
    Markdown by the caller instead.
    """
    state = {"label_shown": False}
    stream_tokens = not quiet and not config.render_markdown

    def on_token(token: str) -> None:
        if not stream_tokens:
            return
        if not state["label_shown"]:
            console.print(f"[bold {accent()}]●[/bold {accent()}] ", end="")
            state["label_shown"] = True
        console.print(token, end="", markup=False, highlight=False, soft_wrap=True)

    def on_tool(name: str, args: dict) -> None:
        if quiet:
            return
        verb = _TOOL_VERBS.get(name, "Used")
        console.print(
            f"\n[{accent()}]●[/{accent()}] [bold]{verb}[/bold] "
            f"[white]{name}[/white]([dim]{escape(_format_args(args))}[/dim])"
        )
        state["label_shown"] = False

    def on_tool_result(name: str, result: str) -> None:
        if quiet:
            return
        lines = (result or "").strip().splitlines()
        snippet = lines[0] if lines else "(no output)"
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        more = f"  [dim](+{len(lines) - 1} more lines)[/dim]" if len(lines) > 1 else ""
        console.print(f"  [grey42]└[/grey42] [dim]{escape(snippet)}[/dim]{more}")

    return _AgentWithReset(
        config, llm, registry, store, on_token, on_tool, on_tool_result, state
    )


class _AgentWithReset(Agent):
    """Agent wrapper that resets the streaming label state before each turn."""

    def __init__(
        self, config, llm, registry, store, on_token, on_tool, on_tool_result, state
    ) -> None:
        super().__init__(
            config,
            llm,
            registry,
            store,
            on_token=on_token,
            on_tool=on_tool,
            on_tool_result=on_tool_result,
        )
        self._state = state

    def run_turn(self, user_input: str, images: list[str] | None = None) -> str:
        self._state["label_shown"] = False
        return super().run_turn(user_input, images=images)


def _show_splash(config: Config) -> None:
    """Clear the screen and show the pixel-art PDO logo, then start."""
    endpoint = config.openai_base_url or "OpenAI (default)"
    interactive = sys.stdout.isatty()

    if interactive:
        console.clear()
    console.print()
    console.print(Align.center(Text(render_logo(), style=f"bold {accent()}")))
    console.print(Align.center(Text("Think. Plan. Do.", style="dim")))
    console.print()
    console.print(
        Align.center(
            Text(
                f"v{__version__}    model: {config.openai_model}    endpoint: {endpoint}",
                style=accent(),
            )
        )
    )
    console.print()
    # A brief pause so the splash registers as a screen, not a flicker. Skipped
    # for non-interactive runs so scripts/pipes aren't slowed down.
    if interactive:
        time.sleep(1.2)
    console.print(
        "[dim]Type [bold]/[/bold] for commands, [bold]/exit[/bold] to quit.[/dim]\n"
    )


def _repl(
    agent: Agent,
    registry: ToolRegistry,
    store: MemoryStore,
    config: Config,
    skills: dict[str, Skill],
) -> int:
    # Built-in commands plus one slash command per loaded skill.
    commands = {**_COMMANDS, **{f"/{s.name}": s.description for s in skills.values()}}
    session = _make_prompt_session(config, agent, commands)
    while True:
        try:
            user_input = _read_input(session)
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye!")
            return 0

        if not user_input:
            continue

        if user_input.startswith("/"):
            if _handle_command(user_input, registry, store, agent, config, skills, commands):
                return 0
            continue

        expanded, images = _expand_file_refs(user_input)
        _run_turn_interactive(agent, config, expanded, images)


# File extensions treated as image attachments (sent to vision models).
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _expand_file_refs(text: str) -> tuple[str, list[str]]:
    """Resolve ``@path`` references: inline text files, collect image paths.

    Returns the (possibly expanded) message text and a list of image file paths
    to attach to the turn for vision-capable models.
    """
    attachments: list[tuple[str, str]] = []
    images: list[str] = []
    for match in _FILE_REF.finditer(text):
        path = Path(match.group(1)).expanduser()
        if not path.is_file():
            continue
        if path.suffix.lower() in _IMAGE_EXTS:
            images.append(str(path.resolve()))
            continue
        try:
            attachments.append((str(path), truncate(path.read_text("utf-8", "ignore"), 8000)))
        except OSError:
            continue
    if attachments or images:
        console.print(f"[dim]📎 attached {len(attachments) + len(images)} file(s)[/dim]")
    if not attachments:
        return text, images
    blocks = "\n\n".join(f"[Attached file: {p}]\n```\n{c}\n```" for p, c in attachments)
    return f"{text}\n\n{blocks}", images


def _run_turn_interactive(
    agent: Agent, config: Config, user_input: str, images: list[str] | None = None
) -> None:
    """Run one turn with a thinking spinner and (optionally) Markdown rendering."""
    try:
        if config.render_markdown:
            # Tokens aren't streamed in this mode; show a spinner while the agent
            # works (tool-activity lines still print live), then render the reply.
            with console.status(f"[{accent()}]Thinking…[/{accent()}]", spinner="dots"):
                answer = agent.run_turn(user_input, images=images)
            console.print()
            console.print(Markdown(answer))
        else:
            agent.run_turn(user_input, images=images)  # raw token streaming
    except KeyboardInterrupt:
        console.print("\n[dim]⏹ Cancelled.[/dim]")
    except LLMError as exc:
        console.print(f"\n[red]LLM error:[/red] {exc}")
    except Exception as exc:  # noqa: BLE001 — never kill the REPL on one bad turn
        logger.exception("Turn failed")
        console.print(f"\n[red]Unexpected error:[/red] {exc}")
    console.print()  # spacing after the reply


def _handle_command(
    command: str,
    registry: ToolRegistry,
    store: MemoryStore,
    agent: Agent,
    config: Config,
    skills: dict[str, Skill],
    commands: dict[str, str],
) -> bool:
    """Handle a slash command. Returns True if PDO should exit."""
    cmd = command.strip().lower()

    if cmd in ("/exit", "/quit"):
        console.print("Goodbye!")
        return True
    if cmd == "/help":
        console.print(Panel(_help_text(commands), border_style=accent()))
    elif cmd in ("/models", "/model"):
        _choose_model(agent, config)
    elif cmd.startswith("/theme"):
        _handle_theme(command, config)
    elif cmd.startswith("/export"):
        _handle_export(command, store)
    elif cmd == "/sessions":
        _print_sessions(store)
    elif cmd.startswith("/new"):
        parts = command.split(maxsplit=1)
        name = store.new_session(parts[1].strip() if len(parts) > 1 else None)
        console.print(f"[green]✓ Started new session[/green] [{accent()}]{name}[/{accent()}]")
    elif cmd.startswith("/resume"):
        _handle_resume(command, store)
    elif cmd == "/version":
        console.print(f"PDO version [{accent()}]{__version__}[/{accent()}]")
    elif cmd == "/tools":
        _print_tools(registry)
    elif cmd == "/mcp":
        _print_mcp()
    elif cmd == "/memory":
        _print_memory(store)
    elif cmd == "/history":
        _print_history(store)
    elif cmd == "/clear":
        store.clear_history()
        console.print("[green]Conversation history cleared.[/green]")
    else:
        # A user-defined skill? (slash command backed by a prompt template.)
        name = command[1:].split(maxsplit=1)[0].lower() if len(command) > 1 else ""
        if name in skills:
            parts = command.split(maxsplit=1)
            rendered = skills[name].render(parts[1].strip() if len(parts) > 1 else "")
            expanded, images = _expand_file_refs(rendered)
            _run_turn_interactive(agent, config, expanded, images)
        else:
            console.print(f"[yellow]Unknown command:[/yellow] {command}  (try /help)")
    return False


def _handle_theme(command: str, config: Config) -> None:
    """`/theme` shows the current theme; `/theme NAME` switches it."""
    parts = command.split()
    available = ", ".join(theme_names())
    if len(parts) < 2:
        console.print(f"Current theme: [{accent()}]{current_theme()}[/{accent()}]")
        console.print(f"[dim]Available: {available}. Use /theme <name>.[/dim]")
        return
    name = parts[1].lower()
    if set_theme(name):
        config.theme = name
        console.print(f"[{accent()}]✓ Theme set to {name}.[/{accent()}]")
    else:
        console.print(f"[yellow]Unknown theme {name!r}.[/yellow] Available: {available}")


def _print_sessions(store: MemoryStore) -> None:
    current = store.current_session()
    console.print("[bold]Sessions[/bold]")
    for name in store.list_sessions():
        marker = f"[{accent()}]●[/{accent()}]" if name == current else " "
        console.print(f"  {marker} {name}")
    console.print("[dim]Switch with /resume <name>, or start one with /new <name>.[/dim]")


def _handle_resume(command: str, store: MemoryStore) -> None:
    parts = command.split(maxsplit=1)
    if len(parts) < 2:
        console.print("[yellow]Usage: /resume <session-name>[/yellow]")
        _print_sessions(store)
        return
    name = parts[1].strip()
    if name not in store.list_sessions():
        console.print(f"[yellow]No session named {name!r}.[/yellow]")
        _print_sessions(store)
        return
    store.switch_session(name)
    console.print(f"[green]✓ Resumed session[/green] [{accent()}]{name}[/{accent()}]")


def _handle_export(command: str, store: MemoryStore) -> None:
    """Save the conversation history to a Markdown file."""
    parts = command.split(maxsplit=1)
    if len(parts) > 1:
        path = Path(parts[1].strip()).expanduser()
    else:
        path = Path.cwd() / f"pdo-conversation-{int(time.time())}.md"

    entries = store.history()
    if not entries:
        console.print("[yellow]No conversation to export yet.[/yellow]")
        return

    lines = ["# PDO conversation", ""]
    for entry in entries:
        who = "You" if entry["role"] == "user" else "PDO"
        lines.append(f"**{who}:**")
        lines.append("")
        lines.append(entry["content"])
        lines.append("")
    try:
        path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        console.print(f"[red]Could not write {path}:[/red] {exc}")
        return
    console.print(f"[green]✓ Exported {len(entries)} messages to[/green] {path}")


def _ask_choice(label: str, count: int) -> int | None:
    """Read a 1-based menu choice; returns None to cancel."""
    raw = console.input(f"[bold]{label}[/bold] [dim](1-{count}, blank to cancel):[/dim] ").strip()
    if not raw:
        return None
    if raw.isdigit() and 1 <= int(raw) <= count:
        return int(raw)
    console.print("[yellow]Invalid choice.[/yellow]")
    return None


def _prompt_secret(prompt: str) -> str:
    """Read a secret (API key) without echoing it to the screen."""
    if _HAVE_PTK and sys.stdout.isatty():
        from prompt_toolkit import prompt as ptk_prompt

        try:
            return ptk_prompt(prompt, is_password=True).strip()
        except (EOFError, KeyboardInterrupt):
            return ""
    import getpass

    try:
        return getpass.getpass(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _resolve_api_key(provider: Provider) -> str:
    """Find an API key for ``provider`` from the session cache or environment.

    Falls back to ``OPENAI_API_KEY`` for OpenRouter, since users often reuse it.
    Prompts interactively (and caches for the session) if nothing is found.
    """
    key = _SESSION_KEYS.get(provider.key) or os.getenv(provider.env_key, "").strip()
    if not key and provider.key == "openrouter":
        key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key

    console.print(f"[yellow]No {provider.env_key} found in the environment.[/yellow]")
    key = _prompt_secret(f"Enter your {provider.label} API key (blank to cancel): ")
    if key:
        _SESSION_KEYS[provider.key] = key  # session-only, never written to disk
    return key


def _provider_base_url(provider: Provider) -> str | None:
    """Resolve the endpoint, honouring OLLAMA_BASE_URL for the local provider."""
    if provider.key == "ollama":
        return os.getenv("OLLAMA_BASE_URL", "").strip() or provider.base_url
    return provider.base_url


def _fetch_models(base_url: str | None, key: str) -> list[str]:
    """Fetch live model ids from an OpenAI-compatible /models endpoint.

    Returns a sorted list, or an empty list if the endpoint can't be reached or
    doesn't support listing (the caller then falls back to the curated list).
    """
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key or "none", base_url=base_url)
        return sorted(model.id for model in client.models.list().data)
    except Exception as exc:  # noqa: BLE001 — listing is best-effort
        logger.warning("Could not fetch models from %s: %s", base_url or "OpenAI", exc)
        return []


# At or below this many models, show a numbered menu; above it, type-to-search.
_MODEL_MENU_LIMIT = 12


def _select_model(models: list[str]) -> str | None:
    """Pick a model: a numbered menu for short lists (e.g. local Ollama models),
    or type-to-search for long ones (e.g. hundreds on OpenRouter). Blank cancels.
    """
    interactive = _HAVE_PTK and sys.stdout.isatty()

    if interactive and len(models) > _MODEL_MENU_LIMIT:
        from prompt_toolkit import prompt as ptk_prompt
        from prompt_toolkit.completion import FuzzyWordCompleter

        try:
            return (
                ptk_prompt(
                    "Model (type to search, Enter to confirm): ",
                    completer=FuzzyWordCompleter(models),
                    complete_while_typing=True,
                ).strip()
                or None
            )
        except (EOFError, KeyboardInterrupt):
            return None

    # Numbered menu: short lists, or any non-interactive terminal.
    shown = models[:40]
    for index, model in enumerate(shown, 1):
        console.print(f"  [cyan]{index}[/cyan]. {model}")
    if len(models) > len(shown):
        console.print(f"  [dim]… and {len(models) - len(shown)} more[/dim]")

    custom_index = len(shown) + 1 if interactive else 0
    if custom_index:
        console.print(f"  [cyan]{custom_index}[/cyan]. [dim]Enter a custom model id[/dim]")

    selection = _ask_choice("Model", custom_index or len(shown))
    if selection is None:
        return None
    if custom_index and selection == custom_index:
        return console.input("Custom model id: ").strip() or None
    return shown[selection - 1]


def _choose_model(agent: Agent, config: Config) -> None:
    """Interactive ``/models`` flow: pick provider → connection → model, then switch."""
    providers = list(PROVIDERS.values())

    console.print("\n[bold cyan]Choose a provider[/bold cyan]")
    for index, provider in enumerate(providers, 1):
        console.print(f"  [cyan]{index}[/cyan]. {provider.label}")
    choice = _ask_choice("Provider", len(providers))
    if choice is None:
        return
    provider = providers[choice - 1]

    base_url = _provider_base_url(provider)

    if provider.key == "ollama":
        # Local server: no authentication and no connection-method step.
        key = "ollama"
    else:
        # Connection method. Only API keys are supported; the menu makes the
        # choice explicit and explains why subscription login isn't available.
        console.print(f"\n[bold cyan]Connect to {provider.label} via[/bold cyan]")
        console.print("  [cyan]1[/cyan]. API key")
        console.print(
            "  [cyan]2[/cyan]. Subscription / account login [dim](not supported)[/dim]"
        )
        method = _ask_choice("Method", 2)
        if method is None:
            return
        if method == 2:
            console.print(
                "[yellow]Subscription login isn't supported — a Claude.ai or "
                "ChatGPT plan does not include API access. Use an API key "
                "(option 1).[/yellow]"
            )
            return
        key = _resolve_api_key(provider)
        if not key:
            console.print("[dim]Cancelled — no API key provided.[/dim]")
            return

    console.print(f"[dim]Fetching available models from {provider.label}…[/dim]")
    models = _fetch_models(base_url, key)
    source = "live from provider"
    if not models:
        models = list(provider.models)
        source = "built-in fallback list"
        if provider.key == "ollama":
            console.print(
                f"[yellow]Couldn't reach Ollama at {base_url}. "
                "Is it running ('ollama serve')?[/yellow]"
            )
    console.print(f"[dim]{len(models)} models available ({source}).[/dim]")

    model = _select_model(models)
    if not model:
        console.print("[dim]Cancelled.[/dim]")
        return

    try:
        llm = OpenAIClient(
            api_key=key,
            model=model,
            temperature=config.temperature,
            base_url=base_url,
        )
    except Exception as exc:  # noqa: BLE001 — show a friendly message, keep the REPL alive
        console.print(f"[red]Failed to initialise {provider.label}:[/red] {exc}")
        return

    agent.set_llm(llm)
    config.openai_model = model
    config.openai_base_url = base_url
    config.openai_api_key = key
    console.print(f"[green]✓ Switched to {provider.label} · {model}[/green]")


def _print_tools(registry: ToolRegistry) -> None:
    plugin_names = set(plugin_tool_names())
    table = Table(title="Available tools", title_style="bold cyan")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description")
    table.add_column("Source", style="dim", no_wrap=True)
    for tool in registry.all():
        if tool.name.startswith("mcp__"):
            source = "mcp"
        elif tool.name in plugin_names:
            source = "plugin"
        else:
            source = "built-in"
        table.add_row(tool.name, tool.description, source)
    console.print(table)
    console.print(
        f"[dim]Drop a .py file defining a Tool subclass in "
        f"{get_plugins_dir()} to add your own.[/dim]"
    )


def _print_mcp() -> None:
    servers = active_servers()
    if not servers:
        console.print(
            "[dim]No MCP servers connected. Configure them in "
            f"{get_mcp_config_path()}.[/dim]"
        )
        return
    for server in servers:
        tools = server.list_tools()
        console.print(f"[{accent()}]●[/{accent()}] [bold]{server.name}[/bold] — {len(tools)} tool(s)")
        for spec in tools:
            console.print(f"    [dim]{spec['name']}[/dim] — {spec.get('description', '')[:70]}")


def _print_memory(store: MemoryStore) -> None:
    facts = store.all_facts()
    prefs = store.preferences()
    if not facts and not prefs:
        console.print("[dim]No memories or preferences saved yet.[/dim]")
        return
    if prefs:
        console.print("[bold]Preferences[/bold]")
        for key, value in prefs.items():
            console.print(f"  {key} = {value}")
    if facts:
        console.print("[bold]Facts[/bold]")
        for fact in facts:
            console.print(f"  [{fact['id']}] {fact['text']}")


def _print_history(store: MemoryStore) -> None:
    entries = store.history(limit=20)
    if not entries:
        console.print("[dim]No conversation history yet.[/dim]")
        return
    for entry in entries:
        role = entry["role"]
        colour = "blue" if role == "user" else "green"
        console.print(f"[{colour}]{role}[/{colour}]: {entry['content']}")


def _format_args(args: dict) -> str:
    """Render tool arguments compactly for the activity line."""
    parts = []
    for key, value in args.items():
        text = str(value).replace("\n", " ")
        if len(text) > 40:
            text = text[:37] + "..."
        parts.append(f"{key}={text!r}")
    return ", ".join(parts)


if __name__ == "__main__":
    sys.exit(main())
