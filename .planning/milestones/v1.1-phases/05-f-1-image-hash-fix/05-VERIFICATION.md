---
phase: 05-f-1-image-hash-fix
verified: 2026-05-12T14:30:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification: null
gaps: []
deferred: []
human_verification: []
---

# Phase 5: Image Hash Fix Verification Report

**Phase Goal:** Agent edits to `mcp-gateway/` reliably reach the running container without manual rebuild gymnastics
**Verified:** 2026-05-12T14:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Success Criteria)

| #  | Truth                                                                                           | Status     | Evidence                                                                              |
|----|-------------------------------------------------------------------------------------------------|------------|---------------------------------------------------------------------------------------|
| SC-1 | An analyst editing any file under `mcp-gateway/src/` triggers an image rebuild on the next `./run_docker.sh` invocation | ✓ VERIFIED | `test_sc1_src_edit_changes_hash` PASSED — overwriting `src/x.py` changes the helper hash |
| SC-2 | An analyst editing `mcp-gateway/pyproject.toml` triggers an image rebuild                     | ✓ VERIFIED | `test_sc2_pyproject_edit_changes_hash` PASSED — overwriting `pyproject.toml` changes the hash |
| SC-3 | Edits to ignored paths (`__pycache__`, `.venv`, `*.egg-info`, `.pytest_cache`) do NOT trigger spurious rebuilds | ✓ VERIFIED | All 4 parametrized cases of `test_sc3_pruned_writes_do_not_change_hash` PASSED |
| SC-4 | A regression test asserts `DOCKERFILE_SHA` changes when `mcp-gateway/src/x.py` is touched     | ✓ VERIFIED | `test_sc1_src_edit_changes_hash` in `mcp-gateway/tests/test_image_hash.py` is the named regression-of-record; 11/11 tests pass in 0.31s |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `run_docker.sh` | Invoke helper with env forwarding; define `DOCKERFILE_SHA`/`SHORT_SHA`/`HASH_IMAGE` in own scope | ✓ VERIFIED | Lines 212-220: env-prefix call to `scripts/compute_image_hash.sh`; all 3 variable assignments confirmed; `--help` exits 0 |
| `scripts/compute_image_hash.sh` | Standalone executable, `set -euo pipefail`, 64-char hex to stdout | ✓ VERIFIED | Exists at mode 0755, 49 lines, syntax OK, produces valid 65-byte output (64 hex + newline) against real repo root |
| `mcp-gateway/tests/test_image_hash.py` | 11-node pytest covering all 4 SCs | ✓ VERIFIED | 11 tests collected, 11 passed, 0.31s runtime — well under 2s D-11 budget |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `run_docker.sh` (DOCKERFILE_SHA assignment) | `scripts/compute_image_hash.sh` | env-var prefix command substitution | ✓ WIRED | `grep -c scripts/compute_image_hash.sh run_docker.sh` = 1; env forwarding of all 4 vars confirmed at lines 213-217 |
| `scripts/compute_image_hash.sh` | `sha256sum / find / LC_ALL=C sort / awk` | subshell pipeline | ✓ WIRED | 2 occurrences of `LC_ALL=C sort` in helper; pipeline ends `\| sha256sum \| awk '{print $1}'`; 0 occurrences remaining in `run_docker.sh` |
| `mcp-gateway/tests/test_image_hash.py` | `scripts/compute_image_hash.sh` | `subprocess.run(["bash", str(HELPER), str(build_root)], env=...)` | ✓ WIRED | `HELPER = REPO_ROOT / "scripts" / "compute_image_hash.sh"` anchored via `Path(__file__).resolve().parents[2]`; explicit minimal env dict confirmed |

### Data-Flow Trace (Level 4)

Not applicable — all three artifacts are build-time scripts and a test file, not components rendering dynamic data.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Helper produces valid 64-char hash | `bash scripts/compute_image_hash.sh "$(pwd)" \| wc -c` | 65 (64 hex + newline) | ✓ PASS |
| Helper rejects missing Dockerfile | `bash scripts/compute_image_hash.sh <tmpdir-no-dockerfile>` | exit 2, stderr contains "Dockerfile" | ✓ PASS |
| `run_docker.sh --help` exits 0 | `./run_docker.sh --help; echo "exit: $?"` | exit: 0 | ✓ PASS |
| All 11 regression tests pass | `pytest mcp-gateway/tests/test_image_hash.py -v` | 11 passed in 0.31s | ✓ PASS |
| No inline `LC_ALL=C sort` remaining in `run_docker.sh` | `grep -c 'LC_ALL=C sort' run_docker.sh` | 0 | ✓ PASS |
| Helper has exactly 2 `LC_ALL=C sort` occurrences | `grep -c 'LC_ALL=C sort' scripts/compute_image_hash.sh` | 2 | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| FOUND-01 | Plans 05-01, 05-02, 05-03 | Agent edits to `mcp-gateway/src/` trigger Docker image rebuild on next `./run_docker.sh` invocation | ✓ SATISFIED | Helper extracts, prunes, and hashes mcp-gateway tree; regression test proves SC-1..SC-4; `run_docker.sh` calls helper and uses `DOCKERFILE_SHA` to gate `docker buildx build` (line 241 guard: `if ! docker image inspect "$HASH_IMAGE"`) |

No orphaned requirements — only FOUND-01 is mapped to Phase 5 in REQUIREMENTS.md, and all three plans claim it.

### Anti-Patterns Found

| File | Lines | Pattern | Severity | Impact |
|------|-------|---------|----------|--------|
| `scripts/compute_image_hash.sh` | 35, 40 | `find ... -print \| LC_ALL=C sort \| xargs sha256sum` — no `xargs -r` (WR-01) | Advisory | If `docker-bin/` or `mcp-gateway/` were ever empty of tracked files, `xargs` would invoke `sha256sum` on stdin, contributing a phantom empty-digest entry. Both directories are currently non-empty (`docker-bin/configure-agent-mcp.sh` exists; `mcp-gateway/src/` has files), so this is latent and does not break SC-1..SC-4 today. |
| `scripts/compute_image_hash.sh` | 35, 40 | `find -print` (newline-delimited) piped to `xargs` (WR-02) | Advisory | Filenames containing whitespace or newlines would be misparsed. Current repo has no such filenames in the hashed paths. Latent; does not break any success criterion today. |

No blocker-severity anti-patterns found. The two warnings are carried forward from the code review (05-REVIEW.md WR-01, WR-02) and are informational for future hardening.

### Human Verification Required

None. All four success criteria are covered by the automated regression test suite and behavioral spot-checks.

### Gaps Summary

No gaps. All four success criteria are verified:

- SC-1 and SC-4 are backed by `test_sc1_src_edit_changes_hash`, which mutates `mcp-gateway/src/x.py` in a hermetic fixture and asserts the helper output changes.
- SC-2 is backed by `test_sc2_pyproject_edit_changes_hash`.
- SC-3 is backed by all four parametrized cases of `test_sc3_pruned_writes_do_not_change_hash` (`__pycache__`, `.venv`, `mcp_gateway.egg-info`, `.pytest_cache`).
- The full mechanism is end-to-end wired: `run_docker.sh` → `scripts/compute_image_hash.sh` → `DOCKERFILE_SHA` → `HASH_IMAGE` tag → `docker image inspect` cache gate.

The two advisory warnings (WR-01 empty-xargs edge case, WR-02 exotic filenames) do not break any success criterion under current repo conditions.

---

_Verified: 2026-05-12T14:30:00Z_
_Verifier: Claude (gsd-verifier)_
