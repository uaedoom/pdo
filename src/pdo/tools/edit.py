"""Targeted file edit tool: replace an exact snippet (safer than full rewrites)."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import Tool, default_confirm
from .filesystem import _resolve, _within_cwd
from .registry import register_tool


@register_tool
class EditFileTool(Tool):
    name = "edit_file"
    description = (
        "Replace an exact text snippet in a file with new text — safer than "
        "rewriting the whole file. The old text must appear exactly once; add "
        "surrounding context to make it unique."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File to edit."},
            "old_string": {
                "type": "string",
                "description": "Exact text to replace (must be unique in the file).",
            },
            "new_string": {"type": "string", "description": "Replacement text."},
        },
        "required": ["path", "old_string", "new_string"],
    }

    def __init__(self, confirm: Callable[[str], bool] = default_confirm) -> None:
        self._confirm = confirm

    def run(self, path: str, old_string: str, new_string: str, **_: Any) -> str:
        target = _resolve(path)
        if not target.exists():
            return f"Error: file not found: {target}"
        if not _within_cwd(target) and not self._confirm(
            f"Edit file OUTSIDE the working directory {target}?"
        ):
            return "Cancelled: editing outside the working directory was not confirmed."

        content = target.read_text(encoding="utf-8")
        occurrences = content.count(old_string)
        if occurrences == 0:
            return "Error: old_string was not found in the file."
        if occurrences > 1:
            return (
                f"Error: old_string is not unique ({occurrences} matches). "
                "Add more surrounding context so it matches exactly once."
            )
        target.write_text(content.replace(old_string, new_string), encoding="utf-8")
        return f"Edited {target} (1 replacement)."
