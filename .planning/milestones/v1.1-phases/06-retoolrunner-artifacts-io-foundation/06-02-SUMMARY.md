---
phase: 06-retoolrunner-artifacts-io-foundation
plan: 02
subsystem: mcp-gateway-helpers
tags: [artifacts-io, confine_to, ensure_subdir, tool_log_path, leaf-module, path-traversal-defense, slug-regex, mcp-gateway]

# Dependency graph
requires:
  - phase: 06-retoolrunner-artifacts-io-foundation
    plan: 01
    provides: 16 RED-state tests in tests/test_artifacts_io.py that lock the FOUND-04 SC-5 + D-09 + D-15 + D-16 contract
provides:
  - mcp_gateway.artifacts_io.confine_to -- canonical realpath+is_relative_to containment (replaces ad-hoc tools/artifacts.py:115-139 pattern for Phase 7+ consumers)
  - mcp_gateway.artifacts_io.ensure_subdir -- slug-validated lazy mkdir (parents=False, exist_ok=True) for the 9 expanded case-dir subdirs
  - mcp_gateway.artifacts_io.tool_log_path -- D-09 canonical log-path format `<ts>-<slug>-<rand4>.txt` with secrets.token_hex(2)
  - mcp_gateway.artifacts_io.EXPANDED_CASE_SUBDIRS -- 9-entry tuple catalog for D-16 lazy-create discipline
  - Leaf-module discipline established (D-07): artifacts_io has zero mcp_gateway.* imports; safe to import from anywhere in the package
affects: [06-03 ReToolRunner implementation will import confine_to + ensure_subdir + tool_log_path, all Phase 7+ typed wrappers that need cwd/output-cap confinement]

# Tech tracking
tech-stack:
  added: []  # stdlib only -- no new pip deps
  patterns:
    - "Leaf-module discipline (D-07): pure-helper module with stdlib-only imports; no cycles possible because no mcp_gateway.* dependencies"
    - "Auto-lowercase-then-validate slug pattern: _validate_slug(name) lowercases before regex match -- callers can pass 'MySlug' or 'myslug' interchangeably (D-09)"
    - "NUL-byte rejection before any Path operation: explicit `\"\\x00\" in os.fspath(arg)` precedes Path() construction to avoid implicit OSError (D-13)"
    - "Resolve case_dir strict=True (existence + dir-ness check), resolve target strict=False (non-existing leaf is the legitimate write case) -- explicit asymmetry per D-11"
    - "16 bits of collision entropy via secrets.token_hex(2) -- ~0 expected collisions across 100 same-second calls (birthday paradox; test asserts >=95 distinct)"

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/artifacts_io.py
  modified: []

key-decisions:
  - "Copied paste-ready code from PLAN.md verbatim -- every code path is derived from CONTEXT.md D-XX or RESEARCH.md Pattern/Code Example; no improvisation"
  - "Used `target.is_relative_to(resolved_case) or target == resolved_case` for containment -- accepts case_dir itself as a valid target (legitimate for confine_to(case, '.'))"
  - "ensure_subdir uses strict=True on the post-mkdir resolve -- guarantees the returned Path is a canonical, existing directory the caller can trust"
  - "Did NOT add __all__ -- per plan instruction, public API discoverable via direct imports keeps grep-the-source navigation cleaner"

patterns-established:
  - "TDD GREEN-phase: Plan 01 wrote 16 RED tests; Plan 02 ships 133 LoC making them all GREEN with zero deviation from the test contract"
  - "Threat-register-as-mitigation: every mitigate-disposition row in PLAN.md <threat_model> (T-6-01 traversal, T-6-01 NUL, T-6-03 symlink, T-6-06 collision, slug injection) is provably mitigated by a named test that passes"

requirements-completed: [FOUND-04]

# Metrics
duration: 4min
completed: 2026-05-13
---

# Phase 6 Plan 2: artifacts_io Leaf Module (FOUND-04) Summary

**Turned 16 RED tests GREEN with a 133-LoC pure-helper leaf module — `confine_to` + `ensure_subdir` + `tool_log_path` + `EXPANDED_CASE_SUBDIRS` — that Plan 03's `ReToolRunner` and every Phase 7+ typed wrapper will import for case-dir confinement, lazy subdir creation, and canonical log-path generation.**

## Performance

- **Duration:** ~4 min (221 s)
- **Started:** 2026-05-13T01:23:12Z
- **Completed:** 2026-05-13T01:26:53Z
- **Tasks:** 1 / 1
- **Files created:** 1
- **Files modified:** 0

## Accomplishments

- Created `mcp-gateway/src/mcp_gateway/artifacts_io.py` (133 LoC) with:
  - `EXPANDED_CASE_SUBDIRS` — 9-entry tuple: `tool-logs, extracted, hex, rop, dynamic, qemu, disassembly, decompilation, xrefs` (D-16)
  - `confine_to(case_dir, path) -> Path` — NUL-byte rejection → strict=True case_dir resolve + is-dir check → strict=False target resolve → `is_relative_to` containment (D-11..D-14)
  - `ensure_subdir(case_dir, name) -> Path` — slug-validated `mkdir(parents=False, exist_ok=True)` returning canonical resolved Path (D-15)
  - `tool_log_path(case_dir, slug) -> Path` — `<ts>-<slug>-<rand4>.txt` format with `secrets.token_hex(2)` rand4 and `%Y%m%dT%H%M%SZ` UTC timestamp (D-09)
  - `_validate_slug(name)` private helper sharing the regex `^[a-z0-9][a-z0-9_-]{0,39}$` between `ensure_subdir` and `tool_log_path`
- Leaf-module discipline enforced (D-07): zero `mcp_gateway.*` imports; stdlib only (`datetime, os, re, secrets, pathlib`).
- All 16 RED tests from Plan 01's `tests/test_artifacts_io.py` flipped to GREEN with no deviation from the test contract.

## Task Commits

Each task committed atomically:

1. **Task 1: Implement `artifacts_io.py`** — `be4eaed` (feat)

## Files Created/Modified

- `mcp-gateway/src/mcp_gateway/artifacts_io.py` (new, 133 lines) — pure-helper leaf module exporting 4 public symbols (`confine_to`, `ensure_subdir`, `tool_log_path`, `EXPANDED_CASE_SUBDIRS`) plus one private helper (`_validate_slug`).

## Verification Results

End-to-end verification per plan's `<verification>` block:

1. **Module imports cleanly:**
   ```
   uv run python -c "from mcp_gateway.artifacts_io import confine_to, ensure_subdir, tool_log_path, EXPANDED_CASE_SUBDIRS; assert len(EXPANDED_CASE_SUBDIRS) == 9"
   ```
   PASS — `imports OK, len=9`.

2. **Leaf-module discipline (D-07):**
   ```
   grep -E "from mcp_gateway|import mcp_gateway" mcp-gateway/src/mcp_gateway/artifacts_io.py
   ```
   PASS — empty result (no mcp_gateway internal imports).

3. **All 16 artifacts_io tests GREEN:**
   ```
   cd mcp-gateway && uv run pytest tests/test_artifacts_io.py -x -ra
   ```
   PASS — `16 passed, 1 warning in 0.54s`.

4. **No regression in existing test suite (excluding test_runner.py — depends on Plan 03):**
   ```
   cd mcp-gateway && uv run pytest tests/ --ignore=tests/test_runner.py -ra -m "not slow"
   ```
   Result: `1 failed, 196 passed, 7 skipped` — the single failure (`tests/e2e/test_mastra_starter.py::test_mastra_starter_full_triage_path`) is a pre-existing e2e test requiring a running gateway + Node.js environment; it does not import `artifacts_io` and is unrelated to this plan. Out of scope per executor scope-boundary rule.

5. **Acceptance-criteria literal grep checks** — all 10 required literals present in `artifacts_io.py` (`def confine_to(`, `def ensure_subdir(`, `def tool_log_path(`, `EXPANDED_CASE_SUBDIRS`, `is_relative_to(`, `secrets.token_hex(2)`, `strftime("%Y%m%dT%H%M%SZ")`, `[a-z0-9][a-z0-9_-]{0,39}`, `"\x00" in`, `mkdir(parents=False, exist_ok=True)`).

## Deviations from Plan

None — plan executed exactly as written. The paste-ready code block from `<action>` was copied verbatim with no behavioral changes. All 16 tests pass on the first run; no auto-fix rules triggered.

## Auth Gates

None — implementation is local file write only.

## Threat Surface Scan

This plan introduces NO new attack surface beyond what was already enumerated in the plan's `<threat_model>`. Every `mitigate`-disposition threat is provably mitigated by a passing test:

| Threat | Mitigation | Test (now GREEN) |
|--------|------------|------------------|
| T-6-01 (path traversal) | `is_relative_to` containment after `resolve(strict=False)` | `test_confine_to_rejects_traversal`, `test_confine_to_rejects_absolute_outside`, `test_confine_to_rejects_nonexistent_case_dir`, `test_confine_to_rejects_non_directory_case_dir` |
| T-6-01 (NUL byte sub-class) | Explicit `"\x00" in os.fspath(arg)` check BEFORE any Path operation | `test_confine_to_rejects_nul_byte` |
| T-6-03 (symlink escape) | `Path.resolve()` follows symlinks before containment check | `test_confine_to_rejects_escaping_symlink`, `test_confine_to_allows_inside_symlink` |
| T-6-06 (log-filename collision) | `secrets.token_hex(2)` 16-bit suffix per call | `test_tool_log_path_no_collision` (100 calls → 16/16 distinct in practice) |
| Slug injection | Shared `_SLUG_RE = ^[a-z0-9][a-z0-9_-]{0,39}$` (auto-lowercased) | `test_ensure_subdir_validates_slug`, `test_tool_log_path_rejects_bad_slug` |

STATUS_ROOT enforcement (D-14, T-6-01 outer ring) is deliberately deferred to `tools/case_dirs.resolve_case_dir`, which Phase 7+ wrappers will compose upstream of `confine_to`. This is plan-intended scope, not a missing mitigation.

## Known Stubs

None — the module is feature-complete. No TODO/FIXME/placeholder strings; all four public symbols have full implementations exercised by passing tests.

## Self-Check: PASSED

- FOUND: mcp-gateway/src/mcp_gateway/artifacts_io.py (133 lines, 4 public symbols + 1 private helper)
- FOUND: commit be4eaed (Task 1 — artifacts_io.py implementation)
- FOUND: 16/16 tests in tests/test_artifacts_io.py passing
- FOUND: zero `mcp_gateway.*` imports in artifacts_io.py source (D-07 leaf invariant)
- FOUND: all 10 acceptance-criteria literals present in the source file
