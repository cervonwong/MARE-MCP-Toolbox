"""Tests for resolve_sample() path-traversal protection + subprocess runner."""
from __future__ import annotations
import asyncio
from pathlib import Path

import pytest

from mcp_gateway.tools import samples as samples_mod
from mcp_gateway.subprocess_runner import _resolve_scripts_dir, run_script


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


async def test_run_script_starts_new_process_session(monkeypatch):
    captured_kwargs = {}

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return b"ok", b""

    async def fake_create_subprocess_exec(*_argv, **kwargs):
        captured_kwargs.update(kwargs)
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await run_script(["/bin/echo", "ok"], cwd="/tmp")

    assert result["exit_code"] == 0
    assert captured_kwargs["start_new_session"] is True


async def test_run_script_timeout_kills_process_group(monkeypatch):
    calls = []

    class FakeProc:
        pid = 12345
        returncode = None

        async def communicate(self):
            await asyncio.sleep(60)
            return b"", b""

        async def wait(self):
            calls.append(("wait", self.pid))
            self.returncode = -9

    async def fake_create_subprocess_exec(*_argv, **_kwargs):
        return FakeProc()

    def fake_killpg(pid, sig):
        calls.append(("killpg", pid, sig))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr("mcp_gateway.subprocess_runner.os.killpg", fake_killpg)

    with pytest.raises(asyncio.TimeoutError):
        await run_script(["/bin/sleep", "60"], cwd="/tmp", timeout=0.01)

    assert calls == [("killpg", 12345, 9), ("wait", 12345)]


def test_run_script_never_uses_shell_true():
    import inspect
    src = inspect.getsource(run_script)
    assert "shell=True" not in src, "T-02-SUBPROC: run_script must not use shell=True"


def test_resolve_scripts_dir_prefers_codex_copy(tmp_path, monkeypatch):
    agent = tmp_path / "agent"
    codex_scripts = agent / ".codex" / "skills" / "malware-analysis-orchestrator" / "scripts"
    claude_scripts = agent / ".claude" / "skills" / "malware-analysis-orchestrator" / "scripts"
    codex_scripts.mkdir(parents=True)
    claude_scripts.mkdir(parents=True)
    monkeypatch.delenv("MCP_GATEWAY_SCRIPTS_DIR", raising=False)
    monkeypatch.setattr("mcp_gateway.subprocess_runner.Path", lambda value: Path(str(value).replace("/agent", str(agent))))

    assert _resolve_scripts_dir() == codex_scripts


def test_resolve_scripts_dir_honors_env(monkeypatch):
    monkeypatch.setenv("MCP_GATEWAY_SCRIPTS_DIR", "/custom/scripts")

    assert _resolve_scripts_dir() == Path("/custom/scripts")
