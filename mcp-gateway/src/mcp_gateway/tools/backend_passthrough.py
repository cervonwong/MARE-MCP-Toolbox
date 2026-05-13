"""Backend-native MCP tool pass-through.

The gateway has its own curated tools, but a pinned disassembler backend may
also expose a larger native MCP surface. This module replaces FastMCP's default
tools/list and tools/call handlers with handlers that merge the gateway-native
surface with the active backend's native tools.

Conflict policy (Phase 7 D-14 -- REVERSES v1.0 "backend wins"):
  Tool-name collisions between gateway-native tools and the active backend are
  REFUSED at gateway lifespan startup. See `tools/collision_check.py`. If startup
  succeeds, the runtime dispatcher below is guaranteed to see disjoint name sets;
  the "if pinned and name in backend_tools" branch is reachable only for
  unambiguously backend-owned names. No semantic change post-startup.

  Rationale: v1.0's "backend wins" allowed a future backend (e.g., IDA Pro
  shipping its own `decompile` tomorrow) to silently shadow our curated tools.
  Phase 7 prefers a loud config-error (exit code 78) over silent functional
  regression -- operators get an actionable message before the first MCP call.
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
import mcp.types as mcp_types

from .. import session_state


def _backend_tool_map() -> dict[str, mcp_types.Tool]:
    pinned = session_state.PINNED_BACKEND
    return getattr(pinned, "tool_cache", {}) or {}


async def refresh_backend_tools() -> list[mcp_types.Tool]:
    """Refresh and return the active backend's native tool definitions."""
    pinned = session_state.PINNED_BACKEND
    if pinned is None or not hasattr(pinned, "list_tools"):
        return []
    tools = await pinned.list_tools()
    pinned.tool_cache = {tool.name: tool for tool in tools}
    return tools


def register(mcp: FastMCP) -> None:
    """Register merged tools/list and tools/call handlers."""

    @mcp._mcp_server.list_tools()
    async def list_gateway_and_backend_tools() -> list[mcp_types.Tool]:
        gateway_tools = await mcp.list_tools()
        by_name = {tool.name: tool for tool in gateway_tools}
        for tool in await refresh_backend_tools():
            by_name[tool.name] = tool
        return list(by_name.values())

    @mcp._mcp_server.call_tool(validate_input=True)
    async def call_gateway_or_backend_tool(
        name: str,
        arguments: dict[str, Any],
    ):
        backend_tools = _backend_tool_map()
        pinned = session_state.PINNED_BACKEND
        if pinned is not None and name not in backend_tools:
            backend_tools = {tool.name: tool for tool in await refresh_backend_tools()}
        if pinned is not None and name in backend_tools:
            return await pinned.call(name, arguments)
        return await mcp.call_tool(name, arguments)
