"""Phase 11 Plan 04 Wave-0 DYN-01 env-gate regression tests.

Verifies the load-bearing invariant: when MCP_GATEWAY_DYNAMIC_TOOLS != "1" at
startup, neither the 7 MCP tools nor the 3 JobToolSpec entries (strace/ltrace/
qemu_user) leak into the live registry.

These tests reload mcp_gateway.tools (and dependent modules) per-test so the
env-gate's import-time effect is exercised. They save & restore sys.modules
to avoid cross-contaminating other test modules.
"""
from __future__ import annotations

import importlib
import sys

import pytest

from mcp.server.fastmcp import FastMCP


EXPECTED_TOOLS_DYNAMIC = {
    "run_strace", "run_ltrace", "run_qemu_user",
    "open_gdb_session", "gdb_exec", "close_gdb_session",
    "get_dynamic_capabilities",
}


@pytest.fixture
def reload_tools(monkeypatch):
    """Reload mcp_gateway.tools (and drop tools.dynamic) per test; restore after.

    The yield value is a callable that performs the reload + returns the reloaded
    tools module (so the caller can read register_all_tools fresh).
    """
    saved_modules = {
        k: v for k, v in list(sys.modules.items())
        if k == "mcp_gateway.tools" or k.startswith("mcp_gateway.tools.")
    }
    # Drop tools.dynamic so the conditional import path is re-evaluated.
    for k in list(sys.modules.keys()):
        if k == "mcp_gateway.tools.dynamic":
            del sys.modules[k]

    def _reload():
        import mcp_gateway.tools as gw_tools
        importlib.reload(gw_tools)
        return gw_tools

    yield _reload

    # Restore: drop everything we touched + put back the saved snapshot
    for k in list(sys.modules.keys()):
        if k == "mcp_gateway.tools" or k.startswith("mcp_gateway.tools."):
            del sys.modules[k]
    for k, v in saved_modules.items():
        sys.modules[k] = v


def test_tools_dynamic_not_imported_when_env_unset(monkeypatch, reload_tools):
    monkeypatch.delenv("MCP_GATEWAY_DYNAMIC_TOOLS", raising=False)
    # Drop tools.dynamic if it was previously loaded
    sys.modules.pop("mcp_gateway.tools.dynamic", None)

    gw_tools = reload_tools()
    m = FastMCP("t", stateless_http=True)
    gw_tools.register_all_tools(m)

    assert "mcp_gateway.tools.dynamic" not in sys.modules
    registered = set(m._tool_manager._tools.keys())
    assert not (EXPECTED_TOOLS_DYNAMIC & registered), \
        f"dynamic tools leaked when env unset: {EXPECTED_TOOLS_DYNAMIC & registered}"


def test_tools_dynamic_imported_when_env_set(monkeypatch, reload_tools):
    monkeypatch.setenv("MCP_GATEWAY_DYNAMIC_TOOLS", "1")
    sys.modules.pop("mcp_gateway.tools.dynamic", None)

    gw_tools = reload_tools()
    m = FastMCP("t", stateless_http=True)
    gw_tools.register_all_tools(m)

    assert "mcp_gateway.tools.dynamic" in sys.modules
    registered = set(m._tool_manager._tools.keys())
    missing = EXPECTED_TOOLS_DYNAMIC - registered
    assert not missing, f"dynamic tools not registered with env set: {missing}"


def test_job_tool_registry_lacks_dynamic_when_env_unset(monkeypatch, reload_tools):
    monkeypatch.delenv("MCP_GATEWAY_DYNAMIC_TOOLS", raising=False)
    # Drop mcp_gateway.dynamic too -- it has the register_job_tool calls at import.
    sys.modules.pop("mcp_gateway.tools.dynamic", None)
    sys.modules.pop("mcp_gateway.dynamic", None)
    # Drop jobs so JOB_TOOL_REGISTRY resets
    sys.modules.pop("mcp_gateway.jobs", None)

    # Re-import jobs first (it owns the registry), then re-import tools
    import mcp_gateway.jobs as jobs_mod  # noqa: F401
    gw_tools = reload_tools()
    m = FastMCP("t", stateless_http=True)
    gw_tools.register_all_tools(m)

    from mcp_gateway.jobs import JOB_TOOL_REGISTRY
    for name in ("strace", "ltrace", "qemu_user"):
        assert name not in JOB_TOOL_REGISTRY, \
            f"job spec {name!r} leaked into JOB_TOOL_REGISTRY when env unset"


def test_job_tool_registry_has_dynamic_when_env_set(monkeypatch, reload_tools):
    monkeypatch.setenv("MCP_GATEWAY_DYNAMIC_TOOLS", "1")
    sys.modules.pop("mcp_gateway.tools.dynamic", None)

    gw_tools = reload_tools()
    m = FastMCP("t", stateless_http=True)
    gw_tools.register_all_tools(m)

    from mcp_gateway.jobs import JOB_TOOL_REGISTRY
    for name in ("strace", "ltrace", "qemu_user"):
        assert name in JOB_TOOL_REGISTRY, \
            f"job spec {name!r} missing from JOB_TOOL_REGISTRY with env set"
