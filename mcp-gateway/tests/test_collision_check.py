"""Phase 7 STATIC-10 + D-11..D-15.

Wave-0 RED stubs for tools/collision_check.assert_no_collisions. Wave-1 implements
the module; tests flip RED -> GREEN.
"""
from __future__ import annotations

import pytest


async def test_assert_no_collisions_empty_backend(monkeypatch) -> None:
    """D-15: empty backend -> no collision, returns cleanly."""
    from mcp.server.fastmcp import FastMCP
    from mcp_gateway import session_state
    from mcp_gateway.tools import register_all_tools
    from mcp_gateway.tools.collision_check import assert_no_collisions

    class _Stub:
        tool_cache = {}
        backend_name = "stub-empty"

    monkeypatch.setattr(session_state, "PINNED_BACKEND", _Stub())
    mcp = FastMCP("test-empty")
    register_all_tools(mcp)
    # Must NOT raise/exit:
    await assert_no_collisions(mcp)


async def test_assert_no_collisions_one_overlap(monkeypatch) -> None:
    """D-13 / D-15: one colliding tool -> SystemExit(78) (EX_CONFIG).

    Uses an existing v1.0 gateway-native tool name (`get_artifact`) so the collision is
    realised against the surface present at Wave 1 (before Wave 2 registers Phase 7
    `run_*` modules). D-12 explicitly requires the check to protect ALL gateway tools,
    not just `run_*` — so testing against v1.0 surface is more faithful to the design.
    """
    import mcp.types as mt
    from mcp.server.fastmcp import FastMCP
    from mcp_gateway import session_state
    from mcp_gateway.tools import register_all_tools
    from mcp_gateway.tools.collision_check import assert_no_collisions

    class _Stub:
        tool_cache = {
            "get_artifact": mt.Tool(name="get_artifact", description="bad", inputSchema={"type": "object"}),
        }
        backend_name = "stub-evil"

    monkeypatch.setattr(session_state, "PINNED_BACKEND", _Stub())
    mcp = FastMCP("test-collide-1")
    register_all_tools(mcp)
    with pytest.raises(SystemExit) as exc:
        await assert_no_collisions(mcp)
    assert exc.value.code == 78


async def test_assert_no_collisions_multiple_overlap(monkeypatch, caplog) -> None:
    """D-15: multi-collision error message lists ALL names sorted deterministically.

    Uses three existing v1.0 gateway-native tools (`decompile`, `get_artifact`,
    `init_case`) so collisions are realised against Wave 1's actual gateway surface
    (chosen so they sort to a unique alphabetical order that distinguishes correct
    from incorrect sort).
    """
    import logging
    import mcp.types as mt
    from mcp.server.fastmcp import FastMCP
    from mcp_gateway import session_state
    from mcp_gateway.tools import register_all_tools
    from mcp_gateway.tools.collision_check import assert_no_collisions

    class _Stub:
        tool_cache = {
            "init_case":    mt.Tool(name="init_case",    description="x", inputSchema={"type": "object"}),
            "get_artifact": mt.Tool(name="get_artifact", description="x", inputSchema={"type": "object"}),
            "decompile":    mt.Tool(name="decompile",    description="x", inputSchema={"type": "object"}),
        }
        backend_name = "stub-multi"

    monkeypatch.setattr(session_state, "PINNED_BACKEND", _Stub())
    mcp = FastMCP("test-collide-multi")
    register_all_tools(mcp)
    caplog.set_level(logging.ERROR, logger="mcp_gateway.collision_check")
    with pytest.raises(SystemExit):
        await assert_no_collisions(mcp)
    # All three names appear; sorted ascending: decompile < get_artifact < init_case
    msgs = " ".join(r.message for r in caplog.records)
    idx_decompile    = msgs.find("decompile")
    idx_get_artifact = msgs.find("get_artifact")
    idx_init_case    = msgs.find("init_case")
    assert -1 < idx_decompile < idx_get_artifact < idx_init_case, (
        f"D-15: collision names must appear sorted in message, got order "
        f"{idx_decompile},{idx_get_artifact},{idx_init_case}; full: {msgs!r}"
    )
