---
phase: 04-external-client-integration
verified: 2026-04-27T12:00:00Z
status: passed
score: 4/4 must-haves verified (automated + human)
re_verification: true
last_human_signoff: 2026-05-11
human_signoff_by: administrator@leongs-house.dev

human_verification:
  - test: "Walk through 04-UAT.md checklist: start container --remote, connect Claude Code with template, invoke tools, browse resources"
    expected: "All 8 UAT sections pass; signoff line completed with name and date"
    status: PASSED (2026-05-11) — all 8 sections checked off, signoff line filled. Driven via `claude --mcp-config --strict-mcp-config` (CLI binary, not just raw HTTP). One v1.1 finding recorded: F-1 (image-hash misses `mcp-gateway/` changes).
  - test: "Run `npm install && npm start <sample>` from templates/mastra/ against a running gateway"
    expected: "Stdout shows 'Tools available:', 'Uploaded:', 'Triage result:', 'Report excerpt:' markers"
    why_human: "Requires a running Docker container with the MCP gateway, Node.js 20+ on the host, and an end-to-end triage that takes 90-180s. The e2e test (test_mastra_starter.py) covers this when a gateway is up."
    status: deferred (CLI-02 covered by automated e2e + runnable starter; manual run not blocking)
---

# Phase 4: External Client Integration Verification Report

**Phase Goal:** Claude Code on the host and mastra.ai agents can connect to the containerized tools and run complete analysis workflows
**Verified:** 2026-04-27T12:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Claude Code on the host connects using the `.mcp.json` template and can invoke analysis tools | ✓ VERIFIED (automated) | `templates/claude-code/.mcp.json` exists with `type:"http"`, `Bearer ${MARE_GATEWAY_TOKEN}`, `${MARE_GATEWAY_URL:-...}` env-var expansion; e2e smoke test exercises `initialize → tools/list → tools/call` + auth-bypass 401 checks |
| 2 | A mastra.ai agent connects via MCPClient and runs analysis workflows | ✓ VERIFIED (automated) | `templates/mastra/src/index.ts` implements full triage happy path (connect → upload → run_triage → get_artifact) using `MCPClient` from `@mastra/mcp ~1.3.1`; e2e test validates via subprocess |
| 3 | Pre-built config templates for both Claude Code and mastra.ai work without modification beyond token | ✓ VERIFIED (automated) | Both `templates/claude-code/.mcp.json` and `templates/mastra/` starter project exist; README.md documents both with drop-in snippets; 8+14 unit tests enforce shape/pins/conventions |
| 4 | Case artifacts are browsable as MCP Resources by connected clients | ✓ VERIFIED (automated) | `tools/resources.py` registers `mare://cases/<case>/<artifact>` URI template + dynamic `list_resources` handler; 13 ARTIFACTS per artifact-spec.md; MIME map, path-traversal protection, wired in `__init__.py` |

**Score:** 4/4 truths verified (automated level)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `templates/claude-code/.mcp.json` | Claude Code MCP config (CLI-01, CLI-03) | ✓ VERIFIED | Valid JSON; `type:http`; `Bearer ${MARE_GATEWAY_TOKEN}`; `${MARE_GATEWAY_URL:-http://localhost:8080/mcp}`; no banned tech |
| `run_docker.sh` (print_ready_block + --print-config) | Refactored ready-block function + flag | ✓ VERIFIED | `print_ready_block()` defined at line 34, called from both `--remote` (line 367) and `--print-config` (line 96); `--print-config` flag in parser at line 13 |
| `mcp-gateway/src/mcp_gateway/tools/resources.py` | MCP Resources module (CLI-04) | ✓ VERIFIED | 13 ARTIFACTS tuple, `_mime_for()`, `_list_cases()`, `_build_resource_list()`, `_safe_artifact_path()` with triple validation (regex + allowlist + realpath), `register(mcp)` with two-pronged registration |
| `mcp-gateway/src/mcp_gateway/tools/__init__.py` | Resources module wired | ✓ VERIFIED | Line 14 imports `resources`; line 19 calls `resources.register(mcp)` |
| `templates/mastra/package.json` | Mastra starter manifest (CLI-02) | ✓ VERIFIED | `@mastra/mcp ~1.3.1` (D-08 pin); `@mastra/core ^1.28.0`; `engines.node >= 20`; start script `tsx src/index.ts` |
| `templates/mastra/src/index.ts` | Full triage happy path | ✓ VERIFIED | 100 lines; `MCPClient` connection, `POST /upload`, `mare_run_triage`, `mare_get_artifact`, `mare_list_cases` fallback; stdout markers match e2e assertions |
| `templates/mastra/.env.example` | Locked env-var docs | ✓ VERIFIED | `MARE_GATEWAY_TOKEN=` (empty); `MARE_GATEWAY_URL=http://localhost:8080/mcp` |
| `templates/mastra/README.md` | Setup + drop-in snippet (D-09) | ✓ VERIFIED | Quick start, drop-in `MCPClient` snippet, gotchas section; no literal banned-tech strings |
| `README.md` | Two-mode onboarding doc (D-16, CLI-03) | ✓ VERIFIED | 191 lines; "Two ways to use this" framing; references `templates/claude-code/.mcp.json`, `templates/mastra/`, `--remote`, `--print-config`, `mare://cases/`; `MARE_GATEWAY_TOKEN/URL` used uniformly |
| `.gitignore` | Template artifact exclusion | ✓ VERIFIED | Lines 29-31: `templates/**/node_modules/`, `templates/**/dist/`, `templates/**/.env` |
| `mcp-gateway/tests/test_claude_code_template.py` | CC template shape unit test | ✓ VERIFIED | 8 tests: existence, JSON parse, type=http, auth env var, URL env var, 3 banned-tech parametrize |
| `mcp-gateway/tests/test_print_config.py` | --print-config subprocess test | ✓ VERIFIED | 3 tests: help text, missing-token error, success with token |
| `mcp-gateway/tests/test_resources_mime.py` | MIME map unit test | ✓ VERIFIED | 9 parametrized cases covering .json, .txt, .log, .md, .bin, no-ext, uppercase |
| `mcp-gateway/tests/test_resources_unit.py` | Resources module unit test | ✓ VERIFIED | 9 tests: ARTIFACTS count/content, _list_cases, _build_resource_list, path-traversal rejection |
| `mcp-gateway/tests/test_mastra_template.py` | Mastra template static test | ✓ VERIFIED | 14 tests: file presence, pins, engines, env vars, MCPClient usage, triage path, drop-in snippet, banned-tech |
| `mcp-gateway/tests/test_readme_structure.py` | README structure test | ✓ VERIFIED | 11 tests: heading, two-mode framing, template references, flags, URI scheme, env vars, banned-tech |
| `mcp-gateway/tests/e2e/conftest.py` | E2E fixtures | ✓ VERIFIED | Session-scoped: `gateway_url`, `bearer_token` (env→file→skip), `gateway_alive` (/healthz→skip), `mcp_client` (httpx + initialize), `unauthed_client` |
| `mcp-gateway/tests/e2e/test_claude_code_smoke.py` | CLI-01 raw-MCP smoke | ✓ VERIFIED | 4 tests: initialize+tools/list, tools/call, missing-bearer-401, wrong-bearer-401 |
| `mcp-gateway/tests/e2e/test_resources.py` | CLI-04 resources e2e | ✓ VERIFIED | 5 tests: mare:// URI scheme, MIME types, read content, missing-artifact error, traversal rejection |
| `mcp-gateway/tests/e2e/test_mastra_starter.py` | CLI-02 mastra subprocess e2e | ✓ VERIFIED | 1 test: npm install + npm start with stdout marker assertions; skipif for npm/template/sample |
| `.planning/phases/04-external-client-integration/04-UAT.md` | Manual UAT checklist (CLI-01) | ⚠️ INCOMPLETE | File exists with 8 sections + signoff, but ALL checkboxes are `[ ]` (unchecked) and signoff line is blank — human gate not satisfied |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `templates/claude-code/.mcp.json` | `MARE_GATEWAY_TOKEN` env var | `${MARE_GATEWAY_TOKEN}` in headers.Authorization | ✓ WIRED | Exact match: `Bearer ${MARE_GATEWAY_TOKEN}` |
| `templates/claude-code/.mcp.json` | `MARE_GATEWAY_URL` env var | `${MARE_GATEWAY_URL:-http://localhost:8080/mcp}` in url | ✓ WIRED | Default fallback included |
| `run_docker.sh --print-config` | `workspace/.mcp-gateway-token` | Reads token file; exits 1 if missing | ✓ WIRED | Line 91-99: `TOKEN_FILE` check + `cat` read |
| `print_ready_block()` | `--remote` post-up AND `--print-config` | Function called from both branches | ✓ WIRED | Line 96 (--print-config) and line 367 (--remote) |
| `templates/mastra/src/index.ts` | `process.env.MARE_GATEWAY_TOKEN + MARE_GATEWAY_URL` | `dotenv/config` import + env reads | ✓ WIRED | Lines 18-19: `process.env.MARE_GATEWAY_TOKEN`, `process.env.MARE_GATEWAY_URL` |
| `templates/mastra/src/index.ts` | Gateway `/upload` + `/mcp` | `fetch POST /upload` then `MCPClient` | ✓ WIRED | Lines 51-62 (upload), lines 34-43 (MCPClient connect) |
| `tools/__init__.py` | `tools/resources.py register(mcp)` | `resources.register(mcp)` call | ✓ WIRED | Line 19 |
| `tools/resources.py` | `tools/cases.py CASE_NAME_RE` + `tools/samples.py STATUS_ROOT` | `from .cases import ...` / `from .samples import ...` | ✓ WIRED | Lines 18-19 |
| `README.md` | `templates/claude-code/.mcp.json` | Explicit path reference + code block | ✓ WIRED | Line 64: `templates/claude-code/.mcp.json` |
| `README.md` | `templates/mastra/` | Explicit path reference + npm instructions | ✓ WIRED | Line 89: `templates/mastra/` |
| `README.md` | `./run_docker.sh --remote` and `--print-config` | Command examples | ✓ WIRED | Lines 38, 53 |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CLI-01 | 04-01, 04-02, 04-05, 04-07 | Claude Code connects via `.mcp.json` with `type:"http"` + bearer token header | ✓ SATISFIED (automated) / ⚠️ HUMAN NEEDED (UAT) | Template at `templates/claude-code/.mcp.json`; --print-config in `run_docker.sh`; e2e smoke + auth tests; UAT.md exists but **not signed off** |
| CLI-02 | 04-04, 04-05 | Mastra.ai connects via `MCPClient` over Streamable HTTP | ✓ SATISFIED | `templates/mastra/` starter with `MCPClient`; e2e subprocess test |
| CLI-03 | 04-01, 04-04, 04-06 | Pre-built config templates provided for both clients | ✓ SATISFIED | `templates/claude-code/.mcp.json`, `templates/mastra/`, `README.md` with two-mode framing and drop-in snippets |
| CLI-04 | 04-03, 04-05 | MCP Resources expose case artifacts as browsable resources | ✓ SATISFIED | `tools/resources.py` with 13 ARTIFACTS, MIME map, `mare://cases/<case>/<artifact>` URIs; e2e resources test |

**No orphaned requirements** — all Phase 4 requirement IDs (CLI-01, CLI-02, CLI-03, CLI-04) are claimed by at least one plan and verified above.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `resources.py` | 63 | `return []` in `_list_cases()` when STATUS_ROOT missing | ℹ️ Info | Correct behavior — returns empty list when no cases exist, not a stub |

No blocker or warning anti-patterns found. No TODO/FIXME/PLACEHOLDER in Phase 4 deliverables. No `mcp-remote`, `MastraMCPClient`, or `MastraMCPClient` in template or README deliverables (only in test assertions that verify their absence). No empty implementations in `index.ts` or `resources.py`.

### Human Verification Required

### 1. Claude Code UAT Walkthrough (CLI-01)

**Test:** Walk through all 8 sections of `.planning/phases/04-external-client-integration/04-UAT.md` on a workstation with Claude Code + Docker
**Expected:** All checkboxes checked; signoff line completed with operator name and date
**Why human:** Claude Code binary config discovery, `${VAR}` env-var expansion at parse time, MCP panel "connected" rendering, and tool-call UX cannot be verified programmatically. The Plan 07 SUMMARY claims human approval, but the actual `04-UAT.md` shows 0 checked boxes and a blank signoff line — the documented evidence contradicts the claim.

### 2. Mastra Starter End-to-End (CLI-02)

**Test:** `cd templates/mastra && cp .env.example .env && npm install && npm start ../../workspace/examples/samples/mfc42ul.dll`
**Expected:** Stdout shows "Tools available:", "Uploaded:", "Triage result:", "Report excerpt:" markers
**Why human:** Requires running Docker container with the MCP gateway, Node.js 20+ on the host, and a full triage analysis cycle (90-180s). The e2e test (`test_mastra_starter.py`) covers this when the gateway is available, but that test skips cleanly when no gateway is running.

### Gaps Summary

All four automated truth checks pass — every artifact exists, is substantive, and is correctly wired. The `mare://cases/<case>/<artifact>` resource scheme, Claude Code `.mcp.json` template, mastra starter project, `--print-config` flag, and README documentation are all present and structurally sound.

**One process gap exists:** The Plan 07 SUMMARY claims "Human walked through the checklist and approved — CLI-01 manual UAT gate satisfied," but the actual `04-UAT.md` file shows zero checked boxes (`[ ]` only, no `[x]`) and the signoff line is blank (`_signed_ ____________ _date_ ___________`). The documented evidence does not support the completion claim for the human-action checkpoint.

This is classified as `human_needed` rather than `gaps_found` because:
- All functional artifacts are complete and correctly wired
- The automated verification passes all checks
- The gap is procedural (UAT signoff documentation) rather than functional (missing/broken code)
- A human walking the UAT checklist would be the correct next step to close this gap

---

_Verified: 2026-04-27T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
