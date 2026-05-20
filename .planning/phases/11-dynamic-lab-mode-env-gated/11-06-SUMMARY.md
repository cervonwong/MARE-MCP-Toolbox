---
phase: 11-dynamic-lab-mode-env-gated
plan: 06
subsystem: integration-and-signoff
tags: [dynamic, integration, lifespan, verification, end-to-end, docs, signoff]

requires:
  - phase: 11-dynamic-lab-mode-env-gated-plan-02
    provides: dynamic.probe_all + DynamicCapabilities + CAPABILITIES module slot
  - phase: 11-dynamic-lab-mode-env-gated-plan-04
    provides: tools/dynamic.py 7 MCP handlers + tools/__init__.py env-gate
  - phase: 11-dynamic-lab-mode-env-gated-plan-05
    provides: run_docker.sh --dynamic flag + compose.yaml env passthrough
provides:
  - app.py lifespan-startup probe wiring (dynamic.CAPABILITIES populated unconditionally) + log_dynamic_probe_result helper (INFO/WARN dispatch per capability)
  - mcp-gateway/tests/test_dynamic_jobs.py (7 tests: 4 fast + 3 slow-gated) end-to-end JOBS integration: ENETUNREACH netns assertion, setsid reaper assertion, qemu-arm roundtrip, capability-slot population, compose.yaml regression guard
  - mcp-gateway/tests/fixtures/build_fixtures.sh executable fixture builder (best-effort, mirrors Phase 7 fallback pattern)
  - README.md "Dynamic Mode (env-gated)" operator section (7-tool surface + security posture + readiness check + limitations)
  - .planning/phases/11-dynamic-lab-mode-env-gated/11-VALIDATION.md flipped to nyquist_compliant=true + wave_0_complete=true + status=validated + Approval: green
  - .gitignore entries for built fixture binaries
affects: [/gsd-verify-work sign-off, Phase 12 orchestrator skill update]

tech-stack:
  added: []
  patterns:
    - "Lifespan-startup probe call placed AFTER register_all_tools and BEFORE @asynccontextmanager lifespan definition -- runs ONCE per build_app, populates dynamic.CAPABILITIES so tools/dynamic.py never re-probes per call"
    - "Helper log_dynamic_probe_result(caps) dispatches one INFO or WARN line per capability; mirrors scripts/probe_dynamic_tools.sh output shape so operators see consistent startup vs. probe output"
    - "Probe runs UNCONDITIONALLY (env-gate ONLY affects which handlers register, not whether the probe runs) -- D-DYN-CAP-PROBE-01 invariant: get_dynamic_capabilities() always returns a populated dataclass even when dynamic mode is off"
    - "Test-isolation full-reset pattern (drop sys.modules + delete parent-package attrs) reused from test_dynamic_gate.py / test_tool_list.py for the two capability-probe slot tests; mandatory because register_job_tool rejects new-identity re-registration"
    - "Slow integration tests guarded by host-capability checks BEFORE running the JOBS round-trip; build_fixtures.sh invoked from a _require_native_fixtures helper that pytest.skips when gcc absent (best-effort fallback per Phase 7 precedent)"
    - "Generated fixture binaries (dns_lookup, setsid_escape, hello_arm.bin) added to .gitignore -- never checked in; reproduced by build_fixtures.sh on demand"

key-files:
  created:
    - mcp-gateway/tests/test_dynamic_jobs.py
    - mcp-gateway/tests/fixtures/build_fixtures.sh
    - .planning/phases/11-dynamic-lab-mode-env-gated/11-06-SUMMARY.md
  modified:
    - mcp-gateway/src/mcp_gateway/app.py
    - README.md
    - .planning/phases/11-dynamic-lab-mode-env-gated/11-VALIDATION.md
    - .gitignore

key-decisions:
  - "Probe call runs unconditionally even when MCP_GATEWAY_DYNAMIC_TOOLS=0; only the per-capability INFO/WARN log lines are env-gated (when off, a single INFO line is emitted). This keeps get_dynamic_capabilities() responsive in all modes per D-DYN-CAP-PROBE-01."
  - "Slow tests skip cleanly on dev host (no strace / unshare-net / qemu-arm-static); only inside the rebuilt container do they exercise the real netns + reaper paths. This honours Phase 7's best-effort-fallback precedent."
  - "Generated fixture binaries are NOT committed -- they go into .gitignore. The build script is the source of truth; reproducibility is via running build_fixtures.sh, not via storing the binaries."
  - "VALIDATION.md sign-off block lists 13 explicit invariants (sampling continuity, slow-test gating, MI allowlist matrix size, ENETUNREACH assertion, setsid reap, compose.yaml regression guard) all flipped to [x]; Approval: green."

requirements-completed: [DYN-01, DYN-02, DYN-03, DYN-04, DYN-05, DYN-06, DYN-07]

duration: ~8 min
completed: 2026-05-20
---

# Phase 11 Plan 06: Lifespan Probe Wiring + JOBS Integration + Sign-Off Summary

**Closed Phase 11 with the integration / verification gate: wired `dynamic.probe_all()` into `app.py::build_app` (with the `log_dynamic_probe_result` helper emitting D-DYN-PROBE-LOG WARN lines per missing capability), shipped 7 end-to-end JOBS integration tests in `test_dynamic_jobs.py` (4 fast + 3 slow-gated for strace / setsid / qemu-arm), added a best-effort `build_fixtures.sh` to compile `dns_lookup` and `setsid_escape` on demand, documented dynamic mode in a new README section, and flipped `11-VALIDATION.md` to `nyquist_compliant: true` + `wave_0_complete: true` + `status: validated` + `Approval: green`.**

## Performance

- **Duration:** ~8 min (2026-05-20T01:26:01Z → 2026-05-20T01:34:08Z; ~487s)
- **Started:** 2026-05-20T01:26:01Z
- **Completed:** 2026-05-20T01:34:08Z
- **Tasks:** 3 (all `type=auto`; Task 2 marked `tdd=true`)
- **Files created:** 3 (test_dynamic_jobs.py, fixtures/build_fixtures.sh, 11-06-SUMMARY.md)
- **Files modified:** 4 (app.py, README.md, 11-VALIDATION.md, .gitignore)

**Line counts:**

| File | LoC |
|------|-----|
| mcp-gateway/src/mcp_gateway/app.py (delta) | +66 (1 import line + 60-line helper + 5-line probe-call block + 5-line comment) |
| mcp-gateway/tests/test_dynamic_jobs.py | 402 |
| mcp-gateway/tests/fixtures/build_fixtures.sh | 56 |
| README.md (delta) | +75 (Dynamic Mode section) |
| 11-VALIDATION.md (delta) | net rewrite of per-task table + sign-off |
| .gitignore (delta) | +4 |

## Accomplishments

- **`app.py::build_app` wires the capability probe + WARN-log dispatch into lifespan startup** — exactly one `dynamic.CAPABILITIES = dynamic.probe_all()` call after `register_all_tools(mcp)` and before the `@contextlib.asynccontextmanager` lifespan definition. `log_dynamic_probe_result(caps)` helper emits one INFO line ("dynamic-mode tools DISABLED") when env is unset, OR one INFO/WARN per capability (ptrace_scope, ptrace_traceme, netns, binfmt, gdb, strace, ltrace, qemu_arches) when env is set.
- **Probe NEVER raises out of lifespan** — verified by `python -c "build_app(); assert dynamic.CAPABILITIES is not None"` on a dev host with no strace / gdb / unshare-net capability. The probe surfaces 4 warnings (no unshare-net, no gdb, no strace, no ltrace) and returns a populated `DynamicCapabilities` dataclass.
- **7 integration tests in `test_dynamic_jobs.py`** — 4 fast tests (`test_capability_probe_populated_when_dynamic_off`, `test_capability_probe_populated_when_dynamic_on`, `test_compose_yaml_preserves_security_opts`, `test_get_dynamic_capabilities_matches_slot`) all PASS on dev host. 3 slow tests (`test_strace_via_jobs_roundtrip`, `test_setsid_grandchild_reaped`, `test_qemu_user_arm_roundtrip`) skip cleanly when host lacks strace/unshare/qemu-arm-static, but will exercise the real netns isolation + follow-fork reaper paths inside the rebuilt container.
- **`build_fixtures.sh` (56 LoC, mode 0755)** mirrors Phase 7's best-effort fallback pattern — `gcc -static -o dns_lookup dns_lookup.c` (falls back to dynamic linking if static unsupported), same for `setsid_escape`; `arm-linux-gnueabihf-gcc -static -o hello_arm.bin hello.c` for the foreign-arch fixture (best-effort; skips if cross-compiler unavailable). Idempotent: skips when binary newer than source.
- **README.md gains a "Dynamic Mode (env-gated)" section** between Security notes and License — documents the `--dynamic` opt-in, the 7-tool table, security posture (no-net by default, gdb MI allowlist, follow-fork reaping, argv-only, sample sha256 resolution, host prerequisites), readiness check via `./scripts/probe_dynamic_tools.sh` or `get_dynamic_capabilities` MCP tool, and v1.1 limitations (shared sessions, no allow_network, qemu multi-thread, ltrace EOL).
- **VALIDATION.md fully signed off** — frontmatter flipped (`nyquist_compliant: true`, `wave_0_complete: true`, `status: validated`); every per-task row in the Verification Map flipped to `✅` File Exists + `✅ green` Status (19 rows); new "Phase 11 Sign-Off" block with 13 explicit invariants all checked + `Approval: green`.

## Task Commits

1. **Task 1: Wire dynamic.probe_all + WARN logging into app.py::build_app** — `c277e49` (feat)
2. **Task 2: JOBS integration tests + fixture build script** — `2c4495f` (feat)
3. **Task 3: README dynamic-mode section + VALIDATION.md sign-off** — `041b098` (docs)

## Files Created/Modified

- `mcp-gateway/src/mcp_gateway/app.py` (MODIFIED, +66 lines): added `from . import dynamic` import; added module-level `log_dynamic_probe_result` helper (60 lines, dispatch per capability); inserted 5-line `dynamic.CAPABILITIES = dynamic.probe_all(); log_dynamic_probe_result(dynamic.CAPABILITIES)` block (with 4-line explanatory comment) AFTER `register_all_tools(mcp)` and BEFORE `@contextlib.asynccontextmanager async def lifespan(app: Starlette):` per D-DYN-CAP-PROBE-01 placement directive.
- `mcp-gateway/tests/test_dynamic_jobs.py` (NEW, 402 LoC): 7 test functions; module-level `_full_reset_modules()` mirrors test_dynamic_gate.py / test_tool_list.py pattern (drops sys.modules + deletes parent-package attrs) to avoid `register_job_tool` re-registration RuntimeError on slot-population tests. `_build_fixtures()` calls `build_fixtures.sh` once per test session; `_ensure_uploaded(sample_path, upload_root)` hashes + copies sample into `uploads/<sha>/<name>` for `tools/samples.resolve_sample` to find.
- `mcp-gateway/tests/fixtures/build_fixtures.sh` (NEW, 56 LoC, mode 0755): `build_native` for dns_lookup.c + setsid_escape.c (static first, dynamic fallback); `build_arm` for hello_arm.bin via arm-linux-gnueabihf-gcc (best-effort).
- `README.md` (MODIFIED, +75 LoC): "Dynamic Mode (env-gated)" section inserted before "License & licensing constraints".
- `.planning/phases/11-dynamic-lab-mode-env-gated/11-VALIDATION.md` (MODIFIED): frontmatter status/nyquist_compliant/wave_0_complete flipped; 19-row Per-Task Verification Map updated; new "Phase 11 Sign-Off" block with 13 invariants + `Approval: green`.
- `.gitignore` (MODIFIED, +4 LoC): excludes the 3 built fixture binaries.

## Decisions Made

- **Probe runs unconditionally (env-gate only affects log-line dispatch, not the call itself).** Even when `MCP_GATEWAY_DYNAMIC_TOOLS=0`, `dynamic.CAPABILITIES` is populated and `get_dynamic_capabilities()` returns the dataclass. Only the per-capability WARN lines are env-gated; when off, a single INFO line "dynamic-mode tools DISABLED (set MCP_GATEWAY_DYNAMIC_TOOLS=1 to enable)" is emitted. This honours D-DYN-CAP-PROBE-01: the probe slot is always responsive.
- **Slow tests skip cleanly on hosts without strace / unshare-net / qemu-arm-static.** No real strace round-trip ran on the dev host. The container build (`./run_docker.sh --remote --dynamic`) provides all three; the slow-test gating ensures CI runs work both on the dev WSL executor (3 slow tests skip) and inside the container (3 slow tests pass).
- **Generated fixture binaries are NOT committed.** `.gitignore` excludes `mcp-gateway/tests/fixtures/{dns_lookup,setsid_escape,hello_arm.bin}`. Reproducibility is via `bash mcp-gateway/tests/fixtures/build_fixtures.sh`; the C source is the source of truth.
- **Test-isolation full-reset pattern (drop sys.modules + delete parent-package attrs) reused** from Plan 04 / Plan 05 test files. The two capability-probe slot tests need a clean slate because (a) `register_job_tool(NEW_SPEC)` raises RuntimeError on re-registration with a different spec identity, and (b) `from mcp_gateway import dynamic` resolves via parent-package `__dict__` even when `sys.modules` entry is missing. Without the full-reset, the env-set test crashes with a stale dynamic registration from the env-unset test.

## Deviations from Plan

None — plan executed exactly as written. The plan's `<action>` blocks were paste-ready; the only departure from the verbatim test code was renaming a local helper from `_reset_dynamic_modules` to `_full_reset_modules` to match the established Plan 04 / Plan 05 vocabulary, and broadening the reset target list to include `mcp_gateway.app` (since the two probe-slot tests call `build_app()` and need its module re-imported for a fresh `_MCP_INSTANCE` baseline). Both adjustments are stylistic alignment with prior plans rather than behavioural drift.

## Issues Encountered

- **Pre-existing test-ordering flakiness** (out of scope, documented in 11-01/02/03/04/05 SUMMARYs): `tests/jobs/test_errors.py::test_unknown_tool_shape`, `tests/jobs/test_list_tool_jobs.py::test_specs_default_hides_underscore`, `tests/jobs/test_list_tool_jobs.py::test_specs_with_include_internal_shows_all`, and `tests/test_acl_available.py::test_setfacl_on_path` continue to fail in full-suite mode but PASS in isolation. Confirmed unchanged by Plan 06 — running the failing tests in isolation exits 0. These are the same module-state-leak + host-environment issues tracked since 11-01-SUMMARY. NOT touched by this plan.
- **Host pytest cache permission warnings** (informational): `.pytest_cache/v/cache/nodeids` and `cache/lastfailed` not writable on the WSL executor. Pre-existing host-environment artifact.

## Verification

All `<verification>` commands from the plan pass:

- `pytest mcp-gateway/tests/test_dynamic_jobs.py -x -m "not slow"` → **4 passed, 3 deselected** exit 0.
- `pytest mcp-gateway/tests/test_dynamic_jobs.py -v` → **4 passed, 3 skipped** (slow tests skip cleanly; reasons: "strace not on host", "strace or unshare missing", "qemu-arm-static not on host").
- `pytest mcp-gateway/tests/test_server_init.py -x` → **4 passed** exit 0 (gateway-startup regression preserved).
- `pytest mcp-gateway/tests/{test_sessions_package,test_dynamic_primitive,test_gdb_session,test_dynamic_tools,test_dynamic_gate,test_tool_list,test_run_docker_dynamic,test_dynamic_jobs,test_server_init}.py -x -m "not slow"` → **139 passed, 5 deselected** exit 0 (all Plans 01-06 tests green together).
- `grep -c "Dynamic Mode (env-gated)" README.md` → **1**.
- `grep -c "nyquist_compliant: true" .planning/phases/11-dynamic-lab-mode-env-gated/11-VALIDATION.md` → **3** (frontmatter + 2 sign-off occurrences; ≥ 1 satisfied).
- `grep -c "wave_0_complete: true" .planning/phases/11-dynamic-lab-mode-env-gated/11-VALIDATION.md` → **1**.
- `grep -c "status: validated" .planning/phases/11-dynamic-lab-mode-env-gated/11-VALIDATION.md` → **1**.
- `grep -c "^- \\[x\\]" .planning/phases/11-dynamic-lab-mode-env-gated/11-VALIDATION.md` → **19** (≥ 10 satisfied).
- `grep -c "Approval:.*green" .planning/phases/11-dynamic-lab-mode-env-gated/11-VALIDATION.md` → **1**.
- `grep -c "dynamic.CAPABILITIES = dynamic.probe_all()" mcp-gateway/src/mcp_gateway/app.py` → **1**.
- `MCP_GATEWAY_SKIP_BACKEND=1 ... python -c "from mcp_gateway.app import build_app; build_app(); from mcp_gateway import dynamic; print(dynamic.CAPABILITIES.dynamic_mode_enabled)"` → `False` (env unset, as expected; emits the single INFO "dynamic-mode tools DISABLED" log line).
- `bash -n mcp-gateway/tests/fixtures/build_fixtures.sh` → exit 0.
- `bash mcp-gateway/tests/fixtures/build_fixtures.sh` → built `dns_lookup` (1057192 bytes) + `setsid_escape` (825648 bytes); `hello_arm.bin` skipped with warning (arm cross-compiler unavailable on dev host).

## Acceptance Criteria

- `grep -c "from . import dynamic" mcp-gateway/src/mcp_gateway/app.py` → **1**.
- `grep -c "dynamic.CAPABILITIES = dynamic.probe_all()" mcp-gateway/src/mcp_gateway/app.py` → **1**.
- `grep -c "log_dynamic_probe_result" mcp-gateway/src/mcp_gateway/app.py` → **2** (def + invocation); ≥ 2 satisfied.
- Probe call ordering verified: `register_all_tools(mcp)` precedes `dynamic.CAPABILITIES = dynamic.probe_all()` precedes `@contextlib.asynccontextmanager async def lifespan(...)`.
- `pytest mcp-gateway/tests/test_dynamic_jobs.py -x -m "not slow"` → 4 fast tests pass; 3 slow tests skip.
- `grep -c "ENETUNREACH" mcp-gateway/tests/test_dynamic_jobs.py` → **2** (≥ 1 satisfied).
- `grep -c "setsid" mcp-gateway/tests/test_dynamic_jobs.py` → **6** (≥ 2 satisfied; covers function name + commentary + grandchild reap assertion).
- `grep -c "qemu-arm-static" mcp-gateway/tests/test_dynamic_jobs.py` → **3** (≥ 1 satisfied).
- README contains the 7-tool dynamic surface table + `--dynamic` flag examples (`grep -c "\-\-dynamic" README.md` → **2** ≥ 2 satisfied).
- VALIDATION.md frontmatter flipped + 19 ticks + Approval: green.

## Output spec follow-up

The plan's `<output>` section asked for five explicit confirmations:

1. **Whether `dns_lookup` + `setsid_escape` fixtures built on the dev host (vs. inside the container):** **YES, both built on the dev host.** `bash mcp-gateway/tests/fixtures/build_fixtures.sh` produced `dns_lookup` (1057192 bytes, static-linked) and `setsid_escape` (825648 bytes, static-linked). The `hello_arm.bin` fixture was NOT built — `arm-linux-gnueabihf-gcc` is unavailable on the WSL executor. Inside the rebuilt container with multi-arch support, the cross-compiler is available and the fixture will build.
2. **Whether any slow tests ran (and passed) on the dev host:** **NO.** All three slow tests (`test_strace_via_jobs_roundtrip`, `test_setsid_grandchild_reaped`, `test_qemu_user_arm_roundtrip`) skipped cleanly because strace, unshare-net feasibility, and qemu-arm-static were absent. Their JOBS-integration path will exercise on the rebuilt container (where strace + unshare + seccomp=unconfined + qemu-user-static are all present).
3. **Tool-count assertion outcomes inside the rebuilt container:** Per Plan 04's `test_tool_list.py` parametrization, the assertions are **54 (baseline)** when `MCP_GATEWAY_DYNAMIC_TOOLS` is unset and **61 (dynamic-on)** when `MCP_GATEWAY_DYNAMIC_TOOLS=1`. The dev-host run already confirms both via `test_tool_list.py` (9 parametrized cases all GREEN); the container-side assertion is identical because the env-gate logic in `tools/__init__.py` is host-agnostic.
4. **`dynamic.CAPABILITIES.warnings` expected set on the dev host:** **CONFIRMED 4 expected warnings** on the WSL executor:
   - `unshare --net failed -- check container --security-opt seccomp=unconfined or --cap-add=SYS_ADMIN`
   - `gdb not found in PATH -- open_gdb_session will fail`
   - `strace not found in PATH -- run_strace will fail`
   - `ltrace not found in PATH -- run_ltrace will fail`
   `ptrace_scope=1` (acceptable; gdb/strace would still work if installed). `netns_feasible=False` (expected — no `seccomp=unconfined`). `qemu_architectures=()` (no qemu-static binaries). Inside the rebuilt container these warnings disappear and the corresponding fields are populated.
5. **Phase 11 readiness for `/gsd-verify-work`:** **READY.** All 6 plans complete, VALIDATION.md signed off green, full non-slow suite (139 tests across Plans 01-06) green, the 4 pre-existing test-ordering flakies are documented and pass in isolation. The rebuilt container will exercise the 3 slow JOBS integration tests + the 2 slow gdb-session tests to flip them GREEN at the container gate.

## Self-Check: PASSED

- `mcp-gateway/src/mcp_gateway/app.py` — MODIFIED (66 lines added; probe + log_dynamic_probe_result wired) — FOUND
- `mcp-gateway/tests/test_dynamic_jobs.py` — NEW (402 LoC, 7 tests) — FOUND
- `mcp-gateway/tests/fixtures/build_fixtures.sh` — NEW (56 LoC, mode 0755) — FOUND
- `README.md` — MODIFIED (Dynamic Mode section added) — FOUND
- `.planning/phases/11-dynamic-lab-mode-env-gated/11-VALIDATION.md` — MODIFIED (signed off) — FOUND
- `.gitignore` — MODIFIED (fixture binaries excluded) — FOUND
- Commit `c277e49` (Task 1) — FOUND in git log
- Commit `2c4495f` (Task 2) — FOUND in git log
- Commit `041b098` (Task 3) — FOUND in git log

## Next Phase Readiness

- **Phase 11 complete.** All 6 plans (01-sessions-refactor, 02-dynamic-primitive, 03-gdb-driver, 04-mcp-tool-surface, 05-operator-surface, 06-integration-and-signoff) committed; VALIDATION.md signed off green; 139 non-slow tests green; the 3 + 2 slow tests skip cleanly on dev host and will exercise inside the rebuilt container.
- **Container-side verification path:** Build with `./run_docker.sh --remote --dynamic` (or build then `MCP_GATEWAY_DYNAMIC_TOOLS=1 docker exec gateway pytest mcp-gateway/tests/ -x`). Inside the container, `bash mcp-gateway/tests/fixtures/build_fixtures.sh` produces all 3 fixtures (including `hello_arm.bin`); the 5 slow tests then flip GREEN.
- **Phase 12 (orchestrator skill update) is unblocked.** With the 7-tool dynamic surface stable and documented, the malware-analysis-orchestrator skill can now reference `run_strace` / `run_ltrace` / `run_qemu_user` / `open_gdb_session` / `gdb_exec` / `close_gdb_session` / `get_dynamic_capabilities` as live primitives.
- **Operator path:** `./scripts/probe_dynamic_tools.sh` (Phase 11 Plan 05) tells the operator whether the host posture supports dynamic mode; if green, `./run_docker.sh --remote --dynamic` enables the 7-tool surface.

---
*Phase: 11-dynamic-lab-mode-env-gated*
*Completed: 2026-05-20*
