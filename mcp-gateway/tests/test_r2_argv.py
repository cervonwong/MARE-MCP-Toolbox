"""Phase 13 HARDEN-03 + HARDEN-04: r2 spawn-argv unit tests (no r2 binary required).

Captures the argv list passed to asyncio.create_subprocess_exec via monkeypatch.
Verifies the sandbox-related argv tokens are in the right order and that no
cfg.sandbox.grain override is emitted (D-08 RESOLUTION 2026-05-20).
"""
from __future__ import annotations
import asyncio
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


@pytest.mark.asyncio
async def test_argv_sandbox_flag_present_before_sample(monkeypatch, tmp_path):
    """HARDEN-03: with sandbox=True, argv contains '-e' 'cfg.sandbox=true' BEFORE sample."""
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
    assert "cfg.sandbox=true" in argv, f"cfg.sandbox=true missing from argv: {argv}"
    e_index = argv.index("-e")
    val_index = argv.index("cfg.sandbox=true")
    sample_index = argv.index(str(sample))
    assert e_index < val_index < sample_index, (
        f"argv ordering wrong: -e at {e_index}, cfg.sandbox=true at {val_index}, "
        f"sample at {sample_index}; full argv={argv}"
    )


@pytest.mark.asyncio
async def test_argv_sandbox_omitted_when_sandbox_false(monkeypatch, tmp_path):
    """HARDEN-03 unsafe-path: with sandbox=False, no cfg.sandbox token at all."""
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
