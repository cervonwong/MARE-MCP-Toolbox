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
