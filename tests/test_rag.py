"""Tests for the BM25 codebase index and the codebase_search tool."""
from __future__ import annotations

import pytest

from pdo.rag import build_index, load_index, search, tokenize
from pdo.tools.rag import CodebaseSearchTool


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    # Keep index files out of the real PDO_HOME.
    monkeypatch.setenv("PDO_HOME", str(tmp_path / "home"))


def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def validate_password(password):\n"
        "    \"\"\"Check password strength for user login.\"\"\"\n"
        "    return len(password) >= 8\n"
    )
    (repo / "billing.py").write_text(
        "def charge_invoice(amount):\n"
        "    \"\"\"Charge the customer's saved card.\"\"\"\n"
        "    return amount * 1.05\n"
    )
    (repo / "README.md").write_text("# Demo\nA sample project about payments.\n")
    (repo / ".venv").mkdir()
    (repo / ".venv" / "junk.py").write_text("should_not_be_indexed = True\n")
    return repo


def test_tokenize_splits_identifiers():
    tokens = tokenize("validatePassword do_thing HTTPServer")
    assert "validatepassword" in tokens and "validate" in tokens and "password" in tokens
    assert "do" in tokens and "thing" in tokens
    assert "server" in tokens


def test_build_and_search_finds_relevant_chunk(tmp_path):
    repo = _make_repo(tmp_path)
    index = build_index(repo)

    paths = {chunk.path for chunk in index.chunks}
    assert "auth.py" in paths and "billing.py" in paths
    assert not any(".venv" in path for path in paths)  # noise dirs skipped

    results = search(index, "password validation login", top_k=2)
    assert results and results[0].chunk.path == "auth.py"


def test_index_round_trips_via_disk(tmp_path):
    repo = _make_repo(tmp_path)
    built = build_index(repo)
    loaded = load_index(repo)
    assert loaded is not None
    assert len(loaded.chunks) == len(built.chunks)
    assert loaded.root == str(repo.resolve())


def test_tool_auto_builds_and_reports_refs(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path)
    monkeypatch.chdir(repo)

    out = CodebaseSearchTool().run(query="charge the customer card invoice")

    assert "billing.py:1-" in out
    assert "charge_invoice" in out


def test_tool_handles_empty_directory(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    assert "index is empty" in CodebaseSearchTool().run(query="anything")


def test_search_no_hits(tmp_path):
    repo = _make_repo(tmp_path)
    index = build_index(repo)
    assert search(index, "zzzqqqxxx nonexistent", top_k=3) == []
