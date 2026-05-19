---
phase: 09-background-job-system
plan: 04
subsystem: jobs-nyquist-test-suite
tags: [jobs, tests, nyquist, verification, wave-0]
dependency_graph:
  requires:
    - mcp_gateway.jobs (Plan 01 -- primitive layer)
    - mcp_gateway.tools.jobs (Plan 02 -- MCP surface)
    - mcp_gateway.app.lifespan (Plan 03 -- wiring + JOB_REGISTRY slot)
  provides:
    - mcp-gateway/tests/jobs/ -- 18 test files (1 conftest + 16 unit/integration + 1 slow capa) + 1 package marker
    - Wave 0 Nyquist sign-off (every JOBS-XX requirement, every SC-1..SC-6, every D-XX behavior under regression test)
    - VALIDATION.md nyquist_compliant=true + wave_0_complete=true
  affects:
    - Phase 10 (extraction-mcp) -- inherits the same Wave-0 test scaffolding pattern + slow-mark convention
    - Phase 11 (dynamic-mode) -- can rely on JOBS-01..07 behavioural invariants under regression

tech_stack:
  added: []  # no new deps; pytest 8 + pytest-asyncio (mode=auto) already configured
  patterns:
    - "Module-attribute access via `from mcp_gateway import jobs` so importlib.reload(jobs) propagates"
    - "registry_factory fixture: env-override + dual-module reload (`jobs` + `tools.jobs`) with finalizer to restore"
    - "FakeContext double for D-16 Tier-2 ctx.report_progress with session_id field"
    - "Synthetic JobToolSpec built per-test (progress_parser closure on stderr `printf >&2` line)"
    - "_require_capa_or_skip helper (shutil.which-based, mirror of Phase 8 _require_r2_or_skip)"
    - "case_dir_fixture monkeypatches samples.STATUS_ROOT (case_dirs.resolve_case_dir reads via module-attr)"

key_files:
  created:
    - mcp-gateway/tests/jobs/__init__.py
    - mcp-gateway/tests/jobs/conftest.py
    - mcp-gateway/tests/jobs/test_spec_validation.py
    - mcp-gateway/tests/jobs/test_registry_lifecycle.py
    - mcp-gateway/tests/jobs/test_start_tool_job.py
    - mcp-gateway/tests/jobs/test_lifecycle_status.py
    - mcp-gateway/tests/jobs/test_get_tool_job.py
    - mcp-gateway/tests/jobs/test_list_tool_jobs.py
    - mcp-gateway/tests/jobs/test_cancel_grace.py
    - mcp-gateway/tests/jobs/test_timeout.py
    - mcp-gateway/tests/jobs/test_log_cap.py
    - mcp-gateway/tests/jobs/test_disconnect_200ms.py
    - mcp-gateway/tests/jobs/test_progress.py
    - mcp-gateway/tests/jobs/test_errors.py
    - mcp-gateway/tests/jobs/test_lru_retention.py
    - mcp-gateway/tests/jobs/test_docstring_disclaimer.py
    - mcp-gateway/tests/jobs/test_terminal_snapshot_json.py
    - mcp-gateway/tests/jobs/test_lifespan_integration.py
    - mcp-gateway/tests/jobs/test_capa_integration.py
  modified:
    - .planning/phases/09-background-job-system/09-VALIDATION.md (frontmatter flipped to nyquist_compliant=true + Wave 0 Actuals table)

decisions:
  - "Test-tool spec for D-16 progress wired as a per-test synthetic JobToolSpec (`_progress_test_probe`) using `progress_parser=lambda line: (5,10,'halfway') if b'PROGRESS' in line else None` -- pattern is paste-ready for future Phase 10/11 progress-emitting tools"
  - "Rule 1 -- jsonschema-absence test rewritten from `pytest.raises(ModuleNotFoundError)` to `'import jsonschema' not in inspect.getsource(jobs)` because mcp SDK transitively installs jsonschema; the Q3 invariant is 'jobs.py does NOT import jsonschema' (semantic equivalence preserved)"
  - "Rule 3 -- conftest.registry_factory now reloads BOTH `mcp_gateway.jobs` AND `mcp_gateway.tools.jobs` when env-override is used (and a finalizer restores both after the test) because tools.jobs imports JobNotFound etc. by name at module load; without the dual-reload, post-reload `except JobNotFound` in tools/jobs.py would miss the new class object and exception would escape (Phase 9 D-15 'tools never raise' contract upheld)"
  - "Rule 3 -- test_lifespan_integration.py also sets MCP_GATEWAY_TOKEN_FILE to tmp_path because auth.load_or_generate_token() defaults to /agent/.mcp-gateway-token which is unwritable on dev host (Phase 7 setfacl-style host-vs-container divergence)"
  - "test_capa_integration.py uses /bin/ls bytes as a 'tiny ELF' sample (copied into case_dir_fixture/sample.bin) -- ls is universally present, ELF-magic-valid, and capa accepts non-malware binaries; on host where capa is missing the test SKIPs cleanly via _require_capa_or_skip"
  - "case_dir_fixture returns the unresolved Path (not str(realpath)) because case_dirs.resolve_case_dir does its own os.path.realpath canonicalization -- handing it the unresolved tmp_path string lets the test exercise the same realpath roundtrip the production code does"

metrics:
  duration: ~11 min
  completed: "2026-05-19T01:57:44Z"
  tasks: 3
  files_touched: 20
  tests_added: 66 non-slow + 1 slow (capa)
  full_suite_runtime: ~31s (66 non-slow) / 0s (1 slow skipped on host)
---

# Phase 09 Plan 04: Wave 0 Nyquist Test Suite Summary

**One-liner:** 17 new test files + 1 conftest + 1 package marker land the Wave 0 Nyquist regression suite for Phase 9 -- every JOBS-XX requirement, every D-XX behavior, every SC-1..SC-6 success criterion encoded as 66 fast tests + 1 slow capa smoke (skips cleanly on dev host).

## What Was Built

### Task 1 — Wave 0 scaffolding (package marker + conftest)

- `mcp-gateway/tests/jobs/__init__.py` — empty file; package marker for `from tests.jobs.conftest import FakeContext, _require_capa_or_skip` cross-import
- `mcp-gateway/tests/jobs/conftest.py` — shared fixtures:
  - `_require_capa_or_skip()` — `shutil.which('capa')` guard (mirrors Phase 8 `_require_r2_or_skip`)
  - `case_dir_fixture` — creates `tmp_path/status/999-test-case/` and monkeypatches `samples.STATUS_ROOT`
  - `registry_factory` — yields fresh `BackgroundJobRegistry`; optional `env={...}` arg reloads `jobs` + `tools.jobs` modules with monkeypatched env constants; finalizer restores
  - `FakeContext` class + `fake_ctx` fixture for D-16 Tier-2 progress tests
- `test_tool_list.py` was already bumped in Plan 03 — no edit needed in Plan 04

### Task 2 — 17 Wave-0 test files (one per VALIDATION.md Wave 0 row)

| File | Tests | Behavior under regression |
|------|-------|---------------------------|
| `test_spec_validation.py` | 10 | Q3 hand-rolled validator: integer min/max, bool-not-integer, string max_length, unknown-field ignored, no jsonschema import in jobs.py source |
| `test_registry_lifecycle.py` | 5 | D-14 async-ctx-mgr; JOBS-04 in-memory invariant; empty-state lists; re-enter after exit |
| `test_start_tool_job.py` | 7 | **SC-1**: D-19 25-key snapshot returned; timeout=0/-1 → invalid-kwargs; timeout=10^20 capped at JOB_MAX_TIMEOUT_S; unknown tool → D-15 #2; bad case_dir → D-15 #4(field=case_dir) |
| `test_lifecycle_status.py` | 4 | D-06: `JobStatus.__args__` is the exact 7-tuple; `_TERMINAL_STATUSES` is the 5-element frozenset; terminal-immutable invariant (cancel-after-terminal is no-op) |
| `test_get_tool_job.py` | 3 | 25-key snapshot returned; field types; unknown job_id → D-15 #3 |
| `test_list_tool_jobs.py` | 6 | `_specs` default (capa only); `include_internal=True` (3 specs); spec-dict keys; 5-key listing shape; state-string + state-list filters |
| `test_cancel_grace.py` | 2 | D-07 ladder reaps 30s sleep within grace; idempotent: second cancel returns `previously_terminal=True` |
| `test_timeout.py` | 1 | D-08: timeout=0.5 on sleep(10) → `killed_timeout` + `timed_out=True` + non-zero exit_code |
| `test_log_cap.py` | 1 | **SC-3**: `_log_burst_probe` with `MCP_GATEWAY_MAX_JOB_LOG_MB=1` → `killed_log_cap` + log file ends with `b"\n=== MARE_JOB_KILLED_LOG_CAP ===\n"` marker |
| `test_disconnect_200ms.py` | 1 | **SC-4**: drive-task externally cancelled → `os.kill(pid, 0)` raises ProcessLookupError within 200 ms (measured: ~0.91 ms on dev host, well under the 200 ms ceiling) |
| `test_progress.py` | 5 | **SC-5**: synthetic spec `progress_parser=(5,10,"halfway") if b"PROGRESS" in line`; Tier-1 fields set on job; Tier-2 `ctx.report_progress` called; second poll with same session_id → dedupe; different session_id → reports again; `progress is None` → never called |
| `test_errors.py` | 6 | **D-15 four-shape closure**: cap-reached (inflight/cap/hint), unknown-tool (tool/known/hint), job-not-found (job_id/hint), invalid-kwargs (field/expected/got); every error has `"error"` string key; no tool handler raises |
| `test_lru_retention.py` | 1 | **D-10**: max_completed=3, submit 4 jobs → oldest evicted; `.txt` AND `.json` files preserved on disk; `get_tool_job(evicted_id)` → D-15 #3 with "tool-logs" hint |
| `test_docstring_disclaimer.py` | 12 | **D-26**: parameterized over 4 tools × 3 invariants: `"In-memory registry"` present; `"shared across all bearer-token clients"` present; no leftover `{_JOBS_DISCLAIMER}` placeholder |
| `test_terminal_snapshot_json.py` | 1 | **D-21**: `log_path_abs.with_suffix(".json")` exists; contents are a 25-key dict; status is terminal; ended_at not None |
| `test_lifespan_integration.py` | 1 | **SC-6**: instrumented `BackgroundJobRegistry.__aexit__` + `SessionRegistry.__aexit__` append to shared list; assertion: `["jobs.__aexit__", "sessions.__aexit__"]` LIFO order; `session_state.JOB_REGISTRY`/`SESSION_REGISTRY` populated inside, None outside |
| `test_capa_integration.py` | 1 (slow) | **D-04**: capa runs end-to-end on `/bin/ls`-as-sample; skipped on dev host (capa absent); container provides capa via Kali base |

**66 non-slow tests + 1 slow test. Full non-slow runtime: ~31 s.**

### Task 3 — VALIDATION.md flip

- Frontmatter: `status: draft → validated`; `nyquist_compliant: false → true`; `wave_0_complete: false → true`; `validated: 2026-05-19` added
- All 19 Wave 0 Requirements checkboxes flipped from `- [ ]` to `- [x]`
- "Wave 0 Actuals" table added with per-file ✅ status + test count + coverage label
- Validation Sign-Off: all 6 checkboxes flipped; "Approval: pending → green"

## Coverage Matrices

### JOBS-XX requirements (all covered by ≥1 passing test)

| Requirement | Coverage |
|-------------|----------|
| JOBS-01 (subprocess safety: argv-only + start_new_session) | test_start_tool_job (D-05 surface), test_disconnect_200ms (pgroup-kill) |
| JOBS-02 (get_tool_job 25-key snapshot) | test_get_tool_job (all 3 tests) |
| JOBS-03 (cancel_tool_job idempotent) | test_cancel_grace (test_cancel_is_idempotent) |
| JOBS-04 (in-memory registry invariant) | test_registry_lifecycle (test_in_memory_invariant_jobs04) |
| JOBS-05 (start_tool_job D-19 25-key snapshot return) | test_start_tool_job (test_sc1_submit_returns_25_key_snapshot) |
| JOBS-06 (subprocess reaped on disconnect ≤200 ms) | test_disconnect_200ms (SC-4) |
| JOBS-07 (D-16 two-tier progress) | test_progress (all 5 tests) |

### SC-1..SC-6 (all covered)

| Success Criterion | Test File | Assertion |
|-------------------|-----------|-----------|
| SC-1 (25-key snapshot in start_tool_job) | test_start_tool_job.py | `set(result.keys()) == D19_KEYS` + status ∈ {pending, running, succeeded} |
| SC-2 (D-19 + D-07 + D-20 contracts) | test_get_tool_job.py + test_cancel_grace.py + test_list_tool_jobs.py | three files cover the three contracts |
| SC-3 (log cap → killed_log_cap + marker) | test_log_cap.py | `data.endswith(b"\\n=== MARE_JOB_KILLED_LOG_CAP ===\\n")` |
| SC-4 (drive-cancel → reap within 200 ms) | test_disconnect_200ms.py | `elapsed_ms < 200` (measured: ~0.91 ms) |
| SC-5 (progress dedup by session_id across polls) | test_progress.py | `len(fake_ctx.calls) == 1` after two polls |
| SC-6 (LIFO unwind: jobs before sessions) | test_lifespan_integration.py | `unwind_order == ["jobs.__aexit__", "sessions.__aexit__"]` |

### D-XX behaviors

| Decision | Test File |
|----------|-----------|
| D-04 (capa user-visible spec) | test_capa_integration.py (slow) |
| D-05 (start_tool_job signature + arg resolution) | test_start_tool_job.py |
| D-06 (7 status vocabulary) | test_lifecycle_status.py |
| D-07 (SIGTERM-grace-SIGKILL ladder) | test_cancel_grace.py |
| D-08 (job-level hard timeout) | test_timeout.py |
| D-09 (counter-based log cap) | test_log_cap.py |
| D-10 (FIFO eviction + log preservation) | test_lru_retention.py |
| D-15 (four error dict shapes) | test_errors.py |
| D-16 (two-tier progress + session-id dedup) | test_progress.py |
| D-19 (25-key snapshot) | test_get_tool_job.py + test_terminal_snapshot_json.py |
| D-20 (list_tool_jobs + `_specs` magic + Q5 filter) | test_list_tool_jobs.py |
| D-21 (sibling .json on terminal) | test_terminal_snapshot_json.py |
| D-25 (LIFO lifespan unwind) | test_lifespan_integration.py |
| D-26 (disclaimer regression) | test_docstring_disclaimer.py |

### SC-4 measured performance

Actual reap time on dev host (measured via `time.monotonic()` delta + `os.kill(pid,0)` loop): **0.91 ms** — far under the 200 ms ceiling. Subprocess group is killed immediately in the `CancelledError` branch of `_spawn_and_drive` via `os.killpg(pgid, SIGKILL)` followed by shielded `proc.wait()`.

## Deviations from Plan

### Rule 1 — jsonschema-absence assertion rewritten

**Found during:** Task 2, after running `test_spec_validation.py`
**Issue:** The plan said the test should be `with pytest.raises(ModuleNotFoundError): import jsonschema`. But the mcp SDK 1.27 (a Phase 2 dep) transitively installs jsonschema into the venv, so the import succeeds.
**Fix:** Rewrote `test_no_jsonschema_dependency` → `test_no_jsonschema_import_in_jobs_module`: asserts `"import jsonschema" not in inspect.getsource(jobs)` and `"from jsonschema" not in inspect.getsource(jobs)`. Semantic invariant unchanged: "jobs.py does NOT use jsonschema". Q3 hand-rolled walker preserved.
**Files modified:** mcp-gateway/tests/jobs/test_spec_validation.py
**Commit:** 11ab0f2

### Rule 3 — registry_factory dual-module reload

**Found during:** Task 2, after running test_lru_retention.py post-test_log_cap.py
**Issue:** `test_log_cap.py` calls `registry_factory(env={"MCP_GATEWAY_MAX_JOB_LOG_MB": "1"})` which `importlib.reload(jobs)`. This creates a NEW `JobNotFound` class object. But `mcp_gateway.tools.jobs` was loaded earlier with `from mcp_gateway.jobs import JobNotFound` — its bound reference points at the OLD class. Subsequent `tools.jobs.get_tool_job` does `except JobNotFound` against the OLD class, but `registry.get()` (called via tools.jobs) is the NEW registry that raises the NEW class. The except clause misses; exception escapes (D-15 "tools never raise" violated in test scope only).
**Fix:** `registry_factory` now reloads BOTH `jobs` AND `tools.jobs` when env is used, AND registers a finalizer to reload both back after the test. Cross-test pollution eliminated; pytest pytest order independence restored.
**Files modified:** mcp-gateway/tests/jobs/conftest.py
**Commit:** 11ab0f2

### Rule 3 — test_lifespan_integration token file env

**Found during:** Task 2, after running test_lifespan_integration.py
**Issue:** `build_app() → load_or_generate_token() → /agent/.mcp-gateway-token.parent.mkdir(parents=True)` raises PermissionError on dev host (no `/agent`).
**Fix:** Test now sets `MCP_GATEWAY_TOKEN_FILE=tmp_path/tok` so the token-file creation uses a tmp directory. Phase 7 established the same precedent for `MCP_GATEWAY_STATUS_DIR`.
**Files modified:** mcp-gateway/tests/jobs/test_lifespan_integration.py
**Commit:** 11ab0f2

### Plan deviation note — Wave 0 file count

The plan's frontmatter `files_modified:` lists 21 entries (18 test files + `tests/test_tool_list.py` + `09-VALIDATION.md` + the two pre-existing files), but `tests/test_tool_list.py` was already bumped in Plan 03 (per 09-03-SUMMARY.md Rule 1 deviation). Plan 04 therefore touches 18 NEW test files + 1 modified planning doc. No regression in `tests/test_tool_list.py` — it still recognizes 47 gateway-native tools including the 4 Phase 9 additions.

## Threat Model Disposition

| Threat ID | Disposition | Mitigation Verified By |
|-----------|-------------|------------------------|
| T-09-01 (kwargs tampering) | mitigate | test_spec_validation.py — 10 tests cover integer/string/boolean boundaries, bool-not-integer, oversized strings |
| T-09-02 (cross-client info disclosure) | accept (documented) | test_docstring_disclaimer.py — 12 parameterized assertions across 4 tools × 3 phrases |
| T-09-03 (log-write DoS) | mitigate | test_log_cap.py — SC-3: cap-reach → marker → SIGKILL → killed_log_cap status |
| T-09-04 (timeout tampering) | mitigate | test_start_tool_job.py — timeout=10^20 capped at JOB_MAX_TIMEOUT_S; timeout=0/-1 → D-15 invalid-kwargs |
| T-09-05 (concurrency DoS) | mitigate | test_errors.py — 3rd submit beyond cap=2 returns D-15 cap-reached dict |
| T-09-06 (stale subprocess) | mitigate | test_disconnect_200ms.py — measured 0.91 ms reap, well under 200 ms ceiling |
| T-09-07 (eviction destroys evidence) | mitigate | test_lru_retention.py — `.txt` + `.json` both `exists()` post-eviction |

## Commits

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Add Phase 9 Wave 0 test scaffolding (package marker, conftest fixtures) | 2a5a875 |
| 2 | Add Phase 9 Wave 0 Nyquist test suite (17 files, 66 tests) | 11ab0f2 |
| 3 | Flip Phase 9 VALIDATION.md to nyquist_compliant=true with Wave 0 Actuals table | 82c11a9 |

## Verification

### Plan acceptance commands

```
$ cd mcp-gateway && pytest -m 'not slow' tests/jobs/ --tb=short
================ 66 passed, 1 deselected, 1 warning in 30.88s ================

$ cd mcp-gateway && pytest -m slow tests/jobs/test_capa_integration.py --tb=short
=========================== short test summary info ============================
SKIPPED [1] tests/jobs/conftest.py:14: capa not on PATH (install via Kali container)
======================== 1 skipped, 1 warning in 0.11s =========================

$ head -10 .planning/phases/09-background-job-system/09-VALIDATION.md
---
phase: 9
slug: background-job-system
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-19
validated: 2026-05-19
---
```

### Full mcp-gateway suite (regression sanity)

```
$ cd mcp-gateway && pytest -m 'not slow' tests/ --tb=line
===== 1 failed, 321 passed, 46 skipped, 3 deselected, 3 warnings in 38.30s =====
```

The 1 failure (`test_acl_available.py::test_setfacl_on_path`) is a pre-existing Phase 7 host-only assertion (setfacl absent from dev host) — out of Phase 9 scope, pre-dates Plan 04, container provides setfacl via Kali base.

### Grep-the-source acceptance

- `grep -nc 'In-memory registry' mcp-gateway/tests/jobs/test_docstring_disclaimer.py` → 1 (parameterized + 4 tools × 3 invariants = 12 assertions)
- `grep -n 'ProcessLookupError' mcp-gateway/tests/jobs/test_disconnect_200ms.py` → 1 (the SC-4 reap assertion)
- `grep -n 'MARE_JOB_KILLED_LOG_CAP' mcp-gateway/tests/jobs/test_log_cap.py` → 1 (marker assertion)
- `grep -nc 'importlib.reload(jobs' mcp-gateway/tests/jobs/conftest.py` → 2 (one in env-override path, one in finalizer restore)
- `grep -n 'start_tool_job' mcp-gateway/tests/test_tool_list.py` → present (already in place from Plan 03)

## Self-Check: PASSED

Files verified:

- FOUND: mcp-gateway/tests/jobs/__init__.py
- FOUND: mcp-gateway/tests/jobs/conftest.py
- FOUND: mcp-gateway/tests/jobs/test_spec_validation.py
- FOUND: mcp-gateway/tests/jobs/test_registry_lifecycle.py
- FOUND: mcp-gateway/tests/jobs/test_start_tool_job.py
- FOUND: mcp-gateway/tests/jobs/test_lifecycle_status.py
- FOUND: mcp-gateway/tests/jobs/test_get_tool_job.py
- FOUND: mcp-gateway/tests/jobs/test_list_tool_jobs.py
- FOUND: mcp-gateway/tests/jobs/test_cancel_grace.py
- FOUND: mcp-gateway/tests/jobs/test_timeout.py
- FOUND: mcp-gateway/tests/jobs/test_log_cap.py
- FOUND: mcp-gateway/tests/jobs/test_disconnect_200ms.py
- FOUND: mcp-gateway/tests/jobs/test_progress.py
- FOUND: mcp-gateway/tests/jobs/test_errors.py
- FOUND: mcp-gateway/tests/jobs/test_lru_retention.py
- FOUND: mcp-gateway/tests/jobs/test_docstring_disclaimer.py
- FOUND: mcp-gateway/tests/jobs/test_terminal_snapshot_json.py
- FOUND: mcp-gateway/tests/jobs/test_lifespan_integration.py
- FOUND: mcp-gateway/tests/jobs/test_capa_integration.py
- FOUND: .planning/phases/09-background-job-system/09-VALIDATION.md (frontmatter flipped)

Commits verified:

- FOUND: 2a5a875 (Task 1)
- FOUND: 11ab0f2 (Task 2)
- FOUND: 82c11a9 (Task 3)

All Plan 04 success criteria satisfied. Phase 9 is Nyquist-compliant. Phase 9 phase-gate complete — ready for `/gsd-verify-work` sign-off and Phase 10 planning.
