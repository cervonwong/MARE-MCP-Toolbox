"""CLI-01 (D-11): ./run_docker.sh --print-config behavior.

Tests two paths:
  1. Missing token file -> non-zero exit + hint on stderr.
  2. Present token file -> exit 0 + ready-block rendered with the token visible.

We invoke the script directly. Because run_docker.sh derives HOST_PWD from
$SCRIPT_DIR/workspace, we copy the script into tmp_path with a sibling
workspace/ dir so its computed token-file path lands in tmp_path/workspace/
without touching the real repo workspace/.
"""
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "run_docker.sh"


def _staged_script(tmp_path: Path) -> Path:
    """Copy run_docker.sh into tmp_path with a fresh workspace/ dir alongside it.
    The script computes HOST_PWD as $SCRIPT_DIR/workspace, so the staged copy's
    HOST_PWD becomes tmp_path/workspace.
    """
    staged = tmp_path / "run_docker.sh"
    shutil.copy2(SCRIPT, staged)
    staged.chmod(0o755)
    (tmp_path / "workspace").mkdir(exist_ok=True)
    return staged


def test_help_documents_print_config():
    res = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert res.returncode == 0, res.stderr
    assert "--print-config" in res.stdout, res.stdout


def test_print_config_missing_token_exits_nonzero(tmp_path):
    staged = _staged_script(tmp_path)
    # No token file in tmp_path/workspace/
    res = subprocess.run(
        ["bash", str(staged), "--print-config"],
        capture_output=True, text=True, timeout=10,
        cwd=tmp_path,
    )
    assert res.returncode != 0, f"expected non-zero, got {res.returncode}; stdout={res.stdout!r}"
    assert "no token file" in res.stderr.lower(), res.stderr
    # Hint message points to --remote
    assert "--remote" in res.stderr, res.stderr


def test_print_config_with_token_emits_ready_block(tmp_path):
    staged = _staged_script(tmp_path)
    fake_token = "test-bearer-token-deadbeef-12345"
    (tmp_path / "workspace" / ".mcp-gateway-token").write_text(fake_token + "\n")
    res = subprocess.run(
        ["bash", str(staged), "--print-config"],
        capture_output=True, text=True, timeout=10,
        cwd=tmp_path,
    )
    assert res.returncode == 0, f"stderr={res.stderr!r}"
    assert "MARE-MCP-Toolbox Gateway is ready" in res.stdout, res.stdout
    assert fake_token in res.stdout, "token not echoed in ready-block"
    # Confirms the JSON snippet is present (CLI-01 onboarding shape).
    assert '"type": "http"' in res.stdout
    assert '"mare-toolbox"' in res.stdout
