"""PDO (Python Do) — Think. Plan. Do.

A terminal-first AI agent that reasons about a goal, plans the work, decides
whether tools are needed, executes them safely, reviews the result, and replies
clearly. The public surface intentionally stays small; everything is wired
together in :mod:`pdo.main`.
"""
from __future__ import annotations

__version__ = "1.0.0"
__all__ = ["__version__", "run_agent"]


def __getattr__(name: str):
    # Lazy re-export so `import pdo` stays lightweight; the agent stack is only
    # pulled in when run_agent is actually used.
    if name == "run_agent":
        from .api import run_agent

        return run_agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
