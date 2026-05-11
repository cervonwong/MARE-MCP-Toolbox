"""CLI-04 unit tests: ARTIFACTS list, _list_cases, _build_resource_list, path safety."""
from __future__ import annotations
from pathlib import Path

import pytest

from mcp_gateway.tools import resources as R


def test_artifacts_count_is_13():
    """D-03: all 13 required artifacts per artifact-spec.md."""
    assert len(R.ARTIFACTS) == 13


def test_artifacts_contains_required_files():
    required = {
        "00_sample_profile.md",
        "01_strings_raw.txt",
        "02_strings_interesting.md",
        "03_imports_raw.txt",
        "04_imports_interesting.md",
        "05_behavior_hypotheses.md",
        "06_component_inventory.md",
        "07_interaction_model.md",
        "08_deep_analysis_plan.md",
        "09_priority_queue.md",
        "10_reporting_draft.md",
        "INDEX.md",
        "CURRENT_STATE.json",
    }
    assert set(R.ARTIFACTS) == required


def test_list_cases_empty_when_status_root_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "STATUS_ROOT", tmp_path / "nope")
    assert R._list_cases() == []


def test_list_cases_filters_by_case_name_regex(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "STATUS_ROOT", tmp_path)
    (tmp_path / "001-good.bin").mkdir()
    (tmp_path / "999-also.dll").mkdir()
    (tmp_path / "no-prefix").mkdir()      # not matching CASE_NAME_RE
    (tmp_path / "01-too-short").mkdir()   # too short prefix (regex needs \d{3})
    (tmp_path / "loose.txt").write_text("x")
    cases = R._list_cases()
    assert cases == ["001-good.bin", "999-also.dll"]


def test_build_resource_list_yields_13_per_case(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "STATUS_ROOT", tmp_path)
    (tmp_path / "001-x.bin").mkdir()
    (tmp_path / "002-y.bin").mkdir()
    listed = R._build_resource_list()
    assert len(listed) == 13 * 2
    uris = [str(r.uri) for r in listed]
    assert "mare://cases/001-x.bin/CURRENT_STATE.json" in uris
    assert "mare://cases/002-y.bin/INDEX.md" in uris
    # MIME types per D-04
    by_uri = {str(r.uri): r.mimeType for r in listed}
    assert by_uri["mare://cases/001-x.bin/CURRENT_STATE.json"] == "application/json"
    assert by_uri["mare://cases/001-x.bin/INDEX.md"] == "text/markdown"
    assert by_uri["mare://cases/001-x.bin/01_strings_raw.txt"] == "text/plain"


def test_safe_artifact_path_rejects_invalid_case_name():
    with pytest.raises(ValueError, match="invalid case name"):
        R._safe_artifact_path("not-a-case", "CURRENT_STATE.json")


def test_safe_artifact_path_rejects_unknown_artifact():
    with pytest.raises(ValueError, match="unknown artifact"):
        R._safe_artifact_path("001-foo.bin", "evil.txt")


def test_safe_artifact_path_rejects_path_traversal_in_case():
    """T-04-01: dotdot segments rejected by CASE_NAME_RE."""
    with pytest.raises(ValueError, match="invalid case name"):
        R._safe_artifact_path("../etc", "INDEX.md")


def test_safe_artifact_path_resolves_under_status_root(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "STATUS_ROOT", tmp_path)
    case = "001-x.bin"
    (tmp_path / case).mkdir()
    p = R._safe_artifact_path(case, "INDEX.md")
    assert str(p).startswith(str(tmp_path.resolve()))
    assert p.name == "INDEX.md"
