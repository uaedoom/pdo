"""Tests for the Phase-1 capability tools (offline ones)."""
from __future__ import annotations

import sqlite3
import subprocess

from pdo.tools.code import PythonExecTool
from pdo.tools.data import SqliteQueryTool
from pdo.tools.edit import EditFileTool
from pdo.tools.git import GitTool
from pdo.tools.search import GlobTool, GrepTool
from pdo.tools.web import _ddg_unwrap, _html_to_text, _parse_ddg_results


def test_glob_finds_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "b.txt").write_text("hi")
    out = GlobTool().run(pattern="**/*.py", path=str(tmp_path))
    assert "a.py" in out and "b.txt" not in out


def test_grep_matches_content(tmp_path):
    (tmp_path / "code.py").write_text("def hello():\n    return 42\n")
    out = GrepTool().run(pattern=r"return \d+", path=str(tmp_path))
    assert "code.py:2:" in out and "return 42" in out


def test_grep_invalid_regex(tmp_path):
    assert "Invalid regular expression" in GrepTool().run(pattern="(", path=str(tmp_path))


def test_edit_unique_replacement(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "f.txt"
    f.write_text("alpha beta gamma")
    out = EditFileTool(confirm=lambda _p: True).run(
        path=str(f), old_string="beta", new_string="DELTA"
    )
    assert "1 replacement" in out
    assert f.read_text() == "alpha DELTA gamma"


def test_edit_non_unique_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "f.txt"
    f.write_text("x x x")
    out = EditFileTool(confirm=lambda _p: True).run(path=str(f), old_string="x", new_string="y")
    assert "not unique" in out
    assert f.read_text() == "x x x"  # unchanged


def test_python_exec_runs_code():
    out = PythonExecTool().run(code="print(6 * 7)")
    assert "42" in out and "[exit 0]" in out


def test_sqlite_query(tmp_path):
    db = tmp_path / "test.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t (id INTEGER, name TEXT)")
    con.execute("INSERT INTO t VALUES (1, 'pdo')")
    con.commit()
    con.close()
    out = SqliteQueryTool().run(db_path=str(db), query="SELECT name FROM t WHERE id = 1")
    assert "pdo" in out


def test_git_status_in_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    out = GitTool().run(args="status --short")
    assert "[exit 0]" in out


def test_web_helpers_parse():
    assert _html_to_text("<b>Hello</b> &amp; bye") == "Hello & bye"
    assert _ddg_unwrap("//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com") == "https://example.com"
    markup = '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fa.com">Title A</a>'
    results = _parse_ddg_results(markup, 5)
    assert results == [("Title A", "https://a.com")]
