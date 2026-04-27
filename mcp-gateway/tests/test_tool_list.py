"""Tests that the curated tool surface meets GW-02 (15-25 tools) and D-01..D-04.

Maps to VALIDATION.md rows:
  - GW-02 test_tool_count_in_range
  - GW-02 test_atomic_tools_map_to_scripts
  - GW-01/GW-02 (tools/list integration)

IMPORTANT -- FastMCP internals vs public API:
  The preferred way to list tool names is via the public MCP client API:
    `async with create_connected_server_and_client_session(mcp._mcp_server) as session:`
    `    resp = await session.list_tools()`
    `    names = {t.name for t in resp.tools}`
  That path is stable across SDK versions (protocol-level tools/list).
  The `mcp._tool_manager._tools` attribute is internal to FastMCP 1.27 and will break
  on future SDK upgrades -- we pin `mcp>=1.27,<1.28` in pyproject.toml to guard against that.
  The private-attr fallback is only kept where it adds value (count sanity check); name
  listing goes through the public API.
"""
from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_gateway.tools import register_all_tools

EXPECTED_TOOLS = {
    # Composite (3)
    "run_triage", "run_deep_analysis", "generate_report",
    # Atomic (10)
    "init_case", "collect_strings", "collect_imports", "scan_yara", "scan_capa",
    "rank_signals", "build_hypothesis", "update_state", "resolve_case", "get_artifact",
    # Disassembler (3)
    "decompile", "list_functions", "get_xrefs",
    # Case/sample mgmt (6) — get_active_backend added in Plan 05 (D-07 pass-through model)
    "list_cases", "set_active_case", "get_active_case", "list_uploads", "get_sample_info",
    "get_active_backend",
}


@pytest.fixture
def registered():
    m = FastMCP("t", stateless_http=True)
    register_all_tools(m)
    return m


async def _list_tool_names(mcp: FastMCP) -> set[str]:
    """PUBLIC API path -- uses protocol-level tools/list over in-memory transport."""
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        resp = await session.list_tools()
        return {t.name for t in resp.tools}


async def test_all_expected_tools_present(registered):
    names = await _list_tool_names(registered)
    assert EXPECTED_TOOLS.issubset(names), f"missing: {EXPECTED_TOOLS - names}"


async def test_tool_count_in_range(registered):
    names = await _list_tool_names(registered)
    n = len(names)
    assert 15 <= n <= 25, f"tool count {n} violates GW-02 (15-25)"


async def test_no_unexpected_tools(registered):
    names = await _list_tool_names(registered)
    extras = names - EXPECTED_TOOLS
    assert not extras, f"unexpected tools registered: {extras}"


async def test_atomic_tools_map_to_scripts(registered):
    """Every shell/py script in orchestrator scripts/ has an atomic tool wrapper."""
    # The mapping is (script_basename -> tool_name); update when scripts are added/renamed.
    mapping = {
        "init_status_tree.sh": "init_case",
        "collect_strings.sh": "collect_strings",
        "collect_imports.sh": "collect_imports",
        "scan_yara.sh": "scan_yara",
        "scan_capa.sh": "scan_capa",
        "rank_signals.py": "rank_signals",
        "build_hypothesis.py": "build_hypothesis",
        "update_state.py": "update_state",
        "resolve_case.sh": "resolve_case",
    }
    names = await _list_tool_names(registered)
    for script, tool in mapping.items():
        assert tool in names, f"atomic tool {tool!r} for script {script!r} not registered"


def test_tool_count_private_sanity(registered):
    """Quick sanity check via FastMCP internal -- guards `mcp>=1.27,<1.28` pin.
    If this breaks on SDK upgrade, rewrite ALL tests in this file using
    `create_connected_server_and_client_session` (the public API path above).
    """
    # FastMCP internal -- if upgraded past 1.27, rewrite using create_connected_server_and_client_session.call_tool(name, args)
    n = len(registered._tool_manager._tools)
    assert 15 <= n <= 25, f"private-attr sanity: tool count {n} violates GW-02 (15-25)"
