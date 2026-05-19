"""Tests that the curated tool surface meets GW-02 + Phase 7 D-16 expansion and D-01..D-04.

Maps to VALIDATION.md rows:
  - GW-02 test_tool_count_in_range
  - GW-02 test_atomic_tools_map_to_scripts
  - GW-01/GW-02 (tools/list integration)

Phase 7 D-16 EXPANDED the curated surface from 22 (v1.0) to 39 tools:
  - run_shell (1)
  - 11 typed static-RE wrappers (run_file, run_die, run_xxd, run_readelf, run_objdump,
    run_nm, run_rabin2, run_capstone_disasm, run_ropper, run_jq, run_yq)
  - 5 artifact-control helpers (write_artifact, append_artifact, list_artifacts,
    get_artifact_tree, get_tool_log)
Phase 8 D-05 adds 4 more (session-scoped r2):
  - open_r2_session, r2_cmd, close_r2_session, list_sessions
Phase 9 D-05 adds 4 more (background jobs):
  - start_tool_job, get_tool_job, cancel_tool_job, list_tool_jobs
Phase 10 D-01 adds 7 more (extraction tier):
  - run_binwalk, run_unblob, run_upx_test, run_upx_list, run_upx_unpack,
    list_extracted_files, promote_extracted_sample
Total after Phase 10: 54. The 15-25 range from v1.0 GW-02 is superseded; the
Phase 10 invariant is 35-60 (absorbs Phase 11's conditional dynamic tools).

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
    # v1.0 curated surface (22 tools) --------------------------------
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
    # Phase 7 D-16 expansion (17 tools) ------------------------------
    # Constrained shell (1)
    "run_shell",
    # Typed static-RE wrappers (11)
    "run_file", "run_die", "run_xxd", "run_readelf", "run_objdump", "run_nm",
    "run_rabin2", "run_capstone_disasm", "run_ropper", "run_jq", "run_yq",
    # Artifact-control helpers (5)
    "write_artifact", "append_artifact", "list_artifacts", "get_artifact_tree",
    "get_tool_log",
    # Phase 8 D-05 session-scoped r2 (4)
    "open_r2_session", "r2_cmd", "close_r2_session", "list_sessions",
    # Phase 9 D-05 background jobs (4)
    "start_tool_job", "get_tool_job", "cancel_tool_job", "list_tool_jobs",
    # Phase 10 D-01 extraction tier (7)
    "run_binwalk", "run_unblob", "run_upx_test", "run_upx_list", "run_upx_unpack",
    "list_extracted_files", "promote_extracted_sample",
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
    # Phase 10 D-01 expands to 54 (47 + 7); range 35-60 absorbs Phase 11's
    # conditional dynamic tools (env-gated, default-off).
    assert 35 <= n <= 60, f"tool count {n} violates Phase 10 D-01 invariant (35-60)"


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
    # Phase 10 D-01 expanded the range to 35-60 (absorbs Phase 11's conditional dynamic tools).
    assert 35 <= n <= 60, f"private-attr sanity: tool count {n} violates Phase 10 D-01 (35-60)"
