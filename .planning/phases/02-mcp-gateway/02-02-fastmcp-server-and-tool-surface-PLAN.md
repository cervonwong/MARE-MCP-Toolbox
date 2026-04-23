---
phase: 02-mcp-gateway
plan: 02
type: execute
wave: 2
depends_on:
  - 02-01
files_modified:
  - mcp-gateway/src/mcp_gateway/app.py
  - mcp-gateway/src/mcp_gateway/subprocess_runner.py
  - mcp-gateway/src/mcp_gateway/tools/__init__.py
  - mcp-gateway/src/mcp_gateway/tools/samples.py
  - mcp-gateway/src/mcp_gateway/tools/cases.py
  - mcp-gateway/src/mcp_gateway/tools/artifacts.py
  - mcp-gateway/src/mcp_gateway/tools/workflows.py
  - mcp-gateway/src/mcp_gateway/tools/disasm.py
  - mcp-gateway/tests/test_server_init.py
  - mcp-gateway/tests/test_tool_list.py
  - mcp-gateway/tests/test_artifact_tools.py
  - mcp-gateway/tests/test_workflow_tools.py
  - mcp-gateway/tests/test_sample_resolution.py
autonomous: true
requirements:
  - GW-01
  - GW-02
tags:
  - mcp
  - fastmcp
  - tools
  - orchestrator
  - python

must_haves:
  truths:
    - "FastMCP Streamable HTTP `initialize` request succeeds via ASGI TestClient with valid bearer"
    - "`tools/list` returns exactly 21 curated tools (3 composite + 10 atomic + 3 disasm + 5 case/sample mgmt)"
    - "Count of exposed tools is between 15 and 25 (GW-02)"
    - "Every orchestrator script in `workspace/.claude/skills/malware-analysis-orchestrator/scripts/` has a matching atomic tool"
    - "Disassembler tools (`decompile`, `list_functions`, `get_xrefs`) are registered even though backend wiring is stubbed until Plan 03"
    - "`resolve_sample(<sha256>)` returns `/agent/uploads/<sha256>/*` first match"
    - "`resolve_sample(<container-path>)` returns the path unchanged IF it is under `/agent/uploads/`, `/agent/examples/`, or `/agent/status/`"
    - "`resolve_sample('../etc/passwd')` raises ValueError (T-02-PATHTRAVERSAL)"
    - "`resolve_sample('/etc/passwd')` raises ValueError (not under allowed prefixes)"
    - "`run_script(argv, cwd='/agent')` uses `asyncio.create_subprocess_exec(*argv)` with no `shell=True` (T-02-SUBPROC)"
    - "`collect_strings` tool shells out to `collect_strings.sh` with the sample path"
    - "`run_triage` composite invokes atomic tools in canonical order"
    - "GET /healthz returns 200 with `{\"ok\": true}` without auth"
  artifacts:
    - path: "mcp-gateway/src/mcp_gateway/app.py"
      provides: "build_app() Starlette factory; FastMCP + /upload route stub + /healthz + auth + Origin middleware"
      exports: ["build_app", "get_mcp"]
    - path: "mcp-gateway/src/mcp_gateway/tools/__init__.py"
      provides: "register_all_tools(mcp) — registers 21 tools"
      exports: ["register_all_tools"]
    - path: "mcp-gateway/src/mcp_gateway/tools/samples.py"
      provides: "resolve_sample() with path-traversal protection"
      exports: ["resolve_sample", "ALLOWED_PREFIXES"]
    - path: "mcp-gateway/src/mcp_gateway/subprocess_runner.py"
      provides: "async run_script() using create_subprocess_exec"
      exports: ["run_script", "SCRIPTS"]
  key_links:
    - from: "mcp-gateway/src/mcp_gateway/app.py::build_app"
      to: "mcp.session_manager.run()"
      via: "Starlette lifespan context manager"
      pattern: "session_manager\\.run"
    - from: "mcp-gateway/src/mcp_gateway/tools/artifacts.py::collect_strings"
      to: "workspace/.claude/skills/malware-analysis-orchestrator/scripts/collect_strings.sh"
      via: "asyncio.create_subprocess_exec with cwd=/agent"
      pattern: "create_subprocess_exec"
    - from: "mcp-gateway/src/mcp_gateway/tools/samples.py::resolve_sample"
      to: "os.path.realpath + prefix check"
      via: "canonicalize then allowlist"
      pattern: "realpath.*startswith"
---

<objective>
Assemble the Starlette+FastMCP application: `build_app()` factory that mounts FastMCP's Streamable HTTP ASGI app at `/mcp`, adds `/healthz`, wires `BearerAuthMiddleware` + `OriginMiddleware`, and registers the 21-tool curated surface. Implement the non-disassembler tools end-to-end (composite workflows + 10 atomic orchestrator shell-outs + 5 case/sample management + 3 disassembler tools as backend-stubbed placeholders).

Purpose: Fulfills GW-01 (FastMCP Streamable HTTP with Auth) and GW-02 (15-25 curated tools mapping to the 13-artifact pipeline). Plan 03 fills in the actual backend routing for the 3 disassembler tools; Plan 04 fills in the `/upload` route handler.

Output: A running gateway that answers `initialize` and `tools/list` over Streamable HTTP with the full 21-tool set; atomic orchestrator tools execute real scripts; disassembler tools return a structured "backend not yet wired" error (replaced in Plan 03).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/02-mcp-gateway/02-CONTEXT.md
@.planning/phases/02-mcp-gateway/02-RESEARCH.md
@.planning/phases/02-mcp-gateway/02-VALIDATION.md
@.planning/phases/02-mcp-gateway/02-01-package-scaffold-and-auth-PLAN.md
@workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md
@workspace/.claude/skills/malware-analysis-orchestrator/scripts/

<interfaces>
<!-- From Plan 01 (must be importable when Plan 02 executes) -->
```python
from mcp_gateway.auth import load_or_generate_token, BearerAuthMiddleware, OriginMiddleware
from mcp_gateway.backend.detect import detect_backend  # returns "ida"|"bn"|"ghidra" or raises
from mcp_gateway import session_state  # exposes PINNED_BACKEND, ACTIVE_CASE
```

<!-- From Plan 03 (NOT yet available — this plan stubs the disasm handlers) -->
```python
# session_state.PINNED_BACKEND will be a PinnedBackend with async `call(tool, args)` method.
# In Plan 02, disasm tools check `if session_state.PINNED_BACKEND is None: return {"error": "backend not yet wired"}`.
```

<!-- Canonical orchestrator script signatures — read verbatim from workspace/.claude/skills/malware-analysis-orchestrator/scripts/ -->
```
init_status_tree.sh <sample_path> [--new]           → writes status/<NNN>-<filename>/ with 13 empty artifacts
collect_strings.sh <sample_path> [case_dir]         → writes 00_sample_profile.md, 01_strings_raw.txt
collect_imports.sh <sample_path> [case_dir]         → writes 03_imports_raw.txt
scan_yara.sh <sample_path> [case_dir]               → appends to 00_sample_profile.md
scan_capa.sh <sample_path> [case_dir]               → appends to 00_sample_profile.md, writes tool-logs/capa.json
rank_signals.py --status-dir <case_dir>             → writes 02_strings_interesting.md, 04_imports_interesting.md
build_hypothesis.py --status-dir <case_dir>         → writes 05_behavior_hypotheses.md
update_state.py --status-dir <case_dir> --phase <x> → writes INDEX.md, CURRENT_STATE.json
resolve_case.sh <sample>                            → stdout: latest status/<NNN>-<filename>/ path
```

<!-- Full 21-tool inventory (D-01..D-04) -->
```
Composite (3):      run_triage, run_deep_analysis, generate_report
Atomic (10):        init_case, collect_strings, collect_imports, scan_yara, scan_capa,
                    rank_signals, build_hypothesis, update_state, resolve_case, get_artifact
Disassembler (3):   decompile, list_functions, get_xrefs
Case/sample (5):    list_cases, set_active_case, get_active_case, list_uploads, get_sample_info
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Sample resolver + async subprocess runner (T-02-PATHTRAVERSAL + T-02-SUBPROC)</name>
  <files>
    mcp-gateway/src/mcp_gateway/tools/__init__.py,
    mcp-gateway/src/mcp_gateway/tools/samples.py,
    mcp-gateway/src/mcp_gateway/subprocess_runner.py,
    mcp-gateway/tests/test_sample_resolution.py
  </files>
  <read_first>
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Pattern 5 Async Subprocess; § Common Pitfalls — Pitfall 9 cwd; § Security Domain — path traversal mitigations)
    - .planning/phases/02-mcp-gateway/02-CONTEXT.md (D-15 sample resolution modes; D-13 upload dir layout)
    - .planning/phases/02-mcp-gateway/02-01-package-scaffold-and-auth-PLAN.md (confirm Plan 01 landed; see files_modified)
    - workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh (line 33 STATUS_ROOT="status" — cwd-relative)
  </read_first>
  <behavior>
    - `resolve_sample("<sha256-hex-64>")` returns `/agent/uploads/<sha256>/<first-filename>` when such a dir exists with 1 file
    - `resolve_sample("<sha256>")` raises FileNotFoundError when uploads dir missing
    - `resolve_sample("/agent/examples/foo.bin")` returns `/agent/examples/foo.bin` if the file exists
    - `resolve_sample("/agent/uploads/<sha>/a.bin")` returns path unchanged (under allowed prefix)
    - `resolve_sample("../etc/passwd")` raises ValueError (T-02-PATHTRAVERSAL)
    - `resolve_sample("/etc/passwd")` raises ValueError (path outside allowed prefixes)
    - `resolve_sample("/agent/../etc/passwd")` raises ValueError after canonicalization
    - `resolve_sample("/agent/uploads/..")` raises ValueError (canonicalized to `/agent`)
    - `run_script(["/bin/echo", "hello"], cwd="/tmp")` returns `{"exit_code": 0, "stdout": "hello\n", "stderr": ""}`
    - `run_script(["/bin/false"], cwd="/tmp")` returns `{"exit_code": 1, ...}` (does NOT raise)
    - `run_script(["/bin/sleep", "60"], cwd="/tmp", timeout=0.1)` raises `asyncio.TimeoutError` and kills the process
    - `run_script` refuses `shell=True` — source does not contain `shell=True` anywhere
  </behavior>
  <action>
Create `mcp-gateway/src/mcp_gateway/tools/__init__.py`:

```python
"""Tool registration entry point. register_all_tools(mcp) registers all 21 tools."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_all_tools(mcp: FastMCP) -> None:
    """Register the curated 21-tool surface on a FastMCP instance.

    Ordering mirrors D-01..D-04 (composite + atomic + disasm + case/sample mgmt).
    """
    # Imports inside the function avoid import-cycle risk during FastMCP module
    # discovery and keep the function as the single registration seam.
    from . import cases, artifacts, workflows, disasm  # noqa: F401
    cases.register(mcp)
    artifacts.register(mcp)
    workflows.register(mcp)
    disasm.register(mcp)
```

Create `mcp-gateway/src/mcp_gateway/tools/samples.py`:

```python
"""Sample resolver: sha256-id or container-local path → absolute path.

T-02-PATHTRAVERSAL mitigation: canonicalize then allowlist-check against known prefixes.
"""
from __future__ import annotations
import os
import re
from pathlib import Path

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

UPLOADS_ROOT = Path(os.environ.get("MCP_GATEWAY_UPLOAD_DIR", "/agent/uploads"))
EXAMPLES_ROOT = Path(os.environ.get("MCP_GATEWAY_EXAMPLES_DIR", "/agent/examples"))
STATUS_ROOT = Path(os.environ.get("MCP_GATEWAY_STATUS_DIR", "/agent/status"))

ALLOWED_PREFIXES = (UPLOADS_ROOT, EXAMPLES_ROOT, STATUS_ROOT)


def _resolve_allowed(path: Path) -> str:
    """Canonicalize + verify the resolved path is under one of ALLOWED_PREFIXES."""
    real = Path(os.path.realpath(path))
    for prefix in ALLOWED_PREFIXES:
        prefix_real = Path(os.path.realpath(prefix))
        try:
            real.relative_to(prefix_real)
            return str(real)
        except ValueError:
            continue
    raise ValueError(
        f"path {path!r} not under allowed prefixes {[str(p) for p in ALLOWED_PREFIXES]}"
    )


def resolve_sample(sample: str) -> str:
    """Resolve a sample identifier (sha256 OR container path) to an absolute filesystem path.

    D-15: "sample" may be a sha256 hex string (previous upload) or an already-absolute
    container path. In both cases the final resolved path must live under one of
    ALLOWED_PREFIXES (uploads, examples, status) — path traversal is rejected (T-02-PATHTRAVERSAL).
    """
    if not isinstance(sample, str) or not sample:
        raise ValueError("sample must be a non-empty string")

    if SHA256_RE.match(sample):
        sample_dir = UPLOADS_ROOT / sample
        if not sample_dir.is_dir():
            raise FileNotFoundError(f"no upload for sha256 {sample}")
        # Pick the first non-hidden file (Phase 2: one file per hash per D-13).
        candidates = sorted(p for p in sample_dir.iterdir() if p.is_file() and not p.name.startswith("."))
        if not candidates:
            raise FileNotFoundError(f"upload dir {sample_dir} is empty")
        return _resolve_allowed(candidates[0])

    # Treat as path. Reject obvious traversal before canonicalizing (defense in depth).
    if ".." in Path(sample).parts:
        raise ValueError(f"path traversal rejected: {sample!r}")
    return _resolve_allowed(Path(sample))
```

Create `mcp-gateway/src/mcp_gateway/subprocess_runner.py`:

```python
"""Async subprocess runner for orchestrator skill scripts.

T-02-SUBPROC mitigation: uses `asyncio.create_subprocess_exec(*argv)` — never shell=True,
never string interpolation. Caller supplies argv as a list; values must be filesystem
paths or allowlisted strings (sample paths come from `resolve_sample`).
"""
from __future__ import annotations
import asyncio
import os
from pathlib import Path

SCRIPTS = Path(
    os.environ.get(
        "MCP_GATEWAY_SCRIPTS_DIR",
        "/agent/workspace/.claude/skills/malware-analysis-orchestrator/scripts",
    )
)


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
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return {
        "exit_code": proc.returncode if proc.returncode is not None else -1,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }
```

Create `mcp-gateway/tests/test_sample_resolution.py`:

```python
"""Tests for resolve_sample() path-traversal protection + subprocess runner."""
from __future__ import annotations
import asyncio
from pathlib import Path

import pytest

from mcp_gateway.tools import samples as samples_mod
from mcp_gateway.subprocess_runner import run_script


@pytest.fixture
def mocked_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    uploads = tmp_path / "uploads"
    examples = tmp_path / "examples"
    status = tmp_path / "status"
    for d in (uploads, examples, status):
        d.mkdir()
    monkeypatch.setattr(samples_mod, "UPLOADS_ROOT", uploads)
    monkeypatch.setattr(samples_mod, "EXAMPLES_ROOT", examples)
    monkeypatch.setattr(samples_mod, "STATUS_ROOT", status)
    monkeypatch.setattr(samples_mod, "ALLOWED_PREFIXES", (uploads, examples, status))
    return {"uploads": uploads, "examples": examples, "status": status}


# -------- resolve_sample --------

def test_resolve_sha256(mocked_dirs):
    sha = "a" * 64
    sample_dir = mocked_dirs["uploads"] / sha
    sample_dir.mkdir()
    f = sample_dir / "suspect.bin"
    f.write_bytes(b"\x00")
    assert samples_mod.resolve_sample(sha) == str(f.resolve())


def test_resolve_sha256_not_found(mocked_dirs):
    sha = "b" * 64
    with pytest.raises(FileNotFoundError):
        samples_mod.resolve_sample(sha)


def test_resolve_path_under_uploads(mocked_dirs):
    f = mocked_dirs["uploads"] / "raw.bin"
    f.write_bytes(b"\x00")
    assert samples_mod.resolve_sample(str(f)) == str(f.resolve())


def test_resolve_path_under_examples(mocked_dirs):
    f = mocked_dirs["examples"] / "good.bin"
    f.write_bytes(b"\x00")
    assert samples_mod.resolve_sample(str(f)) == str(f.resolve())


def test_resolve_traversal_rejected(mocked_dirs):
    with pytest.raises(ValueError, match="traversal"):
        samples_mod.resolve_sample("../etc/passwd")


def test_resolve_outside_allowed_rejected(mocked_dirs):
    with pytest.raises(ValueError, match="not under allowed prefixes"):
        samples_mod.resolve_sample("/etc/passwd")


def test_resolve_traversal_via_allowed_prefix_rejected(mocked_dirs):
    # /<uploads>/../etc — canonicalizes OUT of allowed tree
    sneaky = str(mocked_dirs["uploads"] / ".." / "etc")
    with pytest.raises(ValueError):
        samples_mod.resolve_sample(sneaky)


def test_resolve_empty_string(mocked_dirs):
    with pytest.raises(ValueError):
        samples_mod.resolve_sample("")


# -------- run_script --------

async def test_run_script_echo():
    # pytest-asyncio auto mode (asyncio_mode="auto" in pyproject.toml) picks up async tests.
    # Avoids deprecated asyncio.get_event_loop().run_until_complete() which breaks on Python 3.12+.
    result = await run_script(["/bin/echo", "hello"], cwd="/tmp")
    assert result["exit_code"] == 0
    assert "hello" in result["stdout"]


async def test_run_script_nonzero_exit_does_not_raise():
    result = await run_script(["/bin/false"], cwd="/tmp")
    assert result["exit_code"] == 1


async def test_run_script_timeout():
    with pytest.raises(asyncio.TimeoutError):
        await run_script(["/bin/sleep", "60"], cwd="/tmp", timeout=0.2)


def test_run_script_never_uses_shell_true():
    import inspect
    src = inspect.getsource(run_script)
    assert "shell=True" not in src, "T-02-SUBPROC: run_script must not use shell=True"
```
  </action>
  <verify>
    <automated>pytest mcp-gateway/tests/test_sample_resolution.py -x --no-header -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest mcp-gateway/tests/test_sample_resolution.py -x --no-header -q` exits 0
    - `grep -c 'shell=True' mcp-gateway/src/mcp_gateway/subprocess_runner.py` == 0 (T-02-SUBPROC)
    - `grep -c 'create_subprocess_exec' mcp-gateway/src/mcp_gateway/subprocess_runner.py` == 1
    - `grep -c 'os.path.realpath' mcp-gateway/src/mcp_gateway/tools/samples.py` >= 1
    - `grep -q 'ALLOWED_PREFIXES' mcp-gateway/src/mcp_gateway/tools/samples.py`
    - `grep -q 'cwd.*=.*"/agent"' mcp-gateway/src/mcp_gateway/subprocess_runner.py` (default cwd)
    - `python -c "from mcp_gateway.tools.samples import resolve_sample, ALLOWED_PREFIXES; print(len(ALLOWED_PREFIXES))"` prints 3
    - `python -c "import asyncio; from mcp_gateway.subprocess_runner import run_script; print(asyncio.run(run_script(['/bin/true'], cwd='/tmp'))['exit_code'])"` prints 0
  </acceptance_criteria>
  <done>resolve_sample() rejects all traversal forms; run_script() runs and times out cleanly; T-02-PATHTRAVERSAL and T-02-SUBPROC mitigated; 12 tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Tool modules — cases, artifacts, workflows, disasm (21 tools total)</name>
  <files>
    mcp-gateway/src/mcp_gateway/tools/cases.py,
    mcp-gateway/src/mcp_gateway/tools/artifacts.py,
    mcp-gateway/src/mcp_gateway/tools/workflows.py,
    mcp-gateway/src/mcp_gateway/tools/disasm.py,
    mcp-gateway/tests/test_artifact_tools.py,
    mcp-gateway/tests/test_workflow_tools.py
  </files>
  <read_first>
    - mcp-gateway/src/mcp_gateway/tools/samples.py (Task 1 — use resolve_sample)
    - mcp-gateway/src/mcp_gateway/subprocess_runner.py (Task 1 — use run_script, SCRIPTS)
    - workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh (exact args)
    - workspace/.claude/skills/malware-analysis-orchestrator/scripts/collect_strings.sh
    - workspace/.claude/skills/malware-analysis-orchestrator/scripts/collect_imports.sh
    - workspace/.claude/skills/malware-analysis-orchestrator/scripts/rank_signals.py
    - workspace/.claude/skills/malware-analysis-orchestrator/scripts/build_hypothesis.py
    - workspace/.claude/skills/malware-analysis-orchestrator/scripts/update_state.py
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Tool Surface Design — full 21-tool table; § Pattern 5)
    - .planning/phases/02-mcp-gateway/02-CONTEXT.md (D-01..D-04 tool names; D-08 reuse scripts)
  </read_first>
  <behavior>
    - `cases.py::list_cases()` scans `STATUS_ROOT` for dirs matching `[0-9][0-9][0-9]-*` and returns list of {name, path, mtime}
    - `cases.py::set_active_case(case)` sets `session_state.ACTIVE_CASE` and returns it
    - `cases.py::get_active_case()` returns `session_state.ACTIVE_CASE`
    - `cases.py::list_uploads()` enumerates `UPLOADS_ROOT/<sha256>/*` entries
    - `cases.py::get_sample_info(sample)` returns `{sha256, size, path}` (uses `resolve_sample` + stat + sha256)
    - `artifacts.py::init_case(sample, new=False)` → `run_script(["bash", str(SCRIPTS / "init_status_tree.sh"), path, ...], cwd="/agent")`
    - `artifacts.py::collect_strings(sample, case_dir=None)` → shells out to collect_strings.sh
    - `artifacts.py::collect_imports`, `scan_yara`, `scan_capa` follow the same shell-out pattern
    - `artifacts.py::rank_signals(case_dir)` → `["python3", str(SCRIPTS / "rank_signals.py"), "--status-dir", case_dir]`
    - `artifacts.py::build_hypothesis(case_dir)` → `["python3", str(SCRIPTS / "build_hypothesis.py"), "--status-dir", case_dir]`
    - `artifacts.py::update_state(case_dir, phase)` → `["python3", str(SCRIPTS / "update_state.py"), "--status-dir", case_dir, "--phase", phase]`
    - `artifacts.py::resolve_case(sample)` → shells out to resolve_case.sh, returns stdout-trimmed case path
    - `artifacts.py::get_artifact(case_dir, artifact_name)` reads `<case_dir>/<artifact_name>` with path-traversal check on name
    - `workflows.py::run_triage(sample)` calls atomic tools in order: init_case → collect_strings → collect_imports → scan_yara → scan_capa → rank_signals → build_hypothesis → update_state(phase="triage_complete"); continues on individual step failures; returns `[{step, exit_code, stderr}]` list
    - `workflows.py::run_deep_analysis(case_dir)` Phase 2 stub: updates state to phase "planning_complete"
    - `workflows.py::generate_report(case_dir)` reads `<case_dir>/10_reporting_draft.md` and returns contents (404 if missing)
    - `disasm.py::decompile(function, sample=None)` returns MCP error `{"error": "backend not yet wired", "plan": "Plan 03"}` when `session_state.PINNED_BACKEND is None`; when set, delegates via tool_map (Plan 03 wires this)
    - `disasm.py::list_functions(sample=None)` same shape
    - `disasm.py::get_xrefs(function, sample=None)` same shape
    - Each tool module exposes a `register(mcp: FastMCP)` function that decorates handlers via `@mcp.tool()`
  </behavior>
  <action>
Create `mcp-gateway/src/mcp_gateway/tools/cases.py`:

```python
"""Case management + upload browsing tools (5 tools: list_cases, set_active_case,
get_active_case, list_uploads, get_sample_info).
"""
from __future__ import annotations
import hashlib
import os
import re
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .. import session_state
from .samples import UPLOADS_ROOT, STATUS_ROOT, resolve_sample

CASE_NAME_RE = re.compile(r"^\d{3}-.+")


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_cases() -> list[dict]:
        """Enumerate analysis cases under /agent/status/. Each case dir name is NNN-<filename>."""
        if not STATUS_ROOT.exists():
            return []
        items: list[dict] = []
        for p in sorted(STATUS_ROOT.iterdir()):
            if p.is_dir() and CASE_NAME_RE.match(p.name):
                items.append({
                    "name": p.name,
                    "path": str(p),
                    "mtime": p.stat().st_mtime,
                })
        return items

    @mcp.tool()
    def set_active_case(case: str) -> dict:
        """Set the per-session active case (directory name like '001-foo.bin' or absolute path)."""
        session_state.ACTIVE_CASE = case
        return {"active_case": case}

    @mcp.tool()
    def get_active_case() -> dict:
        """Return the currently-active case for this session (or null)."""
        return {"active_case": session_state.ACTIVE_CASE}

    @mcp.tool()
    def list_uploads() -> list[dict]:
        """Enumerate /agent/uploads/<sha256>/*.bin entries."""
        if not UPLOADS_ROOT.exists():
            return []
        items: list[dict] = []
        for sha_dir in sorted(UPLOADS_ROOT.iterdir()):
            if sha_dir.is_dir() and len(sha_dir.name) == 64:
                for f in sha_dir.iterdir():
                    if f.is_file() and not f.name.startswith("."):
                        items.append({
                            "sha256": sha_dir.name,
                            "filename": f.name,
                            "path": str(f),
                            "size": f.stat().st_size,
                        })
        return items

    @mcp.tool()
    def get_sample_info(sample: str) -> dict:
        """Return {sha256, size, path} for a sample (sha256 id or container path)."""
        path = resolve_sample(sample)
        p = Path(path)
        sha = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return {
            "sha256": sha.hexdigest(),
            "size": p.stat().st_size,
            "path": str(p),
        }
```

Create `mcp-gateway/src/mcp_gateway/tools/artifacts.py`:

```python
"""Atomic pipeline tools (10): init_case, collect_strings, collect_imports, scan_yara,
scan_capa, rank_signals, build_hypothesis, update_state, resolve_case, get_artifact.

D-08: all shell out to workspace/.claude/skills/malware-analysis-orchestrator/scripts/.
T-02-SUBPROC: uses subprocess_runner.run_script (argv-only).
T-02-PATHTRAVERSAL: get_artifact validates artifact_name has no `/` or `..`.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..subprocess_runner import SCRIPTS, run_script
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
            argv.append(case_dir)
        return await run_script(argv, cwd="/agent", timeout=CASE_TIMEOUT_S)

    @mcp.tool()
    async def collect_imports(sample: str, case_dir: Optional[str] = None) -> dict:
        """Extract imports. Writes 03_imports_raw.txt under case_dir."""
        path = resolve_sample(sample)
        argv = ["bash", str(SCRIPTS / "collect_imports.sh"), path]
        if case_dir:
            argv.append(case_dir)
        return await run_script(argv, cwd="/agent", timeout=CASE_TIMEOUT_S)

    @mcp.tool()
    async def scan_yara(sample: str, case_dir: Optional[str] = None) -> dict:
        """Run YARA. Appends matches to 00_sample_profile.md under case_dir."""
        path = resolve_sample(sample)
        argv = ["bash", str(SCRIPTS / "scan_yara.sh"), path]
        if case_dir:
            argv.append(case_dir)
        return await run_script(argv, cwd="/agent", timeout=CASE_TIMEOUT_S)

    @mcp.tool()
    async def scan_capa(sample: str, case_dir: Optional[str] = None) -> dict:
        """Run capa. Appends tables to 00_sample_profile.md + writes tool-logs/capa.json."""
        path = resolve_sample(sample)
        argv = ["bash", str(SCRIPTS / "scan_capa.sh"), path]
        if case_dir:
            argv.append(case_dir)
        return await run_script(argv, cwd="/agent", timeout=CASE_TIMEOUT_S)

    @mcp.tool()
    async def rank_signals(case_dir: str) -> dict:
        """Rank interesting signals. Writes 02_strings_interesting.md + 04_imports_interesting.md."""
        argv = ["python3", str(SCRIPTS / "rank_signals.py"), "--status-dir", case_dir]
        return await run_script(argv, cwd="/agent", timeout=CASE_TIMEOUT_S)

    @mcp.tool()
    async def build_hypothesis(case_dir: str) -> dict:
        """Assemble behavior hypotheses. Writes 05_behavior_hypotheses.md."""
        argv = ["python3", str(SCRIPTS / "build_hypothesis.py"), "--status-dir", case_dir]
        return await run_script(argv, cwd="/agent", timeout=FAST_TIMEOUT_S)

    @mcp.tool()
    async def update_state(case_dir: str, phase: str) -> dict:
        """Update INDEX.md + CURRENT_STATE.json to reflect a new phase."""
        argv = ["python3", str(SCRIPTS / "update_state.py"), "--status-dir", case_dir, "--phase", phase]
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
        if "/" in artifact_name or ".." in artifact_name or artifact_name.startswith("."):
            raise ValueError("artifact_name must be a simple filename without separators")
        full = Path(case_dir) / artifact_name
        # Canonicalize and verify the resolved path stays under case_dir.
        import os as _os
        real_case = _os.path.realpath(case_dir)
        real_full = _os.path.realpath(str(full))
        if not real_full.startswith(real_case + _os.sep) and real_full != real_case:
            raise ValueError("resolved path escapes case_dir")
        if not Path(real_full).is_file():
            raise FileNotFoundError(f"artifact not found: {full}")
        return {
            "case_dir": case_dir,
            "artifact_name": artifact_name,
            "content": Path(real_full).read_text(encoding="utf-8", errors="replace"),
            "size": Path(real_full).stat().st_size,
        }
```

Create `mcp-gateway/src/mcp_gateway/tools/workflows.py`:

```python
"""Composite workflow tools (3): run_triage, run_deep_analysis, generate_report.

run_triage invokes atomic tools in the canonical order from
workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md Quick Start.
Continue-on-error semantics (per RESEARCH.md § Open Questions #3).
"""
from __future__ import annotations
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from ..subprocess_runner import SCRIPTS, run_script
from .samples import resolve_sample

TRIAGE_STEPS = [
    ("init_case",         ["bash",    "init_status_tree.sh"]),
    ("collect_strings",   ["bash",    "collect_strings.sh"]),
    ("collect_imports",   ["bash",    "collect_imports.sh"]),
    ("scan_yara",         ["bash",    "scan_yara.sh"]),
    ("scan_capa",         ["bash",    "scan_capa.sh"]),
]


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def run_triage(sample: str) -> dict:
        """Full triage: init_case → strings → imports → yara → capa → rank → hypothesis → mark triage_complete.

        Returns {steps: [{step, exit_code, stderr_head}], case_dir}. Continue-on-error.
        """
        path = resolve_sample(sample)
        # 1) init_case to get the case dir
        init = await run_script(
            ["bash", str(SCRIPTS / "init_status_tree.sh"), path],
            cwd="/agent",
            timeout=60.0,
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
            r = await run_script(argv, cwd="/agent", timeout=600.0)
            steps.append({"step": name, "exit_code": r["exit_code"], "stderr_head": r["stderr"][:500]})

        for name, py_script in [
            ("rank_signals",     "rank_signals.py"),
            ("build_hypothesis", "build_hypothesis.py"),
        ]:
            if not case_dir:
                steps.append({"step": name, "exit_code": -1, "stderr_head": "no case_dir from init"})
                continue
            argv = ["python3", str(SCRIPTS / py_script), "--status-dir", case_dir]
            r = await run_script(argv, cwd="/agent", timeout=600.0)
            steps.append({"step": name, "exit_code": r["exit_code"], "stderr_head": r["stderr"][:500]})

        if case_dir:
            r = await run_script(
                ["python3", str(SCRIPTS / "update_state.py"), "--status-dir", case_dir, "--phase", "triage_complete"],
                cwd="/agent",
                timeout=60.0,
            )
            steps.append({"step": "update_state", "exit_code": r["exit_code"], "stderr_head": r["stderr"][:500]})

        return {"case_dir": case_dir, "steps": steps}

    @mcp.tool()
    async def run_deep_analysis(case_dir: str) -> dict:
        """Phase 2 stub: mark phase=planning_complete via update_state.py.

        Full deep-analysis is v2 scope (references deep-analysis-checklist.md).
        """
        argv = ["python3", str(SCRIPTS / "update_state.py"), "--status-dir", case_dir, "--phase", "planning_complete"]
        return await run_script(argv, cwd="/agent", timeout=60.0)

    @mcp.tool()
    def generate_report(case_dir: str) -> dict:
        """Read 10_reporting_draft.md from case_dir and return its content."""
        draft = Path(case_dir) / "10_reporting_draft.md"
        if not draft.exists():
            return {"error": "reporting draft not found", "expected_path": str(draft)}
        return {"content": draft.read_text(encoding="utf-8", errors="replace"), "path": str(draft)}
```

Create `mcp-gateway/src/mcp_gateway/tools/disasm.py`:

```python
"""Unified disassembler tools (3): decompile, list_functions, get_xrefs.

Delegates to session_state.PINNED_BACKEND (set by Plan 03's lifespan).
Plan 02: if PINNED_BACKEND is None, return structured "backend not yet wired" error.
Plan 03: wire the real delegation via PinnedBackend.call() + tool_map.translate().
"""
from __future__ import annotations
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .. import session_state
from .samples import resolve_sample


def _backend_error_stub(unified: str) -> dict:
    return {
        "error": "backend not yet wired",
        "unified_tool": unified,
        "note": "Plan 03 will wire the PinnedBackend dispatch here.",
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def decompile(function: str, sample: Optional[str] = None) -> dict:
        """Decompile a function in the active/selected sample via the pinned backend."""
        if session_state.PINNED_BACKEND is None:
            return _backend_error_stub("decompile")
        sample_path = resolve_sample(sample) if sample else None
        # Plan 03 replaces this body with real tool_map.translate + backend.call dispatch.
        return await session_state.PINNED_BACKEND.call_unified(
            "decompile", {"function": function, "sample_path": sample_path}
        )

    @mcp.tool()
    async def list_functions(sample: Optional[str] = None) -> dict:
        """List all functions in the active/selected sample."""
        if session_state.PINNED_BACKEND is None:
            return _backend_error_stub("list_functions")
        sample_path = resolve_sample(sample) if sample else None
        return await session_state.PINNED_BACKEND.call_unified(
            "list_functions", {"sample_path": sample_path}
        )

    @mcp.tool()
    async def get_xrefs(function: str, sample: Optional[str] = None) -> dict:
        """List cross-references to a function in the active/selected sample."""
        if session_state.PINNED_BACKEND is None:
            return _backend_error_stub("get_xrefs")
        sample_path = resolve_sample(sample) if sample else None
        return await session_state.PINNED_BACKEND.call_unified(
            "get_xrefs", {"function": function, "sample_path": sample_path}
        )
```

Create `mcp-gateway/tests/test_artifact_tools.py`:

```python
"""Tests for atomic artifact tools — verify they assemble the correct argv for run_script.

We patch subprocess_runner.run_script to capture argv rather than actually execute scripts.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from mcp_gateway.tools import artifacts as artifacts_mod
from mcp_gateway.tools import samples as samples_mod


@pytest.fixture
def captured_argv(monkeypatch, tmp_path):
    captured: list[tuple[list[str], dict]] = []

    async def fake_run_script(argv, *, cwd="/agent", timeout=600.0, env=None):
        captured.append((list(argv), {"cwd": cwd, "timeout": timeout}))
        return {"exit_code": 0, "stdout": str(tmp_path / "001-demo.bin"), "stderr": ""}

    monkeypatch.setattr(artifacts_mod, "run_script", fake_run_script)
    # Also allow resolve_sample to accept a sample under a tmp uploads dir.
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    sha = "c" * 64
    sd = uploads / sha
    sd.mkdir()
    f = sd / "demo.bin"
    f.write_bytes(b"\x00")
    monkeypatch.setattr(samples_mod, "UPLOADS_ROOT", uploads)
    monkeypatch.setattr(samples_mod, "ALLOWED_PREFIXES", (uploads,))
    return captured, sha, f


async def _invoke(fn, *args, **kwargs):
    return await fn(*args, **kwargs)


def _get_tool(mcp: FastMCP, name: str):
    """Extract the underlying handler callable from a registered FastMCP tool."""
    # FastMCP internal — if upgraded past 1.27, rewrite using create_connected_server_and_client_session.call_tool(name, args)
    # Private-attr access is acceptable here because unit tests need direct access to the
    # bound function for argv-shape assertions (the public API would hide argv inside a
    # subprocess call). Name listing / tools/list tests use the public API (see test_tool_list.py).
    mgr = getattr(mcp, "_tool_manager", None)
    if mgr is None:
        raise AssertionError("FastMCP version missing _tool_manager")
    tool = mgr._tools[name]
    return tool.fn


@pytest.fixture
def registered_mcp():
    mcp = FastMCP("test", stateless_http=True)
    artifacts_mod.register(mcp)
    return mcp


@pytest.mark.asyncio
async def test_init_case_argv(captured_argv, registered_mcp):
    captured, sha, f = captured_argv
    init_case = _get_tool(registered_mcp, "init_case")
    await init_case(sample=sha)
    assert captured[0][0][0] == "bash"
    assert captured[0][0][1].endswith("init_status_tree.sh")
    assert captured[0][0][2] == str(f.resolve())
    assert captured[0][1]["cwd"] == "/agent"


@pytest.mark.asyncio
async def test_collect_strings_with_case_dir(captured_argv, registered_mcp):
    captured, sha, f = captured_argv
    collect_strings = _get_tool(registered_mcp, "collect_strings")
    await collect_strings(sample=sha, case_dir="/agent/status/001-demo.bin")
    argv = captured[0][0]
    assert argv[1].endswith("collect_strings.sh")
    assert argv[2] == str(f.resolve())
    assert argv[3] == "/agent/status/001-demo.bin"


@pytest.mark.asyncio
async def test_rank_signals_uses_python3(captured_argv, registered_mcp):
    captured, _sha, _f = captured_argv
    rank_signals = _get_tool(registered_mcp, "rank_signals")
    await rank_signals(case_dir="/agent/status/001-demo.bin")
    argv = captured[0][0]
    assert argv[0] == "python3"
    assert argv[1].endswith("rank_signals.py")
    assert argv[2:4] == ["--status-dir", "/agent/status/001-demo.bin"]


@pytest.mark.asyncio
async def test_update_state_phase_flag(captured_argv, registered_mcp):
    captured, _sha, _f = captured_argv
    update_state = _get_tool(registered_mcp, "update_state")
    await update_state(case_dir="/x", phase="triage_complete")
    argv = captured[0][0]
    assert argv == ["python3", argv[1], "--status-dir", "/x", "--phase", "triage_complete"]


def test_get_artifact_rejects_traversal(tmp_path, registered_mcp):
    get_artifact = _get_tool(registered_mcp, "get_artifact")
    (tmp_path / "00_sample_profile.md").write_text("hi")
    with pytest.raises(ValueError):
        get_artifact(case_dir=str(tmp_path), artifact_name="../etc/passwd")
    with pytest.raises(ValueError):
        get_artifact(case_dir=str(tmp_path), artifact_name="foo/bar")


def test_get_artifact_reads_content(tmp_path, registered_mcp):
    get_artifact = _get_tool(registered_mcp, "get_artifact")
    (tmp_path / "00_sample_profile.md").write_text("sample-content")
    r = get_artifact(case_dir=str(tmp_path), artifact_name="00_sample_profile.md")
    assert r["content"] == "sample-content"
    assert r["size"] == len("sample-content")
```

Create `mcp-gateway/tests/test_workflow_tools.py`:

```python
"""Tests for composite workflow tools (run_triage ordering, run_deep_analysis phase arg)."""
from __future__ import annotations
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP

from mcp_gateway.tools import workflows as workflows_mod
from mcp_gateway.tools import samples as samples_mod


EXPECTED_ORDER = [
    "init_status_tree.sh",
    "collect_strings.sh",
    "collect_imports.sh",
    "scan_yara.sh",
    "scan_capa.sh",
    "rank_signals.py",
    "build_hypothesis.py",
    "update_state.py",
]


@pytest.fixture
def mocked_run_triage(monkeypatch, tmp_path):
    invocations: list[list[str]] = []

    async def fake_run_script(argv, *, cwd="/agent", timeout=600.0, env=None):
        invocations.append(list(argv))
        # init_status_tree.sh prints the case_dir as the last stdout line
        if argv[1].endswith("init_status_tree.sh"):
            return {"exit_code": 0, "stdout": "/agent/status/001-demo.bin", "stderr": ""}
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(workflows_mod, "run_script", fake_run_script)

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    sha = "d" * 64
    (uploads / sha).mkdir()
    (uploads / sha / "demo.bin").write_bytes(b"\x00")
    monkeypatch.setattr(samples_mod, "UPLOADS_ROOT", uploads)
    monkeypatch.setattr(samples_mod, "ALLOWED_PREFIXES", (uploads,))
    return invocations, sha


def _get_tool(mcp: FastMCP, name: str):
    # FastMCP internal — if upgraded past 1.27, rewrite using create_connected_server_and_client_session.call_tool(name, args)
    # This is acceptable for unit-level tests that need direct function access for argv assertion;
    # name listing and integration tests should use the public API (see test_tool_list.py).
    return mcp._tool_manager._tools[name].fn


@pytest.fixture
def mcp_instance():
    m = FastMCP("test", stateless_http=True)
    workflows_mod.register(m)
    return m


@pytest.mark.asyncio
async def test_run_triage_order(mocked_run_triage, mcp_instance):
    invocations, sha = mocked_run_triage
    run_triage = _get_tool(mcp_instance, "run_triage")
    result = await run_triage(sample=sha)
    scripts_called = [argv[1].split("/")[-1] for argv in invocations]
    assert scripts_called == EXPECTED_ORDER, f"got {scripts_called}"
    # All steps reported
    assert [s["step"] for s in result["steps"]] == [
        "init_case", "collect_strings", "collect_imports", "scan_yara", "scan_capa",
        "rank_signals", "build_hypothesis", "update_state",
    ]


@pytest.mark.asyncio
async def test_run_deep_analysis_sets_phase(mocked_run_triage, mcp_instance):
    invocations, _sha = mocked_run_triage
    run_deep = _get_tool(mcp_instance, "run_deep_analysis")
    await run_deep(case_dir="/agent/status/001-demo.bin")
    argv = invocations[0]
    assert argv[0] == "python3"
    assert argv[1].endswith("update_state.py")
    assert "--phase" in argv and argv[argv.index("--phase") + 1] == "planning_complete"


def test_generate_report_missing(mcp_instance, tmp_path):
    gen = _get_tool(mcp_instance, "generate_report")
    r = gen(case_dir=str(tmp_path))
    assert "error" in r


def test_generate_report_returns_content(mcp_instance, tmp_path):
    (tmp_path / "10_reporting_draft.md").write_text("# Report\nhello")
    gen = _get_tool(mcp_instance, "generate_report")
    r = gen(case_dir=str(tmp_path))
    assert r["content"].startswith("# Report")
```
  </action>
  <verify>
    <automated>pytest mcp-gateway/tests/test_artifact_tools.py mcp-gateway/tests/test_workflow_tools.py -x --no-header -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest mcp-gateway/tests/test_artifact_tools.py -x --no-header -q` exits 0
    - `pytest mcp-gateway/tests/test_workflow_tools.py -x --no-header -q` exits 0
    - `grep -c '@mcp.tool()' mcp-gateway/src/mcp_gateway/tools/cases.py` == 5 (5 case/sample tools)
    - `grep -c '@mcp.tool()' mcp-gateway/src/mcp_gateway/tools/artifacts.py` == 10 (10 atomic tools)
    - `grep -c '@mcp.tool()' mcp-gateway/src/mcp_gateway/tools/workflows.py` == 3 (3 composite tools)
    - `grep -c '@mcp.tool()' mcp-gateway/src/mcp_gateway/tools/disasm.py` == 3 (3 disasm tools)
    - Total: 5+10+3+3 = 21 tools across the four modules
    - `grep -q 'register_all_tools' mcp-gateway/src/mcp_gateway/tools/__init__.py`
    - `grep -q "asyncio.create_subprocess_exec\|from ..subprocess_runner import" mcp-gateway/src/mcp_gateway/tools/artifacts.py`
    - `grep -q 'resolve_sample' mcp-gateway/src/mcp_gateway/tools/artifacts.py`
    - `grep -q 'session_state.PINNED_BACKEND' mcp-gateway/src/mcp_gateway/tools/disasm.py`
    - `python -c "from mcp_gateway.tools import register_all_tools; from mcp.server.fastmcp import FastMCP; m = FastMCP('t', stateless_http=True); register_all_tools(m); print(len(m._tool_manager._tools))"` prints `21`
  </acceptance_criteria>
  <done>All 21 tools registered across the 4 modules; atomic + composite tool argv assembly verified; disasm tools return stub error awaiting Plan 03; 11 tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Starlette app factory (build_app) + tools/list integration test + healthz</name>
  <files>
    mcp-gateway/src/mcp_gateway/app.py,
    mcp-gateway/tests/test_server_init.py,
    mcp-gateway/tests/test_tool_list.py
  </files>
  <read_first>
    - mcp-gateway/src/mcp_gateway/auth.py (Plan 01 — BearerAuthMiddleware, OriginMiddleware, load_or_generate_token)
    - mcp-gateway/src/mcp_gateway/backend/detect.py (Plan 01 — detect_backend)
    - mcp-gateway/src/mcp_gateway/tools/__init__.py (Task 2 — register_all_tools)
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Pattern 1 Full skeleton; § Code Example 1 app.py)
    - .planning/phases/02-mcp-gateway/02-CONTEXT.md (D-09 backend pinned; D-10 fail loud if detect raises)
    - .planning/phases/02-mcp-gateway/02-VALIDATION.md (rows for GW-01 and GW-02)
  </read_first>
  <behavior>
    - `build_app()` returns a Starlette app with routes: `/healthz`, `/upload` (Plan 04 implements handler; Task 3 registers a placeholder returning 501), `/mcp` (mounted FastMCP ASGI)
    - `build_app()` adds `OriginMiddleware` then `BearerAuthMiddleware` (order: Origin outer, Bearer inner)
    - `build_app()` calls `detect_backend()` and logs which backend was selected; if no backend → raise (fail loud per D-10), but in test environments provide `MCP_GATEWAY_SKIP_BACKEND=1` to bypass
    - GET `/healthz` (no auth) → 200 `{"ok": true}`
    - POST `/mcp` with valid bearer + `initialize` JSON-RPC payload → successful session initialize
    - `tools/list` after initialize → returns exactly 21 tools
    - Count of tools is in [15, 25] (GW-02)
    - Every orchestrator script has a matching atomic tool name in the tool list
  </behavior>
  <action>
Create `mcp-gateway/src/mcp_gateway/app.py`:

```python
"""Starlette application factory + FastMCP integration + middleware wiring.

Fulfills GW-01 (FastMCP Streamable HTTP), wires Plan 01 auth, registers 21 tools
from Plan 02 Task 2. The /upload route is a placeholder here returning 501;
Plan 04 replaces it with a real streaming handler.
"""
from __future__ import annotations
import contextlib
import logging
import os

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp.server.fastmcp import FastMCP

from .auth import BearerAuthMiddleware, OriginMiddleware, load_or_generate_token
from .backend.detect import detect_backend
from .tools import register_all_tools
from . import session_state

log = logging.getLogger("mcp_gateway")

_MCP_INSTANCE: FastMCP | None = None


def get_mcp() -> FastMCP:
    """Access the module-level FastMCP instance (used by Plan 03 to register backend-fed tools)."""
    global _MCP_INSTANCE
    if _MCP_INSTANCE is None:
        _MCP_INSTANCE = FastMCP("mare-gateway", stateless_http=True, json_response=True)
    return _MCP_INSTANCE


async def _healthz(request):
    return JSONResponse({"ok": True})


async def _upload_placeholder(request):
    """Placeholder — replaced by Plan 04's real streaming handler."""
    return JSONResponse(
        {"error": "upload handler not yet installed", "plan": "Plan 04"},
        status_code=501,
    )


def build_app() -> Starlette:
    """Assemble the gateway ASGI app.

    Order of operations:
      1) Generate/load bearer token (D-16, D-17, T-02-TOKENLEAK).
      2) Detect backend (D-09). Raise if none installed (D-10 fail-loud) unless
         MCP_GATEWAY_SKIP_BACKEND=1 (test-only escape hatch).
      3) Create FastMCP instance and register all 21 tools (GW-02).
      4) Build Starlette app with /healthz, /upload placeholder, /mcp mount.
      5) Add OriginMiddleware (outer, DNS rebind T-02-NET) + BearerAuthMiddleware (inner, T-02-AUTH).
    """
    token = load_or_generate_token()

    skip_backend = os.environ.get("MCP_GATEWAY_SKIP_BACKEND") == "1"
    if skip_backend:
        log.warning("[gateway] MCP_GATEWAY_SKIP_BACKEND=1 — backend detection bypassed (test mode)")
        backend_name = "none"
    else:
        backend_name = detect_backend()
        log.info("[gateway] backend: %s", backend_name)

    mcp = get_mcp()
    register_all_tools(mcp)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        # Plan 03 extends this lifespan to enter a PinnedBackend context.
        log.info(
            "[gateway] ready on %s:%s",
            os.environ.get("MCP_GATEWAY_HOST", "127.0.0.1"),
            os.environ.get("MCP_GATEWAY_PORT", "8080"),
        )
        log.info("[gateway] token file: %s", os.environ.get("MCP_GATEWAY_TOKEN_FILE", "/agent/.mcp-gateway-token"))
        async with mcp.session_manager.run():
            yield

    app = Starlette(
        routes=[
            Route("/healthz", _healthz, methods=["GET"]),
            Route("/upload", _upload_placeholder, methods=["POST"]),
            Mount("/mcp", app=mcp.streamable_http_app()),
        ],
        lifespan=lifespan,
    )
    # Order matters: Starlette runs middleware in REVERSE add order for requests,
    # so add Bearer last (innermost) to run first; add Origin before Bearer (outermost).
    app.add_middleware(BearerAuthMiddleware, token=token)
    app.add_middleware(OriginMiddleware)
    return app
```

Create `mcp-gateway/tests/test_server_init.py`:

```python
"""Test that the Starlette app initializes FastMCP over Streamable HTTP properly.

Maps to VALIDATION.md row GW-01 (Streamable HTTP initialize returns session id).
Uses Starlette's TestClient with lifespan triggering mcp.session_manager.run().
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "test-token")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / "tok"))
    monkeypatch.setenv("MCP_GATEWAY_SKIP_BACKEND", "1")
    # Reset the module-level FastMCP singleton and tool state between tests
    import mcp_gateway.app as app_mod
    app_mod._MCP_INSTANCE = None
    return app_mod.build_app()


def test_healthz_open(app):
    with TestClient(app) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"ok": True}


def test_healthz_open_ignores_origin(app):
    with TestClient(app) as c:
        r = c.get("/healthz", headers={"Origin": "http://evil.com"})
        # OriginMiddleware runs on all paths; verify /healthz returns 403 on evil Origin.
        assert r.status_code == 403


def test_mcp_requires_bearer(app):
    with TestClient(app) as c:
        r = c.post("/mcp", json={})
        assert r.status_code == 401


def test_mcp_initialize_succeeds(app):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"},
        },
    }
    headers = {
        "Authorization": "Bearer test-token",
        "Accept": "application/json, text/event-stream",
    }
    with TestClient(app) as c:
        r = c.post("/mcp", json=payload, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        # FastMCP's initialize response includes protocolVersion and serverInfo
        assert body.get("result", {}).get("serverInfo", {}).get("name") == "mare-gateway"
```

Create `mcp-gateway/tests/test_tool_list.py`:

```python
"""Tests that the curated tool surface meets GW-02 (15-25 tools) and D-01..D-04.

Maps to VALIDATION.md rows:
  - GW-02 test_tool_count_in_range
  - GW-02 test_atomic_tools_map_to_scripts
  - GW-01/GW-02 (tools/list integration)

IMPORTANT — FastMCP internals vs public API:
  The preferred way to list tool names is via the public MCP client API:
    `async with create_connected_server_and_client_session(mcp._mcp_server) as session:`
    `    resp = await session.list_tools()`
    `    names = {t.name for t in resp.tools}`
  That path is stable across SDK versions (protocol-level tools/list).
  The `mcp._tool_manager._tools` attribute is internal to FastMCP 1.27 and will break
  on future SDK upgrades — we pin `mcp>=1.27,<1.28` in pyproject.toml to guard against that.
  The private-attr fallback is only kept where it adds value (count sanity check); name
  listing goes through the public API.
"""
from __future__ import annotations
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_gateway.tools import register_all_tools

EXPECTED_TOOLS = {
    # Composite (3)
    "run_triage", "run_deep_analysis", "generate_report",
    # Atomic (10)
    "init_case", "collect_strings", "collect_imports", "scan_yara", "scan_capa",
    "rank_signals", "build_hypothesis", "update_state", "resolve_case", "get_artifact",
    # Disassembler (3)
    "decompile", "list_functions", "get_xrefs",
    # Case/sample mgmt (5)
    "list_cases", "set_active_case", "get_active_case", "list_uploads", "get_sample_info",
}


@pytest.fixture
def registered():
    m = FastMCP("t", stateless_http=True)
    register_all_tools(m)
    return m


async def _list_tool_names(mcp: FastMCP) -> set[str]:
    """PUBLIC API path — uses protocol-level tools/list over in-memory transport."""
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        resp = await session.list_tools()
        return {t.name for t in resp.tools}


async def test_all_expected_tools_present(registered):
    names = await _list_tool_names(registered)
    assert EXPECTED_TOOLS.issubset(names), f"missing: {EXPECTED_TOOLS - names}"


async def test_tool_count_in_range(registered):
    names = await _list_tool_names(registered)
    n = len(names)
    assert 15 <= n <= 25, f"tool count {n} violates GW-02 (15-25)"


async def test_no_unexpected_tools(registered):
    names = await _list_tool_names(registered)
    extras = names - EXPECTED_TOOLS
    assert not extras, f"unexpected tools registered: {extras}"


async def test_atomic_tools_map_to_scripts(registered):
    """Every shell/py script in orchestrator scripts/ has an atomic tool wrapper."""
    # The mapping is (script_basename -> tool_name); update when scripts are added/renamed.
    mapping = {
        "init_status_tree.sh": "init_case",
        "collect_strings.sh": "collect_strings",
        "collect_imports.sh": "collect_imports",
        "scan_yara.sh": "scan_yara",
        "scan_capa.sh": "scan_capa",
        "rank_signals.py": "rank_signals",
        "build_hypothesis.py": "build_hypothesis",
        "update_state.py": "update_state",
        "resolve_case.sh": "resolve_case",
    }
    names = await _list_tool_names(registered)
    for script, tool in mapping.items():
        assert tool in names, f"atomic tool {tool!r} for script {script!r} not registered"


def test_tool_count_private_sanity(registered):
    """Quick sanity check via FastMCP internal — guards `mcp>=1.27,<1.28` pin.
    If this breaks on SDK upgrade, rewrite ALL tests in this file using
    `create_connected_server_and_client_session` (the public API path above).
    """
    # FastMCP internal — if upgraded past 1.27, rewrite using create_connected_server_and_client_session.call_tool(name, args)
    n = len(registered._tool_manager._tools)
    assert 15 <= n <= 25, f"private-attr sanity: tool count {n} violates GW-02 (15-25)"
```
  </action>
  <verify>
    <automated>pytest mcp-gateway/tests/test_server_init.py mcp-gateway/tests/test_tool_list.py -x --no-header -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest mcp-gateway/tests/test_server_init.py -x --no-header -q` exits 0
    - `pytest mcp-gateway/tests/test_tool_list.py -x --no-header -q` exits 0
    - `grep -q 'streamable_http_app()' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'session_manager.run()' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'add_middleware(BearerAuthMiddleware' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'add_middleware(OriginMiddleware' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'Route("/healthz"' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'Route("/upload"' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'Mount("/mcp"' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'detect_backend()' mcp-gateway/src/mcp_gateway/app.py`
    - `pytest mcp-gateway/tests/ -v --no-header 2>&1 | grep -E '[0-9]+ passed'` shows >= 35 tests passing (combined with Plan 01 tests)
    - Running the full plan 02 test suite: `pytest mcp-gateway/tests/ -x --no-header -q` exits 0
  </acceptance_criteria>
  <done>Starlette app factory assembled; /healthz open, /mcp gated by bearer, /upload placeholder in place, 21 tools visible via tools/list, initialize handshake succeeds; 10+ new tests green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| MCP tool input (sample, case_dir, artifact_name) | Untrusted: arrives via authenticated MCP call but may be attacker-controlled |
| orchestrator scripts | Trusted (bundled with repo); invoked with argv only, never via shell |
| /agent filesystem subtrees (uploads, examples, status) | Trusted targets for path resolution |
| Plan 03 PinnedBackend | Not yet wired; disasm tools return stub |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-02-SUBPROC | Tampering / RCE | `subprocess_runner.run_script`, all atomic tools | HIGH | mitigate | Task 1: `asyncio.create_subprocess_exec(*argv)`, no `shell=True`, argv is always a list with literal script paths + `resolve_sample()` output. Acceptance criteria greps for absence of `shell=True`. |
| T-02-PATHTRAVERSAL | Tampering / EoP | `tools/samples.py::resolve_sample`, `tools/artifacts.py::get_artifact` | HIGH | mitigate | Task 1: `resolve_sample` canonicalizes with `os.path.realpath` and requires the result under one of ALLOWED_PREFIXES; rejects `..` pre-canonicalization. Task 2: `get_artifact` rejects artifact_name containing `/` or `..` and verifies canonicalized path stays under case_dir. |
| T-02-AUTH | Spoofing / EoP | `/mcp`, `/upload` placeholder | HIGH | mitigate | Task 3: `build_app()` adds `BearerAuthMiddleware` from Plan 01 to the Starlette app covering all `/mcp*` and `/upload` paths. `/healthz` open. Test `test_mcp_requires_bearer` verifies. |
| T-02-NET | Spoofing (DNS rebind) | Starlette app | MEDIUM | mitigate | Task 3: `build_app()` adds `OriginMiddleware` outer layer. Test verifies evil Origin returns 403 even on `/healthz`. |
| T-02-TOKENLEAK | Info Disclosure | token lifecycle | MEDIUM | mitigate | Plan 01 handles token file + log; Task 3 ensures `build_app()` calls `load_or_generate_token()` at startup and nothing else logs the token. |
| T-02-UPLOAD | DoS | /upload placeholder | HIGH | transfer | Plan 04 replaces placeholder with streaming handler enforcing `MCP_GATEWAY_MAX_UPLOAD_MB`. Task 3 placeholder returns 501 — does NOT accept body. |
</threat_model>

<verification>
After all 3 tasks:
1. Full plan test suite: `pytest mcp-gateway/tests/ -x --no-header -q` — exits 0 with >= 35 tests
2. Tool count: `python -c "from mcp_gateway.tools import register_all_tools; from mcp.server.fastmcp import FastMCP; m = FastMCP('t', stateless_http=True); register_all_tools(m); print(len(m._tool_manager._tools))"` prints `21`
3. Initialize handshake: `test_mcp_initialize_succeeds` green (uses Starlette TestClient + Streamable HTTP)
4. Security greps:
   - `grep -rn 'shell=True' mcp-gateway/src/` → no hits
   - `grep -rn 'os.system\|os.popen' mcp-gateway/src/` → no hits
5. `ruff check mcp-gateway/src/ mcp-gateway/tests/` — clean
6. Tools/list symmetry: every script in `workspace/.claude/skills/malware-analysis-orchestrator/scripts/*.{sh,py}` has a tool (verified by `test_atomic_tools_map_to_scripts`)
</verification>

<success_criteria>
- GW-01 met: `build_app()` returns a Starlette app that answers `initialize` over Streamable HTTP at `/mcp` with valid bearer (`test_mcp_initialize_succeeds`)
- GW-02 met: exactly 21 tools registered, all within the 15-25 target, every orchestrator script maps to an atomic tool
- T-02-SUBPROC mitigated: no `shell=True` anywhere; argv-only execution
- T-02-PATHTRAVERSAL mitigated: resolve_sample + get_artifact reject all traversal forms
- T-02-AUTH enforced: `/mcp` without bearer → 401, `/upload` without bearer → 401, `/healthz` open
- T-02-NET enforced: evil Origin → 403, localhost/127.0.0.1/null/missing → 200
- Disasm tools registered but correctly return stub error when `session_state.PINNED_BACKEND is None` (Plan 03 wires real delegation)
- `/upload` placeholder returns 501 (Plan 04 will replace)
- All decisions honored: D-01 (layered tools), D-02 (13 atomic + workflows + disasm), D-03 (verb-first names), D-04 (case tools), D-05 (no raw passthrough), D-08 (reuse scripts), D-09 (detect_backend called)
</success_criteria>

<output>
After completion, create `.planning/phases/02-mcp-gateway/02-02-SUMMARY.md`.
Include:
- 21-tool inventory table with script mappings
- FastMCP + Starlette wiring (middleware order, routes)
- Test counts: test_sample_resolution.py (12), test_artifact_tools.py (6), test_workflow_tools.py (4), test_server_init.py (4), test_tool_list.py (4)
- Threat mitigations: T-02-SUBPROC, T-02-PATHTRAVERSAL (both in Task 1/2); T-02-AUTH/T-02-NET carried into app.py
- Handoff to Plan 03: `session_state.PINNED_BACKEND` is still `None`; `disasm.py` tools return stub — Plan 03 wires real backend dispatch via `.call_unified(unified_name, args)` method on PinnedBackend
- Handoff to Plan 04: `/upload` route returns 501 — Plan 04 replaces `_upload_placeholder` with streaming handler
</output>
