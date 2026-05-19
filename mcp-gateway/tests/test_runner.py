"""Tests for ReToolRunner (Phase 6 / FOUND-02, FOUND-03).

Test layout matches mcp-gateway/tests/test_image_hash.py -- one fixture per test,
hermetic via tmp_path, no shared state across tests. Asyncio mode 'auto' (see
pyproject.toml) means async def test_* runs without explicit @pytest.mark.asyncio.

The runner-source grep test (`test_runner_never_uses_shell_true`) mirrors the
v1.0 pattern at tests/test_sample_resolution.py line 148.
"""
from __future__ import annotations

import asyncio
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import pytest

from mcp_gateway import runner as runner_module
from mcp_gateway.runner import ReToolRunner, run_tool, DEFAULT_TIMEOUT_S


def _make_case_dir(tmp_path: Path) -> Path:
    case = tmp_path / "case"
    case.mkdir()
    return case


# ---- SC-1a: chokepoint integrity (grep-the-source) ----
def test_runner_never_uses_shell_true() -> None:
    src = Path(runner_module.__file__).read_text(encoding="utf-8")
    assert "shell=True" not in src, "ReToolRunner must never use shell=True (D-04, T-6-02)"


# ---- SC-1b: cwd is resolved case_dir ----
async def test_cwd_is_resolved_case_dir(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    runner = ReToolRunner(case_dir=case, slug="cwd-test", timeout=10.0)
    result = await runner.run([sys.executable, "-c", "import os, sys; sys.stdout.write(os.getcwd())"])
    assert result["exit_code"] == 0
    assert result["stdout_head"].strip() == str(case.resolve())


# ---- SC-1c: timeout fires pgroup SIGKILL ----
async def test_timeout_kills_process_group(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    # D-20: subprocess must be dead within 200 ms of timeout firing.
    # The runner internally catches asyncio.TimeoutError after wait_for(timeout=0.5),
    # so the test layer cannot record a post-timeout-only t0. We assert on the
    # combined budget: wait_for(0.5) + cleanup(0.2) = 0.7s upper bound.
    runner = ReToolRunner(case_dir=case, slug="timeout-test", timeout=0.5)
    t0 = time.monotonic()
    result = await runner.run(["sleep", "60"])
    elapsed = time.monotonic() - t0
    assert result["timed_out"] is True
    assert elapsed < 0.5 + 0.2, (
        f"timeout+cleanup took {elapsed:.3f}s, contract is wait_for(0.5) + 0.2s cleanup per D-20"
    )


# ---- SC-1d: CancelledError -> killpg within 200 ms (Pitfall 18) ----
async def test_cancel_propagates_to_killpg(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    runner = ReToolRunner(case_dir=case, slug="cancel-test", timeout=60.0)
    task = asyncio.create_task(runner.run(["sleep", "60"]))
    await asyncio.sleep(0.1)
    t0 = time.monotonic()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    elapsed = time.monotonic() - t0
    # D-20: cancel-to-dead MUST be <200 ms.
    assert elapsed < 0.2, f"cancel-to-dead took {elapsed:.3f}s, contract is <0.2s per D-20"


# ---- SC-2: return shape locked to D-03 ----
async def test_return_shape_locked(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    runner = ReToolRunner(case_dir=case, slug="shape-test", timeout=10.0)
    result = await runner.run(["bash", "-c", "echo hi"])
    # All 12 D-03 keys, in order:
    expected_keys = [
        "exit_code", "timed_out", "duration_s",
        "stdout_head", "stdout_truncated", "stdout_bytes_total",
        "stderr_head", "stderr_truncated", "stderr_bytes_total",
        "log_path", "argv", "slug",
    ]
    assert list(result.keys()) == expected_keys
    assert isinstance(result["exit_code"], int)
    assert isinstance(result["timed_out"], bool)
    assert isinstance(result["duration_s"], float)
    assert isinstance(result["stdout_head"], str)
    assert isinstance(result["log_path"], str)
    assert isinstance(result["argv"], list)
    assert result["slug"] == "shape-test"
    assert result["argv"] == ["bash", "-c", "echo hi"]


# ---- SC-3: auto-capture to tool-logs/, log_path is relative ----
async def test_log_capture_and_head_alignment(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    runner = ReToolRunner(case_dir=case, slug="capture-test", timeout=10.0)
    result = await runner.run(["bash", "-c", "printf 'line1\\nline2\\n'"])
    log_rel = Path(result["log_path"])
    assert not log_rel.is_absolute(), "log_path must be relative to case_dir (D-10)"
    assert log_rel.parts[0] == "tool-logs"
    log_abs = case / log_rel
    assert log_abs.exists()
    on_disk = log_abs.read_bytes()
    assert b"line1\n" in on_disk
    # Head preview matches the first bytes of the file (with ANSI stripped -- no ANSI in echo output).
    assert result["stdout_head"].startswith("line1\nline2\n")


# ---- SC-4: 100 MB urandom completes with bounded RSS ----
@pytest.mark.slow
async def test_100mb_urandom_bounded_rss(tmp_path: Path) -> None:
    if not sys.platform.startswith("linux"):
        pytest.skip("Linux-only ru_maxrss semantics (KB on Linux, bytes elsewhere)")
    case = _make_case_dir(tmp_path)
    rss_before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    runner = ReToolRunner(case_dir=case, slug="urandom-100mb", timeout=60.0)
    result = await runner.run(["bash", "-c", "head -c 104857600 /dev/urandom"])
    rss_after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    assert result["exit_code"] == 0
    assert result["stdout_bytes_total"] == 104857600
    assert result["stdout_truncated"] is True
    delta_kb = rss_after - rss_before
    assert delta_kb < 32 * 1024, f"RSS grew by {delta_kb // 1024} MB -- possible OOM regression"


# ---- D-08: env-var validation at module import ----
def test_env_validation_rejects_bad_values() -> None:
    """Importing mcp_gateway.runner with a non-numeric env var must RuntimeError at import."""
    bad_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "MCP_GATEWAY_RUNNER_DEFAULT_TIMEOUT_S": "abc",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import mcp_gateway.runner"],
        env=bad_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "RuntimeError" in result.stderr or "must be a float" in result.stderr


# ---- D-08 + RESEARCH 55 s margin: default timeout sane ----
def test_default_timeout_below_mcp_cap() -> None:
    assert 0 < DEFAULT_TIMEOUT_S <= 55.0, (
        f"DEFAULT_TIMEOUT_S={DEFAULT_TIMEOUT_S}; must be >0 and <=55s (5s margin under MCP 60s cap)"
    )


# ---- Manifest regression: no new pip deps ----
def test_no_new_pip_deps() -> None:
    src = Path(runner_module.__file__).read_text(encoding="utf-8")
    forbidden = ("import psutil", "from psutil", "import aiofiles", "from aiofiles")
    for token in forbidden:
        assert token not in src, f"runner.py must not import {token!r} -- stdlib + anyio only"


# ---- Phase 9 Q4: proc_callback kwarg ----
@pytest.mark.asyncio
async def test_proc_callback_fires_once_with_live_process(tmp_path):
    captured = []
    runner = ReToolRunner(case_dir=tmp_path, slug="cb_probe", timeout=10.0)
    result = await runner.run(["echo", "hi"], proc_callback=lambda p: captured.append(p))
    assert len(captured) == 1
    assert hasattr(captured[0], "pid")
    assert captured[0].returncode == 0
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_proc_callback_keyword_only(tmp_path):
    runner = ReToolRunner(case_dir=tmp_path, slug="cb_probe", timeout=10.0)
    with pytest.raises(TypeError):
        await runner.run(["echo", "hi"], lambda p: None)


@pytest.mark.asyncio
async def test_proc_callback_default_none_no_regression(tmp_path):
    runner = ReToolRunner(case_dir=tmp_path, slug="cb_probe", timeout=10.0)
    result = await runner.run(["echo", "hi"])
    for k in ("exit_code", "timed_out", "duration_s", "stdout_head",
              "stdout_truncated", "stdout_bytes_total", "stderr_head",
              "stderr_truncated", "stderr_bytes_total", "log_path", "argv", "slug"):
        assert k in result


@pytest.mark.asyncio
async def test_proc_callback_exception_propagates(tmp_path):
    runner = ReToolRunner(case_dir=tmp_path, slug="cb_probe", timeout=10.0)
    def boom(p):
        raise RuntimeError("by design")
    with pytest.raises(RuntimeError, match="by design"):
        await runner.run(["echo", "hi"], proc_callback=boom)
