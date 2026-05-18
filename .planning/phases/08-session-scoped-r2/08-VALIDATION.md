---
phase: 8
slug: session-scoped-r2
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-18
completed: 2026-05-18
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (asyncio_mode='auto') |
| **Config file** | `mcp-gateway/pyproject.toml` (asyncio mode); `mcp-gateway/tests/conftest.py` (shared fixtures) |
| **Quick run command** | `cd mcp-gateway && pytest tests/test_sessions.py tests/test_r2_sessions.py -x` |
| **Full suite command** | `cd mcp-gateway && pytest tests/ -x` |
| **Estimated runtime** | ~5–10 s host (skips when r2 missing); ~15–30 s container (full) |

---

## Sampling Rate

- **After every task commit:** Run `cd mcp-gateway && pytest tests/test_sessions.py tests/test_r2_sessions.py -x`
- **After every plan wave:** Run `cd mcp-gateway && pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Populated by Plan 05 Task 3. Each row maps a task to one or more validation tests from the Source Test Catalog.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-T1 | 01 | 1 | all SESS-* | none | _require_r2_or_skip helper added | unit | `cd mcp-gateway && python -c "from tests.conftest import _require_r2_or_skip"` | ✅ | ✅ |
| 08-01-T2 | 01 | 1 | all SESS-* | T-08-W0 | RED stubs for registry/reaper/cap | grep | `pytest --collect-only tests/test_sessions.py` | ✅ | ✅ |
| 08-01-T3 | 01 | 1 | all SESS-* | T-08-W0 | RED stubs for 4 MCP tools | grep | `pytest --collect-only tests/test_r2_sessions.py` | ✅ | ✅ |
| 08-01-T4 | 01 | 1 | D-26 | T-08-04-04 | EXPANDED_CASE_SUBDIRS regression + resource walker | unit + integration | `pytest tests/test_artifacts_io.py::test_expanded_case_subdirs_catalog tests/test_resources_phase7.py::test_r2_sessions_transcript_exposed` | ✅ | ✅ |
| 08-02-T1 | 02 | 2 | SESS-04, SESS-06 | T-08-02-01..08 | sessions.py primitive | unit | `pytest tests/test_sessions.py -x` | ✅ | ✅ |
| 08-03-T1 | 03 | 2 | SESS-01..03, 05, 06 | T-08-03-01..08 | tools/r2_sessions.py + 4 MCP tools | unit | `pytest tests/test_r2_sessions.py::test_sess05_disclaimer_in_docstrings -x` | ✅ | ✅ |
| 08-04-T1 | 04 | 3 | SESS-04, 05 | T-08-04-01..06 | EXPANDED_CASE_SUBDIRS + session_state | unit | `pytest tests/test_sessions.py::test_expanded_case_subdirs_contains_r2_sessions` | ✅ | ✅ |
| 08-04-T2 | 04 | 3 | SESS-04 | T-08-04-01..06 | tools/__init__ + app.py lifespan via sessions module constants | integration | `python -c "from mcp_gateway.app import build_app"` | ✅ | ✅ |
| 08-05-T1 | 05 | 4 | SESS-04 | T-08-02-02..04 | reaper + cap + lifespan-teardown body | integration | `pytest tests/test_sessions.py -x` | ✅ | ✅ |
| 08-05-T2a | 05 | 4 | SESS-01, SESS-02 | T-08-03-01..08 | opened_sid fixture + SC-1 + SC-2 (shape + json + non-json) | integration | `pytest tests/test_r2_sessions.py::test_aaa_aflj_persists tests/test_r2_sessions.py::test_r2_cmd_result_shape tests/test_r2_sessions.py::test_format_json_iij tests/test_r2_sessions.py::test_format_json_non_json_command -x` | ✅ | ✅ |
| 08-05-T2b | 05 | 4 | SESS-03, SESS-05, SESS-06 + Pitfall 6/18 | T-08-03-01..08 | SC-3 + SC-6 + Pitfalls + D-12 + D-13 | integration | `pytest tests/test_r2_sessions.py -x` | ✅ | ✅ |
| 08-05-T3 | 05 | 4 | all | n/a | Validation Sign-Off | meta | `pytest tests/ -x` GREEN | ✅ | ✅ |

### Source Test Catalog (from RESEARCH §Validation Architecture)

| Req ID | Behavior | Test Type | Automated Command | File Exists |
|--------|----------|-----------|-------------------|-------------|
| SESS-01 | open returns session_id; `aaa` analysis state persists to next `aflj` call | integration | `pytest tests/test_r2_sessions.py::test_aaa_aflj_persists -x` | ✅ |
| SESS-02 | r2_cmd returns 12-key + 6-extension shape; head-truncated; full log on disk | unit | `pytest tests/test_r2_sessions.py::test_r2_cmd_result_shape -x` | ✅ |
| SESS-02 | format="json" parses known-JSON command (iij) | unit | `pytest tests/test_r2_sessions.py::test_format_json_iij -x` | ✅ |
| SESS-02 | format="json" graceful-fail on `?V` → parsed_json=None, parse_error set | unit | `pytest tests/test_r2_sessions.py::test_format_json_non_json_command -x` | ✅ |
| SESS-03 | close_r2_session idempotent; second call returns already_closed: True | unit | `pytest tests/test_r2_sessions.py::test_close_idempotent -x` | ✅ |
| SESS-03 | list_sessions returns fd_count >= 0 for live session | integration | `pytest tests/test_r2_sessions.py::test_list_fd_count_nonneg -x` | ✅ |
| SESS-04 | Reaper kills idle session within idle_s + reaper_interval_s of inactivity | integration | `pytest tests/test_sessions.py::test_reaper_kills_idle -x` | ✅ |
| SESS-04 | Cap-reject: open N+1 → returns D-18 error dict | unit | `pytest tests/test_sessions.py::test_cap_reject -x` | ✅ |
| SESS-04 | Lifespan teardown kills every open r2 PID | integration | `pytest tests/test_sessions.py::test_lifespan_teardown_kills_all -x` | ✅ |
| SESS-05 | open_r2_session.__doc__ contains full SESS-05 disclaimer (D-23 phrasing) | grep-source | `pytest tests/test_r2_sessions.py::test_sess05_disclaimer_in_docstrings -x` | ✅ |
| SESS-06 | r2_cmd(sid, "!ls") raises ValueError; matrix per D-09 | unit | `pytest tests/test_r2_sessions.py::test_dangerous_cmd_refusal_matrix -x` | ✅ |
| SESS-06 | After open, r2_cmd(sid, "e scr.interactive") returns "false" | integration | `pytest tests/test_r2_sessions.py::test_lockdown_init_took_effect -x` | ✅ |
| Pitfall 6 | r2_cmd(sid, "?I prompt", timeout=2.0) returns session_invalidated: true in <5s | integration | `pytest tests/test_r2_sessions.py::test_hung_cmd_kills_session -x` | ✅ |
| Pitfall 18 | Cancel r2_cmd("aaaa") after 0.5s; r2 PID dead within 200 ms | integration | `pytest tests/test_r2_sessions.py::test_cancel_propagates_to_killpg -x` | ✅ |
| D-26 | EXPANDED_CASE_SUBDIRS contains "r2-sessions" | unit | `pytest tests/test_sessions.py::test_expanded_case_subdirs_contains_r2_sessions -x` | ✅ |
| D-26 | Resource walker exposes mare://cases/<case>/r2-sessions/<sid>-transcript.log | integration | `pytest tests/test_resources_phase7.py::test_r2_sessions_transcript_exposed -x` | ✅ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Test-file note: Plan 01 Task 2 places the D-29 EXPANDED_CASE_SUBDIRS regression in `tests/test_sessions.py` (not `tests/test_artifacts_io.py`). The catalog row above uses `test_sessions.py` consistently with Plan 01.*

---

## Wave 0 Requirements

- [x] `mcp-gateway/tests/test_sessions.py` — registry internals + reaper. NEW file.
- [x] `mcp-gateway/tests/test_r2_sessions.py` — MCP tool surface. NEW file.
- [x] `_require_r2_or_skip()` helper — add to `mcp-gateway/tests/conftest.py` (or follow per-file pattern from `test_run_shell.py:32-39`). Pattern: `shutil.which("r2") is None → pytest.skip(...)`.
- [x] Augment `mcp-gateway/tests/test_artifacts_io.py::test_expanded_case_subdirs_catalog` to include `"r2-sessions"` in expected set.
- [x] Augment `mcp-gateway/tests/test_resources_phase7.py` with a depth-2 `r2-sessions/` exposure test.

*No new test framework install needed — `pytest` + `pytest-asyncio` already pinned.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| (none) | — | All Phase 8 behaviors have automated coverage via the catalog above. Lifespan-teardown is automated via Starlette `LifespanContext`. | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-18
