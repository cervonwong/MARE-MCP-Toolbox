"""Phase 10 extraction test fixtures.

Mirrors Phase 9 conftest pattern: _require_<tool>_or_skip gates for slow integration
tests; fake extraction-tree builder for unit tests that don't need real subprocesses.
"""
from __future__ import annotations
import json
import os
import shutil
from pathlib import Path
import pytest


@pytest.fixture
def _require_binwalk_or_skip() -> None:
    if shutil.which("binwalk") is None:
        pytest.skip("binwalk not on PATH (Phase 10 slow integration)")


@pytest.fixture
def _require_unblob_or_skip() -> None:
    if shutil.which("unblob") is None:
        pytest.skip("unblob not on PATH (Phase 10 slow integration)")


@pytest.fixture
def _require_upx_or_skip() -> None:
    if shutil.which("upx") is None and shutil.which("upx-ucl") is None:
        pytest.skip("upx/upx-ucl not on PATH (Phase 10 slow integration)")


@pytest.fixture
def fake_extraction_tree(tmp_path: Path):
    """Builder factory: returns a callable that mints fake `extracted/<engine>-<ts>-<rand>/`
    subdirs with a populated _mare_meta.json and N regular files.

    Used by test_list_extracted_files.py + test_extract_monitor.py for unit-level
    coverage without invoking real binwalk/unblob/upx.
    """
    case = tmp_path / "case-001"
    (case / "extracted").mkdir(parents=True)

    def _make(engine: str, ts: str = "20260519T143211Z", rand4: str = "a3f9",
              file_count: int = 0, status: str = "succeeded",
              symlinks_quarantined: int = 0, cap_exceeded: bool = False) -> Path:
        d = case / "extracted" / f"{engine}-{ts}-{rand4}"
        d.mkdir()
        meta = {
            "engine": engine, "mode": "extract", "started_at": "2026-05-19T14:32:11Z",
            "completed_at": "2026-05-19T14:35:00Z", "status": status,
            "exit_code": 0 if status == "succeeded" else 1,
            "case_dir": str(case), "extraction_dir": f"extracted/{engine}-{ts}-{rand4}",
            "sample": "/agent/uploads/deadbeef/sample.bin",
            "sample_sha256": "deadbeef" * 8, "argv": [engine, "/agent/uploads/deadbeef/sample.bin"],
            "job_id": None, "log_path": "tool-logs/foo.txt",
            "symlinks_quarantined": symlinks_quarantined, "cap_exceeded": cap_exceeded,
            "extract_bytes_total": 0, "monitor_polls": 0,
        }
        (d / "_mare_meta.json").write_text(json.dumps(meta))
        for i in range(file_count):
            (d / f"file{i:04d}.bin").write_bytes(b"x" * 16)
        return d

    return case, _make
