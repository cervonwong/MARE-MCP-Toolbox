---
phase: 11-dynamic-lab-mode-env-gated
plan: 03
subsystem: gdb-session-driver
tags: [dynamic, gdb, sessions, mi3, allowlist, netns]

requires:
  - phase: 11-dynamic-lab-mode-env-gated-plan-01
    provides: sessions/_base.py BaseSession dataclass + SessionRegistry.open(kind="gdb") deferred-import dispatch
  - phase: 11-dynamic-lab-mode-env-gated-plan-02
    provides: mcp_gateway.dynamic.wrap_netns prefix builder for per-call netns isolation
provides:
  - mcp_gateway.sessions.gdb module (420 LoC) — GdbSession dataclass, MI prefix allowlist + deny regex, validate_mi_command, sentinel-framing helpers, lockdown init batch, _build_gdb_argv, _open_gdb driver, 2 env-var module constants (GDB_OPEN_TIMEOUT_S / GDB_CMD_TIMEOUT_S)
  - sessions/__init__.py extended re-exports: GdbSession, GDB_OPEN_TIMEOUT_S, GDB_CMD_TIMEOUT_S, validate_mi_command
  - 25 Wave-0 RED-then-GREEN tests in tests/test_gdb_session.py (55 with parametrize expansion) locking D-04..D-09 contract: 20-vector positive allowlist matrix + 19-vector negative deny matrix + 3-vector composite negative matrix + sentinel framing + lockdown batch + argv shape + dataclass shape + env-var constants + re-export identity + 2 slow integration tests (gated)
affects: [11-04 dynamic MCP tool surface, 11-05 lifespan wiring, 11-06 e2e]

tech-stack:
  added: []
  patterns:
    - "Dataclass inheritance with tail-defaulted fields (matches R2Session): subclass-added fields all carry defaults so BaseSession's tail-defaulted fields (command_count/closed/close_reason/kind) don't violate the Python 3.11 dataclass-inheritance rule"
    - "Allowlist-then-deny double-check: validate_mi_command runs strict positive-prefix lookup FIRST, then a deny-regex anchored on `(?:^|;|\\n|\\s)` SECOND — catches composite vectors like `-info-functions ; python print(1)` where the leading prefix is allowlisted but the chained call is denied"
    - "Sentinel framing via -data-evaluate-expression with escaped inner quotes: write `cmd\\n-data-evaluate-expression \"\\\"<sentinel>\\\"\"\\n` and readuntil terminator substring `^done,value=\"\\\"<sentinel>\\\"\"` — survives gdb's async stop-record interleaving (Pitfall #1)"
    - "Lockdown init batch as ONE write to gdb stdin (10 -gdb-set lines + -gdb-version + sentinel emit) — readuntil-the-sentinel completes only after ALL replies have come back, so the init contract is atomic"
    - "Argv builder NEVER includes -iex / -ex / -x (Pitfall #10) — those flags bypass the MI allowlist; explicit acceptance criterion + test_gdb_argv_does_not_include_iex_ex_x test makes the invariant grep-able"
    - "LEAF-module discipline preserved: gdb.py imports stdlib + mcp_gateway.artifacts_io + mcp_gateway.dynamic.wrap_netns + sessions._base only; NO mcp.server.fastmcp, NO tools.* at top-level"

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/sessions/gdb.py
    - mcp-gateway/tests/test_gdb_session.py
  modified:
    - mcp-gateway/src/mcp_gateway/sessions/__init__.py

key-decisions:
  - "Reused _env_float from sessions._base instead of re-defining a local helper — keeps the bad-value RuntimeError semantics byte-identical to Phase 8 D-14 across all session-kinds (test_gdb_env_validates_bad_values exercises the path)"
  - "Added jit-reader-load and define to the deny regex as explicitly required by the negative-matrix test list — VALIDATION.md DYN-05 row required ≥17 vectors; we ship 19 deny vectors with both jit-reader-load and define present"
  - "Sentinel-emit line placed at the END of the lockdown batch (not interleaved between each -gdb-set line) so the open path uses ONE readuntil-the-sentinel rather than 11 — same wire shape as Phase 8 r2 lockdown"
  - "GdbSession.kind defaults to literal 'gdb' (overrides BaseSession 'r2') so `registry.list()` snapshots correctly tag gdb entries; mi_version='mi3' and netns_wrapped=True are class-level defaults (D-03)"

requirements-completed: [DYN-05]

duration: ~6 min
completed: 2026-05-20
---

# Phase 11 Plan 03: gdb-MI3 session driver Summary

**Landed `mcp_gateway/sessions/gdb.py` (420 LoC) — the gdb-MI3 session driver with `GdbSession` dataclass, `_open_gdb` driver under `wrap_netns`, per-command sentinel framing (`-data-evaluate-expression "\"<sentinel>\""`), mandatory 10-line lockdown init batch (D-05), strict MI prefix allowlist (49 entries) + deny regex (15 vectors), and 2 new env-var module constants (GDB_OPEN_TIMEOUT_S=30.0, GDB_CMD_TIMEOUT_S=60.0). Extended `sessions/__init__.py` with 4 new re-exports. All 25 Wave-0 tests (55 with parametrize) flipped RED→GREEN; Plan 01 + Plan 02 + Phase 8 + tool-count regressions stay green.**

## Performance

- **Duration:** ~6 min (2026-05-20T00:46:01Z → 2026-05-20T00:51:42Z)
- **Started:** 2026-05-20T00:46:01Z
- **Completed:** 2026-05-20T00:51:42Z
- **Tasks:** 2 (both TDD: RED test commit then GREEN implementation commit)
- **Files created:** 2 (sessions/gdb.py, tests/test_gdb_session.py)
- **Files modified:** 1 (sessions/__init__.py — 14-line additive edit)

**Line counts:**

| File | LoC |
|------|-----|
| mcp-gateway/src/mcp_gateway/sessions/gdb.py | 420 |
| mcp-gateway/tests/test_gdb_session.py | 350 |
| mcp-gateway/src/mcp_gateway/sessions/__init__.py diff | +14 (3 new from-import entries inside existing tuple, 4 new __all__ entries, 1 new force-reload submodule name) |

The plan's <output> field estimated gdb.py at ~300 LoC; we landed 420 LoC because the verbatim docstring header, the explicit per-prefix `_ALLOWED_MI_PREFIXES` tuple (49 entries with comments grouping them by class), the 15-clause deny regex with inline annotations, and the defensive error paths inside `_open_gdb` (ProcessLookupError handling for getpgid race, OSError swallow on transcript-header writes) all pushed past the estimate.

## Accomplishments

- **`GdbSession` dataclass landed** — subclass of `BaseSession` with 6 gdb-specific fields (sample_sha256, sample_path, gdb_version, mi_version="mi3", follow_fork_mode="parent", netns_wrapped=True); kind defaults to literal "gdb" overriding BaseSession's "r2". Dataclass inheritance shape verified by `test_gdb_session_dataclass_fields`.
- **Strict MI prefix allowlist** — `_ALLOWED_MI_PREFIXES` tuple with 49 entries (state-inspection, stack, exec-control, breakpoints, threads, symbols, var-objects, framing). `is_allowed_mi(cmd)` does a stripped-prefix lookup; `test_mi_allowlist_positive` parametrize covers 20 representative entries.
- **Deny regex with 15 vectors** — `_DANGEROUS_GDB_RE` anchored on `(?:^|;|\n|\s)` so composite expressions like `-info-functions ; python print(1)` are caught. Vectors: `-interpreter-exec\s+console`, `python`, `pi`, `source`, `shell`, `!`, `-gdb-set\s+logging\s+(?:on|file)`, `-target-(?:select|attach)`, `attach`, `add-symbol-file`, `generate-core-file`, `dump\s`, `set\s+inferior-tty`, `jit-reader-load`, `define\s`. `test_mi_allowlist_negative_matrix` parametrize covers 19 deny vectors (including the 17 from CONTEXT.md + `set logging on` + `info threads` CLI-style).
- **Sentinel framing helpers verified byte-identical** — `build_sentinel_emit("__MARE_END_deadbeef__")` returns exactly `b'-data-evaluate-expression "\\"__MARE_END_deadbeef__\\""\n'`; `build_sentinel_terminator("__MARE_END_deadbeef__")` returns exactly `b'^done,value="\\"__MARE_END_deadbeef__\\""'`.
- **Lockdown init batch verified verbatim** — all 10 `-gdb-set` lines present, `-gdb-version` present, sentinel-emit line at the END so readuntil-the-sentinel completes only after every reply has come back.
- **gdb argv EXACTLY 11 elements** — `wrap_netns(["gdb", "--interpreter=mi3", "--quiet", "--nx", "--nh", str(sample_path)])` returns `["unshare", "--net", "--ipc", "--uts", "--", "gdb", "--interpreter=mi3", "--quiet", "--nx", "--nh", str(sample_path)]`. Pitfall #10 invariant locked: `-iex`, `-ex`, `-x` never appear (only inside a code comment; grep confirms not in the argv list).
- **Env-var constants validated at import** — `GDB_OPEN_TIMEOUT_S=30.0`, `GDB_CMD_TIMEOUT_S=60.0`; bad values raise RuntimeError on module load (Phase 8 D-14 pattern reused via shared `_env_float`).
- **`sessions/__init__.py` extended** — 1 new submodule added to the force-reload list, 4 new re-export imports (`GdbSession`, `GDB_OPEN_TIMEOUT_S`, `GDB_CMD_TIMEOUT_S`, `validate_mi_command`), 4 corresponding entries in `__all__`. Phase 8 / Plan 01 re-exports preserved byte-identical.
- **55 Wave-0 tests pass on a host without gdb** — 25 unique test functions + parametrize expansion = 57 collected, 2 deselected (slow integration tests skip cleanly on hosts without gdb+unshare), 55 pass.

## Task Commits

1. **Task 1: Wave-0 RED tests** — `2dc1c7b` (test) — 346 lines in tests/test_gdb_session.py
2. **Task 2: gdb.py + __init__.py extension** — `ef51dc9` (feat) — 420 lines new in sessions/gdb.py, 14 lines added in sessions/__init__.py, 4 lines refined in tests/test_gdb_session.py (env-validates test sys.modules cleanup)

## Files Created/Modified

- `mcp-gateway/src/mcp_gateway/sessions/gdb.py` (NEW, 420 LoC) — gdb-MI3 driver. Imports: stdlib + `mcp_gateway.artifacts_io.{confine_to, ensure_subdir}` + `mcp_gateway.dynamic.wrap_netns` + `._base.{BaseSession, SessionCapReached, _env_float, make_sentinel}`. Re-uses the shared `_env_float` from `_base.py` rather than redefining a local copy. NO `mcp.server.fastmcp`, NO `tools.*` at top-level (Pitfall: tools.samples would be local-only inside _open_gdb if/when needed).
- `mcp-gateway/src/mcp_gateway/sessions/__init__.py` (MODIFIED, +14 lines):
  - Added `mcp_gateway.sessions.gdb` to the force-reload loop so `importlib.reload(mcp_gateway.sessions)` re-evaluates gdb.py env-var constants.
  - Added a `from .gdb import (...)` block re-exporting `GdbSession`, `GDB_OPEN_TIMEOUT_S`, `GDB_CMD_TIMEOUT_S`, `validate_mi_command`.
  - Appended the 4 new symbols to `__all__`.
- `mcp-gateway/tests/test_gdb_session.py` (NEW, 350 LoC) — 25 Wave-0 unique tests, 57 with parametrize: 20 positive allowlist + 19 negative deny + 3 composite negative + 2 sentinel + 2 argv + 1 lockdown + 1 dataclass + 2 env + 2 re-export + 1 prefix-table + 1 non-string + 1 negative-matrix-size + 2 slow integration (gated by gdb + unshare host probes).

## Decisions Made

- **Reused `_env_float` from `sessions._base`** instead of redefining a local copy in gdb.py. This keeps the bad-value RuntimeError semantics byte-identical to Phase 8 D-14 across all session-kinds. The shared helper raises on `-5` / `not_a_float` exactly as Phase 8 r2's tests already assert. `test_gdb_env_validates_bad_values` confirms the path is exercised via gdb's own constants.
- **`jit-reader-load` and `define` ARE in the deny regex.** The VALIDATION.md DYN-05 row required ≥17 deny vectors and the plan's negative-matrix test list explicitly enumerated both. We ship 15 distinct regex alternatives (mapped to 19 deny vectors when CLI-style aliases like `info threads` and `set logging on` — which fail the allowlist BEFORE the regex runs — are counted). Plan output question #4 explicitly resolved YES.
- **Sentinel-emit line placed at the END of the lockdown batch** (not interleaved between each `-gdb-set` line). This means `_open_gdb` issues ONE `readuntil(sentinel-terminator)` rather than 11 — same wire shape as Phase 8 r2 lockdown (which sends 4 `e` commands + 1 `?e <sentinel>` then readuntil-once).
- **GdbSession.kind = "gdb"** as a class-level default override of BaseSession's "r2". `registry.list()` snapshots will tag gdb entries correctly because the snapshot reads `sess.kind` directly (Plan 01 already wired this).
- **Empty-string default for gdb_version** so the dataclass-fields default rule is satisfied even when the gdb version parse misses (e.g., the `~"GNU gdb (...)"` console-stream record isn't where we expect it). The driver writes the gdb_version line best-effort and leaves the field "" if the prefix isn't found.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] sys.modules cleanup in `test_gdb_env_validates_bad_values` was incomplete**

- **Found during:** Task 2 verification (first non-slow run after gdb.py landed)
- **Issue:** The test deliberately drops `sys.modules["mcp_gateway.sessions.gdb"]`, sets a bad env var, re-imports to verify RuntimeError, then resets the env var and re-imports. BUT it left `sys.modules["mcp_gateway.sessions"]` intact — so the PACKAGE module kept its dangling `GdbSession` reference from the FIRST import (pre-test), while the freshly-imported `mcp_gateway.sessions.gdb` had a NEW `GdbSession` class object. Downstream test `test_gdb_symbols_reexported_from_sessions_package` then failed: `_pkg.GdbSession is _gdb.GdbSession` came out False because they were two different class objects with the same fully-qualified name.
- **Fix:** Extended the cleanup block in `test_gdb_env_validates_bad_values` to also drop `sys.modules["mcp_gateway.sessions"]` and re-import the package. The package's force-reload loop then re-runs `importlib.reload(...gdb)`, both layers bind to the same fresh class object, and the identity test passes.
- **Files modified:** mcp-gateway/tests/test_gdb_session.py only.
- **Verification:** `pytest tests/test_gdb_session.py -m "not slow"` → 55 passed, 2 deselected. `pytest tests/test_gdb_session.py tests/test_sessions_package.py tests/test_dynamic_primitive.py tests/test_sessions.py` → 98 passed, 5 skipped.
- **Committed in:** `ef51dc9` (Task 2 commit; this is a test-only Rule-1 deviation landed in the same atomic GREEN commit)

**2. [Rule 2 - Robustness] Added `ProcessLookupError` guard around `os.getpgid(proc.pid)` in `_open_gdb`**

- **Found during:** Task 2 implementation (defensive read of _open_r2's structure)
- **Issue:** The plan's paste-ready `_open_gdb` calls `pgid = os.getpgid(proc.pid)` immediately after `create_subprocess_exec`. On hosts where the spawned process exits IMMEDIATELY (e.g., gdb missing despite the host check, or an exec failure for the sample), the pid is already reaped by the time we call getpgid and `ProcessLookupError` raises out of the driver before the lockdown timeout / killpg cleanup paths can run.
- **Fix:** Wrapped `os.getpgid(proc.pid)` in `try/except ProcessLookupError`; on miss, awaits `proc.wait()` and raises `RuntimeError("gdb process exited before getpgid")`. Same defensive shape as Phase 9's `_spawn_and_drive` Pitfall handling. The init-batch try/except also catches the generic `Exception` superset on the lockdown side, so any subsequent failure still hits the killpg path safely (pgid may be undefined; the surrounding `try` clauses guard against that with `(ProcessLookupError, PermissionError)`).
- **Files modified:** mcp-gateway/src/mcp_gateway/sessions/gdb.py only.
- **Verification:** Unit test `test_gdb_argv_under_wrap_netns` still passes; no real-gdb spawn happens on host without gdb. The defensive path is exercised only on real-gdb hosts where the lockdown could race a quick exit.
- **Committed in:** `ef51dc9`

---

**Total deviations:** 2 auto-fixed (1 Rule-1 test sys.modules cleanup bug surfaced by the GREEN flip; 1 Rule-2 robustness widening on getpgid race).
**Impact on plan:** Both fixes are internal to the files Task 2 was already creating/modifying. No additional files touched; no cascading edits to Plan 01 / Plan 02 / Phase 6/7/8/9/10 callers.

## Issues Encountered

- **`tests/jobs/test_list_tool_jobs.py` test-ordering flakiness** (out of scope, pre-existing per 11-01 and 11-02 SUMMARYs) — confirmed unchanged by Plan 03. Already documented as Plan 04 (dynamic MCP surface) or test-isolation hygiene concern.
- **Full-suite parallel runs surface 2 pre-existing failures**: `tests/jobs/test_errors.py::test_unknown_tool_shape` and `tests/test_acl_available.py::test_setfacl_on_path`. The first is the same test-ordering flake documented in 11-01-SUMMARY ("test_unknown_tool_shape and test_specs_* reported failures that disappeared when each file was run in isolation"); the second is the pre-existing host-environment issue (acl pkg ships in container build, not on WSL executor). In isolation each test that the full suite reports as failing for `tests/test_dynamic_primitive.py` (the registration tests) PASSES — confirmed via `pytest tests/test_dynamic_primitive.py` → 28 passed.
- **Host pytest cache permission warnings** (informational): `.pytest_cache/v/cache/nodeids` / `lastfailed` not writable on the WSL executor — same noise reported in 11-01 and 11-02 SUMMARYs. Pre-existing host artifact.

## Verification

All `<verification>` commands from the plan pass:

- `pytest mcp-gateway/tests/test_gdb_session.py -m "not slow"` → **55 passed, 2 deselected** exit 0.
- `pytest mcp-gateway/tests/test_sessions_package.py` → **passes** (Plan 01 regression preserved, exercised together with gdb_session below).
- `pytest mcp-gateway/tests/test_dynamic_primitive.py` → **28 passed** exit 0 (Plan 02 regression preserved).
- `pytest mcp-gateway/tests/test_tool_list.py` → **5 passed** exit 0 (tool count still 54 because dynamic surface is not wired yet — that's Plan 04).
- Combined: `pytest test_gdb_session test_sessions_package test_dynamic_primitive test_sessions` → **98 passed, 5 skipped** exit 0.
- `python -c "from mcp_gateway.sessions import GdbSession, GDB_OPEN_TIMEOUT_S, GDB_CMD_TIMEOUT_S, validate_mi_command; print('OK')"` → `OK 30.0 60.0`.
- `python -c "from mcp_gateway.sessions.gdb import validate_mi_command; validate_mi_command('python print(1)')"` → ValueError raised: "gdb-MI command refused: not in allowlist: 'python print(1)'; allowed prefixes are listed in sessions.gdb._ALLOWED_MI_PREFIXES".

## Acceptance Criteria

- `mcp-gateway/src/mcp_gateway/sessions/gdb.py` exists (420 LoC).
- `grep -c "_ALLOWED_MI_PREFIXES" mcp-gateway/src/mcp_gateway/sessions/gdb.py` → 5 (≥2 acceptance threshold).
- `grep -c "_DANGEROUS_GDB_RE" mcp-gateway/src/mcp_gateway/sessions/gdb.py` → 3 (≥2 acceptance threshold).
- `grep -E "wrap_netns\(inner\)|return wrap_netns" mcp-gateway/src/mcp_gateway/sessions/gdb.py` → `return wrap_netns(inner)` matched.
- `grep -c -- '"--interpreter=mi3"' mcp-gateway/src/mcp_gateway/sessions/gdb.py` → 1 (exactly one match, in `_build_gdb_argv`).
- `grep -nE '"\-iex"|"\-ex"| -x ' mcp-gateway/src/mcp_gateway/sessions/gdb.py` → only line 220 (comment "NEVER include -iex / -ex / -x") — Pitfall #10 invariant locked, no argv entries.
- `grep -c "from .gdb import" mcp-gateway/src/mcp_gateway/sessions/__init__.py` → 1.
- `pytest mcp-gateway/tests/test_gdb_session.py -m "not slow"` → 55 pass.
- Slow tests skip cleanly: `test_gdb_session_roundtrip` + `test_gdb_dangerous_cmd_rejected_runtime` both skip with "gdb unavailable on host".

## Output spec follow-up

The plan's `<output>` section asked for five explicit confirmations:

1. **Exact LoC of gdb.py:** **420 LoC** (plan estimated ~300; overrun due to verbatim docstrings, explicit per-prefix allowlist tuple with comments, defensive error paths).
2. **gdb_version parser:** the driver scans the init buffer for lines starting with `~"GNU gdb` (the MI3 console-stream marker emitted by `-gdb-version`). On hosts without gdb the path is unexercised; on the slow integration test (`test_gdb_session_roundtrip`, host-gated) the field is populated best-effort and the test does not assert on its contents — gdb_version is metadata, not a contract. NO fixture binary required, NO monkeypatching used; the test exercises `/bin/true` as the sample so gdb starts cleanly without auto-loading symbols.
3. **Deviations from the verbatim deny regex:** **none for the regex itself**. Behavioural deviations: (a) reused `_env_float` from `sessions._base` instead of redefining a local copy (matches plan's import directive); (b) added `ProcessLookupError` guard around `os.getpgid` in `_open_gdb` (Rule-2 robustness — see Deviations); (c) test-only Rule-1 fix for `sys.modules["mcp_gateway.sessions"]` cleanup.
4. **`-interpreter-exec console "python print(1)"` raises ValueError:** **CONFIRMED** — both the allowlist (`-interpreter-exec console` is NOT a prefix in `_ALLOWED_MI_PREFIXES` — only `-info-`, `-data-evaluate-expression`, etc., are) AND the deny regex (`-interpreter-exec\s+console` alternative) refuse. Test `test_mi_allowlist_negative_matrix[-interpreter-exec console "python print(1)"]` PASSES.
5. **`jit-reader-load` and `define` in the deny regex:** **YES** — both present as deny alternatives (`jit-reader-load` literal; `define\s` to catch `define foo` etc.). The negative-matrix test parametrize covers both vectors and both raise ValueError.

## Self-Check: PASSED

- `mcp-gateway/src/mcp_gateway/sessions/gdb.py` — FOUND (420 LoC)
- `mcp-gateway/tests/test_gdb_session.py` — FOUND (350 LoC, 57 tests collected)
- `mcp-gateway/src/mcp_gateway/sessions/__init__.py` — MODIFIED (+14 lines; force-reload list + new imports + new __all__ entries)
- Commit `2dc1c7b` (Task 1) — FOUND in git log
- Commit `ef51dc9` (Task 2) — FOUND in git log

## Next Phase Readiness

- **Plan 04 (dynamic MCP tool surface, tools/dynamic.py)** is unblocked. Plan 04 will register `open_gdb_session` / `gdb_exec` / `close_gdb_session` MCP tools that dispatch into `SessionRegistry.open(kind="gdb", ...)` — the kind-aware open is wired via Plan 01's deferred-import dispatch, and the Plan 03 driver makes it functional.
- **Plan 05 (lifespan wiring)** stays unchanged — `mcp_gateway.dynamic.CAPABILITIES = probe_all()` is assigned once at app startup gated by `MCP_GATEWAY_DYNAMIC_TOOLS=1`; gdb capability is part of that probe.
- **Plan 06 (e2e + slow tests)** can exercise `_open_gdb` + `exec_one` + close via the live integration tests (now staged but skipping on host); container builds with gdb available will flip the 2 `@pytest.mark.slow` tests to PASS.
- **Tool-count invariant** (`test_tool_list.py::test_tool_count_in_range`) — still **54** because Plan 03 added zero MCP tools; the gdb driver is consumed by Plan 04's tools.

---
*Phase: 11-dynamic-lab-mode-env-gated*
*Completed: 2026-05-20*
