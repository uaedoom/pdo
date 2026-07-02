"""Sub-agent delegation tool.

``delegate_task`` lets the main agent hand a self-contained subtask to a fresh
child agent that runs its own ReAct loop and returns only its final answer.
This keeps the parent's context small on large multi-part jobs.

The tool lives in the agent package (not ``pdo.tools``) because it is
intrinsically coupled to the agent: it needs to spawn one. It is registered by
the top-level agent itself, and deliberately excluded from the registries handed
to children, so delegation cannot recurse without bound.
"""
from __future__ import annotations

import logging
from typing import Any

from ..tools.base import Tool

logger = logging.getLogger(__name__)

# Belt-and-braces recursion cap: children don't get the delegate tool at all,
# but the depth check also guards any future registry changes.
MAX_DELEGATION_DEPTH = 2


class DelegateTool(Tool):
    """Adapter exposing ``Agent.run_subtask`` as a model-callable tool."""

    name = "delegate_task"
    description = (
        "Delegate a self-contained subtask to a fresh sub-agent that has the "
        "same tools and reports back only its final result. Use it to keep "
        "context small when a job has large independent parts (e.g. 'summarise "
        "every file in docs/'). Include ALL information the sub-agent needs — "
        "it cannot see this conversation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The complete, self-contained task for the sub-agent.",
            },
            "context": {
                "type": "string",
                "description": "Optional extra context (paths, constraints, prior findings).",
            },
        },
        "required": ["task"],
    }

    def __init__(self, parent: Any) -> None:  # Any avoids a circular import with core
        self._parent = parent

    def run(self, task: str, context: str = "", **_: Any) -> str:
        return self._parent.run_subtask(task, context)
