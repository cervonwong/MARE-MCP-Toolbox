"""Phase 10 GREEN tests for _mare_meta.json sidecar I/O (D-08).

Atomic JSON writes (Pitfall 6); shallow-merge update; roundtrip preservation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_gateway import extraction


def _make_ext_dir(tmp_path: Path) -> Path:
    case = tmp_path / "100-case"
    case.mkdir()
    return extraction.extraction_dir(case, "binwalk")


def test_write_meta_creates_file(tmp_path: Path):
    d = _make_ext_dir(tmp_path)
    payload = {"engine": "binwalk", "mode": "extract", "status": "running"}
    meta_path = extraction.write_meta(d, payload)
    assert meta_path == d / "_mare_meta.json"
    assert meta_path.is_file()
    on_disk = json.loads(meta_path.read_text(encoding="utf-8"))
    assert on_disk == payload


def test_update_meta_is_atomic(tmp_path: Path):
    """Atomic update: rename is POSIX-atomic so reader never sees partial JSON.

    Sanity-test by writing, updating, and re-reading — at every checkpoint the
    on-disk file must parse as valid JSON (atomic-rename guarantee).
    """
    d = _make_ext_dir(tmp_path)
    extraction.write_meta(d, {"status": "running", "polls": 0})
    meta_path = d / "_mare_meta.json"
    # Read mid-flight should always succeed
    assert json.loads(meta_path.read_text(encoding="utf-8"))["status"] == "running"
    # Perform 5 sequential atomic updates; each one must leave a valid JSON file
    for i in range(1, 6):
        extraction.update_meta(d, {"polls": i})
        # The atomic write_json uses os.rename — the file must still parse.
        parsed = json.loads(meta_path.read_text(encoding="utf-8"))
        assert parsed["polls"] == i
        assert parsed["status"] == "running"


def test_read_meta_roundtrip(tmp_path: Path):
    d = _make_ext_dir(tmp_path)
    payload = {
        "engine": "unblob",
        "mode": "extract",
        "status": "succeeded",
        "exit_code": 0,
        "argv": ["unblob", "--report", "/tmp/x", "--", "/sample"],
        "symlinks_quarantined": 0,
    }
    extraction.write_meta(d, payload)
    got = extraction.read_meta(d)
    assert got == payload


def test_update_meta_preserves_unspecified_fields(tmp_path: Path):
    d = _make_ext_dir(tmp_path)
    extraction.write_meta(d, {"a": 1, "b": 2, "c": "keep"})
    merged = extraction.update_meta(d, {"a": 10})
    assert merged == {"a": 10, "b": 2, "c": "keep"}
    # Re-read from disk to confirm persistence
    on_disk = extraction.read_meta(d)
    assert on_disk == {"a": 10, "b": 2, "c": "keep"}
