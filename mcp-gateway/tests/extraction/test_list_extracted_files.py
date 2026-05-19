"""Phase 10 GREEN tests for tools.extract.list_extracted_files (D-05).

Engine-agnostic enumeration, per-extraction file cap, limit truncation,
engine filter, include_quarantined toggle.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mcp_gateway import extraction
from mcp_gateway.tools import extract


def _patch_resolve_case_dir(monkeypatch, case_path: Path) -> None:
    """Make resolve_case_dir a pass-through for the test's case_path so we can
    bypass STATUS_ROOT containment requirements."""
    def _fake(case_dir: str) -> str:
        return str(Path(case_dir).resolve())
    monkeypatch.setattr("mcp_gateway.tools.extract.resolve_case_dir", _fake)


def test_engine_agnostic_enumeration(fake_extraction_tree, monkeypatch):
    case, make = fake_extraction_tree
    _patch_resolve_case_dir(monkeypatch, case)

    make("binwalk", rand4="aaaa", file_count=2)
    make("unblob", rand4="bbbb", file_count=2)
    make("upx", rand4="cccc", file_count=2)

    res = asyncio.run(extract.list_extracted_files(str(case)))

    assert "error" not in res, res
    assert res["case_dir"] == str(case.resolve())
    engines = sorted(e["engine"] for e in res["extractions"])
    assert engines == ["binwalk", "unblob", "upx"]
    assert res["total_extractions"] == 3


def test_files_per_extraction_cap(fake_extraction_tree, monkeypatch):
    """Per-extraction cap = extraction.MAX_FILES_PER_EXTRACTION (5000 default).

    Monkey-patch a small cap so we don't actually create 5000 files.
    """
    case, make = fake_extraction_tree
    _patch_resolve_case_dir(monkeypatch, case)
    monkeypatch.setattr(extraction, "MAX_FILES_PER_EXTRACTION", 10)

    make("binwalk", rand4="aaaa", file_count=15)

    res = asyncio.run(extract.list_extracted_files(str(case)))

    assert "error" not in res, res
    assert len(res["extractions"]) == 1
    ext = res["extractions"][0]
    # The fake builder writes 15 files + 1 _mare_meta.json = 16 candidate files.
    # The per-extraction cap = 10 -> files_truncated must be True.
    assert ext["files_truncated"] is True
    assert len(ext["files"]) == 10


def test_limit_truncation(fake_extraction_tree, monkeypatch):
    """Cross-extraction overall cap = `limit` kwarg. 3 extractions x 200 files
    each = 600 candidate files; pass limit=500 -> total_files_listed == 500
    and truncated=True."""
    case, make = fake_extraction_tree
    _patch_resolve_case_dir(monkeypatch, case)
    # Raise per-extraction cap so the limit, not the per-cap, drives truncation.
    monkeypatch.setattr(extraction, "MAX_FILES_PER_EXTRACTION", 5000)

    make("binwalk", rand4="aaaa", file_count=200)
    make("unblob", rand4="bbbb", file_count=200)
    make("upx", rand4="cccc", file_count=200)

    res = asyncio.run(extract.list_extracted_files(str(case), limit=500))

    assert "error" not in res, res
    assert res["truncated"] is True
    assert res["total_files_listed"] == 500


def test_engine_filter(fake_extraction_tree, monkeypatch):
    case, make = fake_extraction_tree
    _patch_resolve_case_dir(monkeypatch, case)

    make("binwalk", rand4="aaaa", file_count=1)
    make("unblob", rand4="bbbb", file_count=1)
    make("upx", rand4="cccc", file_count=1)

    res = asyncio.run(extract.list_extracted_files(str(case), engine="binwalk"))

    assert "error" not in res, res
    assert len(res["extractions"]) == 1
    assert res["extractions"][0]["engine"] == "binwalk"


def test_exclude_quarantined(fake_extraction_tree, monkeypatch):
    case, make = fake_extraction_tree
    _patch_resolve_case_dir(monkeypatch, case)
    d = make("binwalk", rand4="aaaa", file_count=2)
    # Add a quarantine sentinel
    sentinel = d / "evil-link.symlink-target.txt"
    sentinel.write_text("SYMLINK QUARANTINE\n... etc\n")

    # include_quarantined=True (default) — sentinel should appear
    res_with = asyncio.run(
        extract.list_extracted_files(str(case), include_quarantined=True)
    )
    paths_with = {f["path"] for f in res_with["extractions"][0]["files"]}
    assert any(p.endswith(".symlink-target.txt") for p in paths_with)

    # include_quarantined=False — sentinel must be excluded
    res_without = asyncio.run(
        extract.list_extracted_files(str(case), include_quarantined=False)
    )
    paths_without = {f["path"] for f in res_without["extractions"][0]["files"]}
    assert not any(p.endswith(".symlink-target.txt") for p in paths_without)
