"""Phase 10 GREEN tests for tools.extract.register — the 7 Phase 10 MCP tools.

Registers the extract module on a fresh FastMCP and asserts the 7 tool names
appear in the registered set with the expected count.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_gateway.tools import extract


_PHASE10_NAMES = {
    "run_binwalk",
    "run_unblob",
    "run_upx_test",
    "run_upx_list",
    "run_upx_unpack",
    "list_extracted_files",
    "promote_extracted_sample",
}


def test_expected_phase10_tools_present():
    m = FastMCP("phase10-test", stateless_http=True)
    extract.register(m)
    registered = set(m._tool_manager._tools.keys())
    missing = _PHASE10_NAMES - registered
    assert not missing, f"missing Phase 10 tools: {missing}"


def test_phase10_tool_count_is_seven():
    m = FastMCP("phase10-count-test", stateless_http=True)
    extract.register(m)
    registered = set(m._tool_manager._tools.keys())
    # Only Phase 10 tools should be registered when only extract.register runs
    assert registered == _PHASE10_NAMES, (
        f"registered set diverges: extras={registered - _PHASE10_NAMES}, "
        f"missing={_PHASE10_NAMES - registered}"
    )
    assert len(registered) == 7
