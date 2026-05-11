# Milestones — MARE-MCP-Toolbox v2

Historical record of shipped milestones. For current work, see `.planning/ROADMAP.md`.

---

## v1.0 — Remote MCP Foundation

**Shipped:** 2026-04-27
**Phases:** 1-4 (16 plans)
**Timeline:** 2026-03-18 → 2026-04-27 (~40 days, 151 commits)
**Archive:** [v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md) · [v1.0-REQUIREMENTS.md](milestones/v1.0-REQUIREMENTS.md)

**Delivered:** IDA Pro as a third disassembler backend plus a remote MCP gateway that exposes the container's analysis tools to Claude Code and mastra.ai over Streamable HTTP — without changing the existing in-container agent workflow.

**Key accomplishments:**
1. IDA Pro headless backend with multi-stage Docker build (license never in image layers), `idalib-mcp` SSE transport, and `configure-agent-mcp.sh` IDA > BN > Ghidra fallback chain
2. Custom FastMCP gateway: 22 curated tools over Streamable HTTP at `/mcp`, bearer-token auth + Origin DNS-rebind middleware, path-traversal and argv-only subprocess mitigations
3. `PinnedBackend` async ClientSession routing disassembler tools to IDA (HTTP) or BN/Ghidra (stdio subprocess), with `asyncio.Lock` serialization and native-name pass-through (`get_active_backend()` for discovery)
4. Streaming `POST /upload` with sha256 content-addressing, 1 GB cap, and rejected path-traversal/multipart content (10 unit + 4 integration tests)
5. Dual-mode container: `./run_docker.sh` (v1-identical local) vs `./run_docker.sh --remote` (detached gateway) from one image; `MCP_GATEWAY_ENABLED` Dockerfile guard makes local-mode byte-identical
6. External client templates: Claude Code `.mcp.json` with `${MARE_GATEWAY_TOKEN}` expansion, mastra.ai starter at `templates/mastra/` using `@mastra/mcp ~1.3.1`, and MCP Resources at `mare://cases/<case>/<artifact>` covering all 13 artifact types

### Known Gaps

- **CLI-01 manual UAT signoff** — `04-UAT.md` 8-step human walkthrough of Claude Code binary connection to a running container is not filled in. Automated verification (`test_claude_code_smoke.py`) covers `initialize → tools/list → tools/call` + auth-bypass 401 checks; the human-action gate (D-17 / Plan 04-07) remains pending and is carried into v1.1.

### Stats

- Phases: 4 (Plans: 16, all SUMMARY.md complete)
- Commits: 151
- LOC delta: +49,754 / -2,712 (across all repo files)
- Verification: Phase 1 ✓, Phase 2 ✓, Phase 3 ✓, Phase 4 ✓ automated (human_needed for CLI-01 UAT)
