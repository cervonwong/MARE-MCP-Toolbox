# Phase 2: MCP Gateway - Context

**Gathered:** 2026-04-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a curated FastMCP server that exposes a Streamable HTTP endpoint (Protocol 2025-03-26) on port 8080 with bearer-token auth, routing disassembler tool calls to whichever backend is installed (IDA > BN > Ghidra) and mapping the orchestrator skill's 13-artifact malware pipeline onto a unified MCP tool surface (15-25 tools). The gateway also serves a file-upload endpoint so remote clients can submit samples.

Out of scope (later phases): Docker Compose wiring & dual-mode entrypoint tuning (Phase 3), Claude Code/mastra.ai client configs (Phase 4), MCP Resources for artifacts (Phase 4), MCP Prompts / notifications / multi-session (v2).

</domain>

<decisions>
## Implementation Decisions

### Tool surface strategy
- **D-01:** Layered tool surface — ships BOTH composite workflow tools (e.g. `run_triage`, `run_deep_analysis`, `generate_report`) AND atomic pipeline tools. Clients choose granularity.
- **D-02:** Atomic tier = one tool per 13-artifact file. ~13 atomic tools + a handful of workflow/case tools + disassembler-routed tools ≈ 18-22 total (fits GW-02's 15-25 target).
- **D-03:** Tool naming uses **verb-first** style — `run_triage`, `decompile`, `collect_strings`, `scan_yara`, `list_functions`, `fetch_strings`, `get_xrefs`, `rank_signals`, `build_hypothesis`, `list_cases`, `get_artifact`, `set_active_case`. Avoid dotted namespaces; avoid underscored-by-domain (e.g. `case_list_artifacts`).
- **D-04:** Case/session state is exposed as tools: `list_cases`, `get_artifact(case_id, artifact_name)`, `set_active_case`, and related helpers. The gateway tracks the active case per MCP session. In Phase 4 these artifacts are additionally promoted to MCP Resources (CLI-04).
- **D-05:** No raw CLI passthrough (already ruled out in REQUIREMENTS.md Out of Scope). Every tool is a curated wrapper with a documented JSON schema.

### Gateway ↔ backend architecture
- **D-06:** Gateway acts as an **MCP client** to each disassembler backend's existing MCP server — it does NOT re-implement disassembler logic.
  - IDA path: gateway calls `http://127.0.0.1:8745/mcp` (idalib-mcp, already running as a background daemon started in Phase 1 by `agent-entrypoint.sh`).
  - BN path: gateway spawns `python3 /agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py` as a persistent stdio subprocess at gateway start.
  - Ghidra path: gateway spawns `python3 /agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py` as a persistent stdio subprocess at gateway start.
- **D-07:** Gateway aggregates the backend's tools and re-exposes them under the unified verb-first names (D-03). Client never sees backend-specific tool names. Backend-specific tools that don't have a unified equivalent are hidden (not exposed) in Phase 2 — only the GW-02 curated set is visible.
- **D-08:** Non-disassembler pipeline tools (`collect_strings`, `collect_imports`, `scan_yara`, `scan_capa`, `rank_signals`, `build_hypothesis`, etc.) **reuse the existing orchestrator skill's scripts** at `workspace/.claude/skills/malware-analysis-orchestrator/scripts/*`. The gateway tool handler shells out to those scripts and captures their output/status. This keeps the 13-artifact pipeline single-sourced so inner-container agents (INF-05) and remote clients run identical code.
- **D-09:** Gateway is started by `agent-entrypoint.sh` at container boot as a long-lived service alongside idalib-mcp. Backend detection reuses the logic from `docker-bin/configure-agent-mcp.sh` (IDA > BN > Ghidra priority, highest-priority installed wins). Detected backend is **pinned for the gateway's lifetime** — no dynamic switching mid-session.
- **D-10:** Gateway crashes/failures in the backend MCP subprocess fail loudly (structured MCP error); the gateway does NOT silently fall back to a lower-priority backend (same policy as Phase 1 D-06).

### File upload mechanism
- **D-11:** Uploads use a **separate HTTP POST endpoint** on the same port as the MCP server, not MCP base64 chunks. Endpoint: `POST /upload` (multipart form or raw body). Returns `{ "sample_id": "<sha256>", "path": "/agent/uploads/<sha256>/<name>", "size": <bytes> }`.
- **D-12:** Upload endpoint is protected by the **same bearer token** as the MCP endpoint (`Authorization: Bearer <token>`). Unauthenticated requests → 401.
- **D-13:** Samples stored at `/agent/uploads/<sha256>/<original_name>` (content-hashed dir, preserves original filename). Dedupes duplicate uploads. Lives on the `/agent` volume (same mount as the workspace) — persists across container restarts when the workspace dir is persistent.
- **D-14:** Default upload size cap: **1 GB**. Configurable via `MCP_GATEWAY_MAX_UPLOAD_MB` env var. Exceeding the cap returns a structured error (HTTP 413 for the upload endpoint, MCP error for tool-triggered paths).
- **D-15:** All sample-accepting tools resolve the `sample` parameter in two ways: (a) as a sha256 hash / `sample_id` from a previous upload, or (b) as a container-local path (e.g. `/agent/examples/foo.bin`). This keeps a single interface for remote clients and inner-container agents alike (preserves INF-05).

### Auth token lifecycle
- **D-16:** Token source: **env var wins, else auto-generate**. If `MCP_GATEWAY_TOKEN` is set (via compose, Docker env, or run_docker.sh), use it verbatim. Otherwise the gateway generates a cryptographically-random token at startup.
- **D-17:** Token is exposed to the user via BOTH: (a) writing it to `/agent/.mcp-gateway-token` (chmod 0600, owned by `agent`), AND (b) printing one-line log: `[gateway] Bearer token: <token>`. The log line can be suppressed with `MCP_GATEWAY_QUIET=1`. The file path is always written.
- **D-18:** Single token for the whole gateway — no per-tool scopes, no multi-user claims. Matches the "single-user or trusted-team local container" deployment model. OAuth 2.1 is explicitly out of scope (PROJECT.md, REQUIREMENTS.md).
- **D-19:** Network binding: gateway binds to `127.0.0.1` by default (GW-05). Set `MCP_GATEWAY_HOST=0.0.0.0` to expose on all interfaces inside the container; Phase 3 adds the host-side port publishing via `compose.yaml`.
- **D-20:** Gateway listens on port `8080` by default (matches ROADMAP success criteria). Configurable via `MCP_GATEWAY_PORT`.

### Claude's Discretion
- Concurrency / session-isolation model for multiple simultaneous remote clients (v2 work per REQUIREMENTS.md GW-V2-03 — Phase 2 can assume single-session or simple serialization).
- Error serialization format (MCP error codes, error payload shape) — follow MCP 2025-03-26 spec defaults.
- Logging level/format, structured vs plain — pick something that plays nicely with `docker compose logs`.
- FastMCP composition details: how tool handlers are registered, middleware order, auth middleware placement.
- Backend subprocess restart policy (e.g. on crash: restart N times then fail, or fail-fast).
- Inter-process transport detail between gateway and the BN/Ghidra stdio MCP servers (raw stdio vs an in-process `ClientSession`).
- Exact schema/argument names for each of the ~20 tools — planner can derive from existing scripts + orchestrator skill assets.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### MCP protocol & libraries
- [MCP Transports spec (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — Streamable HTTP standard, headers, session handling
- [MCP Authorization guide](https://modelcontextprotocol.io/docs/tutorials/security/authorization) — bearer token vs OAuth, when each applies
- [MCP Python SDK (PyPI: `mcp` v1.27.0+)](https://pypi.org/project/mcp/) — FastMCP class, Streamable HTTP support
- [ida-pro-mcp GitHub (mrexodia)](https://github.com/mrexodia/ida-pro-mcp) — endpoint paths (`/mcp` Streamable HTTP + `/sse` SSE on same port), tool surface

### Project-level specs
- `CLAUDE.md` (project root) — Recommended Stack: custom FastMCP gateway over mcp-proxy, Streamable HTTP transport, bearer token, Python 3.11+. Explicit list of "Do NOT Use" items (mcp-remote CVE, SSE legacy, MastraMCPClient).
- `.planning/PROJECT.md` — Core value, security constraints (elevated caps), Out-of-Scope rulings
- `.planning/REQUIREMENTS.md` — GW-01..GW-06 full text, especially GW-02 tool count and GW-04 auth semantics
- `.planning/ROADMAP.md` — Phase 2 goal, depends-on Phase 1, success criteria

### Existing code to reuse / integrate with
- `docker-bin/configure-agent-mcp.sh` — Backend priority detection logic (IDA > BN > Ghidra); gateway must reuse this same detection.
- `Dockerfile` lines 115-147 — idalib + ida-pro-mcp install block; gateway needs a parallel block for FastMCP + dependencies.
- `Dockerfile` lines 246-327 (`agent-entrypoint.sh`) — Where to add gateway daemon startup alongside the existing idalib-mcp daemon.
- `compose.yaml` — env var injection pattern for `MCP_GATEWAY_TOKEN`, `MCP_GATEWAY_HOST`, `MCP_GATEWAY_PORT`, `MCP_GATEWAY_MAX_UPLOAD_MB` (Phase 3 will publish the port).
- `mcp/ghidra-headless-mcp/ghidra_headless_mcp.py` and `ghidra_headless_mcp/server.py` — Reference for tool naming style and stdio MCP server structure to spawn.

### Orchestrator pipeline (source of truth for tool logic)
- `workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md` — Overview, required rules, quick-start sequence
- `workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md` — 13-artifact file list + schemas (drives the atomic tool set)
- `workspace/.claude/skills/malware-analysis-orchestrator/references/workflow.md` — Phase ordering; drives composite `run_triage` / `run_deep_analysis` tools
- `workspace/.claude/skills/malware-analysis-orchestrator/scripts/` — Scripts the gateway shells out to (`init_status_tree.sh`, `collect_strings.sh`, `collect_imports.sh`, `scan_yara.sh`, `scan_capa.sh`, `rank_signals.py`, `build_hypothesis.py`, `update_state.py`)

### Phase 1 context (upstream dependency)
- `.planning/phases/01-ida-pro-backend/01-CONTEXT.md` — Decisions about idalib-mcp transport (`/mcp` on 127.0.0.1:8745), backend priority chain, no silent fallback policy.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Backend detection logic** (`docker-bin/configure-agent-mcp.sh` lines 67-119): IDA > BN > Ghidra priority chain. Gateway should factor this into a shared helper (e.g., `/usr/local/bin/detect-disasm-backend.sh` or a small Python module) so both `configure-agent-mcp.sh` and the gateway use identical logic.
- **Orchestrator scripts** (`workspace/.claude/skills/malware-analysis-orchestrator/scripts/`): `init_status_tree.sh`, `collect_strings.sh`, `collect_imports.sh`, `scan_yara.sh`, `scan_capa.sh`, `rank_signals.py`, `build_hypothesis.py`, `update_state.py`. Directly shell-callable; produce artifact files in `status/<case>/`. The gateway's atomic tools are thin wrappers over these.
- **idalib-mcp daemon** (Phase 1, `agent-entrypoint.sh` lines 269-292): Already running on 127.0.0.1:8745. Gateway connects as an MCP client — no need to spawn it.
- **MCP config writer** (`configure-agent-mcp.sh` lines 121-187): JSON/TOML writing pattern for Claude Code `.mcp.json` + Codex `config.toml`. Phase 4 will produce the host-side equivalent that points at the gateway.
- **Ghidra MCP server** (`mcp/ghidra-headless-mcp/`): Shows tool-name style (`ghidra.info`, `function.list`, `program.open`) and backend abstraction. The unified verb-first names (D-03) map onto these.
- **Upload directory pattern**: `/agent` is the workspace volume; `/agent/uploads/<sha256>/<name>` is a natural extension of the existing layout (`status/`, `examples/`, `mcp/`).

### Established Patterns
- Conditional install via build arg (`INSTALL_BINARY_NINJA`, `INSTALL_IDA_PRO`, `INSTALL_GATEWAY` likely needed — or always-on since FastMCP is small).
- System-wide Python packages via `pip install --break-system-packages`.
- Persistent daemons started in `agent-entrypoint.sh` (gosu to `agent`, nohup, log to `/tmp/*.log`, bind to 127.0.0.1 by default).
- MCP config as JSON/TOML written at entrypoint (Claude Code `.mcp.json`, Codex `config.toml`).
- Host-facing env vars passed through `compose.yaml` environment block.
- No license artifacts in image (same pattern will apply if gateway depends on anything licensed — it shouldn't).

### Integration Points
- **Dockerfile**: New RUN block for FastMCP / `mcp` Python SDK install. Likely a new copy step for the gateway source code under `/opt/mcp-gateway/` or similar.
- **agent-entrypoint.sh**: New block after the idalib-mcp block that starts the gateway. Also needs to handle the token lifecycle (generate if unset, write `/agent/.mcp-gateway-token`, log it).
- **compose.yaml**: New env vars (`MCP_GATEWAY_TOKEN`, `MCP_GATEWAY_HOST`, `MCP_GATEWAY_PORT`, `MCP_GATEWAY_MAX_UPLOAD_MB`, `MCP_GATEWAY_QUIET`). Port publishing deferred to Phase 3.
- **run_docker.sh**: May need helper to surface the auto-generated token to the user after `docker compose up` (e.g., `cat ~/.mare-docker/.mcp-gateway-token` equivalent).
- **New gateway source tree**: Likely lives at `mcp-gateway/` in the repo root (alongside `mcp/`, `docker-bin/`). Contains the Python package, tool modules, tests.

</code_context>

<specifics>
## Specific Ideas

- Follow the existing "start a daemon in agent-entrypoint.sh with nohup + log file + port check" pattern used for idalib-mcp — the gateway should look/log identically from a user perspective.
- Startup logs should clearly show: "[gateway] starting on 127.0.0.1:8080", "[gateway] backend: IDA Pro", "[gateway] token file: /agent/.mcp-gateway-token", "[gateway] ready".
- Token file visibility on the host: because `/agent` is bind-mounted from the host (via `HOST_PWD`), `/agent/.mcp-gateway-token` shows up on the host at the same relative path — users can just `cat .mcp-gateway-token` from the project root after `docker compose up`.
- The verb-first tool names should read as imperative commands to an LLM client (e.g., `run_triage(sample="<sha>")` scans cleanly in a prompt).
- When backend detection picks Ghidra (no IDA, no BN), the gateway should still expose the unified disassembler tool names — the underlying call routes to Ghidra, but the client sees the same surface.

</specifics>

<deferred>
## Deferred Ideas

- MCP Resources for case artifacts (sample profile, strings, hypotheses, reports) → **Phase 4** (CLI-04 is already scoped there).
- MCP Prompts exposing orchestrator workflows as prompt templates → **v2** (GW-V2-01).
- Dynamic notifications for analysis progress → **v2** (GW-V2-02).
- Multi-session / concurrent remote clients with independent analyses → **v2** (GW-V2-03).
- Session lifecycle management, idle timeouts, case cleanup → **v2** (GW-V2-04).
- Unified disassembler abstraction layer (normalize tool args across BN/IDA/Ghidra beyond just names) → **v2** (DIS-V2-01).
- Backend comparison mode (run same analysis on multiple disassemblers and diff) → **v2** (DIS-V2-02).
- Claude Code / mastra.ai client config templates → **Phase 4** (CLI-01, CLI-02, CLI-03).
- Host-side port publishing in `compose.yaml` → **Phase 3** (INF-02).
- Dual-mode entrypoint tuning to ensure local agent mode is unchanged → **Phase 3** (INF-01, INF-05).

</deferred>

---

*Phase: 02-mcp-gateway*
*Context gathered: 2026-04-23*
