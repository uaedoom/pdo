"""Database tools: query a SQLite file."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .base import Tool, truncate
from .registry import register_tool

_MAX_ROWS = 200


@register_tool
class SqliteQueryTool(Tool):
    name = "sqlite_query"
    description = (
        "Run a SQL statement against a SQLite database file. SELECTs return rows; "
        "other statements are committed and report the affected row count."
    )
    parameters = {
        "type": "object",
        "properties": {
            "db_path": {"type": "string", "description": "Path to the .sqlite/.db file."},
            "query": {"type": "string", "description": "The SQL statement to run."},
            "params": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional positional parameters for the query.",
            },
        },
        "required": ["db_path", "query"],
    }

    def run(
        self, db_path: str, query: str, params: list[Any] | None = None, **_: Any
    ) -> str:
        path = Path(db_path).expanduser()
        if not path.exists():
            return f"Error: database not found: {path}"
        try:
            connection = sqlite3.connect(str(path))
            connection.row_factory = sqlite3.Row
            cursor = connection.execute(query, tuple(params or []))
            if cursor.description:  # a result-producing query (SELECT/PRAGMA)
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchmany(_MAX_ROWS)
                lines = [" | ".join(columns)]
                lines += [" | ".join(str(row[c]) for c in columns) for row in rows]
                connection.close()
                return truncate("\n".join(lines)) if rows else "(no rows)"
            connection.commit()
            affected = cursor.rowcount
            connection.close()
            return f"OK ({affected} row(s) affected)."
        except sqlite3.Error as exc:
            return f"SQLite error: {exc}"
