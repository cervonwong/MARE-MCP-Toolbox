"""Atomic pipeline tools (10): init_case, collect_strings, collect_imports, scan_yara,
scan_capa, rank_signals, build_hypothesis, update_state, resolve_case, get_artifact.

D-08: all shell out to workspace/.claude/skills/malware-analysis-orchestrator/scripts/.
T-02-SUBPROC: uses subprocess_runner.run_script (argv-only).
T-02-PATHTRAVERSAL: get_artifact validates artifact_name has no `/`, `\\`, `..`,
controls, or leading dot (shared predicate with uploads).
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..subprocess_runner import SCRIPTS, run_script
from ..uploads import _is_invalid_filename
from .case_dirs import resolve_case_dir
from .samples import resolve_sample

CASE_TIMEOUT_S = 600.0  # 10 minutes — generous upper bound for yara/capa on large samples
FAST_TIMEOUT_S = 60.0


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def init_case(sample: str, new: bool = False) -> dict:
        """Create status/<NNN>-<filename>/ case dir + 13 empty artifact files."""
        path = resolve_sample(sample)
        argv = ["bash", str(SCRIPTS / "init_status_tree.sh"), path]
        if new:
            argv.append("--new")
        return await run_script(argv, cwd="/agent", timeout=FAST_TIMEOUT_S)

    @mcp.tool()
    async def collect_strings(sample: str, case_dir: Optional[str] = None) -> dict:
        """Collect raw strings. Writes 00_sample_profile.md + 01_strings_raw.txt under case_dir."""
        path = resolve_sample(sample)
        argv = ["bash", str(SCRIPTS / "collect_strings.sh"), path]
        if case_dir:
            argv.append(resolve_case_dir(case_dir))
        return await run_script(argv, cwd="/agent", timeout=CASE_TIMEOUT_S)

    @mcp.tool()
    async def collect_imports(sample: str, case_dir: Optional[str] = None) -> dict:
        """Extract imports. Writes 03_imports_raw.txt under case_dir."""
        path = resolve_sample(sample)
        argv = ["bash", str(SCRIPTS / "collect_imports.sh"), path]
        if case_dir:
            argv.append(resolve_case_dir(case_dir))
        return await run_script(argv, cwd="/agent", timeout=CASE_TIMEOUT_S)

    @mcp.tool()
    async def scan_yara(sample: str, case_dir: Optional[str] = None) -> dict:
        """Run YARA. Appends matches to 00_sample_profile.md under case_dir."""
        path = resolve_sample(sample)
        argv = ["bash", str(SCRIPTS / "scan_yara.sh"), path]
        if case_dir:
            argv.append(resolve_case_dir(case_dir))
        return await run_script(argv, cwd="/agent", timeout=CASE_TIMEOUT_S)

    @mcp.tool()
    async def scan_capa(sample: str, case_dir: Optional[str] = None) -> dict:
        """Run capa. Appends tables to 00_sample_profile.md + writes tool-logs/capa.json."""
        path = resolve_sample(sample)
        argv = ["bash", str(SCRIPTS / "scan_capa.sh"), path]
        if case_dir:
            argv.append(resolve_case_dir(case_dir))
        return await run_script(argv, cwd="/agent", timeout=CASE_TIMEOUT_S)

    @mcp.tool()
    async def rank_signals(case_dir: str) -> dict:
        """Rank interesting signals. Writes 02_strings_interesting.md + 04_imports_interesting.md."""
        argv = [
            "python3",
            str(SCRIPTS / "rank_signals.py"),
            "--status-dir",
            resolve_case_dir(case_dir),
        ]
        return await run_script(argv, cwd="/agent", timeout=CASE_TIMEOUT_S)

    @mcp.tool()
    async def build_hypothesis(case_dir: str) -> dict:
        """Assemble behavior hypotheses. Writes 05_behavior_hypotheses.md."""
        argv = [
            "python3",
            str(SCRIPTS / "build_hypothesis.py"),
            "--status-dir",
            resolve_case_dir(case_dir),
        ]
        return await run_script(argv, cwd="/agent", timeout=FAST_TIMEOUT_S)

    @mcp.tool()
    async def update_state(case_dir: str, phase: str) -> dict:
        """Update INDEX.md + CURRENT_STATE.json to reflect a new phase."""
        argv = [
            "python3",
            str(SCRIPTS / "update_state.py"),
            "--status-dir",
            resolve_case_dir(case_dir),
            "--phase",
            phase,
        ]
        return await run_script(argv, cwd="/agent", timeout=FAST_TIMEOUT_S)

    @mcp.tool()
    async def resolve_case(sample: str) -> dict:
        """Return the latest status/<NNN>-<filename>/ case dir for this sample."""
        path = resolve_sample(sample)
        argv = ["bash", str(SCRIPTS / "resolve_case.sh"), path]
        result = await run_script(argv, cwd="/agent", timeout=FAST_TIMEOUT_S)
        result["case_dir"] = result["stdout"].strip() or None
        return result

    @mcp.tool()
    def get_artifact(case_dir: str, artifact_name: str) -> dict:
        """Return the raw contents of <case_dir>/<artifact_name> (no subdirs allowed).

        T-02-PATHTRAVERSAL: artifact_name must not contain '/' or '..'.
        """
        if _is_invalid_filename(artifact_name):
            raise ValueError(
                "artifact_name must be a simple filename without separators or controls"
            )
        resolved_case_dir = resolve_case_dir(case_dir)
        full = Path(resolved_case_dir) / artifact_name
        # Canonicalize and verify the resolved path stays under case_dir.
        real_case = os.path.realpath(resolved_case_dir)
        real_full = os.path.realpath(str(full))
        if not real_full.startswith(real_case + os.sep) and real_full != real_case:
            raise ValueError("resolved path escapes case_dir")
        if not Path(real_full).is_file():
            raise FileNotFoundError(f"artifact not found: {full}")
        return {
            "case_dir": case_dir,
            "artifact_name": artifact_name,
            "content": Path(real_full).read_text(encoding="utf-8", errors="replace"),
            "size": Path(real_full).stat().st_size,
        }
