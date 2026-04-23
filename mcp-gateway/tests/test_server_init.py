"""Test that the Starlette app initializes FastMCP over Streamable HTTP properly.

Maps to VALIDATION.md row GW-01 (Streamable HTTP initialize returns session id).
Uses Starlette's TestClient with lifespan triggering mcp.session_manager.run().
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "test-token")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / "tok"))
    monkeypatch.setenv("MCP_GATEWAY_SKIP_BACKEND", "1")
    # Reset the module-level FastMCP singleton and tool state between tests
    import mcp_gateway.app as app_mod
    app_mod._MCP_INSTANCE = None
    return app_mod.build_app()


def test_healthz_open(app):
    with TestClient(app) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"ok": True}


def test_healthz_open_ignores_origin(app):
    with TestClient(app) as c:
        r = c.get("/healthz", headers={"Origin": "http://evil.com"})
        # OriginMiddleware runs on all paths; verify /healthz returns 403 on evil Origin.
        assert r.status_code == 403


def test_mcp_requires_bearer(app):
    with TestClient(app) as c:
        r = c.post("/mcp", json={})
        assert r.status_code == 401


def test_mcp_initialize_succeeds(app):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"},
        },
    }
    headers = {
        "Authorization": "Bearer test-token",
        "Accept": "application/json, text/event-stream",
    }
    with TestClient(app) as c:
        r = c.post("/mcp", json=payload, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        # FastMCP's initialize response includes protocolVersion and serverInfo
        assert body.get("result", {}).get("serverInfo", {}).get("name") == "mare-gateway"
