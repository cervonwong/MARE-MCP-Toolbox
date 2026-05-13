---
phase: 07-run-shell-typed-static-wrappers-re-artifacts
verified: 2026-05-13T05:04:48Z
status: human_needed
score: 6/6 must-haves verified (host-runnable layer); 3 items require container/MCP-client verification
overrides_applied: 0
human_verification:
  - test: "Dockerfile rebuild produces mare-shell UID=700, /usr/sbin/nologin, /nonexistent home, and ACL revocations on /agent/uploads"
    expected: "`docker compose run --rm gateway-agent id mare-shell` returns `uid=700(mare-shell) gid=700(mare-shell)`; `getfacl /agent/uploads` shows `user:mare-shell:r-x` access AND default ACL"
    why_human: "Requires docker build + run round-trip; mare-shell does not exist on the executor host. test_run_shell.py::test_setpriv_uid_drop SKIPS on host with reason 'mare-shell user not present'."
  - test: "D-35 100 MB /dev/urandom slow test passes inside the container"
    expected: "`docker compose run --rm gateway-agent uv run pytest -m slow tests/test_run_shell.py::test_run_shell_100mb_urandom` exits 0 in <60s; output cap + capture function correctly with the real setpriv -> mare-shell -> bash chain"
    why_human: "Host lacks setfacl, so the slow test is SKIPPED in the local environment (`setfacl unavailable on host; container build installs acl package`)."
  - test: "MCP Resources actually visible to a remote MCP client (Claude Code / mastra) with mare://cases/<case>/tool-logs/<file> URIs"
    expected: "After running a `run_shell` or other captured tool, an external MCP client issues `resources/list` and receives entries for both the v1.0 depth-1 artifacts AND new depth-2 `<subdir>/<file>` entries"
    why_human: "Requires live MCP client roundtrip; mastra e2e suite is already known-failing locally (unrelated Node.js module resolution error, see deferred-items.md)."
---

# Phase 7: run_shell + Typed Static Wrappers + re_artifacts — Verification Report

**Phase Goal:** Remote agents can invoke the full Kali static-analysis surface — ad-hoc bash one-liners plus 12 typed wrappers with structured output — into a confined, captured case-dir artifact tree

**Verified:** 2026-05-13T05:04:48Z
**Status:** human_needed (automated layer fully passes; container-runtime + live-MCP-client behaviours need human verification)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (mapped from ROADMAP Success Criteria + PLAN must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Agent can call `run_shell(case_dir, cmd)` with bash one-liner, runs as `mare-shell` UID with cwd pinned, hard timeout, output cap, auto-capture to `tool-logs/` | ✓ VERIFIED | `tools/shell.py:153-206` defines `run_shell` calling `_validate_cmd` (D-29), `resolve_case_dir` (Phase 6 cwd pin), `ensure_mare_shell_access`, and `run_tool` with `setpriv --reuid=mare-shell --regid=mare-shell --clear-groups --no-new-privs --inh-caps=-all -- bash -c <cmd>` (lines 122-133); Phase 6 `run_tool` provides timeout + output cap + tool-logs/ capture (slug="run_shell") |
| 2 | `MCP_GATEWAY_TOKEN`, API keys, AWS-style creds NOT reachable from inside `run_shell`; docstring states confinement is posture, not isolation | ✓ VERIFIED | `_build_shell_env` (shell.py:70-108) builds env from scratch with explicit `_RUN_SHELL_ALLOWED_KEYS` frozenset of 9 keys (none of which are MCP_GATEWAY_TOKEN/AWS_*/API_*); `run_shell` passes `env=_build_shell_env(...)` to `run_tool` (line 205) so the gateway's `os.environ` is NEVER inherited; docstring line 5 + line 160 contain "posture, not isolation" verbatim |
| 3 | Agent can call run_file, run_die, run_xxd, run_readelf, run_objdump, run_nm, run_rabin2, run_capstone_disasm, run_ropper, run_jq, run_yq — each returning head-truncated preview + captured log | ✓ VERIFIED | `tools/re_static.py` exposes all 11 functions (lines 125, 137, 159, 187, 211, 231, 262, 289, 366, 438, 456) and registers them via `register(mcp)` (lines 481-491). Subprocess wrappers all `await run_tool(...)` (Phase 6 chokepoint → tool-logs/ + head-truncated). In-process wrappers (capstone, ropper) use `_inproc_result` (lines 68-89) producing the same 12-key shape (D-19). Allowlists enforced (`_READELF_ALLOWED`, `_OBJDUMP_MODE_FLAGS`, `_NM_MODE_FLAGS`, `_RABIN2_ALLOWED`). |
| 4 | Case directories transparently grow tool-logs, extracted, hex, rop, dynamic, qemu, disassembly, decompilation, xrefs subdirs on first write (lazy creation) | ✓ VERIFIED | `artifacts_io.EXPANDED_CASE_SUBDIRS` (lines 33-43) is the canonical 9-tuple. `ensure_subdir` (lines 104-119) uses `mkdir(parents=False, exist_ok=True)` for lazy creation. Behavioural spot-check: importing `EXPANDED_CASE_SUBDIRS` returns the exact 9-element tuple and `ensure_subdir(td, 'tool-logs')` produces only that subdir (no always-empty siblings). |
| 5 | Agent can write, append, enumerate, tree-list, and range-read tool logs via write_artifact, append_artifact, list_artifacts, get_artifact_tree, get_tool_log | ✓ VERIFIED | `tools/re_artifacts.py` exposes all 5 functions (lines 74, 122, 158, 197, 257) and registers them (lines 331-335). Writers compose `confine_to(resolve_case_dir(case_dir), relpath)` (lines 91-92, 134-135). Writers call `ensure_mare_shell_access(resolved_case)` BEFORE the write (lines 110, 146) — D-21 honoured. `get_tool_log` clamps length to `STDOUT_HEAD_KB*4*1024` (1 MB; line 284) and returns paginated `next_offset` + `sha256` (lines 309-320). `get_artifact_tree` honours MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES (1024) + MCP_GATEWAY_ARTIFACT_TREE_MAX_DEPTH (8) (lines 209-210). |
| 6 | MCP Resources expose mare://cases/<case>/tool-logs/<file> for every captured log; tool-name collisions between STATIC wrappers and backend-pass-through hard-fail at gateway startup | ✓ VERIFIED | `tools/resources.py:130-157` walks `EXPANDED_CASE_SUBDIRS` at depth 2 emitting `mare://cases/{case}/{sub}/{child.name}` for every non-hidden file. `tools/collision_check.py::assert_no_collisions` (lines 33-67) uses `await mcp.list_tools()` + `session_state.PINNED_BACKEND.tool_cache` and `sys.exit(78)` (EX_CONFIG) on collision. `app.py:93, 114` invokes `await assert_no_collisions(mcp)` in BOTH lifespan paths AFTER PinnedBackend connect AND BEFORE serving. |

**Score:** 6/6 truths verified at the static + import-time level.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `mcp-gateway/pyproject.toml` | capstone>=5.0.0 + ropper>=1.13.10 pinned | ✓ VERIFIED | lines 17-18 |
| `Dockerfile` | mare-shell UID 700 + acl apt + permission revocations | ✓ VERIFIED | line 53 (`yara upx-ucl qemu-user yq acl \`); line 177 (`useradd -r -u 700 -s /usr/sbin/nologin -d /nonexistent mare-shell`); lines 185-191 (D-07 setfacl revocations on /agent/uploads); lines 289-297 (entrypoint re-apply) |
| `mcp-gateway/tests/fixtures/` | 3 binaries + README + regen sources | ✓ VERIFIED | hello_elf, hello_pe.exe, stripped.o + hello_elf.S, hello_pe.c, stripped.S + README.md present |
| `mcp-gateway/src/mcp_gateway/artifacts_io.py` | `ensure_mare_shell_access` + EXPANDED_CASE_SUBDIRS | ✓ VERIFIED | lines 33-43 (tuple), lines 146-181 (helper with both `-m` and `-d -m` setfacl invocations, RuntimeError on missing/failed); 181 lines total |
| `mcp-gateway/src/mcp_gateway/tools/shell.py` | `run_shell` + `_build_shell_env` + `_RUN_SHELL_ALLOWED_KEYS` | ✓ VERIFIED | 211 lines; frozenset at lines 57-67; build_shell_env at lines 70-108; setpriv argv at lines 111-133; cmd validation at lines 136-150; run_shell at lines 153-206; register at lines 209-211 |
| `mcp-gateway/src/mcp_gateway/tools/re_static.py` | 11 typed wrappers with allowlists + in-proc helpers | ✓ VERIFIED | 491 lines; all 11 tools present and registered |
| `mcp-gateway/src/mcp_gateway/tools/re_artifacts.py` | 5 artifact-control tools | ✓ VERIFIED | 335 lines; all 5 tools present and registered |
| `mcp-gateway/src/mcp_gateway/tools/collision_check.py` | `assert_no_collisions` async function | ✓ VERIFIED | 67 lines; async function with sys.exit(78) |
| `mcp-gateway/src/mcp_gateway/tools/resources.py` | depth-2 walk over EXPANDED_CASE_SUBDIRS + env-var caps | ✓ VERIFIED | 217 lines; imports `EXPANDED_CASE_SUBDIRS` (line 20); depth-2 walk emits `mare://cases/<case>/<subdir>/<file>` (lines 130-157); MCP_GATEWAY_RESOURCE_TREE_MAX_DEPTH cap (line 113) |
| `mcp-gateway/src/mcp_gateway/tools/__init__.py` | register_all_tools includes shell, re_static, re_artifacts | ✓ VERIFIED | lines 30-33 (imports), lines 42-44 (registrations); `collision_check` also imported per Wave 3 plan |
| `mcp-gateway/src/mcp_gateway/app.py` | lifespan invokes assert_no_collisions in correct ordering | ✓ VERIFIED | line 21 (import), line 93 (no-backend path), line 114 (real-backend path); both AFTER PINNED_BACKEND assignment, BEFORE session_manager.run() |
| `mcp-gateway/src/mcp_gateway/tools/backend_passthrough.py` | comment block reflects D-14 | ✓ VERIFIED | line 8 reads `Conflict policy (Phase 7 D-14 -- REVERSES v1.0 "backend wins")`; line 17 references Phase 7 |
| Phase 7 test files | RED-stub coverage that flips GREEN | ✓ VERIFIED | tests/test_run_shell.py, test_re_static.py, test_re_artifacts.py, test_collision_check.py, test_resources_phase7.py, test_acl_available.py all present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `tools/shell.py::run_shell` | `runner.run_tool` | `await run_tool(..., env=_build_shell_env(resolved_case))` | ✓ WIRED | line 200-206; explicit `env=` kwarg (Pitfall 5 honoured) — no `os.environ` inheritance |
| `tools/shell.py::run_shell` | `artifacts_io.ensure_mare_shell_access` | call before subprocess spawn | ✓ WIRED | line 193 |
| `tools/shell.py` | `setpriv --reuid=mare-shell ... -- bash -c <cmd>` | `_build_setpriv_argv` | ✓ WIRED | lines 122-133 (NOT `bash -lc` per D-02) |
| `tools/re_artifacts.py::write_artifact/append_artifact` | `artifacts_io.ensure_mare_shell_access` | call before write | ✓ WIRED | lines 110, 146 |
| `tools/re_artifacts.py` (4 tools) | `artifacts_io.confine_to + case_dirs.resolve_case_dir` | composed path resolution | ✓ WIRED | lines 91-92, 134-135, 174-177, 211, 277-280 |
| `tools/re_static.py` (9 subprocess wrappers) | `runner.run_tool` | `await run_tool(...)` calls | ✓ WIRED | lines 130, 142, 174, 205, 225, 243, 276, 450, 468 |
| `tools/resources.py::_build_resource_list` | `artifacts_io.EXPANDED_CASE_SUBDIRS` | module-level import + iteration | ✓ WIRED | line 20 (import) + line 134 (`for sub in EXPANDED_CASE_SUBDIRS`) |
| `app.py::lifespan` | `tools.collision_check.assert_no_collisions` | await call after PinnedBackend connect, before serve | ✓ WIRED | lines 21, 93, 114 (both lifespan paths) |
| `tools/__init__.py::register_all_tools` | `shell.register / re_static.register / re_artifacts.register` | package import + function calls | ✓ WIRED | lines 30-33 (imports), lines 42-44 (calls) |
| `tools/collision_check.py` | `session_state.PINNED_BACKEND.tool_cache` | module import + attribute read | ✓ WIRED | lines 25, 52-54 |
| `pyproject.toml` | `import capstone, ropper` in `re_static.py` | pip install of mcp-gateway editable | ✓ WIRED | pyproject.toml lines 17-18; `re_static.py` lines 299 (capstone), 379 (ropper); imports succeed at runtime |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `run_shell` return dict | Phase 6 12-key dict | `run_tool` actually spawns the subprocess (Phase 6, shipped) and writes tool-logs/ | ✓ Yes — `await run_tool(...)` is the real Phase-6 chokepoint, not a stub | ✓ FLOWING |
| `re_static.run_*` return dicts | 12-key dict + tool-specific keys (magic, detections, json_output, instructions, gadgets, etc.) | `run_tool` for subprocess wrappers; capstone/ropper python bindings for in-proc | ✓ Yes — subprocess wrappers call real Phase-6 runner; in-proc tools call real capstone.Cs(...).disasm and RopperService(...).loadGadgetsFor; both write real files to hex/ rop/ disassembly/ | ✓ FLOWING |
| `re_artifacts.*` return dicts | bytes_written / files list / tree / log content | Real filesystem writes (`target.write_bytes`, `open(target, 'ab')`), real `iterdir()` walks | ✓ Yes — direct filesystem mutations and reads, not static returns | ✓ FLOWING |
| `tools/resources.py::_build_resource_list` | `out: list[mcp_types.Resource]` | `_list_cases()` reads STATUS_ROOT; `(case_root/sub).iterdir()` reads filesystem | ✓ Yes — dynamic per-call enumeration; no hardcoded fixture | ✓ FLOWING |
| `tools/collision_check.py` | `collisions = gateway_names & backend_names` | `await mcp.list_tools()` + `session_state.PINNED_BACKEND.tool_cache` | ✓ Yes — uses public FastMCP API + Phase 2 backend pinning | ✓ FLOWING |

No HOLLOW or DISCONNECTED artifacts found at the data-flow layer. All 17 Phase 7 tools register and surface through FastMCP (verified below).

### Behavioral Spot-Checks

| # | Behavior | Command / Probe | Result | Status |
|---|----------|----------------|--------|--------|
| 1 | All 17 Phase 7 tools register via FastMCP `register_all_tools` | `uv run python -c "from mcp.server.fastmcp import FastMCP; from mcp_gateway.tools import register_all_tools; ... asyncio.run(mcp.list_tools())"` | total tools: 39; phase 7 registered: 17 (append_artifact, get_artifact_tree, get_tool_log, list_artifacts, run_capstone_disasm, run_die, run_file, run_jq, run_nm, run_objdump, run_rabin2, run_readelf, run_ropper, run_shell, run_xxd, run_yq, write_artifact) | ✓ PASS |
| 2 | `EXPANDED_CASE_SUBDIRS` matches the spec 9-tuple AND `ensure_subdir` is lazy (no always-empty sibling dirs) | `import EXPANDED_CASE_SUBDIRS; ensure_subdir(td, 'tool-logs'); listdir(td) == ['tool-logs']` | EXPANDED_CASE_SUBDIRS correct; only `tool-logs` created — lazy creation confirmed | ✓ PASS |
| 3 | Phase 7 test suite passes (host-runnable subset) | `uv run pytest tests/test_run_shell.py tests/test_re_static.py tests/test_re_artifacts.py tests/test_collision_check.py tests/test_resources_phase7.py tests/test_acl_available.py tests/test_artifacts_io.py -q` | 50 passed, 22 skipped (setfacl/die/rabin2/jq/yq/mare-shell host-absences), 1 failed (test_acl_available — expected on host, documented in deferred-items.md) | ✓ PASS (the 1 fail is the by-design "fail loud on host without acl" assertion) |
| 4 | Full mcp-gateway test suite stays green | `uv run pytest -q` | 240 passed, 29 skipped, 2 failed (test_acl_available — host-by-design; test_mastra_starter — pre-existing unrelated Node.js issue) | ✓ PASS (no Phase 7 regression introduced) |
| 5 | SHELL-03 docstring posture statement | `grep "posture, not isolation" tools/shell.py` | 2 hits (module docstring line 5, function docstring line 160) | ✓ PASS |
| 6 | Dockerfile contains mare-shell UID 700 + acl pkg | `grep useradd Dockerfile`, `grep "acl " Dockerfile` | line 177: `useradd -r -u 700 -s /usr/sbin/nologin -d /nonexistent mare-shell`; line 53: `yara upx-ucl qemu-user yq acl \` | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SHELL-01 | 07-01, 07-07, 07-08 | run_shell w/ case_dir cwd, capture, output cap, hard timeout | ✓ SATISFIED | tools/shell.py:153-206 + Phase 6 run_tool chain |
| SHELL-02 | 07-01, 07-07, 07-08 | mare-shell UID, env whitelist excludes MCP_GATEWAY_TOKEN/API/AWS | ✓ SATISFIED | _RUN_SHELL_ALLOWED_KEYS (lines 57-67), _build_shell_env explicit env (lines 70-108), setpriv argv (lines 122-133), Dockerfile useradd line 177 |
| SHELL-03 | 07-01, 07-07 | docstring "posture, not isolation" | ✓ SATISFIED | tools/shell.py:5 + 160 |
| STATIC-01 | 07-01, 07-06 | run_file | ✓ SATISFIED | re_static.py:125-133 |
| STATIC-02 | 07-01, 07-06 | run_die | ✓ SATISFIED | re_static.py:137-155 |
| STATIC-03 | 07-01, 07-06 | run_xxd + saved to hex/ | ✓ SATISFIED | re_static.py:159-183 (capped to 64 KB; full slice written to hex/) |
| STATIC-04 | 07-01, 07-06 | run_readelf allowlist | ✓ SATISFIED | re_static.py:187-207; _READELF_ALLOWED at line 94 |
| STATIC-05 | 07-01, 07-06 | run_objdump + run_nm modes | ✓ SATISFIED | re_static.py:211-258; _OBJDUMP_MODE_FLAGS line 99, _NM_MODE_FLAGS line 108 |
| STATIC-06 | 07-01, 07-06 | run_rabin2 command allowlist | ✓ SATISFIED | re_static.py:262-285; _RABIN2_ALLOWED line 116 |
| STATIC-07 | 07-01, 07-06 | run_capstone_disasm typed JSON | ✓ SATISFIED | re_static.py:289-362; `instructions: list[{address,mnemonic,op_str,bytes}]` line 341-346 |
| STATIC-08 | 07-01, 07-06 | run_ropper + full list to rop/ | ✓ SATISFIED | re_static.py:366-434; `gadgets` capped at `max_gadgets`, full list dumped to rop/ropper-<rand4>.json line 422-424 |
| STATIC-09 | 07-01, 07-06 | run_jq + run_yq | ✓ SATISFIED | re_static.py:438-470 |
| STATIC-10 | 07-01, 07-03, 07-08 | collision hard-fail at gateway startup | ✓ SATISFIED | tools/collision_check.py + app.py wiring |
| ARTIF-01 | 07-01, 07-05 | lazy subdirs (9 expanded) | ✓ SATISFIED | EXPANDED_CASE_SUBDIRS + ensure_subdir; verified behaviourally (spot-check #2) |
| ARTIF-02 | 07-01, 07-02, 07-05 | write_artifact + append_artifact with confine_to | ✓ SATISFIED | re_artifacts.py:74-154 |
| ARTIF-03 | 07-01, 07-05 | list_artifacts + get_artifact_tree | ✓ SATISFIED | re_artifacts.py:158-253 |
| ARTIF-04 | 07-01, 07-05 | get_tool_log paginated | ✓ SATISFIED | re_artifacts.py:257-320; clamp to 1 MB; next_offset + eof + sha256 |
| ARTIF-05 | 07-01, 07-04, 07-08 | mare://cases/<case>/tool-logs/<file> resources | ✓ SATISFIED | tools/resources.py:130-157 (depth-2 walk over EXPANDED_CASE_SUBDIRS); ⚠️ requires live MCP client to confirm wire-level visibility (deferred to human verification item 3) |

**All 18 Phase 7 requirement IDs are accounted for across the 8 plans. No orphans.** No plan-claimed IDs are missing from REQUIREMENTS.md; the REQUIREMENTS.md TOC at lines 137-154 lists every Phase 7 ID and shows them as Phase-7 owned.

### Anti-Patterns Found

| File | Line(s) | Pattern | Severity | Impact |
|------|---------|---------|----------|--------|
| `tools/re_static.py` | 397-399 | `except Exception: pass` in `run_ropper` `applyFilter` | ℹ️ Info | Intentionally swallows ropper filter compile errors so a bad regex from the agent doesn't crash the whole tool. Documented inline as `# ropper filter compile errors are AttributeError/ValueError`. Not a hidden stub. |
| `tools/re_static.py` | 280-282 | `except json.JSONDecodeError: result["json_output"] = None` | ℹ️ Info | rabin2 emits malformed JSON for some commands; tool falls back to setting parse_error key — explicit, not a silent stub. |
| `tools/re_static.py` | 351 | `log_relpath = "(in-process; no case_dir)"` default for capstone when `case_dir is None` | ℹ️ Info | Acceptable — capstone wrapper allows `case_dir=None` per D-30 ("accepted for uniformity"); skips artifact dump deliberately. |

No blockers, no warnings. All grep-flagged constructs are deliberate and documented.

### Human Verification Required

3 items require human / container / live-MCP-client testing — captured in YAML frontmatter:

1. **Dockerfile rebuild produces mare-shell UID=700 and ACL revocations**
   - Test: `docker compose build && docker compose run --rm gateway-agent id mare-shell`
   - Expected: `uid=700(mare-shell) gid=700(mare-shell)`; `getfacl /agent/uploads` shows user:mare-shell:r-x access + default ACL
   - Why human: Host has no `mare-shell` user (test_run_shell.py SKIPS with that reason); container build is the integration point.

2. **D-35 100 MB /dev/urandom slow test passes inside the container**
   - Test: `docker compose run --rm gateway-agent uv run pytest -m slow tests/test_run_shell.py::test_run_shell_100mb_urandom`
   - Expected: PASS in <60s; full setpriv → mare-shell → bash chain with output cap + capture intact
   - Why human: Host lacks `setfacl`, test is SKIPPED locally.

3. **MCP Resources visible to remote MCP client (Claude Code or mastra)**
   - Test: Connect Claude Code via `.mcp.json`, run a captured tool (run_shell or run_xxd), then issue `resources/list`
   - Expected: Both v1.0 depth-1 artifacts AND new `mare://cases/<case>/<subdir>/<file>` entries (e.g., `mare://cases/<case>/tool-logs/<ts>-run_shell-<r4>.txt`) appear
   - Why human: Live MCP wire integration; mastra e2e suite currently fails locally for an unrelated Node.js module resolution issue.

### Gaps Summary

No goal-blocking gaps. Every roadmap success criterion is supported by shipped code; every PLAN must-have artifact exists at the expected path with the expected interfaces; every key link is wired; every data path flows real data; every requirement ID is satisfied at the static + import-time level.

The remaining unknowns are intrinsically out of reach of the host environment (Dockerfile correctness needs `docker build`; D-35 100 MB chokepoint needs setfacl; MCP-wire resource visibility needs a live client). They are captured as `human_verification` items above, are pre-flagged in the phase's own 07-VALIDATION.md "Manual-Only Verifications" table, and are documented in `deferred-items.md`.

---

_Verified: 2026-05-13T05:04:48Z_
_Verifier: Claude (gsd-verifier)_
