"""Tests for CLI defaults (host, port). Maps to GW-05 rows in VALIDATION.md."""
from __future__ import annotations

from mcp_gateway.cli import build_parser, DEFAULT_HOST, DEFAULT_PORT


def test_default_bind_is_localhost(monkeypatch):
    monkeypatch.delenv("MCP_GATEWAY_HOST", raising=False)
    monkeypatch.delenv("MCP_GATEWAY_PORT", raising=False)
    args = build_parser().parse_args([])
    assert args.host == DEFAULT_HOST == "127.0.0.1"
    assert args.port == DEFAULT_PORT == 8080


def test_env_overrides_bind(monkeypatch):
    monkeypatch.setenv("MCP_GATEWAY_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_GATEWAY_PORT", "9090")
    args = build_parser().parse_args([])
    assert args.host == "0.0.0.0"
    assert args.port == 9090


def test_cli_flags_override_env(monkeypatch):
    monkeypatch.setenv("MCP_GATEWAY_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_GATEWAY_PORT", "9090")
    args = build_parser().parse_args(["--host", "127.0.0.1", "--port", "8080"])
    assert args.host == "127.0.0.1"
    assert args.port == 8080
