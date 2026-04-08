# Roadmap: MARE-MCP-Toolbox v2

## Overview

This roadmap delivers two major capabilities to the MARE-MCP-Toolbox: IDA Pro as a third disassembler backend (alongside Binary Ninja and Ghidra), and a remote MCP gateway that exposes the container's analysis tools over Streamable HTTP for external clients like Claude Code and mastra.ai. The work progresses from backend integration (IDA Pro working locally inside the container) through gateway construction (curated tool surface with auth) to container wiring (dual-mode entrypoint, compose config) and finally external client integration (config templates, end-to-end workflows). Each phase delivers independently testable capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: IDA Pro Backend** - Headless IDA Pro as third disassembler option for local agents inside the container
- [ ] **Phase 2: MCP Gateway** - FastMCP server exposing curated tool surface over Streamable HTTP with authentication
- [ ] **Phase 3: Container Integration** - Dual-mode entrypoint, Docker Compose wiring, and file transfer for remote analysis
- [ ] **Phase 4: External Client Integration** - Claude Code and mastra.ai connect to the container and run end-to-end analysis workflows

## Phase Details

### Phase 1: IDA Pro Backend
**Goal**: Local agents inside the container can use IDA Pro for disassembly and decompilation, with automatic fallback across all three backends
**Depends on**: Nothing (first phase)
**Requirements**: IDA-01, IDA-02, IDA-03, IDA-04, IDA-05, IDA-06, INF-03, INF-04
**Success Criteria** (what must be TRUE):
  1. Building the container with `INSTALL_IDA_PRO=1` and a valid IDA zip produces a working IDA Pro installation with no license artifacts in intermediate Docker layers
  2. An agent inside the container can invoke IDA Pro MCP tools (disassemble, decompile, list functions) via stdio transport on a test binary
  3. The fallback chain (BN > IDA > Ghidra) activates the correct backend based on what is installed, verified by `configure-agent-mcp.sh` output
  4. All three disassembler APIs (Binary Ninja, IDA Pro, Ghidra) coexist without Python import errors or version conflicts
  5. IDA Pro license persists across container restarts via host bind mount to `~/.idapro/`
**Plans**: TBD

Plans:
- [ ] 01-01: TBD
- [ ] 01-02: TBD

### Phase 2: MCP Gateway
**Goal**: A curated set of orchestrator-level analysis tools is accessible over Streamable HTTP with bearer token authentication
**Depends on**: Phase 1
**Requirements**: GW-01, GW-02, GW-03, GW-04, GW-05, GW-06
**Success Criteria** (what must be TRUE):
  1. A Streamable HTTP endpoint on port 8080 responds to MCP tool discovery requests and returns the curated tool list (15-25 tools)
  2. Requests without a valid bearer token are rejected with 401; requests with a valid token succeed
  3. Disassembler tools (decompile, list_functions, get_xrefs) route to the installed backend transparently -- the client sees a unified interface regardless of whether BN, IDA, or Ghidra is active
  4. A remote client can upload a binary sample via the file transfer mechanism and then run analysis tools against it
  5. The gateway binds to localhost only by default and requires explicit configuration to listen on all interfaces
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD

### Phase 3: Container Integration
**Goal**: The container starts with both local agent mode and remote MCP gateway mode operational, with no changes to existing local workflows
**Depends on**: Phase 2
**Requirements**: INF-01, INF-02, INF-05
**Success Criteria** (what must be TRUE):
  1. `docker compose up` starts the container with the MCP gateway listening on the configured port (default 8080) alongside the existing local agent environment
  2. An agent running inside the container (existing Claude Code/Codex workflow) continues working identically to v1 -- no regressions
  3. The gateway port is configurable via Docker Compose environment variables without rebuilding the image
**Plans**: TBD

Plans:
- [ ] 03-01: TBD

### Phase 4: External Client Integration
**Goal**: Claude Code on the host and mastra.ai agents can connect to the containerized tools and run complete analysis workflows
**Depends on**: Phase 3
**Requirements**: CLI-01, CLI-02, CLI-03, CLI-04
**Success Criteria** (what must be TRUE):
  1. Claude Code on the host connects to the container using a provided `.mcp.json` snippet and can invoke analysis tools (triage, strings, decompile) against a submitted sample
  2. A mastra.ai agent connects to the container via MCPClient and can run an analysis workflow using the same Streamable HTTP endpoint
  3. Pre-built config templates for both Claude Code and mastra.ai are provided and work without modification beyond inserting the bearer token
  4. Case artifacts (sample profile, strings output, YARA results, reports) are browsable as MCP Resources by connected clients
**Plans**: TBD

Plans:
- [ ] 04-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. IDA Pro Backend | 0/0 | Not started | - |
| 2. MCP Gateway | 0/0 | Not started | - |
| 3. Container Integration | 0/0 | Not started | - |
| 4. External Client Integration | 0/0 | Not started | - |
