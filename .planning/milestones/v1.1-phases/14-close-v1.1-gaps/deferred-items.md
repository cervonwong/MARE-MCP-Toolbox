# Phase 14 — Deferred Items

Out-of-scope discoveries logged during plan execution. Each entry should record the discovering plan, the issue, and the suggested follow-up.

## From Plan 14-02

### 47 already-satisfied v1.1 traceability rows still marked "Pending"

- **Discovered during:** Plan 14-02, Task 3 (final cross-file consistency check)
- **What:** REQUIREMENTS.md traceability table still shows 47 rows with `TBD | Pending` for requirements whose body checkboxes are `[x]` and whose phase VERIFICATION.md marks them satisfied. Affected ID families: FOUND-01..04, SHELL-01/02, STATIC-01..10, ARTIF-05, SESS-01..06, JOBS-01..07, EXTR-01..06, DYN-01..07, SKILL-01..04.
- **Why deferred:** Out of scope for Plan 14-02. The plan's narrative bounds the diff to 14 rows / ≤50 changed lines; flipping 47 more rows would be a much larger, separate sweep. Task 3 acceptance criterion 4 (Pending count == 0) is internally inconsistent with that scope bound.
- **Severity:** medium — `/gsd-audit-milestone v1.1` (planned in Plan 14-05) may flag these as a traceability gap and demand a follow-up sweep before milestone close.
- **Suggested follow-up:** Either (a) add a dedicated wave-1 sister plan to 14-02 that performs the 47-row sweep, or (b) handle inline during Plan 14-05 audit-re-run if the auditor reports them. Source-of-truth for each row's Plan and Verified columns is the corresponding phase's `*-VERIFICATION.md` file.
- **Status:** RESOLVED 2026-05-21 in quick task 260521-mhh — all 47 rows filled from phase VERIFICATION.md sources; v1.1 traceability now shows 61/61 verified.

## From Plan 14-04

### test_r2_sessions.py fixture monkey-patch bypass

- **Discovered during:** Plan 14-04 Task 2 (Phase 8 UAT item 4 — container r2-gated test suite).
- **What:** `tests/conftest.py::opened_sid` patches `_case_dirs_mod.resolve_case_dir`, but `tools/r2_sessions.py` imports `resolve_case_dir` by name at module load (Plan 13 case_dir validator). Monkey-patching the module attribute therefore does not affect r2_sessions' bound name, and 12 tests in `test_r2_sessions.py` error with `ValueError: case_dir must be under /agent/status` when run in-container against a `/tmp/pytest-...` fixture path. `test_r2_sandbox_integration.py::test_sandbox_active_when_open_r2` fails for the same reason.
- **Why deferred:** Pure test-fixture gap; production code passes the validator under normal MCP-driven calls (verified live by HARDEN-03 sandbox UAT item — see 13-VERIFICATION.md). The Phase 14 D-01/D-02 reproducer set (the 8 tests that triggered Phase 14) all pass GREEN, so v1.1 closure invariant holds. Fixing this requires touching `r2_sessions.py` to `import case_dirs as _case_dirs` (access by attribute), which is a Phase 13 contract change out of scope for v1.1 archive.
- **Severity:** low — production correctness is unaffected; only test-suite ergonomics inside the container.
- **Suggested follow-up:** v1.2 cleanup — switch `r2_sessions.py` (and other tools that import `resolve_case_dir`) to `from . import case_dirs as _case_dirs` and access via `_case_dirs.resolve_case_dir(...)`, then drop the host-only skip pattern on the affected r2 tests so they GREEN in-container.
- **Status:** RESOLVED 2026-05-21 in commits 260521-mhh `b080adf` (case_dirs) + `4a1ac2e` (resolve_sample sibling). The first commit refactored `resolve_case_dir` only; in-container verification (2026-05-21T08:50Z) showed the 12 tests still erroring because `opened_sid` ALSO monkeypatches `_samples_mod.resolve_sample` and the same `from X import Y` binding bug applied to it. Follow-up `4a1ac2e` mirrored the refactor for `resolve_sample` (`from mcp_gateway.tools import samples as _samples` + 2 call-site renames + 3 test-side monkeypatches updated to `r2_sessions._samples`). Confirmed in-container: `pytest tests/test_r2_sessions.py tests/test_r2_sandbox_integration.py` → 17 passed (up from 5 passed + 12 errors). 3 unrelated behavioural failures remain — see new sibling entry "r2 session lifecycle test failures in-container" below.

### r2 session lifecycle test failures in-container (3 tests, surfaced by 4a1ac2e)

- **Discovered during:** In-container validation 2026-05-21T08:50Z after commit `4a1ac2e` unlocked the 12 previously-erroring `test_r2_sessions.py` tests. These 3 failures were hidden for the entire v1.1 cycle by the resolve_sample/resolve_case_dir binding-bypass bug.
- **What:** Three deterministic in-container failures in `tests/test_r2_sessions.py` against real r2 6.0.5:
  1. `test_format_json_non_json_command` (line 163) — expects `result["parsed_json"] is None` for a non-JSON r2 command; actual r2 6.0.5 returns parseable JSON (`{'arch': 'x86', 'bits': 16416, 'commit': 0, 'major': 6, ...}`). Likely stale test assumption: r2 became more JSON-permissive between when the test was written and 6.0.5.
  2. `test_hung_cmd_kills_session` (line 296) — after sending a hung r2 command, `result["session_invalidated"]` stays False; expected True. Either the kill path doesn't mark session_invalidated, OR the test's hang-trigger no longer hangs r2 6.0.5.
  3. `test_cancel_propagates_to_killpg` (line 333) — after CancelledError, r2 pid still alive 200ms later. Either real killpg-propagation bug under r2 6.0.5 OR the 200ms cleanup window is too tight on the rebuilt container.
- **Why deferred:** All three were ALWAYS failing in-container but hidden for the entire v1.1 development by the binding-bypass bug (`from X import Y` made the conftest monkeypatch a no-op, so the tests errored before reaching the assertion). The behavioural code paths under test (JSON parsing, hang detection, cancel propagation) all have unit-level coverage that passes; only these end-to-end r2-subprocess paths fail. Production security boundary verified intact (HARDEN-03 closed via direct r2 path).
- **Severity:** medium — three real bugs OR stale tests against r2 6.0.5; production correctness not proven for hang/cancel paths against real subprocess, but the broader test suite (unit + sandbox + 17/17 in-container r2_sessions) still validates the architecture.
- **Suggested follow-up:** v1.2 phase — triage each failure with `/gsd-debug`:
  - Run `format_json_non_json_command` candidate command directly against r2 6.0.5 to confirm JSON-permissiveness change; if confirmed, update test assertion (stale) OR pick a truly non-JSON command (e.g. error-only output).
  - Add r2-level instrumentation to `test_hung_cmd_kills_session` to confirm the hang trigger still hangs r2 6.0.5; if not, update the trigger.
  - Increase cancel-grace window OR add explicit `wait_for(killed, timeout=...)` instead of bare 200ms `sleep` to disambiguate killpg-propagation bug vs. test-timing flakiness.
- **Status:** open.

### Untouched case_dirs/samples consumers (~14 tool call-sites still bind resolvers by name)

- **Discovered during:** Quick task 260521-mhh Task 3 (scoping the r2_sessions refactor).
- **What:** Seven other tool modules import `resolve_case_dir` by name (the same binding shape that broke r2_sessions tests under the conftest monkeypatch): `artifacts.py`, `workflows.py`, `shell.py`, `re_artifacts.py`, `re_static.py`, `jobs.py`, `extract.py`. The same pattern likely applies to `resolve_sample` (the sibling resolver in `samples.py`) — `4a1ac2e` proved this concretely for `r2_sessions.py` but the other 7 modules were not re-audited. NOT currently exercised by any test that needs to bypass the validators, so the bug is latent — but any future test that wants to monkeypatch either resolver against one of these tools will hit the same wall. CONCRETELY confirmed cost: `test_capa_integration.py::test_capa_succeeds_on_simple_sample` fails in-container with the same `not under allowed prefixes` error, indicating `jobs.py` / `extract.py` capa code path has the same binding bypass.
- **Why deferred:** Pre-emptive refactor without a failing test driving it was out of scope for the v1.1 cleanup batch. However, `test_capa_integration` is now a concrete failing test — this entry should be upgraded to "scoped for v1.2" rather than purely latent. The fix is mechanical (same pattern as r2_sessions.py: `from . import case_dirs as _case_dirs` + `from . import samples as _samples` + N call-site renames per file).
- **Severity:** medium (upgraded 2026-05-21 from low) — `test_capa_integration` failing in-container is a concrete blocker for capa-related work. The other 6 modules remain latent.
- **Suggested follow-up:** v1.2 cleanup quick task. Audit BOTH `resolve_case_dir` AND `resolve_sample` consumers across all 7 modules. ~60-100 lines of mechanical diff. Prioritise `jobs.py` + `extract.py` first (capa test blocker).
- **Status:** open.

### test_skill_md_dual_mode.py StopIteration in-container

- **Discovered during:** Plan 14-04 Task 2 (Phase 8 UAT item 4 — pytest collection error).
- **What:** `tests/test_skill_md_dual_mode.py:28` walks parents looking for a `.planning` directory; inside the container at `/opt/mcp-gateway` no parent contains `.planning`, so collection errors with `StopIteration`.
- **Why deferred:** Test was always host-only by intent (it validates the orchestrator skill markdown under `.planning/` / `workspace/skills/`). Container is not its target environment.
- **Severity:** low.
- **Suggested follow-up:** Add `@pytest.mark.skipif(not Path("/host/.planning").is_dir(), reason="host-only")` or move the test under a `host_only/` subdirectory excluded from container runs.
- **Status:** RESOLVED 2026-05-21 in quick task 260521-mhh — added module-level pytest.skip guard at tests/test_skill_md_dual_mode.py:28 that fires when no parent of the test file contains .planning (container path /opt/mcp-gateway/tests/).

### MCP r2_cmd 30s timeout on freshly-opened sessions

- **Discovered during:** Plan 14-04 Task 2 (Phase 13 UAT item 15 — HARDEN-03 live arm).
- **What:** After opening an r2 session via MCP `tools/call open_r2_session` and immediately issuing any `r2_cmd` (even `?V`), the gateway's `R2Session.exec_one` sentinel-readuntil loop never returns, hitting the 30s `R2_CMD_TIMEOUT_S` cap and invalidating the session. Gateway log shows `[sessions] opened ... → [sessions] closed (reason=timeout)`. Direct r2 invocation in the same container with the IDENTICAL argv + stdin batch (`e cfg.sandbox=true; ?e SENTINEL; e cfg.sandbox; ?e SENTINEL; q`) works flawlessly — see HARDEN-03 live arm transcript in 13-VERIFICATION.md.
- **Why deferred:** Phase 13 security boundary (cfg.sandbox=true) is verified intact via the direct-r2 path (HARDEN-03 closed). The session-pipe bug appears to be in the gateway's `R2Session.exec_one` async readuntil — possibly a pipe-buffering or stdin-flush race introduced under Phase 13 hot-fix when `cfg.sandbox=true` engages r2's sandboxed output path. Test suite doesn't catch it because `tests/conftest.py::opened_sid` patches `_case_dirs_mod.resolve_case_dir` and the broader r2 fixture chain bypasses the live MCP pipe entirely (see "test_r2_sessions.py fixture monkey-patch bypass" above).
- **Severity:** medium — affects live MCP r2 session UX over the remote gateway, but does NOT break the security boundary (cfg.sandbox latches correctly) and does NOT affect any v1.1 audit gate (the unit tests for sandbox argv, dangerous-cmd regex, and session caps all pass).
- **Suggested follow-up:** Add an in-process pytest that exercises `R2Session.exec_one` against a real r2 subprocess (no fixture patches) and binds the sentinel-line drain to a real pipe. Investigate whether `proc.stdout.readuntil(b"\n")` mis-handles partial buffers when r2's sandbox-mode line endings differ, or whether the post-spawn init batch is leaving residual bytes in the pipe buffer.
- **Status:** RESOLVED 2026-05-21 in commit `fbcb88b` (debug session: `.planning/debug/r2-cmd-timeout.resolved.md`). Root cause was NOT pipe buffering or sandbox interaction — argv `-q0` was misparsed as one flag but is actually two: `-q` (quiet) + `-0` (emit `\x00` before each command's output). The NUL prefix broke `exec_one`'s exact-match sentinel comparison (init's `readuntil(sentinel_bytes)` substring match was prefix-tolerant, which is why open succeeded but the first `r2_cmd` always timed out). Fix: drop `-0` from argv; keep `-q`. Regression test added at `mcp-gateway/tests/test_r2_argv.py::test_argv_no_null_byte_separator_flag`. Verified in-container: 9/9 r2 tests pass, `cfg.sandbox=true` still latches.

### test_mastra_starter.py: ERR_MODULE_NOT_FOUND under Node.js 25 + tsx 4.21

- **Discovered during:** Plan 14-04 Task 3 (final regression sanity test gate).
- **What:** `tests/e2e/test_mastra_starter.py::test_mastra_starter_full_triage_path` fails with `ERR_MODULE_NOT_FOUND` for `.../mastra/node_modules/.bin/package-CeBgXWuR.mjs` when the host gateway is up (the test has a `gateway_alive` skip-fixture that masks the failure when gateway is down). Root cause: tsx 4.21.0's `.bin/tsx` wrapper imports sibling `.mjs` files via relative paths, but Node.js v25 (host) resolves those relative paths against the `.bin/` directory where the sibling files do NOT exist (they live in `tsx/dist/`). Net effect: any e2e test that subprocess-runs `tsx` inside an npm-installed mastra starter project crashes on import.
- **Why deferred:** This is a v1.0 test (commit `11ac39c feat(04-05): add mastra starter subprocess e2e test (CLI-02)`), NOT a v1.1 / Phase 14 / Plan 01 change. The test's docstring explicitly notes "Node.js 20+ to run the mastra starter test" — it was written for Node 20, and Node 25 has broken something in npm/tsx wrapper resolution. The Plan 01 invariant ("D-03 acceptance gate: `pytest -m 'not slow'` exits 0 with 0 failed") was met in the host run earlier this Phase 14 session (595 passed, 49 skipped, 0 failed) because the gateway was not up and the mastra_starter test skipped via `gateway_alive`. Plan 14-04 brought the gateway up to drive 15 live UAT items, which un-masked this v1.0 environmental failure.
- **Severity:** low — v1.0 CLI-02 functionality (the mastra starter itself) is unaffected at the project / template / starter-skeleton level; only the e2e subprocess invocation against tsx 4.21 + Node 25 is broken. The starter ships and works under Node 20.
- **Suggested follow-up:** v1.2 — pin a tsx version compatible with Node 25 in `templates/mastra/package.json` (likely tsx 4.22+), OR pin Node.js 20 as the documented host runtime, OR rewrite the e2e test to call the bundled mastra package code directly instead of via the npm `.bin/tsx` wrapper.
- **Status:** open.
