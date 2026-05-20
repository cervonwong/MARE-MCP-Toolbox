---
phase: 13
slug: harden-concurrency-caps-and-r2-sandboxing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-20
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x with pytest-asyncio |
| **Config file** | `mcp-gateway/pyproject.toml` |
| **Quick run command** | `cd mcp-gateway && pytest -x --tb=short tests/ -k "phase13 or cap or sandbox or unsafe_r2"` |
| **Full suite command** | `cd mcp-gateway && pytest -x --tb=short tests/` |
| **Estimated runtime** | ~30 seconds (quick) / ~90 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run quick command above
- **After every plan wave:** Run full suite command above
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

Filled by planner from RESEARCH.md Validation Architecture + per-plan task list.
The planner MUST emit one row per task and mark Wave 0 dependencies (test
fixtures, r2 version probe, concurrency harness) with ❌ W0.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-W0-01 | W0 | 0 | HARDEN-W0 | — | r2 version probe — sandbox feature available in container | unit | `cd mcp-gateway && pytest tests/test_r2_version.py -x` | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `mcp-gateway/tests/test_r2_version.py` — verifies container's r2 supports `cfg.sandbox` (probe assumption A1)
- [ ] `mcp-gateway/tests/conftest.py` — add fixtures for concurrency-atomicity tests (N=20 concurrent acquire harness, deterministic spawn-failure injectors)
- [ ] Concurrency-atomicity harness — covers cancel-during-spawn, OSError-during-spawn, OOM-during-init, reaper-closes-idle, shutdown-closes-active per CONTEXT.md D-02

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Unsafe-r2 tool surfaces in `tools/list` only when env var set | D-10 | Requires gateway restart with different env to compare tool inventories | (1) Start gateway with `MCP_GATEWAY_R2_UNSAFE_ALLOWED` unset; call `tools/list`; assert no `open_r2_session_unsafe`. (2) Restart with `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1`; assert tool present. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (r2 version probe, concurrency harness)
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
