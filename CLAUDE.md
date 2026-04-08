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
| ida-mcp (jtsylve) | 2.1.0 | Headless IDA Pro MCP server | Best-in-class: 190+ tools, multi-binary support, built on idalib, PyPI-installable, active development (April 2026 release). Uses stdio transport which matches existing Binary Ninja/Ghidra pattern exactly. | HIGH |
| IDA Pro | 9+ | Disassembler engine | Required by ida-mcp; idalib (IDA-as-a-library) enables headless operation without GUI | HIGH |
| Python | 3.12+ | Runtime for ida-mcp | Required by ida-mcp 2.x; container already has Python 3.x, may need version bump | HIGH |
| uv | latest | Python package manager | Recommended by ida-mcp for installation; faster than pip, handles tool isolation | MEDIUM |
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
| IDA MCP server | ida-mcp (jtsylve) | ida-pro-mcp (mrexodia) | mrexodia's version requires IDA GUI running (plugin-based), not headless. Does not fit Docker container pattern. |
| IDA MCP server | ida-mcp (jtsylve) | ida-headless-mcp (zboralski) | Less mature, fewer tools (~30 vs ~190), less active development |
| Remote transport | mcp-proxy | Custom FastMCP gateway | Unnecessary dev work for v1. mcp-proxy does stdio-to-HTTP bridging out of the box. |
| Remote transport | mcp-proxy | TypeScript MCP SDK + Express | Adds Node.js server dependency to Python-centric container for no benefit |
| Remote transport | Streamable HTTP | SSE (legacy) | SSE deprecated June 2025. Both Claude Code and mastra.ai try Streamable HTTP first. |
| Auth | Bearer token | OAuth 2.1 | Massive complexity for zero benefit in local/team Docker deployment |
| MCP aggregation | mcp-proxy (multi-server) | MetaMCP | MetaMCP is a full SaaS platform with web UI -- overkill for container-internal aggregation |
## Do NOT Use
| Technology | Why Not |
|------------|---------|
| ida-pro-mcp (mrexodia) for headless | Requires running IDA GUI as a plugin host. Not suitable for headless Docker. |
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
| Python | 3.12 | 3.12+ | ida-mcp requirement (stricter than container's current Python) |
| mcp (Python SDK) | 1.20+ | 1.27.0 | Streamable HTTP support |
| mcp-proxy | 0.3.0+ | 0.3.2 | Streamable HTTP bridging |
| Claude Code | current | current | `type: "http"` in .mcp.json |
| @mastra/mcp | 1.3.0+ | 1.3.1 | MCPClient with url transport |
## Sources
- [ida-mcp PyPI](https://pypi.org/project/ida-mcp/) -- v2.1.0, April 2026
- [ida-mcp GitHub (jtsylve)](https://github.com/jtsylve/ida-mcp) -- headless, stdio, 190+ tools
- [ida-mcp 2.0 announcement](https://jtsylve.blog/post/2026/03/25/Announcing-ida-mcp-2) -- architecture details
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
