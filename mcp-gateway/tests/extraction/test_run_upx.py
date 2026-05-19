"""Phase 10 Wave 0 RED-stub -- Wave 1/2 turns these GREEN.

Per CONTEXT D-24: function-top imports of not-yet-existing modules; pytest collection
passes, execution ImportErrors.
"""
from __future__ import annotations
import pytest


def test_test_not_packed():
    from mcp_gateway.tools import extract  # noqa: F401  RED until Plan 04
    assert True  # body populated by Plan 05 Wave-3 GREEN flip


def test_list_parses_columns():
    from mcp_gateway.tools import extract  # noqa: F401  RED until Plan 04
    assert True  # body populated by Plan 05 Wave-3 GREEN flip


@pytest.mark.slow
def test_unpack_writes_output(_require_upx_or_skip):
    from mcp_gateway.tools import extract  # noqa: F401  RED until Plan 04
    assert True  # body populated by Plan 05 Wave-3 GREEN flip
