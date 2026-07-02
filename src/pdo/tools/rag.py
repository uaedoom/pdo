"""Codebase retrieval tool backed by the BM25 index in :mod:`pdo.rag`."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..rag import build_index, load_index, search
from .base import Tool, truncate
from .registry import register_tool

# Snippet size cap per result so a handful of hits can't flood the context.
_SNIPPET_CHARS = 1200


@register_tool
class CodebaseSearchTool(Tool):
    name = "codebase_search"
    description = (
        "Semantic-ish search over the indexed codebase in the current directory: "
        "returns the most relevant code/document chunks for a natural-language "
        "query, with path:line references. Builds the index on first use; the "
        "user can refresh it with /index."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to look for (identifiers, phrases, concepts).",
            },
            "top_k": {
                "type": "integer",
                "description": "How many chunks to return (default 5).",
            },
        },
        "required": ["query"],
    }

    def run(self, query: str, top_k: int = 5, **_: Any) -> str:
        root = Path.cwd()
        index = load_index(root)
        if index is None or index.root != str(root.resolve()):
            index = build_index(root)
        if not index.chunks:
            return "The index is empty — no indexable files found here."

        results = search(index, query, top_k=max(1, min(top_k, 20)))
        if not results:
            return "No relevant chunks found for that query."

        blocks = []
        for result in results:
            chunk = result.chunk
            snippet = chunk.text
            if len(snippet) > _SNIPPET_CHARS:
                snippet = snippet[:_SNIPPET_CHARS] + "\n… [truncated]"
            blocks.append(
                f"[{chunk.path}:{chunk.start}-{chunk.end}] (score {result.score:.1f})\n{snippet}"
            )
        return truncate("\n\n---\n\n".join(blocks), 8000)
