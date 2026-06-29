"""Tests for the filesystem tools."""
from __future__ import annotations

from pdo.tools.filesystem import (
    AppendFileTool,
    CreateDirTool,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)

_ALWAYS = lambda _prompt: True  # noqa: E731 — terse confirm stub for tests
_NEVER = lambda _prompt: False  # noqa: E731


def test_write_then_read(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "note.txt"

    result = WriteFileTool(confirm=_ALWAYS).run(path=str(target), content="hello")
    assert "Wrote" in result
    assert ReadFileTool().run(path=str(target)) == "hello"


def test_overwrite_requires_confirmation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "note.txt"
    target.write_text("original")

    result = WriteFileTool(confirm=_NEVER).run(path=str(target), content="changed")
    assert "Cancelled" in result
    assert target.read_text() == "original"  # unchanged


def test_append_accumulates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "log.txt"

    AppendFileTool(confirm=_ALWAYS).run(path=str(target), content="a")
    AppendFileTool(confirm=_ALWAYS).run(path=str(target), content="b")
    assert ReadFileTool().run(path=str(target)) == "ab"


def test_create_directory_and_list(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    CreateDirTool(confirm=_ALWAYS).run(path=str(tmp_path / "sub"))
    listing = ListDirTool().run(path=str(tmp_path))
    assert "sub" in listing


def test_read_missing_file_is_graceful(tmp_path):
    result = ReadFileTool().run(path=str(tmp_path / "nope.txt"))
    assert result.startswith("Error: file not found")
