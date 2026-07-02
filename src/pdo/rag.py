"""Lexical codebase retrieval (BM25).

``/index`` builds a chunk index of the working directory; the
``codebase_search`` tool ranks chunks against a query with BM25 and returns the
best snippets with ``path:line`` references.

We use lexical retrieval rather than embeddings on purpose: it needs no
embeddings endpoint (OpenRouter doesn't offer one), no API key, and no new
dependencies — and BM25 over code identifiers is strong in practice. Embedding
support can be layered on later without changing the tool interface.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import get_home_dir

logger = logging.getLogger(__name__)

# Files worth indexing (source + docs + config).
_INDEX_EXTS = {
    ".py", ".md", ".txt", ".rst", ".toml", ".ini", ".cfg", ".json", ".yml",
    ".yaml", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".sh", ".zsh",
    ".swift", ".rs", ".go", ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".sql",
}
_SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".ruff_cache",
    ".pytest_cache", "dist", "build", ".mypy_cache", ".idea", ".vscode",
}
_MAX_FILE_BYTES = 200_000
_CHUNK_LINES = 40
_CHUNK_OVERLAP = 10
_MAX_CHUNKS = 20_000

# BM25 constants (standard defaults).
_K1 = 1.5
_B = 0.75

_WORD = re.compile(r"[A-Za-z0-9_]+")
# Split camelCase and acronym boundaries: fooBar -> foo|Bar, HTTPServer -> HTTP|Server.
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def tokenize(text: str) -> list[str]:
    """Split text into lowercase tokens, including snake/camelCase sub-words."""
    tokens: list[str] = []
    for word in _WORD.findall(text):
        lowered = word.lower()
        tokens.append(lowered)
        parts = [p for chunk in _CAMEL.split(word) for p in chunk.split("_") if p]
        if len(parts) > 1:
            tokens.extend(p.lower() for p in parts)
    return tokens


@dataclass
class Chunk:
    path: str  # relative to the index root
    start: int  # 1-based first line
    end: int  # 1-based last line
    text: str


@dataclass
class Index:
    root: str
    built: float
    chunks: list[Chunk] = field(default_factory=list)


def _index_path(root: Path) -> Path:
    digest = hashlib.sha1(str(root.resolve()).encode()).hexdigest()[:16]
    directory = get_home_dir() / "index"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{digest}.json"


def _iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _INDEX_EXTS:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def build_index(root: Path) -> Index:
    """Chunk every indexable file under ``root`` and persist the index."""
    root = root.resolve()
    index = Index(root=str(root), built=time.time())
    for file in _iter_files(root):
        try:
            lines = file.read_text("utf-8", "ignore").splitlines()
        except OSError:
            continue
        rel = str(file.relative_to(root))
        step = _CHUNK_LINES - _CHUNK_OVERLAP
        for start in range(0, max(len(lines), 1), step):
            block = lines[start : start + _CHUNK_LINES]
            if not any(line.strip() for line in block):
                continue
            index.chunks.append(
                Chunk(path=rel, start=start + 1, end=start + len(block), text="\n".join(block))
            )
            if len(index.chunks) >= _MAX_CHUNKS:
                logger.warning("Index chunk cap reached (%d); stopping", _MAX_CHUNKS)
                save_index(index)
                return index
            if start + _CHUNK_LINES >= len(lines):
                break
    save_index(index)
    return index


def save_index(index: Index) -> None:
    payload = {
        "root": index.root,
        "built": index.built,
        "chunks": [vars(chunk) for chunk in index.chunks],
    }
    _index_path(Path(index.root)).write_text(json.dumps(payload), encoding="utf-8")


def load_index(root: Path) -> Index | None:
    path = _index_path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Index(
            root=data["root"],
            built=data["built"],
            chunks=[Chunk(**chunk) for chunk in data["chunks"]],
        )
    except (json.JSONDecodeError, KeyError, TypeError, OSError) as exc:
        logger.warning("Could not load index %s: %s", path, exc)
        return None


@dataclass
class SearchResult:
    chunk: Chunk
    score: float


def search(index: Index, query: str, top_k: int = 5) -> list[SearchResult]:
    """Rank chunks against ``query`` with BM25 and return the top ``top_k``."""
    query_tokens = set(tokenize(query))
    if not query_tokens or not index.chunks:
        return []

    token_lists = [tokenize(chunk.text) for chunk in index.chunks]
    n = len(token_lists)
    avg_len = sum(len(t) for t in token_lists) / n

    # Document frequency per query token.
    df = dict.fromkeys(query_tokens, 0)
    for tokens in token_lists:
        present = query_tokens.intersection(tokens)
        for token in present:
            df[token] += 1

    results: list[SearchResult] = []
    for chunk, tokens in zip(index.chunks, token_lists, strict=True):
        if not tokens:
            continue
        score = 0.0
        length_norm = _K1 * (1 - _B + _B * len(tokens) / avg_len)
        for token in query_tokens:
            tf = tokens.count(token)
            if tf == 0 or df[token] == 0:
                continue
            idf = math.log(1 + (n - df[token] + 0.5) / (df[token] + 0.5))
            score += idf * (tf * (_K1 + 1)) / (tf + length_norm)
        if score > 0:
            results.append(SearchResult(chunk=chunk, score=score))

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]
