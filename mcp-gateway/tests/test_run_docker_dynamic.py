"""Phase 11 Plan 05: pytest-shell-wrap tests for run_docker.sh --dynamic flag parsing.

Hermetic -- does NOT invoke `docker compose`. The script's flag-parsing branches
(--help, EX_USAGE for misuse) exit before reaching docker. Tests run on any host.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = str(REPO_ROOT / "run_docker.sh")


def _run(args, env=None, timeout=5):
    """Run run_docker.sh with controlled args/env. Returns CompletedProcess."""
    full_env = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp")}
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", SCRIPT, *args],
        capture_output=True, env=full_env, timeout=timeout, text=True,
    )


def test_script_is_syntactically_valid():
    r = subprocess.run(["bash", "-n", SCRIPT], capture_output=True, text=True)
    assert r.returncode == 0, f"bash -n failed: {r.stderr}"


def test_dynamic_help_lists_flag():
    r = _run(["--help"])
    assert r.returncode == 0, f"--help should exit 0, got {r.returncode}: {r.stderr}"
    assert "--dynamic" in r.stdout, f"--dynamic not in help output: {r.stdout[:500]}"


def test_dynamic_requires_remote():
    r = _run(["--dynamic"])
    assert r.returncode == 64, (
        f"--dynamic without --remote should exit 64 (EX_USAGE), got {r.returncode}\n"
        f"stdout: {r.stdout[:200]}\nstderr: {r.stderr[:200]}"
    )
    assert "requires --remote" in r.stderr, f"missing 'requires --remote' in stderr: {r.stderr[:500]}"


def test_dynamic_help_exits_zero():
    r = _run(["--help"])
    assert r.returncode == 0
    # Ensure help text mentions the env-gated nature
    assert "MCP-only" in r.stdout or "dynamic" in r.stdout.lower()


def test_no_flag_default_mode_does_not_trigger_dynamic_check():
    # We can't fully run local mode (would invoke docker), but `--help` exits BEFORE local-mode dispatch.
    r = _run(["--help"])
    assert "requires --remote" not in r.stderr
