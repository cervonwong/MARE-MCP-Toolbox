"""Phase 7 ARTIF-05 + D-26, D-27 -- depth-2 resource walk.

Wave-0 RED stubs. Wave-1 extends tools/resources.py::_build_resource_list to walk
EXPANDED_CASE_SUBDIRS at depth 2. Tests flip RED -> GREEN at that point.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


def _seed_case(tmp_status_dir: Path, name: str) -> Path:
    case = tmp_status_dir / name
    case.mkdir()
    return case


def test_resources_depth_2(tmp_status_dir) -> None:
    """D-26: case with files in tool-logs/, hex/, rop/ produces depth-2 resources."""
    from mcp_gateway.tools.resources import _build_resource_list
    case = _seed_case(tmp_status_dir, "300-depth2")
    (case / "tool-logs").mkdir()
    (case / "tool-logs" / "a.txt").write_text("a")
    (case / "hex").mkdir()
    (case / "hex" / "b.bin").write_bytes(b"b")
    (case / "rop").mkdir()
    (case / "rop" / "c.json").write_text("[]")
    uris = {str(r.uri) for r in _build_resource_list()}
    assert any(u.endswith("/300-depth2/tool-logs/a.txt") for u in uris), uris
    assert any(u.endswith("/300-depth2/hex/b.bin") for u in uris), uris
    assert any(u.endswith("/300-depth2/rop/c.json") for u in uris), uris


def test_resources_no_depth_3(tmp_status_dir) -> None:
    """D-26: extracted/<sub>/<file> (depth 3) is NOT exposed in Phase 7."""
    from mcp_gateway.tools.resources import _build_resource_list
    case = _seed_case(tmp_status_dir, "301-deep")
    (case / "extracted" / "sub").mkdir(parents=True)
    (case / "extracted" / "sub" / "deep.bin").write_bytes(b"deep")
    (case / "extracted" / "topfile.txt").write_text("ok")
    uris = {str(r.uri) for r in _build_resource_list()}
    # Depth-2 file IS exposed:
    assert any(u.endswith("/301-deep/extracted/topfile.txt") for u in uris)
    # Depth-3 file is NOT:
    assert not any(u.endswith("/sub/deep.bin") for u in uris), uris


def test_resources_skip_hidden(tmp_status_dir) -> None:
    """D-26: hidden files (.dotfile) in subdirs are NOT enumerated."""
    from mcp_gateway.tools.resources import _build_resource_list
    case = _seed_case(tmp_status_dir, "302-hidden")
    (case / "tool-logs").mkdir()
    (case / "tool-logs" / ".gsd_state").write_text("hidden")
    (case / "tool-logs" / "visible.txt").write_text("visible")
    uris = {str(r.uri) for r in _build_resource_list()}
    assert any(u.endswith("/302-hidden/tool-logs/visible.txt") for u in uris)
    assert not any(u.endswith("/.gsd_state") for u in uris)


def test_resources_max_files_cap(tmp_status_dir, monkeypatch) -> None:
    """D-26: per-resources/list cap of MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES."""
    from mcp_gateway.tools.resources import _build_resource_list
    case = _seed_case(tmp_status_dir, "303-cap")
    (case / "tool-logs").mkdir()
    for i in range(20):
        (case / "tool-logs" / f"f{i:02d}.txt").write_text("x")
    monkeypatch.setenv("MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES", "5")
    out = _build_resource_list()
    assert len(out) <= 5
