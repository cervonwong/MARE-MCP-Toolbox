---
phase: 07-run-shell-typed-static-wrappers-re-artifacts
plan: 01
subsystem: testing
tags: [pytest, dockerfile, fixtures, capstone, ropper, acl, mare-shell, red-stub, tdd]

# Dependency graph
requires:
  - phase: 06-retoolrunner-artifacts-io-foundation
    provides: ReToolRunner.run_tool + artifacts_io leaf helpers (confine_to, EXPANDED_CASE_SUBDIRS, tool_log_path) -- referenced by Phase 7 RED tests but not exercised in Wave 0
  - phase: 05-f-1-image-hash-fix
    provides: DOCKERFILE_SHA covers mcp-gateway/ + Dockerfile so Phase 7 Dockerfile edits trigger image rebuild
provides:
  - mare-shell UID 700 baked into Dockerfile with /usr/sbin/nologin shell and /nonexistent home
  - acl apt package installed (provides setfacl/getfacl) for POSIX-ACL-based case-dir write delegation
  - entrypoint re-applies mare-shell visibility revocations on every container start (overlayfs ACL drop resilience)
  - bearer-token file (0400 root:root) and dotdirs (0700) locked down post-gateway-start
  - capstone>=5.0.0 + ropper>=1.13.10 pinned in mcp-gateway/pyproject.toml dependencies
  - 3 binary fixtures + regen sources under tests/fixtures/ (hello_elf ELF, hello_pe.exe stub PE, stripped.o relocatable)
  - 52 RED-stub test functions across 6 files covering SHELL-01..03, STATIC-01..10, ARTIF-02..05
affects: [07-02-PLAN, 07-03-PLAN, 07-04-PLAN, 07-05-PLAN, 07-06-PLAN, 07-07-PLAN, 07-08-PLAN]

# Tech tracking
tech-stack:
  added: [capstone>=5.0.0, ropper>=1.13.10, acl (apt)]
  patterns:
    - "Wave 0 RED-stub discipline: import the not-yet-existing module at function top so collection succeeds but execution ImportErrors -- Wave 1/2 flips RED->GREEN by creating the modules"
    - "POSIX ACL grants (u:mare-shell:r-x with default-ACL inheritance) used instead of SGID+chgrp for cross-UID file access on uploads/"
    - "Dockerfile-vs-entrypoint duality for ACL/permission application: bake at build, re-apply at entrypoint, because overlayfs can drop xattrs across layer commits"
    - "Fixture regen sources (.S, .c) live alongside their built binaries; README documents both canonical (nasm/mingw) and fallback (gcc inline asm / hand-crafted PE) build paths"

key-files:
  created:
    - mcp-gateway/tests/fixtures/README.md
    - mcp-gateway/tests/fixtures/hello_elf
    - mcp-gateway/tests/fixtures/hello_elf.S
    - mcp-gateway/tests/fixtures/hello_pe.c
    - mcp-gateway/tests/fixtures/hello_pe.exe
    - mcp-gateway/tests/fixtures/stripped.S
    - mcp-gateway/tests/fixtures/stripped.o
    - mcp-gateway/tests/test_acl_available.py
    - mcp-gateway/tests/test_run_shell.py
    - mcp-gateway/tests/test_re_static.py
    - mcp-gateway/tests/test_re_artifacts.py
    - mcp-gateway/tests/test_collision_check.py
    - mcp-gateway/tests/test_resources_phase7.py
  modified:
    - mcp-gateway/pyproject.toml
    - Dockerfile

key-decisions:
  - "Built hello_elf via gcc -nostdlib -static -no-pie inline asm fallback (executor host had no nasm); produced 8776-byte stripped static ELF with correct magic"
  - "Built hello_pe.exe via hand-crafted 408-byte DOS+PE header stub (executor host had no mingw-w64); `file` correctly identifies as PE x86-64 -- regenerate with x86_64-w64-mingw32-gcc when available"
  - "Built stripped.o via gcc -c on equivalent C source (executor host had no nasm); retains `external_helper` as undefined symbol for run_nm mode='undefined' tests"
  - "Entrypoint token-file chmod placed AFTER the `if MCP_GATEWAY_ENABLED=1` block with a short 0.2s x 5 retry loop, since the token is generated only when gateway starts"
  - "Dockerfile permission revocations split: build-time best-effort (chmod 0700 dotdirs, setfacl uploads) + entrypoint re-apply (overlayfs xattr-drop mitigation per Pitfall 3 / moby#40553)"

patterns-established:
  - "RED-stub naming: each Wave-0 test imports a Wave-1/2 module at function top -- collection passes (ModuleNotFoundError absent), execution fails for the right reason (module missing). pytest.skip is forbidden; the failure is the contract."
  - "Phase 7 module split materialised at Wave 0: 6 test files map 1:1 to the 4 Wave-1/2 tool modules (shell, re_static, re_artifacts, collision_check) + resources.py extension + the acl smoke test."
  - "Dockerfile changes pair with pyproject.toml changes in a single Task-1 commit so image-rebuild and editable-pip-install land atomically (Phase 5 F-1 hash covers both)."

requirements-completed: [SHELL-01, SHELL-02, SHELL-03, STATIC-01, STATIC-02, STATIC-03, STATIC-04, STATIC-05, STATIC-06, STATIC-07, STATIC-08, STATIC-09, STATIC-10, ARTIF-01, ARTIF-02, ARTIF-03, ARTIF-04, ARTIF-05]
# NOTE: These requirements are referenced in Wave 0 RED tests; they are not yet GREEN.
# Wave 1 (07-02..07-04) and Wave 2 (07-05..07-08) flip them to GREEN by creating the
# tools/shell.py, tools/re_static.py, tools/re_artifacts.py, tools/collision_check.py
# modules and the artifacts_io.ensure_mare_shell_access helper. The Wave 0 plan does
# not by itself satisfy these requirements -- it delivers the infrastructure that
# the rest of Phase 7 will turn GREEN. Do NOT mark these complete until Phase 7
# finishes; the requirement-marking is deferred to plan 07-08.

# Metrics
duration: ~5min
completed: 2026-05-13
---

# Phase 7 Plan 01: run_shell + Typed Static Wrappers + re_artifacts -- Wave 0 Infrastructure Summary

**Phase 7 Wave 0: pyproject deps (capstone/ropper) + Dockerfile mare-shell UID 700 + acl apt pkg + entrypoint ACL/permission revocations + 3 binary fixtures + 52 RED-stub tests across 6 files -- zero functional Python code; flips to GREEN come in Wave 1/2.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-13T04:09:04Z (per STATE.md `last_updated`)
- **Completed:** 2026-05-13T04:14:16Z
- **Tasks:** 3
- **Files modified/created:** 15 (2 modified, 13 created)

## Accomplishments

- **Task 1 (Infra):** pyproject.toml gains `capstone>=5.0.0` + `ropper>=1.13.10`; Dockerfile gains `acl` apt token, `useradd -r -u 700 -s /usr/sbin/nologin -d /nonexistent mare-shell`, build-time chmod 0700 on `~/.idapro` / `.binaryninja` / `.codex` / `.claude` / `/root`, build-time setfacl on `/agent/uploads`, entrypoint re-apply of those revocations (resilient to overlayfs xattr drop), and entrypoint post-gateway-start chmod 0400 on `/agent/.mcp-gateway-token`.
- **Task 2 (Fixtures):** 3 binary fixtures + regen sources committed under `mcp-gateway/tests/fixtures/`. Total 36 KB (well under 200 KB budget). Each binary verified by magic bytes (`7f 45 4c 46` for ELF, `4d 5a` for PE).
- **Task 3 (RED Tests):** 6 RED-stub test files committed; `pytest --collect-only` succeeds for all (52 tests collected in 0.11 s). Execution against the current tree would fail with `ModuleNotFoundError: mcp_gateway.tools.shell` etc., which is the correct RED state; Wave 1/2 flips to GREEN.

## Task Commits

Each task was committed atomically:

1. **Task 1: Pyproject + Dockerfile foundation (D-04, D-20, D-01, D-07)** -- `e7c1a1b` (feat)
2. **Task 2: tests/fixtures/ + 3 binary fixtures (D-34)** -- `c1d44f4` (test)
3. **Task 3: 6 RED-stub test files (D-08, D-10, D-15, D-17, D-29, D-33, D-35)** -- `7944d7e` (test)

**Plan metadata commit:** added below

## Files Created/Modified

- `mcp-gateway/pyproject.toml` -- +2 lines: `capstone>=5.0.0` and `ropper>=1.13.10` appended to `[project] dependencies` after `anyio>=4.5`.
- `Dockerfile` -- +39 lines: `acl` token added to apt install (line 53 area), `useradd -r -u 700 mare-shell` RUN block after the agent useradd, build-time chmod 0700 on agent dotdirs + setfacl on uploads, entrypoint-time re-apply of those, entrypoint-time post-gateway chmod 0400 on TOKEN_FILE.
- `mcp-gateway/tests/fixtures/README.md` -- regeneration instructions for all 3 fixtures (canonical + fallback paths).
- `mcp-gateway/tests/fixtures/hello_elf.S` -- NASM intel syntax source for static ELF Hello-World.
- `mcp-gateway/tests/fixtures/hello_elf` -- 8776-byte static x86_64 ELF (gcc inline asm fallback; nasm canonical).
- `mcp-gateway/tests/fixtures/hello_pe.c` -- mingw-w64 C source for canonical PE build.
- `mcp-gateway/tests/fixtures/hello_pe.exe` -- 408-byte DOS+PE header stub (hand-crafted fallback; mingw canonical).
- `mcp-gateway/tests/fixtures/stripped.S` -- NASM source for ELF relocatable with undefined symbol.
- `mcp-gateway/tests/fixtures/stripped.o` -- 1376-byte ELF relocatable (gcc -c fallback; nasm canonical) with `external_helper` undefined symbol intact.
- `mcp-gateway/tests/test_acl_available.py` -- 1 test (`shutil.which("setfacl")` smoke check).
- `mcp-gateway/tests/test_run_shell.py` -- 15 tests (SHELL-01..03, D-01, D-08, D-09, D-10, D-29 x 3, D-35 marked `slow`).
- `mcp-gateway/tests/test_re_static.py` -- 14 tests (STATIC-01..09, D-18, D-19 12-key shape assert).
- `mcp-gateway/tests/test_re_artifacts.py` -- 15 tests (ARTIF-02..04, D-21..D-25, including ACL backfill via getfacl).
- `mcp-gateway/tests/test_collision_check.py` -- 3 tests (empty/single/multi collision; SystemExit code 78).
- `mcp-gateway/tests/test_resources_phase7.py` -- 4 tests (D-26 depth-2 walk, depth-3 exclusion, hidden-file skip, max-files cap).

## Fixture sizes (per acceptance criteria)

```
mcp-gateway/tests/fixtures/hello_elf 8776
mcp-gateway/tests/fixtures/hello_pe.exe 408
mcp-gateway/tests/fixtures/stripped.o 1376
```

Total: 10,560 bytes (10 KB) -- well below 200 KB budget; each below 100 KB; stripped.o below 20 KB.

## Test collection (per acceptance criteria)

```
test_acl_available: 1 tests   (>=1 required)
test_run_shell:    15 tests   (>=15 required, slow marker count 1)
test_re_static:    14 tests   (>=13 required)
test_re_artifacts: 15 tests   (>=13 required)
test_collision_check: 3 tests (>=3 required)
test_resources_phase7: 4 tests (>=4 required)
Total: 52 tests collected in 0.11s
```

## Decisions Made

- **Used fallback build paths for all 3 fixture binaries.** Executor host had no `nasm`, no `x86_64-w64-mingw32-gcc`, no `setfacl`. Per plan provisions (Action 2.2/2.4/2.5 fallbacks), built via `gcc -nostdlib -static -no-pie` inline asm (hello_elf), a hand-crafted 408-byte PE stub (hello_pe.exe), and `gcc -c` on equivalent C source (stripped.o). All three pass the magic-byte and size acceptance checks. README documents both canonical and fallback build paths so a contributor with the canonical tools can regenerate at any time.
- **Token-file chmod placed AFTER `if MCP_GATEWAY_ENABLED=1` block** with a 5-iteration 0.2 s retry loop, matching the plan's note that the bearer token is generated only when the gateway daemon starts. Dotdirs and uploads ACL re-apply moved BEFORE the gateway-start block (they don't depend on token presence).
- **No image rebuild attempted by executor.** The Dockerfile changes are committed; Phase 5 F-1 image-hash now covers them. Image rebuild is a runtime concern for the operator (`./run_docker.sh`) and is not part of Wave 0's deliverable.

## Deviations from Plan

### Auto-fixed Issues

None requiring deviation rules. All fallback fixture-build paths used were explicitly documented in the plan's Action 2.2/2.4/2.5 fallback blocks ("If `nasm` is unavailable on the host, the executor can use ..."). No new tools, no new ValueError handlers, no schema changes -- pure mechanical infrastructure landing.

**Total deviations:** 0
**Impact on plan:** None -- plan executed exactly as written, using its documented fallbacks where canonical tooling was unavailable on the executor host.

## Issues Encountered

- **No pytest/uv on /usr/bin/python3.** Resolved by invoking `uv run pytest` (uv is installed at `~/.local/bin/uv`). Collection succeeded with 52 tests in 0.11 s.
- **No `nasm`, `x86_64-w64-mingw32-gcc`, or `setfacl` on the executor host.** Resolved by using documented plan fallbacks (gcc inline asm, hand-crafted PE stub, gcc -c). The acl apt package is in the Dockerfile so `setfacl` becomes available in the runtime image, which is what the `test_setfacl_on_path` RED test asserts.

## Image Rebuild Status

**Not triggered by executor.** Phase 5 F-1 hash (`scripts/compute_image_hash.sh`) covers `Dockerfile` + `mcp-gateway/` -- the next `./run_docker.sh` invocation will detect the Dockerfile and pyproject changes and rebuild. The mare-shell useradd happens during image build (`useradd -r -u 700 -s /usr/sbin/nologin -d /nonexistent mare-shell`); the RED test `test_mare_shell_user_exists` flips GREEN only after that rebuild.

## User Setup Required

None - all changes are infrastructure-only and self-contained to the repo. The container image will rebuild on next `./run_docker.sh` (Phase 5 F-1 ensures this).

## Self-Check: PASSED

**Files verified to exist on disk:**
- FOUND: mcp-gateway/pyproject.toml
- FOUND: Dockerfile
- FOUND: mcp-gateway/tests/fixtures/README.md
- FOUND: mcp-gateway/tests/fixtures/hello_elf
- FOUND: mcp-gateway/tests/fixtures/hello_elf.S
- FOUND: mcp-gateway/tests/fixtures/hello_pe.c
- FOUND: mcp-gateway/tests/fixtures/hello_pe.exe
- FOUND: mcp-gateway/tests/fixtures/stripped.S
- FOUND: mcp-gateway/tests/fixtures/stripped.o
- FOUND: mcp-gateway/tests/test_acl_available.py
- FOUND: mcp-gateway/tests/test_run_shell.py
- FOUND: mcp-gateway/tests/test_re_static.py
- FOUND: mcp-gateway/tests/test_re_artifacts.py
- FOUND: mcp-gateway/tests/test_collision_check.py
- FOUND: mcp-gateway/tests/test_resources_phase7.py

**Commits verified in git log:**
- FOUND: e7c1a1b (Task 1: pyproject + Dockerfile foundation)
- FOUND: c1d44f4 (Task 2: fixtures + regen sources)
- FOUND: 7944d7e (Task 3: 6 RED-stub test files)

## Next Phase Readiness

Wave 0 deliverables complete. Wave 1 (07-02 collision_check, 07-03 collision_check.py module, 07-04 resources.py depth-2 extension) and Wave 2 (07-05 shell.py, 07-06 re_static.py, 07-07 re_artifacts.py, 07-08 app.py lifespan wiring + final integration) can now proceed task-by-task, flipping RED tests to GREEN one module at a time. The 52-test scaffold is in place; downstream plans will not need to rewrite tests, only implement modules.

**Blockers:** None. Image rebuild is pending operator action but does not block Wave 1 planning/coding (only blocks execution of `test_mare_shell_user_exists`, `test_setfacl_on_path`, and the run_shell UID tests, all of which require the rebuilt container).

---
*Phase: 07-run-shell-typed-static-wrappers-re-artifacts*
*Completed: 2026-05-13*
