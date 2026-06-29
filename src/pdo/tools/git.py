"""Git tool: run git commands in the working directory."""
from __future__ import annotations

import shlex
import subprocess
from typing import Any

from .base import Tool, truncate
from .registry import register_tool


@register_tool
class GitTool(Tool):
    name = "git"
    description = (
        "Run a git command in the working directory and return its output "
        "(e.g. 'status --short', 'diff', 'log --oneline -10', "
        "'commit -m \"message\"'). Network commands like push use your "
        "existing credentials."
    )
    parameters = {
        "type": "object",
        "properties": {
            "args": {
                "type": "string",
                "description": "Arguments passed to git, e.g. 'status --short'.",
            }
        },
        "required": ["args"],
    }

    def run(self, args: str, **_: Any) -> str:
        try:
            argv = ["git", *shlex.split(args)]
        except ValueError as exc:
            return f"Error parsing git arguments: {exc}"
        try:
            completed = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            return "Error: git is not installed or not on PATH."
        except subprocess.TimeoutExpired:
            return "Error: git command timed out."
        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        return f"[exit {completed.returncode}]\n{truncate(output or '(no output)')}"
