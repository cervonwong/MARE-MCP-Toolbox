"""Phase 8 GREEN behavioural tests — registry/reaper/cap/dangerous-cmd-regex/lifespan internals.

Plan 01 produced the RED scaffold (assert hasattr stubs). Plan 05 fills the
three SC-4 behavioural bodies (reaper, cap-reject, lifespan teardown) so the
file is fully behavioural. r2-spawning tests cleanly skip on hosts without r2
on PATH; container image provides r2 via the Kali base.
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
    # Reload module so the new env vars take effect.
    import importlib
    from mcp_gateway import sessions
    importlib.reload(sessions)
    try:
        from tests.conftest import _require_r2_or_skip
    except ImportError:
        import shutil as _sh
        if _sh.which("r2") is None:
            pytest.skip("r2 unavailable on host")
    else:
        _require_r2_or_skip()

    # Build a hermetic case_dir + sample. Use the Phase 7 fixture if available;
    # skip if missing.
    case = tmp_path / "case_idle"
    case.mkdir()
    fixture = Path(__file__).parent / "fixtures" / "hello_elf"
    if not fixture.exists():
        pytest.skip("hello_elf fixture missing (Phase 7 D-34)")

    async with sessions.SessionRegistry(
        max_sessions=4, idle_s=2.0, reaper_interval_s=1.0,
    ) as reg:
        sess = await reg.open(
            case_dir=case, sample_sha256="0" * 64,
            sample_path=fixture, init_commands=None,
            open_timeout_s=15.0,
        )
        pid = sess.proc.pid
        # Wait long enough for reaper to fire (idle 2s + interval 1s + margin).
        await asyncio.sleep(4)
        assert reg.count_open() == 0, f"reaper did not close idle session: {reg.list()!r}"
        # The PID must be dead.
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


# ============================================================================
# SESS-04 cap-reject — D-18 error dict shape
# ============================================================================
@pytest.mark.asyncio
async def test_cap_reject(tmp_path, monkeypatch):
    """SESS-04 + D-18: open N+1 returns {error: 'session cap reached', ...}."""
    try:
        from tests.conftest import _require_r2_or_skip
        _require_r2_or_skip()
    except ImportError:
        import shutil as _sh
        if _sh.which("r2") is None:
            pytest.skip("r2 unavailable on host")

    from mcp_gateway import sessions

    case = tmp_path / "case_cap"
    case.mkdir()
    fixture = Path(__file__).parent / "fixtures" / "hello_elf"
    if not fixture.exists():
        pytest.skip("hello_elf fixture missing")

    async with sessions.SessionRegistry(
        max_sessions=2, idle_s=600, reaper_interval_s=60,
    ) as reg:
        s1 = await reg.open(case_dir=case, sample_sha256="0" * 64,
                            sample_path=fixture, init_commands=None,
                            open_timeout_s=15.0)
        s2 = await reg.open(case_dir=case, sample_sha256="0" * 64,
                            sample_path=fixture, init_commands=None,
                            open_timeout_s=15.0)
        with pytest.raises(sessions.SessionCapReached) as ei:
            await reg.open(case_dir=case, sample_sha256="0" * 64,
                           sample_path=fixture, init_commands=None,
                           open_timeout_s=15.0)
        d = ei.value.to_dict()
        assert d["error"] == "session cap reached"
        assert d["max"] == 2
        assert d["open_count"] == 2
        assert isinstance(d["existing"], list) and len(d["existing"]) == 2


# ============================================================================
# SESS-04 lifespan-teardown kills every open r2 PID
# ============================================================================
@pytest.mark.asyncio
async def test_lifespan_teardown_kills_all(tmp_path):
    """SESS-04: SessionRegistry.__aexit__ killpg's every session."""
    try:
        from tests.conftest import _require_r2_or_skip
        _require_r2_or_skip()
    except ImportError:
        import shutil as _sh
        if _sh.which("r2") is None:
            pytest.skip("r2 unavailable on host")

    from mcp_gateway import sessions

    case = tmp_path / "case_shutdown"
    case.mkdir()
    fixture = Path(__file__).parent / "fixtures" / "hello_elf"
    if not fixture.exists():
        pytest.skip("hello_elf fixture missing")

    pids = []
    async with sessions.SessionRegistry(
        max_sessions=4, idle_s=600, reaper_interval_s=60,
    ) as reg:
        for _ in range(2):
            s = await reg.open(case_dir=case, sample_sha256="0" * 64,
                               sample_path=fixture, init_commands=None,
                               open_timeout_s=15.0)
            pids.append(s.proc.pid)
    # After __aexit__, every PID must be dead.
    await asyncio.sleep(0.2)  # killpg + shielded wait grace
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


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
