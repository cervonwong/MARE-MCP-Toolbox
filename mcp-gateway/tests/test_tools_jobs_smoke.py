"""Phase 9 Plan 02 smoke tests for `mcp_gateway.tools.jobs` MCP surface.

These tests are intentionally minimal -- they exercise only the contract that
Plan 02's <verification> block locks in:

  - module imports clean
  - D-26 disclaimer phrases present verbatim in every tool's __doc__
  - register(mcp) attaches all four tools without raising

Behavioural end-to-end tests (D-19 25-key snapshot, D-15 four error shapes,
D-16 Tier-2 ctx.report_progress with session-id dedup, D-20 `_specs` magic
filtering) land in Plan 04.

Wave-0 RED-stub pattern: this file imports `mcp_gateway.tools.jobs` at the top
of every test function -- before Plan 02 lands the file, collection passes but
execution ImportErrors. Plan 02's GREEN flip turns every test PASS.
"""
from __future__ import annotations

import pytest

from mcp.server.fastmcp import FastMCP


# ---------------------------------------------------------------------------
# D-26 verbatim phrases (mirrors test_sess05_disclaimer_in_docstrings pattern).
# ---------------------------------------------------------------------------
D26_PHRASE_IN_MEMORY = "In-memory registry"
D26_PHRASE_SHARED = "shared across all bearer-token clients"


def test_tools_jobs_imports_clean():
    """Plan 02 SC: `python -c "from mcp_gateway.tools import jobs as tj"` succeeds."""
    from mcp_gateway.tools import jobs as tj  # noqa: F401

    # And every public tool symbol is callable.
    for name in ("start_tool_job", "get_tool_job", "cancel_tool_job", "list_tool_jobs"):
        fn = getattr(tj, name)
        assert callable(fn), f"{name} is not callable on tools.jobs"


def test_d26_disclaimer_present_in_every_tool():
    """D-26: every MCP-registered tool's __doc__ carries both verbatim phrases."""
    from mcp_gateway.tools import jobs as tj

    for name in ("start_tool_job", "get_tool_job", "cancel_tool_job", "list_tool_jobs"):
        doc = getattr(tj, name).__doc__ or ""
        assert D26_PHRASE_IN_MEMORY in doc, (
            f"{name} __doc__ missing D-26 phrase {D26_PHRASE_IN_MEMORY!r}"
        )
        assert D26_PHRASE_SHARED in doc, (
            f"{name} __doc__ missing D-26 phrase {D26_PHRASE_SHARED!r}"
        )


def test_register_attaches_four_tools():
    """Plan 02 SC: register(mcp) wires all four tools onto a fresh FastMCP."""
    from mcp_gateway.tools import jobs as tj

    mcp = FastMCP("test-plan-02", stateless_http=True)
    # Must not raise.
    tj.register(mcp)


def test_module_attribute_import_pattern():
    """D-24 + plan acceptance: module-attribute access to jobs.<NAME> is used.

    Plan 02 explicitly forbids `from mcp_gateway.jobs import MAX_JOBS_INFLIGHT`
    for module constants -- module-attribute access lets importlib.reload(jobs)
    propagate through tests (Phase 8 precedent). Verify by reading the source.
    """
    from mcp_gateway.tools import jobs as tj
    import inspect

    src = inspect.getsource(tj)
    assert "from mcp_gateway import jobs" in src, (
        "tools/jobs.py must use module-attribute import `from mcp_gateway import jobs`"
    )


def test_d15_error_paths_via_to_dict():
    """D-15: tools/jobs.py routes every error through one of the four `.to_dict()`s.

    Counts the number of `.to_dict()` call sites; minimum is 4 (one per D-15
    error shape: JobCapReached, UnknownJobTool, JobNotFound, InvalidKwargs).
    """
    from mcp_gateway.tools import jobs as tj
    import inspect

    src = inspect.getsource(tj)
    n = src.count(".to_dict()")
    assert n >= 4, f"expected >=4 .to_dict() call sites in tools/jobs.py, found {n}"


def test_d16_tier2_report_progress_present():
    """D-16: get_tool_job calls ctx.report_progress with session-id dedup."""
    from mcp_gateway.tools import jobs as tj
    import inspect

    src = inspect.getsource(tj)
    assert "ctx.report_progress" in src, (
        "D-16 Tier-2 push site `ctx.report_progress(...)` missing in tools/jobs.py"
    )
    assert "_last_reported_to" in src, (
        "D-16 dedup map `_last_reported_to` not referenced in tools/jobs.py"
    )


def test_d20_specs_magic_state_and_q5_filter():
    """D-20 + Q5: list_tool_jobs branches on state == '_specs' and filters underscore names."""
    from mcp_gateway.tools import jobs as tj
    import inspect

    src = inspect.getsource(tj)
    assert '"_specs"' in src or "'_specs'" in src, (
        "D-20 `_specs` magic-state branch missing in tools/jobs.py"
    )
    assert "include_internal" in src, (
        "Q5 `include_internal` filter missing in tools/jobs.py"
    )
