---
phase: 2
slug: mcp-gateway
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-23
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `.planning/phases/02-mcp-gateway/02-RESEARCH.md` §Validation Architecture

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` + `pytest-asyncio` (matches project pattern — `ghidra_headless_mcp` uses pytest; Dockerfile already installs `pytest` + `ruff`). Python 3.12. |
| **Config file** | `mcp-gateway/pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`). Created in Wave 0. |
| **Quick run command** | `pytest mcp-gateway/tests/ -x --no-header -q` |
| **Full suite command** | `pytest mcp-gateway/tests/ -v --cov=mcp_gateway` |
| **Estimated runtime** | ~30s quick / ~120s full |

---

## Sampling Rate

- **After every task commit:** Run `pytest mcp-gateway/tests/ -x --no-header -q`
- **After every plan wave:** Run `pytest mcp-gateway/tests/ -v --cov=mcp_gateway` + `ruff check mcp-gateway/`
- **Before `/gsd-verify-work`:** Full suite must be green AND `bash mcp-gateway/tests/e2e/smoke.sh` passes (container smoke)
- **Max feedback latency:** 30 seconds (quick) / 120 seconds (full)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-XX-XX | TBD | 0 | (infra) | — | Wave 0 fixtures + pyproject.toml bootstrap | wave 0 | `pytest mcp-gateway/tests/conftest.py --collect-only` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-01 | — | Streamable HTTP `initialize` returns session id | integration | `pytest mcp-gateway/tests/test_server_init.py -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-01 / GW-02 | — | `tools/list` returns the curated 21-tool set | integration | `pytest mcp-gateway/tests/test_tool_list.py -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-02 | — | Count of exposed tools within 15-25 | unit | `pytest mcp-gateway/tests/test_tool_list.py::test_tool_count_in_range -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-02 | — | Each orchestrator script maps to an atomic tool | unit | `pytest mcp-gateway/tests/test_tool_list.py::test_atomic_tools_map_to_scripts -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-03 | — | `decompile` routes to pinned backend (stub backend returns canary) | integration | `pytest mcp-gateway/tests/test_tool_routing.py -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-03 | — | Unified name `list_functions` dispatches to correct backend tool name | unit | `pytest mcp-gateway/tests/test_tool_map.py -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-04 | T-02-AUTH | `/mcp` without `Authorization` → 401 | integration | `pytest mcp-gateway/tests/test_auth.py::test_mcp_requires_bearer -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-04 | T-02-AUTH | `/upload` without `Authorization` → 401 | integration | `pytest mcp-gateway/tests/test_auth.py::test_upload_requires_bearer -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-04 | T-02-AUTH | Valid bearer token passes `initialize` | integration | `pytest mcp-gateway/tests/test_auth.py::test_valid_bearer_ok -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-04 | — | `/healthz` open (no bearer) | unit | `pytest mcp-gateway/tests/test_auth.py::test_health_open -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-05 | T-02-NET | Default bind is 127.0.0.1 | unit | `pytest mcp-gateway/tests/test_cli.py::test_default_bind_is_localhost -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-05 | T-02-NET | `MCP_GATEWAY_HOST=0.0.0.0` overrides default | unit | `pytest mcp-gateway/tests/test_cli.py::test_env_overrides_bind -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-06 | T-02-UPLOAD | POST `/upload` creates `/agent/uploads/<sha256>/<name>` | integration | `pytest mcp-gateway/tests/test_uploads.py::test_upload_roundtrip -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-06 | T-02-UPLOAD | Upload > MAX_BYTES → 413 (streamed, no OOM) | integration | `pytest mcp-gateway/tests/test_uploads.py::test_upload_over_cap -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-06 | T-02-UPLOAD | Duplicate upload dedupes on sha256 | integration | `pytest mcp-gateway/tests/test_uploads.py::test_upload_dedupe -x` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | 1+ | GW-06 | T-02-UPLOAD | Uploaded sample usable via `collect_strings(sample=<sha256>)` | e2e (container) | `bash mcp-gateway/tests/e2e/test_upload_then_analyze.sh` | ❌ W0 | ⬜ pending |
| 02-XX-XX | TBD | final | Phase Gate | — | Docker-compose-up smoke: gateway reachable, `tools/list` works, one triage run | e2e | `bash mcp-gateway/tests/e2e/smoke.sh` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Task IDs will be bound once PLAN.md files assign them. Planner must update this column as part of each plan's Wave 0 / task definitions.*

---

## Wave 0 Requirements

- [ ] `mcp-gateway/pyproject.toml` — package metadata, `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`, `[project.scripts]` entry for `mcp-gateway`
- [ ] `mcp-gateway/tests/conftest.py` — shared fixtures: `fake_backend_mcp`, `gateway_test_client` (ASGI test client), `tmp_upload_dir`, `tmp_status_dir`, `bearer_token`
- [ ] `mcp-gateway/tests/__init__.py` (empty — package marker)
- [ ] `mcp-gateway/tests/e2e/smoke.sh` — compose up + curl smoke test (stub created in Wave 0; body filled in final wave)
- [ ] `mcp-gateway/tests/e2e/test_upload_then_analyze.sh` — upload-then-run integration harness stub
- [ ] Add `pytest-asyncio` to the Dockerfile gateway install block

*Stub test files can be placeholders with `pytest.skip("Wave 0 stub — implemented in later wave")` so the collect phase doesn't error.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Host-mounted token file readable from host side | D-17 visibility | Requires `docker compose up` with actual host bind mount — not reproducible in unit tests without Docker-in-Docker | 1. `docker compose up -d` from project root. 2. `cat .mcp-gateway-token` on host. 3. Token should match gateway log line. |
| Real IDA backend end-to-end (license required) | GW-03 | IDA Pro license cannot ship in image; requires user-provided license | 1. Build image with `INSTALL_IDA_PRO=1` and mounted licenses. 2. `docker compose up`. 3. Confirm `[gateway] backend: IDA Pro` in logs. 4. Run `curl -H "Authorization: Bearer $TOKEN" ... tools/call decompile`. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (conftest, pyproject, e2e stubs)
- [ ] No watch-mode flags (`-f`, `--watch`) in quick/full commands
- [ ] Feedback latency < 30s quick / < 120s full
- [ ] `nyquist_compliant: true` set in frontmatter after plan-checker approves

**Approval:** pending
