"""Tests for resolve_sample() path-traversal protection + subprocess runner."""
from __future__ import annotations
import asyncio
from pathlib import Path

import pytest

from mcp_gateway.tools import samples as samples_mod
from mcp_gateway.subprocess_runner import run_script


@pytest.fixture
def mocked_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    uploads = tmp_path / "uploads"
    examples = tmp_path / "examples"
    status = tmp_path / "status"
    for d in (uploads, examples, status):
        d.mkdir()
    monkeypatch.setattr(samples_mod, "UPLOADS_ROOT", uploads)
    monkeypatch.setattr(samples_mod, "EXAMPLES_ROOT", examples)
    monkeypatch.setattr(samples_mod, "STATUS_ROOT", status)
    monkeypatch.setattr(samples_mod, "ALLOWED_PREFIXES", (uploads, examples, status))
    return {"uploads": uploads, "examples": examples, "status": status}


# -------- resolve_sample --------

def test_resolve_sha256(mocked_dirs):
    sha = "a" * 64
    sample_dir = mocked_dirs["uploads"] / sha
    sample_dir.mkdir()
    f = sample_dir / "suspect.bin"
    f.write_bytes(b"\x00")
    assert samples_mod.resolve_sample(sha) == str(f.resolve())


def test_resolve_sha256_not_found(mocked_dirs):
    sha = "b" * 64
    with pytest.raises(FileNotFoundError):
        samples_mod.resolve_sample(sha)


def test_resolve_path_under_uploads(mocked_dirs):
    f = mocked_dirs["uploads"] / "raw.bin"
    f.write_bytes(b"\x00")
    assert samples_mod.resolve_sample(str(f)) == str(f.resolve())


def test_resolve_path_under_examples(mocked_dirs):
    f = mocked_dirs["examples"] / "good.bin"
    f.write_bytes(b"\x00")
    assert samples_mod.resolve_sample(str(f)) == str(f.resolve())


def test_resolve_traversal_rejected(mocked_dirs):
    with pytest.raises(ValueError, match="traversal"):
        samples_mod.resolve_sample("../etc/passwd")


def test_resolve_outside_allowed_rejected(mocked_dirs):
    with pytest.raises(ValueError, match="not under allowed prefixes"):
        samples_mod.resolve_sample("/etc/passwd")


def test_resolve_traversal_via_allowed_prefix_rejected(mocked_dirs):
    # /<uploads>/../etc — canonicalizes OUT of allowed tree
    sneaky = str(mocked_dirs["uploads"] / ".." / "etc")
    with pytest.raises(ValueError):
        samples_mod.resolve_sample(sneaky)


def test_resolve_empty_string(mocked_dirs):
    with pytest.raises(ValueError):
        samples_mod.resolve_sample("")


# -------- run_script --------

async def test_run_script_echo():
    # pytest-asyncio auto mode (asyncio_mode="auto" in pyproject.toml) picks up async tests.
    # Avoids deprecated asyncio.get_event_loop().run_until_complete() which breaks on Python 3.12+.
    result = await run_script(["/bin/echo", "hello"], cwd="/tmp")
    assert result["exit_code"] == 0
    assert "hello" in result["stdout"]


async def test_run_script_nonzero_exit_does_not_raise():
    result = await run_script(["/bin/false"], cwd="/tmp")
    assert result["exit_code"] == 1


async def test_run_script_timeout():
    with pytest.raises(asyncio.TimeoutError):
        await run_script(["/bin/sleep", "60"], cwd="/tmp", timeout=0.2)


def test_run_script_never_uses_shell_true():
    import inspect
    src = inspect.getsource(run_script)
    assert "shell=True" not in src, "T-02-SUBPROC: run_script must not use shell=True"
