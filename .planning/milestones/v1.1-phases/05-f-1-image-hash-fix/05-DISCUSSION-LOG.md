# Phase 5: F-1 Image-Hash Fix - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-12
**Phase:** 5-f-1-image-hash-fix
**Areas discussed:** Scope of fix, Test location & framework, Testability refactor, Ignore list scope

---

## Pre-discussion observation

`run_docker.sh:212-229` already includes `mcp-gateway/` in `DOCKERFILE_SHA` with prune exclusions matching three of four success criteria. Phase work is therefore: verify, harden, extract for testability, and add the regression test that Success Criterion 4 names.

---

## Gray areas presented

| Area | Description | Selected |
|------|-------------|----------|
| Scope of fix | Hash already includes mcp-gateway/. Verify + regression-test only, or also tighten (LC_ALL=C sort determinism, broader ignore list, robustness)? | ✓ |
| Test location & framework | pytest under mcp-gateway/tests/ (existing infra) vs new top-level tests/ (bash/bats). | ✓ |
| Testability refactor | Keep hash inline in run_docker.sh vs extract to scripts/compute_image_hash.sh callable by tests. | ✓ |
| Ignore list scope | Lock list to spec-required 4 paths vs keep broader defense-in-depth list. | ✓ |

**User's choice:** "continue as you see fit, choose the most sound answer"

The user delegated decisions to Claude across all four areas. Choices below were locked in CONTEXT.md.

---

## Scope of fix

| Option | Description | Selected |
|--------|-------------|----------|
| Verify + regression test only | Don't touch existing hash; just prove it works. | |
| Verify + LC_ALL=C hardening + regression test | Add deterministic sort + test. Low-risk, cross-host correctness. | ✓ |
| Full hash rewrite | Restructure ignore semantics, alternate digest, etc. | |

**Notes:** LC_ALL=C is one line and prevents flap across locales — cheap insurance. No broader rewrite needed; the spec mandate is narrow.

---

## Test location & framework

| Option | Description | Selected |
|--------|-------------|----------|
| pytest under mcp-gateway/tests/ | Reuse conftest.py, match v1.0 pattern (18 existing test files). | ✓ |
| New top-level tests/ with bash/bats | Closer to the script under test. | |
| Inline shellcheck-style assertion in run_docker.sh | Self-test on every invocation. | |

**Notes:** mcp-gateway/tests/ is the established convention. Introducing bash test infra for a single test file is unjustified weight.

---

## Testability refactor

| Option | Description | Selected |
|--------|-------------|----------|
| Keep inline; test invokes run_docker.sh | Test must parse log output or mock docker. | |
| Extract to scripts/compute_image_hash.sh; test invokes helper | Helper prints hash, nothing else. Hermetic test, clean contract. | ✓ |
| Reimplement hash in Python in conftest | Duplicates logic; risks drift. | |

**Notes:** Extraction yields a clean callable surface and zero docker dependency for the test. Helper takes a path arg so tests can run against fixture trees in tmp_path.

---

## Ignore list scope

| Option | Description | Selected |
|--------|-------------|----------|
| Lock to spec 4 (__pycache__, .venv, *.egg-info, .pytest_cache) | Minimal surface. | |
| Keep current 8-item list as defense-in-depth | Strict superset; covers htmlcov, node_modules, dist, .ruff_cache. | ✓ |
| Expand further (.coverage, *.swp, IDE dirs) | Premature without demonstrated flap. | |

**Notes:** Existing broader list is benign and prevents foreseeable flap. Future expansion only on demonstrated need with a test that reproduces.

---

## Claude's Discretion

- Exact helper script name (scripts/compute_image_hash.sh recommended).
- Test fixture layout (single vs per-test) — assertions fixed, structure flexible.
- Helper as standalone script vs sourced bash function — testable contract is what matters.

## Deferred Ideas

- `--explain-hash` flag (developer experience phase).
- CI pre-flight to detect stale image shipments (release phase).
- `scripts/` convention README (after Phase 6/11 add more helpers).
- Locale-assertion guard inside helper (over-engineering until real-world miss occurs).
</content>
</invoke>