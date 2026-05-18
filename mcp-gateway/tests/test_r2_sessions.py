"""Phase 8 RED stubs — MCP tool surface (open/r2_cmd/close/list).

All r2-spawning tests call _require_r2_or_skip() at body top (host without
r2 → cleanly skip). Tests that don't spawn r2 (docstring assertions,
result-shape assertions on mocked sessions) do not skip.

Imports of mcp_gateway.tools.r2_sessions at function top yield RED until
Plan 03 creates the module.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import time
from pathlib import Path

import pytest

from tests.conftest import _require_r2_or_skip


# ============================================================================
# SESS-01 — analysis state persists across calls
# ============================================================================
@pytest.mark.asyncio
async def test_aaa_aflj_persists(tmp_path):
    """SESS-01: open → r2_cmd('aaa') → r2_cmd('aflj') returns parsed JSON with functions."""
    _require_r2_or_skip()
    from mcp_gateway.tools import r2_sessions  # RED until Plan 03
    # Plan 05 fills body: open session against a fixture ELF, run aaa, run aflj with format=json,
    # assert parsed_json is a list with len >= 1.
    assert hasattr(r2_sessions, "open_r2_session")


# ============================================================================
# SESS-02 — result-dict shape (12 Phase-6 keys + 6 r2 extensions)
# ============================================================================
@pytest.mark.asyncio
async def test_r2_cmd_result_shape(tmp_path):
    """SESS-02 + D-11: all 18 keys present with correct types."""
    _require_r2_or_skip()
    from mcp_gateway.tools import r2_sessions  # RED until Plan 03
    # Plan 05 fills body: open session, r2_cmd('?V'); assert keys = base12 + 6 extensions.
    # The 18 required keys:
    required_keys = {
        # Phase 6 D-03 base (12):
        "exit_code", "timed_out", "duration_s",
        "stdout_head", "stdout_truncated", "stdout_bytes_total",
        "stderr_head", "stderr_truncated", "stderr_bytes_total",
        "log_path", "argv", "slug",
        # Phase 8 D-11 extensions (6):
        "session_id", "session_invalidated", "format",
        "parsed_json", "parse_error", "transcript_path",
    }
    assert len(required_keys) == 18
    assert hasattr(r2_sessions, "r2_cmd")


@pytest.mark.asyncio
async def test_format_json_iij(tmp_path):
    """SESS-02 + D-10: format=json on iij returns parsed_json (a dict/list)."""
    _require_r2_or_skip()
    from mcp_gateway.tools import r2_sessions  # RED until Plan 03
    assert hasattr(r2_sessions, "r2_cmd")


@pytest.mark.asyncio
async def test_format_json_non_json_command(tmp_path):
    """SESS-02 + D-10: format=json on ?V → parsed_json=None, parse_error set."""
    _require_r2_or_skip()
    from mcp_gateway.tools import r2_sessions  # RED until Plan 03
    assert hasattr(r2_sessions, "r2_cmd")


# ============================================================================
# SESS-03 — close + list
# ============================================================================
@pytest.mark.asyncio
async def test_close_idempotent(tmp_path):
    """SESS-03 + D-21: second close returns ok=True, already_closed=True."""
    _require_r2_or_skip()
    from mcp_gateway.tools import r2_sessions  # RED until Plan 03
    assert hasattr(r2_sessions, "close_r2_session")


@pytest.mark.asyncio
async def test_list_fd_count_nonneg(tmp_path):
    """SESS-03 + D-22: live session has fd_count >= 0 (or -1 if /proc unreadable)."""
    _require_r2_or_skip()
    from mcp_gateway.tools import r2_sessions  # RED until Plan 03
    assert hasattr(r2_sessions, "list_sessions")


# ============================================================================
# SESS-05 — disclaimer in docstrings (D-23)
# ============================================================================
def test_sess05_disclaimer_in_docstrings():
    """SESS-05 + D-23: open_r2_session AND r2_cmd docstrings carry the full SESS-05 disclaimer."""
    from mcp_gateway.tools import r2_sessions  # RED until Plan 03
    for fn_name in ("open_r2_session", "r2_cmd"):
        fn = getattr(r2_sessions, fn_name)
        assert fn.__doc__ is not None, f"{fn_name} missing docstring"
        doc = fn.__doc__
        # D-23 phrasing checks (full disclaimer):
        assert "shared across all MCP clients" in doc, \
            f"{fn_name} docstring missing SESS-05 disclaimer (shared-across-clients clause)"
        assert "bearer token" in doc, \
            f"{fn_name} docstring missing SESS-05 disclaimer (bearer-token clause)"
        assert "v1.2" in doc or "GW-V2-03" in doc, \
            f"{fn_name} docstring missing SESS-05 deferral marker"
    # list_sessions + close_r2_session get the SHORT form:
    for fn_name in ("list_sessions", "close_r2_session"):
        fn = getattr(r2_sessions, fn_name)
        assert fn.__doc__ is not None
        assert ("See `open_r2_session`" in fn.__doc__) or ("shared across" in fn.__doc__), \
            f"{fn_name} missing short-form SESS-05 cross-reference"


# ============================================================================
# SESS-06 — dangerous-cmd refusal matrix (D-09)
# ============================================================================
@pytest.mark.asyncio
async def test_dangerous_cmd_refusal_matrix(tmp_path):
    """SESS-06 + D-09: r2_cmd refuses every entry in the D-09 positive matrix.

    Positive matrix (must raise ValueError):
      !ls, #!python print(1), R!whoami, pdf ; !ls, aflj | !cat /etc/passwd, ?e foo\\n!ls
    Negative matrix (must NOT raise):
      pi 10, ?V, pdf @ sym.foo, aaa ; afl
    Also: init_commands=['aaa', '!ls'] → open_r2_session raises before spawn.
    """
    _require_r2_or_skip()
    from mcp_gateway.tools import r2_sessions  # RED until Plan 03
    assert hasattr(r2_sessions, "r2_cmd")


@pytest.mark.asyncio
async def test_lockdown_init_took_effect(tmp_path):
    """SESS-06 + D-03: after open, r2_cmd(sid, 'e scr.interactive') returns 'false'."""
    _require_r2_or_skip()
    from mcp_gateway.tools import r2_sessions  # RED until Plan 03
    assert hasattr(r2_sessions, "open_r2_session")


# ============================================================================
# Pitfall 6 — hung-command kills session, session_invalidated=True
# ============================================================================
@pytest.mark.asyncio
async def test_hung_cmd_kills_session(tmp_path):
    """Pitfall 6 + D-20 step d: r2_cmd('?I prompt', timeout=2.0) returns session_invalidated=True
    within 5s; subsequent list_sessions does NOT include this session."""
    _require_r2_or_skip()
    from mcp_gateway.tools import r2_sessions  # RED until Plan 03
    assert hasattr(r2_sessions, "r2_cmd")


# ============================================================================
# Pitfall 18 — cancellation propagates to killpg within 200 ms
# ============================================================================
@pytest.mark.asyncio
async def test_cancel_propagates_to_killpg(tmp_path):
    """Pitfall 18: wrap r2_cmd('aaaa') in a task, cancel after 0.5s, assert r2 PID dead within 200ms."""
    _require_r2_or_skip()
    from mcp_gateway.tools import r2_sessions  # RED until Plan 03
    assert hasattr(r2_sessions, "r2_cmd")


# ============================================================================
# Transcript + per-command log defense-in-depth
# ============================================================================
@pytest.mark.asyncio
async def test_transcript_captures_three_cmds(tmp_path):
    """D-13: open → 3 commands → close; transcript contains all 3 commands + outputs + close footer."""
    _require_r2_or_skip()
    from mcp_gateway.tools import r2_sessions  # RED until Plan 03
    assert hasattr(r2_sessions, "open_r2_session")


@pytest.mark.asyncio
async def test_per_command_log_filename_shape(tmp_path):
    """D-12: per-command log filename matches Phase 6 D-09 shape: <ts>Z-r2_cmd-<rand4>.txt"""
    _require_r2_or_skip()
    from mcp_gateway.tools import r2_sessions  # RED until Plan 03
    # Plan 05 asserts: re.match(r"\d{8}T\d{6}Z-r2_cmd-[0-9a-f]{4}\.txt$", os.path.basename(log_path))
    assert hasattr(r2_sessions, "r2_cmd")
