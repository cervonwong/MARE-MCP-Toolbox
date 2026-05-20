"""Phase 11 Plan 04 Wave-0 DYN-01 env-gate regression tests.

Verifies the load-bearing invariant: when MCP_GATEWAY_DYNAMIC_TOOLS != "1" at
startup, neither the 7 MCP tools nor the 3 JobToolSpec entries (strace/ltrace/
qemu_user) leak into the live registry.

These tests fully reset gateway-package modules before each assertion because:
  - `register_job_tool(SPEC)` rejects re-registration with a new spec object
    (different identity, same name -> RuntimeError) — so we must avoid
    double-registration by starting from a clean slate.
  - `from mcp_gateway import dynamic` resolves via parent-package __dict__,
    bypassing sys.modules misses — so we must also clear parent-package attrs.
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


def _full_reset_modules():
    """Drop every gateway module that could carry stale spec/registry state, then
    delete the corresponding parent-package attributes so subsequent
    `from mcp_gateway import X` triggers a fresh import.
    """
    targets = [
        "mcp_gateway.tools",
        "mcp_gateway.tools.dynamic",
        "mcp_gateway.dynamic",
        "mcp_gateway.jobs",
        "mcp_gateway.extraction",
    ]
    # Also clear any tools.* submodules so register_all_tools re-imports them.
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
def fresh_register():
    """Yield a builder that resets gateway modules, reloads tools, builds an
    MCP server, and registers all tools. Each call yields a fresh setup.
    """
    def _build():
        _full_reset_modules()
        import mcp_gateway.tools as gw_tools
        m = FastMCP("t", stateless_http=True)
        gw_tools.register_all_tools(m)
        return gw_tools, m

    yield _build

    # No teardown reset -- subsequent test modules that depend on stable
    # imports (e.g., test_dynamic_tools.py's module-level `from mcp_gateway
    # import dynamic`) keep working against whichever module instance is
    # currently in sys.modules. Tests that need clean state reset at entry.


def test_tools_dynamic_not_imported_when_env_unset(monkeypatch, fresh_register):
    monkeypatch.delenv("MCP_GATEWAY_DYNAMIC_TOOLS", raising=False)
    gw_tools, m = fresh_register()

    assert "mcp_gateway.tools.dynamic" not in sys.modules, \
        "tools.dynamic was imported despite env unset"
    registered = set(m._tool_manager._tools.keys())
    leaked = EXPECTED_TOOLS_DYNAMIC & registered
    assert not leaked, f"dynamic tools leaked when env unset: {leaked}"


def test_tools_dynamic_imported_when_env_set(monkeypatch, fresh_register):
    monkeypatch.setenv("MCP_GATEWAY_DYNAMIC_TOOLS", "1")
    gw_tools, m = fresh_register()

    assert "mcp_gateway.tools.dynamic" in sys.modules, \
        "tools.dynamic was NOT imported despite env set"
    registered = set(m._tool_manager._tools.keys())
    missing = EXPECTED_TOOLS_DYNAMIC - registered
    assert not missing, f"dynamic tools not registered with env set: {missing}"


def test_job_tool_registry_lacks_dynamic_when_env_unset(monkeypatch, fresh_register):
    monkeypatch.delenv("MCP_GATEWAY_DYNAMIC_TOOLS", raising=False)
    gw_tools, m = fresh_register()

    from mcp_gateway.jobs import JOB_TOOL_REGISTRY
    for name in ("strace", "ltrace", "qemu_user"):
        assert name not in JOB_TOOL_REGISTRY, \
            f"job spec {name!r} leaked into JOB_TOOL_REGISTRY when env unset"


def test_job_tool_registry_has_dynamic_when_env_set(monkeypatch, fresh_register):
    monkeypatch.setenv("MCP_GATEWAY_DYNAMIC_TOOLS", "1")
    gw_tools, m = fresh_register()

    from mcp_gateway.jobs import JOB_TOOL_REGISTRY
    for name in ("strace", "ltrace", "qemu_user"):
        assert name in JOB_TOOL_REGISTRY, \
            f"job spec {name!r} missing from JOB_TOOL_REGISTRY with env set"
