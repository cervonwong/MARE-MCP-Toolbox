---
phase: 1
slug: ida-pro-backend
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-08
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | bash + docker build verification |
| **Config file** | none — test via Docker build + container startup |
| **Quick run command** | `docker build --build-arg INSTALL_IDA_PRO=1 .` (build succeeds) |
| **Full suite command** | Build container + run `ida-mcp --help` inside + verify `configure-agent-mcp.sh` output |
| **Estimated runtime** | ~120 seconds (Docker build dependent) |

---

## Sampling Rate

- **After every task commit:** Run `docker build --build-arg INSTALL_IDA_PRO=1 .`
- **After every plan wave:** Run full suite (build + startup + MCP config verification)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | IDA-01 | integration | `docker build --build-arg INSTALL_IDA_PRO=1 .` | No — Wave 0 | pending |
| 01-01-02 | 01 | 1 | IDA-02 | smoke | `docker run ... ida-mcp --help` | No — Wave 0 | pending |
| 01-02-01 | 02 | 1 | IDA-03 | manual-only | Requires valid IDA license on host | N/A | pending |
| 01-02-02 | 02 | 1 | IDA-04 | unit | `docker run ... configure-agent-mcp.sh && cat /agent/.mcp.json` | No — Wave 0 | pending |
| 01-02-03 | 02 | 1 | IDA-05 | manual-only | Requires valid Hex-Rays license + test binary | N/A | pending |
| 01-02-04 | 02 | 1 | IDA-06 | smoke | `docker run ... python3 -c "import ida_mcp"` | No — Wave 0 | pending |
| 01-02-05 | 02 | 1 | INF-03 | unit | `docker run ... python3 -c "import sys; assert sys.version_info >= (3,12)"` | No — Wave 0 | pending |
| 01-02-06 | 02 | 1 | INF-04 | unit | Place dummy zip, run detection logic, check env vars | No — Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_configure_agent_mcp.sh` — three-way detection test (no IDA license needed, checks detection logic)
- [ ] `tests/test_run_docker_ida.sh` — IDA zip detection test (mock zip file)
- [ ] `tests/test_docker_build.sh` — Docker build verification (build with `INSTALL_IDA_PRO=0` and `INSTALL_IDA_PRO=1`)

*These scripts validate build-time and startup-time behavior without requiring an IDA Pro license.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| IDA Pro license persists via bind mount | IDA-03 | Requires valid IDA license on host machine | 1. Place `ida.key` in `~/.idapro-docker/` 2. Start container 3. Verify license detected inside container 4. Restart container 5. Verify license still present |
| Hex-Rays decompile available | IDA-05 | Requires valid Hex-Rays license + test binary | 1. Ensure IDA+Hex-Rays license is active 2. Load test binary via ida-mcp 3. Call decompile tool on a function 4. Verify decompiled output returned |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
