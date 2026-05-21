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

    Phase 9 additions (D-05):
      - jobs.register(mcp): start_tool_job, get_tool_job, cancel_tool_job,
        list_tool_jobs (4 background-job tools). Lifespan owns the
        BackgroundJobRegistry; this module only registers the MCP surface.

    Phase 10 additions (D-20):
      - extract.register(mcp): run_binwalk, run_unblob, run_upx_test, run_upx_list,
        run_upx_unpack, list_extracted_files, promote_extracted_sample (7 extraction tools).
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
        jobs,             # Phase 9 D-05
        extract,          # Phase 10 D-20
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
    jobs.register(mcp)         # Phase 9 D-05 -- 4 tools: start/get/cancel/list_tool_jobs
    extract.register(mcp)      # Phase 10 D-20 -- 7 tools: run_binwalk, run_unblob, run_upx_{test,list,unpack}, list_extracted_files, promote_extracted_sample
    # Phase 11 D-DYN-IMPORT-01: env-gated conditional registration of dynamic-mode surface.
    # When MCP_GATEWAY_DYNAMIC_TOOLS=1, tools/dynamic.py is imported (which transitively
    # imports mcp_gateway.dynamic, registering 3 JobToolSpecs via register_job_tool at
    # module import time). When unset, neither the 7 tools nor the 3 specs leak.
    # Placed AFTER jobs.register/extract.register so dynamic JobToolSpecs enter a
    # populated JOB_TOOL_REGISTRY, and BEFORE backend_passthrough so the merged
    # tools/list handler sees the gateway-native surface first.
    import os as _os
    if _os.environ.get("MCP_GATEWAY_DYNAMIC_TOOLS") == "1":
        from . import dynamic as dynamic_tools
        dynamic_tools.register(mcp)
    # Phase 13 D-10: env-gated unsafe-r2 tool registration.
    # When MCP_GATEWAY_R2_UNSAFE_ALLOWED=1, open_r2_session_unsafe is registered.
    # Unsafe tool calls _open_r2 with sandbox=False (Plan 03 driver kwarg);
    # WARN-level log on every open (Plan 04 D-11). Tool count delta: +1 per
    # unsafe-allowed env. Total surface: 54/55 baseline; 61/62 with dynamic.
    if _os.environ.get("MCP_GATEWAY_R2_UNSAFE_ALLOWED") == "1":
        r2_sessions.register_unsafe(mcp)
    backend_passthrough.register(mcp)
    # collision_check has no register(); its assert_no_collisions(mcp) is invoked
    # from app.py::lifespan AFTER PinnedBackend's __aenter__ populates tool_cache.
