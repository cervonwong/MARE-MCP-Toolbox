"""Phase 10 GREEN tests for extraction._build_unblob_argv (D-12).

Pure-function argv builder; sample resolved via tools.samples; depth bounds;
extraction_dir confinement check.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mcp_gateway import extraction


@pytest.fixture
def _patched_resolve_sample(monkeypatch):
    """Stub resolve_sample so we don't need a real ALLOWED_PREFIXES file."""
    def _fake_resolve(sample: str) -> str:
        # Pretend the sample is absolute under uploads; return canonical absolute.
        return "/agent/uploads/deadbeef/" + Path(sample).name
    monkeypatch.setattr(
        "mcp_gateway.tools.samples.resolve_sample",
        _fake_resolve,
    )
    return _fake_resolve


def test_argv_shape(tmp_path, _patched_resolve_sample):
    case = tmp_path / "300-case"
    case.mkdir()
    ext_dir = case / "extracted" / "unblob-20260519T143211Z-abcd"
    ext_dir.mkdir(parents=True)

    argv = extraction._build_unblob_argv(
        case,
        {
            "sample": "deadbeef",
            "extraction_dir": str(ext_dir),
            "depth": 5,
        },
    )

    # Shape: unblob --report <ext>/report.json -e <ext> -d 5 -- <sample>
    assert argv[0] == "unblob"
    assert "--report" in argv
    report_idx = argv.index("--report")
    assert argv[report_idx + 1] == str(ext_dir / "report.json")
    assert "-e" in argv
    e_idx = argv.index("-e")
    assert argv[e_idx + 1] == str(ext_dir)
    assert "-d" in argv
    d_idx = argv.index("-d")
    assert argv[d_idx + 1] == "5"
    # `--` separator before sample
    assert "--" in argv
    sep = argv.index("--")
    assert sep == len(argv) - 2
    assert argv[-1].startswith("/agent/uploads/deadbeef/")


def test_sample_resolved(tmp_path, _patched_resolve_sample):
    """The argv builder must call resolve_sample — argv must contain the
    resolved absolute path, not the raw input string."""
    case = tmp_path / "301-case"
    case.mkdir()
    ext_dir = case / "extracted" / "unblob-20260519T143211Z-aaaa"
    ext_dir.mkdir(parents=True)

    argv = extraction._build_unblob_argv(
        case,
        {
            "sample": "rawname.bin",
            "extraction_dir": str(ext_dir),
        },
    )

    # The fake resolve_sample maps the input to /agent/uploads/deadbeef/<basename>.
    assert argv[-1] == "/agent/uploads/deadbeef/rawname.bin"
    # Raw "rawname.bin" must not appear by itself
    assert "rawname.bin" not in argv  # only present as basename of resolved path
    # Defense-in-depth: -- separator placed before sample
    assert argv[-2] == "--"


def test_depth_bounds(tmp_path, _patched_resolve_sample):
    case = tmp_path / "302-case"
    case.mkdir()
    ext_dir = case / "extracted" / "unblob-20260519T143211Z-bbbb"
    ext_dir.mkdir(parents=True)

    # depth=0 must raise
    with pytest.raises(ValueError):
        extraction._build_unblob_argv(
            case, {"sample": "x.bin", "extraction_dir": str(ext_dir), "depth": 0}
        )

    # depth=17 must raise
    with pytest.raises(ValueError):
        extraction._build_unblob_argv(
            case, {"sample": "x.bin", "extraction_dir": str(ext_dir), "depth": 17}
        )

    # depth=8 must succeed
    argv = extraction._build_unblob_argv(
        case, {"sample": "x.bin", "extraction_dir": str(ext_dir), "depth": 8}
    )
    assert "8" in argv


def test_extraction_dir_confinement(tmp_path, _patched_resolve_sample):
    """extraction_dir OUTSIDE case_dir must raise ValueError (defense in depth)."""
    case = tmp_path / "303-case"
    case.mkdir()
    outside = tmp_path / "OUTSIDE-DIR"
    outside.mkdir()
    with pytest.raises(ValueError):
        extraction._build_unblob_argv(
            case,
            {
                "sample": "x.bin",
                "extraction_dir": str(outside),
                "depth": 4,
            },
        )
