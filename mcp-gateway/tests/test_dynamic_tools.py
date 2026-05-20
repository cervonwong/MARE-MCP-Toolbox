"""Phase 11 Plan 04 Wave-0 tests for tools/dynamic.py (the 7 MCP-tool surface).

These tests start RED (ImportError on `from mcp_gateway.tools import dynamic`
because the file doesn't exist yet) and flip GREEN after Task 2 creates the
module.

Covers:
  - D-DYN-TOOL-01: 7 module-level @mcp.tool() handler signatures + register seam
  - D-DYN-TOOL-02: disclaimer string spliced into each tool's __doc__
  - D-DYN-TOOL-03: open_gdb_session return dict shape
  - D-DYN-CAP-PROBE-02: structured cap-missing error dict
  - D-DYN-CAP-REFRESH: refresh=True semantics
  - "Tools NEVER raise out of the MCP boundary" (Phase 6 D-04 + Phase 8 D-18 + Phase 9 D-15)
"""
from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp.server.fastmcp import FastMCP

from mcp_gateway import dynamic as dynamic_mod
from mcp_gateway import session_state
from mcp_gateway.dynamic import DynamicCapabilities


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def caps_ok() -> DynamicCapabilities:
    return DynamicCapabilities(
        probed_at="2026-05-19T00:00:00+00:00",
        dynamic_mode_enabled=True,
        ptrace_scope=0,
        ptrace_traceme_works=True,
        binfmt_misc_mounted=True,
        qemu_architectures=("arm", "aarch64", "mips"),
        qemu_static_binaries=("/usr/bin/qemu-arm-static",),
        netns_feasible=True,
        unshare_path="/usr/bin/unshare",
        gdb_path="/usr/bin/gdb",
        gdb_version="GNU gdb 15.1",
        strace_path="/usr/bin/strace",
        ltrace_path="/usr/bin/ltrace",
        warnings=(),
    )


@pytest.fixture
def caps_no_ptrace(caps_ok: DynamicCapabilities) -> DynamicCapabilities:
    return dataclasses.replace(caps_ok, ptrace_traceme_works=False)


@pytest.fixture
def caps_no_netns(caps_ok: DynamicCapabilities) -> DynamicCapabilities:
    return dataclasses.replace(caps_ok, netns_feasible=False)


@pytest.fixture
def caps_arm_only(caps_ok: DynamicCapabilities) -> DynamicCapabilities:
    return dataclasses.replace(caps_ok, qemu_architectures=("arm",), qemu_static_binaries=("/usr/bin/qemu-arm-static",))


@pytest.fixture
def tmp_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Return a STATUS_ROOT-confined case_dir str. Monkeypatches samples roots."""
    from mcp_gateway.tools import samples as samples_mod
    monkeypatch.setattr(samples_mod, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(samples_mod, "ALLOWED_PREFIXES", (samples_mod.UPLOADS_ROOT, samples_mod.EXAMPLES_ROOT, tmp_path))
    case = tmp_path / "999-dyntest"
    case.mkdir(parents=True, exist_ok=True)
    return str(case)


@pytest.fixture(autouse=True)
def _restore_caps():
    """Save / restore dynamic.CAPABILITIES so test-mutations don't leak across cases."""
    saved = dynamic_mod.CAPABILITIES
    yield
    dynamic_mod.CAPABILITIES = saved


@pytest.fixture(autouse=True)
def _restore_registry():
    saved = session_state.SESSION_REGISTRY
    yield
    session_state.SESSION_REGISTRY = saved


# ---------------------------------------------------------------------------
# Test 1-3: 7-tool surface + disclaimer + register seam
# ---------------------------------------------------------------------------


TOOL_NAMES = (
    "run_strace",
    "run_ltrace",
    "run_qemu_user",
    "open_gdb_session",
    "gdb_exec",
    "close_gdb_session",
    "get_dynamic_capabilities",
)


def test_disclaimer_in_all_docstrings():
    from mcp_gateway.tools import dynamic as td
    for name in TOOL_NAMES:
        fn = getattr(td, name)
        assert fn.__doc__ is not None, f"{name} has no __doc__"
        assert "Dynamic mode tool" in fn.__doc__, f"{name} docstring missing 'Dynamic mode tool'"
        assert "MCP_GATEWAY_DYNAMIC_TOOLS=1" in fn.__doc__, f"{name} docstring missing env var marker"
        assert "unshare --net --ipc --uts" in fn.__doc__, f"{name} docstring missing unshare hint"


def test_seven_handlers_exist():
    from mcp_gateway.tools import dynamic as td
    for name in TOOL_NAMES:
        fn = getattr(td, name, None)
        assert fn is not None, f"{name} missing on tools.dynamic"
        assert inspect.iscoroutinefunction(fn), f"{name} must be async"


def test_register_wires_all_seven():
    from mcp_gateway.tools import dynamic as td
    m = FastMCP("t", stateless_http=True)
    td.register(m)
    registered = set(m._tool_manager._tools.keys())
    for name in TOOL_NAMES:
        assert name in registered, f"{name} not registered on FastMCP after td.register(mcp)"


# ---------------------------------------------------------------------------
# Test 4-6: Trace tools dispatch via JOBS
# ---------------------------------------------------------------------------


async def test_run_strace_dispatches_via_jobs(monkeypatch, tmp_case, caps_ok):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_ok

    sha = "aa" * 32
    fake_snapshot = {"job_id": "jid-1", "status": "pending", "tool": "strace"}
    mock_start = AsyncMock(return_value=fake_snapshot)
    monkeypatch.setattr("mcp_gateway.tools.jobs.start_tool_job", mock_start)
    # Make resolve_sample return a fake path
    monkeypatch.setattr("mcp_gateway.tools.samples.resolve_sample", lambda s: f"/fake/{s}")

    result = await td.run_strace(case_dir=tmp_case, sample_sha256=sha, profile="file_io")
    assert result == fake_snapshot
    mock_start.assert_awaited_once()
    call = mock_start.await_args
    assert call.kwargs["tool"] == "strace"
    assert call.kwargs["case_dir"] == tmp_case
    assert call.kwargs["kwargs"] == {
        "sample": sha,
        "profile": "file_io",
        "extra_args": [],
        "run_argv": [],
    }


async def test_run_ltrace_dispatches_via_jobs(monkeypatch, tmp_case, caps_ok):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_ok

    sha = "bb" * 32
    fake_snapshot = {"job_id": "jid-2", "status": "pending", "tool": "ltrace"}
    mock_start = AsyncMock(return_value=fake_snapshot)
    monkeypatch.setattr("mcp_gateway.tools.jobs.start_tool_job", mock_start)
    monkeypatch.setattr("mcp_gateway.tools.samples.resolve_sample", lambda s: f"/fake/{s}")

    result = await td.run_ltrace(case_dir=tmp_case, sample_sha256=sha, profile="default")
    assert result == fake_snapshot
    mock_start.assert_awaited_once()
    assert mock_start.await_args.kwargs["tool"] == "ltrace"


async def test_run_qemu_user_dispatches_via_jobs(monkeypatch, tmp_case, caps_ok):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_ok

    sha = "cc" * 32
    fake_snapshot = {"job_id": "jid-3", "status": "pending", "tool": "qemu_user"}
    mock_start = AsyncMock(return_value=fake_snapshot)
    monkeypatch.setattr("mcp_gateway.tools.jobs.start_tool_job", mock_start)
    monkeypatch.setattr("mcp_gateway.tools.samples.resolve_sample", lambda s: f"/fake/{s}")

    result = await td.run_qemu_user(
        case_dir=tmp_case, sample_sha256=sha, arch="arm", profile="default"
    )
    assert result == fake_snapshot
    mock_start.assert_awaited_once()
    kwargs = mock_start.await_args.kwargs
    assert kwargs["tool"] == "qemu_user"
    assert kwargs["kwargs"]["arch"] == "arm"


# ---------------------------------------------------------------------------
# Test 7-9: Capability-gated error paths
# ---------------------------------------------------------------------------


async def test_run_strace_returns_capability_error_when_ptrace_missing(
    monkeypatch, tmp_case, caps_no_ptrace
):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_no_ptrace
    mock_start = AsyncMock()
    monkeypatch.setattr("mcp_gateway.tools.jobs.start_tool_job", mock_start)

    result = await td.run_strace(case_dir=tmp_case, sample_sha256="aa" * 32, profile="file_io")
    assert result["error"] == "dynamic capability unavailable"
    assert "ptrace" in result["missing"]
    mock_start.assert_not_awaited()


async def test_run_strace_returns_capability_error_when_netns_missing(
    monkeypatch, tmp_case, caps_no_netns
):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_no_netns
    mock_start = AsyncMock()
    monkeypatch.setattr("mcp_gateway.tools.jobs.start_tool_job", mock_start)

    result = await td.run_strace(case_dir=tmp_case, sample_sha256="aa" * 32, profile="file_io")
    assert result["error"] == "dynamic capability unavailable"
    assert "netns" in result["missing"]
    mock_start.assert_not_awaited()


async def test_run_qemu_user_returns_error_when_arch_unsupported(
    monkeypatch, tmp_case, caps_arm_only
):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_arm_only
    mock_start = AsyncMock()
    monkeypatch.setattr("mcp_gateway.tools.jobs.start_tool_job", mock_start)

    result = await td.run_qemu_user(
        case_dir=tmp_case, sample_sha256="aa" * 32, arch="mips", profile="default"
    )
    assert result["error"] == "qemu arch unavailable"
    assert result["arch"] == "mips"
    assert "arm" in result["available"]
    mock_start.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 10-11: Sample resolution
# ---------------------------------------------------------------------------


async def test_sample_resolution_by_sha256(monkeypatch, tmp_case, caps_ok):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_ok
    sha = "aa" * 32
    seen = {}

    def fake_resolve(s):
        seen["sample"] = s
        return f"/fake/{s}"

    monkeypatch.setattr("mcp_gateway.tools.samples.resolve_sample", fake_resolve)
    monkeypatch.setattr(
        "mcp_gateway.tools.jobs.start_tool_job",
        AsyncMock(return_value={"job_id": "jid", "status": "pending"}),
    )

    await td.run_strace(case_dir=tmp_case, sample_sha256=sha, profile="file_io")
    assert seen["sample"] == sha


async def test_sample_resolution_failure_returns_error_dict(monkeypatch, tmp_case, caps_ok):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_ok
    sha = "bb" * 32

    def raise_missing(s):
        raise FileNotFoundError(f"no upload for sha256 {s}")

    monkeypatch.setattr("mcp_gateway.tools.samples.resolve_sample", raise_missing)
    mock_start = AsyncMock()
    monkeypatch.setattr("mcp_gateway.tools.jobs.start_tool_job", mock_start)

    result = await td.run_strace(case_dir=tmp_case, sample_sha256=sha, profile="file_io")
    assert result["error"] == "sample_not_found"
    assert result["sha256"] == sha
    mock_start.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 12: open_gdb_session
# ---------------------------------------------------------------------------


async def test_open_gdb_session_dispatches_via_registry(monkeypatch, tmp_case, caps_ok):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_ok

    sha = "dd" * 32
    monkeypatch.setattr("mcp_gateway.tools.samples.resolve_sample", lambda s: f"/fake/{s}")

    # Build a fake GdbSession-shaped object
    fake_sess = MagicMock()
    fake_sess.session_id = "sid-1"
    fake_sess.case_dir = Path(tmp_case)
    fake_sess.sample_sha256 = sha
    fake_sess.sample_path = Path(f"/fake/{sha}")
    fake_sess.transcript_path = Path(tmp_case) / "dynamic" / "sid-1-gdb-transcript.log"
    fake_sess.opened_iso = "2026-05-20T00:00:00+00:00"
    fake_sess.gdb_version = "GNU gdb 15.1"
    fake_sess.follow_fork_mode = "parent"
    fake_sess.command_count = 0

    fake_registry = MagicMock()
    fake_registry.open = AsyncMock(return_value=fake_sess)
    fake_registry.count_open = MagicMock(return_value=1)
    fake_registry._max = 8
    session_state.SESSION_REGISTRY = fake_registry

    result = await td.open_gdb_session(
        case_dir=tmp_case, sample_sha256=sha, init_commands=None, follow_fork_mode="parent"
    )

    fake_registry.open.assert_awaited_once()
    call_kwargs = fake_registry.open.await_args.kwargs
    assert call_kwargs["kind"] == "gdb"
    assert call_kwargs["sample_sha256"] == sha

    # D-DYN-TOOL-03 return dict shape
    expected_keys = {
        "session_id", "kind", "case_dir", "sample_sha256", "sample_path",
        "transcript_path", "opened_at", "gdb_version", "follow_fork_mode",
        "max_sessions", "open_count", "init_command_count", "warnings",
    }
    assert expected_keys.issubset(result.keys())
    assert result["kind"] == "gdb"
    assert result["session_id"] == "sid-1"


# ---------------------------------------------------------------------------
# Test 13-15: gdb_exec
# ---------------------------------------------------------------------------


async def test_gdb_exec_validates_then_calls_session_exec_one(monkeypatch, tmp_case, caps_ok):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_ok

    transcript = Path(tmp_case) / "dynamic"
    transcript.mkdir(parents=True, exist_ok=True)
    transcript_file = transcript / "sid-gdb-transcript.log"
    transcript_file.write_bytes(b"")

    fake_sess = MagicMock()
    fake_sess.session_id = "sid"
    fake_sess.case_dir = Path(tmp_case)
    fake_sess.transcript_path = transcript_file
    fake_sess.command_count = 0
    fake_sess.last_used_at = 0.0
    fake_sess.lock = _AsyncLockStub()
    fake_sess.exec_one = AsyncMock(return_value=(b"^done\n", False))

    fake_registry = MagicMock()
    fake_registry.get = MagicMock(return_value=fake_sess)
    fake_registry.close = AsyncMock(return_value={"ok": True})
    session_state.SESSION_REGISTRY = fake_registry

    result = await td.gdb_exec(session_id="sid", cmd="-info-functions")

    fake_sess.exec_one.assert_awaited_once()
    expected_keys = {
        "exit_code", "timed_out", "duration_s",
        "stdout_head", "stdout_truncated", "stdout_bytes_total",
        "stderr_head", "stderr_truncated", "stderr_bytes_total",
        "log_path", "argv", "slug",
        "session_id", "session_invalidated",
        "transcript_path", "mi_result_class", "mi_records", "parse_error",
    }
    assert expected_keys.issubset(result.keys())
    assert result["timed_out"] is False
    assert result["session_invalidated"] is False
    assert result["mi_result_class"] == "done"


async def test_gdb_exec_returns_session_invalidated_on_timeout(monkeypatch, tmp_case, caps_ok):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_ok

    transcript = Path(tmp_case) / "dynamic"
    transcript.mkdir(parents=True, exist_ok=True)
    transcript_file = transcript / "sid-gdb-transcript.log"
    transcript_file.write_bytes(b"")

    fake_sess = MagicMock()
    fake_sess.session_id = "sid"
    fake_sess.case_dir = Path(tmp_case)
    fake_sess.transcript_path = transcript_file
    fake_sess.command_count = 0
    fake_sess.last_used_at = 0.0
    fake_sess.lock = _AsyncLockStub()
    fake_sess.exec_one = AsyncMock(return_value=(b"partial", True))

    fake_registry = MagicMock()
    fake_registry.get = MagicMock(return_value=fake_sess)
    fake_registry.close = AsyncMock(return_value={"ok": True})
    session_state.SESSION_REGISTRY = fake_registry

    result = await td.gdb_exec(session_id="sid", cmd="-info-functions")
    assert result["timed_out"] is True
    assert result["session_invalidated"] is True
    fake_registry.close.assert_awaited_once()
    assert fake_registry.close.await_args.kwargs.get("reason") == "cmd_timeout"


async def test_gdb_exec_rejects_dangerous_cmd_pre_send(monkeypatch, tmp_case, caps_ok):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_ok

    fake_sess = MagicMock()
    fake_sess.exec_one = AsyncMock()

    fake_registry = MagicMock()
    fake_registry.get = MagicMock(return_value=fake_sess)
    session_state.SESSION_REGISTRY = fake_registry

    result = await td.gdb_exec(session_id="sid", cmd="python print(1)")
    assert result.get("error") == "gdb command refused"
    fake_sess.exec_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 16: close_gdb_session idempotent
# ---------------------------------------------------------------------------


async def test_close_gdb_session_idempotent(monkeypatch, tmp_case, caps_ok):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_ok

    calls = {"n": 0}

    async def fake_close(sid, *, reason="user"):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"ok": True, "already_closed": False, "session_id": sid}
        return {"ok": True, "already_closed": True, "session_id": sid}

    fake_registry = MagicMock()
    fake_registry.close = fake_close
    session_state.SESSION_REGISTRY = fake_registry

    r1 = await td.close_gdb_session("sid")
    r2 = await td.close_gdb_session("sid")
    assert r1["ok"] is True
    assert r2["ok"] is True
    assert r2.get("already_closed") is True


# ---------------------------------------------------------------------------
# Test 17-19: get_dynamic_capabilities
# ---------------------------------------------------------------------------


async def test_get_dynamic_capabilities_returns_snapshot(caps_ok):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_ok

    result = await td.get_dynamic_capabilities()
    expected_keys = {
        "probed_at", "dynamic_mode_enabled", "ptrace_scope", "ptrace_traceme_works",
        "binfmt_misc_mounted", "qemu_architectures", "qemu_static_binaries",
        "netns_feasible", "unshare_path", "gdb_path", "gdb_version",
        "strace_path", "ltrace_path", "warnings",
    }
    assert expected_keys.issubset(result.keys())
    assert result["ptrace_traceme_works"] is True


async def test_get_dynamic_capabilities_refresh_reprobes(monkeypatch, caps_ok):
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = None

    sentinel_caps = dataclasses.replace(caps_ok, ptrace_scope=1)
    probe_calls = {"n": 0}

    def fake_probe():
        probe_calls["n"] += 1
        return sentinel_caps

    monkeypatch.setattr(dynamic_mod, "probe_all", fake_probe)
    result = await td.get_dynamic_capabilities(refresh=True)
    assert probe_calls["n"] == 1
    assert result["ptrace_scope"] == 1
    assert dynamic_mod.CAPABILITIES is sentinel_caps


async def test_get_dynamic_capabilities_when_capabilities_slot_none():
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = None

    result = await td.get_dynamic_capabilities()
    assert result.get("error") == "capabilities not probed yet"
    assert "hint" in result


# ---------------------------------------------------------------------------
# Test 20: Tools NEVER raise
# ---------------------------------------------------------------------------


async def test_tools_never_raise(monkeypatch, tmp_case, caps_ok):
    """Induce internal exception via monkeypatch in resolve_sample. All trace tools
    AND open_gdb_session must return a structured dict containing 'error', NOT raise.
    """
    from mcp_gateway.tools import dynamic as td
    dynamic_mod.CAPABILITIES = caps_ok

    def boom(s):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("mcp_gateway.tools.samples.resolve_sample", boom)

    # set up registry so open_gdb_session has somewhere to dispatch
    fake_registry = MagicMock()
    fake_registry.open = AsyncMock()
    fake_registry.close = AsyncMock(return_value={"ok": True, "already_closed": False})
    fake_registry.get = MagicMock()
    fake_registry.count_open = MagicMock(return_value=0)
    fake_registry._max = 8
    session_state.SESSION_REGISTRY = fake_registry

    # 4 sample-resolving tools
    r1 = await td.run_strace(case_dir=tmp_case, sample_sha256="aa" * 32, profile="file_io")
    r2 = await td.run_ltrace(case_dir=tmp_case, sample_sha256="aa" * 32, profile="default")
    r3 = await td.run_qemu_user(case_dir=tmp_case, sample_sha256="aa" * 32, arch="arm", profile="default")
    r4 = await td.open_gdb_session(case_dir=tmp_case, sample_sha256="aa" * 32)
    for r in (r1, r2, r3, r4):
        assert isinstance(r, dict), f"expected dict, got {type(r).__name__}: {r!r}"
        assert "error" in r

    # gdb_exec without a session in registry -> structured error
    fake_registry.get = MagicMock(side_effect=KeyError("unknown"))
    r5 = await td.gdb_exec(session_id="unknown-sid", cmd="-info-functions")
    assert isinstance(r5, dict) and "error" in r5

    # close_gdb_session: induce exception in registry.close
    async def boom_close(sid, *, reason="user"):
        raise RuntimeError("close kaboom")

    fake_registry.close = boom_close
    r6 = await td.close_gdb_session("sid")
    assert isinstance(r6, dict) and "error" in r6

    # get_dynamic_capabilities: refresh raises in probe_all
    def boom_probe():
        raise RuntimeError("probe kaboom")

    monkeypatch.setattr(dynamic_mod, "probe_all", boom_probe)
    r7 = await td.get_dynamic_capabilities(refresh=True)
    assert isinstance(r7, dict) and "error" in r7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _AsyncLockStub:
    """A minimal async-context-manager stub used in place of asyncio.Lock for fakes."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False
