# Requirements: MARE-MCP-Toolbox v2

**Defined:** 2026-04-08
**Core Value:** Automated malware triage and deep analysis via AI agents with full access to professional RE tooling — accessible both from inside the container and from external MCP clients.

## v1 Requirements

### IDA Pro Backend

- [ ] **IDA-01**: IDA Pro installs conditionally via `INSTALL_IDA_PRO` build arg using multi-stage Docker build (license never in image layers)
- [ ] **IDA-02**: IDA Pro headless MCP server (`ida-mcp`) runs via stdio transport inside container
- [ ] **IDA-03**: IDA Pro license persists on host via bind mount to `~/.idapro/` (same pattern as Binary Ninja's `~/.binaryninja/`)
- [ ] **IDA-04**: `configure-agent-mcp.sh` detects IDA Pro and registers MCP server with fallback chain: BN > IDA > Ghidra
- [ ] **IDA-05**: Hex-Rays decompiler functions are available via MCP when user has decompiler license
- [ ] **IDA-06**: Python environment isolation prevents conflicts between IDA Pro (3.12+), Binary Ninja, and Ghidra APIs

### MCP Gateway

- [ ] **GW-01**: Python FastMCP server exposes curated tool surface over Streamable HTTP transport (spec 2025-03-26)
- [ ] **GW-02**: Gateway exposes ~15-25 orchestrator-level tools mapping to the existing 13-artifact pipeline (triage, collect_strings, collect_imports, scan_yara, scan_capa, decompile_function, list_functions, get_xrefs, etc.)
- [ ] **GW-03**: Disassembler tools route to whichever backend is installed (BN > IDA > Ghidra), presenting a unified interface to clients
- [ ] **GW-04**: Bearer token authentication required on all remote MCP endpoints (token generated at container start, passed via environment variable)
- [ ] **GW-05**: Gateway binds to localhost only by default; explicit opt-in for network exposure
- [ ] **GW-06**: File upload mechanism allows remote clients to submit samples to the container for analysis

### External Clients

- [ ] **CLI-01**: Claude Code connects to container via `.mcp.json` with `type: "http"` and bearer token header
- [ ] **CLI-02**: Mastra.ai connects to container via `MCPClient` with same Streamable HTTP endpoint
- [ ] **CLI-03**: Pre-built config templates provided for Claude Code (`.mcp.json` snippet) and mastra.ai
- [ ] **CLI-04**: MCP Resources expose case artifacts (sample profile, strings, imports, hypotheses, reports) as browsable resources

### Container Infrastructure

- [ ] **INF-01**: Dual-mode entrypoint supports both local agent mode (existing) and remote MCP gateway mode (new) simultaneously
- [ ] **INF-02**: Docker Compose exposes gateway port (default 8080) with configurable mapping
- [ ] **INF-03**: Python 3.12+ available in container for ida-mcp compatibility
- [ ] **INF-04**: `run_docker.sh` updated with IDA Pro zip detection and `IDA_USER_DIR` env var for license persistence
- [ ] **INF-05**: Existing local agent workflow (Claude Code/Codex inside container) continues working unchanged

## v2 Requirements

### Advanced Gateway

- **GW-V2-01**: MCP Prompts expose orchestrator workflow as prompt templates (full triage, deep analysis)
- **GW-V2-02**: Dynamic notifications push analysis progress to connected clients
- **GW-V2-03**: Multi-session support — multiple clients can run independent analyses concurrently
- **GW-V2-04**: Database/session lifecycle management with configurable timeouts and cleanup

### Advanced Disassemblers

- **DIS-V2-01**: Unified disassembler abstraction layer (normalize tool names/params across all three backends)
- **DIS-V2-02**: Backend comparison mode — run same analysis on multiple disassemblers and diff results

## Out of Scope

| Feature | Reason |
|---------|--------|
| Custom web UI or dashboard | Clients are Claude Code, Codex, mastra.ai — no custom frontend needed |
| Dynamic analysis orchestration | Static analysis focus; dynamic tools available but not orchestrated |
| Replacing Binary Ninja or Ghidra | IDA Pro is an addition, not a replacement |
| OAuth 2.1 authentication | Overkill for local/team container deployment; bearer token sufficient |
| Raw CLI tool passthrough | Security risk on privileged container; curated tools only |
| ARM64 IDA Pro support | IDA Pro Linux is x86_64-only; hard constraint from Hex-Rays |
| Rewriting existing orchestrator skill | Existing 13-artifact pipeline stays intact |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| (populated during roadmap creation) | | |

**Coverage:**
- v1 requirements: 20 total
- Mapped to phases: 0
- Unmapped: 20 ⚠️

---
*Requirements defined: 2026-04-08*
*Last updated: 2026-04-08 after initial definition*
