"""Tests for skill loading and rendering."""
from __future__ import annotations

from pdo.skills import load_skills


def test_skill_with_description_and_args(tmp_path):
    (tmp_path / "review.md").write_text(
        "description: Review the code\nLook at the project.\n\n{{args}}"
    )
    skills = load_skills(tmp_path)

    assert "review" in skills
    skill = skills["review"]
    assert skill.description == "Review the code"
    assert "the auth module" in skill.render("the auth module")
    assert "{{args}}" not in skill.render("anything")


def test_skill_title_heading_as_description(tmp_path):
    (tmp_path / "explain.md").write_text("# Explain this repo\nExplain the architecture.")
    skills = load_skills(tmp_path)
    assert skills["explain"].description == "Explain this repo"


def test_skill_without_args_placeholder_appends(tmp_path):
    (tmp_path / "commit.md").write_text("description: d\nWrite a commit message.")
    rendered = load_skills(tmp_path)["commit"].render("for the parser change")
    assert rendered.endswith("for the parser change")
    assert "Write a commit message." in rendered


def test_missing_skills_dir(tmp_path):
    assert load_skills(tmp_path / "nope") == {}
