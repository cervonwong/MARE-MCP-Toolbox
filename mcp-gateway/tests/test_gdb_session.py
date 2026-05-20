"""Phase 11 Plan 03 Wave-0: gdb-MI3 driver, allowlist matrix, sentinel framing, lockdown init.

Tests start RED (ImportError on `from mcp_gateway.sessions import GdbSession` because Plan 03
hasn't landed yet) and flip GREEN after Task 2. Slow tests are gated by gdb + netns presence.

Locks contract per CONTEXT.md D-04..D-09, RESEARCH Example 1 + Pitfalls #1/#10, and
VALIDATION.md DYN-05 deny-vector rows.
"""
from __future__ import annotations

import dataclasses
import importlib
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# MI allowlist matrices
# ---------------------------------------------------------------------------
_POSITIVE_MI = [
    "-info-functions",
    "-info-threads",
    "-data-evaluate-expression $rip",
    "-data-list-register-names",
    "-data-read-memory 0x400000 x 1 1 16",
    "-data-disassemble -s 0x400000 -e 0x400100 -- 0",
    "-stack-list-frames",
    "-stack-list-locals 1",
    "-exec-run",
    "-exec-continue",
    "-exec-interrupt",
    "-break-insert main",
    "-break-list",
    "-thread-info",
    "-thread-list-ids",
    "-symbol-info-functions",
    "-file-list-exec-source-files",
    "-var-create v0 * argv",
    "-var-list-children v0",
    "-gdb-version",
]

# 19 deny vectors per VALIDATION.md DYN-05 + CONTEXT.md D-07 negative matrix.
_NEGATIVE_MI = [
    "python print(1)",
    '-interpreter-exec console "python print(1)"',
    "source /tmp/x",
    "!ls",
    "shell ls",
    "pi print(1)",
    "attach 1",
    "-target-select remote :1234",
    "-target-attach 1234",
    "-gdb-set logging on",
    "-gdb-set logging file /tmp/x",
    "add-symbol-file /tmp/x 0x400000",
    "dump memory /tmp/dump 0x400000 0x400100",
    "set inferior-tty /dev/pts/1",
    "generate-core-file /tmp/core",
    "jit-reader-load /tmp/r.so",
    "define foo end",
    "set logging on",   # CLI-style without `-` prefix → not in allowlist
    "info threads",     # CLI-style → not in allowlist
]


def test_negative_matrix_size_lockdown():
    """VALIDATION DYN-05 row requires AT LEAST 17 deny vectors; we ship 19."""
    assert len(_NEGATIVE_MI) >= 17


@pytest.mark.parametrize("cmd", _POSITIVE_MI)
def test_mi_allowlist_positive(cmd):
    from mcp_gateway.sessions.gdb import validate_mi_command
    # MUST NOT raise
    validate_mi_command(cmd)


@pytest.mark.parametrize("cmd", _NEGATIVE_MI)
def test_mi_allowlist_negative_matrix(cmd):
    from mcp_gateway.sessions.gdb import validate_mi_command
    with pytest.raises(ValueError):
        validate_mi_command(cmd)


_COMPOSITE_NEGATIVE = [
    '-info-functions ; -interpreter-exec console "python print(1)"',
    "-info-functions\n-gdb-set logging on",
    "-info-functions;source /tmp/x",
]


@pytest.mark.parametrize("cmd", _COMPOSITE_NEGATIVE)
def test_mi_allowlist_blocks_composite_separators(cmd):
    from mcp_gateway.sessions.gdb import validate_mi_command
    with pytest.raises(ValueError):
        validate_mi_command(cmd)


# ---------------------------------------------------------------------------
# Sentinel framing (D-06)
# ---------------------------------------------------------------------------
def test_gdb_sentinel_emitter_format():
    from mcp_gateway.sessions.gdb import build_sentinel_emit
    s = "__MARE_END_deadbeef__"
    assert build_sentinel_emit(s) == b'-data-evaluate-expression "\\"__MARE_END_deadbeef__\\""\n'


def test_gdb_sentinel_terminator_substring():
    from mcp_gateway.sessions.gdb import build_sentinel_terminator
    s = "__MARE_END_deadbeef__"
    assert build_sentinel_terminator(s) == b'^done,value="\\"__MARE_END_deadbeef__\\""'


# ---------------------------------------------------------------------------
# gdb argv shape (D-04, Pitfall #10)
# ---------------------------------------------------------------------------
def test_gdb_argv_under_wrap_netns(tmp_path):
    from mcp_gateway.sessions.gdb import _build_gdb_argv
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"\x7fELF")  # minimal ELF magic placeholder
    argv = _build_gdb_argv(sample)
    assert argv == [
        "unshare", "--net", "--ipc", "--uts", "--",
        "gdb", "--interpreter=mi3", "--quiet", "--nx", "--nh",
        str(sample),
    ]


def test_gdb_argv_does_not_include_iex_ex_x(tmp_path):
    from mcp_gateway.sessions.gdb import _build_gdb_argv
    sample = tmp_path / "sample2.bin"
    sample.write_bytes(b"\x7fELF")
    argv = _build_gdb_argv(sample)
    # Pitfall #10 — these flags bypass the MI allowlist and MUST NEVER be added.
    assert "-iex" not in argv
    assert "-ex" not in argv
    assert "-x" not in argv


# ---------------------------------------------------------------------------
# Lockdown init batch (D-05)
# ---------------------------------------------------------------------------
def test_lockdown_init_batch_contents():
    from mcp_gateway.sessions.gdb import build_lockdown_init_batch
    batch = build_lockdown_init_batch(sentinel="__MARE_END_deadbeef__")
    assert b"-gdb-set confirm off\n" in batch
    assert b"-gdb-set pagination off\n" in batch
    assert b"-gdb-set print pretty off\n" in batch
    assert b"-gdb-set verbose off\n" in batch
    assert b"-gdb-set debuginfod enabled off\n" in batch
    assert b"-gdb-set auto-solib-add off\n" in batch
    assert b"-gdb-set logging file /dev/null\n" in batch
    assert b"-gdb-set follow-fork-mode parent\n" in batch
    assert b"-gdb-set detach-on-fork on\n" in batch
    assert b"-gdb-set startup-with-shell off\n" in batch
    assert b"-gdb-version\n" in batch
    # Sentinel emit line at the END so readuntil only completes when all init
    # replies have come back.
    assert batch.endswith(b'-data-evaluate-expression "\\"__MARE_END_deadbeef__\\""\n')


# ---------------------------------------------------------------------------
# GdbSession dataclass shape (D-03)
# ---------------------------------------------------------------------------
def test_gdb_session_dataclass_fields():
    from mcp_gateway.sessions import GdbSession
    from mcp_gateway.sessions._base import BaseSession
    assert issubclass(GdbSession, BaseSession)
    assert dataclasses.is_dataclass(GdbSession)
    field_names = {f.name for f in dataclasses.fields(GdbSession)}
    # gdb-specific fields required
    required_gdb_fields = {
        "sample_sha256", "sample_path", "gdb_version",
        "mi_version", "follow_fork_mode", "netns_wrapped",
    }
    missing = required_gdb_fields - field_names
    assert not missing, f"GdbSession missing fields: {missing}"
    # Defaults check via dataclasses.fields default lookup
    defaults = {f.name: f.default for f in dataclasses.fields(GdbSession)}
    assert defaults["mi_version"] == "mi3"
    assert defaults["netns_wrapped"] is True
    assert defaults["kind"] == "gdb"


# ---------------------------------------------------------------------------
# Env-var constants (D-DYN-ENV-01, D-09/D-10)
# ---------------------------------------------------------------------------
def test_gdb_env_constants():
    from mcp_gateway.sessions import GDB_OPEN_TIMEOUT_S, GDB_CMD_TIMEOUT_S
    assert GDB_OPEN_TIMEOUT_S == 30.0
    assert GDB_CMD_TIMEOUT_S == 60.0


def test_gdb_env_validates_bad_values(monkeypatch):
    """Reimporting sessions.gdb with a bad env var raises RuntimeError (Phase 8 D-14 pattern)."""
    monkeypatch.setenv("MCP_GATEWAY_GDB_CMD_TIMEOUT_S", "not_a_float")
    # Drop cached module so re-import re-evaluates module-level _env_float()
    sys.modules.pop("mcp_gateway.sessions.gdb", None)
    with pytest.raises(RuntimeError):
        import mcp_gateway.sessions.gdb  # noqa: F401
    # Cleanup: reload with sane env so subsequent tests in this process are unaffected.
    # We also re-import the sessions PACKAGE so the package-level `GdbSession` binding
    # tracks the freshly-loaded submodule (otherwise the package keeps a dangling
    # reference to the pre-reload class).
    monkeypatch.delenv("MCP_GATEWAY_GDB_CMD_TIMEOUT_S", raising=False)
    sys.modules.pop("mcp_gateway.sessions.gdb", None)
    sys.modules.pop("mcp_gateway.sessions", None)
    import mcp_gateway.sessions  # noqa: F401


# ---------------------------------------------------------------------------
# Re-exports preserved
# ---------------------------------------------------------------------------
def test_gdb_symbols_reexported_from_sessions_package():
    import mcp_gateway.sessions as _pkg
    import mcp_gateway.sessions.gdb as _gdb
    assert _pkg.GdbSession is _gdb.GdbSession
    assert _pkg.GDB_OPEN_TIMEOUT_S == _gdb.GDB_OPEN_TIMEOUT_S
    assert _pkg.GDB_CMD_TIMEOUT_S == _gdb.GDB_CMD_TIMEOUT_S


def test_phase8_reexports_still_work():
    """Plan 03 must NOT regress Plan 01's Phase 8 re-exports."""
    from mcp_gateway.sessions import (
        SessionRegistry, R2Session, MAX_SESSIONS, SESSION_IDLE_S,
        REAPER_INTERVAL_S, R2_CMD_TIMEOUT_S, SESSION_OPEN_TIMEOUT_S,
        _DANGEROUS_R2_CMD_RE, check_dangerous_cmd, SessionCapReached,
        strip_ansi, truncate_for_response, make_sentinel,
    )
    # Identity touchpoints — these symbols must remain importable.
    assert SessionRegistry is not None
    assert R2Session is not None
    assert MAX_SESSIONS >= 1


def test_validate_mi_command_rejects_non_string():
    from mcp_gateway.sessions.gdb import validate_mi_command
    with pytest.raises(ValueError):
        validate_mi_command(b"-info-functions")  # bytes, not str
    with pytest.raises(ValueError):
        validate_mi_command(None)  # type: ignore[arg-type]


def test_allowlist_prefix_table_present():
    """_ALLOWED_MI_PREFIXES must exist and include the canonical entries."""
    from mcp_gateway.sessions.gdb import _ALLOWED_MI_PREFIXES
    assert isinstance(_ALLOWED_MI_PREFIXES, tuple)
    # Canonical prefixes that MUST be present
    for prefix in (
        "-info-",
        "-data-evaluate-expression",
        "-stack-list-frames",
        "-exec-run",
        "-break-insert",
        "-thread-info",
        "-gdb-version",
    ):
        assert prefix in _ALLOWED_MI_PREFIXES, f"missing prefix: {prefix}"


# ---------------------------------------------------------------------------
# Slow integration tests (gated)
# ---------------------------------------------------------------------------
@pytest.mark.slow
@pytest.mark.asyncio
async def test_gdb_session_roundtrip(tmp_path):
    """End-to-end open → exec → close on a real gdb process (slow, host-gated)."""
    if shutil.which("gdb") is None:
        pytest.skip("gdb unavailable on host")
    if shutil.which("unshare") is None:
        pytest.skip("unshare unavailable on host")
    # Probe netns capability
    import subprocess
    try:
        rc = subprocess.run(["unshare", "--net", "true"], capture_output=True, timeout=3).returncode
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("unshare --net failed")
    if rc != 0:
        pytest.skip("unshare --net failed (seccomp restriction)")

    from mcp_gateway.sessions import SessionRegistry
    sample = Path("/bin/true")
    if not sample.exists():
        pytest.skip("no /bin/true on host")
    case_dir = tmp_path / "001-gdbtest"
    case_dir.mkdir()
    reg = SessionRegistry(max_sessions=4, idle_s=600.0, reaper_interval_s=60.0)
    async with reg:
        sess = await reg.open(
            kind="gdb",
            case_dir=case_dir,
            sample_sha256="deadbeef" * 8,
            sample_path=sample,
            init_commands=None,
            open_timeout_s=30.0,
        )
        async with sess.lock:
            raw, timed_out = await sess.exec_one(
                '-data-evaluate-expression "1+1"', timeout=10.0
            )
        assert not timed_out
        assert b'value="2"' in raw or b'value=\\"2\\"' in raw
        await reg.close(sess.session_id, reason="test-done")


@pytest.mark.slow
@pytest.mark.asyncio
async def test_gdb_dangerous_cmd_rejected_runtime(tmp_path):
    """Dangerous MI commands MUST be rejected wrapper-side before any byte hits gdb."""
    if shutil.which("gdb") is None:
        pytest.skip("gdb unavailable on host")
    if shutil.which("unshare") is None:
        pytest.skip("unshare unavailable on host")
    import subprocess
    try:
        rc = subprocess.run(["unshare", "--net", "true"], capture_output=True, timeout=3).returncode
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("unshare --net failed")
    if rc != 0:
        pytest.skip("unshare --net failed (seccomp restriction)")

    from mcp_gateway.sessions import SessionRegistry
    sample = Path("/bin/true")
    if not sample.exists():
        pytest.skip("no /bin/true on host")
    case_dir = tmp_path / "002-gdbdanger"
    case_dir.mkdir()
    reg = SessionRegistry(max_sessions=4, idle_s=600.0, reaper_interval_s=60.0)
    async with reg:
        sess = await reg.open(
            kind="gdb",
            case_dir=case_dir,
            sample_sha256="cafebabe" * 8,
            sample_path=sample,
            init_commands=None,
            open_timeout_s=30.0,
        )
        async with sess.lock:
            with pytest.raises(ValueError):
                await sess.exec_one("python print(1)", timeout=5.0)
            # Session remains usable for a follow-up allowlisted command
            raw, timed_out = await sess.exec_one("-info-threads", timeout=5.0)
            assert not timed_out
        await reg.close(sess.session_id, reason="test-done")
