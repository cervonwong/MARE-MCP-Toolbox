"""Phase 10 GREEN tests for extraction.quarantine_symlinks (D-15 / D-16).

Recursive walk without following links; sentinel format verbatim; idempotency.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcp_gateway import extraction


def _make_ext_dir(tmp_path: Path) -> Path:
    case = tmp_path / "200-case"
    case.mkdir()
    return extraction.extraction_dir(case, "unblob")


def test_sentinel_body_format(tmp_path: Path):
    d = _make_ext_dir(tmp_path)
    target = tmp_path / "outside-target.bin"
    target.write_text("hostile-target-data")
    link = d / "evil-link"
    os.symlink(str(target), str(link))

    count, paths = extraction.quarantine_symlinks(d)

    assert count == 1
    assert paths == ["evil-link"]
    # Original symlink unlinked
    assert not link.is_symlink()
    assert not link.exists()
    # Sentinel file created
    sentinel = d / "evil-link.symlink-target.txt"
    assert sentinel.is_file()
    body = sentinel.read_text(encoding="utf-8")
    # Verify all 5 D-16 header lines appear in the sentinel body
    assert "SYMLINK QUARANTINE" in body
    assert "Original symlink (relative within extraction):" in body
    assert "evil-link" in body
    assert "Target (as-written by extractor):" in body
    assert "Resolved target (canonical absolute):" in body
    assert "Quarantined:" in body
    # The resolved target should mention our outside path
    assert str(target.resolve()) in body or "outside-target.bin" in body


def test_idempotent(tmp_path: Path):
    """Second quarantine pass must find zero new symlinks (the sentinels are
    real files, not symlinks)."""
    d = _make_ext_dir(tmp_path)
    target = tmp_path / "target.bin"
    target.write_text("x")
    os.symlink(str(target), str(d / "link1"))
    os.symlink(str(target), str(d / "link2"))

    count1, paths1 = extraction.quarantine_symlinks(d)
    assert count1 == 2
    assert set(paths1) == {"link1", "link2"}

    # Run a second time — sentinel files are *real* files, not symlinks
    count2, paths2 = extraction.quarantine_symlinks(d)
    assert count2 == 0
    assert paths2 == []
    # No new files written
    expected = {"link1.symlink-target.txt", "link2.symlink-target.txt"}
    actual = {p.name for p in d.iterdir() if p.is_file()}
    assert actual == expected


def test_no_follow_walk(tmp_path: Path):
    """A symlinked subdir whose target lives OUTSIDE the extraction tree must
    NOT be traversed — only the symlink itself is quarantined.

    Set up: extraction_dir/inner-link -> outside_dir, where outside_dir contains
    a "secret.bin". After quarantine, secret.bin must NOT be processed.
    """
    d = _make_ext_dir(tmp_path)
    outside = tmp_path / "secret-outside"
    outside.mkdir()
    secret_link_target = outside / "secret.bin"
    secret_link_target.write_text("shhh")
    # Pre-create a "decoy" symlink inside outside that, if followed, would be
    # quarantined incorrectly.
    decoy_outside_target = tmp_path / "decoy-target.txt"
    decoy_outside_target.write_text("decoy")
    os.symlink(str(decoy_outside_target), str(outside / "decoy-link"))
    # Now create the dir-symlink in the extraction tree.
    os.symlink(str(outside), str(d / "inner-link"))

    count, paths = extraction.quarantine_symlinks(d)

    # Only "inner-link" itself should be quarantined; the decoy-link inside
    # outside/ must NOT be followed.
    assert count == 1
    assert paths == ["inner-link"]
    # The decoy symlink inside outside/ must be untouched (no sentinel created
    # under d for it)
    assert not (d / "decoy-link.symlink-target.txt").exists()
    assert not (d / "inner-link" / "decoy-link.symlink-target.txt").exists()
    # The original outside decoy-link is untouched
    assert (outside / "decoy-link").is_symlink()
