"""Test D-25 LIFO unwind (SC-6): jobs.__aexit__ runs BEFORE sessions.__aexit__."""
from __future__ import annotations

import os

import pytest

from mcp_gateway import jobs as jobs_mod
from mcp_gateway import sessions as sessions_mod
from mcp_gateway import session_state


@pytest.mark.asyncio
async def test_lifo_unwind_jobs_then_sessions(monkeypatch, tmp_path):
    """SC-6: BackgroundJobRegistry.__aexit__ runs BEFORE SessionRegistry.__aexit__.

    Use MCP_GATEWAY_SKIP_BACKEND=1 to avoid backend dependency. Instrument the
    two registry classes' __aexit__ methods to append the order to a shared list.
    """
    monkeypatch.setenv("MCP_GATEWAY_SKIP_BACKEND", "1")
    # Redirect token file to tmp (default /agent/.mcp-gateway-token is not writable on host)
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / "tok"))

    unwind_order: list[str] = []

    real_jobs_aexit = jobs_mod.BackgroundJobRegistry.__aexit__
    real_sessions_aexit = sessions_mod.SessionRegistry.__aexit__

    async def _instr_jobs_aexit(self, exc_type, exc, tb):
        unwind_order.append("jobs.__aexit__")
        return await real_jobs_aexit(self, exc_type, exc, tb)

    async def _instr_sessions_aexit(self, exc_type, exc, tb):
        unwind_order.append("sessions.__aexit__")
        return await real_sessions_aexit(self, exc_type, exc, tb)

    monkeypatch.setattr(jobs_mod.BackgroundJobRegistry, "__aexit__", _instr_jobs_aexit)
    monkeypatch.setattr(sessions_mod.SessionRegistry, "__aexit__", _instr_sessions_aexit)

    # Build the app and exercise its lifespan.
    from mcp_gateway.app import build_app

    app = build_app()
    inside_state = {}

    async with app.router.lifespan_context(app):
        inside_state["JOB_REGISTRY"] = session_state.JOB_REGISTRY
        inside_state["SESSION_REGISTRY"] = session_state.SESSION_REGISTRY

    # Inside lifespan: both slots populated.
    assert inside_state["JOB_REGISTRY"] is not None
    assert inside_state["SESSION_REGISTRY"] is not None

    # After lifespan exits: both slots cleared.
    assert session_state.JOB_REGISTRY is None
    assert session_state.SESSION_REGISTRY is None

    # LIFO unwind order asserted.
    assert unwind_order == ["jobs.__aexit__", "sessions.__aexit__"], (
        f"unexpected unwind order: {unwind_order}"
    )
