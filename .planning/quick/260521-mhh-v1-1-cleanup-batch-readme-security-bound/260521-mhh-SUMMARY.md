---
quick_task: 260521-mhh
title: "v1.1 cleanup batch — security-boundary README, r2_sessions test-infra refactor, REQUIREMENTS traceability sweep, skill-md container-skip"
type: execute
wave: 1
duration_seconds: 338
completed: 2026-05-21
tasks_completed: 4
files_modified:
  - README.md
  - mcp-gateway/src/mcp_gateway/tools/r2_sessions.py
  - mcp-gateway/tests/test_r2_sessions.py
  - mcp-gateway/tests/test_skill_md_dual_mode.py
  - .planning/milestones/v1.1-REQUIREMENTS.md
  - .planning/milestones/v1.1-phases/14-close-v1.1-gaps/deferred-items.md
commits:
  - 6eee149 — Skip test_skill_md_dual_mode at module level when no parent contains .planning
  - 904bc9e — Replace README Security notes with detailed Security boundaries section
  - b080adf — Refactor r2_sessions resolve_case_dir to module-attribute access so test monkeypatch propagates
  - be147c5 — Fill 47 Pending traceability rows in v1.1-REQUIREMENTS.md from phase VERIFICATION.md evidence
---

# Quick Task 260521-mhh: v1.1 Cleanup Batch Summary

**One-liner:** Closed four v1.1 polish backlog items in four atomic commits — added module-level container-skip to test_skill_md_dual_mode, rewrote README Security notes as a structured Security boundaries section, refactored r2_sessions.py to module-attribute access for resolve_case_dir (so the conftest opened_sid monkeypatch propagates), and swept 47 v1.1 traceability rows from `TBD | Pending` to verified plan IDs by reading each phase's VERIFICATION.md.

## Objectives Met

1. **Task 1 (Issue #5):** `tests/test_skill_md_dual_mode.py` no longer trips `StopIteration` at pytest collection time inside the container. Module-level `pytest.skip(..., allow_module_level=True)` guard fires when no parent of `__file__` contains `.planning`.
2. **Task 2 (Issue #2):** `README.md`'s former `## Security notes` (9 lines) replaced with `## Security boundaries` (~70 lines) organised into 7 H3 sub-sections: Network & Auth boundary, Shell & subprocess boundary, r2 sandbox boundary, gdb MI3 boundary (dynamic mode only), Audit & capture boundary, Container capabilities (informational), Disassembler licensing. Explicitly documents `unshare --net --ipc --uts` per-call netns, cwd+UID+no-isolation posture of `run_shell`, r2 `cfg.sandbox=true` latch, bearer + Origin validation, and dynamic-mode opt-in.
3. **Task 3 (Issue #3):** `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` switched from `from mcp_gateway.tools.case_dirs import resolve_case_dir` (binding-by-name) to `from mcp_gateway.tools import case_dirs as _case_dirs` + `_case_dirs.resolve_case_dir(...)` at 2 call sites. The conftest `opened_sid` monkeypatch on `_case_dirs_mod.resolve_case_dir` now propagates to r2_sessions. Three sibling tests (`test_unsafe_passes_sandbox_false`, `test_unsafe_open_warn_log`, `test_unsafe_shares_combined_cap`) updated to patch `r2_sessions._case_dirs.resolve_case_dir`. Host pytest pass: 3 passed, 13 skipped (r2 unavailable on host as expected).
4. **Task 4 (Issue #4):** `.planning/milestones/v1.1-REQUIREMENTS.md` traceability table now has zero `TBD | Pending` rows. All 47 affected rows (FOUND-01..04, SHELL-01/02, STATIC-01..10, ARTIF-05, SESS-01..06, JOBS-01..07, EXTR-01..06, DYN-01..07, SKILL-01..04) now show real plan IDs sourced from each phase's `*-VERIFICATION.md`. Coverage line still reads 61/61.

## Dependency Graph

- **requires:** Phase 5-12 VERIFICATION.md files (each phase verified; sourced plan IDs for traceability sweep)
- **provides:**
  - Explicit security boundary documentation in README (closes STATE.md:196 concern)
  - Module-attribute access pattern in r2_sessions.py (template for future case_dirs consumer refactors)
  - Module-level container-skip guard pattern in test_skill_md_dual_mode.py (template for host-only tests)
  - Complete v1.1 traceability matrix (61/61 verified rows)
- **affects:** None — all four changes are docs/test-infra/import-shape; zero behaviour change in production paths

## Key Files Modified

- `README.md` — `## Security notes` (9 lines) → `## Security boundaries` (~70 lines, 7 H3 sub-sections)
- `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` — import line 47 + 2 call sites at 167 and 453 switched to `_case_dirs.resolve_case_dir(...)` module-attribute form
- `mcp-gateway/tests/test_r2_sessions.py` — 3 monkeypatch sites (lines 395, 437, 474) updated to patch `r2_sessions._case_dirs.resolve_case_dir`
- `mcp-gateway/tests/test_skill_md_dual_mode.py` — line 28 `next(...)` REPO_ROOT walk replaced with list-comprehension + module-level `pytest.skip(allow_module_level=True)` guard
- `.planning/milestones/v1.1-REQUIREMENTS.md` — 47 rows flipped from `TBD | Pending` to plan IDs + `[x]`
- `.planning/milestones/v1.1-phases/14-close-v1.1-gaps/deferred-items.md` — 3 entries flipped to `Status: RESOLVED 2026-05-21 in quick task 260521-mhh ...` (Issues #3, #4, #5 of original audit); 1 new sibling entry added under "From Plan 14-04" for the 7 untouched case_dirs consumers (artifacts.py, workflows.py, shell.py, re_artifacts.py, re_static.py, jobs.py, extract.py)

## Key Decisions

- **r2_sessions refactor scope confined to single module (per plan constraint b).** 7 other tools (artifacts.py, workflows.py, shell.py, re_artifacts.py, re_static.py, jobs.py, extract.py) share the same binding-by-name shape but are not exercised by tests that hit the same monkeypatch chain. Pre-emptive refactor without a failing test driving it is out of scope; logged as new deferred-items entry "Untouched case_dirs consumers (7 tools still bind resolve_case_dir by name)".
- **README Security section position preserved.** Kept between `## Project layout` and `## License & licensing constraints` per plan. Did not touch any other README section.
- **Container-skip strategy: self-detection via parent walk** (plan-recommended option b) rather than hardcoded `/host/.planning` path (option a). The parent-walk is the correct host/container detector and doesn't depend on a path that may not exist in CI.
- **Traceability sweep sourced from VERIFICATION.md files, not memory.** Each REQ-ID family mapped to its phase's `*-VERIFICATION.md`; plan IDs extracted from the verification doc's per-requirement rows. When multiple plans contributed (precedent: ARTIF-01 = 07-01, 07-05), all listed comma-separated.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added third test monkeypatch site in test_r2_sessions.py**
- **Found during:** Task 3 verification (`pytest tests/test_r2_sessions.py`)
- **Issue:** Plan flagged 2 monkeypatch sites at lines 395 and 437, but a third existed at line 474 (`test_unsafe_shares_combined_cap`) that also patched `r2_sessions.resolve_case_dir` directly. After the refactor removed that attribute, the first host run failed with `AttributeError: ... has no attribute 'resolve_case_dir'`.
- **Fix:** Updated line 474 to `monkeypatch.setattr(r2_sessions._case_dirs, "resolve_case_dir", lambda x: str(tmp_path))` matching the other two sites.
- **Files modified:** `mcp-gateway/tests/test_r2_sessions.py:474`
- **Commit:** `b080adf` (rolled into Task 3 commit before pushing)
- **Documented in:** deferred-items.md entry now lists all 3 tests by name (`test_unsafe_passes_sandbox_false`, `test_unsafe_open_warn_log`, `test_unsafe_shares_combined_cap`)

No other deviations. All four tasks executed exactly per plan.

## Verification

### Host-side (executed)

| Check | Command | Expected | Actual |
|-------|---------|----------|--------|
| Task 1 AST + guard | `python3 -c "import ast; ast.parse(open(...).read())" && grep allow_module_level=True` | OK | OK |
| Task 1 deferred-items | `grep "RESOLVED 2026-05-21 in quick task 260521-mhh"` | match | match |
| Task 2 H2 + H3 + content | `grep "^## Security boundaries"` + 4 H3 grep + 3 content greps | all match | all match |
| Task 2 old H2 absent | `! grep "^## Security notes"` | absent | absent |
| Task 3 import shape | `grep "from mcp_gateway.tools import case_dirs as _case_dirs"` | match | match |
| Task 3 old import absent | `! grep "^from mcp_gateway.tools.case_dirs import resolve_case_dir"` | absent | absent |
| Task 3 call sites | `grep -c "_case_dirs.resolve_case_dir(case_dir)"` | 2 | 2 |
| Task 3 module import | `python -c "from mcp_gateway.tools import r2_sessions; assert hasattr(...)"` | pass | pass |
| Task 3 host tests | `pytest tests/test_r2_sessions.py` | 3 passed, 13 skipped, 0 failed | 3 passed, 13 skipped, 0 failed |
| Task 4 Pending rows | `grep -cE '\| TBD +\| Pending +\|'` | 0 | 0 |
| Task 4 row count | `grep -cE '^\| (FOUND\|SHELL\|...)'` | >=61 | 61 |
| Deferred resolved | `grep -c "RESOLVED 2026-05-21 in quick task 260521-mhh"` | >=3 | 3 |

### In-container (deferred to next container rebuild)

- `cd /opt/mcp-gateway && pytest tests/test_r2_sessions.py -m "not slow" -x` — expect the 12 previously-erroring tests to flip GREEN (or skip on `_require_r2_or_skip` if r2 missing, but the case_dir validator should no longer fire).
- `cd /opt/mcp-gateway && pytest tests/test_skill_md_dual_mode.py` — expect "skipped (no parent dir contains .planning)" at module level instead of `StopIteration` collection error.

## Authentication Gates

None encountered. All work was docs / test-infra / import-pattern.

## Deferred Issues

None within scope. One new sibling deferred-items entry added (`Untouched case_dirs consumers`) for the 7 other tools that share the same binding-by-name shape — pre-emptive refactor without a failing test driving it is out of scope for v1.1 cleanup.

## Self-Check: PASSED

Verified items exist on disk:
- `[ -f .planning/quick/260521-mhh-v1-1-cleanup-batch-readme-security-bound/260521-mhh-SUMMARY.md ]` — this file
- Commit `6eee149` exists in `git log` — Task 1
- Commit `904bc9e` exists in `git log` — Task 2
- Commit `b080adf` exists in `git log` — Task 3
- Commit `be147c5` exists in `git log` — Task 4
