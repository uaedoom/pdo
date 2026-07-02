"""Serve mode: expose the PDO agent over stdio JSON-RPC (MCP-compatible).

``pdo --serve`` turns PDO into an **MCP server**: any MCP client (Claude
Desktop, Claude Code, another PDO…) can connect over stdio and call the
``run_task`` tool, which runs a prompt through the full PDO agent — tools,
sub-agents, codebase search and all — and returns the final answer.

Protocol: newline-delimited JSON-RPC 2.0 with the MCP handshake
(``initialize`` → ``tools/list`` → ``tools/call``), i.e. the mirror image of
:mod:`pdo.mcp`, which is PDO acting as a *client*.

Because stdin/stdout carry the protocol, serve mode never prints to stdout and
auto-denies interactive confirmations (dangerous commands are simply refused).
"""
from __future__ import annotations

import json
import logging
from typing import Any, TextIO

from . import __version__
from .mcp import PROTOCOL_VERSION

logger = logging.getLogger(__name__)

_RUN_TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "task": {
            "type": "string",
            "description": "The complete, self-contained task or question for the agent.",
        }
    },
    "required": ["task"],
}


class PDOServer:
    """A minimal MCP server wrapping one PDO agent."""

    def __init__(self, agent: Any) -> None:
        self._agent = agent

    # --- request handling ---------------------------------------------------- #
    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Handle one JSON-RPC message; returns the response (None for notifications)."""
        method = message.get("method", "")
        msg_id = message.get("id")

        if msg_id is None:  # notification (e.g. notifications/initialized)
            return None
        if method == "initialize":
            return self._result(
                msg_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "pdo", "version": __version__},
                },
            )
        if method == "tools/list":
            return self._result(
                msg_id,
                {
                    "tools": [
                        {
                            "name": "run_task",
                            "description": (
                                "Run a task with the PDO agent: it reasons, uses its "
                                "tools (files, shell, web, git, codebase search, "
                                "sub-agents, connected MCP servers) and returns the "
                                "final answer."
                            ),
                            "inputSchema": _RUN_TASK_SCHEMA,
                        }
                    ]
                },
            )
        if method == "tools/call":
            return self._call_tool(msg_id, message.get("params") or {})
        return self._error(msg_id, -32601, f"method not found: {method}")

    def _call_tool(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if name != "run_task":
            return self._error(msg_id, -32602, f"unknown tool: {name}")
        task = (params.get("arguments") or {}).get("task", "").strip()
        if not task:
            return self._error(msg_id, -32602, "missing required argument: task")
        try:
            answer = self._agent.run_turn(task)
            is_error = False
        except Exception as exc:  # noqa: BLE001 — report, keep serving
            logger.exception("run_task failed")
            answer, is_error = f"Agent error: {exc}", True
        return self._result(
            msg_id,
            {"content": [{"type": "text", "text": answer}], "isError": is_error},
        )

    # --- plumbing -------------------------------------------------------------- #
    @staticmethod
    def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    @staticmethod
    def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}

    def serve_forever(self, stdin: TextIO, stdout: TextIO) -> None:
        """Blocking loop: one JSON-RPC message per line until EOF."""
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Ignoring non-JSON input line")
                continue
            response = self.handle(message)
            if response is not None:
                stdout.write(json.dumps(response) + "\n")
                stdout.flush()
