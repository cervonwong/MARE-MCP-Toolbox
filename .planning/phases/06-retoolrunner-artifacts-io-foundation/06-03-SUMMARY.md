---
phase: 06-retoolrunner-artifacts-io-foundation
plan: 03
subsystem: mcp-gateway-runner
tags: [retoolrunner, subprocess, chokepoint, asyncio, killpg, head-buffer, file-sink, tool-logs, mcp-gateway, found-02, found-03]

# Dependency graph
requires:
  - phase: 06-retoolrunner-artifacts-io-foundation
    plan: 01
    provides: 10 RED-state runner tests in tests/test_runner.py locking the FOUND-02 SC-1..SC-4 + D-08 + manifest-regression contract
  - phase: 06-retoolrunner-artifacts-io-foundation
    plan: 02
    provides: mcp_gateway.artifacts_io leaf module (ensure_subdir, tool_log_path, confine_to) consumed by runner.py for log-path construction
provides:
  - mcp_gateway.runner.ReToolRunner -- class form chokepoint primitive (D-01); the only subprocess spawn path every Phase 7+ RE tool will sit atop
  - mcp_gateway.runner.run_tool -- module-level convenience (D-02) for one-shot static-wrapper use in Phase 7
  - Module constants STDOUT_HEAD_KB / STDERR_HEAD_KB / DEFAULT_TIMEOUT_S / MAX_LOG_MB read once at import from MCP_GATEWAY_RUNNER_* env vars (D-08)
  - 12-key D-03 return shape locked for Phase 7+ consumers (exit_code, timed_out, duration_s, stdout_head, stdout_truncated, stdout_bytes_total, stderr_head, stderr_truncated, stderr_bytes_total, log_path, argv, slug)
  - Auto-capture to case_dir/tool-logs/<ts>-<slug>-<rand4>.txt with log_path returned RELATIVE to case_dir (D-09, D-10, FOUND-03)
affects: [07-* run_shell + typed static wrappers, 08-* r2 sessions, 09-* job system, 10-* extraction tier, 11-* dynamic mode tools]

# Tech tracking
tech-stack:
  added: []  # stdlib only -- no new pip deps; passes manifest-regression test
  patterns:
    - "TDD GREEN-phase: Plan 01 wrote 10 RED tests; Plan 03 ships 313 LoC flipping them all GREEN with one tiny docstring-only deviation (described below)"
    - "Concurrent pipe drain via asyncio.gather of two _drain coroutines -- never proc.communicate (Pitfall 1); each drain accumulates head buffer up to head_cap_bytes and writes raw bytes to a single shared file sink up to MAX_LOG_MB"
    - "Head buffer + raw file sink ordering (Pattern 2): write raw bytes to disk first; ANSI strip + UTF-8 boundary truncate + decode happen on the head slice only at finalize-time, so on-disk log keeps forensic fidelity while head_str is safe to log/return"
    - "Process-group cleanup: start_new_session=True at spawn + os.killpg(os.getpgid(proc.pid), signal.SIGKILL) + await asyncio.shield(proc.wait()) on BOTH TimeoutError and CancelledError; swallows ProcessLookupError AND PermissionError"
    - "Cancellation contract (Pitfall 18 / D-17): on CancelledError, kill pgroup then await shield(proc.wait()), THEN re-raise -- prevents cancel cascade from dropping proc.wait() and orphaning the subprocess tree"
    - "Timeout posture (D-04): asyncio.wait_for(0.5) + 0.2s cleanup budget -- runner internally swallows TimeoutError and returns {timed_out=True, exit_code=-9, ...} rather than raising; full stdout/stderr capture is sacrificed on timeout (placeholder zeros) because drains are cancelled mid-flight, but the on-disk log keeps everything that flushed"
    - "Env-var validation at module import (D-08, T-6-07): _env_int / _env_float helpers mirror uploads._max_bytes pattern; bad values raise RuntimeError at the import line so the failure is unambiguous in CI logs"

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/runner.py
  modified: []

key-decisions:
  - "Wrote runner.py end-to-end from the plan's <action> paste-ready code block -- zero structural deviation; copied verbatim, then rephrased a single docstring line after the grep-the-source test caught the literal substring 'shell=True' in prose context (see Deviations)"
  - "Kept the eager slug validation in __init__ by calling tool_log_path() with a throwaway timestamp; the artifacts_io regex raises ValueError BEFORE the first .run() call surfaces a bad slug -- cheaper bug to find at construction time"
  - "Did NOT modify subprocess_runner.py -- the two runners coexist (deferred convergence per v1.2 carryover); existing orchestrator-skill consumers still work, ReToolRunner is purely additive"
  - "Did NOT add __all__ to runner.py -- consistent with artifacts_io.py decision in Plan 02; public API discoverable via grep-the-source"

patterns-established:
  - "TDD GREEN-phase with paste-ready plan code: Wave-0 (Plan 01) writes failing tests; Wave-2 (Plan 02) and Wave-3 (Plan 03) implement modules from PLAN.md <action> blocks verbatim; tests serve as both contract and validation"
  - "Grep-the-source chokepoint test catches BOTH code AND prose violations: a docstring that mentions the forbidden token in a non-code context still fails the test; future plans must phrase 'never use shell=True' as e.g. 'never use the shell-invocation kwarg' to avoid this trap"
  - "On-import env-var validation as load-bearing test surface: test_env_validation_rejects_bad_values uses subprocess.run with an isolated env dict; runner.py's module-level _env_float call raises RuntimeError before any class is exported, so the import itself fails -- verified by non-zero exit + RuntimeError in stderr"

requirements-completed: [FOUND-02, FOUND-03]

# Metrics
duration: 3min
completed: 2026-05-13
---

# Phase 6 Plan 3: ReToolRunner Chokepoint Subprocess Primitive Summary

**Turned 10 RED tests GREEN with a 313-LoC chokepoint runner -- ReToolRunner + run_tool + 4 module-level env-var constants -- that argv-only-spawns subprocesses under start_new_session, concurrently drains stdout/stderr through head buffers and an on-disk tool-logs/ sink with bounded RSS, returns the locked 12-key D-03 dict on success, swallows timeout into a {timed_out=True} result, and properly killpg-shields-reraises on CancelledError. FOUND-02 + FOUND-03 land; Phase 7+ can now `from mcp_gateway.runner import ReToolRunner` and assume the contract.**

## Performance

- **Duration:** ~3 min (~169 s)
- **Started:** 2026-05-13T01:29:55Z
- **Completed:** 2026-05-13T01:32:44Z
- **Tasks:** 1 / 1
- **Files created:** 1
- **Files modified:** 0

## Accomplishments

- Created `mcp-gateway/src/mcp_gateway/runner.py` (313 LoC) implementing the full PLAN.md `<action>` paste-ready code block:
  - `ReToolRunner(case_dir, *, slug, timeout, env, stdout_head_kb, stderr_head_kb)` class with `async def run(self, argv) -> dict` (D-01)
  - `run_tool(case_dir, argv, *, slug, ...)` module-level convenience that constructs a fresh runner and awaits .run (D-02)
  - Module constants `STDOUT_HEAD_KB` / `STDERR_HEAD_KB` / `DEFAULT_TIMEOUT_S` / `MAX_LOG_MB` read at import from `MCP_GATEWAY_RUNNER_*` env vars via `_env_int` / `_env_float` helpers (D-08)
  - `_drain(stream, head_cap_bytes, file_sink, log_cap_bytes)` coroutine: head buffer + raw file sink with both caps; returns `(head_bytes, total_bytes, head_truncated, log_truncated)`
  - `_finalize_head(head_bytes, cap_bytes)`: ANSI strip on bytes → UTF-8-boundary truncate → decode with errors='replace' (Pattern 2 ordering)
  - `_truncate_to_utf8_boundary(buf, n)`: explicit 4-byte walk-back finding the largest prefix ending on a UTF-8 codepoint boundary
  - argv-only spawn via `asyncio.create_subprocess_exec` with `start_new_session=True`; `cwd=str(self._case_dir)` (resolved at __init__)
  - On `TimeoutError`: `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` + `await asyncio.shield(proc.wait())` + return `{timed_out=True, exit_code=-9, ...}` with placeholder zero counters (D-04)
  - On `CancelledError`: same cleanup sequence, then re-raise (D-17 / Pitfall 18)
- Eager `case_dir` validation in `__init__` (resolve strict=True, must be directory) and eager slug validation via `artifacts_io.tool_log_path(self._case_dir, slug)` throwaway call -- failures surface at construction, not at .run()
- All 10 RED tests from Plan 01's `tests/test_runner.py` GREEN -- including the `@pytest.mark.slow`-marked `test_100mb_urandom_bounded_rss` (RSS delta < 32 MB on 100 MB urandom)
- Full mcp-gateway test suite (204 tests, excluding network-dependent e2e) GREEN -- zero regression

## Task Commits

Each task committed atomically:

1. **Task 1: Implement `runner.py` (ReToolRunner + run_tool + 4 env-var module constants)** -- `979d6c1` (feat)

## Files Created/Modified

- `mcp-gateway/src/mcp_gateway/runner.py` (new, 313 lines) -- public API: `ReToolRunner`, `run_tool`, `STDOUT_HEAD_KB`, `STDERR_HEAD_KB`, `DEFAULT_TIMEOUT_S`, `MAX_LOG_MB`; private helpers `_env_int`, `_env_float`, `_drain`, `_finalize_head`, `_truncate_to_utf8_boundary`; module-level compiled regex `_ANSI_ESCAPE`.

## Verification Results

End-to-end verification per plan's `<verification>` block:

1. **Module imports cleanly:**
   ```
   uv run python -c "from mcp_gateway.runner import ReToolRunner, run_tool, STDOUT_HEAD_KB, STDERR_HEAD_KB, DEFAULT_TIMEOUT_S, MAX_LOG_MB"
   ```
   PASS — `IMPORT OK`.

2. **Chokepoint integrity (T-6-02):** `grep -E 'shell=True' src/mcp_gateway/runner.py` returns empty.

3. **Manifest discipline:** `grep -E 'import psutil|from psutil|import aiofiles|from aiofiles' src/mcp_gateway/runner.py` returns empty.

4. **Concurrent drain (Pitfall 1):** `asyncio.gather(` present (drain orchestration); `proc.communicate(` count = 0.

5. **Process-group cleanup form (T-6-05 / D-17 / Pitfall 18):** Both `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` AND `asyncio.shield(proc.wait())` present in source.

6. **All 10 runner tests pass (including SC-4 slow):**
   ```
   cd mcp-gateway && uv run pytest tests/test_runner.py -x -ra
   ```
   Result: `10 passed, 1 warning in 2.93s` (initial run including the `slow` urandom test).

7. **No regression — full suite green:**
   ```
   cd mcp-gateway && uv run pytest tests/ -ra --ignore=tests/e2e
   ```
   Result: `204 passed, 1 warning in 12.85s`. (The e2e test_mastra_starter is excluded as it requires a running gateway + Node.js environment; same exclusion taken by Plan 02 verification.)

8. **All 16 acceptance-criteria literals present** in source: `class ReToolRunner:`, `async def run(self, argv`, `async def run_tool(`, `asyncio.create_subprocess_exec(`, `start_new_session=True`, `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)`, `asyncio.shield(proc.wait())`, both `ProcessLookupError` and `PermissionError` in the killpg except clause, all four `MCP_GATEWAY_RUNNER_*` env var names, `asyncio.gather(`, `reset to placeholder values` (timeout caveat docstring), zero `proc.communicate(` references.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Rephrased two docstring lines that contained the literal substrings `shell=True` and `proc.communicate()`**

- **Found during:** Task 1, first `pytest tests/test_runner.py` run after writing the file from the PLAN's paste-ready code block.
- **Issue:** Two grep-the-source assertions (`test_runner_never_uses_shell_true` and the acceptance-criteria check for zero `proc.communicate(` occurrences) treat ANY occurrence of the literal substrings as a failure, including occurrences inside a prose docstring describing what the runner avoids. The plan's `<action>` paste-ready code block contained these as docstring annotations:
  - `"-- never `shell=True` (D-04 / T-6-02)"`
  - `"-- never `proc.communicate()` (Pitfall 1)"`
- **Fix:** Rephrased the two docstring lines to keep the same semantic meaning without the forbidden substring:
  - `"-- never the shell-invocation kwarg (D-04 / T-6-02)"`
  - `"-- never the blocking `communicate` shortcut (Pitfall 1)"`
- **Files modified:** `mcp-gateway/src/mcp_gateway/runner.py` (docstring lines 11 and 13 only; no behavioral change).
- **Commit:** Included in `979d6c1` (single task commit; the two edits happened pre-commit during the test-flip-to-green loop).
- **Pattern to remember:** The plan's `<action>` block uses the forbidden tokens in prose; the grep test is fundamentally a "no literal substring" check (not a "no kwarg passed to create_subprocess_exec" check). Future plans should phrase the negative invariant without the forbidden token (e.g., "never the shell-invocation kwarg" instead of "never `shell=True`").

## Auth Gates

None -- implementation is local file write only; runner uses `os.environ.copy()` by default with no auth-token consumption.

## Threat Surface Scan

This plan introduces NO new attack surface beyond what was already enumerated in the plan's `<threat_model>`. Every `mitigate`-disposition threat is provably mitigated by a passing test:

| Threat | Mitigation | Test (now GREEN) |
|--------|------------|------------------|
| T-6-02 (shell injection / elevation) | argv-only `asyncio.create_subprocess_exec`; no `shell=True` anywhere | `test_runner_never_uses_shell_true` (grep-the-source) |
| T-6-04 (DoS via PIPE/OOM/log) | Concurrent `asyncio.gather` of two `_drain` coros; head_cap_bytes (`STDOUT_HEAD_KB*1024`/`STDERR_HEAD_KB*1024`) + log_cap_bytes (`MAX_LOG_MB*1024*1024`) | `test_100mb_urandom_bounded_rss` (RSS delta < 32 MB on 100 MB urandom; slow marker) |
| T-6-05 (orphaned subprocess) | `start_new_session=True` + `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` + `await asyncio.shield(proc.wait())` on both timeout and cancel | `test_timeout_kills_process_group` (wait_for 0.5 + 0.2s cleanup budget); `test_cancel_propagates_to_killpg` (< 0.2s cancel-to-dead per D-20) |
| T-6-06 (log filename collision) | Inherited from `artifacts_io.tool_log_path` -- `secrets.token_hex(2)` 16-bit rand4 suffix per call | Verified in Plan 02's `test_tool_log_path_no_collision` |
| T-6-07 (env-var validation) | `_env_int`/`_env_float` raise `RuntimeError` at module import on non-numeric or negative values | `test_env_validation_rejects_bad_values` (subprocess.run with bad env, asserts non-zero exit + RuntimeError in stderr) |
| ANSI escape injection (terminal hijack) | `_ANSI_ESCAPE` regex strips CSI sequences from head slice before decode; raw bytes still go to file sink for forensic fidelity | Implicit in `test_log_capture_and_head_alignment` (head_str safe to log/return, file content preserved) |
| Mid-UTF-8-codepoint truncation | `_truncate_to_utf8_boundary` 4-byte walk-back before `decode(errors='replace')` | Implicit in `test_log_capture_and_head_alignment` (head decodes cleanly) |
| Env leak into subprocess | accept (in this phase) -- documented in module docstring | Phase 7's `run_shell` is the layer that ships the env scrub |

Phase 6 explicitly defers (no scope creep):
- SIGTERM grace period before SIGKILL -- Phase 9 (jobs / user-cancel via `cancel_tool_job`)
- Follow-fork straggler scan via `/proc/<pid>/task/*/children` -- Phase 11 (dynamic mode)
- `MCP_GATEWAY_TOKEN`/AWS-credential env scrub -- Phase 7 (`run_shell`)
- Mount-namespace isolation -- v1.2 (requires `CAP_SYS_ADMIN`)

## Known Stubs

None -- runner.py is feature-complete for FOUND-02 + FOUND-03 scope. The "timeout placeholder counters" caveat (on `timed_out=True` the `stdout_bytes_total` / `stderr_bytes_total` / `*_head` / `*_truncated` fields are zero-placeholders because the drain tasks were cancelled mid-flight by `asyncio.wait_for`) is documented in the module docstring and is intentional per D-04 -- the on-disk log file still captured whatever flushed, so forensic data is not lost. Phase 7+ consumers needing accurate byte counts on timeout can read `log_path` directly.

## Self-Check: PASSED

- FOUND: mcp-gateway/src/mcp_gateway/runner.py (313 lines)
- FOUND: commit 979d6c1 (Task 1 -- runner.py implementation)
- FOUND: all 10 runner tests in tests/test_runner.py GREEN (including @pytest.mark.slow SC-4)
- FOUND: 204/204 mcp-gateway tests GREEN (excluding gateway-dependent e2e per Plan 02 precedent)
- FOUND: all 16 acceptance-criteria literals present in source; `shell=True` absent; `proc.communicate(` absent; `psutil`/`aiofiles` imports absent
- FOUND: D-03 12-key return shape matches `test_return_shape_locked` exact-order assertion
- FOUND: D-10 log_path is relative to case_dir (`test_log_capture_and_head_alignment` asserts `not log_rel.is_absolute()` and `log_rel.parts[0] == "tool-logs"`)
