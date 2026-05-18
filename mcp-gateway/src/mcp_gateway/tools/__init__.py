"""Tool registration entry point. register_all_tools(mcp) registers gateway tools."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_all_tools(mcp: FastMCP) -> None:
    """Register gateway-native tools and backend-native pass-through handlers.

    Ordering mirrors D-01..D-04 (composite + atomic + disasm + case/sample mgmt).
    Backend-native tools are merged dynamically in the tools/list handler when a
    pinned backend is active.

    Phase 7 additions (D-16):
      - shell.register(mcp): run_shell
      - re_static.register(mcp): 11 typed static-RE wrappers
      - re_artifacts.register(mcp): 5 artifact-control helpers
      - tools.collision_check is imported (no register) so the module is loaded
        when register_all_tools runs; app.py::lifespan calls assert_no_collisions(mcp).

    Phase 8 additions (D-05):
      - r2_sessions.register(mcp): open_r2_session, r2_cmd,
        close_r2_session, list_sessions (4 session-scoped r2 tools).
    """
    # Imports inside the function avoid import-cycle risk during FastMCP module
    # discovery and keep the function as the single registration seam.
    from . import (
        cases,
        artifacts,
        workflows,
        disasm,
        resources,
        backend_passthrough,
        shell,            # Phase 7 D-16
        re_static,        # Phase 7 D-16
        re_artifacts,     # Phase 7 D-16
        r2_sessions,      # Phase 8 D-05
        collision_check,  # Phase 7 D-11 (imported; assert_no_collisions called from app.py)
    )  # noqa: F401
    cases.register(mcp)
    artifacts.register(mcp)
    workflows.register(mcp)
    disasm.register(mcp)
    resources.register(mcp)
    # Phase 7 D-16 — register BEFORE backend_passthrough so the merged tools/list
    # handler sees the gateway-native surface first. Order within this trio is alphabetical.
    re_artifacts.register(mcp)
    re_static.register(mcp)
    shell.register(mcp)
    r2_sessions.register(mcp)  # Phase 8 D-05
    backend_passthrough.register(mcp)
    # collision_check has no register(); its assert_no_collisions(mcp) is invoked
    # from app.py::lifespan AFTER PinnedBackend's __aenter__ populates tool_cache.
