"""Tests for plugin auto-discovery."""
from __future__ import annotations

from pdo.tools.registry import ToolRegistry, discover_directory_plugins

_PLUGIN_SOURCE = '''
from typing import Any
from pdo.tools.base import Tool


class HelloPluginTool(Tool):
    name = "hello_plugin"
    description = "Say hi from a plugin."
    parameters = {"type": "object", "properties": {}}

    def run(self, **_: Any) -> str:
        return "hi from plugin"
'''


def test_directory_plugin_is_discovered(tmp_path):
    (tmp_path / "hello.py").write_text(_PLUGIN_SOURCE)

    registry = ToolRegistry()
    discover_directory_plugins(registry, tmp_path)

    assert registry.has("hello_plugin")
    assert registry.get("hello_plugin").run() == "hi from plugin"


def test_underscore_files_are_skipped(tmp_path):
    (tmp_path / "_private.py").write_text(_PLUGIN_SOURCE)

    registry = ToolRegistry()
    discover_directory_plugins(registry, tmp_path)

    assert registry.names() == []


def test_broken_plugin_does_not_crash(tmp_path):
    (tmp_path / "ok.py").write_text(_PLUGIN_SOURCE)
    (tmp_path / "broken.py").write_text("this is ::: not valid python")

    registry = ToolRegistry()
    # Must not raise despite the broken file…
    discover_directory_plugins(registry, tmp_path)
    # …and the valid plugin still loads.
    assert registry.has("hello_plugin")


def test_missing_directory_is_noop(tmp_path):
    registry = ToolRegistry()
    discover_directory_plugins(registry, tmp_path / "does-not-exist")
    assert registry.names() == []
