"""Unified disassembler tools (3): decompile, list_functions, get_xrefs.

Delegates to session_state.PINNED_BACKEND (set by Plan 03's lifespan in app.py).
If PINNED_BACKEND is None (test mode via MCP_GATEWAY_SKIP_BACKEND=1 or no backend),
returns structured "backend not yet wired" stub.

Plan 03 wired PinnedBackend.call_unified -- the `.call_unified` method maps the
unified name to the backend's tool via tool_map.translate and returns a dict
with {unified_tool, backend, backend_tool, content, is_error}.
"""
from __future__ import annotations
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .. import session_state
from .samples import resolve_sample


def _backend_error_stub(unified: str) -> dict:
    return {
        "error": "backend not yet wired",
        "unified_tool": unified,
        "note": "Plan 03 will wire the PinnedBackend dispatch here.",
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def decompile(function: str, sample: Optional[str] = None) -> dict:
        """Decompile a function in the active/selected sample via the pinned backend."""
        if session_state.PINNED_BACKEND is None:
            return _backend_error_stub("decompile")
        sample_path = resolve_sample(sample) if sample else None
        # Plan 03 replaces this body with real tool_map.translate + backend.call dispatch.
        return await session_state.PINNED_BACKEND.call_unified(
            "decompile", {"function": function, "sample_path": sample_path}
        )

    @mcp.tool()
    async def list_functions(sample: Optional[str] = None) -> dict:
        """List all functions in the active/selected sample."""
        if session_state.PINNED_BACKEND is None:
            return _backend_error_stub("list_functions")
        sample_path = resolve_sample(sample) if sample else None
        return await session_state.PINNED_BACKEND.call_unified(
            "list_functions", {"sample_path": sample_path}
        )

    @mcp.tool()
    async def get_xrefs(function: str, sample: Optional[str] = None) -> dict:
        """List cross-references to a function in the active/selected sample."""
        if session_state.PINNED_BACKEND is None:
            return _backend_error_stub("get_xrefs")
        sample_path = resolve_sample(sample) if sample else None
        return await session_state.PINNED_BACKEND.call_unified(
            "get_xrefs", {"function": function, "sample_path": sample_path}
        )
