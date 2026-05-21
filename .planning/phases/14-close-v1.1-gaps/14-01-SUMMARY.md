---
phase: 14-close-v1.1-gaps
plan: 01
subsystem: testing
tags: [pytest, importlib-reload, python-package-attrs, session-cap, acl]

requires:
  - phase: 13-harden-concurrency-caps-and-r2-sandboxing
    provides: SessionCapReached class + open_r2_session_unsafe site (cap-share enforcement under test)
  - phase: 11-dynamic-lab-mode-env-gated
    provides: sessions/ package split (_base + r2 + gdb submodules + reload sweep)
  - phase: 8-session-scoped-r2
    provides: original SessionCapReached + r2_sessions.py wrapper layout
  - phase: 7-run-shell-typed-static-wrappers-re-artifacts
    provides: original test_acl_available.py D-04 contract

provides:
  - "Reload-safe SessionCapReached catch in tools/r2_sessions.py (live sys.modules-fetched sessions module)"
  - "Package-attribute re-bind for sessions.r2 / sessions.gdb after package reload"
  - "Container-only contract on test_setfacl_on_path via @pytest.mark.skipif"
  - "Full-suite pytest -m 'not slow' green baseline (595 passed, 49 skipped, 13 deselected, 0 failed)"

affects:
  - phase 14 plan 02 (REQUIREMENTS.md sync) — needs clean baseline
  - phase 14 plan 03 (ROADMAP.md sync) — needs clean baseline
  - phase 14 plan 04 (STATE.md/VALIDATION.md sync) — needs clean baseline
  - phase 14 plan 05 (live UAT) — needs rebuilt container whose image contains these fixes

tech-stack:
  added: []
  patterns:
    - "Refetch package module from sys.modules at catch time to survive sys.modules.pop + reimport"
    - "Re-bind submodule names as PACKAGE attributes (_sys.modules[__name__].r2 = ...) at end of __init__.py to survive reload sweep"
    - "Use @pytest.mark.skipif(shutil.which(BIN) is None, reason=...) for container-only host-binary contracts"

key-files:
  created: []
  modified:
    - mcp-gateway/src/mcp_gateway/tools/r2_sessions.py
    - mcp-gateway/src/mcp_gateway/sessions/__init__.py
    - mcp-gateway/tests/test_acl_available.py

key-decisions:
  - "D-01 fix went beyond plan literal (Rule-1 deviation): refetch `sessions = sys.modules['mcp_gateway.sessions']` inside each function body BEFORE the try, because the gdb-env test does `sys.modules.pop('mcp_gateway.sessions') + reimport`, leaving the import-time `from mcp_gateway import sessions` binding pointing at a stale package object. Plain `except sessions.SessionCapReached` against the stale binding still resolved to the OLD class and failed to catch the freshly raised exception. The refetch makes module-attribute lookup match the test's `from mcp_gateway.sessions._base import SessionCapReached` raise site."
  - "D-04 picked Option A (skipif) per CONTEXT.md — host-bare runs do not have the apt `acl` package; container builds do; skip is correct posture."
  - "Plan grep acceptance `grep -c \"pytest.mark.skipif\"` returns exactly 1 required removing the literal substring from the docstring (changed 'via the @pytest.mark.skipif decorator' → 'via the skipif decorator above') so the decorator on line 23 is the sole regex match."

patterns-established:
  - "Phase 14 D-01: `sessions = sys.modules['mcp_gateway.sessions']` rebind-then-except is the canonical reload-safe SessionCapReached catch site idiom"
  - "Phase 14 D-02: package __init__ ends with `_sys.modules[__name__].r2 = _sys.modules['mcp_gateway.sessions.r2']` (and gdb) to preserve submodule-as-package-attribute lookup after reload"
  - "Phase 14 D-04: host-binary skipif is the contract pattern for any container-only test (mirror this for future acl/r2/gdb/setfacl-style probes)"

requirements-completed:
  - HARDEN-01
  - HARDEN-02
  - HARDEN-06
  - HARDEN-07
  - SESS-CAP-01
  - JOBS-CAP-01

duration: 8min 43s
completed: 2026-05-21
---

# Phase 14 Plan 01: Close v1.1 Test-Order Regressions Summary

**Three surgical edits (1 test, 2 production) close D-01/D-02/D-04 audit gaps so `cd mcp-gateway && uv run pytest -m 'not slow'` exits 0 with `0 failed` in a single non-isolated invocation.**

## Performance

- **Duration:** 8 min 43 s
- **Started:** 2026-05-21T03:05:08Z
- **Completed:** 2026-05-21T03:13:51Z
- **Tasks:** 4 (3 source edits + 1 verification-only gate)
- **Files modified:** 3

## Accomplishments

- **D-01 closed:** `tools/r2_sessions.py` now catches `SessionCapReached` via the live `sessions` package module (refetched from `sys.modules` inside each function body) at every site. Removed the stale `from mcp_gateway.sessions import SessionCapReached` value-binding. Reproducer `test_gdb_env_validates_bad_values` → `test_unsafe_shares_combined_cap` passes in a single invocation.
- **D-02 closed:** `sessions/__init__.py` now ends with a `_sys.modules[__name__].r2 = ...` / `.gdb = ...` re-bind block so `mcp_gateway.sessions.r2` and `mcp_gateway.sessions.gdb` remain accessible as package attributes after the reload sweep (and after the gdb-env test's `sys.modules.pop('mcp_gateway.sessions') + reimport` sequence). All 6 `test_sessions_concurrency.py` tests now pass when run after the gdb-env trigger.
- **D-04 closed:** `tests/test_acl_available.py` now has `@pytest.mark.skipif(shutil.which("setfacl") is None, reason="setfacl host-binary missing; container-only contract (Phase 14 D-04)")` plus a module docstring documenting the host/container contract. On host (no setfacl): test SKIPS cleanly; in container (acl package installed): test will PASS.
- **D-03 final gate green:** `cd mcp-gateway && uv run pytest -m 'not slow'` exits 0 with `595 passed, 49 skipped, 13 deselected, 0 failed`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Switch tools/r2_sessions.py to module-attribute SessionCapReached catch (D-01)** — `df16206`
2. **Task 2: Re-bind r2 and gdb as package attributes in sessions/__init__.py (D-02)** — `f7bb307`
3. **Task 3: Mark test_setfacl_on_path container-only via skipif (D-04)** — `8c610cb`

Task 4 was verification-only (no source edits); its evidence is the final pytest summary line below.

## Files Created/Modified

- `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` — D-01: removed `SessionCapReached` symbol-import; both `except` sites rewritten to use `sessions.SessionCapReached` with `sessions = sys.modules["mcp_gateway.sessions"]` refetched per call body; added `import sys`; appended `Phase 14 D-01` comment to the existing module-attribute-access rationale.
- `mcp-gateway/src/mcp_gateway/sessions/__init__.py` — D-02: appended `Phase 14 D-02` block re-binding `r2` and `gdb` as `_sys.modules[__name__]` attributes at end of file (after `__all__`). Existing reload sweep preserved.
- `mcp-gateway/tests/test_acl_available.py` — D-04: rewrote with module docstring + `import pytest` + `@pytest.mark.skipif(shutil.which("setfacl") is None, reason="setfacl host-binary missing; container-only contract (Phase 14 D-04)")` decorator.

## Final Acceptance Gate (D-03)

**Command:** `cd mcp-gateway && uv run pytest -m 'not slow'`

**Final summary line (input fingerprint for Plan 05 rebuilt-container UAT):**

```
===== 595 passed, 49 skipped, 13 deselected, 1 warning in 78.75s (0:01:18) =====
```

Exit code: `0`. Re-confirmed with a second run: `595 passed, 49 skipped, 13 deselected, 2 warnings in 85.03s` (exit 0).

The 49 skips are all expected host-environmental skips (radare2, setfacl, die, rabin2, jq, yq, mare-shell user, container gateway endpoint) — all flip to PASS inside the container per the contract.

## Decisions Made

- **D-01 plan-pattern was insufficient as written; required Rule-1 deviation.** See "Deviations from Plan" below.
- **D-04 grep collision fix.** The plan's literal acceptance criterion `grep -c "pytest.mark.skipif"` returns exactly 1 forced removing the dotted form from the assert-message docstring (regex `.` matched any char). Final docstring says "skips via the skipif decorator above." which preserves the human-readable explanation without colliding with the grep.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan-literal D-01 fix did not actually survive `sys.modules.pop('mcp_gateway.sessions') + reimport`**

- **Found during:** Task 1 (Switch r2_sessions.py to module-attribute SessionCapReached catch)
- **Issue:** The plan said "catch via `sessions.SessionCapReached` so the class is resolved at exception-catch time and survives reload." When implemented literally with the existing `from mcp_gateway import sessions` import, the reproducer `test_gdb_env_validates_bad_values` → `test_unsafe_shares_combined_cap` STILL failed because:
  1. `test_gdb_env_validates_bad_values` does `sys.modules.pop("mcp_gateway.sessions", None) + import mcp_gateway.sessions` in its cleanup. This replaces the package in `sys.modules` with a fresh module object.
  2. The `sessions` local name inside `tools/r2_sessions.py` was bound at IMPORT time to the OLD package object, which is no longer in `sys.modules` but is still referenced by the tools module's namespace.
  3. `sessions.SessionCapReached` therefore resolves to the OLD class (from before reload), while the test stub's `from mcp_gateway.sessions._base import SessionCapReached` returns the NEW class (from reloaded `_base`). Catch-clause `isinstance` check fails. Exception propagates. Test fails.
  4. Verified empirically: `id(t.sessions)` before reload ≠ `id(sys.modules['mcp_gateway.sessions'])` after reload; class identities diverged.
- **Fix:** Added `import sys` and rebound `sessions = sys.modules["mcp_gateway.sessions"]` inside each function body just before the try-block. This refetches the LIVE package module on every call, so `sessions.SessionCapReached` resolves against the post-reload class. Catch succeeds. Plan acceptance grep `grep -c "except sessions\.SessionCapReached"` still returns 2 (both call sites use the literal form).
- **Files modified:** `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` (added `import sys`; added `sessions = sys.modules["mcp_gateway.sessions"]` rebind line in both `open_r2_session` and `open_r2_session_unsafe` before their try-blocks; added two `Phase 14 D-01` rationale comments).
- **Verification:** Reproducer `cd mcp-gateway && uv run pytest tests/test_gdb_session.py::test_gdb_env_validates_bad_values tests/test_r2_sessions.py::test_unsafe_shares_combined_cap -q` returns `2 passed`. Isolated run of `tests/test_r2_sessions.py` still passes (`3 passed, 13 skipped`).
- **Committed in:** `df16206` (Task 1 commit).

**2. [Rule 1 - Bug] Plan acceptance grep for D-04 collided with the literal text in the docstring**

- **Found during:** Task 3 (Mark test_setfacl_on_path container-only via skipif)
- **Issue:** The plan's exact rewrite included the phrase `"skips via the @pytest.mark.skipif decorator."` in the assertion message. Grep acceptance criterion `grep -c "pytest.mark.skipif" mcp-gateway/tests/test_acl_available.py` requires exactly 1 hit, but the docstring substring matched too (grep treats `.` as any-char). Two hits → spurious acceptance failure.
- **Fix:** Edited the assertion-message text to remove the literal `pytest.mark.skipif` substring while preserving the meaning: `"skips via the skipif decorator above."`. The decorator on line 23 is now the sole grep match.
- **Files modified:** `mcp-gateway/tests/test_acl_available.py` (assertion message wording only).
- **Verification:** `grep -c "pytest.mark.skipif" tests/test_acl_available.py` returns `1`. `uv run pytest tests/test_acl_available.py -v` returns `1 skipped` with the locked reason string.
- **Committed in:** `8c610cb` (Task 3 commit — change folded into the same commit so the file lands as one atomic edit).

---

**Total deviations:** 2 auto-fixed (2 × Rule 1 - Bug)
**Impact on plan:** Both deviations were necessary for the acceptance criteria to pass. The fixes are surgical and preserve the plan's intent (module-attribute resolution / container-only contract) while making them actually work against the runtime test pollution. No scope creep.

## Issues Encountered

- None beyond the deviations documented above. No new tests added (deferred per CONTEXT.md "regression tests for importlib.reload class-identity pitfall — defer to v1.2 unless cheap").

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 14 Plans 02 / 03 / 04 (REQUIREMENTS/ROADMAP/STATE/VALIDATION sync) have a clean test baseline to land against.
- Phase 14 Plan 05 (live UAT in rebuilt container) will use the literal summary line `595 passed, 49 skipped, 13 deselected, 0 failed` as the pre-rebuild fingerprint; inside the container, the 49 skips drop substantially (radare2 + setfacl + die + rabin2 + jq + yq + mare-shell user + gateway endpoint all become available) and the count flips to roughly `> 640 passed, < 10 skipped`.

## Self-Check: PASSED

Files verified:

- `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` — FOUND
- `mcp-gateway/src/mcp_gateway/sessions/__init__.py` — FOUND
- `mcp-gateway/tests/test_acl_available.py` — FOUND
- `.planning/phases/14-close-v1.1-gaps/14-01-SUMMARY.md` — FOUND (this file)

Commits verified:

- `df16206` — FOUND (Task 1 — D-01)
- `f7bb307` — FOUND (Task 2 — D-02)
- `8c610cb` — FOUND (Task 3 — D-04)

Acceptance greps re-verified:

- `grep -c "except sessions\\.SessionCapReached" mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` → 2 (≥1 required)
- `grep -c "except SessionCapReached" mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` → 0 (= 0 required)
- `grep -c "Phase 14 D-01" mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` → 3 (≥1 required)
- `grep -c "Phase 14 D-02" mcp-gateway/src/mcp_gateway/sessions/__init__.py` → 1 (≥1 required)
- `grep -c "_sys.modules\\[__name__\\]\\.r2 = _sys.modules" mcp-gateway/src/mcp_gateway/sessions/__init__.py` → 1 (= 1 required)
- `grep -c "_sys.modules\\[__name__\\]\\.gdb = _sys.modules" mcp-gateway/src/mcp_gateway/sessions/__init__.py` → 1 (= 1 required)
- `grep -c "pytest.mark.skipif" mcp-gateway/tests/test_acl_available.py` → 1 (= 1 required)
- `grep -c 'shutil.which("setfacl") is None' mcp-gateway/tests/test_acl_available.py` → 1 (≥1 required)
- `grep -c "container-only contract (Phase 14 D-04)" mcp-gateway/tests/test_acl_available.py` → 1 (= 1 required)

Final gate:

- `cd mcp-gateway && uv run pytest -m 'not slow'` → exit `0`; `595 passed, 49 skipped, 13 deselected, 0 failed`.

---
*Phase: 14-close-v1.1-gaps*
*Completed: 2026-05-21*
