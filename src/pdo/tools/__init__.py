"""Built-in tools.

Tool modules register themselves with the shared registry when imported. The
registry imports them lazily (see :func:`pdo.tools.registry.get_registry`), so
importing this package has no side effects beyond making the modules available.
"""
