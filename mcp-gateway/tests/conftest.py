"""Shared test fixtures for mcp-gateway."""
from __future__ import annotations
import os
import secrets
import shutil
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP


def _require_r2_or_skip() -> None:
    """Phase 8 r2-session tests require the `r2` binary on PATH.

    On hosts without r2 (typical dev/CI executor), skip cleanly. Inside the
    container image (Kali base provides `radare2`), tests run for real.
    """
    if shutil.which("r2") is None:
        pytest.skip("r2 unavailable on host; Kali container image provides radare2 by default")


# ---------------------------------------------------------------------------
# Phase 11 require-helpers for dynamic-lab-mode tools (gdb / strace / ltrace /
# qemu-user / netns). Each is `def _require_*_or_skip` so test modules can do
# `from tests.conftest import _require_<tool>_or_skip; _require_<tool>_or_skip()`
# at the top of any test that spawns the actual binary. Mirrors the
# `_require_r2_or_skip` pattern above so CI executors without the tool can
# skip cleanly while the container exercise the real path.
# ---------------------------------------------------------------------------
def _require_gdb_or_skip() -> None:
    """Phase 11 gdb-session tests require the `gdb` binary on PATH."""
    import shutil
    if shutil.which("gdb") is None:
        pytest.skip("gdb unavailable on host")


def _require_strace_or_skip() -> None:
    """Phase 11 strace tests require the `strace` binary on PATH."""
    import shutil
    if shutil.which("strace") is None:
        pytest.skip("strace unavailable on host")


def _require_ltrace_or_skip() -> None:
    """Phase 11 ltrace tests require the `ltrace` binary on PATH."""
    import shutil
    if shutil.which("ltrace") is None:
        pytest.skip("ltrace unavailable on host")


def _require_qemu_user_or_skip(arch: str = "arm") -> None:
    """Phase 11 qemu-user tests require qemu-<arch>-static or qemu-<arch>.

    Defaults to arm. Callers pass `arch="aarch64"` etc. for other targets.
    """
    import shutil
    if shutil.which(f"qemu-{arch}-static") is None and shutil.which(f"qemu-{arch}") is None:
        pytest.skip(f"qemu-{arch}(-static) unavailable on host")


def _require_netns_or_skip() -> None:
    """Phase 11 netns-enforcement tests require `unshare --net true` to succeed.

    On hosts where seccomp blocks `unshare(CLONE_NEWNET)` or where CAP_SYS_ADMIN
    is missing, the probe fails and we skip cleanly. Inside the container with
    `seccomp=unconfined` (CLAUDE.md posture), this returns rc=0.
    """
    import subprocess
    try:
        rc = subprocess.run(
            ["unshare", "--net", "true"],
            capture_output=True, timeout=3,
        ).returncode
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("unshare unavailable or netns probe failed")
    if rc != 0:
        pytest.skip("unshare --net failed (likely seccomp restriction)")


@pytest.fixture
def bearer_token() -> str:
    """Deterministic-per-test bearer token used by auth fixtures."""
    return secrets.token_urlsafe(16)


@pytest.fixture
def tmp_upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setenv("MCP_GATEWAY_UPLOAD_DIR", str(d))
    return d


@pytest.fixture
def tmp_status_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "status"
    d.mkdir()
    monkeypatch.setenv("MCP_GATEWAY_STATUS_DIR", str(d))
    return d


@pytest.fixture
def fake_backend_mcp() -> FastMCP:
    """In-memory MCP server standing in for a real BN/Ghidra/IDA backend."""
    fake = FastMCP("fake-backend", stateless_http=True)

    @fake.tool()
    def list_funcs() -> list[str]:
        return ["main", "init", "doWork"]

    @fake.tool()
    def decompile(function: str) -> str:
        return f"int {function}() {{ return 0; }}"

    @fake.tool()
    def xrefs_to(function: str) -> list[str]:
        return [f"ref_to_{function}_1", f"ref_to_{function}_2"]

    return fake
