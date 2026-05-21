# Phase 5: F-1 Image-Hash Fix - Context

**Gathered:** 2026-05-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Make `./run_docker.sh` reliably invalidate the cached image tag whenever any
file under `mcp-gateway/` (excluding ephemeral cache/build paths) changes, and
prove the invariant with a regression test that fails if the property regresses.

Scope is narrow: harden + verify the content-hash, extract it for testability,
and add the regression test. This phase does NOT touch the Dockerfile, the
gateway runtime, or any v1.1 RE tooling.

</domain>

<decisions>
## Implementation Decisions

### Hash Logic
- **D-01:** The mcp-gateway content hash is already implemented inline at
  `run_docker.sh:212-229`. This phase verifies and hardens it — it does NOT
  rewrite the surrounding image-tag mechanism. The success-criteria assertion
  must continue using the same `DOCKERFILE_SHA` / `SHORT_SHA` / `HASH_IMAGE`
  variable names so downstream consumers (Docker tag, `[build] up to date`
  message, `tag :latest` step) are unaffected.
- **D-02:** Add `LC_ALL=C` to the `sort` invocation inside the hash subshell
  so file ordering is byte-deterministic across hosts (en_US.UTF-8 vs C vs
  zh_CN.UTF-8 currently produce different sort orders for non-ASCII names,
  which would flap the hash between developer machines). Single-line, low-risk.
- **D-03:** Keep the existing prune list as-is — `__pycache__`, `.pytest_cache`,
  `.ruff_cache`, `.venv`, `*.egg-info`, `htmlcov`, `node_modules`, `dist`.
  Spec (Success Criterion 3) requires the first four; the rest are a strict
  superset, all benign, and prevent foreseeable flap from coverage/JS tool
  output. Do NOT remove items just because the spec doesn't name them.
- **D-04:** Do NOT add new ignored paths beyond the current list unless the
  regression test surfaces a real flap source (e.g., `.coverage`, `*.swp`,
  IDE dirs). Premature ignore-list expansion is forbidden — only widen on
  demonstrated need with a test that reproduces the flap.

### Testability Refactor
- **D-05:** Extract the hash computation into a standalone helper:
  `scripts/compute_image_hash.sh`. The helper:
  - Takes one positional arg: the build-root path (defaults to the repo root
    when run from `run_docker.sh`).
  - Reads optional env vars `INSTALL_BINARY_NINJA`, `BINARY_NINJA_ZIP`,
    `INSTALL_IDA_PRO`, `IDA_PRO_ZIP` (matching current run_docker.sh inputs).
  - Prints the 64-char sha256 hex hash to stdout, nothing else.
  - Exits non-zero on missing inputs with a clear stderr message.
- **D-06:** `run_docker.sh` replaces its inline hash subshell with a call to
  the helper. Behavior must be byte-identical to current output for any
  unchanged input — no semantic drift during the extraction.

### Test Design
- **D-07:** Regression test lives at `mcp-gateway/tests/test_image_hash.py`
  (pytest — consistent with all 18 existing v1.0 test files in that directory).
- **D-08:** Tests operate on fixture trees built in `tmp_path` — they do NOT
  mutate the real `mcp-gateway/` tree. The fixture mirrors a minimal
  mcp-gateway layout: a `Dockerfile`, a `docker-bin/` dir with one file, a
  `mcp-gateway/` subdir with `src/x.py`, `pyproject.toml`, and at least one
  pruned path (e.g., `mcp-gateway/__pycache__/foo.pyc`, `mcp-gateway/.venv/lib/marker`).
- **D-09:** Required test cases (one assertion per Success Criterion):
  - SC-1: touch `mcp-gateway/src/x.py` → hash differs from baseline.
  - SC-2: touch `mcp-gateway/pyproject.toml` → hash differs from baseline.
  - SC-3a-d: write a new file under each pruned path
    (`__pycache__`, `.venv`, `*.egg-info`, `.pytest_cache`) → hash equals baseline.
  - SC-4: explicit assertion that touching `mcp-gateway/src/x.py` changes
    the hash returned by `scripts/compute_image_hash.sh` (this is the
    regression-test-of-record named in the success criteria).
- **D-10:** Tests invoke the helper via `subprocess.run` with a clean env
  (no Binja/IDA inputs configured for the baseline cases, since those
  branches require real zip files). A separate test asserts that toggling
  `INSTALL_BINARY_NINJA=0 → 1` with a stub zip changes the hash — this
  guards the existing Binja/IDA conditional from regressing.
- **D-11:** Test must be hermetic — no network, no docker, no real
  mcp-gateway dependency. Runs in <2s in CI.

### Claude's Discretion
The user said "continue as you see fit, choose the most sound answer" — all
decisions above are Claude's recommended defaults. The planner and executor
may adjust within these constraints:
- Exact helper script name (`compute_image_hash.sh` is the recommendation, but
  any descriptive name under `scripts/` is acceptable).
- Internal layout of the pytest fixture (single fixture vs per-test) — the
  required assertions are fixed, the test-file structure is not.
- Whether to inline the helper as a bash function in a shared `lib/` file
  vs a standalone script — preserving the testable contract (callable from
  the test as a subprocess) is what matters.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Spec
- `.planning/ROADMAP.md` §"Phase 5: F-1 Image-Hash Fix" — 4 success criteria
- `.planning/REQUIREMENTS.md` — FOUND-01 (the requirement this phase fulfills)
- `.planning/MILESTONES.md` §F-1 — origin story of the bug
  (caught 2026-05-11 UAT: Plan 04-03's `tools/resources.py` not in image
  until force rebuild)

### Code to Modify
- `run_docker.sh:206-232` — current image-tag + content-hash logic (the
  surface to refactor). Note the existing F-1 comment at lines 209-211.
- `mcp-gateway/tests/conftest.py` — existing pytest config; test must
  integrate without breaking it.

### Test-Pattern Reference
- `mcp-gateway/tests/test_print_config.py` — example of a test that
  invokes `run_docker.sh` patterns via subprocess in a hermetic way.
- `mcp-gateway/tests/test_readme_structure.py` — example of a structural
  pytest that asserts repo-level invariants.

### Constraint Reference
- `CLAUDE.md` §Constraints — licensing rule (IDA/Binja zips never baked
  in); explains why `INSTALL_*` toggles + zip sha gating exists in the
  current hash logic and must be preserved verbatim by the refactor.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`run_docker.sh:212-229`** — current hash subshell. Logic is correct in
  spirit; refactor target, not rewrite target.
- **`mcp-gateway/tests/`** — full pytest infrastructure (conftest.py,
  18 existing test files). New test slots in cleanly.
- **`mcp-gateway/tests/test_print_config.py`** — established pattern for
  subprocess-based hermetic tests against `run_docker.sh` behavior. Worth
  reading as a model for the new test.

### Established Patterns
- All v1.0 tests are pytest under `mcp-gateway/tests/`. No bash/bats/shunit2
  in the repo. The new test follows this pattern (D-07).
- Repo-root scripts that are sourced or invoked by `run_docker.sh` don't
  exist yet under a `scripts/` directory; this phase introduces that
  convention. Future phases may grow it (likely Phase 6 `ReToolRunner`
  helper scripts, Phase 11 dynamic-mode launchers).
- `run_docker.sh` uses `set -euo pipefail` and `trap cleanup_stages EXIT`.
  The new helper script must use the same discipline.

### Integration Points
- `run_docker.sh:206-232` is the only call site for the hash. After
  extraction, that's where the helper is invoked. No other code reads
  `DOCKERFILE_SHA`/`SHORT_SHA` outside this block.
- The image-tag downstream consumers (`docker image inspect "$HASH_IMAGE"`,
  `docker buildx build -t "$HASH_IMAGE"`, `docker tag "$HASH_IMAGE"
  "${IMAGE_REPO}:latest"`) all read `HASH_IMAGE` from the calling scope —
  the refactor must preserve `HASH_IMAGE` as a variable in `run_docker.sh`'s
  scope, not the helper's.

</code_context>

<specifics>
## Specific Ideas

- The user pre-instrumented this fix during the v1.0 → v1.1 transition
  (see the `F-1 fix:` comment at `run_docker.sh:209-211`). This phase
  formalizes, hardens, and tests that fix — it does NOT relitigate it.
- Defense-in-depth philosophy: keep the existing prune list broader than
  the spec demands. The cost of over-pruning is zero (those dirs would
  never legitimately affect the image); the cost of under-pruning is a
  test that flaps on every developer's machine. Same logic applied to
  `LC_ALL=C` (D-02) — cheap insurance.

</specifics>

<deferred>
## Deferred Ideas

- **Image rebuild observability** — a `./run_docker.sh --explain-hash`
  flag that prints which files contributed to the hash and the diff
  vs the cached tag. Useful when a developer is confused about a
  rebuild, but well outside Phase 5 scope. Consider for a future
  developer-experience phase.
- **Hash-cache pre-flight in CI** — verifying that CI doesn't ship an
  image whose `DOCKERFILE_SHA` is stale. Belongs in a future CI/release
  phase, not here.
- **`scripts/` directory convention doc** — once Phases 6, 11 add more
  helpers, a brief README explaining the layout. Not blocking Phase 5.
- **Locale assertion** — making `compute_image_hash.sh` fail-loud if
  invoked in a locale where `LC_ALL=C` was not applied. Over-engineering
  for Phase 5; revisit only if a real-world miss occurs.

</deferred>

---

*Phase: 05-f-1-image-hash-fix*
*Context gathered: 2026-05-12*
</content>
</invoke>