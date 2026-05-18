---
phase: 8
slug: session-scoped-r2
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-18
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

> Populated by the planner from PLAN.md task IDs. Each row maps a task to one or more validation tests from the table below.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (filled by planner) | | | | | | | | | ⬜ pending |

### Source Test Catalog (from RESEARCH §Validation Architecture)

| Req ID | Behavior | Test Type | Automated Command | File Exists |
|--------|----------|-----------|-------------------|-------------|
| SESS-01 | open returns session_id; `aaa` analysis state persists to next `aflj` call | integration | `pytest tests/test_r2_sessions.py::test_aaa_aflj_persists -x` | ❌ W0 |
| SESS-02 | r2_cmd returns 12-key + 6-extension shape; head-truncated; full log on disk | unit | `pytest tests/test_r2_sessions.py::test_r2_cmd_result_shape -x` | ❌ W0 |
| SESS-02 | format="json" parses known-JSON command (iij) | unit | `pytest tests/test_r2_sessions.py::test_format_json_iij -x` | ❌ W0 |
| SESS-02 | format="json" graceful-fail on `?V` → parsed_json=None, parse_error set | unit | `pytest tests/test_r2_sessions.py::test_format_json_non_json_command -x` | ❌ W0 |
| SESS-03 | close_r2_session idempotent; second call returns already_closed: True | unit | `pytest tests/test_r2_sessions.py::test_close_idempotent -x` | ❌ W0 |
| SESS-03 | list_sessions returns fd_count >= 0 for live session | integration | `pytest tests/test_r2_sessions.py::test_list_fd_count_nonneg -x` | ❌ W0 |
| SESS-04 | Reaper kills idle session within idle_s + reaper_interval_s of inactivity | integration | `pytest tests/test_sessions.py::test_reaper_kills_idle -x` | ❌ W0 |
| SESS-04 | Cap-reject: open N+1 → returns D-18 error dict | unit | `pytest tests/test_sessions.py::test_cap_reject -x` | ❌ W0 |
| SESS-04 | Lifespan teardown kills every open r2 PID | integration | `pytest tests/test_sessions.py::test_lifespan_teardown_kills_all -x` | ❌ W0 |
| SESS-05 | open_r2_session.__doc__ contains full SESS-05 disclaimer (D-23 phrasing) | grep-source | `pytest tests/test_r2_sessions.py::test_sess05_disclaimer_in_docstrings -x` | ❌ W0 |
| SESS-06 | r2_cmd(sid, "!ls") raises ValueError; matrix per D-09 | unit | `pytest tests/test_r2_sessions.py::test_dangerous_cmd_refusal_matrix -x` | ❌ W0 |
| SESS-06 | After open, r2_cmd(sid, "e scr.interactive") returns "false" | integration | `pytest tests/test_r2_sessions.py::test_lockdown_init_took_effect -x` | ❌ W0 |
| Pitfall 6 | r2_cmd(sid, "?I prompt", timeout=2.0) returns session_invalidated: true in <5s | integration | `pytest tests/test_r2_sessions.py::test_hung_cmd_kills_session -x` | ❌ W0 |
| Pitfall 18 | Cancel r2_cmd("aaaa") after 0.5s; r2 PID dead within 200 ms | integration | `pytest tests/test_r2_sessions.py::test_cancel_propagates_to_killpg -x` | ❌ W0 |
| D-26 | EXPANDED_CASE_SUBDIRS contains "r2-sessions" | unit | `pytest tests/test_sessions.py::test_expanded_case_subdirs_contains_r2_sessions -x` | ❌ W0 (file exists; new test) |
| D-26 | Resource walker exposes mare://cases/<case>/r2-sessions/<sid>-transcript.log | integration | `pytest tests/test_resources_phase7.py::test_r2_sessions_transcript_exposed -x` | ❌ W0 (file exists; new test) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Test-file note: Plan 01 Task 2 places the D-29 EXPANDED_CASE_SUBDIRS regression in `tests/test_sessions.py` (not `tests/test_artifacts_io.py`). The catalog row above uses `test_sessions.py` consistently with Plan 01.*

---

## Wave 0 Requirements

- [ ] `mcp-gateway/tests/test_sessions.py` — registry internals + reaper. NEW file.
- [ ] `mcp-gateway/tests/test_r2_sessions.py` — MCP tool surface. NEW file.
- [ ] `_require_r2_or_skip()` helper — add to `mcp-gateway/tests/conftest.py` (or follow per-file pattern from `test_run_shell.py:32-39`). Pattern: `shutil.which("r2") is None → pytest.skip(...)`.
- [ ] Augment `mcp-gateway/tests/test_artifacts_io.py::test_expanded_case_subdirs_catalog` to include `"r2-sessions"` in expected set.
- [ ] Augment `mcp-gateway/tests/test_resources_phase7.py` with a depth-2 `r2-sessions/` exposure test.

*No new test framework install needed — `pytest` + `pytest-asyncio` already pinned.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| (none) | — | All Phase 8 behaviors have automated coverage via the catalog above. Lifespan-teardown is automated via Starlette `LifespanContext`. | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
</content>
</invoke>
