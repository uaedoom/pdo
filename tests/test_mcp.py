"""End-to-end test of the MCP stdio client against a tiny fake server.

The fake server is a self-contained Python script that speaks newline-delimited
JSON-RPC, so this exercises the real handshake / list / call path with no
external dependencies or network.
"""
from __future__ import annotations

import sys
import textwrap

from pdo.mcp import MCPServer, load_mcp_config, start_servers
from pdo.tools.registry import ToolRegistry

_FAKE_SERVER = textwrap.dedent(
    '''
    import json, sys

    def send(msg):
        sys.stdout.write(json.dumps(msg) + "\\n")
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        mid, method = msg.get("id"), msg.get("method")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid,
                  "result": {"protocolVersion": "2024-11-05", "capabilities": {},
                             "serverInfo": {"name": "fake", "version": "1"}}})
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [
                {"name": "echo", "description": "Echo text",
                 "inputSchema": {"type": "object",
                                 "properties": {"text": {"type": "string"}},
                                 "required": ["text"]}}]}})
        elif method == "tools/call":
            args = msg["params"].get("arguments", {})
            send({"jsonrpc": "2.0", "id": mid,
                  "result": {"content": [{"type": "text", "text": "echo: " + args.get("text", "")}]}})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid,
                  "error": {"code": -32601, "message": "method not found"}})
    '''
)


def _write_server(tmp_path):
    path = tmp_path / "fake_server.py"
    path.write_text(_FAKE_SERVER)
    return path


def test_server_handshake_list_and_call(tmp_path):
    server = MCPServer("fake", sys.executable, [str(_write_server(tmp_path))])
    try:
        server.start()
        names = [t["name"] for t in server.list_tools()]
        assert "echo" in names
        assert "echo: hi" in server.call_tool("echo", {"text": "hi"})
    finally:
        server.stop()


def test_start_servers_registers_prefixed_tools(tmp_path):
    registry = ToolRegistry()
    config = {"fake": {"command": sys.executable, "args": [str(_write_server(tmp_path))]}}
    servers, summary = start_servers(registry, config)
    try:
        assert registry.has("mcp__fake__echo")
        assert registry.get("mcp__fake__echo").run(text="yo") == "echo: yo"
        assert summary == [("fake", 1, None)]
    finally:
        for server in servers:
            server.stop()


def test_load_mcp_config(tmp_path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text('{"mcpServers": {"a": {"command": "x", "args": []}}}')
    assert load_mcp_config(cfg) == {"a": {"command": "x", "args": []}}
    assert load_mcp_config(tmp_path / "missing.json") == {}


def test_bad_server_is_skipped_not_fatal(tmp_path):
    registry = ToolRegistry()
    config = {"broken": {"command": "this-command-does-not-exist-pdo", "args": []}}
    servers, summary = start_servers(registry, config)
    assert servers == []
    assert summary[0][0] == "broken" and summary[0][2] is not None
