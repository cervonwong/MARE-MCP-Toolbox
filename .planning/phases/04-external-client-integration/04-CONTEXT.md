# Phase 4: External Client Integration - Context

**Gathered:** 2026-04-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire Claude Code (host) and mastra.ai agents to the running container's MCP gateway and prove they can run complete malware-analysis workflows end-to-end. Delivers four user-facing capabilities:

1. **Claude Code config (CLI-01, CLI-03)** — a checked-in `.mcp.json` template plus a runtime `--print-config` helper alongside the existing `run_docker.sh --remote` boot-time print block.
2. **Mastra.ai config (CLI-02, CLI-03)** — a runnable starter project that exercises the full pipeline, plus a drop-in snippet for users (including the project owner) who already have an existing mastra project.
3. **MCP Resources for case artifacts (CLI-04)** — every pipeline artifact under `/agent/status/<case>/` is browsable through `resources/list` + `resources/read` under a `mare://cases/<case>/<artifact>` URI scheme.
4. **End-to-end verification** — automated smoke tests that prove both clients actually talk to the gateway over Streamable HTTP, plus a top-level README rewrite covering the full local + remote story.

Out of scope (rolled to v2 or later):
- MCP Prompts exposing orchestrator workflows (GW-V2-01).
- Resource update notifications / `resources/subscribe` (GW-V2-02 — depends on multi-session lifecycle).
- Multi-session / concurrent independent analyses (GW-V2-03).
- Per-tool scopes / multi-user auth (out of scope per Phase 2 D-18).
- Replacing the boot-time `run_docker.sh --remote` print UX (Phase 3 D-07 — that stays canonical).

</domain>

<decisions>
## Implementation Decisions

### MCP Resources (CLI-04)
- **D-01:** URI scheme is **`mare://cases/<case>/<artifact>`** — custom `mare://` scheme, hierarchical, namespaced. Example: `mare://cases/000-mfc42ul.dll/sample-profile.json`. The `/cases/` segment leaves room for future top-level namespaces (e.g., `mare://uploads/...` later) without breaking existing URIs.
- **D-02:** `resources/list` enumerates **all cases** under `/agent/status/` (mirrors the existing `list_cases()` tool), not just the active case. Browseable across the whole library — clients see everything that exists in the container without having to rotate `set_active_case`. Active case state remains relevant for tool calls (Phase 2 D-04) but does NOT gate resource listing.
- **D-03:** Expose **all 13 pipeline artifacts** as resources (sample profile, strings, imports, YARA results, CAPA results, ranked signals, hypothesis, final report, status tree, etc., per `workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md`). Read-only; lazy-read on `resources/read`. Matches CLI-04's "browseable as MCP Resources" verbatim.
- **D-04:** **MIME types inferred from extension** at read time:
  - `.json` → `application/json`
  - `.txt` / `.log` → `text/plain`
  - `.md` → `text/markdown`
  - Anything else → `application/octet-stream`
  Keeps the gateway from having to maintain a hand-curated artifact-name → mime map.
- **D-05:** **Uploads are NOT exposed as resources.** They remain accessible through the existing `list_uploads()` / `get_sample_info()` tools only. Rationale: avoid streaming raw binary blobs (potentially up to 1 GB per Phase 2 D-14) through `resources/read`, and CLI-04 specifically says "case artifacts" — uploads are inputs, not artifacts.

### Mastra.ai template (CLI-02, CLI-03)
- **D-06:** Ship a **full runnable starter project** at `templates/mastra/` containing `package.json` + `tsconfig.json` + `.env.example` + `src/index.ts` + `README.md`. User clones the folder, copies `.env.example` to `.env`, pastes their bearer token, runs `npm install && npm start` — works without further modification (CLI-03 wording).
- **D-07:** The starter demonstrates the **full triage happy path**: connect → upload sample → call `run_triage` → fetch the resulting report. Single-script (`src/index.ts`); exercises the `/upload` endpoint and the gateway-native pipeline tools so success criterion 2 is unambiguously met.
- **D-08:** **Pin `@mastra/mcp` to `1.3.x`** and `@mastra/core` to latest. Matches CLAUDE.md "Version Compatibility Matrix" — predictable for users and documented as the tested combination. Avoid caret-range or unpinned to prevent silent breakage when mastra ships breaking minors.
- **D-09:** The starter's `README.md` ALSO carries a **5-10 line drop-in `MCPClient` snippet** for users with an existing mastra project (covers the project owner's own integration use case). One file, two audiences.

### Claude Code template (CLI-01, CLI-03)
- **D-10:** Ship `templates/claude-code/.mcp.json` — a bare, working snippet with placeholder values (e.g., `TOKEN-HERE`, `HOST-HERE`, `PORT-HERE`) that the user substitutes by hand if they're working from the file rather than the boot-time print. The file is the **reference**; the `run_docker.sh --remote` print block (Phase 3 D-07) remains the **canonical onboarding UX** for first-time users. No `.example` suffix — keep it discoverable as a real `.mcp.json` shape.
- **D-11:** Add **`./run_docker.sh --print-config`** flag. Reads `workspace/.mcp-gateway-token` for the running container and re-renders the same ready-block emitted at `--remote` startup. Useful when scrollback is gone, the user wants to share onboarding info, or the container was started without `--remote` printing. Does not start/stop the container — pure print. If no token file exists yet (no remote container running), exit non-zero with a hint.

### End-to-end verification
- **D-12:** **CLI-01 verification = both** (a) an automated raw-MCP smoke test using Python `httpx`, hitting `/mcp` with the bearer header and exercising `initialize` → `tools/list` → `tools/call` (mimics what Claude Code does at the protocol level — reproducible in CI, no Claude Code binary needed); AND (b) a documented manual UAT checklist describing the exact steps to validate a real Claude Code session against the container (used as the human-signoff gate for shipping).
- **D-13:** **CLI-02 verification = the `templates/mastra/` starter doubles as the test.** A pytest case (or bash wrapper invoked from pytest) runs `npm install && npm start` against a running gateway in a temp working dir and asserts on the script's stdout/exit code. Killing two birds: the template is verified to actually work, and we don't maintain a separate parallel mastra harness.
- **D-14:** **CLI-04 verification** is a dedicated automated test that issues `resources/list` then `resources/read` against an existing case. Asserts: URI scheme matches `mare://cases/...`, MIME types are correct (per D-04), resource content is non-empty for at least one artifact. Uses the same Python `httpx` smoke harness as D-12.
- **D-15:** New e2e tests live at **`mcp-gateway/tests/e2e/`** — co-located with existing gateway tests. Reuses the pytest config already in `mcp-gateway/pyproject.toml` (`asyncio_mode = "auto"`, `addopts = "-ra"`). The `e2e/` subdir keeps these separable from unit tests so CI can opt in/out (e2e requires a running gateway; unit tests don't).

### Documentation (folded into this phase)
- **D-16:** **Full top-level `README.md` rewrite is in scope for Phase 4** — single coherent doc covering: install, local mode (`./run_docker.sh`), remote mode (`./run_docker.sh --remote`), Claude Code config (with checked-in template reference), mastra.ai config (with starter reference), and resource browsing. Phase 3's deferred "README rewrite covering the new --remote workflow" is ABSORBED here so users get one-stop docs after Phase 4 lands. `mcp-gateway/README.md` may receive a small client-integration update too, but the top-level README is the canonical user entry point.

### Claude's Discretion
- Exact placeholder syntax inside `templates/claude-code/.mcp.json` (e.g., `TOKEN-HERE` vs `<paste-token>` vs `$MCP_GATEWAY_TOKEN`). Pick whatever reads as obviously-not-a-real-value.
- Node version pin and `engines` field in `templates/mastra/package.json` (likely `>=18` or `>=20`).
- Whether `templates/mastra/src/index.ts` uses a hardcoded sample path / sha256 or accepts a CLI arg. Pragma: easiest demo is fine.
- Whether `--print-config` reuses an extracted bash function (`print_ready_block()`) or duplicates the heredoc. Refactor only if low-cost.
- Resource content size cap inside `resources/read` — do we stream large `strings.txt` files in full, or truncate at, e.g., 1 MiB with a "truncated" marker? Default to "read whole file" unless this proves problematic; revisit on first-pain.
- Whether to also touch `mcp-gateway/README.md` in addition to the top-level README rewrite (D-16) — planner can decide based on overlap.
- Logging/error shape for `resources/read` when an artifact file is missing (case exists but pipeline didn't run that step yet). Likely return a structured MCP error rather than empty content.
- Test fixture choice for the e2e harness — reuse `examples/mfc42u.dll` in the workspace or generate a tiny synthetic binary. Use what's already there if reasonable.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level specs
- `.planning/PROJECT.md` — Core value, dual-mode constraint, security/licensing, Out-of-Scope items
- `.planning/REQUIREMENTS.md` — CLI-01..CLI-04 full text; backend (GW-*) and infra (INF-*) constraints
- `.planning/ROADMAP.md` — Phase 4 goal, success criteria, depends-on Phase 3
- `CLAUDE.md` (project root) — Recommended Stack: `@mastra/mcp` 1.3.x + `@mastra/core` latest, Streamable HTTP transport, bearer auth, "Do NOT Use" list (mcp-remote CVE, MastraMCPClient legacy, SSE-only)

### Prior phase context
- `.planning/phases/01-ida-pro-backend/01-CONTEXT.md` — idalib-mcp transport (`/mcp` on 127.0.0.1:8745), backend priority chain, no-silent-fallback policy
- `.planning/phases/02-mcp-gateway/02-CONTEXT.md` — Gateway architecture, env vars, token file location, tool surface (D-01..D-20), pass-through model (D-07), `get_active_backend` (D-07), upload mechanism (D-11..D-15), single-session active-case state (D-04)
- `.planning/phases/03-container-integration/03-CONTEXT.md` — `run_docker.sh --remote` flow (D-01..D-12), token discovery + Claude Code .mcp.json print block (D-07), `MCP_GATEWAY_HOST_BIND/HOST_PORT` env vars (D-04..D-06), `MCP_GATEWAY_ENABLED` guard (D-10/D-11)

### MCP / library references
- [MCP Resources spec (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/server/resources) — `resources/list`, `resources/read`, URI conventions, MIME types
- [MCP Transports spec (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — Streamable HTTP, headers, session handling (already pinned in Phase 2)
- [MCP Python SDK (`mcp` 1.27.x)](https://pypi.org/project/mcp/) — `FastMCP.resource()` decorator, `list_resources` / `read_resource` semantics
- [@mastra/mcp on npm](https://www.npmjs.com/package/@mastra/mcp) — `MCPClient` URL transport, auto Streamable HTTP detection
- [Mastra MCPClient docs](https://mastra.ai/reference/tools/mcp-client) — connection config, tool consumption patterns
- [Claude Code MCP docs](https://code.claude.com/docs/en/mcp) — `.mcp.json` `type: "http"` + Authorization header

### Orchestrator artifact contract (drives Resources)
- `workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md` — **The 13-artifact list with schemas. Source of truth for which files become resources under `mare://cases/<case>/...`.**
- `workspace/.claude/skills/malware-analysis-orchestrator/references/workflow.md` — Phase ordering — informs which artifacts may be missing for in-progress cases (relevant for Resources error handling)

### Existing code to extend / modify
- `mcp-gateway/src/mcp_gateway/app.py` — Where to register Resources alongside tools (`mcp.resource()` calls inside `build_app()` / a new `tools/resources.py` module)
- `mcp-gateway/src/mcp_gateway/tools/cases.py` — `list_cases()` already enumerates `/agent/status/<case>` dirs; Resources logic should reuse the same path resolution
- `mcp-gateway/src/mcp_gateway/tools/samples.py` — `STATUS_ROOT`, `UPLOADS_ROOT`, `resolve_sample()` constants/helpers
- `mcp-gateway/tests/` — Existing pytest harness; new `tests/e2e/` subdir
- `run_docker.sh` (lines 297-345 — the ready-block heredoc) — Extract into a function reusable by a new `--print-config` branch
- `compose.yaml` / `compose.remote.yaml` — Should not need changes for Phase 4 (port + env wiring done in Phase 3)
- `README.md` (top-level) — Full rewrite (D-16)

### New files Phase 4 will create
- `templates/claude-code/.mcp.json` — checked-in CC config (D-10)
- `templates/mastra/{package.json,tsconfig.json,.env.example,README.md,src/index.ts}` — runnable starter (D-06..D-09)
- `mcp-gateway/src/mcp_gateway/tools/resources.py` (likely name) — Resources registration (D-01..D-05)
- `mcp-gateway/tests/e2e/test_claude_code_smoke.py` — CLI-01 raw-MCP smoke (D-12)
- `mcp-gateway/tests/e2e/test_mastra_starter.py` — CLI-02 starter run (D-13)
- `mcp-gateway/tests/e2e/test_resources.py` — CLI-04 resources flow (D-14)
- (Possibly) `mcp-gateway/tests/e2e/conftest.py` — fixture that boots the gateway / asserts a running container

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Boot-time ready-block** (`run_docker.sh` lines 297-345): The Claude Code `.mcp.json` snippet, smoke-curl, and bearer warning are already rendered correctly. Phase 4 just needs to extract this into a function so `--print-config` can reuse it without re-running compose.
- **Token file path** (`workspace/.mcp-gateway-token`, written by gateway at startup, surfaced via the `${HOST_PWD}:/agent` bind mount): Already populated for any running `--remote` container — `--print-config` reads this same file.
- **Gateway tool surface** (`mcp-gateway/src/mcp_gateway/tools/{cases,samples,artifacts,workflows,disasm}.py`): 21 gateway-native tools already registered via `register_all_tools(mcp)` in `app.py`. Adding Resources is a parallel pattern (`@mcp.resource()` instead of `@mcp.tool()`).
- **Case enumeration logic** (`tools/cases.py:list_cases`): Iterates `/agent/status/` for dirs matching `^\d{3}-.+`. Resources reuse this; no second source of truth.
- **Status/uploads roots** (`tools/samples.py`): `STATUS_ROOT = Path("/agent/status")`, `UPLOADS_ROOT = Path("/agent/uploads")`. Resources logic imports these constants directly.
- **`get_active_backend()` tool** (`tools/cases.py`): Already exposed for client-side discovery; mastra/Claude Code starter examples reference it as the "what backend am I talking to?" probe.
- **pytest harness** (`mcp-gateway/pyproject.toml` `[tool.pytest.ini_options]`): `asyncio_mode = "auto"`, `addopts = "-ra"`, `testpaths = ["tests"]`. New `tests/e2e/` subdir inherits config automatically.
- **Existing gateway smoke** (Phase 2 plan 05 added e2e smoke tests): Plan can reference whatever patterns those use rather than inventing harness from scratch.

### Established Patterns
- **FastMCP decorator registration**: `@mcp.tool()` (gateway-native) and `@mcp.resource()` (Phase 4 addition) both registered inside a `register(mcp: FastMCP)` function exported by each module under `tools/`. `register_all_tools(mcp)` calls each.
- **Path-resolution helpers in `samples.py`**: `resolve_sample()`, `STATUS_ROOT`, `UPLOADS_ROOT`. Resources code imports rather than recomputes.
- **Pinned-backend lifespan**: `app.py`'s lifespan context already manages backend session lifetime. Resources do NOT touch backend — they read filesystem only — so they can register before lifespan and stay live regardless of backend health.
- **Heredoc-based user-facing print blocks** (`run_docker.sh` ready-block): Existing convention; `--print-config` follows it.
- **Templates folder convention**: New top-level `templates/` directory mirrors how other RE-tool projects ship `examples/` or `templates/` for client wiring. Distinct from `examples/` (which in this repo holds binary samples like `mfc42u.dll`) — name chosen to avoid conflation.

### Integration Points
- **`mcp-gateway/src/mcp_gateway/tools/__init__.py`** (`register_all_tools` entry point): Add a call to register Resources from a new `resources.py` module. One-line change.
- **`mcp-gateway/src/mcp_gateway/app.py`**: No structural change — `register_all_tools(mcp)` already runs before lifespan. Resources registered there.
- **`run_docker.sh`**: New `--print-config` branch in the flag parser at the top, handler near the `--remote` block. Extract lines 297-345 into a function (`print_ready_block "$TOKEN" "$DISPLAY_HOST" "$MCP_GATEWAY_HOST_PORT"`) so both `--remote` post-up and `--print-config` use the same code.
- **`templates/`** (new): Top-level directory. Conventions in this repo place tool-config under repo root (`compose.yaml`, `Dockerfile`, etc.); `templates/` joins that level.
- **`mcp-gateway/tests/e2e/`** (new subdir): pytest auto-discovers; no config change needed beyond an empty `__init__.py` if desired.
- **`README.md`** (top-level rewrite): Replaces existing content. Reference-paths to templates under `templates/...` and to `run_docker.sh --remote` / `--print-config` flows.

</code_context>

<specifics>
## Specific Ideas

- The mastra README snippet (D-09) should be paste-ready: `import { MCPClient } from '@mastra/mcp'; const client = new MCPClient({ servers: { mare: { url: 'http://localhost:8080/mcp', requestInit: { headers: { Authorization: \`Bearer ${process.env.MARE_TOKEN}\` } } } } });` — concrete, not pseudocode. Project owner (and any user with an existing mastra setup) reads ONE block and integrates.
- The Claude Code config template (D-10) should match the boot-time print block byte-for-byte except for placeholders — so users coming back to the file after running `--remote` once recognize the shape immediately.
- `--print-config` (D-11) should fail loudly when no token file exists: print `[error] no token file at workspace/.mcp-gateway-token — start the container first with: ./run_docker.sh --remote` and exit non-zero. Do NOT silently invent values.
- Resources error semantics (D-04, D-05): when a case exists but a specific artifact is missing (pipeline didn't run that stage yet), `resources/read` should return a structured MCP error rather than empty bytes. Helps clients distinguish "in progress" from "broken".
- README rewrite (D-16) should open with a "two-mode" framing: "Run agents inside the container (local) OR connect external clients to the container's gateway (remote)". The dual-mode story IS the headline of v2.
- E2E tests (D-12..D-15) MUST be runnable against a running container, not require restarting it. Phase 3 set up `--remote` to be detached; tests just need a token + URL pair.
- Bearer token is the sole auth mechanism (Phase 2 D-12, D-18; Phase 3 specifics). Phase 4 must not introduce a second auth surface (no per-client tokens, no scopes, no OAuth).

</specifics>

<deferred>
## Deferred Ideas

- **Resource update notifications** (`notifications/resources/list_changed`, `resources/subscribe`) — depends on multi-session lifecycle; v2 (GW-V2-02 / GW-V2-03).
- **MCP Prompts exposing orchestrator workflows as templates** — v2 (GW-V2-01).
- **Multi-session / concurrent independent analyses** — v2 (GW-V2-03). Phase 4 keeps single-process active-case state from Phase 2 D-04.
- **Truncation/streaming of very large artifacts in `resources/read`** — pragma "read whole file" until first pain; revisit if a real artifact exceeds practical sizes.
- **Per-tool / per-resource scopes / fine-grained auth** — out of scope per Phase 2 D-18; bearer-only.
- **OAuth 2.1 client flow** — explicitly Out of Scope (PROJECT.md, REQUIREMENTS.md).
- **Uploads as MCP Resources** (`mare://uploads/<sha256>/<filename>`) — explicitly rejected (D-05). If a future phase needs binary content browsability, revisit with a streaming-aware URI scheme.
- **Backend comparison mode / unified disasm normalization** — v2 (DIS-V2-01, DIS-V2-02).
- **Codex on-host config template (similar to Claude Code's `.mcp.json`)** — not in CLI-01..CLI-04 scope. If Codex starts shipping host-side MCP support beyond Claude Code, add a `templates/codex/` follow-up.
- **mcp-gateway/README.md polish** — may be touched lightly during Phase 4 (D-16's "may also receive a small update"), but a thorough rewrite of that package-level doc is a follow-up if the top-level README absorbs the user-facing story.
- **CI wiring for the e2e tests** — D-15 places the tests in `mcp-gateway/tests/e2e/`; whether they run in a CI pipeline (and which one) is out of scope for this phase. Tests must be runnable locally; CI integration is a separate concern.

</deferred>

---

*Phase: 04-external-client-integration*
*Context gathered: 2026-04-27*
