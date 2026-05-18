---
phase: 08-session-scoped-r2
plan: 03
subsystem: tools
tags: [r2, radare2, mcp-tools, session-scoped, asyncio, register-wrapper]

# Dependency graph
requires:
  - phase: 06-retoolrunner-artifacts-io-foundation
    provides: STDOUT_HEAD_KB constant, tool_log_path filename shape (D-09), ensure_subdir slug-validated mkdir
  - phase: 07-run-shell-typed-static-wrappers-re-artifacts
    provides: register-wrapper pattern (module-level coroutine + mcp.tool()(fn) in register()), resolve_case_dir contract (str), resolve_sample contract (str)
  - phase: 08-session-scoped-r2 (Plan 02)
    provides: SessionRegistry, R2Session, SessionCapReached, check_dangerous_cmd, strip_ansi, truncate_for_response, env-var module constants (MAX_SESSIONS, R2_CMD_TIMEOUT_S, SESSION_OPEN_TIMEOUT_S)
provides:
  - mcp-gateway/src/mcp_gateway/tools/r2_sessions.py — MCP surface for 4 r2-session tools (403 LoC)
  - open_r2_session: D-19 contract (resolve_case_dir + resolve_sample + explicit hashlib.sha256 + check_dangerous_cmd pre-validation + cap-error dict on SessionCapReached)
  - r2_cmd: D-11 18-key result dict + D-10 format=json suffix logic + D-20 step c/d asyncio.shield artifact persistence
  - close_r2_session: D-21 idempotent close delegating to SessionRegistry.close
  - list_sessions: D-22 fd_count + last_used_iso + idle_s shape; _fd_count returns -1 on /proc read failure
  - register(mcp): Phase 7 register-wrapper pattern (NO touching tools/__init__.py — that lands in Plan 04)
  - SESS-05 disclaimer (D-23) in all 4 docstrings (full form on open + r2_cmd; short form on close + list)
affects: [08-04-PLAN, 08-05-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Post-definition __doc__ splice for variable-interpolated docstrings: Python's parser attaches __doc__ only when the function body's first expression is a pure string literal. The original plan's `\"\"\"...\"\"\" + _SESS_05_DISCLAIMER_FULL` form is a string-concat expression (not a literal), which strips __doc__ to None. Switched to `{_FULL_DISCLAIMER}` placeholder + post-definition `.replace(...)` assignment, mirroring the close/list short-disclaimer pattern. One-line deviation from plan text, zero behavioural change."
    - "Module-attribute access for env-var-driven constants (sessions.MAX_SESSIONS, sessions.R2_CMD_TIMEOUT_S, sessions.SESSION_OPEN_TIMEOUT_S) so importlib.reload(sessions) in Plan 05 tests propagates; matches plan's CRITICAL CONTRACT CORRECTION 3"
    - "Explicit hashlib.sha256 computation from resolve_sample's str return (NOT tuple destructure); matches plan's CRITICAL CONTRACT CORRECTION 1"

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/tools/r2_sessions.py
  modified: []

key-decisions:
  - "Followed Plan 03 verbatim with one micro-deviation: switched the docstring-concat idiom for open_r2_session and r2_cmd from `\"\"\"...\"\"\" + _DISCLAIMER` (which evaluates to a non-literal expression and yields __doc__=None) to the same post-definition __doc__.replace placeholder pattern used by close_r2_session and list_sessions. This is a Rule 1 fix for a plan bug; the disclaimer text content is unchanged."

patterns-established:
  - "Docstring placeholder + post-definition splice for all variable-interpolated docstrings — uniform across all 4 tools in this module"
  - "Module-attribute access (`sessions.X`) for env-var-driven constants, paired with `from sessions import Y` for pure functions/classes whose identity does not change across reload"

requirements-completed: [SESS-01, SESS-02, SESS-03, SESS-05, SESS-06]

# Metrics
duration: 224s
completed: 2026-05-18
---

# Phase 8 Plan 03: tools/r2_sessions.py MCP Surface Summary

Delivered `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` (403 LoC) — the MCP surface layer that wraps the Plan 02 `SessionRegistry` primitive with four `mcp.tool()`-registerable coroutines (`open_r2_session`, `r2_cmd`, `close_r2_session`, `list_sessions`) plus a `register(mcp)` function. Plan 04 will wire `register` into `tools/__init__.py` and the `app.py::lifespan`.

## Performance

- **Duration:** ~224 s (≈3 min 44 s)
- **Started:** 2026-05-18T09:45:48Z
- **Tasks:** 1
- **Files created:** 1 (`mcp-gateway/src/mcp_gateway/tools/r2_sessions.py`)

## Accomplishments

- 403-line module delivered (≥350 plan minimum)
- 4 `mcp.tool()` registration calls present in `register(mcp)`
- 19 of 19 positive grep acceptance criteria pass; both negative checks pass (no `from mcp_gateway.sessions import MAX_SESSIONS/...`; no `sample_sha, sample_path = resolve_sample(...)` destructure)
- `test_sess05_disclaimer_in_docstrings` flips GREEN (was hasattr-passable RED stub; this plan delivers the full docstring content)
- Plan 01 Wave-0 hasattr-checks for `open_r2_session`, `r2_cmd`, `close_r2_session`, `list_sessions` collect + execute past the import line
- `pytest tests/test_r2_sessions.py` → 1 passed, 12 skipped (all behavioural tests skip cleanly on this host because `r2` is not on PATH; container image provides `radare2`)
- Zero edits leaked into `tools/__init__.py`, `session_state.py`, or `app.py` — those are Plan 04's responsibility

## Task Commits

- **Task 1: Create tools/r2_sessions.py with 4 MCP tools + register(mcp)** — `f10179c` `Add r2-session MCP tool surface for Phase 8 (open/r2_cmd/close/list + register)`

## D-XX Coverage Table

| Decision | Implementation in tools/r2_sessions.py |
|---------|---------------------------------------|
| D-05 | Module lives at `mcp_gateway/tools/r2_sessions.py` (sibling to `tools/shell.py`); register-wrapper pattern from Phase 7 |
| D-06 | Imports from `mcp_gateway.sessions` (module + names) + `mcp_gateway.artifacts_io` + `mcp_gateway.runner` + `mcp_gateway.session_state` + `tools.case_dirs` + `tools.samples`; does NOT modify `tools/__init__.py` (Plan 04) |
| D-10 | `_ends_in_j(cmd)` + `sent_cmd = cmd + "j" if (format == "json" and not _ends_in_j(cmd)) else cmd`; best-effort `json.loads` wrapped in try/except → `parsed_json=None + parse_error` on fail |
| D-11 | r2_cmd returns the 18-key result dict: 12 Phase-6 base keys + 6 r2 extensions (`session_id`, `session_invalidated`, `format`, `parsed_json`, `parse_error`, `transcript_path`); `stderr_head=""`, `stderr_truncated=False`, `stderr_bytes_total=0` (sentinel framing reads stdout only) |
| D-12 | `_persist_artifacts` writes per-command log via `tool_log_path(case_dir, "r2_cmd")` (Phase 6 D-09 filename shape) |
| D-13 | Transcript block format: `>>> CMD <ts> <dur>s format=<f> [INVALIDATED]\n<cmd>\n<<< OUTPUT bytes=<b> truncated=<bool>\n<output>\n--- END ---\n` |
| D-19 | open_r2_session: resolve_case_dir → resolve_sample → explicit `hashlib.sha256(sample_path.read_bytes()).hexdigest()` → pre-spawn `check_dangerous_cmd(ic)` for each init_command → `await registry.open(...)` → return D-19 result dict OR D-18 error dict on SessionCapReached |
| D-20 | r2_cmd: validate session_id (ValueError on miss) → check_dangerous_cmd(cmd) → format=json suffix logic → `async with sess.lock: exec_one` → on timeout: `registry.close(session_id, reason="timeout")` + return with `session_invalidated=True, exit_code=-9` → `asyncio.shield(_persist_artifacts(...))` for the per-command-log + transcript writes |
| D-21 | close_r2_session: delegates to `registry.close(session_id, reason="user")`; idempotency is inherited from the registry (Plan 02 already returns `already_closed: True` on second call) |
| D-22 | list_sessions: enumerates `registry.list()`, looks up live R2Session for each via `registry.get`, adds `fd_count` via `_fd_count(sess.proc.pid)` (returns -1 on `OSError` from `/proc/<pid>/fd` read), `last_used_at` as ISO8601, `idle_s` as `now - sess.last_used_at` |
| D-23 | SESS-05 full disclaimer in `open_r2_session` + `r2_cmd` docstrings ("shared across all MCP clients", "bearer token", "v1.2 (GW-V2-03)"); short cross-reference disclaimer ("See `open_r2_session` for the cross-client-sharing limitation") in `close_r2_session` + `list_sessions` docstrings |
| D-25 | No new collision check needed; Phase 7's `assert_no_collisions` already covers ALL gateway-native tool names |

## Tool Signatures + Docstring Lengths

| Tool | Signature | __doc__ length | Disclaimer form |
|------|-----------|-----------|-----------------|
| `open_r2_session` | `async def open_r2_session(case_dir: str, sample: str, *, init_commands: Optional[list[str]] = None, open_timeout: Optional[float] = None) -> dict` | 1313 chars | FULL |
| `r2_cmd` | `async def r2_cmd(session_id: str, cmd: str, *, format: Literal["text", "json"] = "text", timeout: Optional[float] = None) -> dict` | 1566 chars | FULL |
| `close_r2_session` | `async def close_r2_session(session_id: str) -> dict` | 225 chars | SHORT (See `open_r2_session` for …) |
| `list_sessions` | `async def list_sessions() -> dict` | 218 chars | SHORT (See `open_r2_session` for …) |

## Test-Flip Table

| Test | Before this plan | After this plan | Plan that flips behavioural |
|------|------------------|-----------------|----------------------------|
| `test_sess05_disclaimer_in_docstrings` | RED (ImportError on `mcp_gateway.tools.r2_sessions`) | **GREEN** (asserts disclaimer phrases in 4 docstrings) | — (this plan) |
| `test_aaa_aflj_persists` | RED (ImportError) | hasattr-passable stub (collects + runs past import; skipped on no-r2 host) | Plan 05 (behavioural body) |
| `test_r2_cmd_result_shape` | RED (ImportError) | hasattr-passable stub | Plan 05 |
| `test_format_json_iij` | RED (ImportError) | hasattr-passable stub | Plan 05 |
| `test_format_json_non_json_command` | RED (ImportError) | hasattr-passable stub | Plan 05 |
| `test_close_idempotent` | RED (ImportError) | hasattr-passable stub | Plan 05 |
| `test_list_fd_count_nonneg` | RED (ImportError) | hasattr-passable stub | Plan 05 |
| `test_dangerous_cmd_refusal_matrix` | RED (ImportError) | hasattr-passable stub | Plan 05 |
| `test_lockdown_init_took_effect` | RED (ImportError) | hasattr-passable stub | Plan 05 |
| `test_hung_cmd_kills_session` | RED (ImportError) | hasattr-passable stub | Plan 05 |
| `test_cancel_propagates_to_killpg` | RED (ImportError) | hasattr-passable stub | Plan 05 |
| `test_transcript_captures_three_cmds` | RED (ImportError) | hasattr-passable stub | Plan 05 |
| `test_per_command_log_filename_shape` | RED (ImportError) | hasattr-passable stub | Plan 05 |

`pytest tests/test_r2_sessions.py` → 1 passed, 12 skipped (the 12 behavioural tests skip cleanly via `_require_r2_or_skip()` because the host venv lacks `r2`; container provides `radare2`).

## Contract Correctness Confirmations

- **`resolve_sample` consumed as `str`:** `sample_path = Path(resolve_sample(sample))` — no tuple destructure (`sample_sha, sample_path = resolve_sample(...)` form is absent; verified by negative grep).
- **sha256 computed via hashlib:** `sample_sha = hashlib.sha256(sample_path.read_bytes()).hexdigest()` — present and in the right place (after `resolve_sample`, before `registry.open(...)`).
- **Env-var constants accessed via `sessions.<NAME>`:** `sessions.MAX_SESSIONS`, `sessions.R2_CMD_TIMEOUT_S`, `sessions.SESSION_OPEN_TIMEOUT_S` all present; the bind-by-value anti-pattern `from mcp_gateway.sessions import MAX_SESSIONS` is absent (verified by negative grep).
- **No edits leaked into `tools/__init__.py`, `session_state.py`, or `app.py`:** `git diff` against those three paths is empty — Plan 04 owns those changes.

## Decisions Made

Followed Plan 03 verbatim with one micro-deviation documented under Deviations.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `"""…""" + _SESS_05_DISCLAIMER_FULL` docstring-concat idiom for open_r2_session and r2_cmd**

- **Found during:** Task 1 verification — `r2_sessions.open_r2_session.__doc__[:200]` raised `TypeError: 'NoneType' object is not subscriptable` because `__doc__` was `None`.
- **Issue:** Python's parser attaches `__doc__` ONLY when the function body's first expression is a pure string-literal. The plan's `"""…""" + _SESS_05_DISCLAIMER_FULL` form is a string-concat expression, not a literal, so the parser doesn't recognize it as a docstring — the resulting `__doc__` is `None` and `test_sess05_disclaimer_in_docstrings` would fail on `fn.__doc__ is not None`.
- **Fix:** Switched both `open_r2_session` and `r2_cmd` docstrings to the SAME placeholder + post-definition splice pattern that the plan ALREADY uses for `close_r2_session` and `list_sessions`. The docstring now contains `{_FULL_DISCLAIMER}` as a placeholder, and a `<fn>.__doc__ = (<fn>.__doc__ or "").replace("{_FULL_DISCLAIMER}", _SESS_05_DISCLAIMER_FULL)` line immediately after the function definition splices the full disclaimer in. Disclaimer text content is identical to the plan; only the attachment mechanism differs.
- **Files modified:** `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py`
- **Commit:** `f10179c`
- **Acceptance impact:** `cd mcp-gateway && python -c "from mcp_gateway.tools import r2_sessions; print(r2_sessions.open_r2_session.__doc__[:200])"` now succeeds and prints the docstring beginning, matching the plan's exact acceptance criterion. `pytest tests/test_r2_sessions.py::test_sess05_disclaimer_in_docstrings -x` GREEN.

## Authentication Gates

None — no external service interaction during this plan.

## Memory / Import Sanity

```
$ cd mcp-gateway && .venv/bin/python -c "from mcp_gateway.tools import r2_sessions; print(r2_sessions.open_r2_session.__doc__[:200])"
Open a persistent r2 analysis session against `sample` in `case_dir`.

    Arguments:
        case_dir: case directory (validated via resolve_case_dir).
        sample: sample reference -- sha256 or case-dir-r
```

Module imports cleanly. `session_state.SESSION_REGISTRY` is not yet defined (Plan 04 adds it), but that attribute is only accessed inside `_require_registry()` which is called at tool-invocation time, not at import time — so the import remains clean. Plan 04 will add the slot and wire the lifespan.

## Issues Encountered

One bug in the plan's paste-ready code block (docstring-concat idiom) — fixed inline per Rule 1, documented under Deviations. No other issues.

One pytest-cache permission warning persists from prior phases (`PytestCacheWarning` on `.pytest_cache/`); does not affect test results.

## User Setup Required

None — no external service configuration required. `test_sess05_disclaimer_in_docstrings` is fully hermetic (string assertions on `fn.__doc__`). The 12 behavioural tests skip cleanly on hosts without `r2` on PATH via Plan 01's `_require_r2_or_skip()`; container Kali image provides `radare2`.

## Next Phase Readiness

- **Plan 04 (EXPANDED_CASE_SUBDIRS + lifespan wiring + tool registration):** Plan 04 imports `register` from `mcp_gateway.tools.r2_sessions` and calls it from `tools/__init__.py::register_all_tools`. Plan 04 also adds `SESSION_REGISTRY: Optional["SessionRegistry"] = None` to `session_state.py` and wires `async with SessionRegistry(...) as registry: session_state.SESSION_REGISTRY = registry` into `app.py::lifespan`. The four tool functions in this module are ready to consume `session_state.SESSION_REGISTRY` the moment Plan 04 populates it.
- **Plan 05 (integration test bodies):** The 12 RED-stub bodies in `test_r2_sessions.py` currently end in `assert hasattr(r2_sessions, "<fn>")` and pass via that assertion. Plan 05 replaces them with full behavioural assertions per Plan 01's per-test contract.
- No blockers; no decisions deferred to downstream waves.

## Self-Check: PASSED

- `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` — FOUND (403 lines, all 19 positive grep acceptance criteria present, both negative checks pass)
- Commit `f10179c` — FOUND (`Add r2-session MCP tool surface for Phase 8 (open/r2_cmd/close/list + register)`)
- Import sanity: `from mcp_gateway.tools import r2_sessions` exits 0; all 5 callables (`open_r2_session`, `r2_cmd`, `close_r2_session`, `list_sessions`, `register`) present and `callable(...)` true
- `pytest tests/test_r2_sessions.py::test_sess05_disclaimer_in_docstrings -x` → 1 passed
- `pytest --collect-only tests/test_r2_sessions.py` → 13 tests collected, 0 collection errors
- `pytest tests/test_r2_sessions.py` → 1 passed, 12 skipped (host lacks r2; expected)
- Grep `mcp.tool()` count: 4 (target ≥ 4)
- Negative `from mcp_gateway.sessions import MAX_SESSIONS|R2_CMD_TIMEOUT_S|SESSION_OPEN_TIMEOUT_S`: 0 matches (bind-by-value anti-pattern absent)
- Negative `sample_sha, sample_path = resolve_sample(...)`: 0 matches (tuple-destructure anti-pattern absent)
- `git diff` against `tools/__init__.py`, `session_state.py`, `app.py`: empty (no leaked edits)

---
*Phase: 08-session-scoped-r2*
*Completed: 2026-05-18*
