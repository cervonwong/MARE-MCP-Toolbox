---
phase: 05-f-1-image-hash-fix
plan: 02
subsystem: image-build
tags: [bash, content-hash, refactor, docker-cache, mcp-gateway]
requires:
  - "Plan 05-01 (LC_ALL=C inline patch in run_docker.sh:215,220 — provides the byte-spec the helper must mirror)"
  - "Bash 4+ (set -euo pipefail, [[ ]], printf, command substitution)"
  - "GNU coreutils (sha256sum, find, sort, xargs, awk) — already used by run_docker.sh"
provides:
  - "scripts/compute_image_hash.sh — standalone, testable mcp-gateway content-hash helper"
  - "Subprocess boundary for the image-hash logic (unblocks Plan 05-03's pytest regression test)"
affects:
  - "run_docker.sh:212-220 — inline subshell replaced with helper invocation; DOCKERFILE_SHA/SHORT_SHA/HASH_IMAGE still in run_docker.sh scope"
tech-stack:
  added:
    - "scripts/ directory convention (new at repo root — first script lives here; future Phases 6/11 will extend)"
  patterns:
    - "Helper-subprocess + env-var-prefix forwarding (no global export)"
    - "Positional BUILD_ROOT arg + dirname-based default (mirrors run_docker.sh SCRIPT_DIR idiom)"
    - "set -euo pipefail + stderr error messages + categorized non-zero exits (2 = missing input, 3 = toggle/zip mismatch)"
    - "':-' default-value expansion so helper is invocable from a clean env (Plan 05-03 tests)"
key-files:
  created:
    - "scripts/compute_image_hash.sh (51 lines, mode 0755)"
  modified:
    - "run_docker.sh (inline 18-line hash subshell replaced with 7-line command substitution)"
decisions:
  - "D-05 honored verbatim: helper at scripts/compute_image_hash.sh takes one positional arg, reads four env vars with ':-' defaults, emits 64-char hex on stdout, errors to stderr, non-zero exits"
  - "D-06 honored verbatim: run_docker.sh refactor preserves DOCKERFILE_SHA/SHORT_SHA/HASH_IMAGE in calling scope; behavior remains byte-identical to post-Plan-05-01 inline form for any unchanged input"
  - "D-03 honored: eight-item prune list (__pycache__, .pytest_cache, .ruff_cache, .venv, *.egg-info, htmlcov, node_modules, dist) copied verbatim"
  - "CLAUDE.md licensing posture preserved: two-step Binja/IDA conditional pattern (toggle var emitted always; sha256sum of zip only when toggle=1) replicated verbatim"
  - "Env-var prefix syntax (not export) for forwarding into the helper subprocess — scopes side effects to the command substitution"
metrics:
  duration: "100s"
  tasks_completed: 2
  files_created: 1
  files_modified: 1
  completed: "2026-05-12T05:56:50Z"
---

# Phase 5 Plan 2: Extract Image-Hash Helper Summary

**One-liner:** Extracted run_docker.sh:212-229's inline image-hash subshell into a standalone executable `scripts/compute_image_hash.sh`, preserving byte-identical hash output and replacing the call site with an env-prefixed command substitution that keeps DOCKERFILE_SHA/SHORT_SHA/HASH_IMAGE in run_docker.sh's scope.

## Objective Recap

Plan 05-02 makes the mcp-gateway content hash *testable* (Plan 05-03 prerequisite) by giving it a clean subprocess boundary, without changing its output for unchanged inputs. Behavior must remain byte-identical to the post-Plan-05-01 inline form (CLAUDE.md backward-compatibility constraint, D-06).

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Create `scripts/` directory and `compute_image_hash.sh` helper | `27b666e` | `scripts/compute_image_hash.sh` (new, mode 0755) |
| 2 | Replace run_docker.sh:212-229 inline hash subshell with helper invocation | `76a7120` | `run_docker.sh` |

## Implementation Notes

### Helper script (Task 1)

`scripts/compute_image_hash.sh` is a verbatim copy of the canonical skeleton from `05-RESEARCH.md §Code Examples §Helper Script Skeleton`. The contract:

- **Positional arg `BUILD_ROOT`** — defaults to `$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)` (mirrors `run_docker.sh:5`'s `SCRIPT_DIR` idiom).
- **Env vars** (with `':-'` defaults for clean-env safety): `INSTALL_BINARY_NINJA`, `INSTALL_IDA_PRO`, `BINARY_NINJA_ZIP`, `IDA_PRO_ZIP`.
- **stdout:** 64-char lowercase sha256 hex, exactly nothing else.
- **Exit codes:** `0` success; `2` for missing build root / missing Dockerfile; `3` for `INSTALL_*=1` with the corresponding zip missing.
- **Discipline:** `set -euo pipefail`; all variable expansions double-quoted; no `eval`; errors go to stderr.

Both `sort` invocations carry `LC_ALL=C` per D-02 (Plan 05-01 added them inline to run_docker.sh; this plan carries them across with the rest of the body). The eight-item prune list is verbatim (D-03), as is the two-step Binja/IDA conditional pattern (CLAUDE.md licensing posture: toggle string is always part of the hash stream; the zip's own sha256 is only added when the toggle is `"1"`, and if the toggle is `"1"` but the zip is missing the helper exits 3 with a clear stderr message).

### Call-site refactor (Task 2)

`run_docker.sh:212-220` is now:

```bash
DOCKERFILE_SHA="$(
  INSTALL_BINARY_NINJA="$INSTALL_BINARY_NINJA" \
  BINARY_NINJA_ZIP="$BINARY_NINJA_ZIP" \
  INSTALL_IDA_PRO="$INSTALL_IDA_PRO" \
  IDA_PRO_ZIP="$IDA_PRO_ZIP" \
  bash "$SCRIPT_DIR/scripts/compute_image_hash.sh" "$SCRIPT_DIR"
)"
SHORT_SHA="${DOCKERFILE_SHA:0:12}"
HASH_IMAGE="${IMAGE_REPO}:${SHORT_SHA}"
```

Notes:
- The F-1 fix explanatory comment block at lines 208-211 is preserved verbatim above the new call site.
- Env-var prefix syntax (not `export`) is used per D-06, scoping side effects to the helper subprocess.
- `$SCRIPT_DIR` was already in scope at line 5 — no additional plumbing needed.
- All three downstream variables (`DOCKERFILE_SHA`, `SHORT_SHA`, `HASH_IMAGE`) remain assigned in run_docker.sh's own shell scope so all downstream consumers (`docker image inspect "$HASH_IMAGE"`, `docker buildx build -t "$HASH_IMAGE" ...`, `docker tag "$HASH_IMAGE" "${IMAGE_REPO}:latest"`) work unchanged (D-01).
- The trap/cleanup block at lines 225-228 (originally 234+) is unchanged.

## Verification

All overall-verification commands in `05-02-PLAN.md §<verification>` pass:

```
[OK] helper executable, syntax OK
[OK] helper output: 46465d2bfda2b769c9b0bf406bc869961db8d3afeccdda959fdd9e49b765c651 (64 hex)
[OK] missing-Dockerfile exit=2, stderr contains "Dockerfile"
[OK] run_docker.sh syntax OK
[OK] ./run_docker.sh --help exits 0
[count] DOCKERFILE_SHA/SHORT_SHA/HASH_IMAGE defs in run_docker.sh: 3
[count] scripts/compute_image_hash.sh refs in run_docker.sh:       1
[count] LC_ALL=C sort in run_docker.sh:                            0   (inline body removed)
[count] LC_ALL=C sort in scripts/compute_image_hash.sh:            2   (helper body)
```

All success criteria from `05-02-PLAN.md §<success_criteria>` satisfied.

## Deviations from Plan

None — plan executed exactly as written. Both tasks were verbatim copies of the RESEARCH.md skeleton + call-site patch (which were authored to land on top of Plan 05-01's `LC_ALL=C sort` inline patch). Smoke test against the real repo produces a valid 64-char sha256 hex; preflight error paths return the documented exit codes 2/3 with the documented stderr messages.

No auto-fixes triggered (Rules 1-3 dormant). No architectural escalation (Rule 4 dormant).

## Authentication Gates

None. Plan is purely build-script refactor — no auth surface.

## Threat Surface

No new threat surface beyond what the plan's `<threat_model>` already declared:

- T-05-02-01 (Tampering — helper script body): **mitigated** — `set -euo pipefail`, all variable expansions double-quoted, no `eval`, no unquoted command construction.
- T-05-02-02 (Tampering — `BUILD_ROOT` positional arg): **mitigated** — non-directory build roots and missing Dockerfile both reject with `exit 2`.
- T-05-02-03..06: accept (no new exploitable surface introduced).

No threat flags to report — the helper does not create new network/auth/file-system surface; it is a read-only checksum computation.

## Known Stubs

None. Both files are complete, production-ready implementations. The data path is fully wired: `run_docker.sh` → helper subprocess → stdout sha256 hex → consumed verbatim by `DOCKERFILE_SHA`/`SHORT_SHA`/`HASH_IMAGE`.

## Self-Check

```
$ test -f scripts/compute_image_hash.sh && echo FOUND
FOUND
$ test -x scripts/compute_image_hash.sh && echo FOUND
FOUND
$ git log --oneline | grep -q 27b666e && echo FOUND: 27b666e
FOUND: 27b666e
$ git log --oneline | grep -q 76a7120 && echo FOUND: 76a7120
FOUND: 76a7120
```

## Self-Check: PASSED

All claimed artifacts exist on disk; both commits exist in git history.
