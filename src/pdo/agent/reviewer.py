"""Thin reviewer.

A final sanity check on the answer before it reaches the user. For v1 this just
guarantees a non-empty reply; it is the natural extension point for richer
checks later (e.g. verifying claimed actions actually ran).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class Reviewer:
    """Validates and, if necessary, repairs the agent's final answer."""

    def review(self, user_input: str, answer: str) -> str:
        text = (answer or "").strip()
        if not text:
            logger.warning("Empty final answer; substituting a fallback message")
            return (
                "I wasn't able to produce a response to that. "
                "Could you rephrase or add a little more detail?"
            )
        return text
