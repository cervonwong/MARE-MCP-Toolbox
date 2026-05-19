---
phase: 10-extraction-tier
plan: 02
subsystem: extraction-primitive
tags: [extraction, mcp-gateway, jobs, unblob, binwalk3, primitive, leaf-tier]

requires:
  - phase: 06-retoolrunner-artifacts-io-foundation
    provides: artifacts_io leaf helpers (ensure_subdir, confine_to) reused by extraction_dir
  - phase: 09-background-job-system
    provides: JobToolSpec + register_job_tool + JOB_TOOL_REGISTRY; extraction.py registers unblob + binwalk_extract at module-import time
  - phase: 10-extraction-tier (Plan 01)
    provides: 13 RED-stub extraction test files + Dockerfile binwalk3 migration
provides:
  - mcp_gateway.extraction module (leaf-tier primitive) with the locked 7-function public surface, 2 pure argv builders, 2 JobToolSpec entries auto-registered at import, and 4 env-var module constants validated fail-fast
  - Plan 03's monitor implementation (sibling asyncio task) can now import MAX_EXTRACT_BYTES + EXTRACT_MONITOR_INTERVAL_S + update_meta + quarantine_symlinks
  - Plan 04's MCP surface (tools/extract.py) can now import extraction_dir + write_upload + enumerate_extractions and rely on unblob/binwalk_extract job specs being registered
affects: [10-03-PLAN, 10-04-PLAN, 10-05-PLAN]

tech-stack:
  added: []
  patterns:
    - "JobToolSpec registration at module-import time (matches jobs.py:335/352/382)"
    - "Local import of mcp_gateway.tools.samples inside argv builders (matches jobs.py:363 capa pattern) -- avoids circular import via tools/__init__"
    - "Atomic JSON write via tempfile in same dir + os.rename + os.fsync (Pitfall 6 mitigation)"
    - "os.walk(followlinks=False) + os.readlink + os.unlink for symlink quarantine (Pitfall A7 mitigation)"
    - "Pure-function argv builders gated by extraction_path.is_relative_to(case_dir) defense-in-depth check"
    - "Argv '--' separator before sample path (defense-in-depth against attacker-controlled sample names starting with '-')"

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/extraction.py
  modified: []

key-decisions:
  - "Module placed at the same architectural tier as runner.py/sessions.py/jobs.py: zero mcp.server.fastmcp imports, only local tools.samples import inside argv builders"
  - "binwalk3 `depth` kwarg retained in schema for forward compatibility but silently ignored in argv (binwalk3 has no -d/--depth flag per Assumption A2)"
  - "`--` argv separator included in both argv builders (Open Question #5 resolved YES) -- defense-in-depth against sample paths that begin with `-`"
  - "Plan 02 deliberately EXCLUDES start_extract_monitor (Plan 03 owns it) so the concurrency-sensitive sibling-task code can be reviewed in isolation"
  - "extraction_dir uses mkdir(exist_ok=False) followed by resolve(strict=True) -- Pitfall 8 mitigation guarantees no race with pre-existing symlinks"

requirements-completed: []  # EXTR-01..EXTR-06 are PRIMITIVE-LAYER-SATISFIED by this plan but the MCP-surface requirements (run_unblob/run_binwalk/list_extracted_files/promote_extracted_sample/run_upx_*) ship in Plan 04. Marking complete here would be premature.

duration: 4min
completed: 2026-05-19
---

# Phase 10 Plan 02: Extraction Primitive Module Summary

**Leaf-tier primitive `mcp_gateway.extraction` (407 LoC) delivering extraction-dir minting, _mare_meta.json sidecar I/O, recursive symlink quarantine, atomic re-upload, two pure-function argv builders (unblob v26+, binwalk3 v3.1+), and two JobToolSpec entries auto-registered at module import.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-19T06:12:02Z
- **Completed:** 2026-05-19T06:16:00Z (approx.)
- **Tasks:** 1
- **Files created:** 1
- **Files modified:** 0

## Accomplishments

- Locked the Plan 02 public surface verbatim per the plan's `<interfaces>` block: 7 helpers + 2 argv builders + 4 env-var module constants + 2 JobToolSpec entries.
- Flipped 20 of the Plan 01 Wave 0 RED-stub tests to GREEN on first run (collection + execution): `test_extraction_dir.py` (5), `test_meta_sidecar.py` (4), `test_quarantine_symlinks.py` (3), `test_job_specs_unblob.py` (4), `test_job_specs_binwalk_extract.py` (4).
- Registered `unblob` and `binwalk_extract` JobToolSpecs into `JOB_TOOL_REGISTRY` at module-import time (verified: `sorted(JOB_TOOL_REGISTRY.keys()) == ['_log_burst_probe', '_sleep_probe', 'binwalk_extract', 'capa', 'unblob']` after `import mcp_gateway.extraction`).
- Validated fail-fast on bad env vars: `MCP_GATEWAY_MAX_EXTRACT_MB=invalid python -c "from mcp_gateway import extraction"` raises `RuntimeError` at import time.
- Zero FastMCP imports, zero module-top asyncio imports, zero `mcp_gateway.tools.*` imports except 3 LOCAL `samples` imports inside argv builders + write_upload (matches jobs.py:363 capa pattern).

## Task Commits

1. **Task 1: Implement extraction.py -- env constants, helpers, argv builders, JobToolSpec registration** -- `cd8fdc3`

## Public Surface Exported

**Env-var module constants (D-18, fail-fast at import):**

| Constant | Env var | Default | Purpose |
|----------|---------|---------|---------|
| `MAX_EXTRACT_MB` | `MCP_GATEWAY_MAX_EXTRACT_MB` | `4096` | Archive-bomb byte cap (in MB) |
| `EXTRACT_MONITOR_INTERVAL_S` | `MCP_GATEWAY_EXTRACT_MONITOR_INTERVAL_S` | `5.0` | Plan 03 monitor poll interval (s) |
| `MAX_FILES_PER_EXTRACTION` | `MCP_GATEWAY_LIST_EXTRACT_FILES_PER_EXTRACTION` | `5000` | Plan 04 `list_extracted_files` row cap |
| `MAX_EXTRACT_BYTES` | (derived) | `MAX_EXTRACT_MB * 1024 * 1024` = `4294967296` | Plan 03 monitor cap (in bytes) |

**Helpers (7 locked public functions):**

- `extraction_dir(case_dir, engine)` -- mints `extracted/<engine>-<UTC>Z-<rand4>/` (D-07); engine ∈ {binwalk, unblob, upx}; `mkdir(exist_ok=False)` + `resolve(strict=True)` (Pitfall 8).
- `quarantine_symlinks(extraction_dir)` -- recursive `os.walk(followlinks=False)` sweep; writes 6-line `.symlink-target.txt` sentinels (D-15/D-16); idempotent; returns `(count, list_of_rel_paths)`.
- `write_meta(extraction_dir, payload)` -- atomic JSON write via tempfile + `os.rename` (Pitfall 6).
- `update_meta(extraction_dir, patch)` -- shallow-merge + atomic rewrite; returns merged dict.
- `read_meta(extraction_dir)` -- json.loads `_mare_meta.json`; raises FileNotFoundError if absent.
- `enumerate_extractions(case_dir)` -- depth-1 walk of `<case_dir>/extracted/*` matching `^(binwalk|unblob|upx)-[0-9TZ]+-[0-9a-f]{4}$`; per-extraction dict including engine, status, exit_code, job_id, symlinks_quarantined, cap_exceeded, plus internal `_dir_abs` + `_meta`.
- `write_upload(child_path, target_basename)` -- streaming hash + atomic `shutil.move` into `<UPLOADS_ROOT>/<sha256>/<basename>`; idempotent on dedup; reuses `uploads._is_invalid_filename` + `uploads.MAX_BYTES`.

**Pure argv builders (D-12, 2 functions):**

- `_build_unblob_argv(case_dir, kwargs) -> list[str]` (unblob v26+ CLI; LOCAL import of `samples`; `extraction_path.is_relative_to(case_dir)` defense-in-depth; `depth ∈ [1, 16]`).
- `_build_binwalk_extract_argv(case_dir, kwargs) -> list[str]` (binwalk3 v3.1+ CLI; `depth` kwarg accepted but IGNORED per Assumption A2; `matryoshka=True` default inserts `-M`).

**JobToolSpec entries (D-11, registered at module import):**

- `_UNBLOB_SPEC` (`name="unblob"`, `default_timeout_s=3600.0`, `progress_parser=None`, kwargs: case_dir/sample/extraction_dir/depth)
- `_BINWALK_EXTRACT_SPEC` (`name="binwalk_extract"`, `default_timeout_s=1800.0`, `progress_parser=None`, kwargs: case_dir/sample/extraction_dir/depth/matryoshka)

## Argv Shapes (Verbatim)

**Unblob:**
```
unblob --report <extraction_dir>/report.json -e <extraction_dir> -d <depth> -- <sample>
```

**Binwalk (matryoshka=True default):**
```
binwalk -e -M -C <extraction_dir> -l <extraction_dir>/binwalk-report.json -q -- <sample>
```

**Binwalk (matryoshka=False):**
```
binwalk -e -C <extraction_dir> -l <extraction_dir>/binwalk-report.json -q -- <sample>
```

## JOB_TOOL_REGISTRY Confirmation

```
>>> from mcp_gateway import extraction
>>> from mcp_gateway.jobs import JOB_TOOL_REGISTRY
>>> sorted(JOB_TOOL_REGISTRY.keys())
['_log_burst_probe', '_sleep_probe', 'binwalk_extract', 'capa', 'unblob']
```

Both `unblob` and `binwalk_extract` are present after a single `import mcp_gateway.extraction`.

## RED -> GREEN Flip Confirmation

Before this plan: `pytest tests/extraction/test_extraction_dir.py tests/extraction/test_meta_sidecar.py tests/extraction/test_quarantine_symlinks.py tests/extraction/test_job_specs_unblob.py tests/extraction/test_job_specs_binwalk_extract.py` -> **20 failed, ImportError**.

After this plan: same command -> **20 passed**.

The Plan 01 stub bodies (`assert True`) all execute now that `from mcp_gateway import extraction` succeeds. Plan 05 will replace the stubs with behavioural assertions.

## Acceptance Criteria Self-Check

| Criterion | Result |
|-----------|--------|
| `python -c "from mcp_gateway import extraction"` succeeds | PASS |
| `JOB_TOOL_REGISTRY` contains `unblob` + `binwalk_extract` | PASS |
| `MAX_EXTRACT_BYTES == 4096*1024*1024` | PASS (4294967296) |
| `grep -c 'from mcp.server.fastmcp' extraction.py == 0` | PASS |
| `grep -cE '^import asyncio\|^from asyncio' extraction.py == 0` | PASS |
| 9 required functions defined | PASS (grep -cE returns 9) |
| 2 `register_job_tool` calls | PASS |
| `--` separator count >= 2 | PASS (returned 4) |
| `followlinks=False` count >= 1 | PASS (returned 3) |
| `os.rename`/`shutil.move` count >= 2 | PASS (returned 2) |
| Env-var fail-fast on bad value | PASS (RuntimeError raised) |
| Plan 01 RED-stub tests collect cleanly | PASS (20 collected, 20 passed) |

## Deviations from Plan

None of substance. Implementation matches the action-block skeleton verbatim. Minor mechanical differences from the plan's elided skeleton:

- **Module length:** 407 LoC vs plan target 280-380 LoC. Driver: module-level docstrings on every public function (LEAF-discipline self-documentation) + the verbatim multi-line symlink-quarantine sentinel body. Functionally identical; no extra logic beyond what the action block requested.
- **`re` import:** Promoted to a normal `import re` at module top rather than the plan's `__import__("re")` trick for `_DIRNAME_RE`. The `__import__` pattern was useful only when avoiding stdlib imports for a specific test invariant; we already need `re` for the dir-name regex and there is no negative-grep gate against `import re`. Cleaner, no impact on test invariants.

No Rule 1/2/3/4 deviations triggered.

## Threat-Register Mitigations Implemented

| Threat ID | Mitigation in code |
|-----------|-------------------|
| T-10-02-01 (argv injection via sample) | `--` separator before sample in both argv builders (4 occurrences); `resolve_sample` canonicalisation via LOCAL import |
| T-10-02-02 (argv injection via case_dir / extraction_dir) | `extraction_path.is_relative_to(case_dir)` check in both argv builders (ValueError on traversal) |
| T-10-02-03 (symlink-extraction host-file read) | `os.walk(followlinks=False)` + `.symlink-target.txt` sentinel + `os.unlink` (D-15/D-16 verbatim) |
| T-10-02-04 (meta JSON race) | `_atomic_write_json`: tempfile in same dir + `os.fsync` + `os.rename` (POSIX-atomic) |
| T-10-02-05 (promotion path-traversal) | `write_upload` calls `_is_invalid_filename(target_basename)` from `uploads.py` |
| T-10-02-06 (archive bomb DoS) | `MAX_EXTRACT_BYTES` constant defined for Plan 03's monitor to import; bad value -> RuntimeError at import |
| T-10-02-07 (extraction_dir symlink race) | `mkdir(parents=False, exist_ok=False)` + `target.resolve(strict=True)` after mkdir |

## Self-Check: PASSED

- `mcp-gateway/src/mcp_gateway/extraction.py` exists (FOUND, 407 LoC)
- Commit `cd8fdc3` in `git log` (FOUND)
- Module imports cleanly with all 4 env constants + 2 JobToolSpecs registered (FOUND)
- 20 of 20 target RED-stub tests now PASS (FOUND)
- All 12 acceptance-criteria grep/import gates PASS (FOUND)

---
*Phase: 10-extraction-tier*
*Plan: 02 (Wave 1 primitive)*
*Completed: 2026-05-19*
