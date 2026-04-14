---
phase: 1
slug: ida-pro-backend
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-08
updated: 2026-04-14
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
| **Full suite command** | Build container + run `idalib-mcp --help` inside + verify `configure-agent-mcp.sh` output |
| **Estimated runtime** | ~120 seconds (Docker build dependent) |

---

## Sampling Rate

- **After every task commit:** Run `docker build --build-arg INSTALL_IDA_PRO=1 .`
- **After every plan wave:** Run full suite (build + startup + MCP config verification)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 01-01-T1 | 01 | 1 | IDA-01, IDA-02, IDA-06, INF-03 | integration | `grep -q "INSTALL_IDA_PRO" Dockerfile && grep -q "ida-builder" Dockerfile && grep -q "idalib-mcp" Dockerfile && grep -q "ida-pro-mcp" Dockerfile && grep -q "IDADIR=/opt/ida-pro" Dockerfile && grep -q 'INSTALL_IDA_PRO.*!=.*1' Dockerfile && echo "PASS"` | pending |
| 01-01-T2 | 01 | 1 | IDA-03, INF-04 | integration | `grep -q "IDA_PRO_ZIP" run_docker.sh && grep -q "IDA_USER_DIR" run_docker.sh && grep -q "ida.key" run_docker.sh && grep -q "ida.hexlic" run_docker.sh && grep -q "ida-stage" run_docker.sh && grep -q "INSTALL_IDA_PRO" run_docker.sh && grep -q "idapro-docker" compose.yaml && grep -q "IDADIR" compose.yaml && echo "PASS"` | pending |
| 01-02-T1 | 02 | 2 | IDA-04, IDA-05 | integration | `grep -q "idalib-mcp" docker-bin/configure-agent-mcp.sh && grep -q "ida_pro_mcp" docker-bin/configure-agent-mcp.sh && grep -q "sse" docker-bin/configure-agent-mcp.sh && grep -q "localhost:8745" docker-bin/configure-agent-mcp.sh && grep -q "import ida_idaapi" docker-bin/configure-agent-mcp.sh && grep -q "IDADIR" docker-bin/configure-agent-mcp.sh && grep -q "highest priority installed" docker-bin/configure-agent-mcp.sh && echo "PASS"` | pending |

*Status: pending / green / red / flaky*

---

## Post-Phase Verification

These verifications require a built Docker image with a valid IDA Pro installation and cannot be automated as pre-execution test scripts. They are validated after phase execution during `/gsd:verify-work`.

| Behavior | Requirement | Test Type | Verification Command |
|----------|-------------|-----------|---------------------|
| IDA installs conditionally, no license in layers | IDA-01 | integration | `docker build --build-arg INSTALL_IDA_PRO=1 .` succeeds; `docker history` shows no license files |
| idalib-mcp runs via SSE | IDA-02 | smoke | `docker run ... idalib-mcp --help` returns usage |
| Python 3.12+ available | INF-03 | unit | `docker run ... python3 -c "import sys; assert sys.version_info >= (3,12)"` |
| run_docker.sh detects IDA zip | INF-04 | unit | Place dummy zip in repo root, run detection logic, verify env vars set |
| Three-way fallback detection (IDA > BN > Ghidra) | IDA-04 | unit | `docker run ... configure-agent-mcp.sh && cat /agent/.mcp.json` shows SSE config for IDA |
| Python packages coexist without import errors | IDA-06 | smoke | `docker run ... python3 -c "import ida_idaapi"` succeeds when IDA installed |

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| IDA Pro license persists via bind mount | IDA-03 | Requires valid IDA license on host machine | 1. Place `ida.key` or `ida.hexlic` in `~/.idapro-docker/` 2. Start container 3. Verify license detected inside container 4. Restart container 5. Verify license still present |
| Hex-Rays decompile available | IDA-05 | Requires valid Hex-Rays license + test binary | 1. Ensure IDA+Hex-Rays license is active 2. Load test binary via idalib-mcp 3. Call decompile tool on a function 4. Verify decompiled output returned |

---

## Validation Sign-Off

- [x] All tasks have automated verify commands in their plan files
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Post-phase verification covers all requirements not testable at task level
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [x] Task map matches actual plan/task structure (3 tasks: 01-01-T1, 01-01-T2, 01-02-T1)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
