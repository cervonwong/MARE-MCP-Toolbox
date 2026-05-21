---
quick_task: 260521-mhh
title: "v1.1 cleanup batch — security-boundary README, r2_sessions test-infra refactor, REQUIREMENTS traceability sweep, skill-md container-skip"
type: execute
wave: 1
depends_on: []
autonomous: true
files_modified:
  - README.md
  - mcp-gateway/src/mcp_gateway/tools/r2_sessions.py
  - mcp-gateway/tests/test_skill_md_dual_mode.py
  - .planning/milestones/v1.1-REQUIREMENTS.md
  - .planning/milestones/v1.1-phases/14-close-v1.1-gaps/deferred-items.md
must_haves:
  truths:
    - "README has an explicit Security Boundaries section that accurately describes run_shell posture (cwd + UID + no isolation), no-network default, dynamic-mode opt-in, bearer + Origin validation, command capture, and r2 cfg.sandbox latch"
    - "Re-running the 12 r2_sessions tests in-container resolves resolve_case_dir via the monkeypatched path (no more `ValueError: case_dir must be under /agent/status`)"
    - "v1.1-REQUIREMENTS.md traceability table shows 0 rows with `TBD | Pending` for the 47 affected ID families (FOUND/SHELL/STATIC/ARTIF-05/SESS/JOBS/EXTR/DYN/SKILL)"
    - "pytest collection succeeds on test_skill_md_dual_mode.py inside the container (no StopIteration on the .planning walk)"
  artifacts:
    - path: "README.md"
      provides: "Security Boundaries section"
    - path: "mcp-gateway/src/mcp_gateway/tools/r2_sessions.py"
      provides: "module-attribute access to resolve_case_dir so conftest monkeypatch propagates"
    - path: "mcp-gateway/tests/test_skill_md_dual_mode.py"
      provides: "module-level container-skip guard before the .planning walk"
    - path: ".planning/milestones/v1.1-REQUIREMENTS.md"
      provides: "complete traceability for 47 v1.1 requirements"
    - path: ".planning/milestones/v1.1-phases/14-close-v1.1-gaps/deferred-items.md"
      provides: "status updates marking issues #3 + #5 RESOLVED and adding sibling deferred-item for the 7 untouched case_dirs consumers"
  key_links:
    - from: "mcp-gateway/src/mcp_gateway/tools/r2_sessions.py"
      to: "mcp-gateway/tests/conftest.py::opened_sid monkeypatch (`monkeypatch.setattr(_case_dirs_mod, 'resolve_case_dir', ...)`)"
      via: "module-attribute reference (`_case_dirs.resolve_case_dir(...)`) instead of bound name (`resolve_case_dir(...)`)"
      pattern: "from . import case_dirs as _case_dirs"
    - from: ".planning/milestones/v1.1-REQUIREMENTS.md traceability table rows"
      to: ".planning/milestones/v1.1-phases/<phase>/<phase>-VERIFICATION.md"
      via: "executor reads each VERIFICATION.md to discover the plan ID(s) that landed each requirement"
      pattern: "REQ-ID → Plan column populated from VERIFICATION 'Plan(s):' or per-requirement evidence"
---

<objective>
Bundle the four v1.1 cleanup items into a single quick task with four atomic commits. All are S-effort, low-risk, themed ("v1.1 polish"), and independent — no inter-task dependencies. Issue #1 of the original audit (r2_cmd 30s timeout) was already landed in commit `fbcb88b`; this plan closes the remaining backlog from `.planning/milestones/v1.1-phases/14-close-v1.1-gaps/deferred-items.md`.

Purpose: After this lands, the v1.1 milestone closure invariants strengthen: README explicitly documents the security boundary that ops + auditors need to know (closes STATE.md:196 concern); 12 r2-session tests can run GREEN in-container (closes deferred-items #18-25); REQUIREMENTS traceability shows full Plan/Verified coverage (closes #6-14); pytest collection no longer trips inside the container (closes #27-34). Three of the four deferred-items entries flip to `Status: RESOLVED`.

Output:
- README.md with a "Security Boundaries" section (the existing "Security notes" section grows into it; see Task 2 detail)
- r2_sessions.py with `from . import case_dirs as _case_dirs` + 4 call-site renames (resolve_case_dir → _case_dirs.resolve_case_dir)
- test_skill_md_dual_mode.py with a module-level container-skip guard that runs BEFORE the next() walker call on line 28
- v1.1-REQUIREMENTS.md with 47 rows flipped from `TBD | Pending` to `<plan> | [x]`
- deferred-items.md with three status updates + one new sibling entry
</objective>

<execution_context>
Quick-mode execution — no execute-plan workflow indirection. Read this PLAN.md, do the four tasks IN ORDER (5 → 2 → 3 → 4), commit after each per CLAUDE.md (single line, Sentence-cased imperative verb). Push only when the user asks.
</execution_context>

<context>
Background from the planning brief:
- STATE.md:196 logs the security-boundary documentation gap explicitly
- deferred-items.md (Phase 14) entries `test_r2_sessions.py fixture monkey-patch bypass` (lines 18-25), `test_skill_md_dual_mode.py StopIteration in-container` (lines 27-34), and the 47-row traceability sweep (lines 6-14) are the source-of-truth for #2, #3, #4, #5
- Issue #1 (r2_cmd 30s timeout) is already fixed in commit `fbcb88b` — do NOT re-touch
- Each phase under `.planning/milestones/v1.1-phases/<phase>/` has a `<phase>-VERIFICATION.md` that lists which plan(s) satisfied each requirement (this is the source-of-truth for Task 4 column fills)

Codebase facts established during planning (do NOT re-discover):

1. **Issue #3 scope grep result** — 8 source files reference `resolve_case_dir`:
   - 6 use `from .case_dirs import resolve_case_dir`: workflows.py, artifacts.py, shell.py, re_artifacts.py, re_static.py, jobs.py (jobs uses absolute form; group with these for consistency)
   - 2 use `from mcp_gateway.tools.case_dirs import resolve_case_dir`: r2_sessions.py, extract.py
   - The conftest fixture (`opened_sid`) only exercises `r2_sessions.py` via the SESS-* test surface; the other 7 files are NOT exercised by tests that hit the same monkeypatch chain
   - **Decision (constraint b):** refactor ONLY r2_sessions.py in Task 3. Add a sibling deferred-item in deferred-items.md (under "From Plan 14-04") documenting that 7 other consumers (artifacts.py, workflows.py, shell.py, re_artifacts.py, re_static.py, jobs.py, extract.py) share the same module-binding shape and should switch to module-attribute access if future tests want to monkeypatch their case_dir validators

2. **README structure** — existing relevant sections:
   - Line 559: `## Security notes` (8 bullets — bearer, Origin, default bind, capabilities, run_shell posture, IDA/BN licenses, unsafe r2)
   - The user's ask in STATE.md:196 wants MORE explicit boundary breakdown: what is the shell really doing (cwd-confine, not isolation), default-vs-dynamic network behavior, every-invocation-captured guarantee
   - **Insertion strategy (Task 2):** REPLACE `## Security notes` (line 559) with a richer `## Security boundaries` section. Keep the existing 8 bullets (they're correct) but reorganize into 4 sub-headings: "Network & Auth boundary", "Shell & subprocess boundary", "r2 sandbox boundary", "Audit & capture boundary". Add the missing explicit content from STATE.md:196 under each sub-heading. Total target: ~50-70 lines (currently ~9 lines).

3. **Issue #5 fix shape** — line 28 of test_skill_md_dual_mode.py is:
   ```python
   REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".planning").is_dir())
   ```
   This raises `StopIteration` inside the container where no parent of `/opt/mcp-gateway/tests/` contains `.planning`. The fix is to guard the walk BEFORE it executes. Two options from deferred-items:35 — (a) `pytest.mark.skipif` at module level checking `Path("/host/.planning").is_dir()`, or (b) check if any parent contains `.planning` before the walk. Option (b) is cleaner because it makes the test self-detecting; option (a) hardcodes a path that may not exist in CI. **Use option (b)**: replace line 28's `next(...)` with a guard that calls `pytest.skip(...)` at module collection time if no parent matches.

4. **Issue #4 sweep approach** — DO NOT enumerate 47 rows in this plan. Instead instruct the executor: for each REQ-ID family (FOUND, SHELL, STATIC, ARTIF-05, SESS, JOBS, EXTR, DYN, SKILL), open the corresponding `<phase>-VERIFICATION.md` and grep for the REQ-ID; the verification doc records which plan(s) satisfied it. Phase→family map:
   - FOUND-01 → 05-VERIFICATION.md
   - FOUND-02..04 → 06-VERIFICATION.md
   - SHELL-01/02, STATIC-01..10, ARTIF-05 → 07-VERIFICATION.md
   - SESS-01..06 → 08-VERIFICATION.md
   - JOBS-01..07 → 09-VERIFICATION.md
   - EXTR-01..06 → 10-VERIFICATION.md
   - DYN-01..07 → 11-VERIFICATION.md
   - SKILL-01..04 → 12-VERIFICATION.md
   When a requirement is verified by multiple plans, list both (precedent: ARTIF-01 row currently shows `07-01-PLAN.md, 07-05-PLAN.md`).

Risk model:
- Task 2 (README): zero-risk (docs)
- Task 3 (r2_sessions refactor): low-risk — semantically identical Python; risk is breaking other call sites in the file. Mitigation: `<verify>` block runs `python -c "from mcp_gateway.tools import r2_sessions"` to confirm import; then run the 4 r2_sessions tests that DON'T need r2 (the docstring/registration tests) to confirm no behavior change. The 12 r2-spawning tests can only be verified in-container (host has no r2); flag this in the commit message but don't block on it.
- Task 4 (REQUIREMENTS sweep): low-risk (docs) — mechanical fill; verification is `grep -c "TBD  | Pending" .planning/milestones/v1.1-REQUIREMENTS.md` must return 0
- Task 5 (skill-md container skip): zero-risk — only adds a skip; host-mode behavior unchanged

</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix test_skill_md_dual_mode.py StopIteration in container (issue #5)</name>
  <files>mcp-gateway/tests/test_skill_md_dual_mode.py</files>
  <action>
    Open `mcp-gateway/tests/test_skill_md_dual_mode.py`. Line 28 currently reads:

        REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".planning").is_dir())

    Replace this single line with a guarded walk that calls `pytest.skip(...)` at module collection time when no parent contains `.planning`. Exact replacement:

        # Pitfall 4 mitigation: locate REPO_ROOT by .planning marker, not parents[2].
        # Container guard: when no parent contains `.planning` (e.g. inside the Docker
        # image at /opt/mcp-gateway), skip this whole module — the tests validate the
        # orchestrator skill markdown under .planning/ + workspace/skills/ which the
        # container does not ship. Resolves deferred-items.md "test_skill_md_dual_mode.py
        # StopIteration in-container" entry.
        _repo_root_candidates = [p for p in Path(__file__).resolve().parents if (p / ".planning").is_dir()]
        if not _repo_root_candidates:
            import pytest as _pytest
            _pytest.skip("no parent dir contains .planning (host-only test; container does not ship workspace/skills)", allow_module_level=True)
        REPO_ROOT = _repo_root_candidates[0]

    Notes for executor:
    - `pytest` is already imported at the top of the file (line 20), but the local `import pytest as _pytest` re-import is intentional — module-level `pytest.skip(..., allow_module_level=True)` is the documented pattern for collection-time skip and the local rebind avoids reliance on the prior import landing first (no functional difference; preserves the explicit-skip pattern).
    - Do NOT add a `@pytest.mark.skipif` to each test function — the issue is collection-time (line 28 runs at import), so skip MUST happen at module level.
    - Do NOT introduce `Path("/host/.planning")` hardcoded path; the parent-walk is the correct host/container detector.

    Commit message (single line, Sentence-cased imperative per CLAUDE.md):
        Skip test_skill_md_dual_mode at module level when no parent contains .planning

    After committing, update `.planning/milestones/v1.1-phases/14-close-v1.1-gaps/deferred-items.md`:
    in the "test_skill_md_dual_mode.py StopIteration in-container" entry (lines 27-34), change the `Status:` line from `open.` to `RESOLVED 2026-05-21 in quick task 260521-mhh — added module-level pytest.skip guard at tests/test_skill_md_dual_mode.py:28 that fires when no parent of the test file contains .planning (container path /opt/mcp-gateway/tests/).` and amend this Task 1 commit to include the deferred-items.md update.
  </action>
  <verify>
    <automated>cd /home/cervon/Code/MARE-MCP-Toolbox && python -c "import ast; ast.parse(open('mcp-gateway/tests/test_skill_md_dual_mode.py').read())" && grep -q "allow_module_level=True" mcp-gateway/tests/test_skill_md_dual_mode.py && ! grep -q "next(p for p in Path(__file__).resolve().parents" mcp-gateway/tests/test_skill_md_dual_mode.py && grep -q "RESOLVED 2026-05-21 in quick task 260521-mhh" .planning/milestones/v1.1-phases/14-close-v1.1-gaps/deferred-items.md && echo OK</automated>
  </verify>
  <done>
    Module-level pytest.skip guard is in place at line ~28; the original `next(...)` line is gone; the file parses as valid Python; deferred-items.md is updated with RESOLVED status; commit landed with a single-line Sentence-cased imperative message.
  </done>
</task>

<task type="auto">
  <name>Task 2: Add Security Boundaries section to README.md (issue #2)</name>
  <files>README.md</files>
  <action>
    Open `README.md`. The existing `## Security notes` section starts at line 559 and runs ~9 lines. REPLACE it (and rename to `## Security boundaries`) with a structured boundary breakdown. The new section MUST go in the same position (between `## License & licensing constraints` lookbehind context and `## Configuration reference` — wait, recheck: current line order is `## Configuration reference` (line 484) → `## Project layout` (line 523) → `## Security notes` (line 559) → `## License & licensing constraints` (line 569). Keep that position.

    Verified facts to encode (from CLAUDE.md, STATE.md:196, and the existing README body — do NOT invent new claims):

    **Network & Auth boundary:**
    - All `/mcp*` and `/upload` requests require `Authorization: Bearer <token>`; only `/healthz` is unauthenticated
    - Token is generated per `--remote` start and written to `workspace/.mcp-gateway-token` (mode 0600)
    - Origin DNS-rebind middleware rejects cross-origin requests that don't match the bind host
    - Default bind is `127.0.0.1:8080` (localhost-only); LAN exposure requires explicit `MCP_GATEWAY_HOST_BIND=0.0.0.0`
    - No network egress from `run_shell` or any static-wrapper subprocess (they don't touch the network themselves; the host network namespace is shared but nothing in the gateway dials out on behalf of the agent)
    - **Dynamic-mode network policy:** when `--dynamic` is set, `run_strace` / `run_ltrace` / `run_qemu_user` / `open_gdb_session` each run their subprocess under `unshare --net --ipc --uts --` (per-call netns, no inherited host network). Network is unavailable inside dynamic tools; sandboxed-network mode (INetSim/FakeDNS) is v1.2.

    **Shell & subprocess boundary (run_shell, static wrappers, jobs, sessions):**
    - `run_shell` executes a bash one-liner with:
      - cwd PINNED to the active `case_dir` (resolved via `confine_to` — rejects NUL / traversal / symlink escape)
      - dedicated non-root `mare-shell` UID via `setpriv --reuid --regid --clear-groups --no-new-privs --inh-caps=-all`
      - env stripped of `MCP_GATEWAY_TOKEN`, API keys, AWS credentials
      - output cap (`MCP_GATEWAY_RUN_SHELL_MAX_CMD_BYTES` = 32 KiB command, `MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB` preview)
      - hard wallclock timeout (`MCP_GATEWAY_RUNNER_DEFAULT_TIMEOUT_S` = 55 s)
      - process group SIGKILL on timeout/cancel
    - **Confinement is POSTURE, not isolation.** A determined attacker controlling the agent can still read the container's world-readable filesystem from inside `run_shell`. Mount-namespace isolation would require `CAP_SYS_ADMIN` and is deferred to v1.2.
    - The same `ReToolRunner` chokepoint applies to every static wrapper (`run_file`, `run_die`, `run_readelf`, `run_objdump`, `run_nm`, `run_rabin2`, `run_capstone_disasm`, `run_ropper`, `run_xxd`, `run_jq`, `run_yq`), every job-driven tool (`capa`, `unblob`, `binwalk_extract`, `strace`, `ltrace`, `qemu_user`), and every session subprocess (`r2`, `gdb`). All argv-only spawn via `asyncio.create_subprocess_exec` with `start_new_session=True`; no `shell=True` anywhere.

    **r2 sandbox boundary:**
    - `open_r2_session` spawns r2 with `-e cfg.sandbox=true` injected via stdin BEFORE the sample is opened (r2's native one-way latch — cannot be disabled mid-session)
    - `_DANGEROUS_R2_CMD_RE` regex blocks `!` / `R!` / `#!` shell-escape prefixes at the wrapper layer as defense-in-depth (the SECURITY BOUNDARY lives on `cfg.sandbox`, not the regex — see HARDEN-05)
    - `open_r2_session_unsafe` (env-gated via `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1`) spawns WITHOUT `cfg.sandbox`; every open emits a WARN-level audit log line; shares the combined session cap

    **gdb MI3 boundary (dynamic mode only):**
    - `gdb_exec` is restricted to a 49-entry MI prefix allowlist (`-info-`, `-data-evaluate-expression`, `-stack-list-frames`, etc.)
    - Deny regex blocks `python` / `pi` / `-interpreter-exec console` / `source` / `shell` / `!` / `-target-select` / `attach` and 7 other vectors
    - gdb argv NEVER includes `-iex` / `-ex` / `-x`

    **Audit & capture boundary:**
    - Every subprocess invocation captures full stdout/stderr to `case_dir/tool-logs/<UTC>-<slug>-<rand4>.txt`; only a head-truncated preview returns over MCP
    - r2/gdb sessions write a per-command transcript line to `case_dir/r2-sessions/<sid>-transcript.log` / `case_dir/dynamic/gdb-<sid>-transcript.log`
    - Job log size capped at `MCP_GATEWAY_MAX_JOB_LOG_MB` = 256 MB; over-cap jobs are killed with `status=killed_log_cap`
    - In-flight jobs are killed on gateway shutdown (in-memory registry; no persistence by design)

    **Container capabilities (informational, NOT a boundary):**
    - The container runs with `CAP_SYS_PTRACE` and `seccomp=unconfined` so analysis tools (gdb, strace, qemu-user, idalib) can attach to debuggees and emit syscalls. **Do NOT expose the gateway port to the public internet without a reverse proxy you trust.** Default `127.0.0.1` bind exists for this reason.

    **Disassembler licensing:**
    - IDA Pro and Binary Ninja licenses live ONLY on the host bind mount; never baked into image layers (multi-stage build pattern in `Dockerfile`)

    Formatting notes for executor:
    - Use the four sub-headings as `### Network & Auth boundary`, `### Shell & subprocess boundary`, `### r2 sandbox boundary`, `### gdb MI3 boundary (dynamic mode only)`, `### Audit & capture boundary`, `### Container capabilities (informational)`, `### Disassembler licensing` (seven H3s under the H2; ordering matters — Network first, Shell second, then sandbox layers, then audit, then informational appendices)
    - Use bullet lists, not paragraphs
    - Keep total length to ~60-90 lines (the old section was 9; this is the right size to explicitly call out the boundary properties STATE.md:196 asks for)
    - Do NOT touch any OTHER section of README.md (no edits to the toolbox table, no edits to Architecture, no edits to env-var table, no edits to Troubleshooting)

    Commit message:
        Replace README Security notes with detailed Security boundaries section
  </action>
  <verify>
    <automated>cd /home/cervon/Code/MARE-MCP-Toolbox && grep -q "^## Security boundaries" README.md && grep -q "### Shell & subprocess boundary" README.md && grep -q "### r2 sandbox boundary" README.md && grep -q "### Audit & capture boundary" README.md && grep -q "cfg.sandbox=true" README.md && grep -q "unshare --net --ipc --uts" README.md && grep -q "Confinement is POSTURE" README.md && ! grep -q "^## Security notes" README.md && echo OK</automated>
  </verify>
  <done>
    `## Security notes` is renamed and expanded into `## Security boundaries` with five-to-seven H3 sub-sections covering the boundary breakdown STATE.md:196 calls out. All factual claims trace to either the existing README body (env-var table, toolbox table), CLAUDE.md (tech-stack constraints), or verified phase-13/phase-7 implementation details visible in r2_sessions.py / shell.py source. Commit message is single-line Sentence-cased imperative.
  </done>
</task>

<task type="auto">
  <name>Task 3: Refactor r2_sessions.py to use module-attribute access for resolve_case_dir (issue #3)</name>
  <files>
    mcp-gateway/src/mcp_gateway/tools/r2_sessions.py
    .planning/milestones/v1.1-phases/14-close-v1.1-gaps/deferred-items.md
  </files>
  <action>
    **Scope decision (already made by planner):** refactor ONLY `r2_sessions.py`. The other 7 tools that import `resolve_case_dir` by name (artifacts.py, workflows.py, shell.py, re_artifacts.py, re_static.py, jobs.py, extract.py) are NOT exercised by the failing tests and refactoring them would expand the diff without closing any test gaps. Add a sibling deferred-items entry for the 7 untouched consumers (see end of this task).

    Edit `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py`:

    1. Replace the existing import on line 47:
           from mcp_gateway.tools.case_dirs import resolve_case_dir
       with the module-attribute form:
           from mcp_gateway.tools import case_dirs as _case_dirs

       Place it in the same `from mcp_gateway.tools` import cluster (lines 47-48 currently). Keep `samples` import as-is (it's also patched in opened_sid but via a different chain — `_samples_mod` resolves to `mcp_gateway.tools.samples` which IS the bound module; only the `resolve_case_dir` name is the breakage point).

    2. Update the 2 call sites that currently call `resolve_case_dir(case_dir)` directly:
       - Line ~167 (inside `open_r2_session`): `resolved_case = Path(resolve_case_dir(case_dir))` → `resolved_case = Path(_case_dirs.resolve_case_dir(case_dir))`
       - Line ~453 (inside `open_r2_session_unsafe`): `resolved_case = Path(resolve_case_dir(case_dir))` → `resolved_case = Path(_case_dirs.resolve_case_dir(case_dir))`

       (The 4 docstring references at lines 146 and 431 are pure prose — DO NOT edit.)

    3. **Coordinate with the existing test that already monkeypatches `r2_sessions.resolve_case_dir` directly** (tests/test_r2_sessions.py:395 and :437):
           monkeypatch.setattr(r2_sessions, "resolve_case_dir", lambda x: str(tmp_path))
       After the refactor, the name `resolve_case_dir` will NO LONGER exist as a module attribute on `r2_sessions`. Two affected tests:
       - `test_unsafe_passes_sandbox_false` (line 385)
       - `test_unsafe_open_warn_log` (line 422)
       Both already patch `r2_sessions.resolve_case_dir` and `r2_sessions.resolve_sample`. Update BOTH tests to patch the new attribute chain:
           monkeypatch.setattr(r2_sessions._case_dirs, "resolve_case_dir", lambda x: str(tmp_path))
       Keep the `r2_sessions.resolve_sample` line unchanged (still bound by name; that's a separate issue out of scope).

       The 12 in-container tests that consume the `opened_sid` fixture (tests/conftest.py:46-89 — wait, conftest.py only defines the require-helpers; `opened_sid` is in test_r2_sessions.py:46-90). Re-check: `opened_sid` patches `_case_dirs_mod.resolve_case_dir` (line 77). After our refactor, r2_sessions.py reads `_case_dirs.resolve_case_dir` from the SAME underlying `mcp_gateway.tools.case_dirs` module object, so the existing patch will Just Work. NO change needed to the `opened_sid` fixture.

    4. After the edit:
       - There is NO behavior change in production: `_case_dirs.resolve_case_dir(case_dir)` and the prior `resolve_case_dir(case_dir)` resolve to the same function object at every non-test call site
       - The Phase 13 contract is preserved (`resolve_case_dir` is still the STATUS_ROOT validator chokepoint; just accessed via module attribute now)
       - The refactor touches Phase 13's case_dir validator contract per deferred-items.md note; flag this in the commit message footer

    Commit message:
        Refactor r2_sessions resolve_case_dir to module-attribute access so test monkeypatch propagates

    After committing the code change, update `.planning/milestones/v1.1-phases/14-close-v1.1-gaps/deferred-items.md`:

    A) In the existing entry "test_r2_sessions.py fixture monkey-patch bypass" (lines 18-25), change the `Status:` line from `open.` to:
        RESOLVED 2026-05-21 in quick task 260521-mhh — switched r2_sessions.py to `from mcp_gateway.tools import case_dirs as _case_dirs` and access via `_case_dirs.resolve_case_dir(...)`. The conftest `opened_sid` monkeypatch on `_case_dirs_mod.resolve_case_dir` now propagates correctly. Sibling tests `test_unsafe_passes_sandbox_false` + `test_unsafe_open_warn_log` updated to patch `r2_sessions._case_dirs.resolve_case_dir`. In-container `pytest tests/test_r2_sessions.py` expected to flip the 12 previously-erroring tests GREEN (verification deferred to next container rebuild).

    B) Add a NEW sibling entry under "## From Plan 14-04" (after the test_skill_md_dual_mode.py entry, before MCP r2_cmd 30s timeout):

        ### Untouched case_dirs consumers (7 tools still bind resolve_case_dir by name)
        
        - **Discovered during:** Quick task 260521-mhh Task 3 (scoping the r2_sessions refactor).
        - **What:** Seven other tool modules import `resolve_case_dir` by name (the same binding shape that broke r2_sessions tests under the conftest monkeypatch): `artifacts.py`, `workflows.py`, `shell.py`, `re_artifacts.py`, `re_static.py`, `jobs.py`, `extract.py`. They are NOT currently exercised by any test that needs to bypass the STATUS_ROOT validator, so the bug is latent — but any future test that wants to monkeypatch `resolve_case_dir` against one of these tools will hit the same wall.
        - **Why deferred:** Pre-emptive refactor without a failing test driving it is out of scope for the v1.1 cleanup batch. The fix is mechanical (same pattern as r2_sessions.py: `from . import case_dirs as _case_dirs` + N call-site renames).
        - **Severity:** low — latent until someone writes a test that monkeypatches `resolve_case_dir` against one of these modules.
        - **Suggested follow-up:** v1.2 cleanup quick task. ~40-60 lines of mechanical diff across 7 files.
        - **Status:** open.

    Amend this Task 3 commit to include the deferred-items.md updates.
  </action>
  <verify>
    <automated>cd /home/cervon/Code/MARE-MCP-Toolbox && python -c "import ast; ast.parse(open('mcp-gateway/src/mcp_gateway/tools/r2_sessions.py').read())" && grep -q "from mcp_gateway.tools import case_dirs as _case_dirs" mcp-gateway/src/mcp_gateway/tools/r2_sessions.py && ! grep -q "^from mcp_gateway.tools.case_dirs import resolve_case_dir" mcp-gateway/src/mcp_gateway/tools/r2_sessions.py && [ "$(grep -c '_case_dirs.resolve_case_dir(case_dir)' mcp-gateway/src/mcp_gateway/tools/r2_sessions.py)" -eq 2 ] && grep -q "r2_sessions._case_dirs" mcp-gateway/tests/test_r2_sessions.py && cd mcp-gateway && python -c "from mcp_gateway.tools import r2_sessions; print('import OK'); assert hasattr(r2_sessions, '_case_dirs'), 'missing _case_dirs attr'; assert not hasattr(r2_sessions, 'resolve_case_dir'), 'stale resolve_case_dir attr lingering'" && grep -q "RESOLVED 2026-05-21 in quick task 260521-mhh — switched r2_sessions.py" .planning/milestones/v1.1-phases/14-close-v1.1-gaps/deferred-items.md && grep -q "Untouched case_dirs consumers" .planning/milestones/v1.1-phases/14-close-v1.1-gaps/deferred-items.md && echo OK</automated>
  </verify>
  <done>
    r2_sessions.py uses module-attribute access for resolve_case_dir; the 2 production call sites and 2 test files (test_unsafe_passes_sandbox_false, test_unsafe_open_warn_log) are updated; the file imports cleanly via `python -c "from mcp_gateway.tools import r2_sessions"`; deferred-items.md has one entry marked RESOLVED and one new sibling entry for the 7 untouched consumers. NOTE in commit footer that this touches the Phase 13 case_dir validator contract (semantically identical, latent test-infra fix). In-container test re-verification (12 GREEN flips) is deferred to next container rebuild and tracked in the deferred-items RESOLVED text.
  </done>
</task>

<task type="auto">
  <name>Task 4: Sweep v1.1-REQUIREMENTS.md traceability table (issue #4) — fill 47 TBD/Pending rows</name>
  <files>.planning/milestones/v1.1-REQUIREMENTS.md</files>
  <action>
    Fill the 47 rows in the traceability table (lines 156-207 of `v1.1-REQUIREMENTS.md`) currently marked `TBD | Pending`. For each REQ-ID, the source-of-truth is the corresponding phase's VERIFICATION.md.

    **Procedure (do NOT hand-enumerate all 47 rows in this plan; do them as a sweep):**

    For each ID family below, open the phase's VERIFICATION.md, grep for the REQ-ID, and discover which plan(s) satisfied it. Then update the row.

    Family → Verification file map:
    - **FOUND-01** → `.planning/milestones/v1.1-phases/05-f-1-image-hash-fix/05-VERIFICATION.md`
    - **FOUND-02 / FOUND-03 / FOUND-04** → `.planning/milestones/v1.1-phases/06-retoolrunner-artifacts-io-foundation/06-VERIFICATION.md`
    - **SHELL-01 / SHELL-02 / STATIC-01..10 / ARTIF-05** → `.planning/milestones/v1.1-phases/07-run-shell-typed-static-wrappers-re-artifacts/07-VERIFICATION.md`
    - **SESS-01 / SESS-02 / SESS-03 / SESS-04 / SESS-05 / SESS-06** → `.planning/milestones/v1.1-phases/08-session-scoped-r2/08-VERIFICATION.md`
    - **JOBS-01..07** → `.planning/milestones/v1.1-phases/09-background-job-system/09-VERIFICATION.md`
    - **EXTR-01..06** → `.planning/milestones/v1.1-phases/10-extraction-tier/10-VERIFICATION.md`
    - **DYN-01..07** → `.planning/milestones/v1.1-phases/11-dynamic-lab-mode-env-gated/11-VERIFICATION.md`
    - **SKILL-01..04** → `.planning/milestones/v1.1-phases/12-orchestrator-skill-update/12-VERIFICATION.md`

    For each REQ-ID:
    1. Open the relevant VERIFICATION.md
    2. Search for the REQ-ID (e.g., `grep -n "FOUND-01" 05-VERIFICATION.md`)
    3. Identify the plan(s) listed as having implemented it. The verification doc typically lists evidence per requirement (line refs, test files, plan IDs). When multiple plans contributed, list them comma-separated in chronological order (precedent from existing rows: `07-01-PLAN.md, 07-05-PLAN.md` for ARTIF-01).
    4. Update the row from:
           | FOUND-01  | Phase 5  | TBD  | Pending  |
       to (example — verify actual plan ID from 05-VERIFICATION.md):
           | FOUND-01  | Phase 5  | 05-01-PLAN.md, 05-02-PLAN.md, 05-03-PLAN.md | [x]      |

    **Column-width formatting:** preserve the table's existing column alignment. The existing rows that ARE filled (e.g., HARDEN-01..07 at lines 208-216) show the canonical formatting — match that. The `Verified` column should be `[x]` (with surrounding spaces to maintain alignment) — copy the exact `[x]      ` padding used in row HARDEN-01.

    **If a VERIFICATION.md does NOT clearly identify the plan** (rare — Phase 5 in particular landed across 3 plans and the requirement may be split):
    - Open the phase directory and look at the plan names: `ls .planning/milestones/v1.1-phases/<phase>/*-PLAN.md`
    - Match the plan whose `must_haves` truths align with the requirement
    - When in doubt, list ALL plans in the phase (defense-in-depth — broader Plan column is acceptable per the existing precedent of ARTIF-01)

    After the sweep, verify the Coverage line at line 218:
        **Coverage:** 61/61 v1.1 requirements mapped (100%). Phase-13 hardening rows ...
    The text is correct; do NOT change it.

    Verification command in `<verify>`:
        grep -c "| TBD  | Pending  |" .planning/milestones/v1.1-REQUIREMENTS.md   # expected: 0
    Note the exact spacing — the `TBD  | Pending  |` token is the marker for unfilled rows. After the sweep, the count must be 0.

    Estimated diff size: 47 rows × ~1-3 chars-changed-per-row + plan IDs (some rows get ~30 chars added). Roughly 50-100 line CHANGES (each row is one line). Total file size delta: +500 to +1500 bytes.

    Commit message:
        Fill 47 Pending traceability rows in v1.1-REQUIREMENTS.md from phase VERIFICATION.md evidence
  </action>
  <verify>
    <automated>cd /home/cervon/Code/MARE-MCP-Toolbox && [ "$(grep -cE '\| TBD +\| Pending +\|' .planning/milestones/v1.1-REQUIREMENTS.md)" -eq 0 ] && grep -q "^| FOUND-01" .planning/milestones/v1.1-REQUIREMENTS.md && grep -q "^| SKILL-04" .planning/milestones/v1.1-REQUIREMENTS.md && [ "$(grep -cE '^\| (FOUND|SHELL|STATIC|ARTIF|SESS|JOBS|EXTR|DYN|SKILL|HARDEN|SESS-CAP|JOBS-CAP)' .planning/milestones/v1.1-REQUIREMENTS.md)" -ge 61 ] && echo OK</automated>
  </verify>
  <done>
    All 47 previously-`TBD | Pending` rows now show a real plan ID (or comma-separated list) in the Plan column and `[x]` in the Verified column. Zero rows match the `TBD  | Pending` pattern. The Coverage line at the end of the table still reads 61/61. The `deferred-items.md` entry "47 already-satisfied v1.1 traceability rows still marked Pending" (lines 6-14) is updated to `Status: RESOLVED 2026-05-21 in quick task 260521-mhh — all 47 rows filled from phase VERIFICATION.md sources; v1.1 traceability now shows 61/61 verified.` and amended into this Task 4 commit.
  </done>
</task>

</tasks>

<verification>
After all 4 tasks land, run on host:

```bash
# Task 1
grep -c "allow_module_level=True" mcp-gateway/tests/test_skill_md_dual_mode.py   # >= 1

# Task 2
grep -c "^## Security boundaries" README.md   # == 1
grep -c "^## Security notes" README.md        # == 0

# Task 3
python -c "from mcp_gateway.tools import r2_sessions; assert hasattr(r2_sessions, '_case_dirs') and not hasattr(r2_sessions, 'resolve_case_dir')"

# Task 4
grep -cE '\| TBD +\| Pending +\|' .planning/milestones/v1.1-REQUIREMENTS.md   # == 0

# Deferred-items hygiene
grep -c "RESOLVED 2026-05-21 in quick task 260521-mhh" .planning/milestones/v1.1-phases/14-close-v1.1-gaps/deferred-items.md   # >= 3
```

In-container verification (next container rebuild, not blocking this quick task):
- `cd /opt/mcp-gateway && pytest tests/test_r2_sessions.py -m "not slow" -x` — expect the 12 previously-erroring tests to flip GREEN (or skip on `_require_r2_or_skip` if r2 missing, but the case_dir validator should no longer fire)
- `cd /opt/mcp-gateway && pytest tests/test_skill_md_dual_mode.py` — expect "skipped (no parent dir contains .planning)" instead of `StopIteration` collection error

</verification>

<success_criteria>
- README.md has a `## Security boundaries` section with sub-headings covering network/auth, shell/subprocess, r2 sandbox, gdb MI3 (dynamic), audit/capture, container caps, licensing
- `from mcp_gateway.tools import r2_sessions` succeeds; `r2_sessions._case_dirs.resolve_case_dir` resolves; the 2 production call sites use the new attribute chain; 2 test files updated to patch the new attribute chain
- v1.1-REQUIREMENTS.md has zero rows matching `TBD | Pending` pattern; 47 rows now show a plan ID + `[x]`
- test_skill_md_dual_mode.py has a module-level pytest.skip guard; AST-parses cleanly; the original `next(p for p in ...parents...)` line is gone
- deferred-items.md has 3 entries flipped to `Status: RESOLVED 2026-05-21 in quick task 260521-mhh ...` and 1 new sibling entry for untouched case_dirs consumers
- 4 atomic commits landed on main (or feature branch — user decides), each with a single-line Sentence-cased imperative message
</success_criteria>

<output>
After all 4 commits, ask the user whether to push to remote (per CLAUDE.md user-preferences workflow: "Proactively ask the user if they want to commit and push whenever a feature is completed").
</output>
