# Contributing to PDO

Thanks for your interest in improving PDO! This guide covers local setup, the
coding standards we follow, and how to extend the agent.

## Development setup

Requires Python 3.12+.

```bash
git clone https://github.com/your-org/pdo.git
cd pdo
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the checks the CI runs:

```bash
ruff check .
pytest -q
```

The test suite **mocks the LLM**, so it runs with no API key and no network.

## Coding standards

- **Python 3.12+**, with type hints throughout.
- **Clean Architecture + SOLID**: small files, one responsibility per class.
- The **core depends only on interfaces** (`LLMClient`, `Tool`), never on
  concrete providers or specific tools.
- Use `dataclasses` for data structures.
- Use the standard `logging` module (logs go to `logs/`); never `print` for
  diagnostics — the terminal output is for the user.
- Wrap tool execution in exception handling; a tool failure must never crash the
  agent loop.
- Write docstrings, and comments that explain **why**, not what.
- Keep orchestration thin — avoid building frameworks where a function will do.

## Adding a tool

1. Create a module under `src/pdo/tools/`.
2. Subclass `Tool`, set `name`, `description`, and a JSON `parameters` schema,
   and implement `run(self, **kwargs) -> str`.
3. Decorate the class with `@register_tool`.
4. Add the module to the lazy import in `tools/registry.py:get_registry`.
5. For sensitive actions, accept an injectable `confirm` callback (see
   `tools/filesystem.py`) and require confirmation.
6. Add a unit test under `tests/`.

See the "Adding New Tools" section of the [README](README.md) for a complete
example.

## Adding an LLM provider

Implement the `LLMClient` interface in `src/pdo/llm.py` (or a new module) and
wire it up in `main.py`. Keep the agent unchanged — that's the point of the
interface.

## Pull requests

- Keep changes focused; modify only the files a change requires.
- Don't rewrite working modules unnecessarily — preserve backward compatibility.
- Update docs and tests alongside code.
- Ensure `ruff check .` and `pytest` pass.

## Commit messages

Use clear, present-tense messages (e.g. "Add web-search tool"). Reference issues
where relevant.

By contributing you agree that your contributions are licensed under the project's
[MIT License](LICENSE).
