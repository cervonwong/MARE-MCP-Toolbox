"""Phase 7 SHELL-01..03 / D-01, D-02, D-09, D-10, D-28, D-29: constrained shell over MCP.

Exposes one MCP tool: `run_shell(case_dir, cmd, *, timeout=None) -> dict`.

Confinement is **posture, not isolation** -- a layered defense composed of:
  1. UID drop to a dedicated low-privilege `mare-shell` (D-01 setpriv argv)
  2. Environment built from scratch via `_build_shell_env` whitelist (D-09)
  3. cwd pinned to a `resolve_case_dir`-validated case directory (Phase 6 D-14)
  4. Hard timeout via Phase 6 `ReToolRunner` (D-04, D-08)
  5. Output cap + auto-capture to `tool-logs/` via Phase 6 chokepoint
  6. `cmd` size + NUL-byte validation (D-29)
  7. mare-shell case-dir access granted via POSIX ACL (D-03, D-05)

Mount-namespace isolation and per-call netns are deferred to v1.2.

Reference: CONTEXT.md D-01..D-10, D-28..D-32; RESEARCH.md Pattern 3 (env build-from-
scratch), Pattern 4 (setpriv argv), Pitfall 5 (env= kwarg must be passed).

The `run_shell` coroutine is defined at module level (and re-decorated by
`register(mcp)`) so unit tests (`test_run_shell.py`) can import and await it
directly without going through the FastMCP tool-manager. Mirrors the
import-then-register pattern established by `tools/re_artifacts.py`
(Plan 07-05) and `tools/re_static.py` (Plan 07-06).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..artifacts_io import ensure_mare_shell_access
from ..runner import run_tool
from .case_dirs import resolve_case_dir


# D-29: cmd-size cap. Module-level constant read once at import (Phase 6 pattern).
def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        v = int(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from e
    if v <= 0:
        raise RuntimeError(f"{name} must be > 0, got {v}")
    return v


MAX_CMD_BYTES: int = _env_int("MCP_GATEWAY_RUN_SHELL_MAX_CMD_BYTES", 32_768)


# D-09: explicit allowlist of env keys delivered to bash. The frozenset is the SOURCE
# OF TRUTH that tests assert against -- `_build_shell_env`'s output keys MUST be a
# subset of this. Adding a new key requires updating BOTH the frozenset AND
# `_build_shell_env` together so the in-module check below catches drift.
_RUN_SHELL_ALLOWED_KEYS: frozenset[str] = frozenset({
    "PATH",
    "HOME",
    "TERM",
    "NO_COLOR",
    "COLUMNS",
    "LANG",
    "LC_ALL",
    "MARE_CASE_DIR",
    "MARE_SAMPLE_PATH",
})


def _build_shell_env(case_dir, sample_path: Optional[Path] = None) -> dict[str, str]:
    """Build the run_shell child env from scratch (D-09).

    NEVER inherits from `os.environ`. The whitelist comprises:
      - PATH: minimal Debian-ish; no `~/.local/bin` etc.
      - HOME=/var/empty: mare-shell has no home; denies any `~/.foo` write
      - TERM=dumb: bash + tools see no terminal capability
      - NO_COLOR=1: force no-color output (https://no-color.org/)
      - COLUMNS=120: deterministic xxd / objdump column width
      - LANG=LC_ALL=C.UTF-8: predictable locale, UTF-8-safe
      - MARE_CASE_DIR: agents can `cd $MARE_CASE_DIR/extracted` without re-pasting
      - MARE_SAMPLE_PATH (optional): when sample resolution is available
    `PWD` is set by bash itself from `cwd=case_dir`. `SHLVL` is set by bash.

    Pitfall 5: Phase 7 MUST pass `env=_build_shell_env(...)` to `run_tool` --
    `run_tool`'s default `env=None` inherits the gateway's full `os.environ`,
    leaking the bearer token + API keys to the child shell. The defensive
    check below catches drift in this module if the dict ever grows new keys
    that aren't in the frozenset.
    """
    env: dict[str, str] = {
        "PATH":     "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME":     "/var/empty",
        "TERM":     "dumb",
        "NO_COLOR": "1",
        "COLUMNS":  "120",
        "LANG":     "C.UTF-8",
        "LC_ALL":   "C.UTF-8",
        "MARE_CASE_DIR": str(case_dir),
    }
    if sample_path is not None:
        env["MARE_SAMPLE_PATH"] = str(sample_path)
    extra = set(env) - _RUN_SHELL_ALLOWED_KEYS
    if extra:
        raise RuntimeError(
            f"_build_shell_env leaked keys not in _RUN_SHELL_ALLOWED_KEYS: {sorted(extra)} "
            f"-- update the frozenset above to allow them explicitly"
        )
    return env


def _build_setpriv_argv(cmd: str) -> list[str]:
    """D-01 / Pattern 4: defense-in-depth UID + cap + no-new-privs drop.

    `setpriv` (util-linux) gives three knobs `gosu` does not:
      - --clear-groups: wipes supplementary GIDs
      - --no-new-privs: blocks setuid escalation (matters here because the
        container runs with SYS_PTRACE + seccomp=unconfined -- widened cap surface)
      - --inh-caps=-all: drops the inheritable capability set
    Uses `bash -c <cmd>`, NEVER `bash -lc` (D-02) -- `-lc` would re-source
    /etc/profile + ~/.bash_profile, undoing the env scrub.
    """
    return [
        "setpriv",
        "--reuid=mare-shell",
        "--regid=mare-shell",
        "--clear-groups",
        "--no-new-privs",
        "--inh-caps=-all",
        "--",
        "bash",
        "-c",
        cmd,
    ]


def _validate_cmd(cmd: str) -> None:
    """D-29: empty / oversize / NUL-byte rejection. No argv-pattern detection (Pitfall 2)."""
    if not isinstance(cmd, str):
        raise ValueError(f"cmd must be a string, got {type(cmd).__name__}")
    if not cmd.strip():
        raise ValueError("cmd must not be empty or whitespace-only")
    if "\x00" in cmd:
        raise ValueError("cmd must not contain NUL byte")
    encoded_len = len(cmd.encode("utf-8"))
    if encoded_len > MAX_CMD_BYTES:
        raise ValueError(
            f"cmd exceeds MCP_GATEWAY_RUN_SHELL_MAX_CMD_BYTES={MAX_CMD_BYTES} "
            f"(got {encoded_len} bytes). For larger scripts, write_artifact a "
            f"script and `bash <script.sh>` instead."
        )


async def run_shell(
    case_dir: str,
    cmd: str,
    timeout: Optional[float] = None,
) -> dict:
    """Execute a bash one-liner inside the case directory (SHELL-01..03 / D-28).

    Confinement is **posture, not isolation**: the shell runs as a dedicated
    non-root `mare-shell` UID with a stripped environment, a cwd pinned to
    `case_dir`, a hard timeout, an output cap, and auto-capture to `tool-logs/`.
    The `MCP_GATEWAY_TOKEN`, API keys, and AWS credentials are NOT reachable
    from inside the shell. A determined attacker controlling the agent CAN
    still read the container's world-readable filesystem. Mount-namespace
    isolation and network egress controls are deferred to v1.2.

    Implementation:
      1. `cmd` validated (empty / size / NUL byte per D-29)
      2. `case_dir` resolved via `resolve_case_dir` (must be under STATUS_ROOT)
      3. `ensure_mare_shell_access(case_dir)` grants mare-shell the rwx ACL
      4. argv = setpriv --reuid=mare-shell --regid=mare-shell --clear-groups
                --no-new-privs --inh-caps=-all -- bash -c <cmd>      (D-01)
      5. env = `_build_shell_env(case_dir)` whitelist; NO `os.environ` inheritance
      6. Spawn through Phase 6 `run_tool`; head-truncated preview + full
         output captured to `case_dir/tool-logs/<ts>-run_shell-<r4>.txt`

    Returns the Phase 6 12-key result dict (D-03):
      exit_code, timed_out, duration_s,
      stdout_head, stdout_truncated, stdout_bytes_total,
      stderr_head, stderr_truncated, stderr_bytes_total,
      log_path, argv, slug.

    Raises:
      ValueError on cmd validation failure or case_dir traversal.
      RuntimeError on setfacl failure (D-06) or missing acl package.
    """
    # D-32: eager validation before any subprocess spawn.
    _validate_cmd(cmd)
    resolved_case = resolve_case_dir(case_dir)

    # D-05: amortise ACL backfill to the first call per case-dir.
    ensure_mare_shell_access(resolved_case)

    # D-01 / Pattern 4: setpriv-prefixed argv.
    argv = _build_setpriv_argv(cmd)

    # Pitfall 5 + D-09: MUST pass the built-from-scratch env, otherwise
    # run_tool inherits os.environ.copy() and leaks secrets to bash.
    return await run_tool(
        resolved_case,
        argv,
        slug="run_shell",
        timeout=timeout,
        env=_build_shell_env(resolved_case),
    )


def register(mcp: FastMCP) -> None:
    """Register the run_shell MCP tool."""
    mcp.tool()(run_shell)
