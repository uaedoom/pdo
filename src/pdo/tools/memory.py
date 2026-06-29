"""Memory tools: save, search and delete facts in the local JSON store.

These thin wrappers expose :class:`pdo.agent.memory.MemoryStore` to the model so
it can remember useful facts and preferences across turns and sessions.
"""
from __future__ import annotations

from typing import Any

from ..agent.memory import get_memory_store
from .base import Tool
from .registry import register_tool


@register_tool
class MemorySaveTool(Tool):
    name = "memory_save"
    description = "Save a useful fact or user preference to long-term memory."
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The fact to remember."},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags to aid later search.",
            },
        },
        "required": ["text"],
    }

    def run(self, text: str, tags: list[str] | None = None, **_: Any) -> str:
        fact_id = get_memory_store().save_fact(text, tags or [])
        return f"Saved memory {fact_id}."


@register_tool
class MemorySearchTool(Tool):
    name = "memory_search"
    description = "Search long-term memory for facts matching a keyword query."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Keyword(s) to search for."}
        },
        "required": ["query"],
    }

    def run(self, query: str, **_: Any) -> str:
        hits = get_memory_store().search_facts(query)
        if not hits:
            return "No memories matched that query."
        return "\n".join(f"[{hit['id']}] {hit['text']}" for hit in hits)


@register_tool
class MemoryDeleteTool(Tool):
    name = "memory_delete"
    description = "Delete a memory by its id."
    parameters = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "The id of the memory to delete."}
        },
        "required": ["id"],
    }

    def run(self, id: str, **_: Any) -> str:  # noqa: A002 — matches the schema field name
        deleted = get_memory_store().delete_fact(id)
        return "Deleted." if deleted else "No memory with that id."
