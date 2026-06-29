"""Local JSON memory store.

State is split across:

* ``memory.json``        — durable facts, preferences, and the current session name.
* ``sessions/<name>.json`` — one file per named conversation: a rolling summary
  plus recent messages.

Splitting conversations into named sessions lets the user keep separate threads
(``/new``, ``/resume``) and lets the agent compress old turns into a summary so
context stays bounded. :func:`get_memory_store` returns a process-wide singleton
so the agent and the memory tools share the same data.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import get_data_dir

logger = logging.getLogger(__name__)

_DEFAULT_MEMORY: dict[str, Any] = {
    "preferences": {},
    "facts": [],
    "current_session": "default",
}
_DEFAULT_SESSION: dict[str, Any] = {"summary": "", "messages": []}


def _safe_name(name: str) -> str:
    """Sanitise a session name into a safe file stem."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name).strip("_") or "default"


class MemoryStore:
    """Read/write access to PDO's local JSON memory and named sessions."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._dir = Path(data_dir) if data_dir is not None else get_data_dir()
        self._memory_path = self._dir / "memory.json"
        self._sessions_dir = self._dir / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

        self._memory: dict[str, Any] = self._load(self._memory_path, _DEFAULT_MEMORY)
        self._current: str = self._memory.get("current_session") or "default"
        self._migrate_legacy_history()
        self._summary, self._history = self._load_session(self._current)

    # --- persistence -------------------------------------------------------- #
    def _load(self, path: Path, default: Any) -> Any:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s (%s); starting fresh", path, exc)
        return json.loads(json.dumps(default))  # deep copy

    def _save(self, path: Path, data: Any) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            logger.error("Could not write %s: %s", path, exc)

    def _session_path(self, name: str) -> Path:
        return self._sessions_dir / f"{_safe_name(name)}.json"

    def _load_session(self, name: str) -> tuple[str, list[dict[str, Any]]]:
        data = self._load(self._session_path(name), _DEFAULT_SESSION)
        if isinstance(data, list):  # tolerate an old flat-list format
            return "", data
        return data.get("summary", ""), data.get("messages", [])

    def _save_session(self) -> None:
        self._save(
            self._session_path(self._current),
            {"summary": self._summary, "messages": self._history},
        )

    def _migrate_legacy_history(self) -> None:
        """Migrate a pre-sessions history.json into the default session once."""
        legacy = self._dir / "history.json"
        default_path = self._session_path("default")
        if legacy.exists() and not default_path.exists():
            try:
                data = json.loads(legacy.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self._save(default_path, {"summary": "", "messages": data})
            except (json.JSONDecodeError, OSError):
                logger.debug("No legacy history to migrate", exc_info=True)

    # --- conversation history & summary ------------------------------------ #
    def add_message(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content, "ts": time.time()})
        self._save_session()

    def history(self, limit: int | None = None) -> list[dict[str, Any]]:
        if limit is not None and limit > 0:
            return list(self._history[-limit:])
        return list(self._history)

    def clear_history(self) -> None:
        self._history = []
        self._summary = ""
        self._save_session()

    def summary(self) -> str:
        return self._summary

    def set_summary(self, text: str) -> None:
        self._summary = text
        self._save_session()

    def replace_messages(self, messages: list[dict[str, Any]]) -> None:
        """Replace the active message list (used after summarising old turns)."""
        self._history = list(messages)
        self._save_session()

    # --- sessions ----------------------------------------------------------- #
    def current_session(self) -> str:
        return self._current

    def list_sessions(self) -> list[str]:
        names = {path.stem for path in self._sessions_dir.glob("*.json")}
        names.add(_safe_name(self._current))
        return sorted(names)

    def switch_session(self, name: str) -> str:
        self._save_session()  # persist the session we're leaving
        self._current = _safe_name(name)
        self._memory["current_session"] = self._current
        self._save(self._memory_path, self._memory)
        self._summary, self._history = self._load_session(self._current)
        return self._current

    def new_session(self, name: str | None = None) -> str:
        return self.switch_session(name or f"session-{int(time.time())}")

    # --- facts -------------------------------------------------------------- #
    def save_fact(self, text: str, tags: list[str] | None = None) -> str:
        fact_id = uuid.uuid4().hex[:8]
        self._memory.setdefault("facts", []).append(
            {"id": fact_id, "text": text, "tags": tags or [], "created": time.time()}
        )
        self._save(self._memory_path, self._memory)
        return fact_id

    def search_facts(self, query: str) -> list[dict[str, Any]]:
        needle = query.lower().strip()
        return [
            fact
            for fact in self._memory.get("facts", [])
            if needle in fact["text"].lower()
            or any(needle in tag.lower() for tag in fact.get("tags", []))
        ]

    def all_facts(self) -> list[dict[str, Any]]:
        return list(self._memory.get("facts", []))

    def delete_fact(self, fact_id: str) -> bool:
        facts = self._memory.get("facts", [])
        remaining = [fact for fact in facts if fact["id"] != fact_id]
        if len(remaining) == len(facts):
            return False
        self._memory["facts"] = remaining
        self._save(self._memory_path, self._memory)
        return True

    # --- preferences -------------------------------------------------------- #
    def get_preference(self, key: str, default: Any = None) -> Any:
        return self._memory.get("preferences", {}).get(key, default)

    def set_preference(self, key: str, value: Any) -> None:
        self._memory.setdefault("preferences", {})[key] = value
        self._save(self._memory_path, self._memory)

    def preferences(self) -> dict[str, Any]:
        return dict(self._memory.get("preferences", {}))


@lru_cache(maxsize=1)
def get_memory_store() -> MemoryStore:
    """Return the process-wide memory store (created on first call)."""
    return MemoryStore()
