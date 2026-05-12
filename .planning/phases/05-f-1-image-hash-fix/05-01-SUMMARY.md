---
phase: 05-f-1-image-hash-fix
plan: 01
subsystem: infra
tags: [bash, docker, sort, locale, image-hash]

requires: []
provides:
  - "Locale-stable sort in run_docker.sh image-hash subshell (both find pipelines)"
  - "Byte-deterministic DOCKERFILE_SHA across host locales (en_US.UTF-8, C, zh_CN.UTF-8, etc.)"
affects:
  - "05-02-extract-helper-script"
  - "05-03-add-determinism-test"
  - "any future phase that edits run_docker.sh image-hash pipeline"

tech-stack:
  added: []
  patterns:
    - "Inline LC_ALL=C prefix on sort invocations within content-hash pipelines (vs. global export) — keeps intent obvious to future readers"

key-files:
  created: []
  modified:
    - "run_docker.sh — two sort invocations prefixed with LC_ALL=C (lines 215 and 220)"

key-decisions:
  - "Inline LC_ALL=C prefix per sort invocation rather than global export — keeps locale intent visible at the call site (RESEARCH.md §Placement of LC_ALL=C)"

patterns-established:
  - "Locale-stable content hashing: every sort feeding a hash pipeline gets LC_ALL=C inline"

requirements-completed: [FOUND-01]

duration: 2min
completed: 2026-05-12
---

# Phase 05 Plan 01: Locale-Stable Sort in Image Hash Summary

**Two `sort` invocations inside `run_docker.sh`'s content-hash subshell now run under `LC_ALL=C`, eliminating locale-driven flap of `DOCKERFILE_SHA` for source trees containing non-ASCII filenames.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-12T05:52:43Z
- **Completed:** 2026-05-12T05:53:48Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Prefixed the `docker-bin/` find pipeline with `LC_ALL=C sort` (run_docker.sh:215)
- Prefixed the `mcp-gateway/` find pipeline with `LC_ALL=C sort` (run_docker.sh:220)
- Preserved every other byte of the subshell: prune list, Binja/IDA conditional blocks, F-1 fix comment, downstream variables (`DOCKERFILE_SHA`, `SHORT_SHA`, `HASH_IMAGE`), and the `set -euo pipefail` discipline are byte-identical
- `bash -n run_docker.sh` exits 0; `./run_docker.sh --help` exits 0

## Task Commits

1. **Task 1: Add LC_ALL=C to both sort invocations in run_docker.sh image-hash subshell** — `652fa94` (fix)

## Files Created/Modified

- `run_docker.sh` — Two `sort` calls in the image-hash subshell prefixed with `LC_ALL=C` (lines 215 and 220). No other lines changed.

## Decisions Made

- **Inline `LC_ALL=C` prefix** (not a global `export LC_ALL=C` earlier in the script) — the locale intent stays attached to the sort calls that need it, so future readers don't have to scroll to find the cause of byte-deterministic ordering. Matches RESEARCH.md §"Placement of LC_ALL=C".

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external configuration changes.

## Next Phase Readiness

- Plan 05-02 (`scripts/compute_image_hash.sh` helper extraction) can now extract a locale-stable pipeline rather than inheriting a flaky one.
- Plan 05-03 (determinism regression test) has a stable target to assert against.
- No blockers introduced.

## Self-Check: PASSED

- File `run_docker.sh` exists and contains exactly 2 `LC_ALL=C sort` occurrences (verified via `grep -cE`)
- Commit `652fa94` present in `git log` (verified)
- Variables `DOCKERFILE_SHA`, `SHORT_SHA`, `HASH_IMAGE` preserved (verified via grep)
- Prune list line preserved (verified via grep)
- `bash -n run_docker.sh` exits 0; `./run_docker.sh --help` exits 0 (verified)

---
*Phase: 05-f-1-image-hash-fix*
*Completed: 2026-05-12*
