---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Remote RE Tool Expansion
status: verifying
stopped_at: Phase 12 context gathered
last_updated: "2026-05-20T02:07:33.938Z"
last_activity: 2026-05-20
progress:
  total_phases: 8
  completed_phases: 7
  total_plans: 35
  completed_plans: 35
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-12 — v1.1 Remote RE Tool Expansion scoped)

**Core value:** Automated malware triage and deep analysis via AI agents with full access to professional RE tooling — accessible both from inside the container and from external MCP clients.
**Current focus:** Phase 11 — dynamic-lab-mode-env-gated

## Current Position

Milestone: v1.1 Remote RE Tool Expansion
Phase: 12
Plan: Not started
Status: Phase complete — ready for verification
Last activity: 2026-05-20

Progress: [          ] 0% (0/8 phases complete)

## Performance Metrics

**Velocity:**

- Total plans completed (v1.0): 16
- v1.1 plans completed: 0

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

**v1.1 design decisions (newly added):**

- Expose a constrained `run_shell` over MCP — safety from cwd-confinement + timeout + output cap + auto-capture, not argv allowlisting
- Typed wrappers exist for discoverability and structured output (capstone JSON, ropper bounds, r2/gdb sessions), not as the exclusive surface
- Session-scoped r2 and gdb — iterative analyst workflow needs shared analysis state
- Dynamic mode env-gated default-off (`MCP_GATEWAY_DYNAMIC_TOOLS=1`, surfaced via `./run_docker.sh --dynamic`)
- Composite `investigate_*` MCP tools dropped — orchestrator skill is the composer

**v1.1 roadmap decisions (2026-05-12):**

- Adopted research-consensus 8-phase structure (Phases 5-12) verbatim — all 4 research streams converged on this ordering
- Phase 5 (F-1) lands first to unblock every subsequent gateway edit (UAT failure mode 2026-05-11)
- `ReToolRunner` (Phase 6) precedes all consumers; chokepoint primitive validated under wrappers (Phase 7) before sessions/jobs build on it
- Sessions (Phase 8) before Jobs (Phase 9) — same lifespan-registry pattern, r2 validates plumbing at lower complexity than gdb
- Extraction (Phase 10) depends on Jobs (unblob on multi-GB firmware exceeds 60 s MCP cap)
- Dynamic Mode (Phase 11) last among code phases — reuses session plumbing for gdb and job system for long traces
- Orchestrator Skill Update (Phase 12) very last — references all primitives

**Carryover from v1.0:**

- F-1: `run_docker.sh:209-222` `DOCKERFILE_SHA` does not include `mcp-gateway/src/` — gateway-package edits never trigger image rebuild. Now scoped as Phase 5 (FOUND-01).
- [Phase 05-f-1-image-hash-fix]: Inline LC_ALL=C prefix per sort invocation in run_docker.sh image-hash subshell (vs. global export) — keeps locale intent visible at call site
- [Phase 05-f-1-image-hash-fix]: Extracted run_docker.sh:212-229 inline image-hash subshell to scripts/compute_image_hash.sh; refactor preserves byte-identical output and keeps DOCKERFILE_SHA/SHORT_SHA/HASH_IMAGE in run_docker.sh scope (D-01/D-06).
- [Phase 05-f-1-image-hash-fix]: Locked FOUND-01 invariant with hermetic 11-node pytest at mcp-gateway/tests/test_image_hash.py — single-fixture-per-test pattern; explicit env={PATH,HOME} dict to subprocess (no env=os.environ); test skeleton copied verbatim from 05-RESEARCH.md to preserve VALIDATION.md's row-by-row contract.
- [Phase 06-retoolrunner-artifacts-io-foundation]: Wave-0 RED-state test scaffolding pattern -- name failing test functions referencing not-yet-existing modules; Wave 1/2 turn them GREEN. Enforces Nyquist: every <verify> in downstream plans references an existing test.
- [Phase 06-retoolrunner-artifacts-io-foundation]: Threat-register-as-tests -- every <threat_model> row with disposition=mitigate (T-6-01/02/03/06/07) has at least one named test function rather than being prose-only mitigations.
- [Phase 06-retoolrunner-artifacts-io-foundation]: Leaf-module discipline (D-07) enforced for artifacts_io.py -- stdlib-only imports keep the module safe to import from any Phase 7+ tool wrapper without cycles
- [Phase 06-retoolrunner-artifacts-io-foundation]: Paste-ready code from 06-02-PLAN.md <action> block used verbatim -- TDD GREEN-phase executed with zero deviation; all 16 RED tests flipped GREEN on first run
- [Phase 06-retoolrunner-artifacts-io-foundation]: ReToolRunner spawned via asyncio.create_subprocess_exec with start_new_session=True; on TimeoutError swallows + returns {timed_out=True, exit_code=-9}; on CancelledError runs killpg+shielded wait then re-raises (D-04, D-17, Pitfall 18)
- [Phase 06-retoolrunner-artifacts-io-foundation]: Stdout/stderr drained concurrently via asyncio.gather of two _drain coros with head_cap_bytes + raw file sink; on timeout, drain results become zero placeholders but on-disk log preserves what flushed (FOUND-02 SC-4, Pitfall 1)
- [Phase 06-retoolrunner-artifacts-io-foundation]: D-03 12-key return shape locked: exit_code, timed_out, duration_s, stdout_head, stdout_truncated, stdout_bytes_total, stderr_head, stderr_truncated, stderr_bytes_total, log_path, argv, slug -- exact order, never renamed by Phase 7+ consumers
- [Phase 06-retoolrunner-artifacts-io-foundation]: Grep-the-source chokepoint tests catch BOTH code AND prose violations; future plans must phrase 'never shell-invocation kwarg' (not 'never shell=True') in docstrings to avoid spurious test failures from copy-pasted action blocks
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Wave 0 fixture binaries built via documented fallback paths (gcc inline asm for ELF; hand-crafted 408-byte PE stub; gcc -c for stripped.o) because executor host lacked nasm/mingw-w64/setfacl; all pass magic-byte + size acceptance; README documents both canonical and fallback build paths.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Wave 0 RED-stub discipline locked in for Phase 7: 52 tests collected cleanly, each imports the not-yet-existing Phase 7 module at function top so collection passes but execution ImportErrors -- pytest.skip is forbidden; failure-to-import IS the RED state Wave 1/2 will flip to GREEN.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Dockerfile permission/ACL revocations split into build-time best-effort + entrypoint re-apply (overlayfs xattr-drop mitigation per Pitfall 3 / moby#40553); token-file chmod 0400 placed AFTER the MCP_GATEWAY_ENABLED block with a 0.2s x 5 retry loop since the bearer token is generated only when the gateway starts.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-02: ensure_mare_shell_access LEAF extension landed via zero-deviation TDD (RED commit + GREEN commit, 80s total); shutil+subprocess added to artifacts_io.py stdlib-only import block (LEAF discipline preserved, grep 'from mcp_gateway' = 0); fail-loud RuntimeError on missing setfacl OR nonzero exit; mock-based unit tests cover contract on hosts without setfacl (executor host case).
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-03: collision_check.py module (~67 LoC) delivered with verbatim plan code; Wave 0 RED-stub test fixtures retargeted from Phase 7 Wave 2 names (run_xxd/run_file/run_die, not yet registered) to v1.0 gateway-native names (init_case/get_artifact/decompile) so tests are self-contained against Wave 1 surface — collision-detection mechanism unchanged, more faithful to D-12 scope.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-04: tools/resources.py depth-2 walk delivered with paste-ready plan code + one deviation: added _status_root() helper that reads MCP_GATEWAY_STATUS_DIR dynamically per call (the module-level STATUS_ROOT import is preserved as no-env fallback). This honours the existing 'dynamic' listing docstring promise and unblocks test_resources_no_depth_3 + test_resources_skip_hidden which would otherwise see stale STATUS_ROOT when test_resources_unit.py is collected first.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-05: re_artifacts.py (335 LoC) delivered with 3 Rule-3 deviations: (a) module-level coroutines over nested-in-register so tests can import directly; (b) skip-on-no-setfacl helper for 6 ACL-exercising tests (host lacks setfacl); (c) autouse samples.STATUS_ROOT monkeypatch fixture (binding-at-import issue). 9 pass + 6 skip on host; container will flip all 6 to PASS.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-06: tools/re_static.py (491 LoC) delivered with 3 Rule-3 deviations: (a) module-level coroutines + register-wrapper pattern (matches Plan 07-05) so tests import wrappers directly; (b) autouse _sync_samples_roots fixture monkeypatches samples.STATUS_ROOT + EXAMPLES_ROOT + ALLOWED_PREFIXES per test; (c) _require_tool_or_skip guards for die/rabin2/jq/yq (host-missing). 10 pass + 4 skip on host; container will flip all 4 to PASS.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-07: tools/shell.py (211 LoC) delivered with 6 Rule-3 deviations: (a) module-level run_shell + register-wraps pattern (matches 07-05/07-06); (b) autouse samples.STATUS_ROOT monkeypatch fixture; (c) 8 spawning tests gated by _require_setfacl_or_skip; (d) test_mare_shell_user_exists fail->skip (host lacks user, Dockerfile creates it); (e) @mcp.tool() decorator -> mcp.tool()(run_shell) call; (f) assert -> RuntimeError in _build_shell_env drift check. 5 pass + 9 skip + 1 slow-deselect on host.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-08: Wave 3 integration — register_all_tools learns shell/re_static/re_artifacts (D-16); collision_check imported but not registered; assert_no_collisions called on BOTH lifespan paths AFTER backend connect AND BEFORE serving (D-11 ordering, Pitfall 7); backend_passthrough docstring rewritten to reflect D-14 (hard-fail REVERSES v1.0 backend-wins); GW-02 tool-count invariant bumped 15-25 -> 35-50 in test_tool_list.py with explicit D-16 rationale (Rule 1 deviation); final surface = 39 tools (22 v1.0 + 17 Phase 7).
- [Phase 08-session-scoped-r2]: Plan 01 — Wave 0 RED-stub test scaffolding delivered verbatim from plan; 21 new tests + 1 augmented + 1 new on existing file; collection clean, execution ImportErrors as designed. _require_r2_or_skip lives in shared conftest.
- [Phase 08-session-scoped-r2]: D-29 catalog regression intentionally double-covered (test_sessions.py + test_artifacts_io.py) — same invariant from two angles per VALIDATION.md test-file note.
- [Phase 08-session-scoped-r2]: Plan 02: sessions.py primitive landed via zero-deviation TDD GREEN flip — paste-ready Plan 02 code block worked on first import + first test run; 4 of 8 RED stubs in test_sessions.py turned GREEN (regex present, regex matrix, env-var sanity, dataclass fields)
- [Phase 08-session-scoped-r2]: Inline ANSI-strip + UTF-8-safe truncate helpers in sessions.py (Claude's Discretion) rather than widening runner.py's _ANSI_ESCAPE visibility — keeps both modules self-contained; runner.py untouched
- [Phase 08-session-scoped-r2]: Parallel shutdown sweep in SessionRegistry.__aexit__ via asyncio.gather(close(reason='shutdown')) over open sessions (Claude's Discretion D-16 recommendation) — shutdown duration bounded by slowest killpg, not their sum
- [Phase 08-session-scoped-r2]: Plan 03: tools/r2_sessions.py MCP surface landed via 1-deviation TDD GREEN — Rule 1 fix for docstring-concat idiom that yielded __doc__=None (Python parser only attaches pure string literals); switched open/r2_cmd to the placeholder+splice pattern already used by close/list
- [Phase 08-session-scoped-r2]: Plan 03: contract-correctness preserved — resolve_sample consumed as str + explicit hashlib.sha256, env-var constants accessed via sessions.<NAME> (not bind-by-value), zero edits leaked into tools/__init__.py / session_state.py / app.py (those land in Plan 04)
- [Phase 08-session-scoped-r2]: Plan 04: lifespan SessionRegistry wired in both branches with D-14 single-source-of-truth — app.py imports MAX_SESSIONS/SESSION_IDLE_S/REAPER_INTERVAL_S from sessions module (validated at import); negative grep proves 0 os.environ re-reads in app.py
- [Phase 08-session-scoped-r2]: Plan 04: Rule-1 fixed pre-existing Plan-01 walker test (case 'alpha' did not match CASE_NAME_RE = ^\d{3}-.+; renamed to '304-r2sess'); Rule-2 added 4 r2-session tool names to EXPECTED_TOOLS (Phase 7 39 -> Phase 8 43 tools, still within 35-50 range)
- [Phase 08-session-scoped-r2]: Plan 05: filled every Plan 01 RED stub to GREEN behavioural body; opened_sid pytest-asyncio fixture is single source of open-session boilerplate; VALIDATION.md nyquist_compliant=true + wave_0_complete=true.
- [Phase 09-background-job-system]: Plan 01: Q4 surgical extension applied -- ReToolRunner.run gains keyword-only proc_callback kwarg, fires once with live Process after spawn; D-03 12-key contract preserved when None (default)
- [Phase 09-background-job-system]: Plan 01: jobs.py primitive layer landed verbatim (752 LoC) -- BackgroundJobRegistry async-context-manager + 4 D-15 error types + 3 ship-with specs (_sleep_probe / _log_burst_probe / capa); D-24 invariant (no fastmcp import) and Q3 invariant (no jsonschema dep) verified by negative grep
- [Phase 09-background-job-system]: Plan 01: capa spec progress_parser=None per Q1 verification (rich Console.status spinner emits no parseable stderr lines); _spawn_and_drive INLINES spawn+drain rather than wrapping ReToolRunner so Phase 9 can layer per-role tail ring buffers (Q1) and per-line progress dispatch (D-16); JOBS-01 safety preserved at spec level
- [Phase 09-background-job-system]: Plan 02: D-26 disclaimer spliced into all 4 tool docstrings via post-definition .replace() (Phase 8 D-23 mechanism); D-16 Tier-2 ctx.report_progress dedup keyed by ctx.session_id with '_anon_' fallback for programmatic callers
- [Phase 09-background-job-system]: Plan 02: tools/jobs.py uses module-attribute import 'from mcp_gateway import jobs' (NOT 'from mcp_gateway.jobs import NAME') so importlib.reload(jobs) propagates through tests -- matches Phase 8 r2_sessions convention
- [Phase 09-background-job-system]: Plan 02: All 4 D-15 error paths route through .to_dict() (7 call sites covering 4 shapes); tools NEVER raise out of MCP boundary -- Phase 6 D-04 / Phase 8 D-18 contract preserved with defensive type-checks on timeout + limit args (Rule 1/2 deviations)
- [Phase 09-background-job-system]: Plan 03: D-25 LIFO nesting applied — BackgroundJobRegistry nests INSIDE SessionRegistry in BOTH lifespan branches; shutdown unwinds jobs → r2 → backend (Phase 11 r2-orchestrating jobs must release r2 handles BEFORE SessionRegistry __aexit__ kills the sessions)
- [Phase 09-background-job-system]: Plan 03: D-24 module-constant invariant preserved — _build_job_registry imports MAX_JOBS_INFLIGHT/JOB_CANCEL_GRACE_S/MAX_COMPLETED_JOBS from jobs.py; zero new os.environ reads added to app.py (negative grep)
- [Phase 09-background-job-system]: Plan 03: gateway-native tool count 43 → 47 (4 Phase 9 jobs tools); Rule 1 deviation bumped EXPECTED_TOOLS in test_tool_list.py (precedent: Phase 7-08 SUMMARY same pattern)
- [Phase 09-background-job-system]: Plan 04: Wave 0 Nyquist suite landed -- 17 test files + conftest + package marker; 66 non-slow tests pass + 1 slow capa skips cleanly on dev host; SC-4 disconnect reap measured at 0.91 ms (well under 200 ms ceiling)
- [Phase 09-background-job-system]: Plan 04: Rule-3 conftest.registry_factory reloads BOTH mcp_gateway.jobs AND mcp_gateway.tools.jobs when env-override is used (with finalizer to restore), because tools.jobs binds D-15 exception classes by name at import; without dual-reload, tools.jobs.except JobNotFound misses the new class object and the D-15 'tools never raise' contract breaks in test scope
- [Phase 09-background-job-system]: Plan 04: Rule-1 deviation in test_spec_validation -- 'no jsonschema dep' invariant rewritten from  to source-grep against jobs.py because mcp SDK 1.27 transitively installs jsonschema; semantic invariant preserved (jobs.py does NOT import jsonschema)
- [Phase 09-background-job-system]: Plan 04: VALIDATION.md flipped to nyquist_compliant=true + wave_0_complete=true; status=validated; 19 Wave 0 checkboxes ticked; Approval=green; Phase 9 ready for /gsd-verify-work sign-off
- [Phase 09-background-job-system]: Plan 05: D-15 contract gap closure for capa -- 'required' schema rule + broader except (ValueError, FileNotFoundError, KeyError, OSError) around registry.submit() restores 'tools never raise' for capa; baseline 'except Exception' count preserved at 1 (narrow exception list chosen over bare Exception)
- [Phase 10]: Phase 10 Plan 01: Dockerfile apt migrated from binwalk v2 (EOL 2025-12-12) to binwalk3 in Wave 0 so Plan 02 argv builders target binwalk3 CLI from the start
- [Phase 10]: Phase 10 Plan 01: Wave 0 RED-stub scaffold landed verbatim per plan (54 tests collected, 51 ImportError on execution); test bodies are 'assert True' placeholders -- Plan 05 owns behavioural body fill-in (Phase 6/7/8/9 precedent)
- [Phase 10]: Phase 10 Plan 01: scripts/probe_extraction_tools.sh defers Assumption A1/A2/A3 verification to next container rebuild (matches Phase 7 best-effort fallback pattern); operator runs probe inside container before Plan 02 argv builders are finalised
- [Phase 10]: Plan 02: extraction.py LEAF primitive delivered verbatim per plan; module imports cleanly, registers unblob + binwalk_extract JobToolSpecs at import, 20 RED-stub tests flipped GREEN on first run
- [Phase 10]: Plan 02: binwalk3 depth kwarg retained in schema for forward compatibility but silently ignored in argv (Assumption A2: binwalk3 has no -d/--depth flag); recursion controlled by -M only
- [Phase 10]: Plan 02: -- argv separator included in both unblob + binwalk argv builders (Open Question #5 resolved YES) -- defense-in-depth against attacker-controlled sample names starting with -
- [Phase 10]: Plan 03: extraction.py extended in place with archive-bomb monitor (D-17) -- single asyncio.create_task call site inside _spawn_monitor + module-level task retention set (Pitfall: asyncio.create_task GC drop)
- [Phase 10]: Plan 03: D-15 timing rule enforced -- quarantine_symlinks runs in post-terminal hook BEFORE the final update_meta status flip; CancelledError caught (not re-raised) so quarantine still runs on shutdown
- [Phase 10]: Plan 03: _du_sb dedups hardlinks via (st_dev, st_ino) seen-set with os.walk(followlinks=False) + lstat + S_ISREG (Pitfall 7 conservative direction); tools.jobs imported LOCALLY inside coroutine to avoid circular import
- [Phase 10]: Plan 04: _existing_case_for_sha256 D-14 helper co-located in tools/extract.py (NOT extraction.py per CONTEXT D-14) — deliberate primitive-layer-isolation deviation; negative-grep on extraction.py enforces
- [Phase 10]: Plan 04: promote_extracted_sample shells out to scripts/init_status_tree.sh via subprocess_runner.run_script + STATUS_ROOT iterdir pre/post diff to identify new case dir (Pitfall 5: init_case is a closure inside tools/artifacts.py::register, cannot be imported)
- [Phase 10]: Plan 04: 7 tools registered via mcp.tool()(fn) wrapping pattern in register(mcp) — NOT @decorator at definition (matches Phase 8/9 r2_sessions/jobs); allows direct test import + call
- [Phase 10]: Wave-3 integration commit pattern: source wire-up + RED->GREEN test flip + VALIDATION sign-off (matches Phase 7-08 + 9-03 precedent)
- [Phase 10]: Tool-count range bumped 35-50 -> 35-60 to absorb Phase 11 conditional dynamic tools
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 01: sessions/ package re-export __init__.py force-reloads _base + r2 on package reload (4-line block) to preserve Phase 8 D-14 importlib.reload semantics -- Rule-1 deviation surfaced by test_env_var_bad_value_raises during Task 2 verification
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 01: BaseSession dataclass + R2Session subclass with tail-defaulted fields (sample_sha256='', sample_path=Path()) -- no kw_only=True needed; symmetric structure ready for Plan 03 GdbSession
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 01: kind kwarg on SessionRegistry.open defaults to 'r2' for backward compat; gdb branch uses deferred  so Plan 03 lands the gdb driver later without breaking this plan
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 02: JobToolSpec extended with optional post_terminal_hook field (default None) -- all Phase 9/10 specs construct unchanged; hook invoked at TOP of _mark_terminal (before snapshot/eviction) with exception-swallow
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 02: Local _dyn_tool_log_path helper inside dynamic.py instead of extending artifacts_io.tool_log_path with subdir/ext kwargs (LEAF discipline preserved; no cascading edits to Phase 6/7/8/9/10 callers)
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 02: Reaper race-safety widened to (ProcessLookupError, PermissionError, OSError) on both os.getpgid and os.kill -- child exiting mid-walk is benign, reaper never raises out of hook
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 03: gdb.py reused _env_float from sessions._base (not local helper) -- bad-value RuntimeError semantics byte-identical to Phase 8 D-14 across r2/gdb
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 03: deny regex ships 15 alternatives covering 19 deny vectors (jit-reader-load + define explicitly included per VALIDATION DYN-05); allowlist FIRST + deny regex SECOND both raise ValueError
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 03: sentinel-emit at END of lockdown batch (not interleaved) -- ONE readuntil-the-sentinel for the entire 10-line lockdown init, matches Phase 8 r2 wire shape
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 03: gdb argv NEVER includes -iex/-ex/-x (Pitfall #10); _build_gdb_argv returns EXACTLY 11 elements via wrap_netns(["gdb","--interpreter=mi3","--quiet","--nx","--nh",sample])
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 04: tools/dynamic.py (546 LoC) lands 7 env-gated MCP handlers; D-DYN-IMPORT-01 conditional import in tools/__init__.py honored; test_tool_list.py parametrized on env (54 baseline / 61 dynamic); tools NEVER raise contract via try/except returning structured error dicts
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 04: Test-isolation full-reset pattern (drop sys.modules entries + delete parent-package attrs) required because register_job_tool rejects new-identity re-registration AND from-import resolves via parent-package __dict__ bypassing sys.modules misses
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 04: test_dynamic_tools.py uses _DynamicProxy class (not module-level from-import) so dynamic_mod.CAPABILITIES writes always target the CURRENT mcp_gateway.dynamic instance, surviving other test files' module resets
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 05: --dynamic flag compositional with --remote; EX_USAGE (64) hard-fail when used standalone with actionable retry hint
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 05: MCP_GATEWAY_DYNAMIC_TOOLS env passthrough via env-name-only in compose.yaml; ${env:-$DYNAMIC_TOOLS} fallback in run_docker.sh -- explicit env wins, flag wins otherwise
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 05: Dockerfile keeps qemu-user AND adds qemu-user-static (complementary packages); util-linux added defense-in-depth even though Kali base provides it
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 06: Lifespan probe runs UNCONDITIONALLY (env-gate only affects WARN log dispatch); dynamic.CAPABILITIES populated even when MCP_GATEWAY_DYNAMIC_TOOLS=0 so get_dynamic_capabilities() is always responsive (D-DYN-CAP-PROBE-01 invariant)
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 06: Generated fixture binaries (dns_lookup, setsid_escape, hello_arm.bin) added to .gitignore; build_fixtures.sh is the source of truth, mirrors Phase 7 best-effort fallback pattern (static-link first, dynamic fallback)
- [Phase 11-dynamic-lab-mode-env-gated]: Plan 06: VALIDATION.md signed off green -- nyquist_compliant=true, wave_0_complete=true, status=validated, Approval=green; 19 per-task rows flipped ✅; 13-invariant Phase 11 Sign-Off block added

### Pending Todos

- Plan Phase 5 (F-1 Image-Hash Fix) via `/gsd-plan-phase 5`
- Resolve open decisions flagged in research/SUMMARY.md during phase planning:
  - Phase 7: `run_shell` env whitelist contents, `mare-shell` UID primary group ACL on existing case-dirs
  - Phase 8: session resource caps (default 30 min idle, cap 8 sessions per consensus)
  - Phase 9: job log retention/rotation policy
  - Phase 11: per-call netns mechanism, ptrace probe error UX, gdb MI3 command allowlist, binfmt detection helper
- Research flag: `/gsd-research-phase 11` recommended before planning Dynamic Lab Mode (6 distinct pitfalls cluster in that phase)

### Blockers/Concerns

- F-1 (Phase 5) must land before substantive gateway edits, otherwise every subsequent phase hits the "edited gateway, container still has old code" trap that burned 2026-05-11 UAT
- Security boundary needs explicit documentation in v1.1 README: shell is real but cwd-confined to case_dir, no network unless dynamic mode + opt-in, every invocation captured
- Dynamic mode UX surface (`./run_docker.sh --dynamic` ergonomics, env var documentation, mode visibility in `CURRENT_STATE.json`) needs design during Phase 11 planning, not just implementation
- Mount-namespace isolation for `run_shell` deferred to v1.2 (would require CAP_SYS_ADMIN); v1.1 posture-only confinement documented as known limitation

### Quick Tasks Completed (v1.0 era)

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260414-el8 | Refactor: create workspace/ directory, move skills to native .claude/.codex locations, update mount config and README | 2026-04-14 | dfa6cdb | [260414-el8-refactor-create-workspace-directory-move](./quick/260414-el8-refactor-create-workspace-directory-move/) |
| 260414-fsg | Replace docker-bin wrappers with native config files for Claude and Codex | 2026-04-14 | 3b3c981 | [260414-fsg-replace-docker-bin-wrappers-with-native-](./quick/260414-fsg-replace-docker-bin-wrappers-with-native-/) |
| 260414-iee | Move Claude/Codex config from workspace project-level to user-level via configure-agent-mcp.sh | 2026-04-14 | a89af30 | [260414-iee-move-claude-codex-config-from-workspace-](./quick/260414-iee-move-claude-codex-config-from-workspace-/) |
| 260423-f3k | Fix inner agent statusline paths (/workspace -> /agent) | 2026-04-23 | bdae5ea | [260423-f3k-fix-inner-agent-statusline-paths-workspa](./quick/260423-f3k-fix-inner-agent-statusline-paths-workspa/) |
| 260511-cwf | Fix remote MCP security defaults: localhost host bind, exact Origin validation, and case_dir confinement | 2026-05-11 | f556fda | [260511-cwf-fix-remote-mcp-security-defaults-localho](./quick/260511-cwf-fix-remote-mcp-security-defaults-localho/) |
| 260511-evu | Make the Mastra starter provide a browser GUI in addition to the existing CLI, and verify by opening the GUI | 2026-05-11 | uncommitted | [260511-evu-make-the-mastra-starter-provide-a-browse](./quick/260511-evu-make-the-mastra-starter-provide-a-browse/) |
| 260511-fam | Switch the Mastra starter GUI to the default Mastra Studio dashboard with a registered MARE agent and tools | 2026-05-11 | uncommitted | [260511-fam-switch-the-mastra-starter-gui-to-the-def](./quick/260511-fam-switch-the-mastra-starter-gui-to-the-def/) |
| Phase 05-f-1-image-hash-fix P01 | 2min | 1 tasks | 1 files |
| Phase 05-f-1-image-hash-fix P02 | 100s | 2 tasks | 2 files |
| Phase 05-f-1-image-hash-fix P03 | 87s | 1 tasks | 1 files |
| Phase 06-retoolrunner-artifacts-io-foundation P01 | 3min | 3 tasks | 3 files |
| Phase 06-retoolrunner-artifacts-io-foundation P02 | 4min | 1 tasks | 1 files |
| Phase 06-retoolrunner-artifacts-io-foundation P03 | 3min | 1 tasks | 1 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P01 | 5min | 3 tasks | 15 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P02 | 80s | 1 tasks | 2 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P03 | 12min | 1 tasks | 2 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P04 | 3min | 1 tasks | 1 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P05 | 4min | 1 tasks | 2 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P06 | 4min | 1 tasks | 2 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P07 | 3min | 1 tasks | 2 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P08 | 4min | 2 tasks | 6 files |
| Phase 08-session-scoped-r2 P01 | 3min | 4 tasks | 5 files |
| Phase 08-session-scoped-r2 P02 | 2min | 1 tasks | 1 files |
| Phase 08-session-scoped-r2 P03 | 224s | 1 tasks | 1 files |
| Phase 08-session-scoped-r2 P04 | 6min | 2 tasks | 4 files |
| Phase 08-session-scoped-r2 P05 | 4min | 3 tasks | 3 files |
| Phase 09-background-job-system P01 | 5min | 3 tasks | 3 files |
| Phase 09-background-job-system P02 | 6min | 1 tasks | 2 files |
| Phase 09-background-job-system P03 | 3min | 1 tasks | 4 files |
| Phase 09-background-job-system P04 | 11min | 3 tasks | 20 files |
| Phase 09-background-job-system P05 | 7min | 3 tasks | 3 files |
| Phase 10 P01 | 4min | 2 tasks | 16 files |
| Phase 10 P02 | 259s | 1 tasks | 1 files |
| Phase 10 P03 | 3min | 1 tasks | 1 files |
| Phase 10 P04 | 4min30s | 1 tasks | 1 files |
| Phase 10 P05 | 10min | 3 tasks | 16 files |
| Phase 11-dynamic-lab-mode-env-gated P01 | 6min | 2 tasks | 6 files |
| Phase 11-dynamic-lab-mode-env-gated P02 | 8min | 2 tasks | 5 files |
| Phase 11-dynamic-lab-mode-env-gated P03 | 6min | 2 tasks | 3 files |
| Phase 11-dynamic-lab-mode-env-gated P04 | 15min | 2 tasks | 5 files |
| Phase 11-dynamic-lab-mode-env-gated P05 | 8min | 4 tasks | 5 files |
| Phase 11-dynamic-lab-mode-env-gated P06 | 8min | 3 tasks | 7 files |

## Session Continuity

Last session: 2026-05-20T02:07:33.926Z
Stopped at: Phase 12 context gathered
Resume file: .planning/phases/12-orchestrator-skill-update/12-CONTEXT.md
