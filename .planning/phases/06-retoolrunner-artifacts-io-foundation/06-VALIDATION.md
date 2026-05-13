---
phase: 6
slug: retoolrunner-artifacts-io-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-13
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (`asyncio_mode="auto"`) |
| **Config file** | `mcp-gateway/pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd mcp-gateway && python -m pytest tests/test_artifacts_io.py tests/test_runner.py -x -m "not slow"` |
| **Full suite command** | `cd mcp-gateway && python -m pytest -x` |
| **Estimated runtime** | ~30 seconds quick / ~90 seconds full (incl. slow marker) |

---

## Sampling Rate

- **After every task commit:** Run quick command (above)
- **After every plan wave:** Run full suite command (above)
- **Before `/gsd-verify-work`:** Full suite must be green, including `-m slow` for SC-4
- **Max feedback latency:** ~30 seconds (quick) / ~90 seconds (full)

---

## Per-Task Verification Map

> Populated by gsd-planner after PLAN.md files are created. Each row maps a task to its automated verifier.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | FOUND-02/03/04 | — | argv-only execution, traversal rejection, OOM safety | unit/regression-grep | TBD | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `mcp-gateway/tests/test_runner.py` — new test file for `ReToolRunner` (SC-1..SC-4 + D-09 log naming)
- [ ] `mcp-gateway/tests/test_artifacts_io.py` — new test file for `confine_to`, `ensure_subdir`, `tool_log_path`, `EXPANDED_CASE_SUBDIRS` (SC-5)
- [ ] `mcp-gateway/pyproject.toml` — register `markers = ["slow: tests gated for slowness"]` under `[tool.pytest.ini_options]` to silence `PytestUnknownMarkWarning` for the 100 MB urandom test
- [ ] No new framework install — `pytest` + `pytest-asyncio` already in dev deps

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| (none) | — | — | — |

*All Phase 6 behaviors have automated verification — the runner is fully unit-testable.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (two new test files + one-line pyproject marker)
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s (full suite with slow marker)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
