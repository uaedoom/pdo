"""Shell execution tool with a configurable dangerous-command detector.

The detector is a pure function (:func:`is_dangerous`) so it can be unit tested
in isolation. Anything it flags requires an explicit, typed confirmation before
the command runs.
"""
from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Callable, Sequence
from typing import Any

from .base import Tool, default_confirm
from .registry import register_tool

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60

# Exact substrings that are unambiguously destructive. Kept separate from the
# regex patterns so operators can extend either independently.
DEFAULT_DENYLIST: tuple[str, ...] = (
    "rm -rf /",
    "rm -rf /*",
    ":(){:|:&};:",
    "mkfs",
    "dd if=",
    "> /dev/sda",
)

# (pattern, human-readable reason) pairs describing dangerous command shapes.
DANGEROUS_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\brm\b\s+(?:-\S+\s+)*-\S*r", "recursive delete (rm -r)"),
    (r"\brm\b.*\*", "wildcard delete (rm ... *)"),
    (r"\bsudo\b", "elevated privileges (sudo)"),
    (r"\bshutdown\b", "system shutdown"),
    (r"\breboot\b", "system reboot"),
    (r"\bhalt\b", "system halt"),
    (r"\bmkfs\b", "disk format (mkfs)"),
    (r"\bfdisk\b", "disk partitioning (fdisk)"),
    (r"\bmkswap\b", "swap creation (mkswap)"),
    (r"\bdd\b\s+if=", "raw disk write (dd)"),
    (r":\(\)\s*\{.*\}\s*;\s*:", "fork bomb"),
    (r">\s*/dev/sd[a-z]", "writing to a disk device"),
    (r"\bchmod\b\s+-R\s+0?00", "recursive permission wipe (chmod -R 000)"),
)


def is_dangerous(
    command: str, denylist: Sequence[str] | None = None
) -> tuple[bool, str | None]:
    """Classify ``command`` as dangerous or not.

    Returns a ``(dangerous, reason)`` tuple. The reason is a short, human-
    readable explanation suitable for a confirmation prompt.
    """
    text = command.strip()
    lowered = text.lower()

    for token in (denylist if denylist is not None else DEFAULT_DENYLIST):
        if token.lower() in lowered:
            return True, f"matches denylist entry {token!r}"

    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, text):
            return True, reason

    return False, None


@register_tool
class ShellTool(Tool):
    name = "run_shell"
    description = (
        "Run a shell command and return its combined stdout/stderr and exit "
        "code. Commands detected as dangerous require explicit user "
        "confirmation before they run."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute."},
            "timeout": {
                "type": "integer",
                "description": f"Maximum seconds to wait (default {DEFAULT_TIMEOUT}).",
            },
        },
        "required": ["command"],
    }

    def __init__(
        self,
        confirm: Callable[[str], bool] = default_confirm,
        denylist: Sequence[str] | None = None,
    ) -> None:
        self._confirm = confirm
        self._denylist = denylist

    def run(self, command: str, timeout: int = DEFAULT_TIMEOUT, **_: Any) -> str:
        dangerous, reason = is_dangerous(command, self._denylist)
        if dangerous:
            logger.warning("Dangerous command requested (%s): %s", reason, command)
            if not self._confirm(
                f"DANGEROUS command detected — {reason}:\n  {command}\nProceed?"
            ):
                return "Cancelled: dangerous command was not confirmed by the user."

        try:
            completed = subprocess.run(
                command,
                shell=True,  # noqa: S602 — running shell commands is this tool's purpose
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {timeout}s."
        except Exception as exc:  # noqa: BLE001 — never crash the agent loop
            logger.exception("Shell command failed to start")
            return f"Error: could not run command: {exc}"

        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        return f"[exit {completed.returncode}]\n{output or '(no output)'}"
