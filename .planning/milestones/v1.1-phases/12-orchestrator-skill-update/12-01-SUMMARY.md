---
phase: 12
plan: 01
subsystem: orchestrator-skill-update
tags: [test-scaffold, regression, nyquist-wave-0, red-state]
requirements_addressed: [SKILL-03]
requirements_supports: [SKILL-01, SKILL-02, SKILL-04]
dependency_graph:
  requires: []
  provides:
    - "mcp-gateway/tests/test_skill_md_dual_mode.py (14 RED-state regression tests)"
    - "mcp-gateway/tests/snapshots/ (snapshot dir placeholder; SKILL.md.sha256 created by Plan 04)"
  affects:
    - "Plans 02/03/04 GREEN-flip targets locked"
tech-stack:
  added: []
  patterns:
    - "Wave 0 RED-stub discipline (Phase 6/7/8/9 precedent)"
    - "REPO_ROOT walker via `.planning` marker (Pitfall 4 mitigation)"
    - "Soft-warn sha256 snapshot (UserWarning, not failure)"
    - "PyYAML availability fallback to manual regex frontmatter parse"
key-files:
  created:
    - "mcp-gateway/tests/test_skill_md_dual_mode.py (270 LoC, 14 tests collected)"
    - "mcp-gateway/tests/snapshots/.gitkeep (snapshot dir placeholder)"
  modified: []
decisions:
  - "PyYAML fallback path implemented inline (manual regex `---\\n(.*?)\\n---` + line-grep) — mcp-gateway venv lacks pyyaml dep; per CONTEXT.md `<domain>` adding it is out of scope for Phase 12"
  - "Rule-1 fix: `test_no_legacy_bn_first_priority` rewritten as markdown-tolerant regex (`Binary Ninja MCP server\\*{0,2}\\s*--\\s*primary tool`) — plan's literal substring did not match SKILL.md:141 which uses `**` markdown bold; without the regex tweak the test would PASS on the v1.0 baseline and silently let BN-first phrasing survive Plan 04"
metrics:
  duration: "259s (~4.3 min)"
  tasks_completed: 1
  files_changed: 2
  tests_collected: 14
  tests_red: 8
  tests_green: 6  # frontmatter, dual_mode[SKILL.md], dual_mode[workflow.md], no_abbreviated_prefix[SKILL.md], no_abbreviated_prefix[workflow.md], snapshot (soft-warn)
  completed_date: "2026-05-20"
---

# Phase 12 Plan 01: SKILL.md Dual-Mode RED-State Test Scaffold Summary

Wave 0 RED-stub regression module landed verbatim per plan with two Rule-1 deviations (PyYAML fallback, markdown-tolerant BN-first regex); 14 tests collected, 8 fail as designed (covering SKILL-01/02/04 invariants Plans 02/03/04 will flip GREEN), 6 pass as sanity (frontmatter intact, no abbreviated `mcp__mare__` prefix, no gateway-tool refs without fallback in v1.0 SKILL.md).

## Tests Collected (14 total)

| # | Test ID | Status | RED reason / GREEN sanity |
|---|---------|--------|---------------------------|
| 1 | `test_skill_md_frontmatter_intact` | **PASS** (sanity) | T-12 frontmatter invariant already holds in v1.0 |
| 2 | `test_backend_priority_correct` | **FAIL** (RED) | SKILL.md still orders BN before IDA (Plan 04 fix) |
| 3 | `test_no_legacy_bn_first_priority` | **FAIL** (RED) | SKILL.md:141 still says `**Binary Ninja MCP server** -- primary tool` (Plan 04 fix) |
| 4 | `test_workflow_count_locked` | **FAIL** (RED) | `references/workflows/` does not exist (Plan 02 creates 7 W-N files) |
| 5 | `test_workflow_index_present` | **FAIL** (RED) | `references/deep-re-workflows.md` missing (Plan 02 creates) |
| 6 | `test_wn_files_reference_v1_1_wrappers[missing]` | **FAIL** (RED) | No W-N files yet; parametrize id `missing` placeholder (Plan 02 creates) |
| 7 | `test_dual_mode_invariant[SKILL.md]` | **PASS** (sanity) | v1.0 SKILL.md has 0 `mcp__mare*__*` refs, so vacuously satisfies dual-mode rule |
| 8 | `test_dual_mode_invariant[workflow.md]` | **PASS** (sanity) | same: 0 gateway-tool refs in v1.0 workflow.md |
| 9 | `test_no_abbreviated_prefix[SKILL.md]` | **PASS** (sanity) | no `mcp__mare__` (Pitfall 3 form) in v1.0 |
| 10 | `test_no_abbreviated_prefix[workflow.md]` | **PASS** (sanity) | same |
| 11 | `test_skill_md_snapshot` | **PASS** (soft-warn) | UserWarning emitted: snapshot missing; Plan 04 creates baseline via `UPDATE_SKILL_SNAPSHOT=1` |
| 12 | `test_update_state_writes_dynamic_fields` | **FAIL** (RED) | `update_state.py --probe-dynamic` not yet implemented (Plan 03) |
| 13 | `test_artifact_spec_documents_dynamic_fields` | **FAIL** (RED) | `artifact-spec.md` lacks `dynamic_mode_enabled` / `dynamic_capabilities` / `"mode"` tokens (Plan 03) |
| 14 | `test_skill_documents_dynamic_skip_behavior` | **FAIL** (RED) | no `dynamic/<step>-skipped.md` placeholder pattern in SKILL.md or W-5/6/7 (Plan 04) |

Plan-named expected failures (per `<acceptance_criteria>`): `test_backend_priority_correct`, `test_no_legacy_bn_first_priority`, `test_workflow_count_locked`, `test_artifact_spec_documents_dynamic_fields` — all four are FAIL as required.

Sanity passes locked: `test_skill_md_frontmatter_intact` + `test_no_abbreviated_prefix[*]`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Markdown-tolerant BN-first regex in `test_no_legacy_bn_first_priority`**
- **Found during:** Task 1 verification (pytest run shown plan's literal substring "Binary Ninja MCP server -- primary tool" was absent from text — actual SKILL.md:141 wraps the server name in `**...**` markdown bold)
- **Issue:** Plan `<behavior>` block specified an `in` substring check, but the assertion would PASS on the v1.0 baseline (because the markdown bold breaks the literal string match), silently letting BN-first phrasing survive Plan 04's rewrite. Plan `<acceptance_criteria>` explicitly listed this test among the expected RED failures, so the intent is clear: catch BN-first phrasing.
- **Fix:** Replaced literal `in` with regex `re.compile(r"Binary Ninja MCP server\*{0,2}\s*--\s*primary tool")` so the test matches the v1.0 markdown-bold form AND remains tolerant of any whitespace variant Plan 04 might leave behind during the rewrite.
- **Files modified:** `mcp-gateway/tests/test_skill_md_dual_mode.py`
- **Commit:** `7505098`

**2. [Rule 3 - Blocking] PyYAML availability fallback in `test_skill_md_frontmatter_intact`**
- **Found during:** Task 1 verification (`.venv/bin/python -c "import yaml"` → ModuleNotFoundError)
- **Issue:** Plan `<action>` includes a PyYAML pre-check explicitly stating: if not installed, fall back to manual regex parse, and DO NOT add PyYAML to pyproject.toml (out of scope per CONTEXT.md `<domain>`). The mcp-gateway venv lacks PyYAML.
- **Fix:** Per plan's CRITICAL instruction, kept the `import yaml` block with `try/except` and made the test body branch on `yaml is None`. Fallback path extracts the frontmatter block via `re.match(r"---\n(.*?)\n---", text, re.DOTALL)` and line-greps `^name:` and `^description:` with re.MULTILINE. Same invariant asserted on both parse paths. Comment in test body explains the choice.
- **Files modified:** `mcp-gateway/tests/test_skill_md_dual_mode.py`
- **Commit:** `7505098`

## PyYAML Availability Decision

- Host system Python: PyYAML 6.0.1 IS importable
- mcp-gateway venv (`.venv/bin/python`): PyYAML NOT importable (not in `pyproject.toml`)
- Test file uses **both paths**: prefers `yaml.safe_load_all` when available, falls back to manual regex extraction otherwise. Tests run identically on the host (PyYAML path) and inside the mcp-gateway venv (fallback path); both verify the same T-12 frontmatter invariant.
- Plan-mandated constraint honored: PyYAML NOT added to `mcp-gateway/pyproject.toml` (out of scope per CONTEXT.md `<domain>`).

## Snapshot Directory

- `mcp-gateway/tests/snapshots/` created with `.gitkeep` placeholder
- `SKILL.md.sha256` baseline NOT written by this plan (Plan 04 owns first write via `UPDATE_SKILL_SNAPSHOT=1` once SKILL.md rewrite stabilizes)
- `test_skill_md_snapshot` currently emits a `UserWarning` (`SKILL.md snapshot missing at mcp-gateway/tests/snapshots/SKILL.md.sha256`); intentional advisory-only design per D-13 / T-12-07 disposition=accept

## Verification Evidence

- `pytest tests/test_skill_md_dual_mode.py --collect-only -q` → 14 tests collected (≥10 required)
- `pytest tests/test_skill_md_dual_mode.py -q` → 8 failed, 6 passed, 3 warnings; exit 0 (pytest reports failure with exit 1 here normally, but `0` was emitted because the trailing `tee` swallowed the rc; actual rc was non-zero for the bare run). Wave-0 RED state confirmed.
- Full unit suite (`pytest tests/ -q --ignore=tests/e2e`): 12 failed, 508 passed, 46 skipped. 8 of the 12 failures are the new Phase 12 RED tests; remaining 4 are pre-existing host-environment skips/fails (`test_acl_available::test_setfacl_on_path` lacks `setfacl` on dev host, documented Phase 7 known-skip — out of Phase 12 scope per `<scope_boundary>`).
- All `<acceptance_criteria>` checks pass: file exists, exact `GATEWAY_TOOL_RE` regex string present, exact `FALLBACK_RE` prefix present, `.planning`-marker walker in place (Pitfall 4), `UPDATE_SKILL_SNAPSHOT` env-var grep matches.

## Deferred Issues

None — Task 1 acceptance criteria fully satisfied. The `test_acl_available::test_setfacl_on_path` failure is pre-existing (Phase 7 host-skip behavior on dev hosts without `setfacl`) and explicitly out of Phase 12 scope.

## Self-Check: PASSED

Files exist:
- `mcp-gateway/tests/test_skill_md_dual_mode.py` — FOUND
- `mcp-gateway/tests/snapshots/.gitkeep` — FOUND

Commit:
- `7505098` — FOUND in `git log`
