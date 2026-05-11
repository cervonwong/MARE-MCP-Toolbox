"""Composite workflow tools (3): run_triage, run_deep_analysis, generate_report.

run_triage invokes atomic tools in the canonical order from
workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md Quick Start.
Continue-on-error semantics (per RESEARCH.md § Open Questions #3).
"""
from __future__ import annotations
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ..subprocess_runner import SCRIPTS, run_script
from .artifacts import CASE_TIMEOUT_S, FAST_TIMEOUT_S
from .case_dirs import resolve_case_dir
from .samples import resolve_sample


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def run_triage(sample: str) -> dict:
        """Full triage: init_case -> strings -> imports -> yara -> capa -> rank -> hypothesis -> mark triage_complete.

        Returns {steps: [{step, exit_code, stderr_head}], case_dir}. Continue-on-error.
        """
        path = resolve_sample(sample)
        # 1) init_case to get the case dir
        init = await run_script(
            ["bash", str(SCRIPTS / "init_status_tree.sh"), path],
            cwd="/agent",
            timeout=FAST_TIMEOUT_S,
        )
        # init_status_tree.sh prints the case dir path as the last stdout line
        case_dir = init["stdout"].strip().split("\n")[-1] if init["exit_code"] == 0 else ""
        steps = [{"step": "init_case", "exit_code": init["exit_code"], "stderr_head": init["stderr"][:500]}]

        for name, base in [
            ("collect_strings", "collect_strings.sh"),
            ("collect_imports", "collect_imports.sh"),
            ("scan_yara",       "scan_yara.sh"),
            ("scan_capa",       "scan_capa.sh"),
        ]:
            argv = ["bash", str(SCRIPTS / base), path]
            if case_dir:
                argv.append(case_dir)
            r = await run_script(argv, cwd="/agent", timeout=CASE_TIMEOUT_S)
            steps.append({"step": name, "exit_code": r["exit_code"], "stderr_head": r["stderr"][:500]})

        # Mirror per-script timeouts from artifacts.py (atomic-tool wrappers) so
        # the same script has the same timeout policy whether invoked directly or
        # through run_triage. See WR-06.
        py_steps = [
            ("rank_signals",     "rank_signals.py",     CASE_TIMEOUT_S),
            ("build_hypothesis", "build_hypothesis.py", FAST_TIMEOUT_S),
        ]
        for name, py_script, timeout in py_steps:
            if not case_dir:
                steps.append({"step": name, "exit_code": -1, "stderr_head": "no case_dir from init"})
                continue
            argv = ["python3", str(SCRIPTS / py_script), "--status-dir", case_dir]
            r = await run_script(argv, cwd="/agent", timeout=timeout)
            steps.append({"step": name, "exit_code": r["exit_code"], "stderr_head": r["stderr"][:500]})

        if case_dir:
            r = await run_script(
                ["python3", str(SCRIPTS / "update_state.py"), "--status-dir", case_dir, "--phase", "triage_complete"],
                cwd="/agent",
                timeout=FAST_TIMEOUT_S,
            )
            steps.append({"step": "update_state", "exit_code": r["exit_code"], "stderr_head": r["stderr"][:500]})

        return {"case_dir": case_dir, "steps": steps}

    @mcp.tool()
    async def run_deep_analysis(case_dir: str) -> dict:
        """Phase 2 stub: mark phase=planning_complete via update_state.py.

        Full deep-analysis is v2 scope (references deep-analysis-checklist.md).
        """
        argv = [
            "python3",
            str(SCRIPTS / "update_state.py"),
            "--status-dir",
            resolve_case_dir(case_dir),
            "--phase",
            "planning_complete",
        ]
        return await run_script(argv, cwd="/agent", timeout=FAST_TIMEOUT_S)

    @mcp.tool()
    def generate_report(case_dir: str) -> dict:
        """Read 10_reporting_draft.md from case_dir and return its content."""
        resolved_case_dir = resolve_case_dir(case_dir)
        draft = Path(resolved_case_dir) / "10_reporting_draft.md"
        if not draft.exists():
            return {"error": "reporting draft not found", "expected_path": str(draft)}
        return {"content": draft.read_text(encoding="utf-8", errors="replace"), "path": str(draft)}
