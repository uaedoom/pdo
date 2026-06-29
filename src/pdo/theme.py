"""Color themes for the terminal UI.

A theme is just an accent color used across the splash, input box, prompt, tool
bullets and footer. The accent is exposed both as a ``rich`` color name and as a
``prompt_toolkit`` ANSI name, since the two libraries name colors differently.
"""
from __future__ import annotations

# name -> (rich color, prompt_toolkit ansi color)
THEMES: dict[str, tuple[str, str]] = {
    "cyan": ("cyan", "ansicyan"),
    "green": ("green", "ansigreen"),
    "magenta": ("magenta", "ansimagenta"),
    "amber": ("yellow", "ansiyellow"),
    "blue": ("blue", "ansiblue"),
    "mono": ("white", "ansiwhite"),
}

_DEFAULT = "cyan"
_current = _DEFAULT


def set_theme(name: str) -> bool:
    """Switch the active theme. Returns False if the name is unknown."""
    global _current
    if name in THEMES:
        _current = name
        return True
    return False


def current_theme() -> str:
    return _current


def theme_names() -> list[str]:
    return list(THEMES)


def accent() -> str:
    """The accent color as a rich color name."""
    return THEMES.get(_current, THEMES[_DEFAULT])[0]


def accent_ansi() -> str:
    """The accent color as a prompt_toolkit ANSI color name."""
    return THEMES.get(_current, THEMES[_DEFAULT])[1]
