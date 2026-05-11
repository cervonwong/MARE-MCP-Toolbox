"""E2E test fixtures (D-15).

Tests in this directory require a RUNNING gateway. The fixtures resolve the
gateway URL + bearer token from the environment (preferred) or fall back to
workspace/.mcp-gateway-token in the repo. If neither resolves OR /healthz is
unreachable, the entire e2e session is skipped — never a hard failure.

Locked env-var convention (Phase 4): MARE_GATEWAY_URL + MARE_GATEWAY_TOKEN.
Backwards-compatible fallback: MCP_GATEWAY_TOKEN (Phase 2/3 internal name).
"""

from __future__ import annotations
import os
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TOKEN_FILE = REPO_ROOT / "workspace" / ".mcp-gateway-token"


@pytest.fixture(scope="session")
def gateway_url() -> str:
    """Base URL for the gateway (NO trailing /mcp). Default 127.0.0.1:8080."""
    raw = os.environ.get("MARE_GATEWAY_URL", "http://127.0.0.1:8080/mcp")
    # Conftest stores the BASE; per-test code appends /mcp explicitly.
    return raw.rstrip("/").removesuffix("/mcp").rstrip("/") or "http://127.0.0.1:8080"


@pytest.fixture(scope="session")
def bearer_token() -> str:
    """Resolve bearer token: env var first, then workspace/.mcp-gateway-token; else skip."""
    tok = os.environ.get("MARE_GATEWAY_TOKEN") or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        return tok.strip()
    if TOKEN_FILE.exists() and TOKEN_FILE.stat().st_size > 0:
        return TOKEN_FILE.read_text().strip()
    pytest.skip(
        f"no gateway token found — start the container with `./run_docker.sh --remote` "
        f"(checked env: MARE_GATEWAY_TOKEN, MCP_GATEWAY_TOKEN; file: {TOKEN_FILE})"
    )


@pytest.fixture(scope="session")
def gateway_alive(gateway_url: str) -> str:
    """Skip the entire e2e session if the gateway isn't reachable."""
    try:
        r = httpx.get(f"{gateway_url}/healthz", timeout=2.0)
        if r.status_code != 200:
            pytest.skip(f"gateway /healthz returned {r.status_code}")
    except (httpx.ConnectError, httpx.ReadTimeout) as exc:
        pytest.skip(f"gateway not reachable at {gateway_url} ({exc})")
    return gateway_url


@pytest.fixture(scope="session")
def mcp_client(gateway_alive: str, bearer_token: str):
    """httpx.Client preconfigured with bearer + Streamable HTTP headers; runs `initialize` once."""
    with httpx.Client(
        base_url=gateway_alive,
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        timeout=30.0,
        # Per RESEARCH Pitfall 4: Authorization is preserved on same-origin redirects;
        # we hit /mcp directly to avoid any redirect anyway.
        follow_redirects=False,
    ) as client:
        init = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "phase4-pytest", "version": "1"},
                },
            },
        )
        if init.status_code != 200:
            pytest.skip(
                f"gateway initialize returned {init.status_code}: {init.text[:200]}"
            )
        yield client


@pytest.fixture(scope="session")
def unauthed_client(gateway_alive: str):
    """httpx.Client with NO Authorization header — used by auth-bypass tests."""
    with httpx.Client(
        base_url=gateway_alive,
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        timeout=10.0,
        follow_redirects=False,
    ) as client:
        yield client
