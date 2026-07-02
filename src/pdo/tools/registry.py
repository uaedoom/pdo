"""The single tool registry.

Tools auto-register here via the :func:`register_tool` class decorator when
their module is imported. :func:`get_registry` lazily imports the built-in tool
modules the first time it is called, so the rest of the app only ever sees a
fully populated registry and never imports individual tools.
"""
from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from threading import Lock

from .base import Tool

logger = logging.getLogger(__name__)

# Entry-point group third-party packages can register tools under.
PLUGIN_ENTRYPOINT_GROUP = "pdo.plugins"

# Names of tools that were added by plugins (for display/introspection).
_plugin_tool_names: list[str] = []


class ToolRegistry:
    """An ordered collection of tools keyed by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ValueError(f"{type(tool).__name__} must define a non-empty 'name'")
        if tool.name in self._tools:
            logger.warning("Overwriting already-registered tool %r", tool.name)
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(name)
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self) -> list[dict]:
        """Return every tool's JSON schema for the model's ``tools`` parameter."""
        return [tool.to_openai_schema() for tool in self._tools.values()]


# Module-level singleton. Tools register into this instance at import time.
_registry = ToolRegistry()
_loaded = False
_load_lock = Lock()


def register_tool(cls: type[Tool]) -> type[Tool]:
    """Class decorator: instantiate a ``Tool`` subclass and register it.

    Subclasses must be constructible with no required arguments (inject
    dependencies via keyword arguments with sensible defaults).
    """
    _registry.register(cls())
    return cls


def get_registry() -> ToolRegistry:
    """Return the shared registry, importing built-in and plugin tools on first use."""
    global _loaded
    if not _loaded:
        with _load_lock:
            if not _loaded:
                # Importing these modules triggers their @register_tool decorators.
                from . import (  # noqa: F401
                    code,
                    data,
                    edit,
                    filesystem,
                    git,
                    memory,
                    rag,
                    search,
                    shell,
                    web,
                )

                load_plugins(_registry)
                _loaded = True
    return _registry


def plugin_tool_names() -> list[str]:
    """Return the names of tools contributed by plugins."""
    return list(_plugin_tool_names)


def load_plugins(registry: ToolRegistry) -> None:
    """Discover and register external tool plugins (directory + entry points)."""
    from ..config import get_plugins_dir

    try:
        discover_directory_plugins(registry, get_plugins_dir())
    except Exception:  # noqa: BLE001 — discovery must never crash startup
        logger.exception("Directory plugin discovery failed")
    try:
        discover_entrypoint_plugins(registry)
    except Exception:  # noqa: BLE001
        logger.exception("Entry-point plugin discovery failed")


def discover_directory_plugins(registry: ToolRegistry, plugins_dir: Path) -> None:
    """Import every ``*.py`` file in ``plugins_dir`` and register its tools.

    Each file is loaded in isolation; a broken plugin is logged and skipped so
    it can't take down the rest of PDO.
    """
    if not plugins_dir.exists():
        return
    for path in sorted(plugins_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            module = _import_file(path)
            _register_module_tools(registry, module)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to load plugin file %s", path)


def discover_entrypoint_plugins(registry: ToolRegistry) -> None:
    """Load tools advertised by installed packages under the plugin entry-point group.

    An entry point may resolve to a ``Tool`` subclass (registered directly) or a
    callable ``register(registry)`` that adds its own tools.
    """
    try:
        from importlib.metadata import entry_points

        eps = entry_points()
        group = (
            eps.select(group=PLUGIN_ENTRYPOINT_GROUP)
            if hasattr(eps, "select")
            else eps.get(PLUGIN_ENTRYPOINT_GROUP, [])  # Python <3.10 mapping API
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not read plugin entry points")
        return

    for entry_point in group:
        try:
            obj = entry_point.load()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to load plugin entry point %s", entry_point.name)
            continue
        _register_plugin_object(registry, obj)


def _import_file(path: Path):
    """Import a standalone .py file under a unique module name and return it."""
    name = f"pdo_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _register_module_tools(registry: ToolRegistry, module) -> None:
    """Register every concrete ``Tool`` subclass *defined in* ``module``."""
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if (
            issubclass(obj, Tool)
            and obj is not Tool
            and not inspect.isabstract(obj)
            and obj.__module__ == module.__name__  # ignore imported base/others
        ):
            _register_plugin_object(registry, obj)


def _register_plugin_object(registry: ToolRegistry, obj) -> None:
    """Register a plugin-provided Tool subclass or a register(registry) callable."""
    if inspect.isclass(obj) and issubclass(obj, Tool) and obj is not Tool:
        try:
            tool = obj()
        except Exception:  # noqa: BLE001
            logger.exception("Could not instantiate plugin tool %s", obj)
            return
        if tool.name and not registry.has(tool.name):
            registry.register(tool)
            _plugin_tool_names.append(tool.name)
            logger.info("Loaded plugin tool %r", tool.name)
    elif callable(obj):
        obj(registry)
