---
phase: 11-dynamic-lab-mode-env-gated
plan: 02
subsystem: dynamic-primitive
tags: [dynamic, primitive, capabilities, jobs, netns, reaper, strace, ltrace, qemu-user]

requires:
  - phase: 09-background-job-system
    provides: JobToolSpec dataclass, BackgroundJobRegistry, register_job_tool, _spawn_and_drive/_mark_terminal lifecycle
  - phase: 10-extraction-tier
    provides: precedent for JobToolSpec registration from a non-jobs module at import time
  - phase: 11-dynamic-lab-mode-env-gated-plan-01
    provides: sessions/ package refactor enabling Plan 03 gdb session driver to layer on Plan 02 primitives
provides:
  - mcp_gateway.dynamic module (LEAF primitive) with capability probes, profile dicts, allowlist/denylist validation, wrap_netns, build_*_argv builders, reap_followfork_strays, and 3 JobToolSpec registrations
  - JobToolSpec extended with optional 8th `post_terminal_hook` field (default None preserves Phase 9/10 backward-compat)
  - jobs._mark_terminal invokes post_terminal_hook with exception-swallow BEFORE snapshot write and FIFO eviction
  - 28 new RED-then-GREEN unit tests in tests/test_dynamic_primitive.py locking DYN-03/04/06/07 contracts
  - 2 C fixture files (dns_lookup.c, setsid_escape.c) for Plan 04/06 netns + reaper end-to-end tests
affects: [11-03 gdb session driver, 11-04 dynamic MCP tool surface, 11-05 lifespan wiring, 11-06 e2e]

tech-stack:
  added: []
  patterns:
    - "Optional dataclass-field extension pattern: add new field with `= None` default at the tail; all existing call-sites construct unchanged (no kwarg edits to Phase 9/10 specs)"
    - "Post-terminal hook insertion at the TOP of _mark_terminal (before snapshot build) so the hook runs AFTER killpg/proc.wait() finalises in _spawn_and_drive's `finally` but BEFORE state moves from _inflight to _completed"
    - "LEAF-module discipline maintained: dynamic.py imports stdlib + artifacts_io + jobs only; tools.samples imported LOCAL inside _resolve_sample_local to avoid tier crossing"
    - "Per-subdir log-path helper local to dynamic.py (_dyn_tool_log_path) because artifacts_io.tool_log_path is hardcoded to tool-logs/ subdir; Plan 02 needs dynamic/ and qemu/"
    - "Bounded recursive procfs walk for follow-fork stray reap: depth-limited (REAP_DEPTH=8), visited-set deduped, every os syscall wrapped in try/except for race safety (ProcessLookupError/PermissionError/OSError)"

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/dynamic.py
    - mcp-gateway/tests/test_dynamic_primitive.py
    - mcp-gateway/tests/fixtures/dns_lookup.c
    - mcp-gateway/tests/fixtures/setsid_escape.c
  modified:
    - mcp-gateway/src/mcp_gateway/jobs.py

key-decisions:
  - "Hook insertion at the TOP of _mark_terminal: runs AFTER killpg/proc.wait() (guaranteed by _spawn_and_drive's `finally` calling _mark_terminal) and BEFORE snapshot/FIFO eviction. Placement is correct per plan instruction; alternative (end of method) would have run post-eviction which is wrong."
  - "Local _dyn_tool_log_path helper in dynamic.py instead of extending artifacts_io.tool_log_path with ext+subdir kwargs (would have been a Rule-1 deviation cascading into Phase 6/7/8/9/10 callers). Plan 02 stays LEAF; future plans can promote the helper if needed."
  - "Reaper races on ProcessLookupError: every os.getpgid() and os.kill() wrapped in try/except (ProcessLookupError, PermissionError, OSError). A child exiting mid-walk is benign — it's already gone, no reap needed. Plan output question explicitly resolved YES."
  - "Denylist mirrors RESEARCH Pitfall #9 corrections verbatim: drop --exec (not a real strace flag), add -b and --detach-on. The =-split denylist check catches --detach-on=execve."

requirements-completed: [DYN-03, DYN-04, DYN-06, DYN-07]

duration: ~8 min
completed: 2026-05-20
---

# Phase 11 Plan 02: dynamic primitive layer Summary

**Landed mcp_gateway/dynamic.py (~616 LoC) — the LEAF primitive for env-gated dynamic-lab mode — with capability probes (DYN-06), per-call netns argv wrapping (DYN-03/04 isolation), argv profiles + builders for strace/ltrace/qemu_user (DYN-03/04), an allowlist/denylist for extra_args (DYN-03 input-validation), the follow-fork stray reaper (DYN-07 pgroup cleanup), and 3 JobToolSpec registrations.**

**Plus a 1-field backward-compatible extension to Phase 9's JobToolSpec dataclass — adding `post_terminal_hook: Optional[Callable[[Job], asyncio.Future]] = None` — and a single 6-line block at the top of `jobs._mark_terminal` that invokes the hook with exception-swallow semantics. All existing Phase 9/10 specs construct unchanged.**

## Performance

- **Duration:** ~8 min (2026-05-20T00:33:54Z → 2026-05-20T00:42:02Z)
- **Started:** 2026-05-20T00:33:54Z
- **Completed:** 2026-05-20T00:42:02Z
- **Tasks:** 2 (both TDD: RED-stub test commit then GREEN implementation commit)
- **Files created:** 4 (dynamic.py, test_dynamic_primitive.py, dns_lookup.c, setsid_escape.c)
- **Files modified:** 1 (jobs.py — 12 lines added across 2 hunks)

**Line counts:**

| File | LoC |
|------|-----|
| mcp-gateway/src/mcp_gateway/dynamic.py | 616 |
| mcp-gateway/tests/test_dynamic_primitive.py | 358 |
| jobs.py diff (added) | 12 (one field with comment + one 6-line hook block in _mark_terminal) |
| dns_lookup.c | 29 |
| setsid_escape.c | 34 |

## Accomplishments

- **dynamic.py LEAF primitive landed** with the full public surface enumerated in must_haves: `DYNAMIC_TOOLS_ENABLED`, `DynamicCapabilities`, `CAPABILITIES`, `probe_all`, `STRACE_PROFILES`/`LTRACE_PROFILES`/`QEMU_USER_PROFILES`, `EXTRA_ARGS_ALLOWLIST_RE`, `_DENIED_EXTRA_ARG_FLAGS`, `_validate_argv_list`, `wrap_netns`, `build_strace_argv`/`build_ltrace_argv`/`build_qemu_user_argv`, `reap_followfork_strays`, `_reaper_hook`, and 3 `JobToolSpec` entries registered at module import.
- **JobToolSpec extended with optional 8th `post_terminal_hook` field** — default `None` preserves backward compat. Verified: all 5 existing specs (`_sleep_probe`, `_log_burst_probe`, `capa`, `unblob`, `binwalk_extract`) construct unchanged with `hook=None`.
- **`jobs._mark_terminal` wired** — single 6-line block at the TOP of the method (before `snapshot = self._build_snapshot(job)`); the `try/except Exception: log.exception(...)` swallow ensures cleanup proceeds even if the hook raises.
- **3 dynamic specs registered at import** — `strace`, `ltrace`, `qemu_user`. All point `post_terminal_hook` at the same `_reaper_hook` adapter coroutine.
- **28 RED→GREEN unit tests** lock the contract: 9 profile/allowlist tests, 2 wrap_netns tests, 6 builder tests, 4 capability/probe tests, 2 reaper tests, 4 JobToolSpec backward-compat tests, 1 dynamic-spec-registration test.
- **2 C fixtures** (dns_lookup.c — getaddrinfo("example.com") for netns isolation negative-control; setsid_escape.c — fork→setsid→sleep(60) for Plan 06 reaper end-to-end) staged under tests/fixtures/.

## Task Commits

1. **Task 1: Wave-0 RED tests + C fixtures** — `a25cebf` (test)
2. **Task 2: dynamic.py + JobToolSpec.post_terminal_hook** — `aac9572` (feat)

## Files Created/Modified

- `mcp-gateway/src/mcp_gateway/dynamic.py` (NEW, 616 LoC) — LEAF primitive. Imports: stdlib + `mcp_gateway.artifacts_io.ensure_subdir` + `mcp_gateway.jobs.{JobToolSpec, register_job_tool}` only. `tools.samples` imported LOCAL inside `_resolve_sample_local`. Three module-level `register_job_tool(...)` calls at import time.
- `mcp-gateway/src/mcp_gateway/jobs.py` (MODIFIED, +12 lines):
  - JobToolSpec dataclass at line 131-143: added `post_terminal_hook: Optional[Callable[["Job"], "asyncio.Future"]] = None` with explanatory comment (4 lines)
  - `_mark_terminal` at line ~690: prepended 6-line `hook = job.spec.post_terminal_hook; if hook is not None: try: await hook(job) except Exception: log.exception(...)` block + 2-line comment header
- `mcp-gateway/tests/test_dynamic_primitive.py` (NEW, 358 LoC) — 28 Wave-0 tests covering DYN-03/04/06/07.
- `mcp-gateway/tests/fixtures/dns_lookup.c` (NEW, 29 LoC).
- `mcp-gateway/tests/fixtures/setsid_escape.c` (NEW, 34 LoC).

## Decisions Made

- **Post-terminal hook inserted at the TOP of `_mark_terminal`** (before `snapshot = self._build_snapshot(job)`), NOT at the bottom (after FIFO eviction). The plan text explicitly directed this placement (`AT THE TOP of _mark_terminal (before snapshot = self._build_snapshot(job))`). Rationale: hook runs AFTER killpg/proc.wait() (guaranteed by `_spawn_and_drive`'s `finally:` → `await self._mark_terminal(job)`), which is what the reaper needs; running post-snapshot/post-eviction would still be functionally correct for the reaper but contradicts the plan and is harder to reason about.
- **Local `_dyn_tool_log_path` helper** added inside dynamic.py instead of editing `artifacts_io.tool_log_path`. The plan's code block calls `tool_log_path(case_dir, "strace", ".txt", subdir="dynamic")`, but the existing `artifacts_io.tool_log_path(case_dir, slug) -> Path` signature is `case_dir/tool-logs/<ts>-<slug>-<rand4>.txt` with no subdir/ext params. Extending artifacts_io would have rippled to Phase 6/7/8/9/10 callers. Plan 02 stays LEAF; the local helper builds `case_dir/<subdir>/<ts>-<slug>-<rand4><ext>` with the same `_SLUG_RE` validation discipline. Tracked as Rule-3 deviation below.
- **Reaper race safety widened** beyond the plan-suggested `(ProcessLookupError, PermissionError)` to also include `OSError` on both the `os.getpgid()` and `os.kill()` calls. `os.getpgid()` can raise `OSError(ESRCH)` (some kernels) and `os.kill()` can raise `OSError(EPERM)` on container boundaries. Functionally the same intent: "if we can't reach the child, skip it" — never let the reaper raise out of the hook.
- **Denylist matches RESEARCH Pitfall #9 verbatim**: no `--exec` (not a real strace flag); `-b` and `--detach-on` included; `=`-split denylist check catches `--detach-on=execve`. The regex+denylist combination accepts shell-safe `--signal=KILL` and `trace=open,read` while rejecting the 10 metachars enumerated in T-11-02-01.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Local `_dyn_tool_log_path` helper instead of `artifacts_io.tool_log_path(..., subdir=...)`**

- **Found during:** Task 2, before first test run
- **Issue:** The plan's paste-ready builder code calls `tool_log_path(case_dir, "strace", ".txt", subdir="dynamic")` but the existing helper signature in `artifacts_io.py` is `tool_log_path(case_dir, slug) -> Path` (no `ext`, no `subdir`). Calling the plan's signature would have raised `TypeError`. Modifying `artifacts_io.tool_log_path` to accept new kwargs would have cascaded into Phase 6/7/8/9/10 callers and risked silent behaviour change.
- **Fix:** Added a private module-local helper `_dyn_tool_log_path(case_dir, slug, ext, *, subdir)` inside `dynamic.py` that builds `case_dir/<subdir>/<%Y%m%dT%H%M%SZ>-<slug>-<rand4><ext>` using the same `_SLUG_RE = ^[a-z0-9][a-z0-9_-]{0,39}$` slug discipline and `secrets.token_hex(2)` 4-char random suffix as the canonical helper. The three builders call the local helper; `artifacts_io` is untouched.
- **Files modified:** None additional — fix is internal to the new dynamic.py file already being created in Task 2.
- **Verification:** Tests `test_build_strace_argv_shape`, `test_build_ltrace_argv_shape` assert `/dynamic/` in the output path and `.txt` extension; both GREEN. LEAF discipline preserved: `grep -E "^(from|import) mcp_gateway" dynamic.py` shows only `mcp_gateway.artifacts_io.ensure_subdir` and `mcp_gateway.jobs.{JobToolSpec, register_job_tool}`.
- **Committed in:** `aac9572` (Task 2 commit; deviation fix landed in the same atomic implementation commit)

**2. [Rule 2 - Robustness] Widened reaper race-safety exception list**

- **Found during:** Task 2, while reviewing the verbatim algorithm from RESEARCH Example 4
- **Issue:** The plan's `reap_followfork_strays` catches `(ProcessLookupError, PermissionError)` on `os.getpgid(cpid)` and `os.kill(cpid, SIGKILL)`. On some kernels `os.getpgid()` can raise `OSError(ESRCH)` directly (vs. `ProcessLookupError` which is a subclass) and `os.kill()` can raise `OSError(EPERM)` at container PID-namespace boundaries.
- **Fix:** Widened both except-clauses to `(ProcessLookupError, PermissionError, OSError)`. Functionally identical intent; just more defensive.
- **Files modified:** mcp-gateway/src/mcp_gateway/dynamic.py only (no additional files).
- **Verification:** `test_reap_followfork_strays_returns_zero_when_no_strays` exercises the happy path; the broader catches don't change the zero-stray return value. The Plan 06 setsid_escape end-to-end test will exercise the kill path on real strays.
- **Committed in:** `aac9572`

---

**Total deviations:** 2 auto-fixed (1 Rule-3 blocking signature mismatch resolved with local helper; 1 Rule-2 robustness widening of race-safety exception catch)
**Impact on plan:** Both fixes are internal to dynamic.py — the file Task 2 was already creating. No additional files touched, no cascading edits to Phase 6/7/8/9/10 callers.

## Issues Encountered

- **Pre-existing test-ordering flakiness** (out of scope, pre-dated Plan 02): `tests/jobs/test_list_tool_jobs.py::test_specs_default_hides_underscore` and `test_specs_with_include_internal_shows_all` fail when run in the `jobs/` suite alongside other test files but PASS in isolation. Confirmed against `git stash` baseline (Plan 01 commit `4520949`) — the same two tests fail with identical error before any Plan 02 code was added. This is the test-ordering issue documented in 11-01-SUMMARY ("test_unknown_tool_shape and test_specs_* reported failures that disappeared when each file was run in isolation"). NOT caused by Plan 02; deferred per scope boundary.
  - Reproducer: `pytest mcp-gateway/tests/jobs/test_list_tool_jobs.py::test_specs_default_hides_underscore -x` → PASSES
  - Suite-mode reproducer: `pytest mcp-gateway/tests/jobs/ -x -m "not slow"` → fails on that node
  - Root cause sketch: the test asserts `names == ["capa"]` for `state="_specs"` filtering underscore prefixes, but Phase 10's `unblob`/`binwalk_extract` (and now Plan 02's `strace`/`ltrace`/`qemu_user`) get registered globally on `mcp_gateway.extraction` / `mcp_gateway.dynamic` import. The test's `registry_factory.reload` cycle re-imports `mcp_gateway.jobs` but `JOB_TOOL_REGISTRY` is module-state; re-import flushes it BEFORE the dynamic/extraction registrations re-fire. When run alone, no prior import of extraction/dynamic occurred. When run in the jobs suite, prior collection of other test modules (test_runner.py, test_re_artifacts.py via the package `__init__.py`) triggers extraction → registrations land → reload-of-jobs flushes → underscores remain hidden but `capa` AND `unblob` AND `binwalk_extract` AND `strace`/`ltrace`/`qemu_user` survive.
  - This is a Plan 04 (dynamic MCP surface wiring) or Plan 03+ test-isolation hygiene issue — not a Plan 02 primitive-layer concern.

- **Host pytest cache permission warnings** (informational): `.pytest_cache/v/cache/nodeids` and `cache/lastfailed` are not writable on the WSL executor. Same noise reported in 11-01-SUMMARY. Pre-existing host-environment artifact, not test failure.

## Verification

All `<verification>` commands from the plan pass:

- `pytest mcp-gateway/tests/test_dynamic_primitive.py -x` → **28 passed** exit 0.
- `pytest mcp-gateway/tests/test_sessions_package.py mcp-gateway/tests/test_tool_list.py -x` → **15 passed** exit 0 (Plan 01 + tool-count regressions preserved).
- `pytest mcp-gateway/tests/extraction/ -m "not slow"` → **51 passed, 3 deselected** exit 0 (Phase 10 regression preserved).
- `pytest mcp-gateway/tests/jobs/ -m "not slow" --ignore=mcp-gateway/tests/jobs/test_list_tool_jobs.py` → **62 passed, 1 deselected** exit 0 (Phase 9 regression preserved; the 2 flaky tests in test_list_tool_jobs.py are pre-existing per Issues section above).
- `python -c "import mcp_gateway.dynamic as d; from mcp_gateway.jobs import JOB_TOOL_REGISTRY; assert all(n in JOB_TOOL_REGISTRY for n in ('strace','ltrace','qemu_user')); print('OK')"` → `OK`.
- `grep -c "MISSING\|TODO\|FIXME\|XXX" mcp-gateway/src/mcp_gateway/dynamic.py` → `0`.
- `grep -n "post_terminal_hook" mcp-gateway/src/mcp_gateway/jobs.py | wc -l` → `3` (one field definition, one .get in _mark_terminal, one log.exception message) — exceeds the "at least two" acceptance threshold.
- `grep -E "register_job_tool\(.*_SPEC\)" mcp-gateway/src/mcp_gateway/dynamic.py` → **3 matches** (STRACE_SPEC, LTRACE_SPEC, QEMU_USER_SPEC).
- `grep '"unshare", "--net", "--ipc", "--uts", "--"' mcp-gateway/src/mcp_gateway/dynamic.py` → **3 matches** (docstring header constant, docstring of wrap_netns, return statement of wrap_netns) — confirms the netns prefix tuple literal.

## Output spec follow-up

The plan's `<output>` section asked for four explicit confirmations:

1. **Line counts:** dynamic.py = **616 LoC**; jobs.py diff = **+12 lines** (4-line dataclass-field-with-comment hunk + 8-line `_mark_terminal` hook hunk including its 2-line explanatory comment).
2. **Hook insertion location:** placed at the **TOP** of `_mark_terminal` (before `snapshot = self._build_snapshot(job)`), per plan directive. Runs after killpg/proc.wait() (guaranteed by `_spawn_and_drive`'s `finally`) and before FIFO eviction.
3. **Deviations from verbatim regex / denylist:** **none for the regex itself or the denylist set**; both are byte-identical to CONTEXT.md D-DYN-PROF-02 and RESEARCH Pitfall #9 corrected list. Behavioural deviations: (a) introduced local `_dyn_tool_log_path` to absorb the `subdir=`/`ext=` mismatch with `artifacts_io.tool_log_path` (Rule 3 — see Deviations), (b) widened reaper race catch to include `OSError` (Rule 2 — see Deviations).
4. **Reaper race handling:** YES — `os.getpgid(cpid)` race when child exits mid-walk is caught by `(ProcessLookupError, PermissionError, OSError)` and the child is skipped (no kill needed, it's already gone). `os.kill(cpid, SIGKILL)` race is caught by the same triple — same outcome: skip.

## Self-Check: PASSED

- `mcp-gateway/src/mcp_gateway/dynamic.py` — FOUND (616 LoC).
- `mcp-gateway/tests/test_dynamic_primitive.py` — FOUND (358 LoC, 28 tests collected).
- `mcp-gateway/tests/fixtures/dns_lookup.c` — FOUND (29 LoC; contains `getaddrinfo("example.com"`).
- `mcp-gateway/tests/fixtures/setsid_escape.c` — FOUND (34 LoC; contains `setsid()`).
- `mcp-gateway/src/mcp_gateway/jobs.py` — MODIFIED (+12 lines; `post_terminal_hook` field + hook invocation).
- Commit `a25cebf` (Task 1) — FOUND in git log.
- Commit `aac9572` (Task 2) — FOUND in git log.

## Next Phase Readiness

- **Plan 03 (gdb session driver, sessions/gdb.py)** is unblocked — Plan 02 didn't touch the sessions/ package, and Plan 01's BaseSession + kind-aware SessionRegistry are still in place. Plan 03 will add a separate session driver, not a JobToolSpec; it does not consume `_reaper_hook`.
- **Plan 04 (dynamic MCP tool surface, tools/dynamic.py)** can now register `run_strace`/`run_ltrace`/`run_qemu_user` MCP tools that internally call `start_tool_job(tool="strace"|...)` — every dispatch goes through the registered specs from Plan 02. Plan 04 will own the env-gated import of `mcp_gateway.dynamic` from `tools/__init__.py` (which is why the tool count remained at 54 in this plan — dynamic.py is NOT yet imported by tools/).
- **Plan 05 (lifespan wiring)** will assign `mcp_gateway.dynamic.CAPABILITIES = probe_all()` once at app startup, gated by `MCP_GATEWAY_DYNAMIC_TOOLS=1`.
- **Plan 06 (e2e + slow tests)** will compile `dns_lookup.c` and `setsid_escape.c` inside the container, then exercise `wrap_netns` blocking DNS and `reap_followfork_strays` killing setsid grandchildren.
- **Tool-count invariant** (`test_tool_list.py::test_tool_count_in_range`) still **54** — Plan 02 added zero MCP tools; the 3 specs are job-tool specs only, surfaced via `start_tool_job` (Phase 9 plumbing).

---
*Phase: 11-dynamic-lab-mode-env-gated*
*Completed: 2026-05-20*
