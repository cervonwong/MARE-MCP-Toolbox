---
status: resolved
trigger: "Three r2 session lifecycle tests fail in-container after the resolve_sample monkeypatch refactor (commit 4a1ac2e)"
created: 2026-05-21T16:25:00Z
updated: 2026-05-21T18:00:00Z
resolved_commits:
  - f85d722  # Convert test_format_json_non_json_command to injection-based unit test
  - 802b90b  # Convert test_hung_cmd_kills_session to injection-based unit test
  - d3c7069  # Add CancelledError handler in r2_cmd to prevent orphan r2 subprocesses
verification: "In-container: pytest tests/test_r2_sessions.py tests/test_r2_sandbox_integration.py → 17 passed"
---

## Current Focus

hypothesis: Three independent root causes — two stale test triggers/assertions against r2 6.0.5; one real production-code gap (contract violation of Phase 8 D-20 step d).
test: Reproduced all three failures in-container; isolated trigger behavior with direct r2 invocations; cross-referenced Phase 8 design contract.
expecting: Per-test triage report distinguishing stale-test vs production-code-bug.
next_action: Return diagnosis — no fix applied per `goal: find_root_cause_only`.

## Symptoms

expected: All three tests pass cleanly in-container against a real r2 subprocess.

actual: All 3 fail in-container with the following exact errors:
  - test_format_json_non_json_command — AssertionError: parsed_json is dict, expected None
  - test_hung_cmd_kills_session    — AssertionError: session_invalidated is False, expected True
  - test_cancel_propagates_to_killpg — AssertionError: r2 pid still alive 200ms after cancel

errors: Captured at evidence #1-#3 below.

reproduction: docker exec mare-mcp-toolbox-kali-1 bash -lc 'cd /opt/mcp-gateway && python3 -m pytest tests/test_r2_sessions.py::<TEST> -xvs'

started: Tests were silently bypassed via the `from X import Y` binding bug; commit 4a1ac2e fixed the bypass and exposed all three.

## Eliminated

- hypothesis: r2_cmd's JSON-detection logic is broken
  evidence: r2_cmd correctly appends 'j' to commands with format="json" (r2_sessions.py:271). r2 6.0.5 simply added JSON support for `?Vj`. Test #1 is the stale party.
  timestamp: 2026-05-21T16:38:00Z

- hypothesis: `?I prompt` hangs in r2 6.0.5 and the timeout path is broken
  evidence: Direct r2 invocation showed `?I prompt` returns IMMEDIATELY when `scr.interactive=false` (which the lockdown init applies). Subsequent `?e MARK` ran fine in the same r2 process. The hang trigger no longer works.
  timestamp: 2026-05-21T16:39:00Z

- hypothesis: killpg-on-cancel exists but is racy / too slow under r2 6.0.5
  evidence: There is NO killpg-on-cancel path in `r2_cmd` at all. The only kill paths in the source are: (a) on `timed_out=True` after `exec_one` returns; (b) explicit `close_r2_session`; (c) init-batch timeout; (d) `__aexit__` shutdown sweep. `git log -p -S "CancelledError"` on the session source confirms no handler was ever added.
  timestamp: 2026-05-21T16:40:00Z

## Evidence

- timestamp: 2026-05-21T16:30:00Z
  checked: test_format_json_non_json_command in-container
  found: r2_cmd(sid, "?V", format="json") returns parsed_json={'arch':'x86','bits':16416,'commit':0,'major':6,...}. The format=json branch appends 'j', producing `?Vj`, which in r2 6.0.5 returns valid JSON.
  implication: Test assertion is stale. r2 6.0.5 expanded `?Vj` JSON support since the test was written. To pick a truly non-JSON-supporting r2 command, the test needs a fresh candidate (or accept that this assertion no longer maps to r2's behavior).

- timestamp: 2026-05-21T16:31:00Z
  checked: Direct r2 invocation of `?V` vs `?Vj` against /bin/ls under r2 6.0.5 in-container
  found: `printf "?V\nq\n" | r2 -q -2 /bin/ls` returns plain text ("radare2 6.0.5 ..."); `printf "?Vj\nq\n" | r2 -q -2 /bin/ls` returns `{"arch":"x86","os":"linux","bits":16416,...}` — valid JSON.
  implication: Confirms test #1 stale assertion. r2 6.0.5 `?Vj` is JSON-capable.

- timestamp: 2026-05-21T16:32:00Z
  checked: test_hung_cmd_kills_session in-container
  found: `r2_cmd(sid, "?I prompt", timeout=2.0)` returns session_invalidated=False. The session was NOT killed because the command completed cleanly inside r2 (without hanging) — `exec_one` returned with timed_out=False.
  implication: The hang trigger `?I prompt` no longer hangs under `scr.interactive=false`. The production kill-on-timeout path was never exercised because the timeout never fired.

- timestamp: 2026-05-21T16:33:00Z
  checked: Direct r2 behavior of `?I prompt` with scr.interactive=false in-container
  found: `printf "?I prompt\n?e MARK\nq\n" | r2 -q -2 -e scr.interactive=false /bin/ls` → outputs `MARK` and exits cleanly. The `?I` prompt returned immediately; no hang.
  implication: Confirms test #2's hang trigger is stale. `?I` does not hang r2 6.0.5 when scr.interactive=false. To re-validate the kill-on-timeout contract, the test needs a new trigger (e.g. a command that genuinely blocks in r2 6.0.5 — perhaps `R+ pipe` socket I/O or a network-bound command).

- timestamp: 2026-05-21T16:34:00Z
  checked: test_cancel_propagates_to_killpg in-container
  found: After task.cancel(), the r2 PID survives 200ms (asserted dead, was alive). The cancel propagated to the asyncio task but the r2 subprocess kept running.
  implication: r2_cmd has NO killpg-on-cancel handler. Cancellation unwinds the await stack but the subprocess is orphaned (until session close, idle reaper, or registry __aexit__).

- timestamp: 2026-05-21T16:35:00Z
  checked: r2_sessions.py:265-280 (r2_cmd body around exec_one)
  found: Only `timed_out` triggers a registry.close(reason="timeout"). There is no try/except for asyncio.CancelledError, and no asyncio.shield protecting exec_one. The `async with sess.lock:` block exits cleanly on cancellation, releasing the lock — but the subprocess is unmanaged.
  implication: Cancellation propagation is unimplemented in the session path.

- timestamp: 2026-05-21T16:36:00Z
  checked: runner.py CancelledError handling (the established Pitfall 18 reference implementation)
  found: runner.py:268-275 has explicit `except asyncio.CancelledError: try: os.killpg(...); ... await asyncio.shield(proc.wait()); raise`. This is the canonical pattern in the codebase. r2_cmd does NOT replicate it.
  implication: The pattern exists in the project, was deliberately designed (Phase 6 D-04 / D-17), but was not reused in r2_cmd despite the explicit Phase 8 D-20 step d contract.

- timestamp: 2026-05-21T16:37:00Z
  checked: Phase 8 design contract — .planning/milestones/v1.1-phases/08-session-scoped-r2/08-CONTEXT.md:542-552
  found: D-20 step d explicitly states: "On `asyncio.TimeoutError` or `asyncio.CancelledError`: `await SESSION_REGISTRY.close(session_id, reason="timeout" or "cancelled")` — which killpg's the r2 process via D-15's pgid. Return result dict with `session_invalidated: true`, `exit_code: -9`, `timed_out: true`."
  implication: The design contract for r2_cmd explicitly required CancelledError handling. The production code only implements the TimeoutError half. This is a contract violation, not a stale test.

- timestamp: 2026-05-21T16:38:00Z
  checked: git log -p -S "CancelledError" on session source
  found: No commit ever added a CancelledError handler to r2_sessions.py or sessions/r2.py / _base.py exec_one path. The contract was specified in Phase 8 D-20 but never implemented; tests existed but were silently bypassed by the import-binding bug.
  implication: Phase 8 / Plan 05 Task 2b ("flip RED stubs to GREEN") implemented the assertions but did not implement the production code. The bypass bug masked this gap for the entire v1.1 cycle.

## Resolution

root_cause: |
  Three independent root causes:

  TEST 1 (test_format_json_non_json_command) — STALE TEST ASSERTION.
    The test was written against an older r2 where `?Vj` was not JSON-capable.
    In r2 6.0.5, `?Vj` returns a valid JSON dict (`{"arch":"x86","os":"linux",...}`).
    The production r2_cmd code is correct: format="json" appends "j", json.loads parses,
    parsed_json populated, parse_error=None. The test's expectation that `?V` is
    "non-JSON-supporting" no longer matches r2 6.0.5 behavior.

  TEST 2 (test_hung_cmd_kills_session) — STALE HANG TRIGGER.
    The test uses `?I prompt` as a hang trigger, but `?I` does not actually hang
    r2 6.0.5 when scr.interactive=false (which the lockdown init mandates).
    `printf "?I prompt\n?e MARK\nq\n" | r2 -q -2 -e scr.interactive=false /bin/ls`
    completes cleanly with "MARK" output and exit 0. The session timeout path was
    therefore never exercised: exec_one returned timed_out=False, the kill+invalidate
    branch was skipped, session_invalidated=False. The production timeout-kill path
    is NOT proven broken — it is simply not reached by this trigger. Production code
    for the timeout half (r2_sessions.py:276-280) is intact: timed_out=True →
    registry.close(reason="timeout") → killpg via _base.close. Need a different
    hang trigger to actually exercise the timeout path under r2 6.0.5.

  TEST 3 (test_cancel_propagates_to_killpg) — REAL PRODUCTION BUG (CONTRACT VIOLATION).
    Phase 8 D-20 step d explicitly contracts: "On asyncio.TimeoutError or
    asyncio.CancelledError: await SESSION_REGISTRY.close(... reason='timeout' or
    'cancelled') — which killpg's the r2 process." The production code in
    r2_sessions.py only implements the TimeoutError half (via the `timed_out`
    return flag from exec_one). There is NO try/except asyncio.CancelledError
    block around the `async with sess.lock: raw_bytes, timed_out = await
    sess.exec_one(...)` line. On task.cancel(), CancelledError propagates up
    through exec_one, out of r2_cmd, leaving the r2 subprocess running. The test
    correctly observes pid is still alive 200ms later. This contract was
    specified in Phase 8 D-20 step d, the canonical pattern exists in
    runner.py:268-275, but it was never ported into the session r2_cmd. The
    binding-bypass bug (commit 4a1ac2e fix) hid this gap for the entire v1.1
    cycle.

fix: |
  PER-TEST RECOMMENDATIONS (no fix applied — diagnose-only mode):

  TEST 1 — Update the test:
    Pick a truly non-JSON-supporting r2 command in 6.0.5. Candidates:
      - A command that produces text but has no 'j' variant (verify against
        `r2 -h` command list and r2's r_cmd_help.c)
      - A command whose 'j' variant returns plain text or an error message
        (the parse_error path)
    Alternative: rewrite the test to NOT rely on r2-internal "JSON-vs-non-JSON"
    classification; instead drive it by injecting a fake exec_one that returns
    non-JSON bytes, verifying the json.loads-fail branch of r2_cmd. Phase 8 D-10
    is unit-testable WITHOUT a real r2 subprocess.

  TEST 2 — Update the hang trigger AND/OR rewrite the test:
    Option A: Find a real hang command in r2 6.0.5. Candidates to probe:
      - Commands that read from stdin (e.g. `pi` with no count, `q` while a
        socket is held)
      - Commands awaiting network I/O (`R+ tcp://`)
      - A command requiring TTY input (most are auto-handled by scr.interactive=false)
    Option B: Inject a fake exec_one returning timed_out=True directly (unit-test
    the kill+invalidate path without needing a real hang). Avoids r2-version drift.

  TEST 3 — FIX THE PRODUCTION CODE (real bug):
    Add CancelledError handling to r2_cmd in r2_sessions.py. Pattern from
    runner.py:268-275 adapted for the session API:

      try:
          async with sess.lock:
              raw_bytes, timed_out = await sess.exec_one(sent_cmd, timeout=resolved_timeout)
      except asyncio.CancelledError:
          # Pitfall 18 + Phase 8 D-20 step d: kill subprocess + close session on cancel.
          try:
              await asyncio.shield(registry.close(session_id, reason="cancelled"))
          finally:
              raise

    Test 3 then passes as-is. Note: the test's 200ms grace window may need
    extension to ~500ms to be robust under load (runner.py's existing
    cancel-pitfall test uses 200ms but on a process that's not loading a binary;
    r2 with an open sample has more cleanup to do).

  Suggested triage outcome for v1.2:
    - TEST 1: stale — update test (low risk).
    - TEST 2: stale + opportunity — update trigger OR convert to a unit-style
      injection test. Production code probably correct but unproven against
      r2 6.0.5; consider adding a separate end-to-end hang test against a known
      hang trigger if one can be found.
    - TEST 3: real bug — fix r2_cmd to honor Phase 8 D-20 step d's cancellation
      contract. This is the only one of the three that represents a production
      correctness gap. Severity: medium — orphaned r2 subprocesses on client
      disconnect leak until idle-reaper sweep or registry shutdown.

verification: (not applied — diagnose-only)
files_changed: []
