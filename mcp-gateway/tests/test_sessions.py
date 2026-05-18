"""Phase 8 RED stubs — registry/reaper/cap/dangerous-cmd-regex/lifespan internals.

All tests import `mcp_gateway.sessions` at function top so collection passes
but execution ImportErrors until Plan 02 creates the module. pytest.skip is
forbidden in this file — the import-failure IS the RED state.
"""
from __future__ import annotations

import asyncio
import os
import re
import signal
import time
from pathlib import Path

import pytest


# ============================================================================
# SESS-04 reaper — D-14 env-var override + D-17 algorithm
# ============================================================================
@pytest.mark.asyncio
async def test_reaper_kills_idle(tmp_path, monkeypatch):
    """SESS-04: idle session reaped within idle_s + reaper_interval_s."""
    monkeypatch.setenv("MCP_GATEWAY_SESSION_IDLE_S", "2")
    monkeypatch.setenv("MCP_GATEWAY_REAPER_INTERVAL_S", "1")
    from mcp_gateway import sessions  # RED until Plan 02
    # Plan 05 fills body: open session, sleep 4s, assert list() empty, assert PID dead
    assert hasattr(sessions, "SessionRegistry")


# ============================================================================
# SESS-04 cap-reject — D-18 error dict shape
# ============================================================================
@pytest.mark.asyncio
async def test_cap_reject(tmp_path, monkeypatch):
    """SESS-04 + D-18: open N+1 returns {error: 'session cap reached', ...}."""
    monkeypatch.setenv("MCP_GATEWAY_MAX_SESSIONS", "2")
    from mcp_gateway import sessions  # RED until Plan 02
    # Plan 05 fills body: open 2 sessions, open 3rd → returns dict with error key
    assert hasattr(sessions, "SessionRegistry")


# ============================================================================
# SESS-04 lifespan-teardown kills every open r2 PID
# ============================================================================
@pytest.mark.asyncio
async def test_lifespan_teardown_kills_all(tmp_path):
    """SESS-04: SessionRegistry.__aexit__ killpg's every session."""
    from mcp_gateway import sessions  # RED until Plan 02
    # Plan 05 fills body: async with SessionRegistry(...) as reg: open 2 sessions;
    # collect PIDs; exit context; assert os.kill(pid, 0) raises ProcessLookupError for both.
    assert hasattr(sessions, "SessionRegistry")


# ============================================================================
# D-08 _DANGEROUS_R2_CMD_RE — module-level compiled regex
# ============================================================================
def test_dangerous_regex_present():
    """D-08: sessions._DANGEROUS_R2_CMD_RE compiled at module import."""
    from mcp_gateway import sessions  # RED until Plan 02
    assert hasattr(sessions, "_DANGEROUS_R2_CMD_RE")
    rx = sessions._DANGEROUS_R2_CMD_RE
    assert isinstance(rx, re.Pattern)


def test_dangerous_regex_matches_matrix():
    """D-08 + D-09: full-string regex catches compound + pipe + newline shell-escape."""
    from mcp_gateway import sessions  # RED until Plan 02
    rx = sessions._DANGEROUS_R2_CMD_RE
    # Positive (must match):
    for bad in ("!ls", "#!python print(1)", "R!whoami", "pdf ; !ls",
                "aflj | !cat /etc/passwd", "?e foo\n!ls"):
        assert rx.search(bad) is not None, f"expected match for {bad!r}"
    # Negative (must NOT match):
    for ok in ("pi 10", "?V", "pdf @ sym.foo", "aaa ; afl", "aflj"):
        assert rx.search(ok) is None, f"unexpected match for {ok!r}"


# ============================================================================
# D-14 env-var sanity check — RuntimeError on bad values
# ============================================================================
def test_env_var_bad_value_raises(monkeypatch):
    """D-14: MCP_GATEWAY_SESSION_IDLE_S=-5 raises RuntimeError at module import."""
    monkeypatch.setenv("MCP_GATEWAY_SESSION_IDLE_S", "-5")
    # Force re-import:
    import importlib
    from mcp_gateway import sessions  # RED until Plan 02
    with pytest.raises(RuntimeError):
        importlib.reload(sessions)


# ============================================================================
# D-15 R2Session dataclass shape
# ============================================================================
def test_r2session_dataclass_fields():
    """D-15: R2Session has the locked field set."""
    from mcp_gateway import sessions  # RED until Plan 02
    import dataclasses
    assert dataclasses.is_dataclass(sessions.R2Session)
    names = {f.name for f in dataclasses.fields(sessions.R2Session)}
    required = {"session_id", "case_dir", "sample_sha256", "sample_path",
                "proc", "pgid", "lock", "sentinel", "transcript_path",
                "opened_at", "opened_iso", "last_used_at",
                "command_count", "closed", "close_reason"}
    assert required.issubset(names), f"missing fields: {required - names}"


# ============================================================================
# D-29 EXPANDED_CASE_SUBDIRS regression (the catch-Phase-8-revert test)
# ============================================================================
def test_expanded_case_subdirs_contains_r2_sessions():
    """D-26 / D-29: r2-sessions entry exists in the catalog."""
    from mcp_gateway.artifacts_io import EXPANDED_CASE_SUBDIRS
    assert "r2-sessions" in EXPANDED_CASE_SUBDIRS, \
        f"Phase 8 D-26 reverted: {EXPANDED_CASE_SUBDIRS!r}"
