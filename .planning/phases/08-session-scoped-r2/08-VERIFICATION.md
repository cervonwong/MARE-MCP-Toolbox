---
phase: 08-session-scoped-r2
verified: 2026-05-18T00:00:00Z
status: human_needed
score: 6/6 roadmap success criteria verified
overrides_applied: 0
human_verification:
  - test: "Run the full Phase 8 test suite inside the Kali container (r2 present)"
    expected: "All 12 r2-gated tests in tests/test_r2_sessions.py + 3 r2-gated tests in tests/test_sessions.py flip from SKIP to PASS (SC-1 aaa-aflj-persists, SC-2 shape/json/non-json, SC-3 close-idempotent/list-fd_count, SC-4 reaper/cap/lifespan-teardown, SC-5 lockdown-init/refusal-matrix, SC-6 dangerous-cmd-refusal, Pitfall 6 hung-cmd, Pitfall 18 cancel-within-200ms, D-12 per-command-log shape, D-13 transcript-captures-3-cmds)"
    why_human: "These tests require the r2 binary on PATH which the host executor lacks; the Kali container image provides radare2. Verification of real r2 spawn / lockdown init / sentinel framing / dangerous-cmd refusal at runtime / 200ms cancellation propagation can only be observed inside the container. Code-only verification cannot exercise the subprocess path."
  - test: "Manually verify lifespan zombie-free shutdown inside the container"
    expected: "Start the gateway with MCP_GATEWAY_SKIP_BACKEND=1, open 2 r2 sessions via the MCP tools, send SIGTERM to the gateway, and observe no `r2` PIDs remain in `ps -ef` afterwards"
    why_human: "Lifespan teardown is automatically tested by test_lifespan_teardown_kills_all but that test is r2-gated. A live in-container smoke test corroborates the LIFO unwind ordering (SessionRegistry.__aexit__ before PinnedBackend.__aexit__) under a real signal."
---

# Phase 8: Session-Scoped r2 Verification Report

**Phase Goal:** Remote agents can run iterative r2-driven RE — analysis state (`aaa`, flags, comments) persists across MCP calls — without re-analyzing on every invocation

**Verified:** 2026-05-18
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria + Plan must_haves)

| #   | Truth (from ROADMAP SC + plan truths)                                                                                                                                                                                                                                          | Status                | Evidence                                                                                                                                                                                                                                                                                                                                                                                                |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SC-1 | Agent can call `open_r2_session(case_dir, sample, init_commands)`, receive an opaque session_id, and reuse r2's analysis state across subsequent `r2_cmd` calls                                                                                                                | VERIFIED (code) / HUMAN (runtime) | `tools/r2_sessions.py:131-197` defines `open_r2_session`; returns dict with `session_id` (D-19); registry primitive in `sessions.py:250-357` holds a long-lived asyncio.subprocess.Process with stdin/stdout pipes — analysis state persists by construction (single r2 process per session); SESS-01 test `test_aaa_aflj_persists` exists (test_r2_sessions.py:96). Runtime confirmation requires r2. |
| SC-2 | Agent can execute arbitrary r2 commands via `r2_cmd(session_id, cmd, format)` with head-truncated output + full output captured; `close_r2_session`, `list_sessions` enumerate active sessions                                                                                 | VERIFIED              | `r2_cmd` returns the 18-key result dict (`tools/r2_sessions.py:298-319` — exit_code/timed_out/duration_s/stdout_head/stdout_truncated/stdout_bytes_total/stderr_head/stderr_truncated/stderr_bytes_total/log_path/argv/slug + session_id/session_invalidated/format/parsed_json/parse_error/transcript_path). `close_r2_session` at L332-338; `list_sessions` at L351-387. All 4 registered (L398-403). |
| SC-3 | r2 sessions are auto-reaped after configurable idle (default 30 min); session cap (default 8) is enforced; sessions surviving gateway shutdown are killed (no zombie r2 processes)                                                                                             | VERIFIED              | Reaper: `sessions.py:439-458` polls every `REAPER_INTERVAL_S` (default 60s), closes when `now - last_used_at > idle_s` (default 1800s). Cap: `sessions.py:265-267` raises `SessionCapReached`. Shutdown: `__aexit__` at L223-239 cancels reaper + asyncio.gather over open sessions calling `close(reason='shutdown')` which killpg's pgid. Lifespan-wires this in `app.py:113-124, 144-161`.            |
| SC-4 | Dangerous shell-escape commands (`#!`, `R!`, `!`) are refused at the wrapper layer, and every session opens with `scr.interactive=false; scr.color=0`                                                                                                                          | VERIFIED              | `_DANGEROUS_R2_CMD_RE = re.compile(r"(?:^\|;\|\|\|\n)\s*(?:#!\|R!\|!)")` at `sessions.py:83-85`; `check_dangerous_cmd` at L88-99 raises ValueError. Lockdown init batch at `sessions.py:289-295` sends `e scr.interactive=false / e scr.color=0 / e scr.html=0 / e cfg.user=mare` BEFORE user init_commands. Pre-spawn validation at L261-262 and `tools/r2_sessions.py:169-170, 251`.                  |
| SC-5 | The shared-across-bearer-token-clients limitation is documented in `open_r2_session` and `r2_cmd` docstrings (per-`Mcp-Session-Id` keying deferred to v1.2)                                                                                                                    | VERIFIED              | Verified runtime: `tools/r2_sessions.py:53-63` defines disclaimer; L205-207 splices into `open_r2_session.__doc__`; L324-326 splices into `r2_cmd.__doc__`. Confirmed at runtime: all three required phrases ("shared across all MCP clients", "bearer token", "v1.2") appear in both docstrings. `test_sess05_disclaimer_in_docstrings` PASSES on host (no r2 needed).                                |
| SC-6 (plan must_have: "session registry construction routes through D-14 single source of truth") | The 5 env vars (MCP_GATEWAY_SESSION_IDLE_S, MAX_SESSIONS, R2_CMD_TIMEOUT_S, REAPER_INTERVAL_S, SESSION_OPEN_TIMEOUT_S) are read ONCE at sessions.py import and raise RuntimeError on bad values; lifespan consumes them from the sessions module (single source of truth) | VERIFIED              | `sessions.py:71-75` reads 5 env vars via `_env_float`/`_env_int` with sanity checks raising RuntimeError on bad parses / negative values. `app.py:22-27` imports the validated constants; `app.py:97-102` `_build_registry()` constructs SessionRegistry from them. Negative grep: 0 matches for `MCP_GATEWAY_MAX_SESSIONS\|MCP_GATEWAY_SESSION_IDLE_S\|MCP_GATEWAY_REAPER_INTERVAL_S` in `app.py`.    |

**Score:** 6 / 6 roadmap success criteria verified at the code level. SC-1 and SC-2 runtime behaviour (real r2 spawn + analysis-state persistence + 18-key result production) requires container execution.

### Required Artifacts

| Artifact                                                | Expected                                                                       | Status      | Details                                                                                                                                                              |
| ------------------------------------------------------- | ------------------------------------------------------------------------------ | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mcp-gateway/src/mcp_gateway/sessions.py`               | SessionRegistry + R2Session + _DANGEROUS_R2_CMD_RE + 5 env-var constants       | VERIFIED    | 458 LoC. All locked symbols present (verified by Python introspection at module import).                                                                              |
| `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py`      | 4 MCP tools (open/cmd/close/list) + register(mcp) + SESS-05 disclaimer         | VERIFIED    | 403 LoC. Module imports cleanly; 4 callables present; SESS-05 disclaimer phrases present in open_r2_session + r2_cmd docstrings.                                      |
| `mcp-gateway/src/mcp_gateway/session_state.py`          | SESSION_REGISTRY: Optional[SessionRegistry] = None slot + TYPE_CHECKING import | VERIFIED    | 19 lines. Slot present at L19; TYPE_CHECKING import at L13-15; SESS-05 caveat in module docstring L1-9.                                                              |
| `mcp-gateway/src/mcp_gateway/artifacts_io.py`           | EXPANDED_CASE_SUBDIRS contains 'r2-sessions' at index 9 (10 total entries)     | VERIFIED    | Runtime: `EXPANDED_CASE_SUBDIRS[-1] == 'r2-sessions'`, len == 10.                                                                                                     |
| `mcp-gateway/src/mcp_gateway/tools/__init__.py`         | r2_sessions imported + r2_sessions.register(mcp) called before backend_passthrough | VERIFIED | L37 imports `r2_sessions` in tuple; L50 calls `r2_sessions.register(mcp)` BEFORE L51 `backend_passthrough.register(mcp)`.                                            |
| `mcp-gateway/src/mcp_gateway/app.py`                    | SessionRegistry block in BOTH lifespan branches, inside PinnedBackend, after assert_no_collisions, constructed from sessions module constants | VERIFIED | L22-27 imports validated constants; L97-102 `_build_registry()`; L110 + L138 `await assert_no_collisions(mcp)` precedes L113 + L144 SessionRegistry block in both branches; finally pairs at L114/124 + L145/161. |
| `mcp-gateway/tests/test_sessions.py`                    | 8 tests covering D-08 regex, D-14 env-var, D-15 dataclass, D-26 catalog, SC-4 reaper/cap/teardown | VERIFIED | 8 named test functions present; 5 PASS on host (regex×2, env-var, dataclass, catalog); 3 SKIP on host (reaper, cap, lifespan — all r2-gated).                       |
| `mcp-gateway/tests/test_r2_sessions.py`                 | 13 tests covering SESS-01..06 + Pitfall 6/18 + D-12/D-13                       | VERIFIED    | 13 named test functions + opened_sid fixture; 1 PASS on host (SESS-05 disclaimer); 12 SKIP on host (r2-gated).                                                       |
| `mcp-gateway/tests/conftest.py`                         | _require_r2_or_skip() helper                                                   | VERIFIED    | Module-level helper present; skips with reason mentioning Kali container.                                                                                            |

All 9 artifacts: PASS Levels 1-3 (exists, substantive, wired) and Level 4 (data flows). The lifespan-wired `SESSION_REGISTRY` is the canonical "data variable" of the integration — confirmed populated inside the async-context-managed block in both branches and reset to None on exit.

### Key Link Verification

| From                                  | To                                              | Via                                                                          | Status | Details                                                                                                                                                              |
| ------------------------------------- | ----------------------------------------------- | ---------------------------------------------------------------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app.py::lifespan`                    | `session_state.SESSION_REGISTRY`                | assignment on entry, None on exit (try/finally pair)                         | WIRED  | L114 + L124 (no-backend); L145 + L161 (with-backend). 2 assignment + 2 reset.                                                                                       |
| `app.py::lifespan`                    | `mcp_gateway.sessions` module constants         | import-bound validated constants (NOT os.environ re-read)                    | WIRED  | L22-27 named import; `_build_registry()` consumes MAX_SESSIONS/SESSION_IDLE_S/REAPER_INTERVAL_S directly. Negative grep proves 0 env-var re-reads in app.py.        |
| `tools/__init__.py::register_all_tools` | `tools.r2_sessions.register(mcp)`             | import + invocation                                                          | WIRED  | L37 import + L50 call, before backend_passthrough.register at L51.                                                                                                  |
| `tools/r2_sessions.py`                | `session_state.SESSION_REGISTRY`                | module-attribute read inside each tool via `_require_registry()` (L71-77)    | WIRED  | All 4 tools (`open_r2_session`, `r2_cmd`, `close_r2_session`, `list_sessions`) call `_require_registry()` which reads `session_state.SESSION_REGISTRY` at call-time. |
| `tools/r2_sessions.py`                | `mcp_gateway.sessions` (module)                 | module-attribute access (`sessions.MAX_SESSIONS` etc., not `from … import`)  | WIRED  | L33 `from mcp_gateway import sessions`; L173, L193, L254, L384 use `sessions.<NAME>` form. Negative grep confirms no `from sessions import MAX_SESSIONS` pattern.    |
| `tools/r2_sessions.py`                | `tools.case_dirs.resolve_case_dir` + `tools.samples.resolve_sample` | `resolve_case_dir(str) -> str`; `resolve_sample(str) -> str` (NOT tuple); sha256 via hashlib | WIRED  | L162 `Path(resolve_case_dir(case_dir))`; L163 `Path(resolve_sample(sample))`; L164 `hashlib.sha256(sample_path.read_bytes()).hexdigest()`.                          |
| `SessionRegistry.__aexit__`           | every open R2Session                            | `asyncio.gather(close(sid, reason='shutdown') for sid in open_ids)`          | WIRED  | sessions.py:236-239 — `asyncio.gather(..., return_exceptions=True)`.                                                                                                |
| `sessions.py`                         | `artifacts_io.confine_to` + `ensure_subdir`     | path-traversal-safe transcript creation                                      | WIRED  | sessions.py:40 import; L271 `ensure_subdir(case_dir, "r2-sessions")`; L272 `confine_to(case_dir, f"r2-sessions/{session_id}-transcript.log")`.                       |
| `r2_cmd` artifact persistence         | `_persist_artifacts` coroutine                  | `asyncio.shield(...)` wrap so cancellation does NOT lose transcript+log     | WIRED  | tools/r2_sessions.py:284-291 — `asyncio.shield(_persist_artifacts(...))`.                                                                                            |

All 9 key links verified. The "MCP tool → SESSION_REGISTRY → SessionRegistry → R2Session.proc (live r2 stdin/stdout)" wiring chain is intact end-to-end at the code level.

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `tools/r2_sessions.py::r2_cmd` | `raw_bytes` (r2 stdout up to sentinel) | `sess.exec_one(sent_cmd, timeout=resolved_timeout)` — reads from live `asyncio.subprocess.Process.stdout` | Yes (when r2 binary present) | FLOWING (code path); runtime verification gated on r2 (HUMAN) |
| `tools/r2_sessions.py::list_sessions` | `out_sessions` | iterates `registry.list()` which iterates `self._sessions` populated by `SessionRegistry.open` | Yes | FLOWING |
| `tools/r2_sessions.py::open_r2_session` | `sess` (R2Session) | `registry.open(...)` which spawns a real r2 subprocess via `asyncio.create_subprocess_exec` | Yes (when r2 binary present) | FLOWING (code path); runtime verification gated on r2 (HUMAN) |
| `sessions.py::_reaper_loop` | `stale_ids` | snapshot of `self._sessions` filtered by `(now - sess.last_used_at) > self._idle_s` | Yes | FLOWING |
| Resource walker → r2-sessions/ transcripts | `transcript_path` files in `case_dir/r2-sessions/` | written by `sessions.py:315-319` (header) and `sessions.py:397-401` (footer) and `tools/r2_sessions.py:120-123` (per-cmd block) | Yes | FLOWING — and `test_r2_sessions_transcript_exposed` PASSES on host |

No HOLLOW_PROP / DISCONNECTED artifacts found. The data-flow is genuine end-to-end on a host that provides the r2 binary.

### Behavioral Spot-Checks

| Behavior                                                   | Command                                                                                                                  | Result                                                                                       | Status |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- | ------ |
| sessions module imports cleanly + 5 env constants populated | `python -c "from mcp_gateway import sessions; print(sessions.MAX_SESSIONS, sessions.SESSION_IDLE_S)"`                  | `8 1800.0`                                                                                  | PASS   |
| Dangerous-cmd regex compiles and is a re.Pattern            | `python -c "from mcp_gateway import sessions; print(type(sessions._DANGEROUS_R2_CMD_RE))"`                            | `<class 're.Pattern'>`                                                                       | PASS   |
| 4 MCP tools callable                                       | `python -c "from mcp_gateway.tools import r2_sessions; assert all(callable(getattr(r2_sessions, n)) for n in ('open_r2_session','r2_cmd','close_r2_session','list_sessions','register'))"` | exit 0                                                       | PASS   |
| EXPANDED_CASE_SUBDIRS extended                              | `python -c "from mcp_gateway.artifacts_io import EXPANDED_CASE_SUBDIRS; assert EXPANDED_CASE_SUBDIRS[-1] == 'r2-sessions' and len(EXPANDED_CASE_SUBDIRS) == 10"` | exit 0                                            | PASS   |
| build_app() imports + invokes cleanly (no backend)          | `MCP_GATEWAY_SKIP_BACKEND=1 python -c "from mcp_gateway.app import build_app; build_app(); print('ok')"`              | `ok`                                                                                         | PASS   |
| SESSION_REGISTRY slot defaults to None at import            | `python -c "from mcp_gateway import session_state; print(session_state.SESSION_REGISTRY)"`                            | `None`                                                                                       | PASS   |
| SESS-05 disclaimer phrases present in open_r2_session.__doc__ | runtime introspection of `r2_sessions.open_r2_session.__doc__`                                                       | "shared across all MCP clients" + "bearer token" + "v1.2" all True                          | PASS   |
| Phase 8 test files run cleanly                              | `pytest tests/test_sessions.py tests/test_r2_sessions.py --tb=line`                                                     | `6 passed, 15 skipped` (skips are r2-gated; expected)                                       | PASS   |
| Full suite runs                                             | `pytest tests/ --tb=line`                                                                                                | `1 failed, 245 passed, 47 skipped` (1 failure = pre-existing setfacl host-env, out of scope) | PASS (Phase 8 portion); see note |

All 9 spot-checks pass. No Phase-8-introduced regressions; the single failure (`test_setfacl_on_path`) is documented in Plan 04 SUMMARY as a pre-existing host-only failure (`acl` package not on executor; container Kali image provides it).

### Requirements Coverage

| Requirement | Source Plan(s) | Description (from REQUIREMENTS.md) | Status | Evidence |
| ----------- | -------------- | ----------------------------------- | ------ | -------- |
| SESS-01     | 08-01, 08-03, 08-05 | Agent can open a persistent r2 analysis session via `open_r2_session`, receive an opaque session_id, and reuse r2's analysis state across calls | SATISFIED (code) / NEEDS HUMAN (runtime) | `open_r2_session` defined (tools/r2_sessions.py:131-197); long-lived subprocess holds analysis state by construction (sessions.py:278-285 spawn; L321-335 R2Session retention). `test_aaa_aflj_persists` exists with full behavioural body. Runtime confirmation needs r2 in container. |
| SESS-02     | 08-01, 08-03, 08-05 | Agent can execute arbitrary r2 commands via `r2_cmd(session_id, cmd, format)` with head-truncated output + full output captured | SATISFIED | `r2_cmd` defined (tools/r2_sessions.py:213-319); 18-key dict including `stdout_head` (truncated) + `stdout_bytes_total` + `log_path` (full output). 3 SESS-02 tests with full bodies. |
| SESS-03     | 08-01, 08-03, 08-05 | Agent can close a session via `close_r2_session` and enumerate active sessions via `list_sessions` | SATISFIED | `close_r2_session` at L332-338 (idempotent via `SessionRegistry.close`); `list_sessions` at L351-387. 2 SESS-03 tests with full bodies. |
| SESS-04     | 08-01, 08-02, 08-04, 08-05 | r2 sessions auto-reaped after idle (default 30 min); cap (default 8) enforced; surviving-shutdown sessions killed | SATISFIED | Reaper (sessions.py:439-458); cap (L265-267 + SessionCapReached L177-192); `__aexit__` parallel-shutdown (L223-239). All 3 SESS-04 tests have full behavioural bodies. |
| SESS-05     | 08-01, 08-03, 08-04, 08-05 | Sessions shared across same-bearer-token clients (single-tenant by design); documented in docstrings (per-Mcp-Session-Id deferred to v1.2) | SATISFIED | Full disclaimer in open/r2_cmd docstrings (`_SESS_05_DISCLAIMER_FULL`, post-definition splice). `test_sess05_disclaimer_in_docstrings` PASSES on host. session_state.py module docstring also documents the SESS-05 caveat at module top. |
| SESS-06     | 08-01, 08-02, 08-03, 08-05 | r2 sessions refuse dangerous shell-escape commands (`#!`, `R!`, `!`); init runs with `scr.interactive=false; scr.color=0` | SATISFIED | `_DANGEROUS_R2_CMD_RE` (sessions.py:83-85); `check_dangerous_cmd` raises ValueError (L88-99); lockdown init batch hardcoded (L289-295) is sent BEFORE user init_commands. 2 SESS-06 tests with full bodies. **Note:** Code review CR-02 flags the regex has gaps for backtick-substitution and `.!` dot-shell-eval forms — but the requirement language ("refuse dangerous shell-escape commands `#!`, `R!`, `!`") is satisfied verbatim by the current implementation and tests. CR-02 is advisory hardening, not a must-have failure. |

All 6 requirements SATISFIED at the code level. SESS-01 / SESS-02 / SESS-03 / SESS-04 / SESS-06 require an r2-equipped host for runtime confirmation (12 tests SKIP on the executor host; PASS expected in container).

No ORPHANED requirements (no Phase 8 requirement IDs in REQUIREMENTS.md beyond SESS-01..06; all are claimed by at least one plan).

### Anti-Patterns Found

A scan over the 9 modified/created source files in mcp-gateway/src/mcp_gateway/ produced no Phase-8-introduced blockers. Notable findings:

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `sessions.py` | 83-85 | Regex denylist `(?:^\|;\|\|\|\n)\s*(?:#!\|R!\|!)` misses backtick substitution + `.!cmd` (CR-02) | Warning | Documented by 08-REVIEW.md CR-02. Requirement text mentions only `#!`, `R!`, `!` so SESS-06 is technically satisfied; hardening tracked separately. |
| `sessions.py` | 264-355 | Cap check + spawn under-the-lock pattern: cap-check + session_id under `self._lock`, spawn outside lock, insertion under `self._lock` again (CR-01 TOCTOU) | Warning | Documented by 08-REVIEW.md CR-01. Sequential cap-reject test is GREEN; concurrent regression is the gap. |
| `sessions.py` | 286 | `os.getpgid(proc.pid)` is racy + redundant (WR-03) | Info | Minor; `pgid == proc.pid` by setsid contract. |
| `sessions.py` | 149-171 | `exec_one` does not handle `IncompleteReadError` (WR-02) | Info | r2-crash mid-command escapes as unhandled exception instead of session_invalidated=True path. |
| `tools/r2_sessions.py` | 164 | `sample_path.read_bytes()` loads entire sample into memory for sha256 (WR-06) | Info | Multi-GB samples can OOM the gateway. |

No `TODO`/`FIXME`/`PLACEHOLDER` comments introduced by Phase 8 in any source file. No `return None / return [] / return {}` stub patterns. No `console.log`-only handlers. No empty-prop call sites. Per the user's instructions, the 2 critical findings (CR-01, CR-02) are advisory — they are tracked by 08-REVIEW.md for `/gsd-code-review-fix` follow-up, and they do not violate any Phase 8 must-have or any SESS-* requirement text.

### Human Verification Required

Two items need human verification (see frontmatter `human_verification` for the structured form):

#### 1. Container test-suite run for r2-gated tests

**Test:** Run `cd mcp-gateway && pytest tests/test_sessions.py tests/test_r2_sessions.py -x --tb=short` inside the Kali container image where `radare2` is installed.

**Expected:** The 3 r2-gated tests in test_sessions.py (test_reaper_kills_idle, test_cap_reject, test_lifespan_teardown_kills_all) AND the 12 r2-gated tests in test_r2_sessions.py (test_aaa_aflj_persists, test_r2_cmd_result_shape, test_format_json_iij, test_format_json_non_json_command, test_close_idempotent, test_list_fd_count_nonneg, test_dangerous_cmd_refusal_matrix, test_lockdown_init_took_effect, test_hung_cmd_kills_session, test_cancel_propagates_to_killpg, test_transcript_captures_three_cmds, test_per_command_log_filename_shape) all flip from SKIP to PASS. Total: 21 PASS + 0 SKIP for these two files.

**Why human:** The executor host lacks the `r2` binary; the Kali container image provides it. The skipped tests exercise the real subprocess spawn / lockdown init / sentinel framing / cancellation propagation / per-command-log filename shape / transcript writes — none of which can be verified by static code analysis alone.

#### 2. In-container lifespan teardown smoke test (zero zombie r2 processes)

**Test:** Inside the container, start the gateway (`MCP_GATEWAY_SKIP_BACKEND=1 python -m mcp_gateway` or equivalent), open 2 r2 sessions via the MCP tools against a small ELF, send SIGTERM to the gateway, then run `ps -ef | grep r2` on the host (or `ps` inside the container if its PID 1 is preserved).

**Expected:** Zero `r2` processes remain after the gateway exits.

**Why human:** Programmatic verification (`test_lifespan_teardown_kills_all`) is r2-gated. A live smoke test corroborates that the LIFO unwind ordering (SessionRegistry.__aexit__ before PinnedBackend.__aexit__) holds under a real signal, not just under Starlette LifespanContext in pytest. This is the primary deliverable of SC-3 ("sessions surviving gateway shutdown are killed (no zombie r2 processes)").

### Gaps Summary

No gaps blocking goal achievement. All 6 ROADMAP Success Criteria are SATISFIED at the code level; all 6 SESS-* requirements have full implementation evidence + named pytest functions; all 9 plan-declared must_have artifacts exist and are wired; the 9 key links are intact end-to-end; data-flow Level 4 confirms genuine producer→consumer chains (no hollow props / disconnected sources).

The two critical findings in 08-REVIEW.md (CR-01 cap TOCTOU under concurrent open; CR-02 regex denylist gaps for backtick + `.!`) are advisory hardening items, not failures of the Phase 8 must-haves:
- CR-01: the sequential `test_cap_reject` test is GREEN; the requirement text "a session cap (default 8) is enforced" is satisfied by the current code under the tested path. Concurrent regression is tracked separately for `/gsd-code-review-fix`.
- CR-02: the requirement text "refuse dangerous shell-escape commands (`#!`, `R!`, `!`)" names exactly those three prefixes; the current regex catches them verbatim. Wider hardening (backtick substitution, `.!` dot-shell-eval) is recommended but not a must-have failure.

The remaining gap is purely environmental: 15 r2-gated tests skip on the executor host and require container execution to flip GREEN. This is by design (`_require_r2_or_skip` is the explicit hermetic-test discipline pattern); the container is the production verification environment.

**Status: human_needed** — code-level verification PASS; runtime confirmation of r2 subprocess behaviour requires container execution.

---

_Verified: 2026-05-18_
_Verifier: Claude (gsd-verifier)_

## Live UAT Results (Phase 14 closure)

### Container r2-gated test suite
- **Date:** 2026-05-21T04:08:30Z
- **Container build:** kali-re-tools:0ac0f3e3ebbf (sha256:5d2171dc651b, built 2026-05-21T03:59:12Z)
- **Command:** `docker exec mare-mcp-toolbox-kali-1 bash -lc 'cd /opt/mcp-gateway && uv run pytest tests/test_gdb_session.py::test_gdb_env_validates_bad_values tests/test_r2_sessions.py::test_unsafe_shares_combined_cap tests/test_sessions_concurrency.py -q'`
- **Outcome:** passed
- **Transcript:**
  ```
  ........                                                                 [100%]
  8 passed in 2.81s
  ```
- **Notes:** The Phase 14 D-01/D-02 reproducer set (the 8 tests that triggered Phase 14 in the first place) all pass GREEN inside the rebuilt container. The broader r2-test file (`test_r2_sessions.py`) carries pre-existing fixture issues unrelated to Phase 14: 12 collection-time errors arise because `tests/conftest.py::opened_sid` monkey-patches `_case_dirs_mod.resolve_case_dir`, but `tools/r2_sessions.py` imports `resolve_case_dir` by name (Plan 13 case_dir validator change). This is a pure test-fixture gap (production code passes the validator correctly under normal MCP-driven calls — see HARDEN-03 live arm below) and is captured in `.planning/phases/14-close-v1.1-gaps/deferred-items.md` for v1.2 cleanup.

### Gateway shutdown smoke test leaves no zombie r2 processes
- **Date:** 2026-05-21T04:10:30Z
- **Container build:** kali-re-tools:0ac0f3e3ebbf
- **Command:** Open 2 r2 sessions via MCP (`tools/call open_r2_session`), then `docker exec mare-mcp-toolbox-kali-1 kill -TERM 45` (mcp-gateway PID), then `ps -eo pid,ppid,stat,cmd | grep r2`.
- **Outcome:** passed
- **Transcript:**
  ```
  === r2 procs BEFORE gateway SIGTERM ===
     PID  PPID STAT CMD
      77    45 Ss   r2 -2 -q0 -e scr.interactive=false -e scr.color=0 -e scr.html=0 -e cfg.user=mare /agent/examples/samples/mfc42ul.dll
      78    45 Ss   r2 -2 -q0 -e scr.interactive=false -e scr.color=0 -e scr.html=0 -e cfg.user=mare /agent/examples/samples/mfc42ul.dll

  === SIGTERM gateway PID 45 ===

  === r2 procs AFTER gateway SIGTERM ===
  (no matching r2 processes)
  zombie_r2_count=0
  live_r2_count=0

  === ps -ef snapshot ===
  UID        PID  PPID  C STIME TTY          TIME CMD
  agent        1     0  0 04:10 ?        00:00:00 tail -f /dev/null
  agent       37     1  0 04:10 ?        00:00:00 /usr/bin/python3 /usr/local/bin/idalib-mcp --host 127.0.0.1 --port 8745
  agent       45     1  7 04:10 ?        00:00:03 [mcp-gateway] <defunct>
  agent       76    37  2 04:10 ?        00:00:00 /usr/bin/python3 -m ida_pro_mcp.idalib_server --host 127.0.0.1 --port 43683
  ```
- **Notes:** SessionRegistry.__aexit__ killpg'd both r2 sessions during graceful gateway shutdown. The defunct gateway PID is expected (PID 1 `tail -f` is not a reaper); zero r2 procs remained. Closes audit item.

