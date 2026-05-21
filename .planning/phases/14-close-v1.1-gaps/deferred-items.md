# Phase 14 — Deferred Items

Out-of-scope discoveries logged during plan execution. Each entry should record the discovering plan, the issue, and the suggested follow-up.

## From Plan 14-02

### 47 already-satisfied v1.1 traceability rows still marked "Pending"

- **Discovered during:** Plan 14-02, Task 3 (final cross-file consistency check)
- **What:** REQUIREMENTS.md traceability table still shows 47 rows with `TBD | Pending` for requirements whose body checkboxes are `[x]` and whose phase VERIFICATION.md marks them satisfied. Affected ID families: FOUND-01..04, SHELL-01/02, STATIC-01..10, ARTIF-05, SESS-01..06, JOBS-01..07, EXTR-01..06, DYN-01..07, SKILL-01..04.
- **Why deferred:** Out of scope for Plan 14-02. The plan's narrative bounds the diff to 14 rows / ≤50 changed lines; flipping 47 more rows would be a much larger, separate sweep. Task 3 acceptance criterion 4 (Pending count == 0) is internally inconsistent with that scope bound.
- **Severity:** medium — `/gsd-audit-milestone v1.1` (planned in Plan 14-05) may flag these as a traceability gap and demand a follow-up sweep before milestone close.
- **Suggested follow-up:** Either (a) add a dedicated wave-1 sister plan to 14-02 that performs the 47-row sweep, or (b) handle inline during Plan 14-05 audit-re-run if the auditor reports them. Source-of-truth for each row's Plan and Verified columns is the corresponding phase's `*-VERIFICATION.md` file.
- **Status:** open.

## From Plan 14-04

### test_r2_sessions.py fixture monkey-patch bypass

- **Discovered during:** Plan 14-04 Task 2 (Phase 8 UAT item 4 — container r2-gated test suite).
- **What:** `tests/conftest.py::opened_sid` patches `_case_dirs_mod.resolve_case_dir`, but `tools/r2_sessions.py` imports `resolve_case_dir` by name at module load (Plan 13 case_dir validator). Monkey-patching the module attribute therefore does not affect r2_sessions' bound name, and 12 tests in `test_r2_sessions.py` error with `ValueError: case_dir must be under /agent/status` when run in-container against a `/tmp/pytest-...` fixture path. `test_r2_sandbox_integration.py::test_sandbox_active_when_open_r2` fails for the same reason.
- **Why deferred:** Pure test-fixture gap; production code passes the validator under normal MCP-driven calls (verified live by HARDEN-03 sandbox UAT item — see 13-VERIFICATION.md). The Phase 14 D-01/D-02 reproducer set (the 8 tests that triggered Phase 14) all pass GREEN, so v1.1 closure invariant holds. Fixing this requires touching `r2_sessions.py` to `import case_dirs as _case_dirs` (access by attribute), which is a Phase 13 contract change out of scope for v1.1 archive.
- **Severity:** low — production correctness is unaffected; only test-suite ergonomics inside the container.
- **Suggested follow-up:** v1.2 cleanup — switch `r2_sessions.py` (and other tools that import `resolve_case_dir`) to `from . import case_dirs as _case_dirs` and access via `_case_dirs.resolve_case_dir(...)`, then drop the host-only skip pattern on the affected r2 tests so they GREEN in-container.
- **Status:** open.

### test_skill_md_dual_mode.py StopIteration in-container

- **Discovered during:** Plan 14-04 Task 2 (Phase 8 UAT item 4 — pytest collection error).
- **What:** `tests/test_skill_md_dual_mode.py:28` walks parents looking for a `.planning` directory; inside the container at `/opt/mcp-gateway` no parent contains `.planning`, so collection errors with `StopIteration`.
- **Why deferred:** Test was always host-only by intent (it validates the orchestrator skill markdown under `.planning/` / `workspace/skills/`). Container is not its target environment.
- **Severity:** low.
- **Suggested follow-up:** Add `@pytest.mark.skipif(not Path("/host/.planning").is_dir(), reason="host-only")` or move the test under a `host_only/` subdirectory excluded from container runs.
- **Status:** open.

### MCP r2_cmd 30s timeout on freshly-opened sessions

- **Discovered during:** Plan 14-04 Task 2 (Phase 13 UAT item 15 — HARDEN-03 live arm).
- **What:** After opening an r2 session via MCP `tools/call open_r2_session` and immediately issuing any `r2_cmd` (even `?V`), the gateway's `R2Session.exec_one` sentinel-readuntil loop never returns, hitting the 30s `R2_CMD_TIMEOUT_S` cap and invalidating the session. Gateway log shows `[sessions] opened ... → [sessions] closed (reason=timeout)`. Direct r2 invocation in the same container with the IDENTICAL argv + stdin batch (`e cfg.sandbox=true; ?e SENTINEL; e cfg.sandbox; ?e SENTINEL; q`) works flawlessly — see HARDEN-03 live arm transcript in 13-VERIFICATION.md.
- **Why deferred:** Phase 13 security boundary (cfg.sandbox=true) is verified intact via the direct-r2 path (HARDEN-03 closed). The session-pipe bug appears to be in the gateway's `R2Session.exec_one` async readuntil — possibly a pipe-buffering or stdin-flush race introduced under Phase 13 hot-fix when `cfg.sandbox=true` engages r2's sandboxed output path. Test suite doesn't catch it because `tests/conftest.py::opened_sid` patches `_case_dirs_mod.resolve_case_dir` and the broader r2 fixture chain bypasses the live MCP pipe entirely (see "test_r2_sessions.py fixture monkey-patch bypass" above).
- **Severity:** medium — affects live MCP r2 session UX over the remote gateway, but does NOT break the security boundary (cfg.sandbox latches correctly) and does NOT affect any v1.1 audit gate (the unit tests for sandbox argv, dangerous-cmd regex, and session caps all pass).
- **Suggested follow-up:** Add an in-process pytest that exercises `R2Session.exec_one` against a real r2 subprocess (no fixture patches) and binds the sentinel-line drain to a real pipe. Investigate whether `proc.stdout.readuntil(b"\n")` mis-handles partial buffers when r2's sandbox-mode line endings differ, or whether the post-spawn init batch is leaving residual bytes in the pipe buffer.
- **Status:** open.
