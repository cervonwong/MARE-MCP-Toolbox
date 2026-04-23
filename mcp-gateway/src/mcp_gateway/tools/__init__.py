"""Tool registration entry point. register_all_tools(mcp) registers all 21 tools."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_all_tools(mcp: FastMCP) -> None:
    """Register the curated 21-tool surface on a FastMCP instance.

    Ordering mirrors D-01..D-04 (composite + atomic + disasm + case/sample mgmt).
    """
    # Imports inside the function avoid import-cycle risk during FastMCP module
    # discovery and keep the function as the single registration seam.
    from . import cases, artifacts, workflows, disasm  # noqa: F401
    cases.register(mcp)
    artifacts.register(mcp)
    workflows.register(mcp)
    disasm.register(mcp)
