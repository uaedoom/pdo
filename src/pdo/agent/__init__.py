"""The agent package: orchestration, planning, routing, execution and memory.

Each module here is intentionally small and single-purpose. ``core.Agent`` wires
them together; nothing in this package references concrete tools directly — it
only talks to the tool registry.
"""
