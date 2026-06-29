"""Filesystem tools: read, write, append, list and create directories.

Writes are sandboxed to the current working directory by default. Writing
outside it, or overwriting an existing file, requires explicit confirmation —
the confirmation callback is injectable so it can be mocked in tests.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .base import Tool, default_confirm
from .registry import register_tool

logger = logging.getLogger(__name__)

# Guard against accidentally pasting a huge file into the model context.
MAX_READ_CHARS = 200_000


def _resolve(path: str) -> Path:
    """Expand ``~`` and resolve to an absolute path."""
    return Path(path).expanduser().resolve()


def _within_cwd(path: Path) -> bool:
    """Return True if ``path`` is inside the current working directory."""
    try:
        path.relative_to(Path.cwd().resolve())
        return True
    except ValueError:
        return False


@register_tool
class ReadFileTool(Tool):
    name = "read_file"
    description = "Read and return the UTF-8 text contents of a file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read."}
        },
        "required": ["path"],
    }

    def run(self, path: str, **_: Any) -> str:
        target = _resolve(path)
        if not target.exists():
            return f"Error: file not found: {target}"
        if not target.is_file():
            return f"Error: not a file: {target}"
        data = target.read_text(encoding="utf-8", errors="replace")
        if len(data) > MAX_READ_CHARS:
            data = data[:MAX_READ_CHARS] + "\n... [truncated]"
        return data


@register_tool
class WriteFileTool(Tool):
    name = "write_file"
    description = (
        "Write text to a file (creating parent directories). Asks for "
        "confirmation before overwriting a file or writing outside the working "
        "directory."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Destination file path."},
            "content": {"type": "string", "description": "Text to write."},
        },
        "required": ["path", "content"],
    }

    def __init__(self, confirm: Callable[[str], bool] = default_confirm) -> None:
        self._confirm = confirm

    def run(self, path: str, content: str, **_: Any) -> str:
        target = _resolve(path)
        if not _within_cwd(target) and not self._confirm(
            f"Write OUTSIDE the working directory to {target}?"
        ):
            return "Cancelled: writing outside the working directory was not confirmed."
        if target.exists() and not self._confirm(f"Overwrite existing file {target}?"):
            return "Cancelled: overwrite was not confirmed."
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} characters to {target}"


@register_tool
class AppendFileTool(Tool):
    name = "append_file"
    description = (
        "Append text to a file (creating it if needed). Asks for confirmation "
        "before writing outside the working directory."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target file path."},
            "content": {"type": "string", "description": "Text to append."},
        },
        "required": ["path", "content"],
    }

    def __init__(self, confirm: Callable[[str], bool] = default_confirm) -> None:
        self._confirm = confirm

    def run(self, path: str, content: str, **_: Any) -> str:
        target = _resolve(path)
        if not _within_cwd(target) and not self._confirm(
            f"Append OUTSIDE the working directory to {target}?"
        ):
            return "Cancelled: writing outside the working directory was not confirmed."
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(content)
        return f"Appended {len(content)} characters to {target}"


@register_tool
class ListDirTool(Tool):
    name = "list_directory"
    description = "List the entries of a directory (directories are marked)."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory to list. Defaults to the current directory.",
            }
        },
    }

    def run(self, path: str = ".", **_: Any) -> str:
        target = _resolve(path)
        if not target.exists():
            return f"Error: directory not found: {target}"
        if not target.is_dir():
            return f"Error: not a directory: {target}"
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = [f"{'[dir] ' if entry.is_dir() else '      '}{entry.name}" for entry in entries]
        return "\n".join(lines) if lines else "(empty directory)"


@register_tool
class CreateDirTool(Tool):
    name = "create_directory"
    description = (
        "Create a directory (including parents). Asks for confirmation before "
        "creating it outside the working directory."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to create."}
        },
        "required": ["path"],
    }

    def __init__(self, confirm: Callable[[str], bool] = default_confirm) -> None:
        self._confirm = confirm

    def run(self, path: str, **_: Any) -> str:
        target = _resolve(path)
        if not _within_cwd(target) and not self._confirm(
            f"Create directory OUTSIDE the working directory at {target}?"
        ):
            return "Cancelled: creating outside the working directory was not confirmed."
        target.mkdir(parents=True, exist_ok=True)
        return f"Created directory {target}"
