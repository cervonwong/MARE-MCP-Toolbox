---
phase: 12-orchestrator-skill-update
plan: 04
subsystem: skill-content
tags: [skill-content, backend-priority, dual-mode-prose, snapshot-baseline, ida-first, workflow-routing]

requires:
  - phase: 12-orchestrator-skill-update/12-01
    provides: test_skill_md_dual_mode.py harness (Wave 0 RED stubs) + snapshots dir scaffold
  - phase: 12-orchestrator-skill-update/12-02
    provides: 7 W-N workflow files + deep-re-workflows.md index
  - phase: 12-orchestrator-skill-update/12-03
    provides: scripts/update_state.py --probe-dynamic + artifact-spec.md dynamic fields
provides:
  - SKILL.md v1.1 prose: IDA-first backend priority (D-01)
  - SKILL.md ## Backend Priority H2 section
  - SKILL.md ## Workflow Decision Tree routing to W-1..W-7 (D-04)
  - SKILL.md ## Disassembly Backend Guidance (collapsed BN + Ghidra; D-02)
  - SKILL.md ## Operating Modes (D-07/D-09 run_shell sentinel + per-step decision rule)
  - SKILL.md ## Dynamic-Mode Skip Behavior (D-18 placeholder + INDEX.md row pattern)
  - SKILL.md legacy-prefix appendix (mcp__ida_mcp__*, mcp__binary_ninja_headless_mcp__*, mcp__ghidra_headless_mcp__*)
  - workflow.md mode-aware preamble + W-N routing block + v1.1 tool-prefix footnotes in Phase 0/1/2/6
  - deep-analysis-checklist.md Workflow Selection subsection (D-06)
  - mcp-gateway/tests/snapshots/SKILL.md.sha256 baseline (D-13)
affects: [phase-13-and-beyond, verification, milestone-v1.1-completion]

tech-stack:
  added: []
  patterns:
    - "Dual-mode prose discipline: every gateway-tool example pairs with `scripts/` or `run_shell` fallback within ±3 lines (D-12 invariant)"
    - "Backend-native first-call pattern: agents call `get_active_backend()` before backend-specific tool names; legacy `mcp__<backend>__*` prefixes preserved in scripts-mode appendix only"
    - "Closed-list slug constraint for skip placeholders (`strace-all`, `ltrace-libc`, `gdb-open-bt`, `qemu-<arch>-run`) -- T-12-03 path-injection mitigation"

key-files:
  created:
    - mcp-gateway/tests/snapshots/SKILL.md.sha256
  modified:
    - workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md
    - workspace/.claude/skills/malware-analysis-orchestrator/references/workflow.md
    - workspace/.claude/skills/malware-analysis-orchestrator/references/deep-analysis-checklist.md

key-decisions:
  - "Placeholder token in code blocks switched from `run_X` to `<tool_name>` to avoid regex collision with `mcp__mare-toolbox__<token>` tool-registry validator (Rule 1 fix)"
  - "Backend Priority section split into 3 short paragraphs to land both gateway-mode reference and scripts-mode fallback within the dual-mode ±3-line window (Rule 3 fix)"
  - "First-call code block annotated with gateway-mode and scripts-mode-fallback comments to land fallback within ±3 lines of the gateway tool token inside the code block (Rule 3 fix)"
  - "Renamed `## Dual-Mode Operation` to `## Operating Modes` to match plan's REQUIRED_H2 regex (`Operating Modes?`) used by test_skill_md_has_required_h2_sections (Rule 1 fix)"

patterns-established:
  - "Skill prose with code blocks: when a `mcp__mare-toolbox__*` token appears inside a fenced code block, add a comment line referencing `fallback` or `scripts/` within ±3 lines so the dual-mode invariant test inspects pair-presence not pair-distance-on-prose-only"
  - "H2 heading wording is load-bearing: REQUIRED_H2 regex test enforces `Backend Priorit`, `Operating Modes?`, `Workflow Decision Tree`, `Dynamic.*Mode` substrings; rename only with regex check first"

requirements-completed: [SKILL-01, SKILL-03]

duration: 17min
completed: 2026-05-20
---

# Phase 12 Plan 04: Orchestrator Skill Update Summary

**SKILL.md rewritten end-to-end for v1.1: IDA-first backend priority, unified Disassembly Backend Guidance (BN+Ghidra collapsed), Operating Modes + Dynamic-Mode Skip Behavior H2 sections, Workflow Decision Tree routing to W-1..W-7, plus matching sweeps to workflow.md and deep-analysis-checklist.md and the sha256 snapshot baseline.**

## Performance

- **Duration:** ~17 min
- **Started:** 2026-05-20T13:08:00Z
- **Completed:** 2026-05-20T13:30:00Z
- **Tasks:** 3
- **Files modified:** 3
- **Files created:** 1 (snapshot baseline)

## Accomplishments

- SKILL.md backend priority flipped from BN-first to IDA-first; legacy `Binary Ninja MCP server -- primary tool` phrasing removed
- SKILL.md gains 3 new H2 sections: `## Backend Priority`, `## Operating Modes`, `## Dynamic-Mode Skip Behavior`
- SKILL.md Workflow Decision Tree now routes by `detected_format` + signals into W-1..W-7 (W-2 + W-5 paired for ELF dynamic gate)
- BN + Ghidra Guidance sections collapsed into unified `## Disassembly Backend Guidance` per D-02, with first-call code block and scripts-mode legacy-prefix appendix
- workflow.md gains mode-aware preamble + W-N routing blockquote + v1.1 tool-prefix footnotes on Phase 0/1/2 + Phase 6 W-N branching pointer
- deep-analysis-checklist.md gains `## Workflow Selection` subsection (D-06) pointing at deep-re-workflows.md
- `mcp-gateway/tests/snapshots/SKILL.md.sha256` baseline created (`5b88955c64e09db189a22a3c1c2e97298468f7fce81c7ef484d9cf5d85f233ab`, 65 bytes)
- 4 originally-RED tests turned GREEN: `test_backend_priority_correct`, `test_no_legacy_bn_first_priority`, `test_skill_md_has_required_h2_sections`, `test_decision_tree_routes_to_all_wn`
- Final `test_skill_md_dual_mode.py` result: 51 passed / 1 RED (out-of-scope `test_scripts_references_resolve`)

## Task Commits

1. **Task 1: Rewrite SKILL.md (Edits 1-6 + Operating Modes H2 + Dynamic-Mode Skip Behavior H2)** - `4c4d34b`
2. **Task 2: Sweep workflow.md + deep-analysis-checklist.md** - `23868e4`
3. **Task 3: Generate SKILL.md sha256 baseline** - `eaf2ef2`

## Files Created/Modified

- `workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md` (276 → 343 lines, +67 net): frontmatter `description` updated to mention IDA Pro MCP + mare-toolbox gateway; new `## Backend Priority` section; rewritten Workflow Decision Tree; rewritten `### Disassembly and Decompilation`; updated Fallback Order step 4; BN+Ghidra Guidance collapsed into `## Disassembly Backend Guidance` (with code block first-call pattern + legacy-prefix appendix); new `## Operating Modes` section; new `## Dynamic-Mode Skip Behavior` section
- `workspace/.claude/skills/malware-analysis-orchestrator/references/workflow.md` (97 → 124 lines, +27): added mode-aware preamble blockquote with W-1..W-7 routing; added v1.1 tool-prefix footnote to Phase 0 (`run_file`, `run_die`, `run_rabin2`, `open_r2_session`, `scan_yara.sh`, `scan_capa.sh`); added v1.1 footnote to Phase 1 (`collect_strings.sh` + `run_shell` chain); added v1.1 footnote to Phase 2 (`run_rabin2`, `run_readelf`, `run_nm`, `run_objdump`); added W-N branching pointer to Phase 6
- `workspace/.claude/skills/malware-analysis-orchestrator/references/deep-analysis-checklist.md` (73 → 82 lines, +9): new `## Workflow Selection` subsection after H1, before `## Component Prioritization`; 4-step framing (Read catalog / Route by format+signals / Apply across W-N / Honor mode + dynamic-mode gates)
- `mcp-gateway/tests/snapshots/SKILL.md.sha256` (created): `5b88955c64e09db189a22a3c1c2e97298468f7fce81c7ef484d9cf5d85f233ab\n` (65 bytes)

## Decisions Made

1. **Code-block fallback comments**: Adding `# Gateway mode:` and `# Scripts-mode fallback: ...` annotation lines inside the first-call code block lands the fallback within ±3 lines of the gateway token, satisfying the dual_mode_invariant regression test without breaking the pedagogical first-call recipe.
2. **`## Operating Modes` H2 name**: The plan body referred to the section as "Dual-Mode Operation" but the test's REQUIRED_H2 regex is `Operating Modes?`. Renamed to `## Operating Modes` to land the assertion (Rule 1). The deep-analysis-checklist.md cross-reference was updated to match.
3. **Placeholder token in pseudo-code**: `mcp__mare-toolbox__run_X(case_dir, ...)` matches the tool-registry regex as token `run_` (uppercase X stops the `\w+` greedy match in `mcp__mare[-_]toolbox__([a-z0-9_]+)`). Replaced with `<tool_name>` so the pseudo-code is clearly a placeholder and the regex sees no candidate.
4. **`## Backend Priority` H2 split**: Single dense paragraph triggered the dual_mode_invariant ±3-line window failure. Split into 3 short paragraphs so the gateway-mode `get_active_backend()` mention and scripts-mode-fallback paragraph are within the regex window.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] H2 heading "Dual-Mode Operation" did not match REQUIRED_H2 regex**

- **Found during:** Task 1, after running `test_skill_md_has_required_h2_sections`
- **Issue:** Plan body said `## Dual-Mode Operation`, but the test's regex is `^##\s+.*Operating Modes?` -- "Dual-Mode Operation" does not contain "Operating Modes" as a substring
- **Fix:** Renamed the H2 to `## Operating Modes`; updated cross-reference in `deep-analysis-checklist.md` Workflow Selection subsection to match
- **Files modified:** SKILL.md, deep-analysis-checklist.md
- **Verification:** `test_skill_md_has_required_h2_sections` PASSED
- **Committed in:** 4c4d34b (Task 1), 23868e4 (Task 2 cross-ref update)

**2. [Rule 1 - Bug] Pseudo-code placeholder `run_X` parsed by tool-registry regex as `run_`**

- **Found during:** Task 1, after running `test_tool_tokens_exist_in_gateway_registry`
- **Issue:** `mcp__mare-toolbox__run_X(case_dir, sample, ...)` placeholder in the Operating Modes pseudo-code matched the registry-validator regex `mcp__mare[-_]toolbox__([a-z0-9_]+)` as token `run_` (uppercase X stops the lowercase-only group), and `run_` is not a real tool name
- **Fix:** Replaced `run_X` with `<tool_name>` (angle brackets clearly mark a placeholder and break out of the `\w` regex chain)
- **Files modified:** SKILL.md
- **Verification:** `test_tool_tokens_exist_in_gateway_registry` PASSED
- **Committed in:** 4c4d34b (Task 1)

**3. [Rule 3 - Blocking] `## Backend Priority` and first-call code block tripped dual_mode_invariant ±3-line window**

- **Found during:** Task 1, after running `test_dual_mode_invariant[SKILL.md]`
- **Issue:** (a) The single-paragraph `## Backend Priority` block put `mcp__mare-toolbox__get_active_backend()` 5+ lines away from any `scripts/`/`fallback` word. (b) The first-call pseudo-code block put `mcp__mare-toolbox__get_active_backend()` inside a fenced block with no fallback annotation
- **Fix:** (a) Split `## Backend Priority` into 3 short paragraphs; the third paragraph leads with "Scripts-mode fallback:" within ±3 lines of the gateway token. (b) Added `# Gateway mode:` and `# Scripts-mode fallback: read .mcp.json ...` comment lines inside the code block immediately above/below the gateway token
- **Files modified:** SKILL.md
- **Verification:** `test_dual_mode_invariant[SKILL.md]` PASSED
- **Committed in:** 4c4d34b (Task 1)

---

**Total deviations:** 3 auto-fixed (2 Rule-1 bugs, 1 Rule-3 blocking)
**Impact on plan:** All fixes were test-driven mechanical corrections to land the SKILL-01/03/04 invariants without altering the substantive plan content. No scope creep; the prose still teaches exactly what the plan body specified.

## Out-of-scope Findings (Deferred)

- `test_scripts_references_resolve` remains RED because `W-7-cross-arch-iot.md` references `scripts/probe_dynamic_tools.sh` which is in `mcp-gateway/scripts/` (Phase 11 artifact) but not in the skill's `scripts/` directory. Per prompt instructions, this is out-of-scope for 12-04 and the plan owner will address separately (likely by adding a thin skill-side wrapper or updating the W-7 reference to the correct path).

## Issues Encountered

None beyond the auto-fixed deviations above. The plan body was substantively correct; the deviations were test-regex precision adjustments and a heading-rename for invariant compliance.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All Phase 12 SKILL-01..SKILL-04 requirements satisfied (modulo the deferred `probe_dynamic_tools.sh` script-resolve issue tracked above)
- 12 in-scope tests in `test_skill_md_dual_mode.py` are GREEN
- SKILL.md sha256 baseline locked; future edits will surface as soft UserWarning until baseline refresh
- Phase 12 is the final code+content phase of v1.1 milestone Remote RE Tool Expansion

## Self-Check: PASSED

Verified:
- `workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md` exists (343 lines)
- `workspace/.claude/skills/malware-analysis-orchestrator/references/workflow.md` exists (124 lines)
- `workspace/.claude/skills/malware-analysis-orchestrator/references/deep-analysis-checklist.md` exists (82 lines)
- `mcp-gateway/tests/snapshots/SKILL.md.sha256` exists (65 bytes, matches live SKILL.md sha256)
- Commits 4c4d34b, 23868e4, eaf2ef2 all present in `git log`
- 4 originally-RED tests are GREEN: test_backend_priority_correct, test_no_legacy_bn_first_priority, test_skill_md_has_required_h2_sections, test_decision_tree_routes_to_all_wn

---
*Phase: 12-orchestrator-skill-update*
*Completed: 2026-05-20*
