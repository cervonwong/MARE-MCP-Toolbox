"""Tool registration entry point. register_all_tools(mcp) registers gateway tools."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_all_tools(mcp: FastMCP) -> None:
    """Register gateway-native tools and backend-native pass-through handlers.

    Ordering mirrors D-01..D-04 (composite + atomic + disasm + case/sample mgmt).
    Backend-native tools are merged dynamically in the tools/list handler when a
    pinned backend is active.
    """
    # Imports inside the function avoid import-cycle risk during FastMCP module
    # discovery and keep the function as the single registration seam.
    from . import cases, artifacts, workflows, disasm, resources, backend_passthrough  # noqa: F401
    cases.register(mcp)
    artifacts.register(mcp)
    workflows.register(mcp)
    disasm.register(mcp)
    resources.register(mcp)
    backend_passthrough.register(mcp)
