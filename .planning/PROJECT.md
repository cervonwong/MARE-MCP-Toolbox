# MARE-MCP-Toolbox v2

## What This Is

An agentic malware analysis platform built on a Kali Linux Docker container with 50+ reverse engineering tools and MCP-connected disassembler backends (Binary Ninja, Ghidra, and now IDA Pro). v2 adds the ability to expose the entire container as a remote MCP server, enabling external clients — Claude Code on the host, mastra.ai, or any MCP-compatible agent framework — to use the container's tools without running an agent inside it.

## Core Value

Automated malware triage and deep analysis via AI agents with full access to professional RE tooling — accessible both from inside the container (current mode) and from external MCP clients (new mode).

## Requirements

### Validated

- ✓ Kali Linux Docker container with 50+ RE tools — existing
- ✓ Binary Ninja headless MCP backend (conditional install) — existing
- ✓ Ghidra headless MCP fallback — existing
- ✓ Malware analysis orchestrator skill (Claude Code + Codex) — existing
- ✓ 13-artifact structured case pipeline — existing
- ✓ Content-hash Docker image caching — existing
- ✓ Agent wrappers for Claude Code and Codex inside container — existing
- ✓ IDA Pro as optional disassembler backend — Validated in Phase 1: ida-pro-backend
- ✓ Curated MCP tool surface (22 gateway-native tools) over Streamable HTTP with bearer auth — Validated in Phase 2: mcp-gateway
- ✓ Streaming binary upload with sha256 content-addressing and 1 GB cap — Validated in Phase 2: mcp-gateway
- ✓ Backend-as-client routing (PinnedBackend ClientSession to IDA/BN/Ghidra) with unified disasm tool surface — Validated in Phase 2: mcp-gateway
- ✓ Remote MCP server mode — Streamable HTTP exposed via `compose.yaml` ports block driven by `MCP_GATEWAY_HOST_BIND/HOST_PORT`, no rebuild needed — Validated in Phase 3: container-integration
- ✓ Dual-mode operation — `./run_docker.sh` (v1-identical local) vs `./run_docker.sh --remote` (detached gateway) selected from one image; `MCP_GATEWAY_ENABLED` guard ensures local mode has zero gateway leak — Validated in Phase 3: container-integration

### Active

- [ ] Claude Code host-side MCP client compatibility — connect via `.mcp.json` to container's remote MCP server
- [ ] Mastra.ai client compatibility — container as MCP server consumable by mastra.ai agent workflows

### Out of Scope

- Rewriting existing orchestrator skill — existing workflow stays intact
- Building a custom UI or web frontend — clients are Claude Code, Codex, mastra.ai
- Dynamic analysis orchestration — static analysis focus maintained
- Replacing Binary Ninja or Ghidra — IDA Pro is an addition, not a replacement

## Context

- Current architecture: agents (Claude Code/Codex) run inside Docker container, call MCP tools locally via stdio transport
- Binary Ninja integration pattern: provide zip at build time, conditional Dockerfile install, MCP repo cloned at runtime, `configure-agent-mcp.sh` detects and registers
- MCP ecosystem is evolving — remote MCP servers use SSE or streamable HTTP transport instead of stdio
- IDA Pro has headless mode (`idat`/`idat64`) and IDAPython — need to research existing MCP wrappers
- Mastra.ai is a TypeScript AI agent framework that can consume MCP servers as tool providers
- Claude Code supports remote MCP servers in `.mcp.json` via `url` transport type

## Constraints

- **Licensing**: IDA Pro and Binary Ninja require user-provided licenses — never baked into images
- **Security**: Container runs with elevated capabilities (SYS_PTRACE, seccomp=unconfined) — remote MCP server must consider auth/network exposure
- **Transport**: Remote MCP needs network-accessible transport (SSE/HTTP), not stdio
- **Backward compatibility**: Existing "agent inside container" mode must continue working unchanged

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Add IDA Pro as third disassembler option | User request; IDA is industry standard for RE | ✓ Done — Phase 1 |
| Use ida-pro-mcp (mrexodia) over jtsylve fork | SSE transport built-in; better fits remote MCP architecture | ✓ Done — Phase 1 |
| Custom FastMCP gateway over mcp-proxy | 22 gateway-native curated tools + transparent backend pass-through; mcp-proxy was generic stdio bridge only | ✓ Done — Phase 2 |
| Bearer token + Origin header auth (no OAuth) | Single-team local/VPN deployment; OAuth 2.1 was overkill | ✓ Done — Phase 2 |
| sha256 content-addressed upload layout (`<UPLOAD_DIR>/<sha256>/<filename>`) | Dedup by content; round-trip via `resolve_sample` | ✓ Done — Phase 2 |
| PinnedBackend ClientSession (lifespan-managed) routes disasm tools to active backend | Long-lived session avoids reconnect cost; IDA via Streamable HTTP, BN/Ghidra via stdio subprocess | ✓ Done — Phase 2 |
| Expose container as remote MCP server | Enables Claude Code host + mastra.ai as clients | ✓ Done — Phase 3 (port publishing); Phase 4 (client configs) pending |
| Dual-mode architecture (local + remote) | Preserve existing workflow while adding new capability | ✓ Done — Phase 3 |
| `MCP_GATEWAY_ENABLED` Dockerfile guard for no-leak local mode | Structural guarantee that local mode = v1 byte-identical, gateway daemon never starts | ✓ Done — Phase 3 |
| Single launcher (`run_docker.sh --remote`) vs separate compose files | One UX entry point; mode selected by flag → env exports → compose overlay | ✓ Done — Phase 3 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-27 after Phase 3 (container-integration) completion*
