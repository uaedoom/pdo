"""Example PDO plugin tool.

To use it, copy this file into your PDO plugins directory (shown by the `/tools`
command — by default ``<PDO_HOME>/plugins``). PDO loads it on the next start and
the model can call ``current_time``.

A plugin only needs to subclass ``Tool``; the ``@register_tool`` decorator is
optional for plugins because PDO discovers ``Tool`` subclasses automatically.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pdo.tools.base import Tool


class CurrentTimeTool(Tool):
    name = "current_time"
    description = "Return the current local date and time (ISO 8601)."
    parameters = {"type": "object", "properties": {}}

    def run(self, **_: Any) -> str:
        return datetime.now().isoformat(timespec="seconds")
