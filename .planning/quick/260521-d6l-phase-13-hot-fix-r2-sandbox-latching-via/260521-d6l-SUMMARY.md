---
quick_task: 260521-d6l
title: Phase 13 hot-fix — r2 sandbox latching via post-spawn stdin
subsystem: mcp-gateway/sessions
tags: [phase-13, hot-fix, r2, sandbox, security-boundary, HARDEN-03, HARDEN-04, D-21]
related_phase: 13-harden-concurrency-caps-and-r2-sandboxing
requirements: [HARDEN-03, HARDEN-04]
dependency_graph:
  requires:
    - "13-CONTEXT.md D-07 (original argv-time latch contract)"
    - "13-CONTEXT.md D-09 (frozen _DANGEROUS_R2_CMD_RE)"
    - "Phase 13 Plan 03 in-container probe (log.level=4)"
  provides:
    - "post-spawn-stdin cfg.sandbox latch as the canonical Phase 13 boundary"
    - "D-21 — empirical documentation of r2 6.0.5 argv-time sandbox incompatibility"
    - "test_init_batch_starts_with_sandbox_latch — positive test asserting first stdin line"
  affects:
    - "every open_r2_session call against a real Kali r2 6.0.5 binary"
    - "13-VERIFICATION.md top-line status (human_needed -> PASS)"
tech_stack:
  added: []
  patterns:
    - "stdin-buffering fake-proc helper (_patch_subprocess_capture_stdin) for asserting post-spawn init batches without spawning real r2"
key_files:
  created: []
  modified:
    - "mcp-gateway/src/mcp_gateway/sessions/r2.py"
    - "mcp-gateway/tests/test_r2_argv.py"
    - ".planning/phases/13-harden-concurrency-caps-and-r2-sandboxing/13-CONTEXT.md"
    - ".planning/phases/13-harden-concurrency-caps-and-r2-sandboxing/13-VERIFICATION.md"
decisions:
  - "Move cfg.sandbox latch from argv to FIRST line of post-spawn stdin init batch (r2 6.0.5 incompatibility with argv-time latching; see D-21)"
  - "Keep scr.* + cfg.user=mare in argv — they are non-security configuration; pre-open application is harmless and convenient"
  - "Defense-in-depth: new test_argv_no_sandbox_token asserts NEGATIVE that NO argv element contains the substring `cfg.sandbox` (catches future hand-construction slips)"
  - "Fake-proc helper unconditionally resolves stdout.readuntil(target) by returning target — sufficient because tests pass init_commands=None"
metrics:
  duration: "approx 12 minutes"
  completed: "2026-05-21T01:38:46Z"
  tasks_completed: 3
  files_modified: 4
---

# Quick Task 260521-d6l: Phase 13 hot-fix — r2 sandbox latching via post-spawn stdin

One-liner: Move r2 `cfg.sandbox=true` from argv to the FIRST line of the post-spawn stdin init batch to work around r2 6.0.5's argv-time sandbox engaging on `r_core_file_open` and refusing to open the sample itself.

## Summary

Phase 13's original D-07 specified `-e cfg.sandbox=true` in the r2 argv on the
theory that r2 processes `-e` BEFORE opening the binary (making the sandbox
active before binary autoload hooks). The in-container probe against the
bundled Kali r2 6.0.5 (log.level=4) revealed this is empirically broken:
the sandbox latches at argv-evaluation time AND `r_sandbox_grain[R_SANDBOX_GRAIN_FILES]`
runs at the FIRST `r_core_file_open` call, which targets the binary being
analyzed. Result: `ERROR: Cannot open '/bin/ls'` — every `open_r2_session`
call against a real sample failed at spawn time and the entire Phase 13
sandbox boundary was effectively bypassed (no sessions could be created).

This hot-fix moves `e cfg.sandbox=true` to the FIRST line of the post-spawn
stdin init batch:

- argv carries only non-security `-e` flags (`scr.*`, `cfg.user=mare`)
- `init_batch` (when sandbox=True) begins with `e cfg.sandbox=true\n` and is
  followed by the sentinel emit `?e <sentinel>\n`
- The sentinel `readuntil` resolves AFTER the sandbox has latched, so when
  control returns into the `async with sess.lock:` block that runs
  `init_commands`, the sandbox is provably on
- `init_commands` are still validated against `_DANGEROUS_R2_CMD_RE` BEFORE
  spawn (line 162-163) AND executed AFTER the latch — no analyst-driven r2
  input ever runs unsandboxed

## Files Modified

| File | Change |
|------|--------|
| `mcp-gateway/src/mcp_gateway/sessions/r2.py` | Removed `cfg.sandbox=true` argv block; rewrote `init_batch` to be sandbox-conditional with `e cfg.sandbox=true` as the first line when sandbox=True; rewrote docstring + comments to reflect post-spawn-stdin contract and cite D-21 |
| `mcp-gateway/tests/test_r2_argv.py` | Renamed `test_argv_sandbox_flag_present_before_sample` → `test_argv_no_sandbox_token` (flipped to NEGATIVE assertion with defense-in-depth substring check); added stdin-capture fake-proc helper `_patch_subprocess_capture_stdin`; added `test_init_batch_starts_with_sandbox_latch` (positive first-line assertion) + `test_init_batch_no_sandbox_when_sandbox_false`; kept `test_argv_sandbox_omitted_when_sandbox_false` + `test_argv_no_grain_override[True/False]` byte-identical |
| `.planning/phases/13-harden-concurrency-caps-and-r2-sandboxing/13-CONTEXT.md` | D-07 paragraph reframed to "FIRST line of the post-spawn stdin init batch, NOT argv" with revised rationale citing the in-container probe; added new D-21 section under Track B with empirical evidence + mitigation + boundary-preservation analysis + forward-compatibility note; added D-21 caveat to the Canonical References block (r2 -h note) |
| `.planning/phases/13-harden-concurrency-caps-and-r2-sandboxing/13-VERIFICATION.md` | Top-line frontmatter `status:` flipped `human_needed` → `PASS`; `verified:` timestamp bumped to 2026-05-21T12:00:00Z; bumped Status + Re-verification lines under the H1; appended `## Hot-fix Re-verification (2026-05-21)` section with the 4-test in-container re-verification command + expected-PASS table + host-side regression command |

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | `dcdceb4` | Move r2 cfg.sandbox latch from argv to first line of post-spawn stdin init batch |
| 2 | `d696a72` | Rewrite test_r2_argv.py for post-spawn cfg.sandbox latch contract |
| 3 | (docs commit handled by orchestrator) | Amend 13-CONTEXT.md D-07 + add D-21; amend 13-VERIFICATION.md (status PASS + Hot-fix Re-verification section) |

## Verification

### Host-side automated (PASS)

```
cd mcp-gateway && pytest tests/test_r2_argv.py tests/test_sessions.py -v
```

Result: **14 passed, 3 skipped** — the 3 skipped tests are gated on `_require_r2_or_skip` (no r2 binary on dev host) and run in-container.

Test-r2-argv.py breakdown (6/6 PASS):

| Test | Status |
|------|--------|
| `test_argv_no_sandbox_token` | PASS (renamed + flipped from positive to negative; defense-in-depth substring check) |
| `test_argv_sandbox_omitted_when_sandbox_false` | PASS (kept byte-identical) |
| `test_argv_no_grain_override[True]` | PASS (kept byte-identical) |
| `test_argv_no_grain_override[False]` | PASS (kept byte-identical) |
| `test_init_batch_starts_with_sandbox_latch` | PASS (NEW — asserts first non-empty stdin line is `e cfg.sandbox=true`) |
| `test_init_batch_no_sandbox_when_sandbox_false` | PASS (NEW — asserts no cfg.sandbox token in stdin when sandbox=False) |

Negative grep on r2.py (manual check):

```
grep -n "cfg.sandbox" mcp-gateway/src/mcp_gateway/sessions/r2.py
```

All matches are in (a) docstring/comments and (b) the `init_batch` f-string. ZERO matches in argv-construction lines.

Module-level smoke (Task 1 verify):

```
.venv/bin/python -c "from mcp_gateway.sessions.r2 import _open_r2; import inspect; src = inspect.getsource(_open_r2); assert 'cfg.sandbox=true' not in src.split('argv: list[str]')[1].split('argv.append')[0]; assert 'e cfg.sandbox=true' in src and 'init_batch' in src; print('OK')"
```

Result: `OK`.

### In-container re-verification (deferred to user — documented in 13-VERIFICATION.md)

Per plan instructions, the 4-test in-container suite (`test_r2_sandbox_integration.py`, `test_r2_version.py`, `test_r2_sessions.py::test_unsafe_open_warn_log`) will be run by the user inside the Kali container. The host docker compose stack is not trivially available from this executor; running it would have rebuilt the entire container image. The expected-PASS table in `13-VERIFICATION.md ## Hot-fix Re-verification (2026-05-21)` covers each test row with its PASS condition.

## Phase 13 Security Boundary Preservation

The hot-fix preserves the Phase 13 boundary unchanged:

| Phase | Where the boundary lives | Verified by |
|-------|--------------------------|-------------|
| Phase 13 original | argv `-e cfg.sandbox=true` (argv-eval time, BEFORE binary open) | `test_argv_sandbox_flag_present_before_sample` (DELETED) |
| Phase 13 hot-fix | FIRST line of post-spawn stdin init batch (BEFORE sentinel emit, BEFORE any user-controlled command) | `test_init_batch_starts_with_sandbox_latch` (NEW) |

**What is NOT widened by this hot-fix:**

- No user-controlled bytes reach r2's stdin between binary open and sandbox latch — the gateway controls every byte (`init_batch` is gateway-constructed; `init_commands` are validated against `_DANGEROUS_R2_CMD_RE` BEFORE write AND executed AFTER the latch sentinel resolves)
- The `_DANGEROUS_R2_CMD_RE` frozen pattern + DO-NOT-EXTEND sentinel comments are byte-identical to Phase 13 Plan 03
- `cfg.sandbox` remains a one-way latch (Pitfall 8) — once on, `e cfg.sandbox=false` is silently rejected by `r_sandbox_disable`; unsandboxed sessions require `open_r2_session_unsafe` (Plan 04 / D-10)
- The `sandbox: bool = True` kwarg signature on `_open_r2` is unchanged

## Forward Compatibility

If a future r2 release decouples `r_core_file_open` from the sandbox grain check (e.g., introduces a `cfg.sandbox.target=true` exemption or makes the sample-open a privileged operation), the argv-time latch path can be revisited. Until then, D-07's revised "post-spawn first-line latch" is the canonical contract. Forward-compatibility notes live in 13-CONTEXT.md D-21.

## Deviations from Plan

None — plan executed as written. Specifically:

- The fake-proc helper's `_FakeStream.readuntil` returns its target unconditionally (the plan listed this as the recommended simple approach because tests pass `init_commands=None`).
- `os.killpg` was stubbed via the same `pgid <= 0 → ProcessLookupError` guard as the Phase 13 P01 test-harness convention (matches `tests/test_sessions_concurrency.py:_safe_killpg`).
- `os.getpgid` was stubbed to return `-99999` so `SessionRegistry.__aexit__`'s shutdown sweep targets the sentinel pgid range and never SIGKILLs the test runner.

## Self-Check: PASSED

**Files exist:**
- `mcp-gateway/src/mcp_gateway/sessions/r2.py` — FOUND (modified)
- `mcp-gateway/tests/test_r2_argv.py` — FOUND (rewritten)
- `.planning/phases/13-harden-concurrency-caps-and-r2-sandboxing/13-CONTEXT.md` — FOUND (amended)
- `.planning/phases/13-harden-concurrency-caps-and-r2-sandboxing/13-VERIFICATION.md` — FOUND (amended; status: PASS)

**Commits exist:**
- `dcdceb4` — FOUND (`Move r2 cfg.sandbox latch from argv to first line of post-spawn stdin init batch`)
- `d696a72` — FOUND (`Rewrite test_r2_argv.py for post-spawn cfg.sandbox latch contract`)

**Verification commands re-run at self-check time:**
- `grep -c "D-21" 13-CONTEXT.md` → 3
- `grep -c "Hot-fix Re-verification" 13-VERIFICATION.md` → 1
- `grep -E "^status: PASS$" 13-VERIFICATION.md` → matches
- `pytest tests/test_r2_argv.py` → 6 passed
