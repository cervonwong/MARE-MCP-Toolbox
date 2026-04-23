"""Tests for backend/tool_map.py translation layer. Maps to VALIDATION.md GW-03 unit row."""
from __future__ import annotations

import pytest

from mcp_gateway.backend.tool_map import (
    TOOL_MAP,
    supported_unified_tools,
    translate,
    validate_backend_support,
)


# --------- translate() ---------

@pytest.mark.parametrize(
    "unified,backend,expected_tool",
    [
        ("decompile",      "ida",    "decompile"),
        ("decompile",      "ghidra", "decomp.function"),
        ("list_functions", "ida",    "list_funcs"),
        ("list_functions", "ghidra", "function.list"),
        ("get_xrefs",      "ida",    "xrefs_to"),
        ("get_xrefs",      "ghidra", "reference.to"),
    ],
)
def test_translate_returns_backend_tool(unified, backend, expected_tool):
    tool, args = translate(unified, backend, {"foo": "bar"})
    assert tool == expected_tool
    assert args == {"foo": "bar"}  # identity transform in Phase 2


def test_translate_unknown_unified_raises():
    with pytest.raises(KeyError, match="unknown unified tool"):
        translate("not_a_tool", "ida")


def test_translate_unknown_backend_raises():
    with pytest.raises(KeyError, match="backend 'not_a_backend'"):
        translate("decompile", "not_a_backend")


def test_translate_empty_args_default():
    tool, args = translate("decompile", "ida")
    assert args == {}


# --------- supported_unified_tools + validate_backend_support ---------

def test_supported_unified_tools_are_the_3_disasm_tools():
    assert set(supported_unified_tools()) == {"decompile", "list_functions", "get_xrefs"}


def test_all_three_backends_supported_for_every_unified_tool():
    for unified in supported_unified_tools():
        backends = set(TOOL_MAP[unified].keys())
        assert backends == {"ida", "bn", "ghidra"}, f"{unified} missing a backend"


def test_validate_backend_support_ida():
    assert validate_backend_support("ida") == ["decompile", "get_xrefs", "list_functions"]


def test_validate_backend_support_missing_backend():
    assert validate_backend_support("qemu") == []
