"""Minimal Model Context Protocol (MCP) client.

Connects to MCP servers over the stdio transport (newline-delimited JSON-RPC
2.0), lists their tools, and exposes each as a PDO :class:`~pdo.tools.base.Tool`
so the agent can use them transparently. Implemented synchronously with the
standard library only — no extra dependencies, consistent with PDO's v1 design.

Servers are declared in ``<PDO_HOME>/mcp.json`` using the widely-used format::

    {
      "mcpServers": {
        "filesystem": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
        }
      }
    }
"""
from __future__ import annotations

import json
import logging
import os
import re
import select
import subprocess
import time
from pathlib import Path
from typing import Any

from . import __version__
from .tools.base import Tool, truncate
from .tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
_REQUEST_TIMEOUT = 30
_CALL_TIMEOUT = 120

# Servers started this process, for introspection (e.g. the /mcp command).
_ACTIVE_SERVERS: list[MCPServer] = []


class MCPError(RuntimeError):
    """Raised when an MCP server errors or can't be reached."""


def _sanitize(name: str) -> str:
    """Make a tool name safe for the model API (^[A-Za-z0-9_-]{1,64}$)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)[:64]


class MCPServer:
    """A single MCP server subprocess, spoken to over stdio JSON-RPC."""

    def __init__(
        self, name: str, command: str, args: list[str], env: dict[str, str] | None = None
    ) -> None:
        self.name = name
        self.command = command
        self.args = list(args)
        self.env = dict(env or {})
        self._proc: subprocess.Popen | None = None
        self._id = 0
        self._tools: list[dict[str, Any]] = []

    # --- lifecycle ---------------------------------------------------------- #
    def start(self) -> None:
        """Spawn the server, perform the MCP handshake, and cache its tools."""
        self._proc = subprocess.Popen(  # noqa: S603 — launching a user-configured server
            [self.command, *self.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env={**os.environ, **self.env},
        )
        self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "pdo", "version": __version__},
            },
        )
        self._notify("notifications/initialized")
        self._tools = self._request("tools/list").get("tools", [])

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            self._proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 — force-kill if it won't exit cleanly
            self._proc.kill()
        finally:
            self._proc = None

    # --- public API --------------------------------------------------------- #
    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._tools)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        result = self._request(
            "tools/call", {"name": name, "arguments": arguments}, timeout=_CALL_TIMEOUT
        )
        parts = []
        for item in result.get("content", []):
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
            else:
                parts.append(json.dumps(item))
        text = "\n".join(parts) if parts else "(no content)"
        if result.get("isError"):
            return f"Error from MCP tool: {truncate(text)}"
        return truncate(text)

    # --- JSON-RPC plumbing -------------------------------------------------- #
    def _send(self, message: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise MCPError(f"MCP server {self.name!r} is not running")
        self._proc.stdin.write(json.dumps(message) + "\n")
        self._proc.stdin.flush()

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _request(
        self, method: str, params: dict[str, Any] | None = None, timeout: int = _REQUEST_TIMEOUT
    ) -> dict[str, Any]:
        self._id += 1
        request_id = self._id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})

        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self._read_line(deadline - time.time())
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == request_id:
                if "error" in message:
                    raise MCPError(message["error"].get("message", "MCP error"))
                return message.get("result", {})
            # Otherwise it's a notification or an unrelated message: ignore it.
        raise MCPError(f"timed out waiting for {method!r} from {self.name!r}")

    def _read_line(self, timeout: float) -> str | None:
        if self._proc is None or self._proc.stdout is None:
            return None
        try:
            ready, _, _ = select.select([self._proc.stdout], [], [], max(0.0, timeout))
        except (OSError, ValueError):
            # select may not work on this platform's pipes; fall back to blocking.
            return self._proc.stdout.readline() or None
        if not ready:
            return None
        return self._proc.stdout.readline() or None


class MCPTool(Tool):
    """Adapts a remote MCP tool to PDO's Tool interface."""

    def __init__(self, server: MCPServer, mcp_name: str, description: str, schema: dict | None):
        self.name = _sanitize(f"mcp__{server.name}__{mcp_name}")
        self.description = description or f"MCP tool {mcp_name} from {server.name}."
        self.parameters = schema or {"type": "object", "properties": {}}
        self._server = server
        self._mcp_name = mcp_name

    def run(self, **kwargs: Any) -> str:
        try:
            return self._server.call_tool(self._mcp_name, kwargs)
        except MCPError as exc:
            return f"Error: {exc}"


def load_mcp_config(path: Path) -> dict[str, dict]:
    """Read the ``mcpServers`` mapping from ``path`` (empty if missing/invalid)."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read MCP config %s: %s", path, exc)
        return {}
    servers = data.get("mcpServers", data) if isinstance(data, dict) else {}
    return servers if isinstance(servers, dict) else {}


def start_servers(
    registry: ToolRegistry, servers_config: dict[str, dict]
) -> tuple[list[MCPServer], list[tuple[str, int, str | None]]]:
    """Start each configured server and register its tools.

    Returns the started servers and a per-server ``(name, tool_count, error)``
    summary. A server that fails to start is skipped, not fatal.
    """
    started: list[MCPServer] = []
    summary: list[tuple[str, int, str | None]] = []

    for name, spec in servers_config.items():
        command = spec.get("command")
        if not command:
            summary.append((name, 0, "no 'command' specified"))
            continue
        server = MCPServer(name, command, spec.get("args", []), spec.get("env", {}))
        try:
            server.start()
        except Exception as exc:  # noqa: BLE001 — a bad server must not crash PDO
            logger.warning("MCP server %r failed to start: %s", name, exc)
            summary.append((name, 0, str(exc)))
            continue

        count = 0
        for spec_tool in server.list_tools():
            tool = MCPTool(
                server,
                spec_tool["name"],
                spec_tool.get("description", ""),
                spec_tool.get("inputSchema"),
            )
            if not registry.has(tool.name):
                registry.register(tool)
                count += 1
        started.append(server)
        _ACTIVE_SERVERS.append(server)
        summary.append((name, count, None))

    return started, summary


def active_servers() -> list[MCPServer]:
    return list(_ACTIVE_SERVERS)
