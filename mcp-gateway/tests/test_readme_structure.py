"""CLI-03 (D-16): top-level README.md structural assertions.

Grep-style — asserts headings, anchor phrases, template references, and the
absence of banned tech from CLAUDE.md's 'Do NOT Use' list.
"""

from __future__ import annotations
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"


@pytest.fixture(scope="module")
def text() -> str:
    assert README.is_file(), f"missing README at {README}"
    return README.read_text(encoding="utf-8")


def test_h1_heading(text):
    assert re.search(r"(?m)^#\s+MARE-MCP-Toolbox\b", text), "missing top-level heading"


def test_two_mode_framing(text):
    """D-16: README opens with two-mode framing."""
    assert "Two ways to use this" in text or "Two modes" in text


def test_references_claude_code_template(text):
    assert "templates/claude-code/.mcp.json" in text


def test_references_mastra_template(text):
    assert "templates/mastra" in text


def test_references_remote_flag(text):
    assert "./run_docker.sh --remote" in text


def test_references_print_config_flag(text):
    """Plan 02 (D-11) flag must be documented for users."""
    assert "--print-config" in text


def test_documents_mare_uri_scheme(text):
    """Plan 03 (CLI-04, D-01) — resource URIs surfaced for clients."""
    assert "mare://cases/" in text


def test_uses_locked_env_var_names(text):
    """RESEARCH Pitfall 8: uniform env-var convention across docs + templates."""
    assert "MARE_GATEWAY_TOKEN" in text
    assert "MARE_GATEWAY_URL" in text


@pytest.mark.parametrize(
    "banned",
    [
        "mcp-remote",  # CVE-2025-6514
        "MastraMCPClient",  # legacy class
    ],
)
def test_no_banned_tech(text, banned):
    """CLAUDE.md 'Do NOT Use' list."""
    assert banned not in text, f"banned token {banned!r} in README"


def test_links_to_mcp_gateway_dir(text):
    """Cross-reference to gateway internals so users can find the tool surface."""
    assert "mcp-gateway/" in text or "mcp-gateway)" in text
