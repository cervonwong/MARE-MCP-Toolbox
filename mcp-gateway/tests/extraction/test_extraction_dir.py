"""Phase 10 GREEN tests for extraction.extraction_dir (D-07).

Engine-prefix naming + UTC timestamp + 4-hex-char rand suffix; collision-free.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from mcp_gateway import extraction


_DIRNAME_RE = re.compile(r"^(binwalk|unblob|upx)-\d{8}T\d{6}Z-[0-9a-f]{4}$")


def test_binwalk_engine_prefix(tmp_path: Path):
    case = tmp_path / "001-case"
    case.mkdir()
    out = extraction.extraction_dir(case, "binwalk")
    assert out.exists() and out.is_dir()
    assert out.parent.name == "extracted"
    assert out.parent.parent.resolve() == case.resolve()
    assert _DIRNAME_RE.match(out.name), f"basename {out.name!r} does not match engine regex"
    assert out.name.startswith("binwalk-")


def test_unblob_engine_prefix(tmp_path: Path):
    case = tmp_path / "002-case"
    case.mkdir()
    out = extraction.extraction_dir(case, "unblob")
    assert out.exists() and out.is_dir()
    assert _DIRNAME_RE.match(out.name)
    assert out.name.startswith("unblob-")


def test_upx_engine_prefix(tmp_path: Path):
    case = tmp_path / "003-case"
    case.mkdir()
    out = extraction.extraction_dir(case, "upx")
    assert out.exists() and out.is_dir()
    assert _DIRNAME_RE.match(out.name)
    assert out.name.startswith("upx-")


def test_rand4_avoids_collision(tmp_path: Path):
    """Five extraction_dir calls in the same second must yield five distinct paths."""
    case = tmp_path / "004-case"
    case.mkdir()
    names = set()
    for _ in range(5):
        out = extraction.extraction_dir(case, "binwalk")
        names.add(out.name)
    assert len(names) == 5, f"collision in 5 calls: {names}"


def test_rejects_invalid_engine(tmp_path: Path):
    case = tmp_path / "005-case"
    case.mkdir()
    with pytest.raises(ValueError) as exc_info:
        extraction.extraction_dir(case, "ghidra")  # type: ignore[arg-type]
    msg = str(exc_info.value)
    # Mentions the allowed engine set
    assert "binwalk" in msg and "unblob" in msg and "upx" in msg
