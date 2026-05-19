# Roadmap: MARE-MCP-Toolbox v2

## Milestones

- ✅ **v1.0 Remote MCP Foundation** — Phases 1-4 (shipped 2026-04-27) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- 🚧 **v1.1 Remote RE Tool Expansion** — Phases 5-12 (in progress, scoped 2026-05-12)

## Phases

<details>
<summary>✅ v1.0 Remote MCP Foundation (Phases 1-4) — SHIPPED 2026-04-27</summary>

- [x] Phase 1: IDA Pro Backend (3/3 plans)
- [x] Phase 2: MCP Gateway (5/5 plans)
- [x] Phase 3: Container Integration (1/1 plan)
- [x] Phase 4: External Client Integration (7/7 plans)

Full details: [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)

</details>

### v1.1 Remote RE Tool Expansion

- [ ] **Phase 5: F-1 Image-Hash Fix** — Extend `run_docker.sh` content-hash to include `mcp-gateway/` so gateway-package edits trigger image rebuild
- [ ] **Phase 6: ReToolRunner + artifacts_io Foundation** — Single argv-only subprocess execution path with cwd-confinement, process-group cleanup, output capture, and the canonical `confine_to` helper
- [ ] **Phase 7: run_shell + Typed Static Wrappers + re_artifacts** — Constrained bash one-liner, 12 typed static RE tool wrappers, expanded case-dir artifact tree, and artifact control helpers
- [ ] **Phase 8: Session-Scoped r2** — Persistent r2 analysis sessions with idle reaper, session cap, and dangerous-command refusal
- [ ] **Phase 9: Background Job System** — `start_tool_job`/`get_tool_job`/`cancel_tool_job` for long-running tools that exceed the 60 s MCP request cap
- [x] **Phase 10: Extraction Tier** — `run_unblob`, `run_binwalk`, UPX wrappers, child-file enumeration, and `promote_extracted_sample` (completed 2026-05-19)
- [ ] **Phase 11: Dynamic Lab Mode (env-gated)** — `run_strace`/`run_ltrace`/`run_qemu_user` + session-scoped gdb, default-off via `MCP_GATEWAY_DYNAMIC_TOOLS=1`
- [ ] **Phase 12: Orchestrator Skill Update** — Update `malware-analysis-orchestrator` to encode v1.1 tool surface, fix backend priority drift, and preserve dual-mode operation

## Phase Details

### Phase 5: F-1 Image-Hash Fix
**Goal**: Agent edits to `mcp-gateway/` reliably reach the running container without manual rebuild gymnastics
**Depends on**: Nothing (gates all subsequent v1.1 phases)
**Requirements**: FOUND-01
**Success Criteria** (what must be TRUE):
  1. An analyst editing any file under `mcp-gateway/src/` triggers an image rebuild on the next `./run_docker.sh` invocation
  2. An analyst editing `mcp-gateway/pyproject.toml` triggers an image rebuild on the next `./run_docker.sh` invocation
  3. Edits to ignored paths (`__pycache__`, `.venv`, `*.egg-info`, `.pytest_cache`) do NOT trigger spurious rebuilds
  4. A regression test asserts `DOCKERFILE_SHA` changes when `mcp-gateway/src/x.py` is touched
**Plans**: 3 plans
  - [x] 05-01-PLAN.md — Add LC_ALL=C to both sort invocations in run_docker.sh image-hash subshell (D-02)
  - [x] 05-02-PLAN.md — Extract hash to scripts/compute_image_hash.sh + patch run_docker.sh call site (D-05, D-06)
  - [x] 05-03-PLAN.md — Add hermetic pytest regression test mcp-gateway/tests/test_image_hash.py (D-07..D-11)

### Phase 6: ReToolRunner + artifacts_io Foundation
**Goal**: One auditable, OOM-safe execution path exists for every v1.1 subprocess invocation, and every path-accepting tool can reject traversal uniformly
**Depends on**: Phase 5
**Requirements**: FOUND-02, FOUND-03, FOUND-04
**Success Criteria** (what must be TRUE):
  1. Every v1.1 subprocess invocation can route through `ReToolRunner` with argv-only execution, cwd-confined to a resolved `case_dir`, hard timeout, and process-group SIGKILL on timeout or cancel
  2. Runner returns a structured JSON shape (`exit_code`, `stdout_head`, `stderr_head`, `log_path`, `timed_out`, byte/truncation counts) that wrappers layer over
  3. Full stdout/stderr of every runner-driven invocation is auto-captured to `case_dir/tool-logs/<timestamp>-<slug>.txt` while only a head-truncated preview returns over MCP
  4. A 100 MB-of-`/dev/urandom` stdout test completes in bounded time with bounded RSS (no PIPE deadlock, no OOM)
  5. A canonical `confine_to(case_dir, path)` helper rejects path traversal and is importable from every v1.1 tool module
**Plans**: 3 plans
  - [x] 06-01-PLAN.md — Wave-0 test scaffolding: register `slow` pytest marker + create RED test stubs (`test_runner.py`, `test_artifacts_io.py`) covering SC-1..SC-5, D-08, D-09, D-15, D-16
  - [x] 06-02-PLAN.md — Wave-1 leaf module `artifacts_io.py`: `confine_to`, `ensure_subdir`, `tool_log_path`, `EXPANDED_CASE_SUBDIRS` (D-06, D-09, D-11..D-16) — turns 16 artifacts_io tests GREEN
  - [x] 06-03-PLAN.md — Wave-2 chokepoint `runner.py`: `ReToolRunner` class + `run_tool` convenience + 4 env-var module constants (D-01..D-04, D-07, D-08, D-10, D-17, D-18) — turns 10 runner tests GREEN

### Phase 7: run_shell + Typed Static Wrappers + re_artifacts
**Goal**: Remote agents can invoke the full Kali static-analysis surface — ad-hoc bash one-liners plus 12 typed wrappers with structured output — into a confined, captured case-dir artifact tree
**Depends on**: Phase 6
**Requirements**: SHELL-01, SHELL-02, SHELL-03, STATIC-01, STATIC-02, STATIC-03, STATIC-04, STATIC-05, STATIC-06, STATIC-07, STATIC-08, STATIC-09, STATIC-10, ARTIF-01, ARTIF-02, ARTIF-03, ARTIF-04, ARTIF-05
**Success Criteria** (what must be TRUE):
  1. An agent can call `run_shell(case_dir, cmd)` with a bash one-liner; the shell executes as a dedicated non-root `mare-shell` UID with cwd pinned to the case directory, hard timeout, output cap, and auto-capture to `tool-logs/`
  2. The `MCP_GATEWAY_TOKEN`, API keys, and AWS-style credentials are NOT reachable from inside `run_shell`, and the docstring states explicitly that confinement is posture (cwd + UID + timeout + capture), not OS-level isolation
  3. An agent can identify samples (`run_file`, `run_die`), read bounded hex windows (`run_xxd`), inspect ELF/PE metadata (`run_readelf`, `run_objdump`, `run_nm`, `run_rabin2`), disassemble byte ranges with typed JSON (`run_capstone_disasm`), search ROP gadgets with typed JSON (`run_ropper`), and query case artifacts with jq/yq — each returning a head-truncated preview plus a captured log
  4. Case directories transparently grow `tool-logs/`, `extracted/`, `hex/`, `rop/`, `dynamic/`, `qemu/`, `disassembly/`, `decompilation/`, `xrefs/` subdirs on first write (lazy creation, no always-empty dirs)
  5. An agent can write, append, enumerate, and tree-list artifacts via `write_artifact`, `append_artifact`, `list_artifacts`, `get_artifact_tree`, and range-read multi-megabyte logs via `get_tool_log` without blowing the MCP response cap
  6. MCP Resources expose `mare://cases/<case>/tool-logs/<file>` for every captured log, and a tool-name collision between STATIC wrappers and backend-pass-through tools hard-fails at gateway startup
**Plans**: 8 plans
  - [x] 07-01-PLAN.md — Wave 0: Dockerfile + pyproject foundation, 7 fixtures, 6 RED-stub test files (D-01, D-04, D-07, D-20, D-34)
  - [x] 07-02-PLAN.md — Wave 1A: artifacts_io.ensure_mare_shell_access (D-05, D-06)
  - [x] 07-03-PLAN.md — Wave 1B: tools/collision_check.py + SystemExit(78) on overlap (D-11..D-15)
  - [x] 07-04-PLAN.md — Wave 1C: tools/resources.py depth-2 walk over EXPANDED_CASE_SUBDIRS (D-26, D-27)
  - [x] 07-05-PLAN.md — Wave 2A: tools/re_artifacts.py — write/append/list/tree/get_tool_log (D-21..D-25)
  - [x] 07-06-PLAN.md — Wave 2B: tools/re_static.py — 11 typed wrappers (D-18, D-19, D-30..D-32)
  - [x] 07-07-PLAN.md — Wave 2C: tools/shell.py — run_shell with setpriv + env whitelist (D-01, D-02, D-09, D-28, D-29)
  - [x] 07-08-PLAN.md — Wave 3: integrate tools/__init__.py + app.py lifespan + backend_passthrough comment + D-35 slow rerun (D-11, D-14, D-16)
**UI hint**: no

### Phase 8: Session-Scoped r2
**Goal**: Remote agents can run iterative r2-driven RE — analysis state (`aaa`, flags, comments) persists across MCP calls — without re-analyzing on every invocation
**Depends on**: Phase 6, Phase 7
**Requirements**: SESS-01, SESS-02, SESS-03, SESS-04, SESS-05, SESS-06
**Success Criteria** (what must be TRUE):
  1. An agent can call `open_r2_session(case_dir, sample, init_commands)`, receive an opaque session_id, and reuse r2's analysis state across subsequent `r2_cmd` calls
  2. An agent can execute arbitrary r2 commands via `r2_cmd(session_id, cmd, format)` with head-truncated output + full output captured, close sessions with `close_r2_session`, and enumerate active sessions with `list_sessions`
  3. r2 sessions are auto-reaped after configurable idle (default 30 min); a session cap (default 8) is enforced; sessions surviving gateway shutdown are killed (no zombie r2 processes)
  4. Dangerous shell-escape commands (`#!`, `R!`, `!`) are refused at the wrapper layer, and every session opens with `scr.interactive=false; scr.color=0`
  5. The shared-across-bearer-token-clients limitation is documented in `open_r2_session` and `r2_cmd` docstrings (per-`Mcp-Session-Id` keying deferred to v1.2)
**Plans**: 5 plans
  - [x] 08-01-PLAN.md — Wave 0: RED-stub test scaffolding (test_sessions.py + test_r2_sessions.py + _require_r2_or_skip helper + augment EXPANDED_CASE_SUBDIRS + resource-walker tests) (D-08, D-09, D-26, D-27, D-29)
  - [x] 08-02-PLAN.md — Wave 2: sessions.py primitive (R2Session dataclass, SessionRegistry async-context-manager, reaper loop, _DANGEROUS_R2_CMD_RE, 5 env-var module constants) (D-01..D-04, D-06, D-08, D-09, D-13..D-18)
  - [x] 08-03-PLAN.md — Wave 2: tools/r2_sessions.py MCP surface (open_r2_session, r2_cmd, close_r2_session, list_sessions + register pattern + SESS-05 disclaimer in docstrings) (D-05, D-06, D-10..D-13, D-19..D-23)
  - [x] 08-04-PLAN.md — Wave 3: integration (EXPANDED_CASE_SUBDIRS extension, SESSION_REGISTRY slot in session_state, tools/__init__ register wiring, app.py::lifespan SessionRegistry block in both branches) (D-05, D-07, D-24, D-25, D-26)
  - [x] 08-05-PLAN.md — Wave 4: end-to-end validation (flip RED stubs to GREEN with full behavioural bodies for SC-1..SC-5 + Pitfall 6 + Pitfall 18; update 08-VALIDATION.md nyquist_compliant: true) (D-27, D-28)

### Phase 9: Background Job System
**Goal**: Remote agents can launch long-running RE tools (capa, unblob, Ghidra/IDA auto, strace, qemu) and poll for completion without hitting the 60 s MCP request cap
**Depends on**: Phase 6
**Requirements**: JOBS-01, JOBS-02, JOBS-03, JOBS-04, JOBS-05, JOBS-06, JOBS-07
**Success Criteria** (what must be TRUE):
  1. An agent can call `start_tool_job(tool, args)`, receive an opaque job_id, and the job runs through `ReToolRunner` with the same safety properties (argv-only, cwd-confine, process-group, capture)
  2. An agent can poll a job via `get_tool_job(job_id)` returning status, head-tail of stdout/stderr, exit code if done, and the log artifact path; cancel via `cancel_tool_job` (SIGTERM then SIGKILL); enumerate via `list_tool_jobs(state)`
  3. Each job's log artifact is capped at `MCP_GATEWAY_MAX_JOB_LOG_MB` (default 256 MB); over-cap jobs are killed and marked `status=killed_log_cap`; completed jobs are LRU-cleaned to bound memory
  4. Client disconnect or request cancellation propagates correctly — subprocess is dead within 200 ms (asserted by test) via `asyncio.shield(proc.wait())` and `killpg(SIGKILL)`
  5. Long-running tools can report progress via MCP `Context.report_progress(progress, total, message)` where the underlying tool produces progress signals (e.g., unblob percent-complete)
  6. Gateway restart cancels all in-flight jobs (in-memory registry only), and this behavior is documented in tool docstrings
**Plans**: 5 plans (4 original + 1 gap-closure)
  - [x] 09-01-PLAN.md — Wave 1: jobs.py primitive (BackgroundJobRegistry + Job/JobToolSpec/JobStatus + 4 D-15 error types + JOB_TOOL_REGISTRY with _sleep_probe/_log_burst_probe/capa specs + 10 env-var constants + chunked-read drain + counter log-cap + FIFO eviction + .json snapshot) AND a surgical 2-line proc_callback kwarg extension to runner.py (D-01..D-14, D-22, D-23, Q1, Q2, Q4)
  - [x] 09-02-PLAN.md — Wave 2: tools/jobs.py MCP surface (start_tool_job / get_tool_job / cancel_tool_job / list_tool_jobs with D-26 disclaimer splice, D-15 four error shapes, D-16 Tier-2 ctx.report_progress with session-id dedup, D-19 25-key snapshot, D-20 _specs magic + Q5 include_internal filter)
  - [x] 09-03-PLAN.md — Wave 2: lifespan wiring (session_state.JOB_REGISTRY slot, app.py both branches nest BackgroundJobRegistry INSIDE SessionRegistry per D-25 LIFO unwind, tools/__init__ import + register call)
  - [x] 09-04-PLAN.md — Wave 3: Nyquist test suite (18 test files under tests/jobs/ covering SC-1..SC-6 + D-15/D-19/D-20/D-21/D-26 + JOBS-01..JOBS-07; SC-4 200 ms reaping; SC-3 MARE_JOB_KILLED_LOG_CAP marker; capa slow integration gated by capa availability) + test_tool_list.py bumped 43 → 47 + VALIDATION.md flipped nyquist_compliant: true
  - [x] 09-05-PLAN.md — Wave 4 (gap closure): close D-15 contract hole on capa tool path (09-VERIFICATION.md truth #7 / CR-01 + CR-02) — add required-field enforcement to _validate_kwargs + broaden start_tool_job except clause around registry.submit() to catch (ValueError, FileNotFoundError, KeyError, OSError) + 2 regression tests in test_errors.py

### Phase 10: Extraction Tier
**Goal**: Remote agents can carve embedded files out of firmware/packed samples and promote children into first-class cases for recursive triage
**Depends on**: Phase 6, Phase 7, Phase 9
**Requirements**: EXTR-01, EXTR-02, EXTR-03, EXTR-04, EXTR-05, EXTR-06
**Success Criteria** (what must be TRUE):
  1. An agent can run binwalk in signatures, entropy, or extract modes via `run_binwalk(case_dir, sample, mode)`, with extraction output confined to `case_dir/extracted/binwalk-<ts>/`
  2. An agent can run unblob with structured `--report` JSON via `run_unblob(case_dir, sample)`, with output confined to `case_dir/extracted/unblob-<ts>/` and the long-running case dispatched as a background job
  3. An agent can test/list/unpack UPX-packed samples via `run_upx_test`, `run_upx_list`, `run_upx_unpack` with output under `case_dir/extracted/upx-<ts>/`
  4. An agent can enumerate previously-extracted files via `list_extracted_files(case_dir)` regardless of which engine produced them
  5. An agent can promote an extracted child to a new case via `promote_extracted_sample(parent_case_dir, child_path)`, which re-uploads with sha256 content-addressing, initializes a new case directory, and returns the new case_dir
  6. Extraction tools enforce symlink quarantine (replaced with `.symlink-target.txt`), archive-bomb cap (`MCP_GATEWAY_MAX_EXTRACT_MB` default 4 GB), and atomic promotion (sha256 recomputed)
**Plans**: 5 plans
  - [x] 10-01-PLAN.md — Wave 0: Dockerfile binwalk3 migration + 13-file RED-stub test scaffold + in-container probe script (D-01, D-24, A1/A2/A3 resolution)
  - [x] 10-02-PLAN.md — Wave 1 primitive: extraction.py core (env constants, extraction_dir, sidecar I/O, quarantine_symlinks, write_upload, two pure argv builders, two JobToolSpec registrations) (D-07..D-12, D-15, D-16, D-18, D-19)
  - [x] 10-03-PLAN.md — Wave 1 monitor: start_extract_monitor + _du_sb + GC-safe task retention + post-terminal symlink quarantine hook (D-17)
  - [x] 10-04-PLAN.md — Wave 2 surface: tools/extract.py — 7 @mcp.tool() handlers + D-23 disclaimer splices + 6 D-22 error shapes + register(mcp) (D-01..D-06, D-22, D-23)
  - [x] 10-05-PLAN.md — Wave 3 integration: tools/__init__.py wiring + EXPECTED_TOOLS 47→54 + range bump + Wave 0 RED→GREEN flip on all 13 test files + VALIDATION.md sign-off (D-20)

### Phase 11: Dynamic Lab Mode (env-gated)
**Goal**: Operators can opt into a first-class dynamic-analysis surface (strace, ltrace, qemu-user, gdb sessions) via `./run_docker.sh --dynamic`, default-off so the standard container shape is unchanged
**Depends on**: Phase 6, Phase 7, Phase 8, Phase 9
**Requirements**: DYN-01, DYN-02, DYN-03, DYN-04, DYN-05, DYN-06, DYN-07
**Success Criteria** (what must be TRUE):
  1. Dynamic tools (`run_strace`, `run_ltrace`, `run_qemu_user`, `open_gdb_session`, `gdb_exec`, `close_gdb_session`, `get_dynamic_capabilities`) are registered if and only if `MCP_GATEWAY_DYNAMIC_TOOLS=1` at startup; `tools/list` does not advertise them when off
  2. An operator can run `./run_docker.sh --dynamic` to enable dynamic mode end-to-end (env var set, `CURRENT_STATE.json` marks the mode, dynamic-mode defaults applied including no-net and `dynamic/` cwd)
  3. An agent can run `run_strace`, `run_ltrace`, and `run_qemu_user` with allowlisted argv profiles, output captured to `case_dir/dynamic/` or `case_dir/qemu/`, with default no-net via per-call `unshare --net`
  4. An agent can drive an interactive gdb-MI3 session (`open_gdb_session` → `gdb_exec` → `close_gdb_session`) restricted to an allowlist of MI prefixes (no `python <code>` sandbox escape); session plumbing reuses the Phase 8 registry
  5. `get_dynamic_capabilities()` probes and reports `ptrace_scope`, `binfmt_misc` status, available qemu architectures, and netns feasibility at gateway startup so agents and operators detect missing capabilities before sample execution
  6. Long-running dynamic tools dispatch through the JOBS system, follow-fork process groups are reaped via `/proc/<runner_pid>/task/*/children` scanning, and samples must be resolved via sha256 from `uploads/` or an existing `case_dir`
**Plans**: TBD

### Phase 12: Orchestrator Skill Update
**Goal**: The `malware-analysis-orchestrator` skill encodes the v1.1 tool surface, fixes stale v1.0 assumptions, and preserves dual-mode operation (gateway + local-script fallback)
**Depends on**: Phase 5, Phase 6, Phase 7, Phase 8, Phase 9, Phase 10, Phase 11
**Requirements**: SKILL-01, SKILL-02, SKILL-03, SKILL-04
**Success Criteria** (what must be TRUE):
  1. The skill at `workspace/.claude/skills/malware-analysis-orchestrator/` reflects backend priority `IDA > BN > Ghidra` (correcting v1.0 documentation drift)
  2. The skill encodes the deep RE checklist mapping findings → tools (W-1 packed-binary triage, W-2 ELF deep-dive, W-3 PE deep-dive, W-4 ROP hunt, W-5 dynamic API trace, W-6 firmware unpack, W-7 cross-arch IoT triage), each mapped to v1.1 typed wrappers with `run_shell` fallbacks
  3. Every skill step preserves dual-mode operation — has an MCP path (gateway tools) and a local-script path (`scripts/...`) with a decision rule based on `tools/list` content; a regression test snapshots SKILL.md and fails CI on unconditional `mcp__mare__*` references with no fallback
  4. The skill marks dynamic mode status in `CURRENT_STATE.json` so subsequent analysis steps know whether dynamic tools are available; dynamic-mode-only steps are skipped (with a noted reason) when the mode is off
**Plans**: TBD

## Progress

| Phase                          | Milestone | Plans | Status      | Completed  |
|--------------------------------|-----------|-------|-------------|------------|
| 1. IDA Pro Backend             | v1.0      | 3/3   | Complete    | 2026-04-27 |
| 2. MCP Gateway                 | v1.0      | 5/5   | Complete    | 2026-04-27 |
| 3. Container Integration       | v1.0      | 1/1   | Complete    | 2026-04-27 |
| 4. External Client Integration | v1.0      | 7/7   | Complete    | 2026-04-27 |
| 5. F-1 Image-Hash Fix          | v1.1      | 0/3   | Not started | -          |
| 6. ReToolRunner Foundation     | v1.1      | 0/3   | Not started | -          |
| 7. run_shell + Static Wrappers | v1.1      | 0/?   | Not started | -          |
| 8. Session-Scoped r2           | v1.1      | 0/5   | Not started | -          |
| 9. Background Job System       | v1.1      | 0/?   | Not started | -          |
| 10. Extraction Tier            | v1.1      | 5/5 | Complete   | 2026-05-19 |
| 11. Dynamic Lab Mode           | v1.1      | 0/?   | Not started | -          |
| 12. Orchestrator Skill Update  | v1.1      | 0/?   | Not started | -          |
