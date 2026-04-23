"""Tests for load_or_generate_token + BearerAuthMiddleware + OriginMiddleware.

Maps to: .planning/phases/02-mcp-gateway/02-VALIDATION.md rows GW-04 (all).
"""
from __future__ import annotations
import os
import stat
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mcp_gateway.auth import (
    BearerAuthMiddleware,
    OriginMiddleware,
    load_or_generate_token,
)


def _build_test_app(token: str) -> Starlette:
    async def mcp_ok(request):
        return JSONResponse({"ok": True})

    async def upload_ok(request):
        return JSONResponse({"ok": True})

    async def health_ok(request):
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[
            Route("/mcp", mcp_ok, methods=["POST"]),
            Route("/upload", upload_ok, methods=["POST"]),
            Route("/healthz", health_ok, methods=["GET"]),
        ]
    )
    app.add_middleware(BearerAuthMiddleware, token=token)
    return app


# -------- load_or_generate_token --------

def test_env_var_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "supersecret-from-env")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / "tok"))
    assert load_or_generate_token() == "supersecret-from-env"


def test_generated_token_when_env_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("MCP_GATEWAY_TOKEN", raising=False)
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / "tok"))
    tok = load_or_generate_token()
    assert len(tok) >= 32
    # token_urlsafe(32) is 43 characters URL-safe base64 without padding.
    assert isinstance(tok, str)


def test_token_file_is_0600(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "t")
    tok_path = tmp_path / "tok"
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tok_path))
    load_or_generate_token()
    assert tok_path.exists()
    mode = stat.S_IMODE(tok_path.stat().st_mode)
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


def test_quiet_suppresses_log(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "t")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / "tok"))
    monkeypatch.setenv("MCP_GATEWAY_QUIET", "1")
    caplog.set_level("INFO", logger="mcp_gateway.auth")
    load_or_generate_token()
    assert not any("Bearer token:" in r.getMessage() for r in caplog.records)


# -------- BearerAuthMiddleware --------

def test_health_open(bearer_token):
    with TestClient(_build_test_app(bearer_token)) as client:
        r = client.get("/healthz")
        assert r.status_code == 200


def test_mcp_requires_bearer(bearer_token):
    with TestClient(_build_test_app(bearer_token)) as client:
        r = client.post("/mcp", json={})
        assert r.status_code == 401
        assert "missing bearer token" in r.text


def test_upload_requires_bearer(bearer_token):
    with TestClient(_build_test_app(bearer_token)) as client:
        r = client.post("/upload", content=b"x")
        assert r.status_code == 401


def test_valid_bearer_ok(bearer_token):
    with TestClient(_build_test_app(bearer_token)) as client:
        r = client.post("/mcp", json={}, headers={"Authorization": f"Bearer {bearer_token}"})
        assert r.status_code == 200


def test_invalid_bearer_rejected(bearer_token):
    with TestClient(_build_test_app(bearer_token)) as client:
        r = client.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401
        assert "invalid bearer token" in r.text


# -------- OriginMiddleware --------

def _app_with_origin_only() -> Starlette:
    async def ok(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", ok, methods=["POST"])])
    app.add_middleware(OriginMiddleware)
    return app


def test_origin_localhost_allowed():
    with TestClient(_app_with_origin_only()) as client:
        r = client.post("/mcp", json={}, headers={"Origin": "http://127.0.0.1:3000"})
        assert r.status_code == 200


def test_origin_null_allowed():
    with TestClient(_app_with_origin_only()) as client:
        r = client.post("/mcp", json={}, headers={"Origin": "null"})
        assert r.status_code == 200


def test_origin_missing_allowed():
    with TestClient(_app_with_origin_only()) as client:
        r = client.post("/mcp", json={})
        assert r.status_code == 200


def test_origin_evil_rejected():
    with TestClient(_app_with_origin_only()) as client:
        r = client.post("/mcp", json={}, headers={"Origin": "http://evil.com"})
        assert r.status_code == 403
