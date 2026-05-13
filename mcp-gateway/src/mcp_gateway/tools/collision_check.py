"""Phase 7 STATIC-10 / D-11..D-15: hard-fail at gateway lifespan startup if
gateway-native tool names overlap with the active backend's tool surface.

Reverses v1.0's "backend wins" policy stated in tools/backend_passthrough.py:8.
The runtime dispatcher in `call_gateway_or_backend_tool` is unchanged — since
startup guarantees no overlaps after this check, the "if pinned and name in
backend_tools" branch is reachable only for unambiguously backend-owned names.

Invocation site: `app.py::lifespan` AFTER `register_all_tools(mcp)` AND AFTER
`PinnedBackend.__aenter__` (which calls `refresh_backend_tools()` populating
`session_state.PINNED_BACKEND.tool_cache`). Calling before either of those two
events would see an incomplete tool set and pass spuriously (Pitfall 7).

Exit semantics: SystemExit(78) (EX_CONFIG per sysexits.h). Raising RuntimeError
from inside lifespan can be swallowed by Starlette/uvicorn translation; sys.exit
is the most reliable way to surface the EX_CONFIG code through the ASGI stack.
"""
from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from .. import session_state

log = logging.getLogger("mcp_gateway.collision_check")

# Exit code per sysexits.h(3); operator runbooks grep for this rather than reading full logs.
_EX_CONFIG = 78


async def assert_no_collisions(mcp: FastMCP) -> None:
    """Hard-fail at lifespan if gateway-native and backend tool names overlap (D-11..D-15).

    Called from app.py::lifespan AFTER register_all_tools(mcp) AND AFTER
    PinnedBackend has populated its tool_cache (i.e., after the first
    refresh_backend_tools() call), BEFORE the app starts serving.

    On collision: logs a structured error to logger 'mcp_gateway.collision_check'
    listing every colliding name sorted ascending plus the backend label, then
    calls sys.exit(78) (EX_CONFIG).

    Empty backend (tool_cache == {} or PINNED_BACKEND is None) → returns cleanly.

    Scope (D-12): ALL gateway-native tools (not just `run_*`) — protects v1.0
    surface (`init_case`, `collect_strings`, `get_artifact`, etc.) as well.
    """
    gateway_tools = await mcp.list_tools()
    gateway_names = {t.name for t in gateway_tools}

    pinned = session_state.PINNED_BACKEND
    backend_cache = getattr(pinned, "tool_cache", {}) if pinned is not None else {}
    backend_names = set((backend_cache or {}).keys())

    collisions = sorted(gateway_names & backend_names)
    if not collisions:
        return

    backend_label = getattr(pinned, "backend_name", "<unknown>") if pinned is not None else "<unknown>"
    msg = (
        f"FATAL: gateway-native tool names collide with backend "
        f"'{backend_label}': {collisions}"
    )
    log.error(msg)
    # D-13: surface EX_CONFIG through the ASGI stack reliably.
    sys.exit(_EX_CONFIG)
