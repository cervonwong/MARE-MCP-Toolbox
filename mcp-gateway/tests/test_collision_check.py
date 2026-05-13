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
    """D-13 / D-15: one colliding tool -> SystemExit(78) (EX_CONFIG)."""
    import mcp.types as mt
    from mcp.server.fastmcp import FastMCP
    from mcp_gateway import session_state
    from mcp_gateway.tools import register_all_tools
    from mcp_gateway.tools.collision_check import assert_no_collisions

    class _Stub:
        tool_cache = {
            "run_xxd": mt.Tool(name="run_xxd", description="bad", inputSchema={"type": "object"}),
        }
        backend_name = "stub-evil"

    monkeypatch.setattr(session_state, "PINNED_BACKEND", _Stub())
    mcp = FastMCP("test-collide-1")
    register_all_tools(mcp)
    with pytest.raises(SystemExit) as exc:
        await assert_no_collisions(mcp)
    assert exc.value.code == 78


async def test_assert_no_collisions_multiple_overlap(monkeypatch, caplog) -> None:
    """D-15: multi-collision error message lists ALL names sorted deterministically."""
    import logging
    import mcp.types as mt
    from mcp.server.fastmcp import FastMCP
    from mcp_gateway import session_state
    from mcp_gateway.tools import register_all_tools
    from mcp_gateway.tools.collision_check import assert_no_collisions

    class _Stub:
        tool_cache = {
            "run_xxd": mt.Tool(name="run_xxd", description="x", inputSchema={"type": "object"}),
            "run_file": mt.Tool(name="run_file", description="x", inputSchema={"type": "object"}),
            "run_die":  mt.Tool(name="run_die",  description="x", inputSchema={"type": "object"}),
        }
        backend_name = "stub-multi"

    monkeypatch.setattr(session_state, "PINNED_BACKEND", _Stub())
    mcp = FastMCP("test-collide-multi")
    register_all_tools(mcp)
    caplog.set_level(logging.ERROR, logger="mcp_gateway.collision_check")
    with pytest.raises(SystemExit):
        await assert_no_collisions(mcp)
    # All three names appear; sorted ascending
    msgs = " ".join(r.message for r in caplog.records)
    idx_die = msgs.find("run_die")
    idx_file = msgs.find("run_file")
    idx_xxd = msgs.find("run_xxd")
    assert -1 < idx_die < idx_file < idx_xxd, (
        f"D-15: collision names must appear sorted in message, got order {idx_die},{idx_file},{idx_xxd}; full: {msgs!r}"
    )
