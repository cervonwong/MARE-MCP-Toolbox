# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.1 — Remote RE Tool Expansion

**Shipped:** 2026-05-21
**Phases:** 10 (5-14) | **Plans:** 48 | **Commits:** 247

### What Was Built

- Constrained `run_shell` + 11 typed static RE wrappers (`run_file`/`run_die`/`run_xxd`/`run_readelf`/`run_objdump`/`run_nm`/`run_rabin2`/`run_capstone_disasm`/`run_ropper`/`run_jq`/`run_yq`) backed by a single `ReToolRunner` chokepoint with argv-only spawn, cwd-confinement, hard timeout, process-group `SIGKILL`, and auto-capture to `case_dir/tool-logs/`
- Session-scoped r2 (Phase 8) and gdb-MI3 (Phase 11) sessions with kind-aware `SessionRegistry`, lifespan teardown, idle reaper, and combined `BoundedSemaphore` cap (Phase 13)
- Background job system (Phase 9) with `start_tool_job`/`get_tool_job`/`cancel_tool_job`/`list_tool_jobs`, in-memory FIFO registry, log-cap with `MARE_JOB_KILLED_LOG_CAP` marker, MCP `Context.report_progress` for tools like unblob
- Extraction tier (Phase 10): `run_binwalk` (binwalk3), `run_unblob`, UPX trio, `list_extracted_files`, `promote_extracted_sample` (atomic re-upload with sha256), symlink quarantine, archive-bomb monitor
- Env-gated Dynamic Lab Mode (Phase 11): `run_strace`/`run_ltrace`/`run_qemu_user` + gdb sessions, `./run_docker.sh --dynamic` operator entry, capability probes, no-net default via per-call `unshare`
- Orchestrator skill v1.1 rewrite (Phase 12): IDA-first backend priority, 7 W-N workflow files, dual-mode (gateway vs scripts) preserved, dynamic-mode skip behavior
- Hardening (Phase 13): atomic semaphore caps, r2 `cfg.sandbox=true` security boundary (stdin-latched per hot-fix `d696a72`), env-gated `open_r2_session_unsafe`

### What Worked

- **Wave-0 RED-stub discipline.** Every plan that introduced a new module landed a "tests fail because the module doesn't exist yet" scaffold first; Wave 1/2 turned RED → GREEN. Nyquist alignment was almost automatic.
- **Paste-ready code blocks in plans.** Most plans landed verbatim from the `<action>` block on first run (Phases 6/8/10 all had zero-deviation TDD GREEN flips). When deviations happened (Rule 1/3), they were documented in SUMMARY immediately.
- **LEAF-module discipline for primitives.** `artifacts_io.py`, `sessions/_base.py`, `extraction.py`, `dynamic.py` all kept stdlib-only or sibling-only imports — no cycles, safe to import from any tool wrapper.
- **Splitting v1.1 into 9 feature phases + 1 closure phase.** Phase 14 as a dedicated meta-audit gap-closure phase (not bookkeeping smeared across 5-13) made the gap-closure auditable in its own SUMMARY/VERIFICATION pair.
- **Audit re-run as success oracle.** Phase 14 Plan 04's terminal step was literally "run `/gsd-audit-milestone v1.1` and require `status: passed`." Removed ambiguity on "is the milestone done?"

### What Was Inefficient

- **TOCTOU caps shipped first, then hardened (Phase 13).** Phase 8/9 used `if count >= max: raise` without lock-guarding the check + the slot acquisition. Concurrent N+1 callers slipped past in tests. Phase 13 rewrote both to `asyncio.BoundedSemaphore` with single release sink in `_mark_terminal`. Catch this in Wave 0 next time — atomicity is a property tests can express RED-first.
- **r2 sandbox argv vs stdin churn.** Phase 13 Plan 03 latched `cfg.sandbox=true` via argv `-e cfg.sandbox=true`; live testing in Phase 14 showed r2 evaluated argv `-e` flags AFTER binary autoload — leaving a window. Hot-fix `d696a72` moved the latch to a post-spawn stdin batch. Lesson: when the security boundary depends on tool internals (r2 eval order), live-test the boundary before declaring victory at code review.
- **Per-phase frontmatter drift.** 4 phases (07/08/10/11) closed Phase 14 live UAT items in-document but did not re-flip `status: human_needed` → `status: passed`. Cosmetic but recurring. Either automate the frontmatter flip when adding a `## Live UAT Results` section, or accept the in-document closure as canonical and stop using the frontmatter field.
- **REQUIREMENTS.md traceability columns lag bodies.** 47 rows still show `TBD | Pending` despite `[x]` body checkboxes and phase VERIFICATION.md being SATISFIED. The traceability table is bookkeeping that doesn't gate execution — but it confuses audit. Either drive it from VERIFICATION.md programmatically or stop maintaining the columns.
- **Test-isolation fragility (Phase 14 D-01/D-02).** `from sessions import SessionCapReached` bound a class at import time that didn't survive `sys.modules.pop` + reimport in test reload paths. Lesson: when a module is reload-target in tests, use `sys.modules['mcp_gateway.sessions'].SessionCapReached` at catch sites — or accept that reload is incompatible with name-bound imports.

### Patterns Established

- **`@mcp.tool()(fn)` register-wrapper pattern (NOT decorator at definition).** Phases 7/8/9/10/11 all moved tool functions to module level and registered via `mcp.tool()(fn)` inside a `register(mcp)` call. Lets tests import handlers directly + call them; decorator at definition couples handler to the FastMCP instance and breaks reuse.
- **Disclaimer splice via post-definition `.replace()`.** SESS-05, JOBS D-26, EXTR D-23 disclaimers spliced into `fn.__doc__` after the function is defined — preserves the docstring as a parser-attached literal while injecting the long-form text once.
- **`EXPECTED_TOOLS` parametrized on env.** `test_tool_list.py` parametrizes on `MCP_GATEWAY_DYNAMIC_TOOLS` so both 54 (baseline) and 61 (with dynamic) tool counts are regression-locked. Same pattern for `MCP_GATEWAY_R2_UNSAFE_ALLOWED` in Phase 13.
- **`JobToolSpec.post_terminal_hook` for tier-aware cleanup.** Phase 10 extraction quarantine + Phase 11 follow-fork reaper attach to terminal-state via a single optional callable on the spec. Phase 9 specs leave it `None` (no regression).
- **In-process `_DynamicProxy` for tests against reloadable modules.** Phase 11 Plan 04 introduced this to write to `dynamic_mod.CAPABILITIES` even after another test resets the parent module — preferable to `sys.modules` games when only writing one attribute.

### Key Lessons

1. **Atomicity is a Wave-0 invariant.** If a cap, a registry slot, or a semaphore exists, write the concurrent-N+1 RED test before the primitive. Don't ship `count >= max` and harden later.
2. **Live-test security boundaries.** A passing argv test is not the same as a passing `e cfg.sandbox` round-trip inside an open r2 session. Phase 13 → Phase 14 hot-fix is the canonical case.
3. **Plan paste-ready code blocks.** When the `<action>` block can be `git apply`-equivalent, deviation-budget collapses and SUMMARY can record only the Rule 1/2/3 corrections that actually mattered.
4. **Separate the meta-audit phase.** Don't smear gap-closure across feature phases. Phase 14 as a dedicated phase made the closure visible, scoped, and auditable.
5. **Frontmatter consistency is automation work.** If you require humans to flip 4 `status:` fields after closing UAT in-document, they will not. Either automate or drop the field.

### Cost Observations

- Model mix: predominantly Opus (gsd-* agents default to quality profile per `.planning/config.json`)
- Sessions: not instrumented; ~10 days end-to-end calendar time with 247 commits
- Notable: 14-04 (live UAT closure + audit re-run) was the longest single plan at ~30 min wall-clock; most plans completed in 2-10 min via paste-ready code blocks and zero-deviation TDD flips

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Commits | Key Change |
|-----------|--------|-------|---------|------------|
| v1.0      | 4      | 16    | 151     | Initial GSD adoption; phases 1-4 paced over ~40 days |
| v1.1      | 10     | 48    | 247     | Wave-0 RED-stub discipline + paste-ready plan code blocks + dedicated meta-audit closure phase; ~9 days |

### Cumulative Tool Surface

| Milestone | Baseline Tools | Dynamic-Mode Tools | New Phases |
|-----------|----------------|---------------------|------------|
| v1.0      | 22             | n/a                 | 4          |
| v1.1      | 54             | 61                  | 10 (cumulative: 14) |

### Top Lessons (Verified Across Milestones)

1. **Custom FastMCP over generic stdio bridge (v1.0) → custom orchestration over generic primitives (v1.1).** Both milestones validated that bespoke gateway code carrying multiple cross-cutting concerns (auth + /upload + orchestrator tools + backend pass-through; chokepoint runner + session registry + job registry + capability probes) beats stitching together off-the-shelf bridges.
2. **Live UAT is the only honest oracle.** v1.0 caught the F-1 image-hash bug only at 2026-05-11 UAT after green tests; v1.1 caught the r2 argv-sandbox window only at Phase 14 live container UAT after green Phase 13 unit tests. Schedule live container UAT inside the milestone, not after.
