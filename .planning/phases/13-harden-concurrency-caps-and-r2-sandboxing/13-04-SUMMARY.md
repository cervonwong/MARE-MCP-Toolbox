---
phase: 13
plan: 04
subsystem: tools
tags:
  - harden
  - r2-sandbox
  - env-gated-tool
  - audit-log
  - tools-list-axis
  - cap-sharing
requirements:
  - HARDEN-06
requirements_addressed:
  - HARDEN-06
dependency_graph:
  requires:
    - phase-13-plan-01 (SessionRegistry self._sem combined cap; _slot_released flag)
    - phase-13-plan-03 (sandbox: bool = True kwarg on _open_r2 driver)
    - phase-11-dynamic-lab-mode-env-gated (DYN-01 env-gated registration pattern template)
  provides:
    - "MCP tool open_r2_session_unsafe registered iff MCP_GATEWAY_R2_UNSAFE_ALLOWED=1"
    - "register_unsafe(mcp) factored separately from register(mcp) so the four safe tools stay always-on"
    - "sandbox: bool = True kwarg forwarding through SessionRegistry.open() into _open_r2"
    - "WARN-level audit log line for every unsafe-r2 open (session_id, sample_sha256[:8], case_dir)"
    - "4-case (dynamic × unsafe) tool-list axis: 54 / 55 / 61 / 62 tools"
  affects:
    - tools/__init__.py (env-gate block AFTER dynamic-mode block, BEFORE backend_passthrough)
    - sessions/_base.py::SessionRegistry.open (sandbox kwarg forwards to _open_r2; ignored for gdb)
tech-stack:
  added: []
  patterns:
    - "Env-gated MCP tool registration (mirrors Phase 11 DYN-01 MCP_GATEWAY_DYNAMIC_TOOLS pattern)"
    - "Separate MCP surface (D-10) — no flag on the safe tool; the tool IS the unsafe variant"
    - "WARN-level audit log via stdlib logging.getLogger (D-11)"
    - "Q6 combined-cap sharing via single SessionRegistry._sem (no per-kind quotas)"
key-files:
  created: []
  modified:
    - mcp-gateway/src/mcp_gateway/sessions/_base.py
    - mcp-gateway/src/mcp_gateway/tools/r2_sessions.py
    - mcp-gateway/src/mcp_gateway/tools/__init__.py
    - mcp-gateway/tests/test_tool_list.py
    - mcp-gateway/tests/test_r2_sessions.py
decisions:
  - "open_r2_session_unsafe is a SEPARATE MCP tool, not a kwarg on open_r2_session (D-10) — keeps tools/list audit visible from outside the container"
  - "SessionRegistry.open() gains sandbox: bool = True keyword-only param; forwarded only on the r2 branch (gdb branch silently ignores it per D-12 docstring)"
  - "register_unsafe(mcp) factored as a SEPARATE function from register(mcp); tools/__init__.py calls register_unsafe iff env=1 — keeps the four safe tools always-on and the unsafe tool conditionally added"
  - "WARN-log fields are (session_id, sample_sha256[:8], case_dir) — minimum needed for audit grep without leaking the full sample sha or environment"
  - "warnings response field carries the literal string 'r2 sandbox is DISABLED for this session' so clients can detect unsafe sessions without inspecting the tool name"
  - "Tool-list axis test is a NEW dedicated parametrize (4-case product) appended at the file tail, rather than re-shaping every existing test — minimises Rule-1 deviations"
  - "Cap-sharing test stubs _open_r2 to exercise the Plan 01 atomic probe-and-acquire flow without spawning real r2; sentinel pgid=-99999 + autouse os.killpg refusing non-positive pgids (Plan 01 test discipline)"
metrics:
  duration: 455s
  tasks: 2
  files: 5
  completed: 2026-05-21
---

# Phase 13 Plan 04: Env-gated open_r2_session_unsafe + WARN-log + shared cap Summary

Added an opt-in `open_r2_session_unsafe` MCP tool that spawns r2 WITHOUT `cfg.sandbox=true`, gated behind `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1` at gateway startup. The tool mirrors `open_r2_session`'s shape but routes through the Plan 03 `_open_r2(..., sandbox=False)` driver kwarg via a new `sandbox: bool = True` parameter on `SessionRegistry.open()`. Every successful unsafe-open emits a `logging.WARNING` line with `session_id`, `sample_sha256[:8]`, and `case_dir` for audit-trail visibility. The unsafe path shares the SAME combined SessionRegistry cap as safe r2 + gdb sessions (Q6 resolution).

## What Was Built

### Files modified (3 source + 2 test)

1. **mcp-gateway/src/mcp_gateway/sessions/_base.py** — `SessionRegistry.open()` gains a new keyword-only `sandbox: bool = True` parameter. When `kind="r2"`, the kwarg is forwarded to `_open_r2`. When `kind="gdb"`, the kwarg is silently ignored (documented in the docstring) — gdb has no `cfg.sandbox`-equivalent and its security boundary is the MI allowlist + deny regex (Phase 11 D-07). Default `True` preserves backward-compatible safe behavior for every Phase 8/9/10/11 caller (they never pass `sandbox`).

2. **mcp-gateway/src/mcp_gateway/tools/r2_sessions.py** — Added a new module-level `open_r2_session_unsafe` coroutine with the SAME signature as `open_r2_session` (the tool IS the unsafe variant — no flag on the MCP surface). Internally calls `registry.open(..., sandbox=False)`. After a successful open emits `log.warning("[r2_sessions] unsafe session opened: session_id=%s sample_sha256=%s case_dir=%s", ...)`. Response dict mirrors `open_r2_session` but the `warnings` field contains the literal string `"r2 sandbox is DISABLED for this session"`. Post-definition `__doc__` splice injects the standard `_SESS_05_DISCLAIMER_FULL` (matches the open_r2_session pattern). Added `register_unsafe(mcp)` function that registers ONLY this one tool.

3. **mcp-gateway/src/mcp_gateway/tools/__init__.py** — Added a new env-gate block AFTER the existing dynamic-mode block at lines 71-74 and BEFORE `backend_passthrough.register(mcp)`:
   ```python
   if _os.environ.get("MCP_GATEWAY_R2_UNSAFE_ALLOWED") == "1":
       r2_sessions.register_unsafe(mcp)
   ```
   The `r2_sessions` symbol is already imported via the top-of-function multi-import (line 46); no new import needed.

4. **mcp-gateway/tests/test_tool_list.py** — Added two new EXPECTED sets (`EXPECTED_TOOLS_BASELINE_UNSAFE` = 55, `EXPECTED_TOOLS_DYNAMIC_UNSAFE` = 62) plus three new tests:
   - `test_tool_list_with_unsafe_axis` — 4-case parametrize covering the full `(dynamic_env, unsafe_env)` cross-product against exact-set expected (54 / 55 / 61 / 62 tools).
   - `test_unsafe_r2_absent_baseline` — Asserts `open_r2_session_unsafe` is NOT in `tools/list` when `MCP_GATEWAY_R2_UNSAFE_ALLOWED` is unset.
   - `test_unsafe_r2_present_with_env` — Asserts `open_r2_session_unsafe` IS in `tools/list` when the env=1.

5. **mcp-gateway/tests/test_r2_sessions.py** — Three new behavioural tests:
   - `test_unsafe_passes_sandbox_false` (unit, no r2 spawn): Monkeypatches `sessions.r2.asyncio.create_subprocess_exec` to capture argv via a sentinel exception. Asserts the captured argv does NOT contain `"cfg.sandbox=true"`, proving `sandbox=False` propagates from the tool → `SessionRegistry.open()` → `_open_r2` → spawn argv.
   - `test_unsafe_open_warn_log` (integration, `@pytest.mark.slow` + `_require_r2_or_skip`): Uses `caplog` to capture WARNING records on logger `mcp_gateway.tools.r2_sessions`. Asserts at least one record exists whose message contains `unsafe session opened`, `session_id=`, `sample_sha256=`, and `case_dir=`. Also asserts the response `warnings` field equals `["r2 sandbox is DISABLED for this session"]`. Skips on dev host (passes in container).
   - `test_unsafe_shares_combined_cap` (Q6 unit, no r2 spawn): Stubs `_open_r2` to exercise the Plan 01 atomic probe-and-acquire flow without spawning r2. Builds a `SessionRegistry(max_sessions=2)`; opens 1 safe + 1 unsafe session successfully; asserts a 3rd `open_r2_session_unsafe` call returns the `SessionCapReached` error dict and `reg._sem.locked()` is `True`. Uses sentinel `pgid=-99999` + autouse `os.killpg` guard refusing non-positive pgids (Plan 01 test discipline).

## Key Invariants Locked in Tests

| Invariant | Test | Source |
|-----------|------|--------|
| HARDEN-06 env-gated visibility (4-case axis: 54/55/61/62) | `test_tool_list_with_unsafe_axis` | CONTEXT.md D-10; threat T-13-13 |
| HARDEN-06 absent when env unset | `test_unsafe_r2_absent_baseline` | CONTEXT.md D-10 |
| HARDEN-06 present when env=1 | `test_unsafe_r2_present_with_env` | CONTEXT.md D-10 |
| HARDEN-06 sandbox=False propagation through SessionRegistry.open → _open_r2 | `test_unsafe_passes_sandbox_false` | CONTEXT.md D-12; threat T-13-15 |
| HARDEN-06 / D-11 WARN-log audit trail (session_id + sha256[:8] + case_dir) | `test_unsafe_open_warn_log` (slow; in-container) | CONTEXT.md D-11; threat T-13-14 |
| HARDEN-06 Q6 combined-cap sharing (unsafe shares the same `_sem`) | `test_unsafe_shares_combined_cap` | CONTEXT.md Q6; threat T-13-16 |
| Tool-count surface: 54 baseline / 55 baseline+unsafe / 61 dynamic / 62 dynamic+unsafe | `test_tool_list_with_unsafe_axis` (exact-set assertion) | Plan 04 must_haves |

## Threat Model Verification

| Threat ID | Mitigation Verified By |
|-----------|------------------------|
| **T-13-13** (information disclosure — unintended capability advertisement) | `test_unsafe_r2_absent_baseline` + `test_tool_list_with_unsafe_axis` (env=None branches) prove the unsafe tool is NEVER in `tools/list` when the env is unset. Default container shape is unchanged. |
| **T-13-14** (repudiation — unsandboxed r2 usage not audit-trailed) | `test_unsafe_open_warn_log` captures the WARN-level log record on `mcp_gateway.tools.r2_sessions` and asserts the required fields (`session_id=`, `sample_sha256=`, `case_dir=`). Operators grepping logs for `"unsafe session opened"` can audit every invocation. |
| **T-13-15** (EoP — unsafe path leaks to safe-tool callers) | `test_unsafe_passes_sandbox_false` proves `sandbox=False` only flows from `open_r2_session_unsafe` (no flag on the safe tool); the captured argv never contains `cfg.sandbox=true` on the unsafe path. The driver-layer `sandbox: bool = True` default + separate MCP surface make accidental leakage structurally impossible. |
| **T-13-16** (DoS — unsafe sessions evade combined cap) | `test_unsafe_shares_combined_cap` builds a `max_sessions=2` registry, opens 1 safe + 1 unsafe, asserts the 3rd unsafe call hits `SessionCapReached` (cap shared with safe + gdb) and `reg._sem.locked()` is `True`. Q6 resolution is locked. |

## Tool-Count Surface (4-case axis)

| `MCP_GATEWAY_DYNAMIC_TOOLS` | `MCP_GATEWAY_R2_UNSAFE_ALLOWED` | Tool count | Set name |
|---|---|---|---|
| unset | unset | 54 | `EXPECTED_TOOLS_BASELINE` |
| unset | `1` | 55 | `EXPECTED_TOOLS_BASELINE_UNSAFE` |
| `1` | unset | 61 | `EXPECTED_TOOLS_DYNAMIC` |
| `1` | `1` | 62 | `EXPECTED_TOOLS_DYNAMIC_UNSAFE` |

## Verification Results

```
=== Smoke imports ===
$ python -c "from mcp_gateway.tools.r2_sessions import open_r2_session_unsafe, register_unsafe; \
              from mcp_gateway.sessions._base import SessionRegistry; \
              import inspect; sig=inspect.signature(SessionRegistry.open); \
              assert 'sandbox' in sig.parameters and sig.parameters['sandbox'].default is True"
SMOKE OK

=== Env-unset tool-list visibility ===
$ python -c "...register_all_tools(m); assert 'open_r2_session_unsafe' not in tool_names"
UNREGISTERED OK -- env unset

=== Tool-list 4-case axis ===
$ pytest tests/test_tool_list.py::test_tool_list_with_unsafe_axis -x
4 passed

=== Tool-list new absence/presence tests ===
$ pytest tests/test_tool_list.py::test_unsafe_r2_absent_baseline tests/test_tool_list.py::test_unsafe_r2_present_with_env -x
2 passed

=== Full tool-list regression (existing 15 tests stay GREEN) ===
$ pytest tests/test_tool_list.py -x
15 passed

=== Unsafe behavioural tests (sandbox=False propagation + shared cap) ===
$ pytest tests/test_r2_sessions.py::test_unsafe_passes_sandbox_false \
         tests/test_r2_sessions.py::test_unsafe_shares_combined_cap -x
2 passed

=== Unsafe WARN-log test (slow; in-container) ===
$ pytest tests/test_r2_sessions.py::test_unsafe_open_warn_log -v
1 skipped (r2 unavailable on host; ready for container)

=== Full sessions regression (Phase 8/11/13) ===
$ pytest tests/test_r2_sessions.py tests/test_tool_list.py tests/test_sessions.py \
         tests/test_sessions_package.py tests/test_sessions_concurrency.py \
         tests/test_gdb_session.py -k "not slow"
97 passed, 15 skipped, 3 deselected
```

## Acceptance Criteria Verification

| Criterion | Result |
|-----------|--------|
| `grep "async def open_r2_session_unsafe" mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` | 1 -- OK |
| `grep "def register_unsafe" mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` | 1 -- OK |
| `grep "MCP_GATEWAY_R2_UNSAFE_ALLOWED" mcp-gateway/src/mcp_gateway/tools/__init__.py` | 2 -- OK (comment + check) |
| `grep "r2_sessions.register_unsafe(mcp)" mcp-gateway/src/mcp_gateway/tools/__init__.py` | 1 -- OK |
| `grep "sandbox: bool = True" mcp-gateway/src/mcp_gateway/sessions/_base.py` | 1 -- OK |
| `grep "sandbox=sandbox" mcp-gateway/src/mcp_gateway/sessions/_base.py` | 1 -- OK |
| `grep "sandbox=False" mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` | 2 -- OK (docstring + registry.open call) |
| `grep "log.warning" mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` | 1 -- OK |
| `grep "r2 sandbox is DISABLED for this session" mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` | 2 -- OK (docstring + warnings field) |
| `grep "EXPECTED_TOOLS_BASELINE_UNSAFE\|EXPECTED_TOOLS_DYNAMIC_UNSAFE" mcp-gateway/tests/test_tool_list.py` | 4 -- OK |
| `grep "def test_tool_list_with_unsafe_axis" mcp-gateway/tests/test_tool_list.py` | 1 -- OK |
| `grep "MCP_GATEWAY_R2_UNSAFE_ALLOWED" mcp-gateway/tests/test_tool_list.py` | 8 -- OK (>=2 required) |
| `grep -E "def test_unsafe_passes_sandbox_false\|def test_unsafe_open_warn_log\|def test_unsafe_shares_combined_cap" tests/test_r2_sessions.py` | 3 -- OK |
| `grep "assert names == expected" tests/test_tool_list.py` (exact-set assertion) | 1 -- OK |
| `pytest tests/test_tool_list.py::test_tool_list_with_unsafe_axis -x` | 4 passed -- OK |
| `pytest tests/test_r2_sessions.py::test_unsafe_passes_sandbox_false tests/test_r2_sessions.py::test_unsafe_shares_combined_cap -x` | 2 passed -- OK |
| `pytest tests/test_r2_sessions.py::test_unsafe_open_warn_log -x` | 1 skipped (dev host); ready for container -- OK |

## Deviations from Plan

**[Rule 1 - Bug] `test_unsafe_shares_combined_cap` stub session needed transcript path under case_dir.**

- **Found during:** Task 2 test execution.
- **Issue:** Initial stub `_open_r2` placed the synthetic `transcript_path` at `/tmp/{sid}-transcript.log`, but `open_r2_session_unsafe`'s response-building code calls `sess.transcript_path.relative_to(sess.case_dir)`, which raises `ValueError` when the transcript is outside the case dir.
- **Fix:** Materialise `case_dir/r2-sessions/` in the stub and place the transcript file under it; also cast `case_dir` (which arrives as `Path` from registry.open) consistently.
- **Files modified:** `mcp-gateway/tests/test_r2_sessions.py` (test infrastructure only; no production code change).
- **Commit:** d805b92 (included in Task 2 commit).

No other deviations. The Plan 04 paste-ready code in the `<action>` blocks landed verbatim for production code; the tool-list test extension followed the "dedicated parametrize at file tail" path (per plan's minimal-Rule-1-deviation hint) instead of rewriting every existing test.

## Authentication Gates

None — no auth surfaces touched by this plan.

## Deferred Issues

Two pre-existing pollution issues observed during full-suite regression but NOT caused by Plan 13-04 (logged in `deferred-items.md` per SCOPE BOUNDARY rule):

- Item #2: `tests/test_sessions_concurrency.py` — 6 tests pass in isolation, fail under full-suite ordering. Pre-existing since Plan 01.
- Item #3: `tests/test_r2_sessions.py::test_unsafe_shares_combined_cap` — passes in isolation, falls victim to the same cross-file module-state leak under full-suite ordering. Same root cause as #2.

Recommended quick-task fix: add a module-level `_full_reset_modules()` fixture to `test_sessions_concurrency.py` (mirrors `test_tool_list.py`'s pattern). ~10 LOC.

## Self-Check: PASSED

- mcp-gateway/src/mcp_gateway/sessions/_base.py: MODIFIED (verified via `git diff --stat`)
- mcp-gateway/src/mcp_gateway/tools/r2_sessions.py: MODIFIED
- mcp-gateway/src/mcp_gateway/tools/__init__.py: MODIFIED
- mcp-gateway/tests/test_tool_list.py: MODIFIED
- mcp-gateway/tests/test_r2_sessions.py: MODIFIED
- Commit c77e2fe (Task 1): FOUND in `git log`
- Commit d805b92 (Task 2): FOUND in `git log`

All claimed artifacts exist; all claimed commits exist.
