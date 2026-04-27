---
phase: 3
slug: container-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-27
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | bash smoke scripts (no test framework — pure shell assertions against `docker compose`, `docker exec`, `curl`) |
| **Config file** | none — phase-local scripts under `.planning/phases/03-container-integration/scripts/` (Wave 0 creates) |
| **Quick run command** | `bash .planning/phases/03-container-integration/scripts/smoke-local.sh` |
| **Full suite command** | `bash .planning/phases/03-container-integration/scripts/smoke-all.sh` (runs `smoke-local.sh` then `smoke-remote.sh`) |
| **Estimated runtime** | ~30s local, ~45s remote (image pre-built) |

---

## Sampling Rate

- **After every task commit:** Run `bash .planning/phases/03-container-integration/scripts/smoke-local.sh` (cheap — no container start needed for pure file/grep checks; runs in ~10s when image is cached)
- **After every plan wave:** Run `bash .planning/phases/03-container-integration/scripts/smoke-all.sh`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds (image build cached; `compose up -d` + token wait + teardown)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 3-01-01 | 01 | 0 | INF-01,INF-02,INF-05 | — | N/A | smoke-script-stub | `test -x .planning/phases/03-container-integration/scripts/smoke-local.sh` | ❌ W0 | ⬜ pending |
| 3-01-02 | 01 | 0 | INF-01,INF-02,INF-05 | — | N/A | smoke-script-stub | `test -x .planning/phases/03-container-integration/scripts/smoke-remote.sh` | ❌ W0 | ⬜ pending |
| 3-01-03 | 01 | 1 | INF-02 | T-INF-AUTH | gateway port published only on opt-in | grep | `grep -E '\$\{MCP_GATEWAY_HOST_BIND.*MCP_GATEWAY_HOST_PORT.*MCP_GATEWAY_PORT' compose.yaml` | ✅ | ⬜ pending |
| 3-01-04 | 01 | 1 | INF-01 | — | mode-gated daemon launch | grep | `grep -E 'MCP_GATEWAY_ENABLED.*=.*1' Dockerfile` | ✅ | ⬜ pending |
| 3-01-05 | 01 | 1 | INF-01 | — | overlay-only remote keepalive | file-exists+grep | `test -f compose.remote.yaml && grep -E '"tail".*"/dev/null"' compose.remote.yaml` | ❌ W0 | ⬜ pending |
| 3-01-06 | 01 | 1 | INF-01 | — | --remote flag parsing exports correct env | grep | `grep -E 'MCP_GATEWAY_HOST=0.0.0.0' run_docker.sh && grep -E 'MCP_GATEWAY_ENABLED=1' run_docker.sh` | ✅ | ⬜ pending |
| 3-01-07 | 01 | 1 | INF-01 | T-INF-AUTH | token print block surfaces bearer to user | grep | `grep -E 'mcp.json|Authorization: Bearer' run_docker.sh` | ✅ | ⬜ pending |
| 3-01-08 | 01 | 2 | INF-05 | — | local-mode no-leak (no port, no daemon, v1 shell intact) | smoke-script | `bash .planning/phases/03-container-integration/scripts/smoke-local.sh` | ❌ W0 | ⬜ pending |
| 3-01-09 | 01 | 2 | INF-01,INF-02 | T-INF-AUTH | remote-mode end-to-end (port reachable from host with bearer) | smoke-script | `bash .planning/phases/03-container-integration/scripts/smoke-remote.sh` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `.planning/phases/03-container-integration/scripts/smoke-local.sh` — local-mode regression assertions (D-12): no `0.0.0.0:8080->8080/tcp` in `docker compose ps --format json`, no `mcp-gateway` process inside container (`docker exec ... pgrep -f mcp-gateway` exits non-zero), `claude --version` and `codex --version` succeed, default cwd is `/agent`
- [ ] `.planning/phases/03-container-integration/scripts/smoke-remote.sh` — remote-mode end-to-end assertions: `compose up -d` succeeds, token file `workspace/.mcp-gateway-token` appears within 15s, `curl -H "Authorization: Bearer $TOKEN" http://localhost:${MCP_GATEWAY_HOST_PORT:-8080}/health` returns 2xx, gateway log contains `0.0.0.0:8080`, idempotent re-run reprints the token, `compose down` cleans up
- [ ] `.planning/phases/03-container-integration/scripts/smoke-all.sh` — orchestrates both smoke scripts in sequence with shared trap-cleanup
- [ ] `.planning/phases/03-container-integration/scripts/lib_assert.sh` — shared bash assertion helpers (`assert_contains`, `assert_exit_0`, `assert_no_match`) for consistent failure messages

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `0.0.0.0` host bind reachable from a different LAN host | INF-02 | Single-machine CI cannot fake a peer host on the LAN | From a second machine on the same network: `curl -H "Authorization: Bearer $TOKEN" http://<host-ip>:8080/health` returns 2xx |
| Token print block is paste-friendly into Claude Code `.mcp.json` | INF-01 | Visual UX assessment — readability cannot be auto-graded | After `./run_docker.sh --remote`, copy the printed JSON snippet into a host `.mcp.json`, run `claude` from that directory, confirm the gateway tools appear in `/mcp` listing |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (smoke scripts + assertion lib)
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
