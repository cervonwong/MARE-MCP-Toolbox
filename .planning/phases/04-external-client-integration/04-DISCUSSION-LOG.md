# Phase 4: External Client Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-27
**Phase:** 04-external-client-integration
**Areas discussed:** MCP Resources design (CLI-04), Mastra.ai template scope, Claude Code template delivery, End-to-end verification, Documentation scope

---

## Gray-area selection

| Option | Description | Selected |
|--------|-------------|----------|
| MCP Resources design (CLI-04) | URI scheme, scope, mime types, which artifacts to expose | ✓ |
| Mastra.ai template scope | One-file vs starter project, location, workflow demonstrated | ✓ |
| Claude Code template delivery | Checked-in template + `--print-config` flag vs boot-time print only | ✓ |
| End-to-end verification | Automated MCP smoke vs manual UAT vs both; test home | ✓ |

**User selected:** all four areas. (README/docs scope was added as a follow-up question after the four primary areas resolved.)

---

## MCP Resources design (CLI-04)

### Q: What URI scheme for case artifacts?

| Option | Description | Selected |
|--------|-------------|----------|
| `mare://cases/<case>/<artifact>` (Recommended) | Custom mare:// scheme, hierarchical, namespaced, future-proof | ✓ |
| `file:///agent/status/<case>/<file>` | Use file:// pointing at actual paths; mixes filesystem semantics into MCP namespace | |
| Flat `mare:///<case>/<artifact>` | Skip /cases/ segment, no future namespacing for non-case resources | |

**User's choice:** `mare://cases/<case>/<artifact>` — custom scheme with hierarchical /cases/ segment.

### Q: Which cases should appear in list_resources?

| Option | Description | Selected |
|--------|-------------|----------|
| All cases under /agent/status/ (Recommended) | Browseable across whole library; matches list_cases() tool | ✓ |
| Active case only | Smaller surface; client must rotate active case | |
| Active case + uploads index | Hybrid; more URIs to maintain | |

**User's choice:** All cases — full browseability.

### Q: Which of the 13 pipeline artifacts should be exposed as resources?

| Option | Description | Selected |
|--------|-------------|----------|
| All 13 artifacts (Recommended) | Full pipeline visibility: profile, strings, imports, yara, capa, signals, hypothesis, report, tree, etc. | ✓ |
| Final outputs only | Just sample profile, hypothesis, final report | |
| Skip raw blob artifacts (binary samples) | Exclude original .bin from resources | |

**User's choice:** All 13 artifacts — read-only, lazy-read.

### Q: How should MIME types be assigned?

| Option | Description | Selected |
|--------|-------------|----------|
| Infer from extension (Recommended) | .json → application/json, .txt/.md → text/plain or markdown, unknown → octet-stream | ✓ |
| Always text/plain | Simple but loses JSON semantics | |
| Always application/json | Forces wrapping for non-JSON | |

**User's choice:** Infer from extension.

### Q (follow-up): Should the upload directory be browseable as resources too?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, expose uploads as resources | Parallel to mare://cases | |
| No, keep uploads tool-only (Recommended) | Available via list_uploads / get_sample_info; avoids streaming raw blobs through MCP read_resource | ✓ |

**User's choice:** No — uploads stay tool-only.

---

## Mastra.ai template scope

### Q: What should the mastra.ai template look like?

| Option | Description | Selected |
|--------|-------------|----------|
| Full starter project (Recommended) | package.json + tsconfig + .env.example + src/index.ts + README; works out of the box | ✓ |
| Single agent.ts + README | One TS file showing MCPClient wiring | |
| Snippet in docs only | Documentation snippet, no checked-in runnable project | |

**User's choice:** Full starter project.
**Notes:** "i already have a separate mastra project that i want to use with this project as an MCP, but sure, we can create another full start project in a separate folder." — User has an existing mastra setup but agreed to ship a starter. Rationale for D-09's drop-in snippet (covers the "existing project" use case alongside the starter).

### Q: Where should the mastra template live in the repo?

| Option | Description | Selected |
|--------|-------------|----------|
| `templates/mastra/` (Recommended) | New top-level templates/ dir; pairs with templates/claude-code/ | ✓ |
| `examples/mastra-client/` | Conflicts with existing examples/ (binary samples) | |
| `mcp-gateway/templates/mastra/` | Co-locate with gateway package | |

**User's choice:** `templates/mastra/`.

### Q: What workflow should the mastra starter demonstrate?

| Option | Description | Selected |
|--------|-------------|----------|
| Triage one sample end-to-end (Recommended) | Connect, upload, run_triage, fetch report | ✓ |
| Tool-listing demo only | Connect, list tools, exit | |
| Two scripts: minimal + full | src/connect.ts + src/triage.ts | |

**User's choice:** Triage one sample end-to-end.

### Q: How to handle the mastra version pin?

| Option | Description | Selected |
|--------|-------------|----------|
| Pin to @mastra/mcp 1.3.x + @mastra/core latest (Recommended) | Matches CLAUDE.md compat matrix | ✓ |
| Use ^1.3 (caret range) | Allows minor upgrades; risks silent breakage | |
| Use latest unpinned | Fastest divergence | |

**User's choice:** Pin to @mastra/mcp 1.3.x + @mastra/core latest.

### Q (follow-up): Include a 'drop-in snippet' README for users with existing mastra projects?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, README snippet for existing projects (Recommended) | Covers project-owner use case + new-user case in one phase | ✓ |
| Starter project only | Skip inline snippet | |

**User's choice:** Yes — include the snippet.

---

## Claude Code template delivery

### Q: Should we ALSO ship a checked-in Claude Code config template?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, `templates/claude-code/.mcp.json.example` (Recommended) | Placeholder syntax {{TOKEN}}, pairs with templates/mastra/ | |
| Boot-time print only | Skip checked-in template; rely on run_docker.sh --remote | |
| `templates/claude-code/.mcp.json` (no .example) | Bare working snippet with TOKEN-HERE; simpler diff | ✓ |

**User's choice:** `templates/claude-code/.mcp.json` — bare snippet without `.example` suffix.

### Q: Add a way to re-print the config block without restarting the container?

| Option | Description | Selected |
|--------|-------------|----------|
| `./run_docker.sh --print-config` (Recommended) | New flag reads workspace/.mcp-gateway-token and re-renders the ready-block | ✓ |
| No — they can read the token file directly | Skip the flag | |
| Add it as a tiny standalone script (bin/print-mare-config.sh) | Separate script | |

**User's choice:** `./run_docker.sh --print-config` flag.

---

## End-to-end verification

### Q: How to verify CLI-01 (Claude Code connects + runs tools)?

| Option | Description | Selected |
|--------|-------------|----------|
| Automated raw-MCP curl/Python smoke test (Recommended) | Python httpx hits /mcp with bearer; reproducible in CI | |
| Manual UAT checklist | Human runs Claude Code on host | |
| Both: automated + manual UAT note | Smoke + checklist | ✓ |

**User's choice:** Both — automated smoke + manual UAT checklist.

### Q: How to verify CLI-02 (mastra.ai connects + runs workflow)?

| Option | Description | Selected |
|--------|-------------|----------|
| Run the templates/mastra/ starter as the test (Recommended) | Template doubles as smoke test via npm i && npm start | ✓ |
| Separate Python test using @mastra/mcp transcript shape | Replay byte-level MCP session | |
| Manual UAT only | Human runs starter, eyeballs report | |

**User's choice:** Run the starter as the test.

### Q: How to verify CLI-04 (Resources expose case artifacts)?

| Option | Description | Selected |
|--------|-------------|----------|
| Automated MCP resources/list + resources/read (Recommended) | Smoke harness asserts URI scheme + mime + content | ✓ |
| Folded into the Claude Code UAT | No standalone test | |
| Skip dedicated test | Trust unit tests | |

**User's choice:** Automated resources/list + resources/read test.

### Q: Where do the new e2e tests live?

| Option | Description | Selected |
|--------|-------------|----------|
| `mcp-gateway/tests/e2e/` (Recommended) | Co-located with existing gateway tests; reuses pytest config | ✓ |
| `tests/` at repo root | Top-level new harness | |
| `scripts/smoke/` shell scripts | Bash + curl + jq | |

**User's choice:** `mcp-gateway/tests/e2e/`.

---

## Documentation scope

### Q: Phase 3 deferred 'README rewrite covering --remote workflow' to after Phase 4. Fold it into Phase 4?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, full top-level README rewrite (Recommended) | Single coherent doc covering install, local mode, remote mode, both client configs, Resources | ✓ |
| Smaller scope: mcp-gateway/README.md update only | Leave top-level README rewrite as separate follow-up | |
| Keep deferred | Phase 4 ships templates + Resources only | |

**User's choice:** Yes — full top-level README rewrite folded into Phase 4.

---

## Claude's Discretion

Areas where the user explicitly deferred or left flexibility:

- Exact placeholder syntax inside `templates/claude-code/.mcp.json` (TOKEN-HERE vs alternatives)
- Node version pin in `templates/mastra/package.json`
- Whether the mastra starter accepts a CLI sample arg or hardcodes one
- Refactor scope when extracting the ready-block heredoc into a function
- Resource content size cap (truncation policy)
- Whether `mcp-gateway/README.md` is also touched alongside the top-level rewrite
- Error shape returned from `resources/read` for missing artifacts
- Test fixture choice (existing `examples/mfc42u.dll` vs synthetic binary)

## Deferred Ideas

- Resource update notifications + `resources/subscribe` (v2)
- MCP Prompts (GW-V2-01)
- Multi-session / concurrent analyses (GW-V2-03)
- Streaming/truncation of very large artifacts (revisit on first pain)
- Uploads as MCP Resources (explicitly rejected — would need streaming-aware scheme)
- Codex on-host MCP config template (not in CLI-01..CLI-04 scope)
- CI wiring for the new e2e tests (out of scope; tests must be runnable locally)
- mcp-gateway/README.md thorough rewrite (top-level README absorbs the user-facing story; package README is a follow-up if needed)
