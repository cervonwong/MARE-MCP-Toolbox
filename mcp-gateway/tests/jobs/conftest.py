"""Shared fixtures for Phase 9 background-job tests."""
from __future__ import annotations

import importlib
import shutil
from pathlib import Path

import pytest


def _require_capa_or_skip() -> None:
    """Skip the test if `capa` binary not on PATH (host-dev usually missing; container has it)."""
    if shutil.which("capa") is None:
        pytest.skip("capa not on PATH (install via Kali container)")


@pytest.fixture
def case_dir_fixture(tmp_path: Path, monkeypatch) -> Path:
    """Provide a STATUS_ROOT-confined case_dir for tests.

    Creates tmp_path/status/<case>/ and monkeypatches samples.STATUS_ROOT so
    resolve_case_dir accepts the path. Returns the resolved (realpath) case-dir
    so resolve_case_dir's realpath comparison matches.
    """
    from mcp_gateway.tools import samples

    status_root = tmp_path / "status"
    status_root.mkdir(parents=True, exist_ok=True)
    case = status_root / "999-test-case"
    case.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(samples, "STATUS_ROOT", str(status_root), raising=True)
    # Return resolved path so callers can pass it directly to resolve_case_dir
    return Path(str(case))


@pytest.fixture
def registry_factory(monkeypatch):
    """Factory that constructs a BackgroundJobRegistry with optional env-overrides.

    Use the returned builder to apply test-scoped env values BEFORE the registry's
    module constants are read (via importlib.reload).

    Returns: a callable `_build(**kwargs)` that yields a fresh
    BackgroundJobRegistry. Pass `env={"MCP_GATEWAY_MAX_JOB_LOG_MB": 1}` to apply
    env-overrides + reload jobs module BEFORE constructing the registry.
    """
    from mcp_gateway import jobs as jobs_mod

    def _build(*, max_inflight=4, cancel_grace_s=10.0, max_completed=200,
               env: dict | None = None):
        if env:
            for k, v in env.items():
                monkeypatch.setenv(k, str(v))
            importlib.reload(jobs_mod)
        return jobs_mod.BackgroundJobRegistry(
            max_inflight=max_inflight,
            cancel_grace_s=cancel_grace_s,
            max_completed=max_completed,
        )

    return _build


class FakeContext:
    """Minimal MCP Context double for D-16 Tier-2 progress tests."""

    def __init__(self, session_id: str = "fake-session"):
        self.session_id = session_id
        self.calls: list[tuple] = []

    async def report_progress(self, progress, total=None, message=None):
        self.calls.append((progress, total, message))


@pytest.fixture
def fake_ctx():
    return FakeContext()
