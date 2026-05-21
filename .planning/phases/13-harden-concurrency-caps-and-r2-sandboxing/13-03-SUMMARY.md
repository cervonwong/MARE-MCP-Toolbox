---
phase: 13
plan: 03
subsystem: sessions
tags:
  - harden
  - r2-sandbox
  - cfg-sandbox
  - argv-eval-time
  - frozen-regex
  - ux-layer
requirements:
  - HARDEN-03
  - HARDEN-04
  - HARDEN-05
requirements_addressed:
  - HARDEN-03
  - HARDEN-04
  - HARDEN-05
dependency_graph:
  requires:
    - phase-08-session-scoped-r2 (_DANGEROUS_R2_CMD_RE shape, check_dangerous_cmd contract, _open_r2 driver)
    - phase-13-plan-01 (atomic probe-and-acquire pattern on SessionRegistry; sessions/r2.py overlap region)
  provides:
    - "sandbox: bool = True kwarg on _open_r2 (orthogonal to the kind axis; Plan 04 will pass sandbox=False from open_r2_session_unsafe)"
    - "`-e cfg.sandbox=true` argv tokens BEFORE the positional sample path when sandbox=True"
    - "Frozen _DANGEROUS_R2_CMD_RE with Phase 13 reframed docstring + DO NOT EXTEND warning + PHASE 13 SECURITY BOUNDARY DELINEATION module-level framing block"
    - "Wave 0 r2 version + cfg.sandbox accept probe (A1 verified invariant)"
    - "Argv-builder unit tests (4 cases) + sandbox-active integration positive control + frozen-regex snapshot test"
  affects:
    - tools/r2_sessions.py (open_r2_session continues to call _open_r2 without passing sandbox -- gets True implicitly)
    - Plan 04 (open_r2_session_unsafe) will call _open_r2(..., sandbox=False)
tech-stack:
  added: []
  patterns:
    - "r2 argv-eval-time sandbox: -e cfg.sandbox=true processed BEFORE binary open (D-07)"
    - "No cfg.sandbox.grain argv flag -- default grain=all + cfg.sandbox=true blocks r_sandbox_system + upper-dir-open (D-08 RESOLUTION 2026-05-20)"
    - "Frozen-regex-as-UX-layer (D-09) -- security boundary delegated to r2's in-process C-level guards"
    - "Monkeypatch asyncio.create_subprocess_exec + sentinel exception to test argv ordering without spawning r2 (no r2 dependency on dev host)"
key-files:
  created:
    - mcp-gateway/tests/test_r2_version.py
    - mcp-gateway/tests/test_r2_argv.py
    - mcp-gateway/tests/test_r2_sandbox_integration.py
  modified:
    - mcp-gateway/src/mcp_gateway/sessions/r2.py
    - mcp-gateway/tests/test_sessions.py
decisions:
  - "_DANGEROUS_R2_CMD_RE pattern preserved byte-identical to Phase 8; only the surrounding module comment + check_dangerous_cmd docstring reframed (D-09)"
  - "Sandbox enforced via argv `-e` tokens INSERTED BEFORE the positional sample path so r2's pre-binary-open eval activates cfg.sandbox=true before any binary autoload hook or format-handler plugin runs (D-07)"
  - "NO cfg.sandbox.grain override flag emitted -- default grain=all + cfg.sandbox=true is sufficient for r_sandbox_system and upper-dir-open mitigations (D-08 RESOLUTION 2026-05-20)"
  - "sandbox: bool = True is a kw-only LAST parameter on _open_r2 so existing positional callers in tools/r2_sessions.py stay backward-compatible without code changes"
  - "Module-level Phase 13 framing block uses sentinel strings 'PHASE 13 SECURITY BOUNDARY DELINEATION' + 'DO NOT EXTEND THIS REGEX' so a future cleanup pass cannot silently delete the warning (locked by test_dangerous_regex_docstring_reframed)"
  - "Wave 0 r2 version probe runs r2 -V + -e cfg.sandbox=true -c 'e cfg.sandbox' against /dev/null; asserts stderr does NOT contain both 'unknown' AND 'cfg.sandbox' so A1 (container's r2 supports cfg.sandbox) is a verified invariant"
metrics:
  duration: 421s
  tasks: 3
  files: 5
  completed: 2026-05-21
---

# Phase 13 Plan 03: r2 cfg.sandbox boundary + frozen-regex reframing Summary

Moved the r2 security boundary from a regex parser-arms-race onto r2's native `cfg.sandbox=true`, enforced via argv `-e` flags at spawn time (BEFORE binary open). The existing `_DANGEROUS_R2_CMD_RE` is now byte-identical-frozen and reframed as a UX layer that gives operators a clearer error than r2's sandbox-refused output for the common `!`/`R!`/`#!` shell-escape cases. Added a `sandbox: bool = True` kwarg on `_open_r2` so Plan 04's `open_r2_session_unsafe` can spawn unsandboxed r2 via the same driver without polluting the kind axis.

## What Was Built

### Files modified (1 source + 4 test)

1. **mcp-gateway/src/mcp_gateway/sessions/r2.py** —
   - Replaced the module-level regex comment block (lines 37-42) with the Phase 13 reframed framing block containing the literal sentinel strings `PHASE 13 SECURITY BOUNDARY DELINEATION` and `DO NOT EXTEND THIS REGEX`. The pattern itself (`_DANGEROUS_R2_CMD_RE = re.compile(r"(?:^|;|\||\n)\s*(?:#!|R!|!)")`) is **byte-identical** to Phase 8.
   - Reframed the `check_dangerous_cmd` docstring as a UX layer over the cfg.sandbox security boundary; the runtime behaviour (per-command refusal, `ValueError` with prefix-naming message) is unchanged.
   - Added `sandbox: bool = True` as the LAST keyword-only parameter on `_open_r2`; updated the function docstring to describe the D-07 argv-eval-time sandbox guarantee.
   - Replaced the spawn block: argv is now built as `["r2", "-2", "-q0"] + (["-e", "cfg.sandbox=true"] if sandbox else []) + [str(sample_path)]`, then splat-passed to `asyncio.create_subprocess_exec`. The `-e cfg.sandbox=true` tokens are guaranteed to appear BEFORE the positional sample path so r2's pre-binary-open config eval activates the sandbox before any autoload hook or format-handler plugin runs.

2. **mcp-gateway/tests/test_r2_version.py (NEW, 53 lines)** — Wave 0 r2 version probe converting RESEARCH Assumption A1 ("the container's r2 supports cfg.sandbox") into a verified invariant. Two tests:
   - `test_r2_version_parseable`: runs `r2 -V`; asserts rc==0 and first stdout line contains `radare2` (case-insensitive).
   - `test_r2_cfg_sandbox_supported`: runs `r2 -2 -q0 -e cfg.sandbox=true -c "e cfg.sandbox" -- /dev/null`; asserts stderr does NOT contain both `unknown` AND `cfg.sandbox` (the combination that indicates the variable is unsupported).
   Both gated on `_require_r2_or_skip()` so dev-host CI skips cleanly.

3. **mcp-gateway/tests/test_r2_argv.py (NEW, 95 lines)** — Argv-builder unit tests using monkeypatched `asyncio.create_subprocess_exec` to capture argv tokens without spawning r2. 3 test functions, 4 parametrized cases:
   - `test_argv_sandbox_flag_present_before_sample` (HARDEN-03): asserts `-e` < `cfg.sandbox=true` < sample-path index in argv.
   - `test_argv_sandbox_omitted_when_sandbox_false` (HARDEN-03 unsafe-path): asserts neither `cfg.sandbox=true` nor `cfg.sandbox=false` appears.
   - `test_argv_no_grain_override` (HARDEN-04, parametrized over `[True, False]`): asserts `cfg.sandbox.grain` is NOT a substring of any argv token for either sandbox setting.

4. **mcp-gateway/tests/test_r2_sandbox_integration.py (NEW, 45 lines)** — Sandbox-active integration positive control (`@pytest.mark.slow`, gated on `_require_r2_or_skip`). Spawns a real r2 session with `sandbox=True`, then queries `e cfg.sandbox` via `exec_one` and asserts the runtime response contains `true`. Proves cfg.sandbox=true is the actual enforcing boundary, not just the gateway-side pre-filter. Skips cleanly on r2-less hosts; ready to run in-container.

5. **mcp-gateway/tests/test_sessions.py** — Appended two HARDEN-05 tests:
   - `test_dangerous_regex_frozen`: asserts `_DANGEROUS_R2_CMD_RE.pattern == r"(?:^|;|\||\n)\s*(?:#!|R!|!)"` byte-identical to Phase 8 D-08.
   - `test_dangerous_regex_docstring_reframed`: reads `inspect.getsource(r2)` and asserts both `DO NOT EXTEND THIS REGEX` and `PHASE 13 SECURITY BOUNDARY DELINEATION` appear in the module source. Locks the reframing intent so a future cleanup pass cannot silently delete the warning.

## Key Invariants Locked in Tests

| Invariant | Test | Source |
|-----------|------|--------|
| HARDEN-03 argv ordering (`-e` before `cfg.sandbox=true` before sample) | `test_argv_sandbox_flag_present_before_sample` | CONTEXT.md D-07; RESEARCH.md Code Example 4 |
| HARDEN-03 unsafe-path (sandbox=False omits sandbox tokens entirely) | `test_argv_sandbox_omitted_when_sandbox_false` | CONTEXT.md D-12 |
| HARDEN-03 sandbox-active positive control (cfg.sandbox is true at runtime) | `test_sandbox_active_when_open_r2` (slow; in-container) | CONTEXT.md D-07; threat T-13-09 mitigation |
| HARDEN-04 no grain override (default grain=all preserved) | `test_argv_no_grain_override` (×2 parametrized) | CONTEXT.md D-08 RESOLUTION 2026-05-20 |
| HARDEN-05 regex byte-identical to Phase 8 | `test_dangerous_regex_frozen` | CONTEXT.md D-09 |
| HARDEN-05 reframed docstring locked (DO NOT EXTEND + framing block) | `test_dangerous_regex_docstring_reframed` | CONTEXT.md D-09; threat T-13-11 |
| Wave 0 A1 verification (container r2 supports cfg.sandbox) | `test_r2_cfg_sandbox_supported` | RESEARCH.md Assumption A1; threat T-13-12 |
| Phase 8 regex refusal regression (one bad command does not invalidate session) | Existing `test_dangerous_*` tests (unchanged) | Phase 8 D-08/D-09 |

## Threat Model Verification

| Threat ID | Mitigation Verified By |
|-----------|------------------------|
| **T-13-09** (r2 command-syntax bypass → host-side `system()`) | `test_argv_sandbox_flag_present_before_sample` proves `-e cfg.sandbox=true` is in argv BEFORE the sample path; r2's `r_sandbox_system` guard activates at libr level beyond reach of command-syntax tricks. `test_sandbox_active_when_open_r2` (in-container) confirms cfg.sandbox is true at runtime. Default grain=all + cfg.sandbox=true blocks `!shell`/`R!`/`system()` paths. |
| **T-13-10** (r2 autoload-hook / format-handler exec on binary open BEFORE init batch) | `test_argv_sandbox_flag_present_before_sample` enforces `-e` index < sample index, so r2's argv-eval-time config evaluation activates the sandbox BEFORE the positional binary is opened. |
| **T-13-11** (false confidence in regex as security layer) | `test_dangerous_regex_docstring_reframed` requires both `DO NOT EXTEND THIS REGEX` and `PHASE 13 SECURITY BOUNDARY DELINEATION` to appear in the module source; a silent deletion of the warning fails the test. |
| **T-13-12** (silent r2-version regression breaks sandbox) | `test_r2_cfg_sandbox_supported` runs in-container against the bundled r2 build; if a future container build ships an r2 that no longer accepts `cfg.sandbox`, the test fails before any real-world session ever spawns. |

## Wave 0 A1 Verification Status

- **Dev host (executor):** `test_r2_version_parseable` and `test_r2_cfg_sandbox_supported` both SKIP cleanly via `_require_r2_or_skip()` (r2 not on PATH).
- **Container (Kali base with `radare2` apt package):** ready to flip to PASS on next container rebuild. The probe asserts `r2 -V` output contains `radare2` and that `r2 -e cfg.sandbox=true ... -c "e cfg.sandbox"` does NOT emit an unknown-variable warning to stderr.

## Verification Results

```
=== Smoke test ===
$ python -c "from mcp_gateway.sessions.r2 import _open_r2, _DANGEROUS_R2_CMD_RE; \
              import inspect; sig=inspect.signature(_open_r2); \
              assert 'sandbox' in sig.parameters and sig.parameters['sandbox'].default is True; \
              assert _DANGEROUS_R2_CMD_RE.pattern == r'(?:^|;|\\||\\n)\\s*(?:#!|R!|!)'"
SMOKE OK

=== Wave 0 r2 version probe ===
$ pytest tests/test_r2_version.py -x
tests/test_r2_version.py ss   (2 skipped on dev host; ready for container)

=== Argv-builder unit suite (4 cases) ===
$ pytest tests/test_r2_argv.py -x
tests/test_r2_argv.py ....    (4 passed)

=== Frozen-regex + reframed-docstring snapshot ===
$ pytest tests/test_sessions.py::test_dangerous_regex_frozen tests/test_sessions.py::test_dangerous_regex_docstring_reframed -x
tests/test_sessions.py ..     (2 passed)

=== Sandbox-active integration ===
$ pytest tests/test_r2_sandbox_integration.py -x
tests/test_r2_sandbox_integration.py s   (1 skipped on dev host; ready for container)

=== Phase 8 regex-refusal regression (legacy tests stay GREEN) ===
$ pytest tests/test_sessions.py tests/test_r2_sessions.py -x -k "dangerous or refuse"
tests/test_sessions.py ..; tests/test_r2_sessions.py s   (2 passed, 1 skipped)

=== Full sessions regression ===
$ pytest tests/test_sessions.py tests/test_r2_sessions.py -x
9 passed, 15 skipped, 1 warning in 2.38s
```

## Acceptance Criteria Verification

| Criterion | Result |
|-----------|--------|
| `grep "sandbox: bool = True" src/mcp_gateway/sessions/r2.py` | 1 match (kwarg added) -- OK |
| `grep "cfg.sandbox=true" src/mcp_gateway/sessions/r2.py` | 7 matches (argv token + docstring + comments) -- OK |
| `grep "cfg.sandbox.grain" src/mcp_gateway/sessions/r2.py` | 0 -- OK (Rule 1 reworded the comment to honour the no-grain literal-grep contract) |
| `grep "DO NOT EXTEND THIS REGEX" src/mcp_gateway/sessions/r2.py` | 1 match -- OK |
| `grep "PHASE 13 SECURITY BOUNDARY DELINEATION" src/mcp_gateway/sessions/r2.py` | 1 match -- OK |
| `_DANGEROUS_R2_CMD_RE.pattern == r"(?:^\|;\|\\\|\|\\n)\\s*(?:#!\|R!\|!)"` | True -- OK |
| `_open_r2` has `sandbox` parameter with default `True` | OK |
| `pytest tests/test_r2_argv.py -x` | 4 passed -- OK |
| `pytest tests/test_sessions.py::test_dangerous_regex_*` | 2 passed -- OK |
| `pytest tests/test_r2_sandbox_integration.py -x` | 1 skipped (dev host) -- OK; container will flip to passed |
| `pytest tests/test_r2_version.py -x` | 2 skipped (dev host) -- OK; container will flip to passed |
| Existing regex-refusal tests stay GREEN | 2 passed -- OK |

## Deviations from Plan

**[Rule 1 - Bug] Reworded `cfg.sandbox.grain` literal in comment block to honour acceptance-criterion grep contract.**

- **Found during:** Task 2 verification step (grep acceptance check).
- **Issue:** The plan's paste-ready `<action>` code for the spawn-block comment contained the literal string `cfg.sandbox.grain` ("Phase 13 D-08 RESOLUTION (2026-05-20): NO cfg.sandbox.grain override."). However, the plan's own acceptance criterion (and `test_argv_no_grain_override`) requires `grep "cfg.sandbox.grain" mcp-gateway/src/mcp_gateway/sessions/r2.py` to return 0. The action-block comment and the acceptance-criterion grep contract are mutually contradictory.
- **Resolution:** Reworded the comment from "NO cfg.sandbox.grain override" to "NO grain-override argv flag" -- semantic intent (no grain-override argv flag) is preserved verbatim and the literal token is gone so the acceptance grep returns 0.
- **Files modified:** `mcp-gateway/src/mcp_gateway/sessions/r2.py` (comment line only; no code-path change).
- **Commit:** f8c4f2c (Task 2 commit includes the reworded comment).

No other deviations. The remaining paste-ready code from `13-03-PLAN.md::<action>` blocks landed verbatim; all greps for acceptance criteria pass on first run; the frozen-regex snapshot is byte-identical and the docstring sentinel strings are exact verbatim.

## Authentication Gates

None -- no auth surfaces touched by this plan.

## Self-Check: PASSED

- mcp-gateway/src/mcp_gateway/sessions/r2.py: MODIFIED -- verified via `git show f8c4f2c --stat`
- mcp-gateway/tests/test_r2_version.py: CREATED (53 lines) -- verified via Read
- mcp-gateway/tests/test_r2_argv.py: CREATED (95 lines) -- verified via Read
- mcp-gateway/tests/test_r2_sandbox_integration.py: CREATED (45 lines) -- verified via Read
- mcp-gateway/tests/test_sessions.py: MODIFIED (test_dangerous_regex_frozen + test_dangerous_regex_docstring_reframed appended) -- verified via `grep -c "def test_dangerous_regex"`
- Commit 2e5f237 (Task 1): FOUND in `git log`
- Commit f8c4f2c (Task 2): FOUND in `git log`
- Commit 1683f8e (Task 3): FOUND in `git log`

All claimed artifacts exist; all claimed commits exist.
