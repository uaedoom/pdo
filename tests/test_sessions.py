"""Tests for named sessions and the summary store."""
from __future__ import annotations

import json

from pdo.agent.memory import MemoryStore


def test_sessions_are_isolated(tmp_path):
    store = MemoryStore(tmp_path)
    store.add_message("user", "in default")

    store.new_session("feature-x")
    assert store.current_session() == "feature-x"
    assert store.history() == []  # fresh session

    store.add_message("user", "in feature-x")
    store.switch_session("default")
    assert [m["content"] for m in store.history()] == ["in default"]

    assert set(store.list_sessions()) >= {"default", "feature-x"}


def test_summary_and_replace(tmp_path):
    store = MemoryStore(tmp_path)
    for i in range(5):
        store.add_message("user", f"msg {i}")
    store.set_summary("a summary")
    store.replace_messages(store.history()[-2:])

    assert store.summary() == "a summary"
    assert len(store.history()) == 2

    # Persisted across reloads.
    reloaded = MemoryStore(tmp_path)
    assert reloaded.summary() == "a summary"
    assert len(reloaded.history()) == 2


def test_legacy_history_is_migrated(tmp_path):
    legacy = tmp_path / "history.json"
    legacy.write_text(json.dumps([{"role": "user", "content": "old", "ts": 1.0}]))

    store = MemoryStore(tmp_path)
    assert [m["content"] for m in store.history()] == ["old"]
