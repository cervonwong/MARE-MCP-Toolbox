"""Phase 8 GREEN behavioural tests — MCP tool surface (open/r2_cmd/close/list).

Plan 01 produced the RED scaffold; Plan 05 Task 2a + 2b fill every behavioural
body. All r2-spawning tests skip cleanly on hosts without r2 (via
_require_r2_or_skip); container image runs them for real.

Every behavioural test consumes the `opened_sid` fixture (defined below) so
open-session boilerplate has a single source of truth.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import signal
import time
from pathlib import Path

import pytest
import pytest_asyncio

from tests.conftest import _require_r2_or_skip


# ============================================================================
# Shared fixtures for behavioural tests (Plan 05 Task 2a).
# ============================================================================
from mcp_gateway import session_state, sessions as _sessions_mod
from mcp_gateway.tools import (
    r2_sessions,
    samples as _samples_mod,
    case_dirs as _case_dirs_mod,
)

FIXTURE_ELF = Path(__file__).parent / "fixtures" / "hello_elf"


def _require_fixture_elf() -> Path:
    if not FIXTURE_ELF.exists():
        pytest.skip("hello_elf fixture missing (Phase 7 D-34)")
    return FIXTURE_ELF


@pytest_asyncio.fixture
async def opened_sid(tmp_path, monkeypatch):
    """Open a real r2 session and yield (sid, registry, case_dir).

    Boots a fresh SessionRegistry into session_state.SESSION_REGISTRY for the
    duration of the test, monkeypatches resolve_case_dir + resolve_sample so
    the test stays hermetic (tmp_path-only, no STATUS_ROOT scaffolding), and
    opens a single r2 session against the FIXTURE_ELF.

    Yields (session_id: str, registry: SessionRegistry, case_dir: str).

    The registry's __aexit__ kills every still-open session, so tests do not
    need to call close_r2_session in tear-down (idempotent close + cap-test
    cases that DO want to call close are still free to).
    """
    _require_r2_or_skip()
    _require_fixture_elf()

    case_dir = tmp_path / "case-1"
    case_dir.mkdir()

    # Stage the fixture under the case dir so resolve_sample's "container path"
    # mode resolves it cleanly (path under STATUS_ROOT, but we monkeypatch that
    # check away below).
    sample_dest = case_dir / "sample.elf"
    sample_dest.write_bytes(FIXTURE_ELF.read_bytes())

    # Monkeypatch the resolvers to bypass STATUS_ROOT scaffolding.
    # resolve_case_dir returns str (NOT Path; matches Plan 03 contract).
    # resolve_sample returns str (NOT a tuple; Plan 03 computes sha256
    # explicitly via hashlib).
    monkeypatch.setattr(_case_dirs_mod, "resolve_case_dir", lambda c: str(case_dir))
    monkeypatch.setattr(_samples_mod, "resolve_sample", lambda s: str(sample_dest))

    async with _sessions_mod.SessionRegistry(
        max_sessions=8, idle_s=1800.0, reaper_interval_s=60.0,
    ) as reg:
        monkeypatch.setattr(session_state, "SESSION_REGISTRY", reg)
        opened = await r2_sessions.open_r2_session(
            case_dir=str(case_dir),
            sample=str(sample_dest),
            open_timeout=60.0,
        )
        yield (opened["session_id"], reg, str(case_dir))
        # Registry __aexit__ killpgs the session if still open.


# ============================================================================
# SESS-01 — analysis state persists across calls
# ============================================================================
@pytest.mark.asyncio
async def test_aaa_aflj_persists(opened_sid):
    """SESS-01: open → r2_cmd('aaa') → r2_cmd('aflj') returns parsed JSON with functions."""
    sid, _reg, _case = opened_sid
    # Drive analysis on this session, then query function list as JSON.
    aaa = await r2_sessions.r2_cmd(sid, "aaa")
    assert aaa["session_invalidated"] is False
    result = await r2_sessions.r2_cmd(sid, "aflj", format="json")
    assert result["session_invalidated"] is False
    assert result["format"] == "json"
    assert result["parsed_json"] is not None, f"aflj returned no parsed_json: {result!r}"
    assert isinstance(result["parsed_json"], list)
    assert len(result["parsed_json"]) >= 1, "aaa did not discover any function"


# ============================================================================
# SESS-02 — result-dict shape (12 Phase-6 keys + 6 r2 extensions)
# ============================================================================
@pytest.mark.asyncio
async def test_r2_cmd_result_shape(opened_sid):
    """SESS-02 + D-11: all 18 keys present with correct types."""
    sid, _reg, _case = opened_sid
    result = await r2_sessions.r2_cmd(sid, "?V")
    required = {
        "exit_code", "timed_out", "duration_s",
        "stdout_head", "stdout_truncated", "stdout_bytes_total",
        "stderr_head", "stderr_truncated", "stderr_bytes_total",
        "log_path", "argv", "slug",
        "session_id", "session_invalidated", "format",
        "parsed_json", "parse_error", "transcript_path",
    }
    missing = required - result.keys()
    assert not missing, f"missing keys: {missing}"
    assert result["slug"] == "r2_cmd"
    assert result["stderr_head"] == ""
    assert result["stderr_truncated"] is False
    assert result["stderr_bytes_total"] == 0
    assert result["session_id"] == sid


# ============================================================================
# SESS-02 — format=json on a known-JSON command (iij)
# ============================================================================
@pytest.mark.asyncio
async def test_format_json_iij(opened_sid):
    """SESS-02 + D-10: format=json on iij returns parsed_json (a dict/list)."""
    sid, _reg, _case = opened_sid
    # First run aaa so iij has imports to list (small ELFs may have none).
    await r2_sessions.r2_cmd(sid, "aaa")
    result = await r2_sessions.r2_cmd(sid, "iij", format="json")
    assert result["format"] == "json"
    # parsed_json is permitted to be a list or dict depending on r2 version;
    # the contract is "not None and not parse_error" on a JSON-supporting cmd.
    assert result["parse_error"] is None, f"unexpected parse_error: {result['parse_error']!r}"
    assert result["parsed_json"] is not None or result["stdout_bytes_total"] == 0, \
        f"iij returned content but parsed_json is None: {result!r}"


# ============================================================================
# SESS-02 — format=json on a non-JSON command (?V) → parsed_json=None + parse_error
# ============================================================================
@pytest.mark.asyncio
async def test_format_json_non_json_command(opened_sid):
    """SESS-02 + D-10: format=json on ?V → parsed_json=None, parse_error set."""
    sid, _reg, _case = opened_sid
    result = await r2_sessions.r2_cmd(sid, "?V", format="json")
    assert result["format"] == "json"
    assert result["parsed_json"] is None
    assert isinstance(result["parse_error"], str) and result["parse_error"], \
        f"expected parse_error to be a non-empty string: {result['parse_error']!r}"


# ============================================================================
# SESS-03 — close idempotent
# ============================================================================
@pytest.mark.asyncio
async def test_close_idempotent(opened_sid):
    """SESS-03 + D-21: second close returns ok=True, already_closed=True."""
    sid, _reg, _case = opened_sid
    first = await r2_sessions.close_r2_session(sid)
    assert first["ok"] is True
    assert first["already_closed"] is False
    second = await r2_sessions.close_r2_session(sid)
    assert second["ok"] is True
    assert second["already_closed"] is True


# ============================================================================
# SESS-03 — list_sessions fd_count contract
# ============================================================================
@pytest.mark.asyncio
async def test_list_fd_count_nonneg(opened_sid):
    """SESS-03 + D-22: live session has fd_count >= 0 (or -1 if /proc unreadable)."""
    sid, _reg, _case = opened_sid
    listing = await r2_sessions.list_sessions()
    assert listing["open_count"] >= 1
    entries = [s for s in listing["sessions"] if s["session_id"] == sid]
    assert entries, f"opened sid {sid} not present in list_sessions: {listing!r}"
    entry = entries[0]
    # fd_count is >= 0 OR -1 (proc-read failure path)
    assert entry["fd_count"] >= -1
    assert "pid" in entry and isinstance(entry["pid"], int)
    assert "command_count" in entry


# ============================================================================
# SESS-05 — disclaimer in docstrings (D-23)
# ============================================================================
def test_sess05_disclaimer_in_docstrings():
    """SESS-05 + D-23: open_r2_session AND r2_cmd docstrings carry the full SESS-05 disclaimer."""
    from mcp_gateway.tools import r2_sessions  # already imported at module top; re-bind locally
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
# SESS-06 — dangerous-command refusal matrix (D-09)
# ============================================================================
@pytest.mark.asyncio
async def test_dangerous_cmd_refusal_matrix(opened_sid, monkeypatch, tmp_path):
    """SESS-06 + D-09: r2_cmd refuses every entry in the D-09 positive matrix.

    Positive matrix (must raise ValueError):
      !ls, #!python print(1), R!whoami, pdf ; !ls, aflj | !cat /etc/passwd, ?e foo\\n!ls
    Negative matrix (must NOT raise):
      pi 1, ?V, aaa ; afl
    Also: init_commands=['aaa', '!ls'] → open_r2_session raises before spawn.
    """
    sid, _reg, case_dir = opened_sid

    positive_matrix = [
        "!ls",
        "#!python print(1)",
        "R!whoami",
        "pdf ; !ls",
        "aflj | !cat /etc/passwd",
        "?e foo\n!ls",
    ]
    for bad in positive_matrix:
        with pytest.raises(ValueError, match="dangerous r2 command refused"):
            await r2_sessions.r2_cmd(sid, bad)

    # Negative matrix — must NOT raise.
    negative_matrix = ["pi 1", "?V", "aaa ; afl"]
    for ok in negative_matrix:
        result = await r2_sessions.r2_cmd(sid, ok)
        assert result["session_invalidated"] is False, \
            f"benign cmd {ok!r} unexpectedly invalidated session: {result!r}"

    # init_commands matrix — refusal occurs BEFORE r2 spawn
    with pytest.raises(ValueError, match="dangerous r2 command refused"):
        await r2_sessions.open_r2_session(
            case_dir=case_dir,
            sample=str(Path(case_dir) / "sample.elf"),
            init_commands=["aaa", "!ls"],
        )


# ============================================================================
# SESS-06 — lockdown init took effect (scr.interactive=false)
# ============================================================================
@pytest.mark.asyncio
async def test_lockdown_init_took_effect(opened_sid):
    """SESS-06 + D-03: after open, r2_cmd(sid, 'e scr.interactive') returns 'false'."""
    sid, _reg, _case = opened_sid
    result = await r2_sessions.r2_cmd(sid, "e scr.interactive")
    # r2's `e <key>` (no =) prints the current value. Expect "false".
    assert "false" in result["stdout_head"].lower(), \
        f"scr.interactive lockdown not effective: {result['stdout_head']!r}"


# ============================================================================
# Pitfall 6 — hung command kills session, session_invalidated=True
# ============================================================================
@pytest.mark.asyncio
async def test_hung_cmd_kills_session(opened_sid):
    """Pitfall 6 + D-20 step d: r2_cmd('?I prompt', timeout=2.0) returns session_invalidated=True
    within 5s; subsequent list_sessions does NOT include this session."""
    sid, _reg, _case = opened_sid
    # `?I` requests an interactive prompt which will hang; with timeout=2.0 the
    # session must be killed and session_invalidated=True returned within 5s.
    start = time.monotonic()
    result = await r2_sessions.r2_cmd(sid, "?I prompt", timeout=2.0)
    elapsed = time.monotonic() - start
    assert elapsed < 5.0, f"hung cmd took {elapsed:.2f}s to return"
    assert result["session_invalidated"] is True
    assert result["timed_out"] is True
    assert result["exit_code"] == -9
    # Session is gone from list_sessions
    listing = await r2_sessions.list_sessions()
    sids = {s["session_id"] for s in listing["sessions"]}
    assert sid not in sids


# ============================================================================
# Pitfall 18 — cancellation propagates to killpg within 200 ms
# ============================================================================
@pytest.mark.asyncio
async def test_cancel_propagates_to_killpg(opened_sid):
    """Pitfall 18: wrap r2_cmd('aaaa') in a task, cancel after 0.5s, assert r2 PID dead within 200ms."""
    sid, reg, _case = opened_sid
    # Capture the r2 PID BEFORE issuing aaaa, so we can verify it dies post-cancel.
    sess_obj = reg.get(sid)
    pid = sess_obj.proc.pid

    task = asyncio.create_task(r2_sessions.r2_cmd(sid, "aaaa", timeout=60.0))
    await asyncio.sleep(0.5)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Pitfall 18: PID must be dead within 200ms of cancel.
    dead = False
    for _ in range(20):  # 20 * 10ms = 200ms
        try:
            os.kill(pid, 0)
            await asyncio.sleep(0.01)
        except ProcessLookupError:
            dead = True
            break
    assert dead, f"r2 pid {pid} still alive 200ms after cancel"


# ============================================================================
# D-13 — transcript captures three commands + close footer
# ============================================================================
@pytest.mark.asyncio
async def test_transcript_captures_three_cmds(opened_sid):
    """D-13: open → 3 commands → close; transcript contains all 3 commands + outputs + close footer."""
    sid, _reg, case_dir = opened_sid
    for c in ("?V", "aaa", "afl"):
        await r2_sessions.r2_cmd(sid, c)
    await r2_sessions.close_r2_session(sid)
    transcript = Path(case_dir) / "r2-sessions" / f"{sid}-transcript.log"
    text = transcript.read_text(encoding="utf-8", errors="replace")
    for c in ("?V", "aaa", "afl"):
        assert c in text, f"command {c!r} missing from transcript"
    assert "closed" in text
    assert "reason=user" in text


# ============================================================================
# D-12 — per-command log filename matches Phase 6 D-09 shape
# ============================================================================
@pytest.mark.asyncio
async def test_per_command_log_filename_shape(opened_sid):
    """D-12: per-command log filename matches Phase 6 D-09 shape: <ts>Z-r2_cmd-<rand4>.txt"""
    sid, _reg, _case = opened_sid
    result = await r2_sessions.r2_cmd(sid, "?V")
    rel = result["log_path"]
    basename = os.path.basename(rel)
    assert re.match(r"^\d{8}T\d{6}Z-r2_cmd-[0-9a-f]{4}\.txt$", basename), \
        f"log filename does not match Phase 6 D-09 shape: {basename!r}"


# ============================================================================
# Phase 13 HARDEN-06 tests — open_r2_session_unsafe
# ============================================================================

import asyncio as _asyncio
import datetime as _datetime
import secrets as _secrets
import time as _time
from pathlib import Path as _Path


class _CapturedArgvForUnsafe(Exception):
    def __init__(self, argv):
        self.argv = argv


@pytest.mark.asyncio
async def test_unsafe_passes_sandbox_false(tmp_path, monkeypatch):
    """HARDEN-06: open_r2_session_unsafe → registry.open(sandbox=False) → _open_r2 spawn argv has NO cfg.sandbox=true token."""
    from mcp_gateway import session_state
    from mcp_gateway.sessions._base import SessionRegistry

    # Build a sample
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"\x7fELF" + b"\x00" * 32)

    # Monkeypatch resolve_case_dir + resolve_sample to accept our tmp paths.
    # r2_sessions accesses resolve_case_dir via module-attribute (`_case_dirs.resolve_case_dir`)
    # so the patch must target the case_dirs module, not r2_sessions itself.
    monkeypatch.setattr(r2_sessions._case_dirs, "resolve_case_dir", lambda x: str(tmp_path))
    monkeypatch.setattr(r2_sessions._samples, "resolve_sample", lambda x: str(sample))

    # Capture argv via monkeypatch on asyncio.create_subprocess_exec.
    # The _open_r2 driver lives in sessions.r2; patch the asyncio module
    # symbol it uses (sessions.r2.asyncio.create_subprocess_exec).
    from mcp_gateway.sessions import r2 as r2mod

    async def _fake_spawn(*argv, **kw):
        raise _CapturedArgvForUnsafe(list(argv))

    monkeypatch.setattr(r2mod.asyncio, "create_subprocess_exec", _fake_spawn)

    async with SessionRegistry(max_sessions=2, idle_s=10, reaper_interval_s=10) as reg:
        monkeypatch.setattr(session_state, "SESSION_REGISTRY", reg)
        with pytest.raises(_CapturedArgvForUnsafe) as ei:
            await r2_sessions.open_r2_session_unsafe(
                str(tmp_path), "deadbeef",
                init_commands=None, open_timeout=5.0,
            )
    argv = ei.value.argv
    joined = " ".join(argv)
    assert "cfg.sandbox=true" not in joined, (
        f"unsafe path must NOT inject cfg.sandbox=true; argv={argv}"
    )


@pytest.mark.slow
@pytest.mark.asyncio
async def test_unsafe_open_warn_log(tmp_path, monkeypatch, caplog):
    """HARDEN-06 / D-11: every unsafe-open emits a WARNING log line with the required fields."""
    _require_r2_or_skip()
    _require_fixture_elf()

    from mcp_gateway import session_state
    from mcp_gateway.sessions._base import SessionRegistry

    case_dir = tmp_path / "case-unsafe"
    case_dir.mkdir()
    sample_dest = case_dir / "sample.elf"
    sample_dest.write_bytes(FIXTURE_ELF.read_bytes())

    monkeypatch.setattr(r2_sessions._case_dirs, "resolve_case_dir", lambda c: str(case_dir))
    monkeypatch.setattr(r2_sessions._samples, "resolve_sample", lambda s: str(sample_dest))

    async with SessionRegistry(max_sessions=2, idle_s=30, reaper_interval_s=30) as reg:
        monkeypatch.setattr(session_state, "SESSION_REGISTRY", reg)
        with caplog.at_level("WARNING", logger="mcp_gateway.tools.r2_sessions"):
            result = await r2_sessions.open_r2_session_unsafe(
                str(case_dir), str(sample_dest),
                init_commands=None, open_timeout=60.0,
            )
        # Inspect captured log records
        warn_records = [r for r in caplog.records
                        if r.levelname == "WARNING"
                        and r.name == "mcp_gateway.tools.r2_sessions"]
        assert warn_records, "no WARNING records captured on mcp_gateway.tools.r2_sessions"
        # Format the message the same way the logger does
        msg = " ".join(r.getMessage() for r in warn_records)
        assert "unsafe session opened" in msg
        assert "session_id=" in msg
        assert "sample_sha256=" in msg
        assert "case_dir=" in msg
        # Verify warnings field
        assert result.get("warnings") == ["r2 sandbox is DISABLED for this session"]


@pytest.mark.asyncio
async def test_unsafe_shares_combined_cap(tmp_path, monkeypatch):
    """HARDEN-06 Q6: unsafe sessions share the combined SessionRegistry cap with safe sessions."""
    from mcp_gateway import session_state
    from mcp_gateway.sessions._base import SessionRegistry, make_sentinel
    from mcp_gateway.sessions import r2 as r2mod

    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"\x7fELF")

    monkeypatch.setattr(r2_sessions._case_dirs, "resolve_case_dir", lambda x: str(tmp_path))
    monkeypatch.setattr(r2_sessions._samples, "resolve_sample", lambda x: str(sample))

    # Stub _open_r2 to exercise the registry semaphore without spawning r2.
    # The stub mirrors the atomic probe-and-acquire pattern from sessions/r2.py.
    async def _stub_open_r2(registry, *, case_dir, sample_sha256, sample_path,
                            init_commands, open_timeout_s, sandbox=True):
        async with registry._lock:
            if registry._sem.locked():
                from mcp_gateway.sessions._base import SessionCapReached
                raise SessionCapReached(registry._max, registry.count_open(), registry.list())
            await registry._sem.acquire()
            sid = _secrets.token_urlsafe(12)
        # Build a minimal R2Session with all required BaseSession fields. Use a
        # FAKE proc object with pid=0 + a no-op async wait() so close()'s
        # killpg(0,...) is blocked by the autouse fixture and proc.wait() does
        # not hang. Transcript path MUST live under case_dir so the tool
        # response's relative_to(case_dir) call works.
        class _FakeProc:
            pid = 0
            async def wait(self):
                return 0
        now_mono = _time.monotonic()
        now_iso = _datetime.datetime.now(_datetime.timezone.utc).isoformat(timespec="seconds")
        # case_dir is a Path; make a child path under it for the transcript.
        _case_path = _Path(case_dir)
        _case_path.mkdir(parents=True, exist_ok=True)
        _transcript_dir = _case_path / "r2-sessions"
        _transcript_dir.mkdir(exist_ok=True)
        sess = r2mod.R2Session(
            session_id=sid,
            case_dir=_case_path,
            pgid=-99999,  # sentinel pgid (matches Plan 01 test discipline)
            lock=_asyncio.Lock(),
            sentinel=make_sentinel(),
            transcript_path=_transcript_dir / f"{sid}-transcript.log",
            opened_at=now_mono,
            opened_iso=now_iso,
            last_used_at=now_mono,
            proc=_FakeProc(),
            sample_sha256=sample_sha256,
            sample_path=sample_path,
        )
        async with registry._lock:
            registry._sessions[sid] = sess
        return sess

    monkeypatch.setattr(r2mod, "_open_r2", _stub_open_r2)

    # Autouse killpg guard: refuse non-positive pgids so the stubbed sentinel
    # pgid=-99999 doesn't SIGKILL anything real on close().
    real_killpg = os.killpg

    def _safe_killpg(pgid, sig):
        if pgid <= 0:
            raise ProcessLookupError(f"refusing killpg({pgid}, {sig}) in test")
        return real_killpg(pgid, sig)

    monkeypatch.setattr(os, "killpg", _safe_killpg)

    async with SessionRegistry(max_sessions=2, idle_s=30, reaper_interval_s=30) as reg:
        monkeypatch.setattr(session_state, "SESSION_REGISTRY", reg)
        r1 = await r2_sessions.open_r2_session(str(tmp_path), "abc",
                                               init_commands=None, open_timeout=5.0)
        assert "error" not in r1, r1
        r2 = await r2_sessions.open_r2_session_unsafe(str(tmp_path), "def",
                                                      init_commands=None, open_timeout=5.0)
        assert "error" not in r2, r2
        # Third call (either safe or unsafe) must hit the cap.
        r3 = await r2_sessions.open_r2_session_unsafe(str(tmp_path), "ghi",
                                                      init_commands=None, open_timeout=5.0)
        assert r3.get("error") == "session cap reached", r3
        assert reg._sem.locked() is True
