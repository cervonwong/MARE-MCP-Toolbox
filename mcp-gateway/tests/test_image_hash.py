"""FOUND-01 / Phase 5: regression test for the mcp-gateway content hash.

Invariants:
  SC-1: editing any file under mcp-gateway/src/ changes the hash.
  SC-2: editing mcp-gateway/pyproject.toml changes the hash.
  SC-3: writes into pruned paths (__pycache__, .venv, *.egg-info, .pytest_cache)
        do NOT change the hash.
  SC-4: the regression-test-of-record -- same as SC-1, named explicitly.
  Bonus: toggling INSTALL_BINARY_NINJA=0->1 (with a stub zip) changes the hash.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts" / "compute_image_hash.sh"


@pytest.fixture
def build_root(tmp_path: Path) -> Path:
    """Minimal mcp-gateway build-root mirror (D-08)."""
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    (tmp_path / "docker-bin").mkdir()
    (tmp_path / "docker-bin" / "tool.sh").write_text("#!/bin/bash\necho hi\n")
    gw = tmp_path / "mcp-gateway"
    (gw / "src").mkdir(parents=True)
    (gw / "src" / "x.py").write_text("x = 1\n")
    (gw / "pyproject.toml").write_text("[project]\nname='mcp-gateway'\n")
    # Pruned paths -- must not contribute to hash.
    (gw / "__pycache__").mkdir()
    (gw / "__pycache__" / "stale.pyc").write_bytes(b"\x00\x01")
    (gw / ".venv" / "lib").mkdir(parents=True)
    (gw / ".venv" / "lib" / "marker").write_text("venv\n")
    (gw / "mcp_gateway.egg-info").mkdir()
    (gw / "mcp_gateway.egg-info" / "PKG-INFO").write_text("metadata\n")
    (gw / ".pytest_cache").mkdir()
    (gw / ".pytest_cache" / "CACHEDIR.TAG").write_text("Signature\n")
    return tmp_path


def _hash(build_root: Path, env_extra: dict | None = None) -> str:
    base_env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    if env_extra:
        base_env.update(env_extra)
    res = subprocess.run(
        ["bash", str(HELPER), str(build_root)],
        capture_output=True, text=True, timeout=10, env=base_env,
    )
    assert res.returncode == 0, f"helper failed: stderr={res.stderr!r}"
    out = res.stdout.strip()
    assert len(out) == 64, f"expected 64-char hex, got {out!r}"
    return out


def test_helper_exists_and_executable():
    assert HELPER.is_file(), f"missing helper at {HELPER}"
    assert os.access(HELPER, os.X_OK), f"helper not executable: {HELPER}"


def test_baseline_hash_stable(build_root):
    """Same fixture invoked twice produces the same hash."""
    assert _hash(build_root) == _hash(build_root)


def test_sc1_src_edit_changes_hash(build_root):
    """SC-1 + SC-4: editing mcp-gateway/src/x.py changes the hash."""
    baseline = _hash(build_root)
    (build_root / "mcp-gateway" / "src" / "x.py").write_text("x = 2  # changed\n")
    assert _hash(build_root) != baseline


def test_sc2_pyproject_edit_changes_hash(build_root):
    """SC-2: editing mcp-gateway/pyproject.toml changes the hash."""
    baseline = _hash(build_root)
    (build_root / "mcp-gateway" / "pyproject.toml").write_text(
        "[project]\nname='mcp-gateway-edited'\n"
    )
    assert _hash(build_root) != baseline


@pytest.mark.parametrize("pruned_subdir,filename", [
    ("__pycache__", "new.pyc"),
    (".venv", "new-file"),
    ("mcp_gateway.egg-info", "new-meta"),
    (".pytest_cache", "new-cache"),
])
def test_sc3_pruned_writes_do_not_change_hash(build_root, pruned_subdir, filename):
    """SC-3a-d: writes under pruned paths do not flap the hash."""
    baseline = _hash(build_root)
    target = build_root / "mcp-gateway" / pruned_subdir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"new content")
    assert _hash(build_root) == baseline


def test_binja_toggle_changes_hash(build_root, tmp_path):
    """D-10 bonus: toggling INSTALL_BINARY_NINJA with a stub zip changes the hash."""
    stub_zip = tmp_path / "binja.zip"
    stub_zip.write_bytes(b"PK\x03\x04stub")
    baseline = _hash(build_root)
    toggled = _hash(build_root, env_extra={
        "INSTALL_BINARY_NINJA": "1",
        "BINARY_NINJA_ZIP": str(stub_zip),
    })
    assert toggled != baseline


def test_helper_clean_env_no_binja_inputs(build_root):
    """D-10: clean-env invocation succeeds with no Binja/IDA env vars set."""
    # Just asserts _hash() works with the default base env (no INSTALL_* vars).
    out = _hash(build_root)
    assert len(out) == 64


def test_missing_dockerfile_exits_nonzero(tmp_path):
    """D-05 contract: clear stderr message on missing inputs."""
    (tmp_path / "docker-bin").mkdir()
    (tmp_path / "mcp-gateway").mkdir()
    res = subprocess.run(
        ["bash", str(HELPER), str(tmp_path)],
        capture_output=True, text=True, timeout=10,
        env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")},
    )
    assert res.returncode != 0
    assert "Dockerfile" in res.stderr
