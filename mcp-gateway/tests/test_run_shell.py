"""Phase 7 SHELL-01..03 + D-08, D-09, D-10, D-29, D-35, Pitfall 1.

Wave-0 RED stubs. Every test_* references mcp_gateway.tools.shell -- which does NOT
exist yet -- so failure is ImportError at execution time. Wave-1/2 implementation
flips these to GREEN by creating tools/shell.py.

Test naming mirrors RESEARCH.md "Phase Requirements -> Test Map" rows.
"""
from __future__ import annotations

import os
import pwd
from pathlib import Path

import pytest


def _make_case_dir(tmp_path: Path) -> Path:
    case = tmp_path / "case"
    case.mkdir()
    return case


# ---- Pitfall 1: mare-shell UID exists at the OS layer (Dockerfile useradd) ----
def test_mare_shell_user_exists() -> None:
    """D-01 + Claude's-Discretion UID 700 pin."""
    try:
        entry = pwd.getpwnam("mare-shell")
    except KeyError:
        pytest.fail(
            "Phase 7 D-01 requires `useradd -r -u 700 -s /usr/sbin/nologin -d /nonexistent mare-shell` "
            "in the Dockerfile. The image must be rebuilt after Wave-0 lands."
        )
    assert entry.pw_uid == 700, f"expected UID 700 pin, got {entry.pw_uid}"
    assert entry.pw_shell in ("/usr/sbin/nologin", "/sbin/nologin")


# ---- SHELL-03: docstring documents posture-not-isolation (D-28) ----
def test_run_shell_docstring_posture() -> None:
    """SHELL-03: run_shell.__doc__ contains 'posture, not isolation'."""
    from mcp_gateway.tools.shell import run_shell  # WAVE-2 module
    assert run_shell.__doc__ is not None
    assert "posture, not isolation" in run_shell.__doc__.lower() or \
           "posture not isolation" in run_shell.__doc__.lower(), (
        "D-28 requires docstring to explicitly state confinement is 'posture, not isolation'"
    )


# ---- SHELL-02: _RUN_SHELL_ALLOWED_KEYS is the complete whitelist (D-09) ----
def test_allowed_keys_frozenset() -> None:
    """D-09: _RUN_SHELL_ALLOWED_KEYS is a frozenset containing exactly the 9 keys."""
    from mcp_gateway.tools.shell import _RUN_SHELL_ALLOWED_KEYS  # WAVE-2 module
    assert isinstance(_RUN_SHELL_ALLOWED_KEYS, frozenset)
    expected = frozenset({
        "PATH", "HOME", "TERM", "NO_COLOR", "COLUMNS",
        "LANG", "LC_ALL", "MARE_CASE_DIR", "MARE_SAMPLE_PATH",
    })
    assert _RUN_SHELL_ALLOWED_KEYS == expected, (
        f"D-09 whitelist mismatch: got {_RUN_SHELL_ALLOWED_KEYS}, expected {expected}"
    )


# ---- SHELL-01: cwd pinned to case_dir ----
async def test_run_shell_pwd_equals_case_dir(tmp_status_dir, tmp_path: Path) -> None:
    """SHELL-01 (cwd pinned)."""
    from mcp_gateway.tools.shell import run_shell  # WAVE-2 module
    case = tmp_status_dir / "001-fixture"
    case.mkdir()
    result = await run_shell(str(case), "pwd")
    assert result["exit_code"] == 0
    assert result["stdout_head"].strip() == str(case.resolve())


# ---- SHELL-01: hard timeout ----
async def test_run_shell_timeout_kills_pgroup(tmp_status_dir, tmp_path: Path) -> None:
    """SHELL-01 (timeout)."""
    from mcp_gateway.tools.shell import run_shell
    case = tmp_status_dir / "002-fixture"
    case.mkdir()
    result = await run_shell(str(case), "sleep 60", timeout=0.5)
    assert result["timed_out"] is True


# ---- SHELL-01: stdout cap ----
async def test_run_shell_stdout_cap(tmp_status_dir) -> None:
    """SHELL-01 (output cap)."""
    from mcp_gateway.tools.shell import run_shell
    case = tmp_status_dir / "003-fixture"
    case.mkdir()
    result = await run_shell(str(case), "head -c 1048576 /dev/zero")
    assert result["stdout_truncated"] is True
    assert result["stdout_bytes_total"] >= 1048576


# ---- SHELL-01: auto-capture to tool-logs/ ----
async def test_run_shell_log_capture(tmp_status_dir) -> None:
    """SHELL-01 (auto-capture)."""
    from mcp_gateway.tools.shell import run_shell
    case = tmp_status_dir / "004-fixture"
    case.mkdir()
    result = await run_shell(str(case), "echo HelloMARE")
    log_path = case / result["log_path"]
    assert log_path.is_file()
    assert "HelloMARE" in log_path.read_text(encoding="utf-8", errors="replace")


# ---- SHELL-02: drops to mare-shell UID 700 (D-08) ----
async def test_run_shell_drops_to_mare_shell_uid(tmp_status_dir) -> None:
    """SHELL-02 (mare-shell UID, D-08)."""
    from mcp_gateway.tools.shell import run_shell
    case = tmp_status_dir / "005-fixture"
    case.mkdir()
    result = await run_shell(str(case), "id -u")
    assert result["exit_code"] == 0, f"stderr={result['stderr_head']!r}"
    assert result["stdout_head"].strip() == "700"


# ---- SHELL-02: token file unreachable (D-08) ----
async def test_run_shell_cannot_read_token(tmp_status_dir) -> None:
    """SHELL-02 (token file inaccessible, D-08)."""
    from mcp_gateway.tools.shell import run_shell
    case = tmp_status_dir / "006-fixture"
    case.mkdir()
    result = await run_shell(str(case), "cat /agent/.mcp-gateway-token 2>&1 >/dev/null; echo $?")
    # Either token doesn't exist or is unreadable to mare-shell; both yield non-zero exit from `cat`.
    # The echoed status should NOT be "0".
    assert result["stdout_head"].strip() != "0"


# ---- SHELL-02 (D-08, D-10): env scrub of TOKEN / API_KEY / AWS_ / ANTHROPIC_ / OPENAI_ ----
async def test_run_shell_env_no_secrets(tmp_status_dir, monkeypatch) -> None:
    """SHELL-02 + D-09 + D-10: parent-env secrets do not reach the shell."""
    from mcp_gateway.tools.shell import run_shell
    case = tmp_status_dir / "007-fixture"
    case.mkdir()
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "should-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-shouldnotleak")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIASHOULDNOTLEAK")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("BN_LICENSE_TEXT", "binja-license")
    monkeypatch.setenv("IDA_USER", "ida-user")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_shouldnotleak")
    result = await run_shell(str(case), "env")
    leak = result["stdout_head"]
    for forbidden in (
        "MCP_GATEWAY_TOKEN", "ANTHROPIC_API_KEY", "AWS_ACCESS_KEY_ID",
        "OPENAI_API_KEY", "BN_LICENSE_TEXT", "IDA_USER", "GITHUB_TOKEN",
        "should-not-leak", "sk-shouldnotleak", "AKIASHOULDNOTLEAK",
    ):
        assert forbidden not in leak, f"D-10 violation: {forbidden!r} leaked to shell env"


# ---- D-09: MARE_CASE_DIR is set in the shell env ----
async def test_run_shell_mare_case_dir_env(tmp_status_dir) -> None:
    """D-09: MARE_CASE_DIR points at the resolved case_dir from within bash."""
    from mcp_gateway.tools.shell import run_shell
    case = tmp_status_dir / "008-fixture"
    case.mkdir()
    result = await run_shell(str(case), "echo \"$MARE_CASE_DIR\"")
    assert result["stdout_head"].strip() == str(case.resolve())


# ---- D-29: cmd validation: empty ----
async def test_run_shell_rejects_empty_cmd(tmp_status_dir) -> None:
    """D-29: empty / whitespace-only cmd raises ValueError."""
    from mcp_gateway.tools.shell import run_shell
    case = tmp_status_dir / "009-fixture"
    case.mkdir()
    with pytest.raises(ValueError):
        await run_shell(str(case), "")
    with pytest.raises(ValueError):
        await run_shell(str(case), "   \t\n")


# ---- D-29: cmd validation: too long ----
async def test_run_shell_rejects_long_cmd(tmp_status_dir) -> None:
    """D-29: cmd exceeding MCP_GATEWAY_RUN_SHELL_MAX_CMD_BYTES (default 32768) raises ValueError."""
    from mcp_gateway.tools.shell import run_shell
    case = tmp_status_dir / "010-fixture"
    case.mkdir()
    with pytest.raises(ValueError):
        await run_shell(str(case), "x" * 32769)


# ---- D-29: cmd validation: NUL byte ----
async def test_run_shell_rejects_nul_byte(tmp_status_dir) -> None:
    """D-29: NUL byte in cmd raises ValueError."""
    from mcp_gateway.tools.shell import run_shell
    case = tmp_status_dir / "011-fixture"
    case.mkdir()
    with pytest.raises(ValueError):
        await run_shell(str(case), "echo\x00x")


# ---- D-35: 100 MB urandom rerun at the run_shell layer (slow) ----
@pytest.mark.slow
async def test_run_shell_100mb_urandom(tmp_status_dir) -> None:
    """D-35: chokepoint integrity preserved through the full run_shell stack."""
    from mcp_gateway.tools.shell import run_shell
    case = tmp_status_dir / "012-fixture"
    case.mkdir()
    result = await run_shell(str(case), "head -c 104857600 /dev/urandom")
    # Must exit cleanly and have stdout_truncated=True (head-cap fired)
    assert result["exit_code"] == 0
    assert result["stdout_truncated"] is True
    assert result["stdout_bytes_total"] >= 100 * 1024 * 1024
