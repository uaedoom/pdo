"""Tests for the tool registry."""
from __future__ import annotations

from pdo.tools.base import Tool
from pdo.tools.registry import ToolRegistry, get_registry


def test_builtin_tools_are_registered():
    registry = get_registry()
    names = set(registry.names())
    for expected in {"read_file", "write_file", "run_shell", "memory_save"}:
        assert expected in names


def test_schemas_have_expected_shape():
    for schema in get_registry().schemas():
        assert schema["type"] == "function"
        function = schema["function"]
        assert function["name"]
        assert "description" in function
        assert function["parameters"]["type"] == "object"


def test_register_and_retrieve_custom_tool():
    registry = ToolRegistry()

    class EchoTool(Tool):
        name = "echo"
        description = "Echo its input."
        parameters = {"type": "object", "properties": {}}

        def run(self, **kwargs):
            return "echo"

    registry.register(EchoTool())
    assert registry.has("echo")
    assert registry.get("echo").run() == "echo"


def test_unknown_tool_raises_keyerror():
    registry = ToolRegistry()
    try:
        registry.get("does-not-exist")
    except KeyError:
        return
    raise AssertionError("expected KeyError for unknown tool")


def test_nameless_tool_is_rejected():
    registry = ToolRegistry()

    class Nameless(Tool):
        def run(self, **kwargs):
            return ""

    try:
        registry.register(Nameless())
    except ValueError:
        return
    raise AssertionError("expected ValueError for a tool without a name")
