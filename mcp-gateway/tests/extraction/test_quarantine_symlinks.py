"""Phase 10 Wave 0 RED-stub -- Wave 1/2 turns these GREEN.

Per CONTEXT D-24: function-top imports of not-yet-existing modules; pytest collection
passes, execution ImportErrors.
"""
from __future__ import annotations
import pytest


def test_sentinel_body_format():
    from mcp_gateway import extraction  # noqa: F401  RED until Plan 02
    assert True  # body populated by Plan 05 Wave-3 GREEN flip


def test_idempotent():
    from mcp_gateway import extraction  # noqa: F401  RED until Plan 02
    assert True  # body populated by Plan 05 Wave-3 GREEN flip


def test_no_follow_walk():
    from mcp_gateway import extraction  # noqa: F401  RED until Plan 02
    assert True  # body populated by Plan 05 Wave-3 GREEN flip
