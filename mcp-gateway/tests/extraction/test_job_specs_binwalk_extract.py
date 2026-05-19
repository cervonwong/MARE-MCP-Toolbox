"""Phase 10 GREEN tests for extraction._build_binwalk_extract_argv (D-12).

binwalk3 has no --depth flag (Assumption A2); matryoshka=True adds -M.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mcp_gateway import extraction


@pytest.fixture
def _patched_resolve_sample(monkeypatch):
    def _fake_resolve(sample: str) -> str:
        return "/agent/uploads/deadbeef/" + Path(sample).name
    monkeypatch.setattr(
        "mcp_gateway.tools.samples.resolve_sample",
        _fake_resolve,
    )
    return _fake_resolve


def test_argv_shape(tmp_path, _patched_resolve_sample):
    """matryoshka=False -> argv has no -M flag."""
    case = tmp_path / "400-case"
    case.mkdir()
    ext_dir = case / "extracted" / "binwalk-20260519T143211Z-1111"
    ext_dir.mkdir(parents=True)

    argv = extraction._build_binwalk_extract_argv(
        case,
        {
            "sample": "fw.bin",
            "extraction_dir": str(ext_dir),
            "matryoshka": False,
        },
    )

    # Shape: binwalk -e -C <ext> -l <ext>/binwalk-report.json -q -- <sample>
    assert argv[0] == "binwalk"
    assert "-e" in argv
    assert "-M" not in argv  # matryoshka=False
    assert "-C" in argv
    c_idx = argv.index("-C")
    assert argv[c_idx + 1] == str(ext_dir)
    assert "-l" in argv
    l_idx = argv.index("-l")
    assert argv[l_idx + 1] == str(ext_dir / "binwalk-report.json")
    assert "-q" in argv
    assert "--" in argv
    sep = argv.index("--")
    assert sep == len(argv) - 2
    assert argv[-1] == "/agent/uploads/deadbeef/fw.bin"


def test_matryoshka_flag(tmp_path, _patched_resolve_sample):
    """matryoshka=True (default) -> -M placed between -e and -C."""
    case = tmp_path / "401-case"
    case.mkdir()
    ext_dir = case / "extracted" / "binwalk-20260519T143211Z-2222"
    ext_dir.mkdir(parents=True)

    # Default (no key) is matryoshka=True
    argv = extraction._build_binwalk_extract_argv(
        case,
        {"sample": "fw.bin", "extraction_dir": str(ext_dir)},
    )
    assert "-M" in argv
    e_idx = argv.index("-e")
    m_idx = argv.index("-M")
    c_idx = argv.index("-C")
    assert e_idx < m_idx < c_idx

    # Explicit True
    argv2 = extraction._build_binwalk_extract_argv(
        case,
        {"sample": "fw.bin", "extraction_dir": str(ext_dir), "matryoshka": True},
    )
    assert "-M" in argv2


def test_sample_resolved(tmp_path, _patched_resolve_sample):
    case = tmp_path / "402-case"
    case.mkdir()
    ext_dir = case / "extracted" / "binwalk-20260519T143211Z-3333"
    ext_dir.mkdir(parents=True)

    argv = extraction._build_binwalk_extract_argv(
        case,
        {"sample": "rawfw.bin", "extraction_dir": str(ext_dir)},
    )
    # Resolved absolute path under uploads root
    assert argv[-1] == "/agent/uploads/deadbeef/rawfw.bin"
    assert argv[-2] == "--"


def test_extraction_dir_confinement(tmp_path, _patched_resolve_sample):
    case = tmp_path / "403-case"
    case.mkdir()
    outside = tmp_path / "OUTSIDE"
    outside.mkdir()
    with pytest.raises(ValueError):
        extraction._build_binwalk_extract_argv(
            case,
            {"sample": "fw.bin", "extraction_dir": str(outside)},
        )
