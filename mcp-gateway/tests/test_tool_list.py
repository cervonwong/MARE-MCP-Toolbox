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
Total after Phase 10: 54.

Phase 11 Plan 04 adds 7 MORE conditionally (env-gated, OFF by default):
  - run_strace, run_ltrace, run_qemu_user, open_gdb_session, gdb_exec,
    close_gdb_session, get_dynamic_capabilities
Total with MCP_GATEWAY_DYNAMIC_TOOLS=1: 61.

D-DYN-TEST-COUNT: This file parametrizes the tool-count and EXPECTED_TOOLS
assertions on MCP_GATEWAY_DYNAMIC_TOOLS so BOTH counts (54 baseline / 61 with
dynamic) are regression-locked.

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

import importlib
import sys

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session


EXPECTED_TOOLS_BASELINE = {
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

# Phase 11 D-DYN-TEST-COUNT: when MCP_GATEWAY_DYNAMIC_TOOLS=1, the env-gated
# dynamic-mode tools are added on top of the baseline (54 -> 61).
EXPECTED_TOOLS_DYNAMIC = EXPECTED_TOOLS_BASELINE | {
    "run_strace", "run_ltrace", "run_qemu_user",
    "open_gdb_session", "gdb_exec", "close_gdb_session",
    "get_dynamic_capabilities",
}

# Phase 13 HARDEN-06: env-gated unsafe-r2 tool.
# When MCP_GATEWAY_R2_UNSAFE_ALLOWED=1, open_r2_session_unsafe is added on top
# of whichever baseline/dynamic surface is currently active. Tool-count delta: +1.
EXPECTED_TOOLS_BASELINE_UNSAFE = EXPECTED_TOOLS_BASELINE | {"open_r2_session_unsafe"}
EXPECTED_TOOLS_DYNAMIC_UNSAFE = EXPECTED_TOOLS_DYNAMIC | {"open_r2_session_unsafe"}


def _set_env(monkeypatch, env_value):
    if env_value is None:
        monkeypatch.delenv("MCP_GATEWAY_DYNAMIC_TOOLS", raising=False)
    else:
        monkeypatch.setenv("MCP_GATEWAY_DYNAMIC_TOOLS", env_value)


def _full_reset_modules():
    """Drop every gateway module that could carry stale spec/registry state, then
    delete the corresponding parent-package attributes so subsequent
    `from mcp_gateway import X` triggers a fresh import.

    Required because `register_job_tool` rejects re-registration with a new
    spec object (different identity, same name -> RuntimeError); reload-based
    isolation collapses without a full reset.
    """
    targets = [
        "mcp_gateway.tools",
        "mcp_gateway.tools.dynamic",
        "mcp_gateway.dynamic",
        "mcp_gateway.jobs",
        "mcp_gateway.extraction",
    ]
    targets.extend([k for k in list(sys.modules) if k.startswith("mcp_gateway.tools.")])
    for k in targets:
        sys.modules.pop(k, None)
    import mcp_gateway as _pkg
    for attr in ("tools", "dynamic", "jobs", "extraction"):
        if hasattr(_pkg, attr):
            try:
                delattr(_pkg, attr)
            except AttributeError:
                pass


@pytest.fixture
def make_mcp():
    """Reset gateway modules fresh per call so env-gated import is honored.

    Yields a builder `_build(env_value)` that performs the reset, re-imports
    tools, and returns a registered FastMCP instance.

    No teardown reset is performed -- subsequent tests that need a clean
    state must reset themselves (the in-process registries rebuild on the next
    fresh import driven by their own fixtures).
    """
    def _build(env_value):
        _full_reset_modules()
        import mcp_gateway.tools as gw_tools
        m = FastMCP("t", stateless_http=True)
        gw_tools.register_all_tools(m)
        return m

    yield _build


async def _list_tool_names(mcp: FastMCP) -> set[str]:
    """PUBLIC API path -- uses protocol-level tools/list over in-memory transport."""
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        resp = await session.list_tools()
        return {t.name for t in resp.tools}


# ---------------------------------------------------------------------------
# D-DYN-TEST-COUNT: parametrize on env. Baseline 54 (env unset) / Dynamic 61
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env_value,expected",
    [(None, EXPECTED_TOOLS_BASELINE), ("1", EXPECTED_TOOLS_DYNAMIC)],
)
async def test_all_expected_tools_present(monkeypatch, make_mcp, env_value, expected):
    _set_env(monkeypatch, env_value)
    m = make_mcp(env_value)
    names = await _list_tool_names(m)
    assert expected.issubset(names), f"missing: {expected - names}"


@pytest.mark.parametrize(
    "env_value,expected_count",
    [(None, 54), ("1", 61)],
)
async def test_tool_count_in_range(monkeypatch, make_mcp, env_value, expected_count):
    """Phase 11 D-DYN-TEST-COUNT: exact-count assertion (not a range).

    Baseline 54 when MCP_GATEWAY_DYNAMIC_TOOLS unset; 61 when set to '1'.
    """
    _set_env(monkeypatch, env_value)
    m = make_mcp(env_value)
    names = await _list_tool_names(m)
    n = len(names)
    assert n == expected_count, (
        f"tool count {n} != expected {expected_count} for env_value={env_value!r} "
        f"(Phase 11 D-DYN-TEST-COUNT invariant)"
    )


@pytest.mark.parametrize(
    "env_value,expected",
    [(None, EXPECTED_TOOLS_BASELINE), ("1", EXPECTED_TOOLS_DYNAMIC)],
)
async def test_no_unexpected_tools(monkeypatch, make_mcp, env_value, expected):
    _set_env(monkeypatch, env_value)
    m = make_mcp(env_value)
    names = await _list_tool_names(m)
    extras = names - expected
    assert not extras, f"unexpected tools registered (env_value={env_value!r}): {extras}"


async def test_atomic_tools_map_to_scripts(monkeypatch, make_mcp):
    """Every shell/py script in orchestrator scripts/ has an atomic tool wrapper.

    Independent of MCP_GATEWAY_DYNAMIC_TOOLS — atomic tools are in baseline.
    """
    _set_env(monkeypatch, None)
    m = make_mcp(None)
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
    names = await _list_tool_names(m)
    for script, tool in mapping.items():
        assert tool in names, f"atomic tool {tool!r} for script {script!r} not registered"


@pytest.mark.parametrize(
    "env_value,expected_count",
    [(None, 54), ("1", 61)],
)
def test_tool_count_private_sanity(monkeypatch, make_mcp, env_value, expected_count):
    """Quick sanity check via FastMCP internal -- guards `mcp>=1.27,<1.28` pin.

    Phase 11 D-DYN-TEST-COUNT parametrized.
    """
    _set_env(monkeypatch, env_value)
    m = make_mcp(env_value)
    # FastMCP internal -- if upgraded past 1.27, rewrite using create_connected_server_and_client_session.call_tool(name, args)
    n = len(m._tool_manager._tools)
    assert n == expected_count, (
        f"private-attr sanity: tool count {n} != expected {expected_count} "
        f"for env_value={env_value!r} (Phase 11 D-DYN-TEST-COUNT)"
    )


# ---------------------------------------------------------------------------
# Phase 13 HARDEN-06 tests — env-gated open_r2_session_unsafe axis
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dynamic_env,unsafe_env,expected", [
    (None, None, EXPECTED_TOOLS_BASELINE),
    (None, "1", EXPECTED_TOOLS_BASELINE_UNSAFE),
    ("1", None, EXPECTED_TOOLS_DYNAMIC),
    ("1", "1", EXPECTED_TOOLS_DYNAMIC_UNSAFE),
])
async def test_tool_list_with_unsafe_axis(dynamic_env, unsafe_env, expected, monkeypatch, make_mcp):
    """HARDEN-06: open_r2_session_unsafe registered iff MCP_GATEWAY_R2_UNSAFE_ALLOWED=1."""
    # Set dynamic env (matches existing pattern)
    _set_env(monkeypatch, dynamic_env)
    # Set unsafe env (new axis)
    if unsafe_env is None:
        monkeypatch.delenv("MCP_GATEWAY_R2_UNSAFE_ALLOWED", raising=False)
    else:
        monkeypatch.setenv("MCP_GATEWAY_R2_UNSAFE_ALLOWED", unsafe_env)
    m = make_mcp(dynamic_env)
    names = await _list_tool_names(m)
    # Exact-set assertion: registered set must equal expected.
    assert names == expected, (
        f"tool-list mismatch:\n"
        f"  dynamic={dynamic_env!r} unsafe={unsafe_env!r}\n"
        f"  expected count={len(expected)}, got count={len(names)}\n"
        f"  missing from registered: {expected - names}\n"
        f"  extra in registered:     {names - expected}"
    )


async def test_unsafe_r2_absent_baseline(monkeypatch, make_mcp):
    """HARDEN-06: unsafe tool is ABSENT when env unset (default secure posture)."""
    _set_env(monkeypatch, None)
    monkeypatch.delenv("MCP_GATEWAY_R2_UNSAFE_ALLOWED", raising=False)
    m = make_mcp(None)
    names = await _list_tool_names(m)
    assert "open_r2_session_unsafe" not in names, (
        "open_r2_session_unsafe MUST NOT be registered when MCP_GATEWAY_R2_UNSAFE_ALLOWED is unset"
    )


async def test_unsafe_r2_present_with_env(monkeypatch, make_mcp):
    """HARDEN-06: unsafe tool IS present when env=1."""
    _set_env(monkeypatch, None)
    monkeypatch.setenv("MCP_GATEWAY_R2_UNSAFE_ALLOWED", "1")
    m = make_mcp(None)
    names = await _list_tool_names(m)
    assert "open_r2_session_unsafe" in names, (
        "open_r2_session_unsafe MUST be registered when MCP_GATEWAY_R2_UNSAFE_ALLOWED=1"
    )
