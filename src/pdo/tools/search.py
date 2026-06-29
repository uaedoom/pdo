"""Code-search tools: glob for files and grep file contents."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import Tool, truncate
from .registry import register_tool

# Directories that are noise for code search; skipped by grep.
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".ruff_cache", ".pytest_cache"}
_MAX_HITS = 200


def _skipped(path: Path) -> bool:
    return any(part in _SKIP_DIRS for part in path.parts)


@register_tool
class GlobTool(Tool):
    name = "glob_files"
    description = "Find files matching a glob pattern (e.g. '**/*.py') under a directory."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern, e.g. '**/*.md'."},
            "path": {"type": "string", "description": "Base directory (default current)."},
        },
        "required": ["pattern"],
    }

    def run(self, pattern: str, path: str = ".", **_: Any) -> str:
        base = Path(path).expanduser()
        if not base.exists():
            return f"Error: path not found: {base}"
        matches = [
            str(p) for p in sorted(base.glob(pattern)) if p.is_file() and not _skipped(p)
        ][:500]
        return truncate("\n".join(matches)) if matches else "No files matched."


@register_tool
class GrepTool(Tool):
    name = "search_files"
    description = (
        "Search file contents for a regular expression and return matching "
        "'path:line: text'. Skips common noise directories (.git, .venv, …)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regular expression to search for."},
            "path": {"type": "string", "description": "Base directory (default current)."},
            "glob": {
                "type": "string",
                "description": "Limit to files matching this glob (default '**/*').",
            },
        },
        "required": ["pattern"],
    }

    def run(self, pattern: str, path: str = ".", glob: str = "**/*", **_: Any) -> str:
        base = Path(path).expanduser()
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return f"Invalid regular expression: {exc}"

        hits: list[str] = []
        for file in base.glob(glob):
            if not file.is_file() or _skipped(file):
                continue
            try:
                content = file.read_text("utf-8", "ignore")
            except OSError:
                continue
            for lineno, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    hits.append(f"{file}:{lineno}: {line.strip()[:200]}")
                    if len(hits) >= _MAX_HITS:
                        return truncate("\n".join(hits) + "\n… [more matches omitted]")
        return truncate("\n".join(hits)) if hits else "No matches found."
