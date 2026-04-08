# Feature Landscape

**Domain:** Agentic malware analysis platform with remote MCP server capability and IDA Pro integration
**Researched:** 2026-04-08

## Table Stakes

Features users expect. Missing = product feels incomplete.

### IDA Pro Headless Integration

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Conditional IDA Pro install at build time | Same pattern as Binary Ninja — user provides installer, Dockerfile installs if present | Med | Follow existing Binary Ninja pattern: build arg `INSTALL_IDA=0/1`, bind-mount IDA installer zip. Requires IDA Pro 9+ with idalib. |
| IDA headless MCP server (stdio) | Agents inside the container need IDA via MCP tools, same as BN/Ghidra | Med | Use `jtsylve/ida-mcp` (Python, ~190 tools, supervisor/worker model, idalib-based). It is the most complete headless implementation. Requires Python 3.12+ and IDA Pro 9+ license. |
| Disassembly and decompilation tools | Core RE capability — list functions, decompile to pseudocode, get disassembly | Low | Provided by ida-mcp out of the box. Hex-Rays decompiler license needed for pseudocode. |
| Cross-reference queries | Standard RE workflow — find callers/callees, string xrefs, API xrefs | Low | Provided by ida-mcp. Essential for the orchestrator's deep analysis phase. |
| Type and structure management | Applying types, creating structs, using FLIRT signatures | Low | Provided by ida-mcp. Important for accurate decompilation. |
| Fallback chain: BN MCP > IDA MCP > Ghidra MCP > r2 | Users expect graceful degradation when only some tools are licensed | Med | Extend `configure-agent-mcp.sh` to detect IDA installation and register as MCP server. IDA slots in as second priority (or user-configurable). |
| License file mounting (never baked into image) | Licensing compliance — IDA license must come from host at runtime | Low | Mount IDA license via Docker volume or bind-mount, same pattern as BN_USER_DIRECTORY. |

### Remote MCP Server (Transport and Connectivity)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Streamable HTTP transport endpoint | MCP spec 2025-03-26 standard. Claude Code uses `--transport http`. Mastra tries Streamable HTTP first. SSE is deprecated. | Med | Single HTTP endpoint (e.g., `http://container:8080/mcp`) supporting POST+GET. Use `@modelcontextprotocol/sdk` TypeScript or `mcp` Python SDK which implement the transport. |
| SSE fallback compatibility | Older clients and transition period (SSE deprecated but still used). Streamable HTTP spec allows SSE streaming within it. | Low | Streamable HTTP inherently supports SSE for server-to-client streaming. No separate SSE endpoint needed if using spec-compliant Streamable HTTP. |
| Bearer token authentication | Remote server exposed on network needs auth. Claude Code supports `--header "Authorization: Bearer ..."`. Mastra supports custom fetch with auth headers. | Med | Simple shared-secret bearer token. Set via environment variable at container start. Validate on every request. Not OAuth — this is a local/private network tool, not a public service. |
| TLS termination support | Network security for tokens in transit | Low | Delegate to reverse proxy (Caddy, nginx) or Docker network. Container serves plain HTTP; TLS at edge. Document but don't implement TLS in the MCP server itself. |
| `.mcp.json` compatibility for Claude Code | Users configure Claude Code on host to connect to container | Low | Provide example `.mcp.json`: `{"mcpServers": {"mare-toolbox": {"type": "http", "url": "http://localhost:8080/mcp", "headers": {"Authorization": "Bearer ${MARE_TOKEN}"}}}}` |
| Mastra MCPClient compatibility | Mastra connects via `new MCPClient({servers: {mare: {url: new URL("http://...")}}})` with optional `requestInit` for auth headers | Low | Streamable HTTP endpoint is natively compatible. Document `requestInit` config for auth. |
| Session management (Mcp-Session-Id) | Stateful analysis — IDA databases stay open, analysis state persists across tool calls within a session | High | Streamable HTTP spec supports session IDs. Map sessions to analysis contexts (open binaries, case directories). Critical for multi-binary concurrent analysis. |
| Health check endpoint | Clients need to know if server is alive before sending analysis requests | Low | Simple `/health` or `/ready` HTTP endpoint returning server status and available backends. |

### Curated MCP Tool Surface

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Orchestrator-level triage tool | One tool call to run full triage (hashes, file ID, strings, imports, YARA, capa). Design around user goals, not CLI wrappers. | Med | Wraps `init_status_tree.sh` + collection scripts. Returns structured triage summary. Agent says "triage this binary" not "run sha256sum then run strings then...". |
| String extraction tool | Extract and rank interesting strings from a binary | Low | Wraps `collect_strings.sh` + `rank_signals.py` for the strings dimension. |
| Import/API analysis tool | Extract and rank interesting imports | Low | Wraps `collect_imports.sh` + `rank_signals.py` for the imports dimension. |
| YARA scan tool | Run YARA rules against a binary | Low | Wraps `scan_yara.sh`. Returns structured match results. |
| Capa capability scan tool | Run Mandiant capa for ATT&CK-mapped capabilities | Low | Wraps `scan_capa.sh`. Returns structured capability results. |
| Decompile function tool | Decompile a specific function using available disassembler backend | Med | Routes to BN/IDA/Ghidra MCP based on availability. Abstracts backend choice from the remote client. |
| Get function list tool | List functions in a loaded binary | Low | Routes to available disassembler backend. |
| Cross-reference lookup tool | Find xrefs to/from address or symbol | Low | Routes to available disassembler backend. |
| File upload/transfer mechanism | Remote clients need to send binaries to the container for analysis | High | Accept binary via tool call argument (base64) or shared volume mount. For large files, shared volume is practical. For remote-only, base64 in tool args or a dedicated upload endpoint. |
| Case directory listing tool | List existing analysis cases and their status | Low | Reads status/ directory structure and CURRENT_STATE.json files. |
| Report retrieval tool | Get analysis reports and artifacts from a completed case | Low | Read and return contents of case directory artifacts. |

## Differentiators

Features that set product apart. Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Unified disassembler abstraction | Single tool interface regardless of whether BN, IDA, or Ghidra is the backend. No other toolbox offers this. | High | Normalize tool names and arguments across three backends. E.g., `decompile_function(address)` routes to whichever is available. Massive DX win for agents. |
| Dual-mode operation (local agent + remote MCP) | Same container serves agents running inside it AND external MCP clients simultaneously | Med | Local agents use stdio MCP as today. Remote MCP server runs in parallel on HTTP port. Both share the same tool implementations. Unique capability. |
| Multi-binary concurrent analysis | Keep multiple binaries open across sessions, analyze in parallel | High | ida-mcp 2.0's supervisor/worker model supports this natively. Extend to BN/Ghidra backends. Map sessions to open databases. |
| MCP Resources for analysis context | Expose case artifacts as MCP resources (`mare://cases/000-malware/profile`, `mare://cases/000-malware/hypotheses`) so clients can read analysis state | Med | ida-mcp 2.0 exposes 36 resources. Follow same pattern for orchestrator artifacts. Provides read-only context without tool calls. |
| MCP Prompts for guided workflows | Pre-built prompts for common workflows: "triage binary", "deep analysis of function", "generate report" | Low | ida-mcp 2.0 exposes 8 prompts for guided RE workflows. Define prompts that match the 13-artifact pipeline phases. |
| Orchestrator-as-a-tool (full pipeline) | Single tool call that runs the entire 8-phase orchestrator pipeline end-to-end and returns the final report | Med | Remote agents call one tool, get a complete analysis. Internally runs all phases. Useful for Mastra workflows that want fire-and-forget analysis. |
| Dynamic tool availability notifications | When a disassembler backend starts/stops, notify connected clients via MCP `list_changed` | Med | Claude Code supports `list_changed` notifications. Tools appear/disappear based on available backends. |
| Entropy and binary structure visualization data | Return entropy analysis and section layout as structured data for client-side rendering | Low | Wraps `binwalk` entropy output. Useful for automated packer detection workflows. |

## Anti-Features

Features to deliberately NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Raw CLI wrappers as MCP tools | Exposing `strings`, `sha256sum`, `readelf` as individual tools creates too many low-value tools, wastes agent context, and forces LLMs to orchestrate shell commands. MCP best practice: design around user goals. | Compose CLI tools into high-level operations (triage, string analysis, import analysis). The orchestrator already has this logic. |
| OAuth 2.1 authorization server | Massive complexity for a developer tool running on localhost or private network. OAuth is for public cloud services. | Bearer token auth via shared secret. Simple, sufficient, secure with TLS. |
| Web UI or dashboard | Out of scope per PROJECT.md. Clients are Claude Code, Codex, Mastra. | Expose all functionality via MCP tools, resources, and prompts. |
| Dynamic analysis execution | Container runs static analysis. Dynamic analysis (debugging, emulation) is a different security model and scope. | Keep `gdb`, `strace`, `qemu-user` available as CLI tools for agents inside the container, but do not expose via remote MCP. |
| Plugin-based IDA integration (non-headless) | Requires IDA GUI running, defeats Docker headless purpose. mrexodia/ida-pro-mcp's plugin mode needs a running IDA instance. | Use idalib-based headless only (jtsylve/ida-mcp or similar). No GUI dependency. |
| Custom MCP transport implementation | Reimplementing Streamable HTTP from scratch is error-prone and unnecessary. | Use official `@modelcontextprotocol/sdk` (TypeScript) or `mcp` (Python) SDK which provides transport implementations. |
| Per-user multi-tenancy | Adding user management, access control lists, role-based permissions. This is a single-user/team development tool. | Single bearer token, single user context. If teams need isolation, run separate containers. |
| Persistent cross-session state in MCP server | Complex state management, data corruption risks, unclear value for analysis workflows that are inherently per-session. | Sessions are ephemeral. Case directories on disk provide persistence. Clients can reconnect and reference existing cases by path. |

## Feature Dependencies

```
IDA Pro Installation → IDA Headless MCP Server (idalib needs IDA installed)
IDA Headless MCP Server → Disassembler Fallback Chain Update
Streamable HTTP Endpoint → Claude Code Compatibility
Streamable HTTP Endpoint → Mastra Compatibility  
Streamable HTTP Endpoint → Bearer Token Auth
Bearer Token Auth → .mcp.json Template
File Upload Mechanism → Orchestrator Triage Tool (remote clients need to send files)
Orchestrator Triage Tool → Case Directory Listing
Orchestrator Triage Tool → Report Retrieval
Session Management → Multi-binary Concurrent Analysis
Unified Disassembler Abstraction → Decompile Function Tool (remote)
Unified Disassembler Abstraction → Get Function List Tool (remote)
Unified Disassembler Abstraction → Cross-reference Lookup Tool (remote)
```

## MVP Recommendation

Prioritize for first milestone:

1. **IDA Pro conditional install** (Dockerfile pattern) — unblocks all IDA features
2. **IDA headless MCP server via jtsylve/ida-mcp** — stdio transport for local agents
3. **Fallback chain update** in `configure-agent-mcp.sh` — IDA integrates with existing agent workflow
4. **Streamable HTTP MCP endpoint** — single gateway exposing curated tools to remote clients
5. **Bearer token auth** — minimum viable security for network exposure
6. **Core curated tools** (triage, strings, imports, YARA, capa, decompile, function list) — the tool surface remote clients interact with
7. **File transfer mechanism** — remote clients need to get binaries into the container

Defer:

- **Unified disassembler abstraction**: High complexity, can initially expose backend-specific tools and unify later
- **MCP Resources and Prompts**: Nice-to-have, tools are sufficient for MVP
- **Multi-binary concurrent analysis**: Works within ida-mcp natively, but cross-backend concurrency is complex
- **Orchestrator-as-a-tool (full pipeline)**: Useful but can be added after core tools work
- **Dynamic tool availability notifications**: Polish feature, not blocking

## Sources

- [jtsylve/ida-mcp](https://github.com/jtsylve/ida-mcp) — Headless IDA Pro MCP server, ~190 tools, supervisor/worker, idalib-based (HIGH confidence)
- [mrexodia/ida-pro-mcp](https://github.com/mrexodia/ida-pro-mcp) — Plugin + headless IDA MCP, SSE transport, 76+ tools (HIGH confidence)
- [ida-mcp 2.0 announcement](https://jtsylve.blog/post/2026/03/25/Announcing-ida-mcp-2) — Architecture details, multi-database support (HIGH confidence)
- [blacktop/idapro Docker](https://hub.docker.com/r/blacktop/idapro) — IDA Pro Docker container patterns (MEDIUM confidence)
- [MCP Transports spec 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — Streamable HTTP standard (HIGH confidence)
- [Auth0: MCP Streamable HTTP](https://auth0.com/blog/mcp-streamable-http/) — Why SSE deprecated, security improvements (HIGH confidence)
- [Claude Code MCP docs](https://code.claude.com/docs/en/mcp) — Transport types, .mcp.json format, auth headers, scopes (HIGH confidence)
- [Mastra MCPClient reference](https://mastra.ai/reference/tools/mcp-client) — Streamable HTTP first, SSE fallback, requestInit config (HIGH confidence)
- [MCP best practices](https://www.philschmid.de/mcp-best-practices) — Design around user goals, not REST-to-MCP 1:1 (MEDIUM confidence)
- [Awesome RE MCP](https://github.com/crowdere/Awesome-RE-MCP) — Curated RE tools with MCP servers (MEDIUM confidence)
