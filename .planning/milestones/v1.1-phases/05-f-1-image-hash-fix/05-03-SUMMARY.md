---
phase: 05-f-1-image-hash-fix
plan: 03
subsystem: testing
tags: [pytest, subprocess, bash, sha256, regression-test, docker-cache, found-01]

requires:
  - phase: 05-f-1-image-hash-fix
    provides: "scripts/compute_image_hash.sh helper (Plan 05-02) with documented stdout/stderr/exit contract"
provides:
  - "Hermetic 11-node pytest regression test (`mcp-gateway/tests/test_image_hash.py`) locking the FOUND-01 invariant: gateway source edits flip the image hash, pruned-path writes do not."
  - "Subprocess test pattern with explicit minimal env dict (PATH + HOME only) — reusable template for any future test that exercises a repo shell script without env bleed."
  - "Coverage of all four Phase 5 Success Criteria (SC-1..SC-4) plus D-10 Binja-toggle guard, runnable in <0.5s wall-clock."
affects: [phase-06-retool-runner, phase-07-shell-and-wrappers, phase-08-sessions, phase-09-jobs, phase-10-extraction, phase-11-dynamic-mode, phase-12-orchestrator-skill-update]

tech-stack:
  added: []
  patterns:
    - "Hermetic subprocess test: build fixture under tmp_path, invoke shell helper with explicit env={PATH, HOME[+extras]}, never env=os.environ"
    - "Single-fixture-per-test hash comparison: build → baseline → mutate → recompute → compare (Pitfall 4 avoidance — paths embedded in sha256sum output)"

key-files:
  created:
    - "mcp-gateway/tests/test_image_hash.py - 11-node pytest regression for FOUND-01"
  modified: []

key-decisions:
  - "Copied test skeleton verbatim from 05-RESEARCH.md §Code Examples §Test File Skeleton — fixture byte-spec and assertion contracts already locked at research time, no re-design at execute time"
  - "Excluded mcp-gateway/tests/e2e/ from the full-suite verification run (those e2e tests require a running docker container; this plan is hermetic per D-11)"

patterns-established:
  - "Subprocess shell-helper test idiom: REPO_ROOT = Path(__file__).resolve().parents[2]; explicit env dict; timeout=10 on every subprocess.run; hash equality on stripped stdout"
  - "Parametrized prune-invariance coverage: one @pytest.mark.parametrize with 4 (subdir, filename) tuples encodes SC-3a..d as 4 collected nodes"

requirements-completed: [FOUND-01]

duration: 87s
completed: 2026-05-12
---

# Phase 05 Plan 03: Regression Test for mcp-gateway Content Hash Summary

**Hermetic 11-node pytest at `mcp-gateway/tests/test_image_hash.py` locking the FOUND-01 invariant — agent edits to `mcp-gateway/src/` or `pyproject.toml` flip the image hash; writes under `__pycache__`/`.venv`/`*.egg-info`/`.pytest_cache` do not; runs in <0.5s.**

## Performance

- **Duration:** 87s (~1.5 min)
- **Started:** 2026-05-12T05:58:51Z
- **Completed:** 2026-05-12T06:00:18Z
- **Tasks:** 1
- **Files modified:** 1 (created)

## Accomplishments

- New regression test `mcp-gateway/tests/test_image_hash.py` covering all four Phase 5 Success Criteria plus the D-10 Binja-toggle guard
- 11 pytest nodes collected and passing (8 plain test functions + 1 parametrized test with 4 cases = 11 nodes)
- Test suite runs in 0.31s wall-clock — well under the 2s D-11 budget
- Full mcp-gateway non-e2e suite still green: 178 passed in 2.21s
- Hermetic: no docker, no network, no real `mcp-gateway/` tree mutation, explicit env dict (only PATH+HOME) prevents developer-shell env bleed

## Task Commits

1. **Task 1: Create mcp-gateway/tests/test_image_hash.py with 11 collected tests** — `a0485c4` (test)

_TDD note: The plan tagged this task `tdd="true"`, but the task is the contract definition for an already-shipped helper (Plan 05-02's `scripts/compute_image_hash.sh`). The "RED → GREEN" sequence collapses because the helper already conforms: running the freshly written tests against the existing helper passes 11/11 on first invocation. No separate failing-test commit was needed — the test file IS the RED+GREEN result in one shot since the helper was authored against the same RESEARCH.md contract._

**Plan metadata commit:** pending (final commit at end of execution).

## Files Created/Modified

- `mcp-gateway/tests/test_image_hash.py` — 122-line pytest file with the `build_root` fixture (mirroring the D-08 byte-spec), the `_hash()` subprocess helper, and 8 test functions (one parametrized for 4 cases, totalling 11 collected nodes).

## Decisions Made

- **Copied skeleton verbatim from RESEARCH.md.** The research phase already locked the fixture byte-spec, the `_hash()` env construction, the 11 assertion contracts, and the four pruned-path parametrize tuples. Execute-time re-design would risk drift from the contract that VALIDATION.md's verification map enforces. The plan explicitly instructed "copy verbatim".
- **No `pytest.ini` / marker changes.** Per D-11 and the test running in 0.31s, no `@pytest.mark.slow` is needed. The test is collected by default under `testpaths = ["tests"]`.
- **Excluded `mcp-gateway/tests/e2e/` from the full-suite verification.** Those e2e tests require docker/network and are normally gated behind a `--run-e2e` marker. Running `pytest mcp-gateway/tests/ -x --ignore=mcp-gateway/tests/e2e` keeps the verification hermetic and matches what `/gsd-verify-work` will run.

## Deviations from Plan

None — plan executed exactly as written. The fixture tree, the `_hash()` helper, the 7 test function names (the count of `def test_` symbols is 8, which matches the spec's 7 plain + 1 parametrized when read as "7 distinct test scenarios"), the parametrize tuples, and the `timeout=10` discipline all match the RESEARCH.md skeleton verbatim.

## Issues Encountered

- **Pre-existing `.pytest_cache` permission warning.** The real `mcp-gateway/.pytest_cache/` directory has restricted permissions (an artifact of running pytest under various uids historically). pytest emits a `PytestCacheWarning: cache could not write path … [Errno 13] Permission denied` on every run. This is unrelated to Plan 05-03 — it appears on every existing test invocation. Not blocking; not in scope.

## User Setup Required

None — no external service configuration required.

## Acceptance Criteria Verification

All criteria from the plan's `<acceptance_criteria>` block satisfied:

| Criterion | Result |
|-----------|--------|
| `test -f mcp-gateway/tests/test_image_hash.py` | ✓ file exists |
| AST parse | ✓ valid Python |
| Collect-only count | ✓ 11 nodes collected |
| `pytest -x` exits 0 | ✓ 11 passed |
| Runtime <2s | ✓ 0.31s (D-11 met) |
| `grep -c 'def test_'` >= 7 | ✓ 8 (7 scenarios, one with parametrize) |
| `grep -c '@pytest.mark.parametrize'` >= 1 | ✓ 1 |
| Each pruned subdir name present | ✓ 3 each (fixture create + parametrize + assertion path = 3 occurrences per name) |
| `INSTALL_BINARY_NINJA` present | ✓ 3 |
| `env=os.environ` absent | ✓ 0 (Pitfall 3 avoided) |
| `hashlib` absent | ✓ 0 (no Python-side hashing) |
| `timeout=10` present | ✓ 2 (in `_hash()` and in `test_missing_dockerfile_exits_nonzero`) |
| Full mcp-gateway suite green | ✓ 178 passed in 2.21s |

## Threat Model Verification

Per the plan's `<threat_model>` block — all mitigations applied:

- **T-05-03-01 (Tampering: fixture writes):** Every write is anchored on the `tmp_path` parameter passed in by pytest. No string concatenation onto `REPO_ROOT` for writes. `HELPER` and `REPO_ROOT` are read-only path references.
- **T-05-03-02 (Tampering: env bleed):** `_hash()` constructs `base_env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")}` and only updates with `env_extra` for the Binja toggle test. `grep -c 'env=os.environ' = 0` confirms no developer-shell INSTALL_* vars can pollute the helper.
- **T-05-03-04 (DoS: test runtime):** Both `subprocess.run` call sites pass `timeout=10`. Full suite runs in 0.31s.

## Next Phase Readiness

- **Phase 5 exit gate:** With Plans 05-01 (`LC_ALL=C` patch), 05-02 (helper extraction), and 05-03 (this regression test) complete, FOUND-01 is now verifiable end-to-end. The phase-level `/gsd-verify-work` smoke (`pytest mcp-gateway/tests/test_image_hash.py -x` + `./run_docker.sh --help`) should pass cleanly.
- **Phase 6 unblocked:** With the image-hash regression locked, subsequent v1.1 phases can safely edit `mcp-gateway/src/` knowing rebuilds will trigger. The 2026-05-11 UAT failure mode (Plan 04-03's `tools/resources.py` not in the container until forced rebuild) is now structurally prevented.
- **Pattern reuse:** Phase 6's `ReToolRunner` and Phase 7's `run_shell` tests will likely benefit from the same hermetic-subprocess pattern established here (explicit env dict, tmp_path fixture, timeout=10).

## Self-Check: PASSED

- ✓ Created file exists: `mcp-gateway/tests/test_image_hash.py`
- ✓ Commit `a0485c4` present in git log (test: add FOUND-01 regression test for mcp-gateway content hash)
- ✓ 11 pytest nodes collected, 11 passing
- ✓ Full mcp-gateway suite still green (178 passed)

---
*Phase: 05-f-1-image-hash-fix*
*Completed: 2026-05-12*
