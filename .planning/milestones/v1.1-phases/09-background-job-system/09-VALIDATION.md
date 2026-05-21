---
phase: 9
slug: background-job-system
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-19
validated: 2026-05-19
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Populate from 09-RESEARCH.md "Validation Architecture" section during planning.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (already configured in `mcp-gateway/pyproject.toml`) |
| **Config file** | `mcp-gateway/pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd mcp-gateway && pytest tests/jobs -x --tb=short` |
| **Full suite command** | `cd mcp-gateway && pytest tests/ -x --tb=short` |
| **Estimated runtime** | ~30 seconds (quick) / ~90 seconds (full, excluding `-m slow` capa test) |

---

## Sampling Rate

- **After every task commit:** Run quick command for any file in `jobs.py` / `tools/jobs.py` / `session_state.py` / `app.py` / `tools/__init__.py`
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green; `pytest -m slow tests/jobs/test_capa_integration.py` must also pass if capa is installed
- **Max feedback latency:** 30 seconds (quick run)

---

## Per-Task Verification Map

Populated by planner — every task must reference a test file in this map (or declare Wave 0 dependency).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD-by-planner | — | — | — | — | — | — | — | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Per RESEARCH.md §"Validation Architecture" — 15 new test files:

- [x] `mcp-gateway/tests/jobs/__init__.py` — package marker
- [x] `mcp-gateway/tests/jobs/conftest.py` — shared fixtures (registry factory, _sleep_probe spec helper, fake `proc_callback`)
- [x] `mcp-gateway/tests/jobs/test_spec_validation.py` — `JobToolSpec.kwargs_schema` hand-rolled validator (Q3)
- [x] `mcp-gateway/tests/jobs/test_registry_lifecycle.py` — `BackgroundJobRegistry` `__aenter__`/`__aexit__` + cap-reach
- [x] `mcp-gateway/tests/jobs/test_start_tool_job.py` — D-05 signature + argument resolution order
- [x] `mcp-gateway/tests/jobs/test_lifecycle_status.py` — D-06 7-state vocabulary + terminal-immutable invariant
- [x] `mcp-gateway/tests/jobs/test_get_tool_job.py` — D-19 snapshot shape (25 keys)
- [x] `mcp-gateway/tests/jobs/test_list_tool_jobs.py` — D-20 result shape + `_specs` magic value
- [x] `mcp-gateway/tests/jobs/test_cancel_grace.py` — D-07 SIGTERM-grace-SIGKILL ladder
- [x] `mcp-gateway/tests/jobs/test_timeout.py` — D-08 job-level hard timeout → `killed_timeout`
- [x] `mcp-gateway/tests/jobs/test_log_cap.py` — D-09 counter-based cap → `killed_log_cap` (SC-3)
- [x] `mcp-gateway/tests/jobs/test_disconnect_200ms.py` — SC-4 subprocess reaped within 200 ms after drain cancel
- [x] `mcp-gateway/tests/jobs/test_progress.py` — D-16 two-tier progress (Tier-1 capture + Tier-2 `ctx.report_progress`)
- [x] `mcp-gateway/tests/jobs/test_errors.py` — D-15 four locked error dict shapes
- [x] `mcp-gateway/tests/jobs/test_lru_retention.py` — D-10 FIFO completion eviction; logs preserved
- [x] `mcp-gateway/tests/jobs/test_docstring_disclaimer.py` — D-26 disclaimer regression (scan tool docstrings)
- [x] `mcp-gateway/tests/jobs/test_terminal_snapshot_json.py` — D-21 sibling `.json` written on terminal state
- [x] `mcp-gateway/tests/jobs/test_lifespan_integration.py` — D-25 nested registry registration + shutdown unwind LIFO
- [x] `mcp-gateway/tests/jobs/test_capa_integration.py` (`-m slow`) — D-04 capa spec smoke; gated by `capa --version` availability

---

## Wave 0 Actuals (post-Plan-04)

| File | Status | Coverage |
|------|--------|----------|
| tests/jobs/__init__.py | ✅ | package marker |
| tests/jobs/conftest.py | ✅ | fixtures (registry_factory, case_dir_fixture, FakeContext, _require_capa_or_skip) |
| tests/jobs/test_spec_validation.py | ✅ 10 tests | Q3 hand-rolled validator |
| tests/jobs/test_registry_lifecycle.py | ✅ 5 tests | D-14 + JOBS-04 |
| tests/jobs/test_start_tool_job.py | ✅ 7 tests | SC-1 + D-05 |
| tests/jobs/test_lifecycle_status.py | ✅ 4 tests | D-06 + terminal-immutable |
| tests/jobs/test_get_tool_job.py | ✅ 3 tests | D-19 + JOBS-02 |
| tests/jobs/test_list_tool_jobs.py | ✅ 6 tests | D-20 + Q5 |
| tests/jobs/test_cancel_grace.py | ✅ 2 tests | D-07 + JOBS-03 idempotent |
| tests/jobs/test_timeout.py | ✅ 1 test | D-08 killed_timeout |
| tests/jobs/test_log_cap.py | ✅ 1 test | D-09 + SC-3 |
| tests/jobs/test_disconnect_200ms.py | ✅ 1 test | SC-4 (≤200 ms) |
| tests/jobs/test_progress.py | ✅ 5 tests | D-16 + SC-5 + JOBS-07 |
| tests/jobs/test_errors.py | ✅ 6 tests | D-15 four-shape closure |
| tests/jobs/test_lru_retention.py | ✅ 1 test | D-10 + log preservation |
| tests/jobs/test_docstring_disclaimer.py | ✅ 12 tests (4 tools × 3 invariants) | D-26 regression |
| tests/jobs/test_terminal_snapshot_json.py | ✅ 1 test | D-21 sibling .json |
| tests/jobs/test_lifespan_integration.py | ✅ 1 test | SC-6 + D-25 LIFO |
| tests/jobs/test_capa_integration.py | ⚠️ slow / skip-on-host | D-04 |

**Total: 66 non-slow tests pass + 1 slow test (skipped on dev host, runs in container).**

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| capa runs against real binary inside Kali container | JOBS-01 (real-world demo) | Container-only; requires capa install and a sample on disk | Build image, `docker run`, exercise `start_tool_job(tool="capa", kwargs={"sample": "..."}, case_dir="...")` end-to-end |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (18 test files above)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** green
