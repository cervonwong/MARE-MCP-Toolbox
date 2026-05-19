"""Phase 10 Wave 0 RED-stub -- Wave 1/2 turns these GREEN.

Per CONTEXT D-24: function-top imports of not-yet-existing modules; pytest collection
passes, execution ImportErrors.
"""
from __future__ import annotations
import pytest


def test_signatures_mode_parses_rows():
    from mcp_gateway.tools import extract  # noqa: F401  RED until Plan 04
    assert True  # body populated by Plan 05 Wave-3 GREEN flip


def test_entropy_mode_parses_rows():
    from mcp_gateway.tools import extract  # noqa: F401  RED until Plan 04
    assert True  # body populated by Plan 05 Wave-3 GREEN flip


@pytest.mark.slow
def test_extract_mode_dispatches_job(_require_binwalk_or_skip):
    from mcp_gateway.tools import extract  # noqa: F401  RED until Plan 04
    assert True  # body populated by Plan 05 Wave-3 GREEN flip


def test_errors_structured():
    from mcp_gateway.tools import extract  # noqa: F401  RED until Plan 04
    assert True  # body populated by Plan 05 Wave-3 GREEN flip
