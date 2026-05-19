"""Phase 10 GREEN tests for D-23 disclaimer splice on tools/extract handlers.

Long-form disclaimer on 4 long-form tools (run_binwalk, run_unblob,
list_extracted_files, promote_extracted_sample).
Short-form disclaimer on 3 UPX tools (run_upx_test/list/unpack).
"""
from __future__ import annotations

from mcp_gateway.tools import extract


_LONG_PHRASE = "shared across all bearer-token clients"
_LONG_INMEM = "in-memory job"


def test_run_unblob_disclaimer():
    doc = extract.run_unblob.__doc__ or ""
    assert _LONG_PHRASE in doc
    assert _LONG_INMEM in doc


def test_run_binwalk_disclaimer():
    doc = extract.run_binwalk.__doc__ or ""
    assert _LONG_PHRASE in doc
    assert _LONG_INMEM in doc


def test_list_extracted_files_disclaimer():
    doc = extract.list_extracted_files.__doc__ or ""
    assert _LONG_PHRASE in doc
    assert _LONG_INMEM in doc


def test_promote_extracted_sample_disclaimer():
    doc = extract.promote_extracted_sample.__doc__ or ""
    assert _LONG_PHRASE in doc
    assert _LONG_INMEM in doc
    # Promotion-specific phrase from the long disclaimer
    assert "Promotion lineage lives in" in doc


def test_run_upx_test_short_disclaimer():
    doc = extract.run_upx_test.__doc__ or ""
    assert _LONG_PHRASE in doc
    # Short form must NOT contain the long-form "in-memory job" phrase
    assert _LONG_INMEM not in doc


def test_run_upx_list_short_disclaimer():
    doc = extract.run_upx_list.__doc__ or ""
    assert _LONG_PHRASE in doc
    assert _LONG_INMEM not in doc


def test_run_upx_unpack_short_disclaimer():
    doc = extract.run_upx_unpack.__doc__ or ""
    assert _LONG_PHRASE in doc
    assert _LONG_INMEM not in doc
