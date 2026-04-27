"""CLI-01, CLI-03 (D-10): templates/claude-code/.mcp.json shape verification."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "templates" / "claude-code" / ".mcp.json"


def test_template_file_exists():
    assert TEMPLATE.is_file(), f"missing CC template at {TEMPLATE}"


def test_template_parses_as_json():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_template_declares_http_type():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    server = data["mcpServers"]["mare-toolbox"]
    assert server["type"] == "http", f"expected type=http, got {server['type']!r}"


def test_template_authorization_bearer_env_var():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    auth = data["mcpServers"]["mare-toolbox"]["headers"]["Authorization"]
    # Must reference MARE_GATEWAY_TOKEN env var (D-10, RESEARCH Pattern 2, locked env convention).
    assert auth == "Bearer ${MARE_GATEWAY_TOKEN}", auth


def test_template_url_uses_env_var_with_default():
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    url = data["mcpServers"]["mare-toolbox"]["url"]
    assert url == "${MARE_GATEWAY_URL:-http://localhost:8080/mcp}", url


@pytest.mark.parametrize("banned", ["mcp-remote", "MastraMCPClient", '"sse"'])
def test_template_no_banned_tech(banned):
    """CLAUDE.md 'Do NOT Use' list: mcp-remote (CVE-2025-6514), MastraMCPClient, SSE."""
    text = TEMPLATE.read_text(encoding="utf-8")
    assert banned not in text, f"banned token {banned!r} present in template"
