# Project Research Summary

**Project:** MARE-MCP-Toolbox v2 (IDA Pro Integration + Remote MCP Server)
**Domain:** Agentic malware analysis platform with remote MCP server capability
**Researched:** 2026-04-08
**Confidence:** MEDIUM-HIGH

## Executive Summary

MARE-MCP-Toolbox v2 extends a Docker-based malware analysis container with two capabilities: headless IDA Pro as a third disassembler backend, and a network-accessible MCP server so external clients (Claude Code on the host, mastra.ai agents) can invoke container tools over HTTP. The existing container already supports Binary Ninja and Ghidra via stdio MCP servers, 50+ CLI RE tools, and an orchestrator pipeline. The v2 work adds IDA Pro following the same conditional-install pattern and layers a Streamable HTTP gateway on top of the existing tool backends.

The recommended approach uses jtsylve/ida-mcp (v2.1.0) for the IDA Pro headless backend -- it provides ~190 tools via idalib with a supervisor/worker model that prevents database corruption from concurrent access. For the remote MCP gateway, the project should build a custom FastMCP (Python SDK) server that exposes a curated set of 15-25 orchestrator-level tools, routing disassembler calls to whichever backend is available. This is preferred over blindly proxying all backend tools via mcp-proxy, because the curated surface prevents context window flooding and avoids exposing raw shell capabilities on a privileged container. Bearer token authentication and localhost-only binding are non-negotiable from day one given the container elevated privileges (SYS_PTRACE, seccomp=unconfined).

The primary risks are: IDA Pro license leakage through Docker image layers (use multi-stage builds), Python environment conflicts between three disassembler APIs (use isolated environments per backend), and exposing an unauthenticated MCP server on a privileged container (implement auth before first port exposure). All three risks are well-understood with clear mitigations documented in PITFALLS.md.

## Key Findings

### Recommended Stack

The stack is Python-centric, matching the existing container ecosystem. No new language runtimes are needed.

**Core technologies:**
- **ida-mcp (jtsylve) v2.1.0:** Headless IDA Pro MCP server via idalib -- ~190 tools, supervisor/worker process isolation, stdio transport, PyPI-installable. The most complete headless IDA MCP implementation available.
- **FastMCP (Python MCP SDK v1.27.0+):** MCP gateway server with native Streamable HTTP support. Avoids adding Node.js to a Python-centric container.
- **Streamable HTTP (MCP spec 2025-03-26):** The current standard transport. SSE was deprecated June 2025. Both Claude Code and mastra.ai support it natively.
- **Bearer token auth:** Simple shared-secret authentication via environment variable. OAuth 2.1 is explicitly rejected as overkill for single-team local/VPN deployments.

**Note on ida-mcp choice:** STACK.md and ARCHITECTURE.md initially diverged (jtsylve vs mrexodia). The recommendation is jtsylve/ida-mcp because it uses idalib natively (true headless, no GUI dependency), has built-in process isolation per database, and is stdio-based which matches the existing Binary Ninja/Ghidra pattern exactly. The mrexodia variant is viable but its primary mode is plugin-based (requires IDA GUI).

**Note on gateway approach:** STACK.md recommended mcp-proxy (zero-code bridging) while ARCHITECTURE.md recommended a custom FastMCP gateway (curated tool surface). The recommendation is the **custom FastMCP gateway** -- the curated tool surface is essential for security and usability. Raw proxying of 190+ IDA tools would flood LLM context windows and expose low-level operations that should not be network-accessible.

### Expected Features

**Must have (table stakes):**
- Conditional IDA Pro install at Docker build time (mirrors Binary Ninja pattern)
- IDA headless MCP server via stdio for local agents
- Disassembler fallback chain update: BN > IDA > Ghidra
- Streamable HTTP MCP endpoint for remote clients
- Bearer token authentication on the gateway
- Core curated tools: triage, strings, imports, YARA, capa, decompile, function list, xrefs
- File transfer mechanism for remote clients to submit binaries
- .mcp.json template for Claude Code host-side configuration
- mastra.ai MCPClient configuration support

**Should have (differentiators):**
- Unified disassembler abstraction (single tool interface regardless of backend)
- Dual-mode operation (local stdio + remote HTTP simultaneously)
- MCP Resources for analysis context (case artifacts as mare:// URIs)
- MCP Prompts for guided workflows (triage, deep analysis, report generation)
- Orchestrator-as-a-tool (full pipeline via single tool call)

**Defer (v2+):**
- Multi-binary concurrent analysis across backends (ida-mcp handles it internally; cross-backend is complex)
- Dynamic tool availability notifications (list_changed)
- Per-client token management and rotation
### Architecture Approach

The system operates in dual mode from a single container: local agents use stdio MCP servers directly (unchanged from v1), while remote clients connect through a FastMCP gateway over Streamable HTTP on port 8080. The gateway implements a Tool Router that maps curated MCP tool names to backend executables -- dispatching disassembler calls to whichever backend is installed (BN/IDA/Ghidra via stdio subprocess) and CLI tool calls to subprocess execution. The gateway is an additional entry point, not a replacement for local mode.

**Major components:**
1. **MCP Gateway (FastMCP/Python)** -- Streamable HTTP server on :8080, handles auth, exposes curated tool surface, manages sessions
2. **Tool Router/Registry** -- Maps unified tool names to backend-specific implementations, handles disassembler selection and fallback
3. **IDA Pro MCP Backend** -- New stdio MCP server via ida-mcp, added alongside existing BN and Ghidra backends
4. **configure-agent-mcp.sh (extended)** -- Detects all three disassemblers, configures local agent MCP, sets active backend for gateway routing

### Critical Pitfalls

1. **IDA license leakage in Docker layers** -- Use multi-stage builds exclusively. Never ENV HCLI_API_KEY. Copy only /opt/ida to final stage. The HCLI install flow is different from Binary Ninja zip pattern.
2. **Python environment conflicts (3 disassemblers)** -- Each disassembler API installs into site-packages differently. IDA requires specific Python version (3.12/3.13). Use isolated venvs or per-process PYTHONPATH. Test three-way coexistence before moving to remote MCP work.
3. **Unauthenticated MCP on privileged container** -- Container has SYS_PTRACE + seccomp=unconfined. Auth and localhost binding must be implemented before the first port is exposed. No exceptions.
4. **idalib threading model causes silent DB corruption** -- Use ida-mcp supervisor/worker model (one subprocess per database). Never share .idb files between concurrent sessions.
5. **IDA Pro x86_64-only on Linux** -- No ARM64 idalib. Must force --platform=linux/amd64 when IDA is installed. Document Apple Silicon limitation.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: IDA Pro Backend Integration
**Rationale:** Foundation phase with no external dependencies. Follows proven Binary Ninja conditional-install pattern. Must validate Python environment coexistence before building anything on top.
**Delivers:** IDA Pro as a third disassembler option for local agents inside the container.
**Addresses:** Conditional IDA install, IDA headless MCP (stdio), fallback chain update, license mounting
**Avoids:** License leakage (multi-stage build from day one), Python conflicts (test three-way coexistence), x86_64 platform constraint (document and pin)
**Key risk:** Python version compatibility between Kali rolling, IDA 9.x (needs 3.12+), Binary Ninja, and pyghidra.

### Phase 2: MCP Gateway Foundation
**Rationale:** Depends on Phase 1 (need all three backends available to test routing). This is the core new capability -- the curated tool surface that remote clients interact with.
**Delivers:** FastMCP server with Streamable HTTP, bearer token auth, curated tool surface (~15-25 tools), unified disassembler routing.
**Addresses:** Streamable HTTP endpoint, bearer token auth, core curated tools (triage, decompile, strings, YARA, capa, xrefs, function list), Tool Router with disassembler abstraction
**Avoids:** Raw tool surface exposure (allowlist pattern only), unauthenticated access (auth middleware from first commit), deprecated SSE transport
**Key risk:** Designing the right tool granularity -- too fine-grained wastes context, too coarse loses flexibility.

### Phase 3: Container Integration and Dual-Mode
**Rationale:** Depends on Phase 2 (gateway must exist). Wires the gateway into the container lifecycle -- entrypoint, compose config, port mapping, environment variables.
**Delivers:** Container that starts with MCP gateway automatically, dual-mode operation (local + remote), file transfer mechanism for remote binary submission.
**Addresses:** Entrypoint gateway launch, compose.yaml updates, run_docker.sh updates, dual-mode validation, file upload/transfer, health check endpoint
**Avoids:** Breaking local agent workflow (gateway is additive, not replacement), binding to 0.0.0.0 without auth

### Phase 4: External Client Integration
**Rationale:** Depends on Phase 3 (dual-mode must work). Final mile -- connecting Claude Code and mastra.ai on the host to the containerized tools.
**Delivers:** End-to-end workflows from host-side clients through to analysis results. Documentation and configuration templates.
**Addresses:** .mcp.json template for Claude Code, mastra.ai MCPClient config, session management, case directory listing, report retrieval
**Avoids:** Hardcoded secrets in config files (use env var expansion)

### Phase 5: Differentiators (Post-MVP)
**Rationale:** Polish and power features after core functionality is validated end-to-end.
**Delivers:** MCP Resources, MCP Prompts, orchestrator-as-a-tool, dynamic tool notifications.
**Addresses:** All should-have differentiator features from FEATURES.md.

### Phase Ordering Rationale

- **Phase 1 before Phase 2:** The gateway needs backends to route to. IDA integration validates the three-way Python coexistence that the gateway depends on.
- **Phase 2 before Phase 3:** Tool surface design and auth must be correct before exposing any port. Easier to test gateway in isolation first.
- **Phase 3 before Phase 4:** Container must be wired up before external clients can connect. Dual-mode must be validated before client templates are documented.
- **Phases 1-4 are MVP.** Phase 5 is enhancement. Each phase delivers testable, independently valuable functionality.
### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** IDA Pro HCLI Docker installation flow differs significantly from Binary Ninja zip pattern. Need to study the official HCLI Dockerfile closely. Python version pinning across three APIs needs testing.
- **Phase 2:** Tool surface design requires careful thought -- which of the ~190 ida-mcp tools and 50+ CLI tools to curate into the gateway 15-25 tool surface. May need prototype iteration.

Phases with standard patterns (skip deep research):
- **Phase 3:** Docker compose, entrypoint scripting, port mapping -- well-documented, established patterns.
- **Phase 4:** Claude Code .mcp.json and mastra.ai MCPClient configuration are thoroughly documented with clear examples in official docs.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All recommended tools have official docs, PyPI packages, and recent releases. ida-mcp 2.1.0 released April 2026. |
| Features | HIGH | Feature landscape well-defined by PROJECT.md scope and existing codebase patterns. Clear MVP vs. defer line. |
| Architecture | MEDIUM-HIGH | Dual-mode pattern is sound but untested. Minor divergence between researchers on ida-mcp variant (resolved in synthesis). Gateway tool surface design needs prototype validation. |
| Pitfalls | HIGH | All critical pitfalls are well-documented with clear mitigations. IDA Docker patterns verified against official HCLI Dockerfile. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Python 3.12/3.13 compatibility matrix:** IDA 9.x requires 3.12+, but Kali rolling may ship a different version. Need to verify exact version requirements and test three-way API coexistence during Phase 1.
- **Tool surface curation:** The exact list of 15-25 curated gateway tools needs design work during Phase 2 planning. Research identified the principle (orchestrator-level, not CLI wrappers) but not the specific tool list.
- **Session management complexity:** Streamable HTTP sessions mapped to analysis contexts (open databases, case directories) is marked HIGH complexity. May need to start with stateless mode and add sessions later.
- **File transfer for large binaries:** Base64 in tool args works for small files but not large malware samples. Shared volume mount is practical for co-located setups but not for truly remote clients. Needs design decision during Phase 3.
- **mcp-proxy vs FastMCP gateway:** Research recommends FastMCP for curation, but mcp-proxy could serve as a quick prototype. The final architecture should use FastMCP, but Phase 2 could validate transport with mcp-proxy first.

## Sources

### Primary (HIGH confidence)
- [ida-mcp GitHub (jtsylve)](https://github.com/jtsylve/ida-mcp) -- headless IDA MCP, 190+ tools, supervisor/worker
- [ida-mcp 2.0 announcement](https://jtsylve.blog/post/2026/03/25/Announcing-ida-mcp-2) -- architecture details
- [MCP Transports spec 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) -- Streamable HTTP standard
- [MCP Python SDK](https://pypi.org/project/mcp/) -- v1.27.0, FastMCP with Streamable HTTP
- [Claude Code MCP docs](https://code.claude.com/docs/en/mcp) -- .mcp.json http type, auth headers
- [Mastra MCPClient reference](https://mastra.ai/reference/tools/mcp-client) -- URL transport, requestInit
- [HCLI official Dockerfile](https://github.com/HexRaysSA/ida-hcli/blob/main/docs/advanced/docker/Dockerfile) -- multi-stage IDA Docker pattern

### Secondary (MEDIUM confidence)
- [mcp-proxy GitHub](https://github.com/sparfenyuk/mcp-proxy) -- stdio-to-HTTP bridge option
- [mrexodia/ida-pro-mcp](https://github.com/mrexodia/ida-pro-mcp) -- alternative IDA MCP (plugin + headless modes)
- [Bitsight - Exposed MCP Servers](https://www.bitsight.com/blog/exposed-mcp-servers-reveal-new-ai-vulnerabilities) -- security context for auth requirement
- [Auth0 - Why MCP deprecated SSE](https://auth0.com/blog/mcp-streamable-http/) -- transport decision rationale
- [Cloudflare Streamable HTTP Blog](https://blog.cloudflare.com/streamable-http-mcp-servers-python/) -- Python implementation patterns

### Tertiary (LOW confidence)
- [blacktop/idapro Docker](https://hub.docker.com/r/blacktop/idapro) -- community IDA Docker patterns (may differ from HCLI official)
- [MCP best practices (philschmid)](https://www.philschmid.de/mcp-best-practices) -- tool design principles

---
*Research completed: 2026-04-08*
*Ready for roadmap: yes*