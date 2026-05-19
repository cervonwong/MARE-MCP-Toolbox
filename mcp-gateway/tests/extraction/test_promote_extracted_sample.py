"""Phase 10 GREEN tests for tools.extract.promote_extracted_sample (D-06 / D-14).

Mocks: STATUS_ROOT, UPLOADS_ROOT, run_script, resolve_case_dir.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from mcp_gateway import extraction
from mcp_gateway.tools import extract
from mcp_gateway.tools import samples as tools_samples


def _setup_roots(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    """Point UPLOADS_ROOT and STATUS_ROOT at tmp_path-local dirs."""
    uploads = tmp_path / "uploads"
    status = tmp_path / "status"
    uploads.mkdir()
    status.mkdir()

    # tools.samples module-level globals
    monkeypatch.setattr(tools_samples, "UPLOADS_ROOT", uploads)
    monkeypatch.setattr(tools_samples, "STATUS_ROOT", status)
    monkeypatch.setattr(
        tools_samples, "ALLOWED_PREFIXES", (uploads, status),
    )
    # tools.extract re-imports STATUS_ROOT/UPLOADS_ROOT at module top
    monkeypatch.setattr(extract, "STATUS_ROOT", status)
    monkeypatch.setattr(extract, "UPLOADS_ROOT", uploads)

    # resolve_case_dir is a closure that consults samples.STATUS_ROOT — works
    # because we patched samples.STATUS_ROOT above. But we still patch the
    # extract-module binding for direct calls.
    def _fake_case(case_dir: str) -> str:
        return str(Path(case_dir).resolve())
    monkeypatch.setattr(extract, "resolve_case_dir", _fake_case)
    return uploads, status


def _patch_run_script(monkeypatch, status: Path, new_case_name: str):
    """Stub subprocess_runner.run_script so init_status_tree.sh is faked: it
    creates the new case directory in STATUS_ROOT and returns exit_code=0.
    """
    async def _fake_run_script(argv, *, cwd="/agent", timeout=60.0, env=None):
        new_case = status / new_case_name
        new_case.mkdir(parents=True, exist_ok=True)
        return {
            "exit_code": 0,
            "stdout": f"created {new_case}\n",
            "stderr": "",
        }
    monkeypatch.setattr(extract, "run_script", _fake_run_script)


def _make_parent_with_child(parent: Path, content: bytes = b"carved-child-bytes") -> Path:
    """Set up parent_case_dir/extracted/unblob-.../child.bin."""
    ext_dir = parent / "extracted" / "unblob-20260519T143211Z-aaaa"
    ext_dir.mkdir(parents=True)
    child = ext_dir / "child.bin"
    child.write_bytes(content)
    return child


def test_promotion_flow(tmp_path, monkeypatch):
    uploads, status = _setup_roots(monkeypatch, tmp_path)
    parent = status / "100-parent-case"
    parent.mkdir()
    child = _make_parent_with_child(parent)
    _patch_run_script(monkeypatch, status, "101-child-case")

    res = asyncio.run(
        extract.promote_extracted_sample(str(parent), str(child))
    )

    assert "error" not in res, res
    assert res["new_case_dir"].endswith("101-child-case")
    assert res["new_case_name"] == "101-child-case"
    assert isinstance(res["sha256"], str) and len(res["sha256"]) == 64
    assert res["idempotent_reuse"] is False
    assert "lineage_path" in res
    # _lineage.json was written
    lineage_p = Path(res["lineage_path"])
    assert lineage_p.is_file()
    lineage = json.loads(lineage_p.read_text(encoding="utf-8"))
    assert lineage["promoted_sha256"] == res["sha256"]
    assert lineage["parent_case_dir"] == str(parent.resolve())


def test_idempotent_by_sha256(tmp_path, monkeypatch):
    uploads, status = _setup_roots(monkeypatch, tmp_path)
    parent = status / "100-parent-case"
    parent.mkdir()
    child = _make_parent_with_child(parent, content=b"idempotent-test")
    _patch_run_script(monkeypatch, status, "101-child-case")

    res1 = asyncio.run(extract.promote_extracted_sample(str(parent), str(child)))
    assert "error" not in res1, res1
    assert res1["idempotent_reuse"] is False
    first_case_dir = res1["new_case_dir"]

    # Second call: should detect existing lineage and reuse
    res2 = asyncio.run(extract.promote_extracted_sample(str(parent), str(child)))
    assert "error" not in res2, res2
    assert res2["idempotent_reuse"] is True
    assert res2["new_case_dir"] == first_case_dir
    assert res2["sha256"] == res1["sha256"]


def test_force_new_bypasses_idempotent(tmp_path, monkeypatch):
    uploads, status = _setup_roots(monkeypatch, tmp_path)
    parent = status / "100-parent-case"
    parent.mkdir()
    child = _make_parent_with_child(parent, content=b"force-new-bytes")
    _patch_run_script(monkeypatch, status, "101-child-case")

    res1 = asyncio.run(extract.promote_extracted_sample(str(parent), str(child)))
    assert res1["idempotent_reuse"] is False

    # Switch the fake to mint a different case dir name on the next call
    _patch_run_script(monkeypatch, status, "102-child-case")

    res2 = asyncio.run(
        extract.promote_extracted_sample(str(parent), str(child), force_new=True)
    )
    assert "error" not in res2, res2
    assert res2["idempotent_reuse"] is False
    assert res2["new_case_dir"] != res1["new_case_dir"]


def test_rejects_outside_extracted(tmp_path, monkeypatch):
    uploads, status = _setup_roots(monkeypatch, tmp_path)
    parent = status / "100-parent-case"
    parent.mkdir()
    # Create a file OUTSIDE extracted/ but inside the case
    outside_in_case = parent / "stray.bin"
    outside_in_case.write_bytes(b"stray")

    res = asyncio.run(
        extract.promote_extracted_sample(str(parent), str(outside_in_case))
    )

    assert isinstance(res, dict)
    assert "error" in res
    assert "extracted" in res["error"]


def test_rejects_symlink_sentinel(tmp_path, monkeypatch):
    uploads, status = _setup_roots(monkeypatch, tmp_path)
    parent = status / "100-parent-case"
    parent.mkdir()
    ext_dir = parent / "extracted" / "binwalk-20260519T143211Z-bbbb"
    ext_dir.mkdir(parents=True)
    sentinel = ext_dir / "link.symlink-target.txt"
    sentinel.write_text("SYMLINK QUARANTINE\n... etc")

    res = asyncio.run(
        extract.promote_extracted_sample(str(parent), str(sentinel))
    )
    assert isinstance(res, dict)
    assert "error" in res
    assert "symlink quarantine sentinel" in res["error"]


def test_sha256_recomputed(tmp_path, monkeypatch):
    """sha256 in the returned dict must equal hashlib.sha256(child_bytes), even
    if some fake meta would say otherwise.
    """
    import hashlib
    uploads, status = _setup_roots(monkeypatch, tmp_path)
    parent = status / "100-parent-case"
    parent.mkdir()
    child_bytes = b"recompute-me-please-12345"
    expected = hashlib.sha256(child_bytes).hexdigest()
    child = _make_parent_with_child(parent, content=child_bytes)
    _patch_run_script(monkeypatch, status, "101-child-case")

    res = asyncio.run(extract.promote_extracted_sample(str(parent), str(child)))

    assert "error" not in res, res
    assert res["sha256"] == expected


def test_errors_structured(tmp_path, monkeypatch):
    """Invalid parent_case_dir -> D-22 shape 1 error dict (not raised)."""
    def _bad_case(case_dir: str) -> str:
        raise ValueError("not under STATUS_ROOT")
    monkeypatch.setattr(extract, "resolve_case_dir", _bad_case)

    res = asyncio.run(
        extract.promote_extracted_sample("/nonexistent/parent", "/somewhere/x.bin")
    )
    assert isinstance(res, dict)
    assert res.get("error") == "invalid case_dir"
