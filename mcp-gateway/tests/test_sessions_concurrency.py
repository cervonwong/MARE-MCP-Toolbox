"""Phase 13 HARDEN-01 + SESS-CAP-01: concurrency-atomicity tests for SessionRegistry.

Tests the BoundedSemaphore cap-enforcement primitive (Phase 13 D-01) under
concurrent contention. Uses a stub _open_<kind> driver so tests run without
r2 / gdb binaries on the host. The semaphore primitive itself is exercised
against the real SessionRegistry from sessions/_base.py.

Test matrix (D-02): cancel/oserror/runtime-error/reaper-idle/shutdown sessions.
Plus the primary N+1 contention proof (test_n_concurrent_opens_exactly_one_rejected).

These tests are the central correctness proof for HARDEN-01 (atomic cap) and
SESS-CAP-01 (sessions-registry slot lifecycle). T-13-01 (TOCTOU resource
exhaustion) is mitigated by test_n_concurrent_opens_exactly_one_rejected.
T-13-02 (cleanup-path crash on over-release) is mitigated by the failure-
cleanup matrix tests.

Safety note: SessionRegistry.close() calls os.killpg(sess.pgid, SIGKILL).
Stub sessions use a sentinel pgid value of -99999 (a never-existing pgid)
so killpg raises ProcessLookupError (caught silently by close()) instead of
killing the test process group. Real r2/gdb spawns under start_new_session=True
get their own pgid; the stub must NEVER share pgid=0 with the test runner.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_gateway.sessions._base import (
    BaseSession,
    SessionCapReached,
    SessionRegistry,
    make_sentinel,
)


# Sentinel pgid for stub sessions. -99999 is far outside any valid pid namespace
# so killpg raises ProcessLookupError (silently swallowed by close()). NEVER
# use 0 -- that targets the test runner's own process group and kills pytest.
_STUB_PGID = -99999


@pytest.fixture(autouse=True)
def _patch_killpg(monkeypatch):
    """Defense-in-depth: make os.killpg a no-op for the stub PGID range.

    SessionRegistry.close() calls os.killpg(sess.pgid, SIGKILL). If a stub
    session's pgid ever defaults to 0 (the test runner's own pgid) the test
    suite would SIGKILL itself. Belt-and-braces patch raises ProcessLookupError
    for any pgid < 0 (our stub range) so the kill path is exercised as a no-op.
    """
    real_killpg = os.killpg

    def _safe_killpg(pgid, sig):
        if pgid <= 0:
            raise ProcessLookupError(f"stub pgid {pgid}: no real process group")
        return real_killpg(pgid, sig)

    monkeypatch.setattr("os.killpg", _safe_killpg)


# ---------------------------------------------------------------------------
# Helper: build a stub BaseSession that registers itself in registry._sessions.
# Avoids r2/gdb binary spawn; the semaphore primitive itself is what we test.
# ---------------------------------------------------------------------------
def _stub_session(session_id: str) -> BaseSession:
    proc = MagicMock()
    # proc.wait() must be awaitable -- return a completed coroutine via lambda.

    async def _wait():
        return 0

    proc.wait = _wait
    proc.pid = 0
    now_mono = time.monotonic()
    return BaseSession(
        session_id=session_id,
        case_dir=Path("/tmp"),
        pgid=_STUB_PGID,
        lock=asyncio.Lock(),
        sentinel=make_sentinel(),
        transcript_path=Path("/tmp/_does_not_exist.log"),
        opened_at=now_mono,
        opened_iso="2026-05-20T00:00:00",
        last_used_at=now_mono,
        proc=proc,
        kind="r2",
    )


# ---------------------------------------------------------------------------
# Stub driver mirroring sessions/r2.py::_open_r2's Phase 13 probe-and-acquire
# pattern. Drives the REAL SessionRegistry._sem + _lock + _sessions; only the
# subprocess + transcript I/O is replaced. Tests can inject failure-injection
# hooks via the `fail_at` / `sleep_s` knobs.
# ---------------------------------------------------------------------------
async def _stub_open(
    registry,
    *,
    case_dir,
    sample_sha256,
    sample_path,
    init_commands,
    open_timeout_s,
    sleep_s: float = 0.0,
    fail_at: str = "",
    **_kw,
) -> BaseSession:
    """Phase 13 D-01/D-03 probe-and-acquire pattern, then optional failure injection."""
    async with registry._lock:
        if registry._sem.locked():
            raise SessionCapReached(
                registry._max, registry.count_open(), registry.list()
            )
        await registry._sem.acquire()
        sid = secrets.token_urlsafe(12)

    sess = None
    try:
        if fail_at == "pre_spawn_oserror":
            raise OSError("simulated OSError before spawn")
        if sleep_s > 0:
            await asyncio.sleep(sleep_s)
        if fail_at == "post_acquire_runtime":
            raise RuntimeError("simulated init failed")
        sess = _stub_session(sid)
        async with registry._lock:
            registry._sessions[sid] = sess
        return sess
    except BaseException:
        # D-02: release the reserved slot on ANY failure (CancelledError + Exception).
        if sess is not None:
            sess._slot_released = True
        registry._sem.release()
        raise


# ============================================================================
# Test 1: N+1 contention -- the central HARDEN-01 correctness proof
# ============================================================================
@pytest.mark.asyncio
async def test_n_concurrent_opens_exactly_one_rejected(monkeypatch):
    """T-13-01 mitigation: 4 concurrent opens against cap=3 -> exactly 1 rejected.

    Pre-Phase-13: the TOCTOU race could let 2+ callers both observe count<max
    and both proceed; post-Phase-13 the atomic probe-and-acquire under
    registry._lock guarantees exactly 1 SessionCapReached.
    """
    monkeypatch.setattr(
        "mcp_gateway.sessions.r2._open_r2",
        lambda registry, **kw: _stub_open(registry, sleep_s=0.05, **kw),
    )
    async with SessionRegistry(
        max_sessions=3, idle_s=600, reaper_interval_s=600,
    ) as reg:
        results = await asyncio.gather(*[
            reg.open(
                case_dir=Path("/tmp"),
                sample_sha256="abc",
                sample_path=Path("/tmp/x"),
                init_commands=None,
                open_timeout_s=5,
                kind="r2",
            )
            for _ in range(4)
        ], return_exceptions=True)
        successes = [r for r in results if isinstance(r, BaseSession)]
        failures = [r for r in results if isinstance(r, SessionCapReached)]
        assert len(successes) == 3, (
            f"expected 3 successes, got {len(successes)}; results={results!r}"
        )
        assert len(failures) == 1, (
            f"expected 1 cap-reject, got {len(failures)}; results={results!r}"
        )
        # The cap-reject payload still uses the dict-as-truth (D-04).
        d = failures[0].to_dict()
        assert d["error"] == "session cap reached"
        assert d["max"] == 3


# ============================================================================
# Test 2: cancel-during-spawn releases the slot (no slot leak)
# ============================================================================
@pytest.mark.asyncio
async def test_cancel_during_spawn_releases_slot(monkeypatch):
    """T-13-02 + D-02: cancelling a spawn task must release the reserved slot."""
    monkeypatch.setattr(
        "mcp_gateway.sessions.r2._open_r2",
        lambda registry, **kw: _stub_open(registry, sleep_s=1.0, **kw),
    )
    async with SessionRegistry(
        max_sessions=2, idle_s=600, reaper_interval_s=600,
    ) as reg:
        task = asyncio.create_task(
            reg.open(
                case_dir=Path("/tmp"), sample_sha256="abc",
                sample_path=Path("/tmp/x"), init_commands=None,
                open_timeout_s=5, kind="r2",
            )
        )
        await asyncio.sleep(0.05)  # let task reach the inner sleep
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, BaseException):
            pass
        # After cancel, the slot MUST be back -- both slots should be free.
        # The semaphore's _value should be back at max_sessions (2).
        # Probe by opening 2 more sessions: both should succeed without blocking.
        s1 = await reg.open(
            case_dir=Path("/tmp"), sample_sha256="abc",
            sample_path=Path("/tmp/x"), init_commands=None,
            open_timeout_s=5, kind="r2",
        )
        s2 = await reg.open(
            case_dir=Path("/tmp"), sample_sha256="abc",
            sample_path=Path("/tmp/x"), init_commands=None,
            open_timeout_s=5, kind="r2",
        )
        assert isinstance(s1, BaseSession) and isinstance(s2, BaseSession)


# ============================================================================
# Test 3: OSError during spawn releases slot (no slot leak)
# ============================================================================
@pytest.mark.asyncio
async def test_oserror_during_spawn_releases_slot(monkeypatch):
    """T-13-02 + D-02: OSError during spawn must release the slot."""
    monkeypatch.setattr(
        "mcp_gateway.sessions.r2._open_r2",
        lambda registry, **kw: _stub_open(
            registry, fail_at="pre_spawn_oserror", **kw
        ),
    )
    async with SessionRegistry(
        max_sessions=2, idle_s=600, reaper_interval_s=600,
    ) as reg:
        # First call fails with OSError -- slot must be released.
        with pytest.raises(OSError):
            await reg.open(
                case_dir=Path("/tmp"), sample_sha256="abc",
                sample_path=Path("/tmp/x"), init_commands=None,
                open_timeout_s=5, kind="r2",
            )
        # Now swap to a successful stub; both slots should still be available.
        monkeypatch.setattr(
            "mcp_gateway.sessions.r2._open_r2",
            lambda registry, **kw: _stub_open(registry, **kw),
        )
        s1 = await reg.open(
            case_dir=Path("/tmp"), sample_sha256="abc",
            sample_path=Path("/tmp/x"), init_commands=None,
            open_timeout_s=5, kind="r2",
        )
        s2 = await reg.open(
            case_dir=Path("/tmp"), sample_sha256="abc",
            sample_path=Path("/tmp/x"), init_commands=None,
            open_timeout_s=5, kind="r2",
        )
        assert isinstance(s1, BaseSession) and isinstance(s2, BaseSession)


# ============================================================================
# Test 4: RuntimeError during init releases slot (no slot leak)
# ============================================================================
@pytest.mark.asyncio
async def test_runtime_error_during_init_releases_slot(monkeypatch):
    """T-13-02 + D-02: RuntimeError('init failed') from init batch must release slot."""
    monkeypatch.setattr(
        "mcp_gateway.sessions.r2._open_r2",
        lambda registry, **kw: _stub_open(
            registry, fail_at="post_acquire_runtime", **kw
        ),
    )
    async with SessionRegistry(
        max_sessions=2, idle_s=600, reaper_interval_s=600,
    ) as reg:
        with pytest.raises(RuntimeError):
            await reg.open(
                case_dir=Path("/tmp"), sample_sha256="abc",
                sample_path=Path("/tmp/x"), init_commands=None,
                open_timeout_s=5, kind="r2",
            )
        # Both slots still available.
        monkeypatch.setattr(
            "mcp_gateway.sessions.r2._open_r2",
            lambda registry, **kw: _stub_open(registry, **kw),
        )
        s1 = await reg.open(
            case_dir=Path("/tmp"), sample_sha256="abc",
            sample_path=Path("/tmp/x"), init_commands=None,
            open_timeout_s=5, kind="r2",
        )
        s2 = await reg.open(
            case_dir=Path("/tmp"), sample_sha256="abc",
            sample_path=Path("/tmp/x"), init_commands=None,
            open_timeout_s=5, kind="r2",
        )
        assert isinstance(s1, BaseSession) and isinstance(s2, BaseSession)


# ============================================================================
# Test 5: reaper closes idle session and releases slot (no slot leak)
# ============================================================================
@pytest.mark.asyncio
async def test_reaper_idle_releases_slot(monkeypatch, tmp_path):
    """T-13-02 + D-02: reaper-closes-idle path releases the semaphore slot.

    Uses real transcript paths under tmp_path so close()'s transcript-footer
    open() succeeds. The reaper runs every reaper_interval_s and closes any
    session whose last_used_at is older than idle_s.
    """
    case = tmp_path / "case_reaper"
    case.mkdir()

    async def _stub_open_with_transcript(registry, **kw):
        async with registry._lock:
            if registry._sem.locked():
                raise SessionCapReached(
                    registry._max, registry.count_open(), registry.list()
                )
            await registry._sem.acquire()
            sid = secrets.token_urlsafe(12)
        try:
            sess = _stub_session(sid)
            # Override transcript_path to a writable location for the close
            # footer.
            sess.case_dir = case
            sess.transcript_path = case / f"{sid}-transcript.log"
            sess.transcript_path.touch()
            # Make the session look idle immediately so the reaper picks it up.
            sess.last_used_at = time.monotonic() - 100.0
            async with registry._lock:
                registry._sessions[sid] = sess
            return sess
        except BaseException:
            registry._sem.release()
            raise

    monkeypatch.setattr(
        "mcp_gateway.sessions.r2._open_r2", _stub_open_with_transcript,
    )
    # idle_s=0.1, reaper_interval_s=0.05 so the reaper fires fast.
    async with SessionRegistry(
        max_sessions=2, idle_s=0.1, reaper_interval_s=0.05,
    ) as reg:
        s1 = await reg.open(
            case_dir=case, sample_sha256="abc",
            sample_path=Path("/tmp/x"), init_commands=None,
            open_timeout_s=5, kind="r2",
        )
        s2 = await reg.open(
            case_dir=case, sample_sha256="abc",
            sample_path=Path("/tmp/x"), init_commands=None,
            open_timeout_s=5, kind="r2",
        )
        assert isinstance(s1, BaseSession) and isinstance(s2, BaseSession)
        # Wait for reaper to run (idle 0.1 + interval 0.05 + margin).
        await asyncio.sleep(0.5)
        assert reg.count_open() == 0, f"reaper did not close idle sessions: {reg.list()!r}"
        # Both slots should be free; a 3rd open() must succeed without blocking.
        s3 = await reg.open(
            case_dir=case, sample_sha256="abc",
            sample_path=Path("/tmp/x"), init_commands=None,
            open_timeout_s=5, kind="r2",
        )
        assert isinstance(s3, BaseSession)


# ============================================================================
# Test 6: shutdown active sessions -- no ValueError on over-release
# ============================================================================
@pytest.mark.asyncio
async def test_shutdown_active_releases_or_clean_exit(monkeypatch, tmp_path):
    """T-13-02 + D-02: __aexit__ shutdown sweep closes active sessions cleanly.

    Each open session's close() releases its slot exactly once; the registry's
    __aexit__ MUST NOT release the semaphore directly (D-02 invariant). No
    ValueError should be raised from BoundedSemaphore over-release.
    """
    case = tmp_path / "case_shutdown"
    case.mkdir()

    async def _stub_open_with_transcript(registry, **kw):
        async with registry._lock:
            if registry._sem.locked():
                raise SessionCapReached(
                    registry._max, registry.count_open(), registry.list()
                )
            await registry._sem.acquire()
            sid = secrets.token_urlsafe(12)
        try:
            sess = _stub_session(sid)
            sess.case_dir = case
            sess.transcript_path = case / f"{sid}-transcript.log"
            sess.transcript_path.touch()
            async with registry._lock:
                registry._sessions[sid] = sess
            return sess
        except BaseException:
            registry._sem.release()
            raise

    monkeypatch.setattr(
        "mcp_gateway.sessions.r2._open_r2", _stub_open_with_transcript,
    )

    reg = SessionRegistry(max_sessions=2, idle_s=600, reaper_interval_s=600)
    async with reg:
        s1 = await reg.open(
            case_dir=case, sample_sha256="abc",
            sample_path=Path("/tmp/x"), init_commands=None,
            open_timeout_s=5, kind="r2",
        )
        s2 = await reg.open(
            case_dir=case, sample_sha256="abc",
            sample_path=Path("/tmp/x"), init_commands=None,
            open_timeout_s=5, kind="r2",
        )
        assert isinstance(s1, BaseSession) and isinstance(s2, BaseSession)
    # __aexit__ has run -- both sessions should be marked closed; no ValueError
    # should have surfaced. If we got here without an exception, the test passes.
    assert all(s.closed for s in reg._sessions.values()), (
        f"expected all sessions closed after __aexit__, got {reg._sessions!r}"
    )
