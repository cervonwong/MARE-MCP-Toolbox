<!-- GSD:project-start source:PROJECT.md -->
## Project

**MARE-MCP-Toolbox v2**

An agentic malware analysis platform built on a Kali Linux Docker container with 50+ reverse engineering tools and MCP-connected disassembler backends (Binary Ninja, Ghidra, and now IDA Pro). v2 adds the ability to expose the entire container as a remote MCP server, enabling external clients — Claude Code on the host, mastra.ai, or any MCP-compatible agent framework — to use the container's tools without running an agent inside it.

**Core Value:** Automated malware triage and deep analysis via AI agents with full access to professional RE tooling — accessible both from inside the container (current mode) and from external MCP clients (new mode).

### Constraints

- **Licensing**: IDA Pro and Binary Ninja require user-provided licenses — never baked into images
- **Security**: Container runs with elevated capabilities (SYS_PTRACE, seccomp=unconfined) — remote MCP server must consider auth/network exposure
- **Transport**: Remote MCP needs network-accessible transport (SSE/HTTP), not stdio
- **Backward compatibility**: Existing "agent inside container" mode must continue working unchanged
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### IDA Pro Headless MCP Backend
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| ida-pro-mcp (mrexodia) | latest | IDA Pro MCP server with headless idalib mode | 50+ tools, supports both GUI plugin and headless idalib modes. Headless mode (`idalib-mcp`) runs an SSE server — already network-accessible, no proxy needed for remote access. Active development. | HIGH |
| IDA Pro | 9+ | Disassembler engine | Required for idalib support; provides the analysis engine | HIGH |
| idapro (bundled) | from IDA install | Python idalib wrapper | Installed from IDA's `idalib/python` directory (not PyPI). Activated via `py-activate-idalib.py`. Must be first import in scripts. | HIGH |
| Python | 3.11+ | Runtime for ida-pro-mcp | Required by ida-pro-mcp; container already has Python 3.x | HIGH |
### Remote MCP Gateway Server
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| mcp-proxy (sparfenyuk) | 0.3.x | Bridge stdio MCP servers to Streamable HTTP | Purpose-built for exactly this use case. Wraps any stdio MCP server and exposes it over Streamable HTTP. Python-based, Docker-ready, zero custom code needed for basic bridging. | HIGH |
| mcp (Python SDK) | 1.27.0 | MCP protocol implementation | Underlying SDK used by mcp-proxy and ida-mcp. Supports stdio, SSE, and Streamable HTTP transports. | HIGH |
| Streamable HTTP | Protocol 2025-03-26 | Network transport | The current MCP standard. SSE was deprecated June 2025. All major clients (Claude Code, mastra.ai) support Streamable HTTP with automatic SSE fallback. | HIGH |
### Claude Code Host-Side Client
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Claude Code `.mcp.json` | current | Connect host Claude Code to container MCP | Native support for `type: "http"` with `url` field. Auto-detects Streamable HTTP, falls back to SSE. Supports `${ENV_VAR}` expansion for tokens. | HIGH |
### Mastra.ai Client Integration
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| @mastra/mcp | 1.3.x | MCP client for mastra.ai agents | Official mastra MCP client package. Auto-detects Streamable HTTP when given a `url`. Replaces deprecated `MastraMCPClient`. | HIGH |
| @mastra/core | latest | Mastra framework core | Required peer dependency for agents and tools | MEDIUM |
### Authentication & Security
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Bearer token (static) | n/a | Simple auth for container MCP endpoint | Container runs locally or on trusted network. OAuth 2.1 is overkill for single-user/team tooling behind Docker network or VPN. Generate a random token at container start, pass via env var. | HIGH |
| Docker network isolation | n/a | Network boundary | Bind MCP port to localhost only by default; explicit opt-in for network exposure | HIGH |
## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| IDA MCP server | ida-pro-mcp (mrexodia) | ida-mcp (jtsylve) | jtsylve's version has 190+ tools and stdio transport, but ida-pro-mcp's headless idalib mode with built-in SSE server better fits the remote MCP architecture (no proxy needed). User preference. |
| IDA MCP server | ida-pro-mcp (mrexodia) | ida-headless-mcp (zboralski) | Less mature, fewer tools (~30 vs ~50), less active development |
| Remote transport | mcp-proxy | Custom FastMCP gateway | Unnecessary dev work for v1. mcp-proxy does stdio-to-HTTP bridging out of the box. |
| Remote transport | mcp-proxy | TypeScript MCP SDK + Express | Adds Node.js server dependency to Python-centric container for no benefit |
| Remote transport | Streamable HTTP | SSE (legacy) | SSE deprecated June 2025. Both Claude Code and mastra.ai try Streamable HTTP first. |
| Auth | Bearer token | OAuth 2.1 | Massive complexity for zero benefit in local/team Docker deployment |
| MCP aggregation | mcp-proxy (multi-server) | MetaMCP | MetaMCP is a full SaaS platform with web UI -- overkill for container-internal aggregation |
## Do NOT Use
| Technology | Why Not |
|------------|---------|
| ida-mcp (jtsylve) | Not selected — ida-pro-mcp chosen instead for built-in SSE transport and user preference. |
| SSE transport (deprecated) | Deprecated in MCP spec June 2025. Use Streamable HTTP. Clients fall back to SSE automatically if needed. |
| MastraMCPClient (old class) | Deprecated in mastra.ai. Use `MCPClient` from `@mastra/mcp`. |
| mcp-remote (npm) | Had CVE-2025-6514 (CVSS 9.6 command injection). Use official SDK or mcp-proxy instead. |
| OAuth 2.1 for container auth | Engineering overkill for single-team local/VPN deployment. |
## Installation
### Inside Docker container (build time)
# IDA Pro headless MCP (alongside existing tools)
# MCP proxy for remote access
# Or with uv (faster)
### Docker compose port exposure
### Container entrypoint addition
# Start mcp-proxy bridging the active disassembler MCP to Streamable HTTP
### Host-side Claude Code
### Mastra.ai project
## Version Compatibility Matrix
| Component | Min Version | Tested With | Notes |
|-----------|-------------|-------------|-------|
| IDA Pro | 9.0 | 9.x | Requires idalib support |
| Python | 3.11 | 3.11+ | ida-pro-mcp requirement |
| mcp (Python SDK) | 1.20+ | 1.27.0 | Streamable HTTP support |
| mcp-proxy | 0.3.0+ | 0.3.2 | Streamable HTTP bridging |
| Claude Code | current | current | `type: "http"` in .mcp.json |
| @mastra/mcp | 1.3.0+ | 1.3.1 | MCPClient with url transport |
## Sources
- [ida-pro-mcp GitHub (mrexodia)](https://github.com/mrexodia/ida-pro-mcp) -- GUI plugin + headless idalib, SSE transport, 50+ tools
- [idapro PyPI](https://pypi.org/project/idapro/) -- official Hex-Rays idalib Python wrapper (v0.0.7)
- [idalib docs (Hex-Rays)](https://docs.hex-rays.com/user-guide/idalib) -- idalib installation and activation
- [MCP Transports spec](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) -- Streamable HTTP standard
- [MCP Python SDK](https://pypi.org/project/mcp/) -- v1.27.0
- [mcp-proxy GitHub](https://github.com/sparfenyuk/mcp-proxy) -- stdio-to-HTTP bridge
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) -- reference (not recommended for this project)
- [Mastra MCPClient docs](https://mastra.ai/reference/tools/mcp-client) -- URL transport, auto Streamable HTTP
- [@mastra/mcp npm](https://www.npmjs.com/package/@mastra/mcp) -- v1.3.1
- [Claude Code MCP docs](https://code.claude.com/docs/en/mcp) -- .mcp.json http type
- [MCP Auth guide](https://modelcontextprotocol.io/docs/tutorials/security/authorization) -- OAuth vs Bearer
- [CVE-2025-6514](https://stackoverflow.blog/2026/01/21/is-that-allowed-authentication-and-authorization-in-model-context-protocol/) -- mcp-remote vulnerability
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
