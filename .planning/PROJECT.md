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

- ✓ Claude Code host-side MCP client compatibility — automated e2e + manual UAT signoff 2026-05-11 — Validated in Phase 4: external-client-integration (CLI-01)
- ✓ Mastra.ai client compatibility — `templates/mastra/` runnable starter, full triage happy path — Validated in Phase 4: external-client-integration (CLI-02)

### Active

(None — v1.0 shipped. Run `/gsd-new-milestone` to scope v1.1.)

### Out of Scope

- Rewriting existing orchestrator skill — existing workflow stays intact
- Building a custom UI or web frontend — clients are Claude Code, Codex, mastra.ai
- Dynamic analysis orchestration — static analysis focus maintained
- Replacing Binary Ninja or Ghidra — IDA Pro is an addition, not a replacement

## Current State

**Shipped:** v1.0 Remote MCP Foundation (2026-04-27) — see [.planning/MILESTONES.md](MILESTONES.md)

- Three disassembler backends (IDA Pro, Binary Ninja, Ghidra) with IDA > BN > Ghidra fallback chain
- Custom FastMCP gateway exposing 22 curated tools over Streamable HTTP at `/mcp` with bearer-token auth and Origin DNS-rebind middleware
- `PinnedBackend` async ClientSession routes disassembler tools to IDA (HTTP) or BN/Ghidra (stdio); native-name pass-through, `get_active_backend()` for discovery
- Streaming `POST /upload` with sha256 content-addressing, 1 GB cap, path-traversal/multipart rejection
- Dual-mode container: `./run_docker.sh` (v1-identical local) vs `./run_docker.sh --remote` (gateway) from one image; `MCP_GATEWAY_ENABLED` Dockerfile guard ensures byte-identical local mode
- External client templates: Claude Code `.mcp.json` with env-var token expansion, mastra.ai starter (`@mastra/mcp ~1.3.1`), MCP Resources at `mare://cases/<case>/<artifact>` covering all 13 artifact types

**Carryover Finding (F-1, v1.1):** `run_docker.sh` content-hash for the image cache covers `Dockerfile`, `docker-bin/`, and the disassembler zips, but **not `mcp-gateway/src/`**. Edits to the gateway package land in repo and pass unit/e2e tests (which import from the source tree) but the running container keeps the previously-baked code. Surfaced during 2026-05-11 UAT — Plan 04-03's `tools/resources.py` had to be rebuilt into the image before `resources/list` returned non-empty. Fix in v1.1: extend `DOCKERFILE_SHA` to include `mcp-gateway/`.

## Next Milestone Goals

To be scoped via `/gsd-new-milestone`. Candidate themes from v2 backlog and v1.0 carryovers:

- **F-1 fix** — extend `run_docker.sh` content-hash to include `mcp-gateway/` so gateway-package edits trigger an image rebuild
- **GW-V2-01..04** — MCP Prompts as orchestrator templates; progress notifications; multi-session support; session lifecycle management
- **DIS-V2-01/02** — Unified disassembler abstraction layer; backend comparison mode (diff IDA/BN/Ghidra outputs on the same sample)

## Context

- Current architecture: agents (Claude Code/Codex) run inside Docker container; remote clients connect to the same container via Streamable HTTP at `/mcp` (port 8080 by default, localhost-only unless `MCP_GATEWAY_HOST_BIND` set)
- Binary Ninja and IDA Pro use the same provisioning pattern: zip at build time, conditional Dockerfile install, MCP server registered by `configure-agent-mcp.sh`
- MCP ecosystem standardized on Streamable HTTP (spec 2025-03-26) — SSE deprecated June 2025; clients fall back automatically
- Mastra.ai is a TypeScript AI agent framework that consumes MCP servers via `@mastra/mcp ~1.3.1`; full triage workflow demonstrated in `templates/mastra/`
- Claude Code supports remote MCP servers in `.mcp.json` via `type: "http"` with `${ENV_VAR}` expansion at parse time

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
*Last updated: 2026-04-27 after v1.0 milestone (Remote MCP Foundation) completion*
