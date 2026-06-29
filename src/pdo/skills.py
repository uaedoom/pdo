"""User-defined skills: reusable prompt templates invoked as slash commands.

Each ``.md`` file in the skills directory becomes a slash command named after the
file (``review.md`` → ``/review``). The file body is a prompt template; an
optional first line ``description: ...`` or ``# Title`` sets the menu description.
Use ``{{args}}`` in the template to interpolate whatever the user types after the
command (otherwise their text is appended).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    name: str  # slash command name without the leading "/"
    description: str
    template: str

    def render(self, args: str) -> str:
        """Produce the prompt to send, substituting the user's arguments."""
        if "{{args}}" in self.template:
            return self.template.replace("{{args}}", args)
        return self.template if not args else f"{self.template}\n\n{args}"


def load_skills(skills_dir: Path) -> dict[str, Skill]:
    """Load every ``*.md`` skill file from ``skills_dir`` (name → Skill)."""
    skills: dict[str, Skill] = {}
    if not skills_dir.exists():
        return skills
    for path in sorted(skills_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Could not read skill %s", path)
            continue
        name = path.stem.lower().lstrip("/")
        description, template = _parse_skill(text, name)
        skills[name] = Skill(name=name, description=description, template=template)
    return skills


def _parse_skill(text: str, name: str) -> tuple[str, str]:
    lines = text.splitlines()
    description = f"Custom skill: {name}"
    if lines:
        first = lines[0].strip()
        if first.lower().startswith("description:"):
            description = first.split(":", 1)[1].strip() or description
            return description, "\n".join(lines[1:]).strip()
        if first.startswith("# "):
            description = first[2:].strip() or description
            return description, "\n".join(lines[1:]).strip()
    return description, text.strip()
