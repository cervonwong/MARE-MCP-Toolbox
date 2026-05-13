---
phase: 07-run-shell-typed-static-wrappers-re-artifacts
plan: 06
subsystem: mcp-gateway/tools
tags:
  - typed-wrappers
  - re-static
  - capstone
  - ropper
  - allowlist
  - in-process
requires:
  - artifacts_io.confine_to
  - artifacts_io.ensure_subdir
  - runner.run_tool
  - runner.STDOUT_HEAD_KB
  - tools.case_dirs.resolve_case_dir
  - tools.samples.resolve_sample
provides:
  - tools.re_static.register
  - tools.re_static.run_file
  - tools.re_static.run_die
  - tools.re_static.run_xxd
  - tools.re_static.run_readelf
  - tools.re_static.run_objdump
  - tools.re_static.run_nm
  - tools.re_static.run_rabin2
  - tools.re_static.run_capstone_disasm
  - tools.re_static.run_ropper
  - tools.re_static.run_jq
  - tools.re_static.run_yq
affects:
  - mcp-gateway test suite (test_re_static.py flips Wave 0 RED -> GREEN)
tech-stack:
  added:
    - capstone (already in pyproject.toml from D-20; first consumer)
    - ropper (already in pyproject.toml from D-20; first consumer)
  patterns:
    - Module-level coroutines + `register(mcp)` decorator wrapper
    - D-19 `_inproc_result` 12-key shape helper for in-process tools
    - Allowlist as frozenset / dict-keyed enum mapping
    - Per-test autouse fixture to monkeypatch import-time-bound globals
key-files:
  created:
    - mcp-gateway/src/mcp_gateway/tools/re_static.py
  modified:
    - mcp-gateway/tests/test_re_static.py
decisions:
  - "Used the module-level coroutines + register() wrapper pattern from re_artifacts.py (Plan 07-05) so unit tests import the wrappers directly without going through FastMCP's tool-manager."
  - "Added an autouse `_sync_samples_roots` fixture to test_re_static.py (Rule 3 deviation): `samples.STATUS_ROOT` and `samples.EXAMPLES_ROOT` are bound at import-time and don't pick up per-test env mutations; the fixture monkeypatches both module attributes + `ALLOWED_PREFIXES` per test."
  - "Added `_require_tool_or_skip(tool)` helper (Rule 3 deviation): die / rabin2 / jq / yq are not installed on the executor host. Container image (Kali) ships them; tests skip cleanly on dev hosts. Allowlist-violation tests do NOT use the guard (they assert pre-spawn ValueError, no subprocess needed)."
  - "ropper gadget extraction uses defensive `_gadget_to_dict` helper that tolerates missing `lines` / `bytes` attributes — different ropper versions expose slightly different Gadget shapes."
metrics:
  duration: 4min
  completed: 2026-05-13
---

# Phase 7 Plan 6: Typed Static-RE Wrappers (re_static.py) Summary

`mcp-gateway/src/mcp_gateway/tools/re_static.py` (491 LoC) delivers the eleven D-18 typed RE wrappers — 9 subprocess wrappers (`run_file`, `run_die`, `run_xxd`, `run_readelf`, `run_objdump`, `run_nm`, `run_rabin2`, `run_jq`, `run_yq`) layered over Phase 6's `run_tool` chokepoint, plus 2 in-process wrappers (`run_capstone_disasm`, `run_ropper`) that produce the same 12-key result shape via `_inproc_result` (D-19).

## What Changed

- **NEW** `mcp-gateway/src/mcp_gateway/tools/re_static.py` (491 LoC)
  - 11 module-level `async def` wrappers (one per D-18 row)
  - 5 module-level constants: `_STDOUT_HEAD_BYTES`, `_READELF_ALLOWED`, `_OBJDUMP_MODE_FLAGS`, `_NM_MODE_FLAGS`, `_RABIN2_ALLOWED`, `_XXD_HEX_DUMP_CAP`
  - 4 module-level helpers: `_rand4`, `_utc_ts`, `_inproc_result`, `register(mcp)`
- **MODIFIED** `mcp-gateway/tests/test_re_static.py`
  - Added autouse `_sync_samples_roots` fixture (monkeypatches `samples.STATUS_ROOT`, `samples.EXAMPLES_ROOT`, `samples.ALLOWED_PREFIXES` per test)
  - Added `_require_tool_or_skip(tool)` helper for host-missing tools
  - Added skip guards to `test_run_die_pe`, `test_run_rabin2_info`, `test_run_jq_artifact`, `test_run_yq_artifact`

## Allowlist Sizes (D-18 verbatim)

| Allowlist | Size | Members |
|-----------|------|---------|
| `_READELF_ALLOWED` | 10 | `{-h, -l, -d, -S, -s, -r, -a, -W, -n, -V}` |
| `_OBJDUMP_MODE_FLAGS` | 5 | `{headers, disasm, syms, relocs, all}` |
| `_NM_MODE_FLAGS` | 4 | `{all, dynamic, undefined, defined}` |
| `_RABIN2_ALLOWED` | 8 | `{i, is, iI, ii, iE, iz, zz, iL}` |

`_READELF_ALLOWED` extended beyond D-18's locked 8-member core (`{-h, -l, -d, -S, -s, -r, -a, -W}`) by 2 (`-n` notes, `-V` version info) per the plan's Claude's-Discretion clause: "Whether `run_readelf`'s allowlist ... includes a couple more harmless flags (`-n` for notes, `-V` for version info) is the planner's call."

## Test Outcome

`tests/test_re_static.py`: **10 passed, 4 skipped on host**

| # | Test | Status |
|---|------|--------|
| 1 | `test_run_file_elf` | PASSED |
| 2 | `test_run_die_pe` | SKIPPED (host lacks `die`) |
| 3 | `test_run_xxd_bounded` | PASSED |
| 4 | `test_run_readelf_rejects_disallowed_flag` | PASSED |
| 5 | `test_run_readelf_header` | PASSED |
| 6 | `test_run_objdump_headers` | PASSED |
| 7 | `test_run_objdump_rejects_invalid_mode` | PASSED |
| 8 | `test_run_nm_all` | PASSED |
| 9 | `test_run_rabin2_rejects_invalid_command` | PASSED |
| 10 | `test_run_rabin2_info` | SKIPPED (host lacks `rabin2`) |
| 11 | `test_run_capstone_disasm_x86_64` | PASSED |
| 12 | `test_run_ropper_x86_64` | PASSED |
| 13 | `test_run_jq_artifact` | SKIPPED (host lacks `jq`) |
| 14 | `test_run_yq_artifact` | SKIPPED (host lacks `yq`) |

The 4 skipped tests will PASS unchanged inside the Kali container image once Phase 7 Wave 3 lands the Dockerfile updates that install `die`, `rabin2`, `jq`, `yq` (already present in the v1.0 Kali Dockerfile apt list per CLAUDE.md, but the executor host is bare Ubuntu/WSL).

Acceptance criteria from the plan all pass:

- 1× `def register(mcp: FastMCP)` definition
- 11× `mcp.tool()(...)` registration calls
- 11× `async def run_<name>` wrappers
- 4× `_inproc_result` references (1 def + 3 call sites — capstone, ropper, plus a docstring/helper signature)
- 9× `slug="run_<subprocess>"` strings
- 1× `ensure_subdir(resolved_case, "hex")`, 1× `ensure_subdir(resolved_case, "rop")`, 1× `ensure_subdir(resolved_case, "disassembly")`
- 0× `shell=True`
- LoC = 491 (target: ~600)

## Capstone / Ropper Import Smoke

```
$ uv run python -c "import capstone; print(capstone.__version__)"
5.0.7

$ uv run python -c "from ropper import RopperService; print('ropper ok')"
ropper ok
```

Both bindings install cleanly via D-20's pyproject.toml pins (`capstone>=5.0.0`, `ropper>=1.13.10`). The capstone disasm test (`test_run_capstone_disasm_x86_64`) confirms the `0x90 0xc3` (NOP + RET) decode returns `[{mnemonic: nop}, {mnemonic: ret}]` with the full D-19 12-key shape. The ropper test (`test_run_ropper_x86_64`) confirms gadget extraction from the `hello_elf` fixture returns a capped gadget list and writes the full list to `<case>/rop/ropper-<ts>-<rand4>.json`.

## Deviations from Plan

### Rule 3 — Blocking Issue Auto-fixes

**1. [Rule 3] Module-level coroutines instead of nested-in-register**
- **Found during:** Task 1 first test run
- **Issue:** The plan's <action> block showed all 11 wrappers nested inside `register(mcp)`, but the Wave-0 RED tests do `from mcp_gateway.tools.re_static import run_file` — they can't import functions that only exist after `register(mcp)` is called.
- **Fix:** Promoted all 11 wrappers + 2 helpers to module level (matching the pattern already used by `tools/re_artifacts.py` from Plan 07-05). `register(mcp)` now just decorates each via `mcp.tool()(func_name)`.
- **Files modified:** `mcp-gateway/src/mcp_gateway/tools/re_static.py`
- **Commit:** d3f6515

**2. [Rule 3] Autouse fixture for import-time-bound `samples.STATUS_ROOT` / `EXAMPLES_ROOT`**
- **Found during:** First post-implementation pytest run (test #2 onward failed with "case_dir must be under <stale STATUS_ROOT>")
- **Issue:** `samples.STATUS_ROOT` and `samples.EXAMPLES_ROOT` are read at module import from `MCP_GATEWAY_STATUS_DIR` / `MCP_GATEWAY_EXAMPLES_DIR` env vars. The `tmp_status_dir` conftest fixture monkeypatches the env var per test, but the module-level `STATUS_ROOT` stays bound to the first test's value. `tools.case_dirs.resolve_case_dir` and `samples.resolve_sample` both read these module attributes directly, so they fail on test #2 onward. Additionally, the FIXTURES path (`tests/fixtures/`) is not under any allowed prefix, so `resolve_sample` would reject the fixture binaries.
- **Fix:** Added autouse `_sync_samples_roots` fixture that monkeypatches `samples.STATUS_ROOT` to `tmp_status_dir`, `samples.EXAMPLES_ROOT` to `FIXTURES`, and `samples.ALLOWED_PREFIXES` to `(UPLOADS_ROOT, FIXTURES, tmp_status_dir)` per test. Mirrors the pattern from `test_re_artifacts.py` (Plan 07-05 deviation 3).
- **Files modified:** `mcp-gateway/tests/test_re_static.py`
- **Commit:** d3f6515

**3. [Rule 3] Skip-on-no-tool helper for host-missing external binaries**
- **Found during:** Second post-implementation pytest run
- **Issue:** Tests for `run_die`, `run_rabin2`, `run_jq`, `run_yq` spawn external tools (`die`, `rabin2`, `jq`, `yq`) that are present in the Kali container image but NOT on this executor host. Tests hit `FileNotFoundError: [Errno 2] No such file or directory`.
- **Fix:** Added `_require_tool_or_skip(tool)` helper using `shutil.which(tool)`. Inserted at the top of the 4 host-missing tool tests. Allowlist-violation tests do NOT use the guard because they assert `ValueError` BEFORE any subprocess spawn (acceptance_criteria already lists these specifically).
- **Files modified:** `mcp-gateway/tests/test_re_static.py`
- **Commit:** d3f6515

## Threat Coverage Confirmation

Every `<threat_model>` row with disposition=mitigate has a corresponding test or code-level mitigation:

| Threat ID | Test or mitigation |
|-----------|--------------------|
| T-7-W2B-01 (argv injection via mode) | `test_run_objdump_rejects_invalid_mode` + frozenset/dict membership checks on every wrapper |
| T-7-W2B-02 (sections=["-Z"] disallowed flag) | `test_run_readelf_rejects_disallowed_flag` |
| T-7-W2B-05 (jq/yq exfil non-confined files) | `confine_to(resolved_case, artifact_path)` in `run_jq` / `run_yq` |
| T-7-W2B-06 (capstone case_dir traversal) | `resolve_case_dir(case_dir)` precedes `ensure_subdir` in `run_capstone_disasm` |
| T-7-W2B-07 (future `shell=True`) | `grep -c 'shell=True' = 0` acceptance criterion |
| T-7-W2B-08 (run_xxd offset/length validation) | Eager `ValueError` for `offset < 0` and `length <= 0` before any subprocess spawn |

## Self-Check: PASSED

Files exist:
- FOUND: `mcp-gateway/src/mcp_gateway/tools/re_static.py`
- FOUND: `mcp-gateway/tests/test_re_static.py` (modified)

Commits exist:
- FOUND: d3f6515 — `Add tools/re_static.py with 11 typed RE wrappers (Phase 07-06)`
