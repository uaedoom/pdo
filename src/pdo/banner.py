"""Pixel-art logo for the startup splash screen.

Each letter is a small bitmap (1 = filled pixel). Pixels are drawn as a pair of
block characters (``██``) so they look roughly square in a terminal, where
character cells are taller than they are wide.
"""
from __future__ import annotations

# 4-wide x 5-tall bitmaps for the letters we need.
_LETTERS: dict[str, list[str]] = {
    "P": [
        "1111",
        "1001",
        "1111",
        "1000",
        "1000",
    ],
    "D": [
        "1110",
        "1001",
        "1001",
        "1001",
        "1110",
    ],
    "O": [
        "1111",
        "1001",
        "1001",
        "1001",
        "1111",
    ],
}

_ON = "██"
_OFF = "  "
_ROWS = 5


def render_logo(word: str = "PDO", gap: str = "  ") -> str:
    """Render ``word`` as multi-line pixel-block art.

    Raises:
        KeyError: if a character in ``word`` has no defined bitmap.
    """
    lines = ["" for _ in range(_ROWS)]
    last = len(word) - 1
    for index, char in enumerate(word):
        bitmap = _LETTERS[char.upper()]
        for row in range(_ROWS):
            lines[row] += "".join(_ON if pixel == "1" else _OFF for pixel in bitmap[row])
            if index != last:
                lines[row] += gap
    return "\n".join(lines)
