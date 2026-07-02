"""Tests for @file references (text inlining + image attachment) and encoding."""
from __future__ import annotations

import base64

from pdo.agent.core import _encode_image
from pdo.main import _expand_file_refs

# 1x1 transparent PNG.
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def test_text_file_is_inlined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("secret = 42")

    text, images = _expand_file_refs("what is in @notes.txt")

    assert "secret = 42" in text
    assert images == []


def test_image_file_is_collected_not_inlined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "shot.png").write_bytes(_PNG_BYTES)

    text, images = _expand_file_refs("describe @shot.png please")

    assert text == "describe @shot.png please"  # text unchanged
    assert images == [str(tmp_path / "shot.png")]


def test_mixed_text_and_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.md").write_text("# doc")
    (tmp_path / "b.jpg").write_bytes(_PNG_BYTES)

    text, images = _expand_file_refs("see @a.md and @b.jpg")

    assert "# doc" in text
    assert images == [str(tmp_path / "b.jpg")]


def test_missing_files_are_ignored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    text, images = _expand_file_refs("look at @nope.png and @gone.txt")
    assert text == "look at @nope.png and @gone.txt"
    assert images == []


def test_encode_image_produces_data_url(tmp_path):
    file = tmp_path / "pixel.png"
    file.write_bytes(_PNG_BYTES)

    url = _encode_image(str(file))

    assert url is not None and url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == _PNG_BYTES


def test_encode_image_rejects_unknown_or_missing(tmp_path):
    (tmp_path / "notes.txt").write_text("hi")
    assert _encode_image(str(tmp_path / "notes.txt")) is None  # not an image ext
    assert _encode_image(str(tmp_path / "missing.png")) is None
