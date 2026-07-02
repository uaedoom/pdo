"""Tests for serve mode (PDO as an MCP server) with a mocked agent/LLM."""
from __future__ import annotations

import io
import json

from pdo import __version__
from pdo.serve import PDOServer


class FakeAgent:
    def __init__(self, answer="the answer", fail=False):
        self._answer = answer
        self._fail = fail
        self.seen: list[str] = []

    def run_turn(self, task, images=None):
        if self._fail:
            raise RuntimeError("boom")
        self.seen.append(task)
        return self._answer


def _drive(server: PDOServer, messages: list[dict]) -> list[dict]:
    stdin = io.StringIO("\n".join(json.dumps(m) for m in messages) + "\n")
    stdout = io.StringIO()
    server.serve_forever(stdin, stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def test_full_mcp_handshake_and_call():
    agent = FakeAgent(answer="42 files")
    responses = _drive(
        PDOServer(agent),
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "run_task", "arguments": {"task": "count files"}},
            },
        ],
    )

    init, listing, call = responses
    assert init["result"]["serverInfo"] == {"name": "pdo", "version": __version__}
    assert [t["name"] for t in listing["result"]["tools"]] == ["run_task"]
    assert call["result"]["content"] == [{"type": "text", "text": "42 files"}]
    assert call["result"]["isError"] is False
    assert agent.seen == ["count files"]


def test_unknown_method_and_tool_errors():
    server = PDOServer(FakeAgent())
    responses = _drive(
        server,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "nope"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "other"}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "run_task", "arguments": {}},
            },
        ],
    )
    assert responses[0]["error"]["code"] == -32601
    assert responses[1]["error"]["code"] == -32602
    assert "task" in responses[2]["error"]["message"]


def test_agent_failure_is_reported_not_fatal():
    responses = _drive(
        PDOServer(FakeAgent(fail=True)),
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "run_task", "arguments": {"task": "x"}},
            }
        ],
    )
    assert responses[0]["result"]["isError"] is True
    assert "boom" in responses[0]["result"]["content"][0]["text"]


def test_garbage_lines_are_ignored():
    stdin = io.StringIO('not json\n{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n')
    stdout = io.StringIO()
    PDOServer(FakeAgent()).serve_forever(stdin, stdout)
    lines = stdout.getvalue().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["id"] == 1
