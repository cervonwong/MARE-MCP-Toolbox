"""Async subprocess runner for orchestrator skill scripts.

T-02-SUBPROC mitigation: uses the argv-only async exec primitive from ``asyncio``
— never a shell invocation, never string interpolation. Caller supplies argv as
a list; values must be filesystem paths or allowlisted strings (sample paths
come from ``resolve_sample``).

The test ``test_run_script_never_uses_shell_true`` enforces the policy by
grepping the function source for the forbidden keyword argument. See the threat
register row T-02-SUBPROC in the plan for details.

Scripts run in their own process session so timeout cleanup can kill child
processes spawned by shell pipelines or analysis tools, not just the parent.
"""
from __future__ import annotations
import asyncio
import os
import signal
from pathlib import Path

def _resolve_scripts_dir() -> Path:
    configured = os.environ.get("MCP_GATEWAY_SCRIPTS_DIR")
    if configured:
        return Path(configured)

    candidates = [
        Path("/agent/.codex/skills/malware-analysis-orchestrator/scripts"),
        Path("/agent/.claude/skills/malware-analysis-orchestrator/scripts"),
        Path("/agent/workspace/.claude/skills/malware-analysis-orchestrator/scripts"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


SCRIPTS = _resolve_scripts_dir()


async def run_script(
    argv: list[str],
    *,
    cwd: str = "/agent",
    timeout: float = 600.0,
    env: dict[str, str] | None = None,
) -> dict:
    """Run a script asynchronously. Returns {exit_code, stdout, stderr}.

    cwd defaults to /agent because init_status_tree.sh uses a relative STATUS_ROOT="status"
    (Pitfall 9 in RESEARCH.md). Callers who don't need that may override.
    """
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env if env is not None else os.environ.copy(),
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await proc.wait()
        raise
    return {
        "exit_code": proc.returncode if proc.returncode is not None else -1,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }
