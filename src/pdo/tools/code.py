"""Code execution tool.

Runs Python in a *separate process* with a timeout. This isolates crashes and
bounds runtime, but it is NOT a security sandbox — the code runs with the same
permissions as PDO. Use it for calculations and quick data tasks.
"""
from __future__ import annotations

import subprocess
import sys
from typing import Any

from .base import Tool, truncate
from .registry import register_tool


@register_tool
class PythonExecTool(Tool):
    name = "python_exec"
    description = (
        "Execute a snippet of Python code in a separate process and return its "
        "stdout/stderr. Good for calculations, parsing, and quick data tasks. "
        "Print results you want to see."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python source to run."},
            "timeout": {
                "type": "integer",
                "description": "Maximum seconds to run (default 30).",
            },
        },
        "required": ["code"],
    }

    def run(self, code: str, timeout: int = 30, **_: Any) -> str:
        try:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"Error: code timed out after {timeout}s."
        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        return f"[exit {completed.returncode}]\n{truncate(output or '(no output)')}"
