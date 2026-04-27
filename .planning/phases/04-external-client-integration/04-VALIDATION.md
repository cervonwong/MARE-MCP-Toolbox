---
phase: 04
slug: external-client-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-27
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: Validation Architecture in 04-RESEARCH.md.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (Python e2e) + Node `npm install && npm start` (mastra starter, invoked from pytest) |
| **Config file** | `mcp-gateway/pyproject.toml` (`[tool.pytest.ini_options]`: `asyncio_mode = "auto"`, `addopts = "-ra"`, `testpaths = ["tests"]`) — auto-discovers new `tests/e2e/` subdir |
| **Quick run command** | `cd mcp-gateway && uv run pytest tests/e2e/ -v -m "not slow"` |
| **Full suite command** | `cd mcp-gateway && uv run pytest -v` (unit + e2e) |
| **Estimated runtime** | Unit-only ~10s; e2e ~30-90s (mastra `npm install` cold-cache dominates) |

E2E tests require a running gateway — `conftest.py` reads `MARE_GATEWAY_URL` + `MARE_GATEWAY_TOKEN` from env (or falls back to `workspace/.mcp-gateway-token` + `http://localhost:8080/mcp`). If neither is reachable, fixtures `pytest.skip()` cleanly so unit-only CI never breaks.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/e2e/<file_just_touched> -v` (single-file scope)
- **After every plan wave:** Run `uv run pytest tests/e2e/ -v`
- **Before `/gsd-verify-work`:** Full suite (`uv run pytest -v`) must be green AND a manual UAT pass against a real Claude Code session per D-12 checklist
- **Max feedback latency:** ~30 seconds for any single e2e file; ~90s for the full e2e directory

---

## Per-Task Verification Map

> Plan IDs are filled in once `gsd-planner` finalizes the wave/plan layout. Each requirement maps to at least one automated test plus (where applicable) a manual UAT step.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD-resources-list | resources | 2 | CLI-04 | T-04-01 (path traversal in URI) | `mare://cases/<case>/<artifact>` resolves only under `/agent/status/<case>/`; `..` segments rejected | e2e (httpx) | `uv run pytest tests/e2e/test_resources.py::test_list -v` | ❌ W0 | ⬜ pending |
| TBD-resources-read | resources | 2 | CLI-04 | T-04-01 | `resources/read` returns 404-style MCP error for missing artifact (not empty content); MIME types match D-04 map | e2e (httpx) | `uv run pytest tests/e2e/test_resources.py::test_read -v` | ❌ W0 | ⬜ pending |
| TBD-resources-mime | resources | 2 | CLI-04 | — | `.json`→`application/json`, `.txt`/`.log`→`text/plain`, `.md`→`text/markdown`, else `application/octet-stream` | unit | `uv run pytest mcp-gateway/tests/test_resources_mime.py -v` | ❌ W0 | ⬜ pending |
| TBD-cc-template | claude-code | 1 | CLI-01, CLI-03 | — | `templates/claude-code/.mcp.json` parses as valid JSON and matches the `--remote` ready-block byte-for-byte except placeholders | unit | `uv run pytest mcp-gateway/tests/test_claude_code_template.py -v` | ❌ W0 | ⬜ pending |
| TBD-cc-smoke | claude-code | 3 | CLI-01 | T-04-02 (auth bypass) | `initialize` → `tools/list` → `tools/call(list_uploads)` succeeds with bearer header; same flow returns 401 without it | e2e (httpx) | `uv run pytest tests/e2e/test_claude_code_smoke.py -v` | ❌ W0 | ⬜ pending |
| TBD-cc-uat | claude-code | — | CLI-01 | — | Manual UAT checklist passes against a real Claude Code session (`/mcp` connect, tool call, resource browse) | manual | See `04-UAT.md` (created with plans) | n/a | ⬜ pending |
| TBD-print-config | print-config | 1 | CLI-01 | — | `./run_docker.sh --print-config` prints same ready-block as `--remote`; exits non-zero with hint when no token file present | unit (bats or pytest+subprocess) | `uv run pytest mcp-gateway/tests/test_print_config.py -v` | ❌ W0 | ⬜ pending |
| TBD-mastra-pkg | mastra | 1 | CLI-02, CLI-03 | — | `templates/mastra/package.json` pins `@mastra/mcp` to `~1.3.1`, declares `@mastra/core` per D-08; `tsconfig.json`/`.env.example` present | unit | `uv run pytest mcp-gateway/tests/test_mastra_template.py -v` | ❌ W0 | ⬜ pending |
| TBD-mastra-starter | mastra | 3 | CLI-02 | — | Starter completes the full triage happy path: connect → upload → run_triage → fetch report; exits 0; stdout contains expected milestone markers | e2e (subprocess) | `uv run pytest tests/e2e/test_mastra_starter.py -v` | ❌ W0 | ⬜ pending |
| TBD-readme-rewrite | docs | 3 | (CLI-03 indirect) | — | Top-level `README.md` opens with two-mode framing; references `templates/claude-code/.mcp.json`, `templates/mastra/`, `./run_docker.sh --remote`, `--print-config`, and `mare://cases/...` URIs | unit (grep-based) | `uv run pytest mcp-gateway/tests/test_readme_structure.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `mcp-gateway/tests/e2e/__init__.py` — empty init for pytest discovery
- [ ] `mcp-gateway/tests/e2e/conftest.py` — fixtures: `gateway_url`, `gateway_token`, `mcp_session` (httpx-based JSON-RPC helper); `pytest.skip` when no gateway reachable
- [ ] `mcp-gateway/tests/e2e/test_claude_code_smoke.py` — stubs for CLI-01 (initialize/tools/list/tools/call + auth-failure case)
- [ ] `mcp-gateway/tests/e2e/test_mastra_starter.py` — stub running `npm install && npm start` in temp working copy of `templates/mastra/`
- [ ] `mcp-gateway/tests/e2e/test_resources.py` — stubs for CLI-04 (resources/list, resources/read, missing-artifact error)
- [ ] `mcp-gateway/tests/test_resources_mime.py` — pure unit test for MIME map (no gateway needed)
- [ ] `mcp-gateway/tests/test_claude_code_template.py` — JSON-shape parsing of `templates/claude-code/.mcp.json`
- [ ] `mcp-gateway/tests/test_mastra_template.py` — package.json field assertions
- [ ] `mcp-gateway/tests/test_print_config.py` — subprocess invocation of `./run_docker.sh --print-config`
- [ ] `mcp-gateway/tests/test_readme_structure.py` — grep-style assertions on top-level README sections

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Claude Code session against running container | CLI-01 | Validates the **actual** Claude Code binary's behavior; httpx smoke only proves wire compatibility | See `04-UAT.md`: 1) start container with `./run_docker.sh --remote`, 2) copy ready-block into host `~/.claude/.mcp.json`, 3) open Claude Code, 4) confirm `mare` MCP connects, 5) run a tool call (`list_uploads`), 6) browse a resource, 7) confirm result rendering |
| Mastra-in-existing-project drop-in snippet | CLI-02, CLI-03 | The 5-10 line snippet from `templates/mastra/README.md` (D-09) is meant for users with their OWN mastra app — not testable in a hermetic harness | Manual: copy snippet into a fresh mastra project, run, confirm tool listing |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s (full e2e suite)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
