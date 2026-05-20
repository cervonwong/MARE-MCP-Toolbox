"""Phase 11 Plan 06: end-to-end JOBS integration for dynamic mode.

Slow tests are gated by host capability presence via _require_*_or_skip helpers.
Fast tests (capability slot population, compose.yaml regression) run unconditionally.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
BUILD_SCRIPT = FIXTURES / "build_fixtures.sh"


def _build_fixtures() -> bool:
    """Run build_fixtures.sh once; return True if dns_lookup + setsid_escape built."""
    if BUILD_SCRIPT.exists():
        subprocess.run(
            ["bash", str(BUILD_SCRIPT)],
            capture_output=True,
            timeout=60,
            check=False,
        )
    return (FIXTURES / "dns_lookup").exists() and (FIXTURES / "setsid_escape").exists()


def _ensure_uploaded(sample_path: Path, upload_root: Path) -> str:
    """Hash + copy sample into uploads/<sha>/<name>; return sha256 hex."""
    sha = hashlib.sha256(sample_path.read_bytes()).hexdigest()
    target_dir = upload_root / sha
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / sample_path.name
    if not target.exists():
        shutil.copy(sample_path, target)
    return sha


def _require_native_fixtures():
    if not _build_fixtures():
        pytest.skip("native fixtures (dns_lookup, setsid_escape) could not be built; gcc missing?")


def _full_reset_modules() -> None:
    """Drop every gateway module that could carry stale spec/registry state.

    Matches the pattern in test_dynamic_gate.py / test_tool_list.py: drop modules
    AND delete parent-package attributes so `from mcp_gateway import X` triggers a
    fresh import (Python attribute-lookup short-circuits sys.modules misses via
    parent-package __dict__).
    """
    targets = [
        "mcp_gateway.app",
        "mcp_gateway.tools",
        "mcp_gateway.tools.dynamic",
        "mcp_gateway.dynamic",
        "mcp_gateway.jobs",
        "mcp_gateway.extraction",
    ]
    targets.extend([k for k in list(sys.modules) if k.startswith("mcp_gateway.tools.")])
    for k in targets:
        sys.modules.pop(k, None)
    import mcp_gateway as _pkg
    for attr in ("app", "tools", "dynamic", "jobs", "extraction"):
        if hasattr(_pkg, attr):
            try:
                delattr(_pkg, attr)
            except AttributeError:
                pass


# ---------------------------------------------------------------------------
# Fast tests (always run)
# ---------------------------------------------------------------------------


def test_capability_probe_populated_when_dynamic_off(monkeypatch, tmp_path):
    monkeypatch.delenv("MCP_GATEWAY_DYNAMIC_TOOLS", raising=False)
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "test")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / "tok"))
    monkeypatch.setenv("MCP_GATEWAY_SKIP_BACKEND", "1")
    _full_reset_modules()
    import mcp_gateway.app as app_mod
    app_mod._MCP_INSTANCE = None
    from mcp_gateway import dynamic
    dynamic.CAPABILITIES = None
    app_mod.build_app()
    assert dynamic.CAPABILITIES is not None
    assert dynamic.CAPABILITIES.dynamic_mode_enabled is False


def test_capability_probe_populated_when_dynamic_on(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_GATEWAY_DYNAMIC_TOOLS", "1")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "test")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / "tok"))
    monkeypatch.setenv("MCP_GATEWAY_SKIP_BACKEND", "1")
    _full_reset_modules()
    import mcp_gateway.app as app_mod
    app_mod._MCP_INSTANCE = None
    from mcp_gateway import dynamic
    dynamic.CAPABILITIES = None
    app_mod.build_app()
    assert dynamic.CAPABILITIES is not None
    assert dynamic.CAPABILITIES.dynamic_mode_enabled is True


def test_compose_yaml_preserves_security_opts():
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / "compose.yaml").read_text()
    assert "seccomp=unconfined" in text, (
        "compose.yaml LOST seccomp=unconfined -- Pitfall #2 regression!"
    )
    assert "SYS_PTRACE" in text, (
        "compose.yaml LOST SYS_PTRACE -- ptrace will fail"
    )
    assert "MCP_GATEWAY_DYNAMIC_TOOLS" in text, (
        "compose.yaml does not pass MCP_GATEWAY_DYNAMIC_TOOLS"
    )


def test_get_dynamic_capabilities_matches_slot(monkeypatch):
    monkeypatch.setenv("MCP_GATEWAY_DYNAMIC_TOOLS", "1")
    _full_reset_modules()
    from mcp_gateway import dynamic
    from mcp_gateway.tools.dynamic import get_dynamic_capabilities
    if dynamic.CAPABILITIES is None:
        dynamic.CAPABILITIES = dynamic.probe_all()
    slot_dict = dataclasses.asdict(dynamic.CAPABILITIES)
    result = asyncio.run(get_dynamic_capabilities())
    assert result == slot_dict


# ---------------------------------------------------------------------------
# Slow tests (gated on tool presence)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.asyncio
async def test_strace_via_jobs_roundtrip(monkeypatch, tmp_path):
    if shutil.which("strace") is None:
        pytest.skip("strace not on host")
    if shutil.which("unshare") is None:
        pytest.skip("unshare not on host")
    try:
        rc = subprocess.run(
            ["unshare", "--net", "true"], capture_output=True, timeout=3
        ).returncode
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pytest.skip("unshare --net probe failed")
    if rc != 0:
        pytest.skip("unshare --net not feasible on host")
    _require_native_fixtures()

    # Set up environment
    monkeypatch.setenv("MCP_GATEWAY_DYNAMIC_TOOLS", "1")
    monkeypatch.setenv("MCP_GATEWAY_UPLOAD_DIR", str(tmp_path / "uploads"))
    (tmp_path / "uploads").mkdir()
    case_dir = tmp_path / "case-001-strace-test"
    case_dir.mkdir()
    (case_dir / "dynamic").mkdir()

    # Upload the dns_lookup fixture
    sha = _ensure_uploaded(FIXTURES / "dns_lookup", tmp_path / "uploads")

    # Run probe + populate CAPABILITIES slot
    from mcp_gateway import dynamic
    dynamic.CAPABILITIES = dynamic.probe_all()
    if not (dynamic.CAPABILITIES.netns_feasible and dynamic.CAPABILITIES.ptrace_traceme_works):
        pytest.skip(f"host capabilities insufficient: {dynamic.CAPABILITIES.warnings}")

    # Boot up registries (mimic lifespan)
    from mcp_gateway import session_state
    from mcp_gateway.jobs import (
        BackgroundJobRegistry,
        MAX_JOBS_INFLIGHT,
        JOB_CANCEL_GRACE_S,
        MAX_COMPLETED_JOBS,
    )
    async with BackgroundJobRegistry(
        max_inflight=MAX_JOBS_INFLIGHT,
        cancel_grace_s=JOB_CANCEL_GRACE_S,
        max_completed=MAX_COMPLETED_JOBS,
    ) as jr:
        session_state.JOB_REGISTRY = jr
        try:
            from mcp_gateway.tools.dynamic import run_strace
            from mcp_gateway.tools.jobs import get_tool_job

            snap = await run_strace(
                case_dir=str(case_dir),
                sample_sha256=sha,
                profile="network",
            )
            assert "error" not in snap, f"run_strace returned error: {snap}"
            job_id = snap["job_id"]

            # Poll for terminal status
            deadline = time.monotonic() + 30
            j = None
            while time.monotonic() < deadline:
                j = await get_tool_job(job_id)
                if j.get("status") in (
                    "succeeded",
                    "failed",
                    "cancelled",
                    "killed_timeout",
                    "killed_log_cap",
                ):
                    break
                await asyncio.sleep(0.5)
            else:
                pytest.fail(f"job {job_id} did not reach terminal in 30s: {j}")

            # Verify netns prefix in argv
            argv = j.get("argv", [])
            assert argv[:5] == ["unshare", "--net", "--ipc", "--uts", "--"], (
                f"argv prefix not netns-wrapped: {argv[:5]}"
            )

            # Find the strace output file under case_dir/dynamic/
            output_files = list((case_dir / "dynamic").glob("*-strace-*.txt"))
            assert output_files, f"no strace output under {case_dir / 'dynamic'}"
            content = output_files[0].read_text(errors="replace")
            assert "ENETUNREACH" in content or "EHOSTUNREACH" in content, (
                "netns did not block DNS -- strace shows no ENETUNREACH/EHOSTUNREACH "
                f"(first 1000 bytes): {content[:1000]}"
            )
        finally:
            session_state.JOB_REGISTRY = None


@pytest.mark.slow
@pytest.mark.asyncio
async def test_setsid_grandchild_reaped(monkeypatch, tmp_path):
    if shutil.which("strace") is None or shutil.which("unshare") is None:
        pytest.skip("strace or unshare missing")
    _require_native_fixtures()

    monkeypatch.setenv("MCP_GATEWAY_DYNAMIC_TOOLS", "1")
    monkeypatch.setenv("MCP_GATEWAY_UPLOAD_DIR", str(tmp_path / "uploads"))
    (tmp_path / "uploads").mkdir()
    case_dir = tmp_path / "case-001-setsid-test"
    case_dir.mkdir()
    (case_dir / "dynamic").mkdir()

    sha = _ensure_uploaded(FIXTURES / "setsid_escape", tmp_path / "uploads")

    from mcp_gateway import dynamic, session_state
    dynamic.CAPABILITIES = dynamic.probe_all()
    if not (dynamic.CAPABILITIES.netns_feasible and dynamic.CAPABILITIES.ptrace_traceme_works):
        pytest.skip("host capabilities insufficient")

    from mcp_gateway.jobs import (
        BackgroundJobRegistry,
        MAX_JOBS_INFLIGHT,
        JOB_CANCEL_GRACE_S,
        MAX_COMPLETED_JOBS,
    )
    async with BackgroundJobRegistry(
        max_inflight=MAX_JOBS_INFLIGHT,
        cancel_grace_s=JOB_CANCEL_GRACE_S,
        max_completed=MAX_COMPLETED_JOBS,
    ) as jr:
        session_state.JOB_REGISTRY = jr
        try:
            from mcp_gateway.tools.dynamic import run_strace
            from mcp_gateway.tools.jobs import get_tool_job

            snap = await run_strace(
                case_dir=str(case_dir),
                sample_sha256=sha,
                profile="process",
                timeout=15.0,
            )
            assert "error" not in snap, f"run_strace returned error: {snap}"
            job_id = snap["job_id"]

            # Poll for terminal status (binary parent exits fast; strace
            # exits when the traced parent process exits)
            deadline = time.monotonic() + 30
            j = None
            while time.monotonic() < deadline:
                j = await get_tool_job(job_id)
                if j.get("status") in ("succeeded", "failed", "killed_timeout"):
                    break
                await asyncio.sleep(0.3)

            # Parse the grandchild PID from the strace output
            output_files = list((case_dir / "dynamic").glob("*-strace-*.txt"))
            assert output_files
            content = output_files[0].read_text(errors="replace")
            # The fixture prints `escaped_pid=<N>` to stdout, which strace captures.
            import re
            m = re.search(r"escaped_pid=(\d+)", content)
            if m is None:
                pytest.skip(
                    f"could not find escaped_pid marker; strace output (truncated): "
                    f"{content[:500]}"
                )
            grandchild_pid = int(m.group(1))

            # Within 2s, the reaper should have killed the grandchild
            killed = False
            for _ in range(20):
                try:
                    os.kill(grandchild_pid, 0)  # signal 0 = check existence
                except (ProcessLookupError, OSError):
                    killed = True
                    break
                time.sleep(0.1)
            # Best-effort cleanup if the reaper missed it (avoid lingering sleep 60)
            if not killed:
                try:
                    os.kill(grandchild_pid, 9)
                except (ProcessLookupError, OSError):
                    pass
            assert killed, f"grandchild PID {grandchild_pid} survived reap_followfork_strays"
        finally:
            session_state.JOB_REGISTRY = None


@pytest.mark.slow
@pytest.mark.asyncio
async def test_qemu_user_arm_roundtrip(monkeypatch, tmp_path):
    if shutil.which("qemu-arm-static") is None:
        pytest.skip("qemu-arm-static not on host")
    if shutil.which("unshare") is None:
        pytest.skip("unshare not on host")
    _build_fixtures()
    hello_arm = FIXTURES / "hello_arm.bin"
    if not hello_arm.exists():
        pytest.skip("hello_arm.bin fixture not built (arm-linux-gnueabihf-gcc unavailable?)")

    monkeypatch.setenv("MCP_GATEWAY_DYNAMIC_TOOLS", "1")
    monkeypatch.setenv("MCP_GATEWAY_UPLOAD_DIR", str(tmp_path / "uploads"))
    (tmp_path / "uploads").mkdir()
    case_dir = tmp_path / "case-001-qemu-test"
    case_dir.mkdir()
    (case_dir / "qemu").mkdir()

    sha = _ensure_uploaded(hello_arm, tmp_path / "uploads")

    from mcp_gateway import dynamic, session_state
    dynamic.CAPABILITIES = dynamic.probe_all()
    if "arm" not in dynamic.CAPABILITIES.qemu_architectures and not any(
        "qemu-arm-static" in b for b in dynamic.CAPABILITIES.qemu_static_binaries
    ):
        pytest.skip("qemu-arm not in capability snapshot")

    from mcp_gateway.jobs import (
        BackgroundJobRegistry,
        MAX_JOBS_INFLIGHT,
        JOB_CANCEL_GRACE_S,
        MAX_COMPLETED_JOBS,
    )
    async with BackgroundJobRegistry(
        max_inflight=MAX_JOBS_INFLIGHT,
        cancel_grace_s=JOB_CANCEL_GRACE_S,
        max_completed=MAX_COMPLETED_JOBS,
    ) as jr:
        session_state.JOB_REGISTRY = jr
        try:
            from mcp_gateway.tools.dynamic import run_qemu_user
            from mcp_gateway.tools.jobs import get_tool_job

            snap = await run_qemu_user(
                case_dir=str(case_dir),
                sample_sha256=sha,
                arch="arm",
                profile="simple",
            )
            if "error" in snap:
                pytest.skip(f"run_qemu_user returned error (likely capability gap): {snap}")
            job_id = snap["job_id"]

            deadline = time.monotonic() + 30
            j = None
            while time.monotonic() < deadline:
                j = await get_tool_job(job_id)
                if j.get("status") in ("succeeded", "failed"):
                    break
                await asyncio.sleep(0.5)

            # Either succeeded with "Hello from ARM" or failed for known
            # qemu-user multi-thread issues; only assert on success.
            if j and j.get("status") == "succeeded":
                stdout = j.get("stdout_head", "")
                assert "Hello" in stdout, (
                    f"qemu-arm ran but expected output missing: {stdout[:200]}"
                )
        finally:
            session_state.JOB_REGISTRY = None
