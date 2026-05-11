---
phase: 04-external-client-integration
plan: 06
subsystem: documentation
tags: [readme, onboarding, d-16, two-mode, claude-code, mastra]

# Dependency graph
requires:
  - phase: 04-external-client-integration
    provides: Plans 01-04 shipped templates/ and run_docker.sh flags
provides:
  - Single-source onboarding README covering local + remote modes (D-16)
  - Grep-based structural test enforcing README invariants
affects: [onboarding, documentation, cli-03]

# Tech tracking
tech-stack:
  added: []
  patterns: [grep-style structural test for documentation]

key-files:
  created:
    - mcp-gateway/tests/test_readme_structure.py
  modified:
    - README.md

key-decisions:
  - "Full rewrite of README (not patch) to establish two-mode framing as the v2 headline"
  - "Grep-style pytest enforces section structure — catches env-var drift or missing template references"

patterns-established:
  - "Structural doc tests: parametrize banned-tech list in pytest, same pattern as test_claude_code_template.py"

requirements-completed: [CLI-03]

# Metrics
duration: 2min
completed: 2026-04-27
---

# Phase 4 Plan 06: Top-level README Rewrite (D-16) Summary

**Two-mode README with D-16 framing: local agent mode vs remote MCP gateway mode, with grep-based structural test enforcing invariants**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-27T08:37:37Z
- **Completed:** 2026-04-27T08:39:55Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Rewrote top-level README.md per D-16 with two-mode comparison table, quick-start sections for both local and remote modes, Claude Code and mastra.ai client onboarding, MCP resource browsing docs, troubleshooting table, project layout, and security notes
- Created 11-test grep-style structural unit test enforcing headings, artifact references, locked env-var convention, and absence of banned tech

## Task Commits

Each task was committed atomically:

1. **Task 1: Write the new top-level README.md (D-16 two-mode framing)** - `4772261` (feat)
2. **Task 2: Add grep-style unit test asserting README structure** - `5896e27` (test)

## Files Created/Modified
- `README.md` - Full rewrite with two-mode framing, all Phase 4 artifact references, troubleshooting, security notes
- `mcp-gateway/tests/test_readme_structure.py` - 11 grep-style structural assertions (9 tests + 2 parametrized banned-tech checks)

## Decisions Made
- Full rewrite of README rather than patching the existing one — the v2 two-mode framing is a fundamentally different top-level narrative
- Grep-style test pattern matches the established approach in `test_claude_code_template.py` for consistency

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- README complete with all Phase 4 deliverables referenced
- Structural test guards against future drift
- Ready for Plan 07 (if any) or phase completion

---
*Phase: 04-external-client-integration*
*Completed: 2026-04-27*

## Self-Check: PASSED
