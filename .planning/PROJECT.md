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

### Active

- [ ] IDA Pro as optional disassembler backend (same pattern as Binary Ninja — conditional install, headless MCP server)
- [ ] Remote MCP server mode — expose container tools as MCP endpoints accessible over network transport (SSE/streamable HTTP)
- [ ] Claude Code host-side MCP client compatibility — connect via `.mcp.json` to container's remote MCP server
- [ ] Mastra.ai client compatibility — container as MCP server consumable by mastra.ai agent workflows
- [ ] Curated MCP tool surface — expose orchestrator-level operations (triage, strings, YARA, decompile, etc.) not raw CLI wrappers
- [ ] Dual-mode operation — both "agent inside container" and "remote MCP server" modes work simultaneously or selectively

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
| Add IDA Pro as third disassembler option | User request; IDA is industry standard for RE | — Pending |
| Expose container as remote MCP server | Enables Claude Code host + mastra.ai as clients | — Pending |
| Research existing IDA headless MCP projects | Build vs. buy decision for IDA MCP integration | — Pending |
| Dual-mode architecture (local + remote) | Preserve existing workflow while adding new capability | — Pending |

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
*Last updated: 2026-04-08 after initialization*
