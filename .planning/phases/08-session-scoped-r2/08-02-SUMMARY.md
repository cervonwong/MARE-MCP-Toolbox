---
phase: 08-session-scoped-r2
plan: 02
subsystem: sessions
tags: [sessions, r2, radare2, async, subprocess, primitive, leaf]

# Dependency graph
requires:
  - phase: 06-retoolrunner-artifacts-io-foundation
    provides: confine_to (path-traversal rejection), ensure_subdir (slug-validated mkdir), EXPANDED_CASE_SUBDIRS catalog, env-var sanity pattern (D-08), process-group cleanup contract (D-17)
  - phase: 07-run-shell-typed-static-wrappers-re-artifacts
    provides: depth-2 resource walker pattern (Plan 04 extension target), Wave-0 RED-stub discipline
  - phase: 08-session-scoped-r2 (Plan 01)
    provides: test_sessions.py RED stubs (test_dangerous_regex_present, test_dangerous_regex_matches_matrix, test_env_var_bad_value_raises, test_r2session_dataclass_fields)
provides:
  - mcp-gateway/src/mcp_gateway/sessions.py — SessionRegistry async-context-manager primitive (458 LoC)
  - R2Session dataclass with all 15 D-15 fields locked
  - _DANGEROUS_R2_CMD_RE compiled regex matching D-08 pattern verbatim
  - check_dangerous_cmd(cmd) raising ValueError per D-09
  - 5 env-var module constants (SESSION_IDLE_S, MAX_SESSIONS, R2_CMD_TIMEOUT_S, REAPER_INTERVAL_S, SESSION_OPEN_TIMEOUT_S) with fail-loud RuntimeError on bad values
  - SessionCapReached exception carrying D-18 error dict via to_dict()
  - _reaper_loop with exception-isolated iterations + CancelledError propagation (D-17)
  - SessionRegistry.open with lockdown init batch BEFORE user init_commands (D-03) and pre-spawn validation (D-19 step 3)
  - SessionRegistry.close idempotent + killpg + shielded wait + transcript footer (D-21)
  - SessionRegistry.__aexit__ parallel shutdown sweep via asyncio.gather (Claude's Discretion)
  - strip_ansi + truncate_for_response inline helpers (defense-in-depth; runner.py copies kept private)
affects: [08-03-PLAN, 08-04-PLAN, 08-05-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Primitive-layer pattern: sessions.py is below MCP — never imports mcp.server.fastmcp; Plan 03 tools/r2_sessions.py is the MCP surface that imports from this module"
    - "Inline ANSI-strip + UTF-8-safe truncate helpers (vs. importing from runner.py) — sidesteps potential circular-import worry; runner.py's _ANSI_ESCAPE stays module-private"
    - "Async-context-manager registry pattern carries forward from PinnedBackend — __aenter__ starts background reaper task, __aexit__ cancels it + sweeps every open session in parallel via asyncio.gather"
    - "Per-session randomized sentinel via secrets.token_hex(4) (D-04) — eliminates global-sentinel collision risk; line-anchored readuntil framing"
    - "Cap-reject (D-18) over LRU-evict — raises SessionCapReached exception with to_dict() payload that downstream tool surface (Plan 03) returns as the operator-visible error dict"

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/sessions.py
  modified: []

key-decisions:
  - "Followed Plan 02 verbatim — paste-ready code block from the <action> section used unchanged; zero deviations from D-01..D-18"
  - "Picked the inline-copy path for ANSI-strip / UTF-8 truncate helpers (Claude's Discretion bullet) rather than widening runner.py's _ANSI_ESCAPE visibility — keeps runner.py untouched and sessions.py self-contained"
  - "Lockdown init batch sent as a single newline-joined write + one sentinel emitter (D-03) — bounded by open_timeout_s via asyncio.wait_for around readuntil"
  - "Parallel shutdown via asyncio.gather over open sessions (Claude's Discretion recommendation D-16) — shutdown bounded by slowest killpg, not their sum"

patterns-established:
  - "Module-level env-var read + sanity check + RuntimeError-on-bad-value, mirroring Phase 6 runner.py — testable via importlib.reload(sessions) under monkeypatch.setenv"
  - "Idempotent close() returning the same shape on first call (already_closed: False) and subsequent calls (already_closed: True) — caller never needs to special-case repeat closes"

requirements-completed: [SESS-04, SESS-06]

# Metrics
duration: 2min
completed: 2026-05-18
---

# Phase 8 Plan 02: sessions.py Primitive Summary

Delivered `mcp-gateway/src/mcp_gateway/sessions.py` (458 LoC) — the layer below MCP that owns `SessionRegistry`, `R2Session`, `_DANGEROUS_R2_CMD_RE`, the 5 env-var module constants, and the reaper algorithm. Plan 03 builds the MCP tool layer on top.

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-18T09:41:08Z
- **Completed:** 2026-05-18T09:43:14Z
- **Tasks:** 1
- **Files created:** 1 (`mcp-gateway/src/mcp_gateway/sessions.py`)

## Accomplishments

- Created 458-line `sessions.py` module — within plan's ~280-400 LoC target range plus expected verbose comments
- All 17 acceptance-criteria grep patterns present in the source
- Module imports cleanly: `from mcp_gateway import sessions; print(sessions.MAX_SESSIONS, sessions.SESSION_IDLE_S)` → `8 1800.0`
- `type(sessions._DANGEROUS_R2_CMD_RE)` → `<class 're.Pattern'>`
- 8 `log.info / log.exception` call sites (well above ≥4 verification target)
- Flipped 4 RED tests from Plan 01 to GREEN as designed; 3 other Wave-0 stubs remain hasattr-passable (they still GREEN-pass against this module; Plan 05 replaces their bodies with full behavioural assertions)
- Zero regression in the broader Phase 6/7 test surface — pre-existing 5 RED tests are exactly the ones Plans 03/04 own (D-26 catalog augment, Plan 03 MCP-surface stubs, host-missing setfacl)

## Task Commits

- **Task 1: Create sessions.py primitive** — `8829c3b` `Add sessions.py primitive layer for Phase 8 (SessionRegistry, R2Session, dangerous-cmd regex)`

## D-XX Coverage Table

| Decision | Implementation in sessions.py |
|---------|-------------------------------|
| D-01 | Raw asyncio + sentinel-marker framing — no r2pipe import, no `to_thread.run_sync` |
| D-02 | `asyncio.create_subprocess_exec("r2", "-2", "-q0", str(sample_path), ..., start_new_session=True)` |
| D-03 | Lockdown batch (`scr.interactive=false / scr.color=0 / scr.html=0 / cfg.user=mare`) sent BEFORE user init_commands |
| D-04 | `sentinel = f"__MARE_END_{secrets.token_hex(4)}__"` — per-session randomized |
| D-06 | Only imports `mcp_gateway.artifacts_io` (and stdlib); does NOT import from `tools/*` |
| D-08 | `_DANGEROUS_R2_CMD_RE = re.compile(r"(?:^|;|\||\n)\s*(?:#!|R!|!)")` — full-string scan |
| D-09 | `check_dangerous_cmd(cmd)` raises `ValueError("dangerous r2 command refused: shell-escape prefix '!' / '#!' / 'R!' is blocked by the gateway wrapper")` |
| D-13 | Transcript header + footer written to `r2-sessions/<session_id>-transcript.log` via `confine_to` |
| D-14 | All 5 env vars read once at module import via `_env_float` / `_env_int`; fail loud on bad parses or negative values |
| D-15 | `@dataclasses.dataclass class R2Session` with all 15 fields locked (session_id, case_dir, sample_sha256, sample_path, proc, pgid, lock, sentinel, transcript_path, opened_at, opened_iso, last_used_at, command_count, closed, close_reason) |
| D-16 | `SessionRegistry` async-context-manager — `__aenter__` starts reaper task; `__aexit__` cancels reaper + parallel `asyncio.gather(close(...))` over open sessions |
| D-17 | `_reaper_loop` per-iteration `try/except Exception` (CancelledError re-raised); snapshotted via `list(self._sessions.items())` to avoid mutation-during-iteration |
| D-18 | `SessionCapReached(max, open_count, existing)` raised before any r2 spawn; `to_dict()` returns the D-18 error dict shape (`{error: 'session cap reached', max, open_count, existing}`) |
| D-19 (step 3) | `for ic in init_commands: check_dangerous_cmd(ic)` BEFORE any subprocess spawn |
| D-21 | `close()` idempotent — second call returns `already_closed: True`; killpg + `asyncio.shield(proc.wait())` + transcript footer |
| Helpers | Inline `strip_ansi` + `truncate_for_response` (Claude's Discretion: chose inline copies over widening runner.py visibility) |

## Test-Flip Table

| Test | Plan 01 State | This Plan State | Plan that flips behavioural |
|------|---------------|-----------------|----------------------------|
| `test_dangerous_regex_present` | RED (ImportError) | **GREEN** (full assert) | — (this plan) |
| `test_dangerous_regex_matches_matrix` | RED (ImportError) | **GREEN** (full assert) | — (this plan) |
| `test_env_var_bad_value_raises` | RED (ImportError) | **GREEN** (full assert) | — (this plan) |
| `test_r2session_dataclass_fields` | RED (ImportError) | **GREEN** (full assert) | — (this plan) |
| `test_reaper_kills_idle` | RED (ImportError) | hasattr-passable stub (GREEN against this module's `SessionRegistry`) | Plan 05 (behavioural body) |
| `test_cap_reject` | RED (ImportError) | hasattr-passable stub (GREEN against this module's `SessionRegistry`) | Plan 05 (behavioural body) |
| `test_lifespan_teardown_kills_all` | RED (ImportError) | hasattr-passable stub (GREEN against this module's `SessionRegistry`) | Plan 05 (behavioural body) |
| `test_expanded_case_subdirs_contains_r2_sessions` | RED (AssertionError: "r2-sessions" not in catalog) | unchanged RED | Plan 04 (D-26 catalog extension) |

`pytest tests/test_sessions.py` → 7 passed, 1 failed (the D-26 catalog assertion that Plan 04 fixes — per Plan 01 SUMMARY's design).

## Decisions Made

Followed Plan 02 verbatim. Two Claude's Discretion calls applied per the plan's notes:

1. **Inline ANSI/truncate helpers** rather than widening runner.py's `_ANSI_ESCAPE` visibility — keeps both modules self-contained and avoids the (minor) circular-import worry. Runner.py untouched.
2. **Parallel shutdown sweep** via `asyncio.gather` in `__aexit__` — shutdown duration bounded by slowest killpg, not their sum.

## Deviations from Plan

None — plan executed exactly as written. The paste-ready code block from the `<action>` section worked on first import + first test run.

The one expected wrinkle the plan called out — `"r2-sessions"` slug acceptance by `ensure_subdir`'s `_validate_slug` regex despite NOT being in `EXPANDED_CASE_SUBDIRS` yet (Plan 04 territory) — was verified before write: the slug regex `^[a-z0-9][a-z0-9_-]{0,39}$` matches `"r2-sessions"` independently of catalog membership.

## Memory / Import Sanity

```
$ cd mcp-gateway && .venv/bin/python -c "from mcp_gateway import sessions; print(sessions.MAX_SESSIONS, sessions.SESSION_IDLE_S); print(type(sessions._DANGEROUS_R2_CMD_RE))"
8 1800.0
<class 're.Pattern'>
```

Module imports cleanly with no side-effects beyond reading the 5 env vars. No subprocess is spawned at import time (subprocess happens only inside `SessionRegistry.open`).

## Issues Encountered

None. One pytest-cache permission warning persists from prior phases (`PytestCacheWarning` on `.pytest_cache/`); does not affect test results.

## User Setup Required

None — no external service configuration required. All four GREEN tests are hermetic (regex match, dataclass shape inspection, env-var monkeypatch + importlib.reload). The integration tests that spawn r2 (in Plan 05) skip cleanly on hosts without `r2` on PATH via `_require_r2_or_skip()` from Plan 01.

## Next Phase Readiness

- **Plan 03 (tools/r2_sessions.py MCP surface):** Can import `SessionRegistry`, `R2Session`, `check_dangerous_cmd`, the 5 env-var constants, `SessionCapReached`, `strip_ansi`, `truncate_for_response` directly from `mcp_gateway.sessions`. The full session lifecycle (open + exec_one + close) is in place; Plan 03 wires the four MCP tools (`open_r2_session`, `r2_cmd`, `close_r2_session`, `list_sessions`) around it.
- **Plan 04 (lifespan + EXPANDED_CASE_SUBDIRS + tool registration):** `SessionRegistry` is an async-context-manager — Plan 04's `app.py::lifespan` can adopt the `async with SessionRegistry(...) as registry:` block as a drop-in. The 3 D-26-dependent tests will flip GREEN once `"r2-sessions"` is added to `EXPANDED_CASE_SUBDIRS`.
- **Plan 05 (integration test bodies):** The 3 remaining hasattr stubs in test_sessions.py (test_reaper_kills_idle, test_cap_reject, test_lifespan_teardown_kills_all) currently pass via `assert hasattr(sessions, "SessionRegistry")`; Plan 05 replaces them with full behavioural bodies that exercise the reaper / cap-reject / shutdown-sweep paths this module ships.
- No blockers; no decisions deferred to downstream waves.

## Self-Check: PASSED

- `mcp-gateway/src/mcp_gateway/sessions.py` — FOUND (458 lines, all 17 acceptance grep patterns present)
- `8829c3b` commit — FOUND (`Add sessions.py primitive layer for Phase 8 (SessionRegistry, R2Session, dangerous-cmd regex)`)
- Import sanity: `from mcp_gateway import sessions` exits 0; `sessions.MAX_SESSIONS == 8`; `sessions.SESSION_IDLE_S == 1800.0`; `type(sessions._DANGEROUS_R2_CMD_RE) == re.Pattern`
- Target 4 GREEN tests: all pass under pytest
- Plan's `min_lines: 250` met (458 actual)
- `log.info / log.exception` count: 8 (≥ 4 target)
- `"class SessionRegistry"` present
- Module is below MCP (grep for `mcp.server.fastmcp` in sessions.py): 0 matches

---
*Phase: 08-session-scoped-r2*
*Completed: 2026-05-18*
