"""Phase 13 HARDEN-03 + HARDEN-04 (HOT-FIX 2026-05-21): r2 spawn-argv + init-batch unit tests.

After the 2026-05-21 hot-fix (see 13-CONTEXT.md D-21), `cfg.sandbox=true`
MUST NOT appear in the r2 argv: r2 6.0.5 latches cfg.sandbox at argv-eval
time and refuses `r_core_file_open` on the binary itself (in-container
log.level=4 probe: "ERROR: Cannot open '/bin/ls'"). Instead, when
sandbox=True, the FIRST non-empty line of the post-spawn stdin init batch
MUST be `e cfg.sandbox=true` — latching the Phase 13 security boundary
BEFORE any user-controlled command.

This file captures argv via a monkeypatched `asyncio.create_subprocess_exec`
short-circuit (for the NEGATIVE argv assertions) AND via a stdin-capturing
fake proc (for the POSITIVE init-batch latch assertions).
"""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
import pytest

from mcp_gateway.sessions._base import SessionRegistry
from mcp_gateway.sessions.r2 import _open_r2


class _CapturedArgv(Exception):
    def __init__(self, argv):
        self.argv = argv


def _patch_subprocess(monkeypatch):
    """Replace asyncio.create_subprocess_exec to capture argv and abort spawn."""
    async def _fake(*argv, **kw):
        raise _CapturedArgv(list(argv))
    # Patch on the r2 module (where create_subprocess_exec is called) and on asyncio itself.
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake)


# ---------------------------------------------------------------------------
# Stdin-capture fake-proc helper (HOT-FIX 2026-05-21).
#
# Builds a fake asyncio subprocess whose stdin.write() appends to an in-memory
# buffer and whose stdout.readuntil() unconditionally returns its target arg —
# this makes the sentinel-readuntil in _open_r2 resolve immediately so the
# coroutine returns cleanly and the test can inspect the captured stdin bytes.
#
# Also stubs os.getpgid (returns a sentinel -99999) and os.killpg (no-op for
# pgid<=0) so SessionRegistry.__aexit__'s shutdown sweep does NOT fire a real
# SIGKILL at the test runner's own process group (matches the Phase 13 P01
# test-harness pattern documented in STATE.md).
# ---------------------------------------------------------------------------
class _FakeStream:
    def __init__(self):
        self._buf = bytearray()

    def write(self, data):
        self._buf.extend(data)

    async def drain(self):
        return None

    async def readuntil(self, target):
        # Unconditional resolve: returning target makes _open_r2's
        # `readuntil((sentinel + "\n").encode())` complete immediately.
        return target


class _FakeProc:
    def __init__(self):
        self.pid = 12345
        self.stdin = _FakeStream()
        self.stdout = _FakeStream()
        self.stderr = _FakeStream()

    async def wait(self):
        return 0


def _patch_subprocess_capture_stdin(monkeypatch):
    """Patch create_subprocess_exec + os.getpgid + os.killpg for stdin capture.

    Returns a dict whose `captured["proc"]` is set when _open_r2 spawns; tests
    can read `captured["proc"].stdin._buf` to inspect the post-spawn stdin bytes.
    """
    captured: dict = {}

    async def _fake_create(*argv, **kw):
        proc = _FakeProc()
        captured["proc"] = proc
        captured["argv"] = list(argv)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create)

    # _STUB_PGID = -99999 matches tests/test_sessions_concurrency.py convention.
    # os.getpgid must return our sentinel so SessionRegistry.close()'s killpg
    # call targets the sentinel range (NOT the test runner's pgid=0).
    monkeypatch.setattr(os, "getpgid", lambda pid: -99999)

    real_killpg = os.killpg

    def _safe_killpg(pgid, sig):
        if pgid <= 0:
            raise ProcessLookupError(f"stub pgid {pgid}: no real process group")
        return real_killpg(pgid, sig)

    monkeypatch.setattr(os, "killpg", _safe_killpg)
    return captured


# ---------------------------------------------------------------------------
# NEGATIVE argv assertions — captured via the _CapturedArgv short-circuit.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_argv_no_sandbox_token(monkeypatch, tmp_path):
    """HOT-FIX 2026-05-21: argv MUST NOT contain `cfg.sandbox=true` when sandbox=True.

    r2 6.0.5 refuses `r_core_file_open` on the binary itself if cfg.sandbox is
    latched at argv-eval time (see 13-CONTEXT.md D-21). The sandbox latch lives
    in the post-spawn stdin init batch — verified by
    test_init_batch_starts_with_sandbox_latch below.
    """
    _patch_subprocess(monkeypatch)
    sample = tmp_path / "x.bin"
    sample.write_bytes(b"\x7fELF")
    case_dir = tmp_path
    async with SessionRegistry(max_sessions=2, idle_s=10, reaper_interval_s=10) as reg:
        with pytest.raises(_CapturedArgv) as ei:
            await _open_r2(
                reg, case_dir=case_dir, sample_sha256="a" * 64,
                sample_path=sample, init_commands=None,
                open_timeout_s=5.0, sandbox=True,
            )
    argv = ei.value.argv
    assert "cfg.sandbox=true" not in argv, (
        f"cfg.sandbox=true MUST NOT appear in argv (D-21): {argv}"
    )
    # Defense-in-depth: no argv element contains the substring `cfg.sandbox`
    # (catches any future hand-construction slip such as `cfg.sandbox.grain`,
    # `cfg.sandbox=false`, etc.).
    for tok in argv:
        assert "cfg.sandbox" not in tok, (
            f"argv element {tok!r} contains cfg.sandbox; full argv={argv}"
        )


@pytest.mark.asyncio
async def test_argv_sandbox_omitted_when_sandbox_false(monkeypatch, tmp_path):
    """HARDEN-03 unsafe-path: with sandbox=False, no cfg.sandbox token in argv at all."""
    _patch_subprocess(monkeypatch)
    sample = tmp_path / "x.bin"
    sample.write_bytes(b"\x7fELF")
    async with SessionRegistry(max_sessions=2, idle_s=10, reaper_interval_s=10) as reg:
        with pytest.raises(_CapturedArgv) as ei:
            await _open_r2(
                reg, case_dir=tmp_path, sample_sha256="a" * 64,
                sample_path=sample, init_commands=None,
                open_timeout_s=5.0, sandbox=False,
            )
    argv = ei.value.argv
    joined = " ".join(argv)
    assert "cfg.sandbox=true" not in joined, f"cfg.sandbox=true leaked into unsafe argv: {argv}"
    assert "cfg.sandbox=false" not in joined, (
        f"sandbox=False must omit sandbox tokens entirely, not explicitly set false: {argv}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("sandbox", [True, False])
async def test_argv_no_grain_override(monkeypatch, tmp_path, sandbox):
    """HARDEN-04 / D-08 RESOLUTION: no cfg.sandbox.grain in argv (default grain=all)."""
    _patch_subprocess(monkeypatch)
    sample = tmp_path / "x.bin"
    sample.write_bytes(b"\x7fELF")
    async with SessionRegistry(max_sessions=2, idle_s=10, reaper_interval_s=10) as reg:
        with pytest.raises(_CapturedArgv) as ei:
            await _open_r2(
                reg, case_dir=tmp_path, sample_sha256="a" * 64,
                sample_path=sample, init_commands=None,
                open_timeout_s=5.0, sandbox=sandbox,
            )
    argv = ei.value.argv
    joined = " ".join(argv)
    assert "cfg.sandbox.grain" not in joined, (
        f"cfg.sandbox.grain MUST NOT appear in argv per D-08 RESOLUTION: {argv}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("sandbox", [True, False])
async def test_argv_no_null_byte_separator_flag(monkeypatch, tmp_path, sandbox):
    """HOT-FIX 2026-05-21 (r2-cmd-timeout): argv MUST NOT contain `-0` or `-q0`.

    `r2 -h` defines `-0` as "print \\x00 after init and every command". When
    present, every line on r2's stdout (including the per-command sentinel
    emitted by `?e <sentinel>`) is prefixed with a NUL byte, which breaks
    R2Session.exec_one's `line == sentinel_line` equality check and causes
    a 30-second timeout on the FIRST r2_cmd call. The argv must use `-q`
    (quiet) alone; the explicit sentinel framing already delimits commands.
    """
    _patch_subprocess(monkeypatch)
    sample = tmp_path / "x.bin"
    sample.write_bytes(b"\x7fELF")
    async with SessionRegistry(max_sessions=2, idle_s=10, reaper_interval_s=10) as reg:
        with pytest.raises(_CapturedArgv) as ei:
            await _open_r2(
                reg, case_dir=tmp_path, sample_sha256="a" * 64,
                sample_path=sample, init_commands=None,
                open_timeout_s=5.0, sandbox=sandbox,
            )
    argv = ei.value.argv
    assert "-0" not in argv, (
        f"`-0` (NUL-byte separator) MUST NOT appear in argv — it breaks "
        f"exec_one's sentinel match. Got argv={argv}"
    )
    assert "-q0" not in argv, (
        f"`-q0` MUST NOT appear in argv — r2 parses it as `-q` + `-0` and "
        f"the `-0` half breaks exec_one's sentinel match. Got argv={argv}"
    )


# ---------------------------------------------------------------------------
# POSITIVE init-batch assertions — captured via the stdin-buffering fake proc.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_init_batch_starts_with_sandbox_latch(monkeypatch, tmp_path):
    """HOT-FIX 2026-05-21: with sandbox=True, the FIRST non-empty line of the
    post-spawn stdin init batch is `e cfg.sandbox=true`, latching the Phase 13
    security boundary BEFORE any user-controlled command."""
    captured = _patch_subprocess_capture_stdin(monkeypatch)
    sample = tmp_path / "x.bin"
    sample.write_bytes(b"\x7fELF")
    async with SessionRegistry(max_sessions=2, idle_s=10, reaper_interval_s=10) as reg:
        await _open_r2(
            reg, case_dir=tmp_path, sample_sha256="a" * 64,
            sample_path=sample, init_commands=None,
            open_timeout_s=5.0, sandbox=True,
        )
    buf = bytes(captured["proc"].stdin._buf)
    lines = [ln for ln in buf.split(b"\n") if ln.strip()]
    assert lines, f"init batch was empty: {buf!r}"
    assert lines[0] == b"e cfg.sandbox=true", (
        f"first non-empty stdin line must be 'e cfg.sandbox=true', got {lines[0]!r}; "
        f"full buf={buf!r}"
    )


@pytest.mark.asyncio
async def test_init_batch_no_sandbox_when_sandbox_false(monkeypatch, tmp_path):
    """HOT-FIX 2026-05-21: with sandbox=False, the stdin init batch contains
    no cfg.sandbox token (unsafe path leaves sandbox at r2's default = off)."""
    captured = _patch_subprocess_capture_stdin(monkeypatch)
    sample = tmp_path / "x.bin"
    sample.write_bytes(b"\x7fELF")
    async with SessionRegistry(max_sessions=2, idle_s=10, reaper_interval_s=10) as reg:
        await _open_r2(
            reg, case_dir=tmp_path, sample_sha256="a" * 64,
            sample_path=sample, init_commands=None,
            open_timeout_s=5.0, sandbox=False,
        )
    buf = bytes(captured["proc"].stdin._buf)
    assert b"cfg.sandbox" not in buf, (
        f"sandbox=False must not emit any cfg.sandbox token in stdin: {buf!r}"
    )
