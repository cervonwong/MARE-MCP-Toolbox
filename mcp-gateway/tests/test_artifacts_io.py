"""Tests for artifacts_io helpers (Phase 6 / FOUND-04).

Tests `confine_to`, `ensure_subdir`, `tool_log_path`, `EXPANDED_CASE_SUBDIRS`.
Hermetic -- every test creates its own tmp_path case_dir. No shared state.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from mcp_gateway.artifacts_io import (
    EXPANDED_CASE_SUBDIRS,
    confine_to,
    ensure_subdir,
    tool_log_path,
)


def _make_case_dir(tmp_path: Path) -> Path:
    case = tmp_path / "case"
    case.mkdir()
    return case


# ---- SC-5a: confine_to allows relative path inside case_dir ----
def test_confine_to_allows_relative_inside(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    result = confine_to(case, "foo.txt")
    assert result == (case / "foo.txt").resolve()


# ---- SC-5b: non-existing leaf is OK (write-side case) ----
def test_confine_to_allows_nonexisting_leaf(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    result = confine_to(case, "sub/bar.txt")
    assert result.name == "bar.txt"
    assert result.parent.name == "sub"
    # Must NOT raise FileNotFoundError (D-13).


# ---- SC-5c: traversal rejected ----
def test_confine_to_rejects_traversal(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    with pytest.raises(ValueError):
        confine_to(case, "../../etc/passwd")


# ---- SC-5d: absolute path outside rejected ----
def test_confine_to_rejects_absolute_outside(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    with pytest.raises(ValueError):
        confine_to(case, "/etc/passwd")


# ---- SC-5e: symlink whose target lies inside case_dir is allowed ----
def test_confine_to_allows_inside_symlink(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    real = case / "real.txt"
    real.write_text("ok")
    link = case / "link.txt"
    link.symlink_to(real)
    result = confine_to(case, "link.txt")
    assert result == real.resolve()


# ---- SC-5f: symlink whose target leaves case_dir is rejected ----
def test_confine_to_rejects_escaping_symlink(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("escape")
    link = case / "escape-link.txt"
    link.symlink_to(outside)
    with pytest.raises(ValueError):
        confine_to(case, "escape-link.txt")


# ---- SC-5g: NUL byte in path rejected ----
def test_confine_to_rejects_nul_byte(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    with pytest.raises(ValueError):
        confine_to(case, "foo\x00bar.txt")


# ---- D-11 step 1: case_dir must exist ----
def test_confine_to_rejects_nonexistent_case_dir(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does-not-exist"
    with pytest.raises(ValueError):
        confine_to(nonexistent, "foo.txt")


# ---- D-11 step 1: case_dir must be a directory ----
def test_confine_to_rejects_non_directory_case_dir(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("not a dir")
    with pytest.raises(ValueError):
        confine_to(f, "foo.txt")


# ---- D-09: tool_log_path filename format ----
def test_tool_log_path_format(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    p = tool_log_path(case, "myslug")
    name = p.name
    # <%Y%m%dT%H%M%SZ>-<slug>-<rand4>.txt
    assert re.fullmatch(r"\d{8}T\d{6}Z-myslug-[0-9a-f]{4}\.txt", name), (
        f"name does not match D-09 format: {name!r}"
    )
    assert p.parent.name == "tool-logs"
    assert p.parent.parent == case


# ---- D-09: same-second concurrent calls -> different paths via rand4 ----
def test_tool_log_path_no_collision(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    paths = {tool_log_path(case, "race").name for _ in range(100)}
    # 100 calls in <1 s with 16 bits of entropy -> ~0 collisions expected.
    # Allow tiny chance via birthday paradox but require at least 95 distinct.
    assert len(paths) >= 95, f"only {len(paths)} distinct paths in 100 calls -- rand4 not working"


# ---- D-09: slug regex enforced; auto-lowercase ----
def test_tool_log_path_rejects_bad_slug(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    with pytest.raises(ValueError):
        tool_log_path(case, "BAD SLUG!")
    # Lowercase happy path: "MySlug" -> lowercased to "myslug" -> matches regex
    p = tool_log_path(case, "MySlug")
    assert "myslug" in p.name


# ---- D-15: ensure_subdir idempotent ----
def test_ensure_subdir_idempotent(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    p1 = ensure_subdir(case, "tool-logs")
    p2 = ensure_subdir(case, "tool-logs")
    assert p1 == p2
    assert p1.is_dir()


# ---- D-15: slug regex on subdir name ----
def test_ensure_subdir_validates_slug(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    with pytest.raises(ValueError):
        ensure_subdir(case, "BADNAME!!")


# ---- D-16: EXPANDED_CASE_SUBDIRS catalog ----
def test_expanded_case_subdirs_catalog() -> None:
    expected = {
        "tool-logs", "extracted", "hex", "rop",
        "dynamic", "qemu", "disassembly", "decompilation", "xrefs",
    }
    assert set(EXPANDED_CASE_SUBDIRS) == expected
    assert len(EXPANDED_CASE_SUBDIRS) == 9
    assert isinstance(EXPANDED_CASE_SUBDIRS, tuple)


# ---- D-16: lazy -- no subdirs created at case init ----
def test_no_empty_subdirs_at_case_init(tmp_path: Path) -> None:
    case = _make_case_dir(tmp_path)
    for name in EXPANDED_CASE_SUBDIRS:
        assert not (case / name).exists(), (
            f"{name} exists in freshly-created case_dir -- catalog must be lazy-create"
        )
