# Phase 1: IDA Pro Backend - Context

**Gathered:** 2026-04-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Local agents inside the container can use IDA Pro for disassembly and decompilation via headless MCP, with automatic fallback across all three backends (IDA > BN > Ghidra). IDA Pro installs conditionally at build time, license persists via host bind mount, and Python environments coexist without conflicts.

</domain>

<decisions>
## Implementation Decisions

### Co-installation model
- All three disassemblers (BN, IDA, Ghidra) can coexist in the same image via independent build args (`INSTALL_BINARY_NINJA`, `INSTALL_IDA_PRO`)
- Ghidra is only installed when neither BN nor IDA is enabled (not always-on fallback)
- Only one disassembler active at a time -- fallback chain picks the highest-priority installed backend
- No simultaneous MCP server registration -- one backend per session

### Backend selection & fallback chain
- Priority order: IDA > BN > Ghidra (IDA preferred when installed)
- No manual override via env var -- priority chain only
- Log which backend was selected at container start (e.g., "Using IDA Pro (highest priority installed)")
- If the selected backend fails to start (e.g., license issue), fail with a clear warning -- do NOT silently fall back to the next backend

### IDA Pro provisioning
- Zip-at-build-time pattern, same as Binary Ninja -- place `idapro.zip` in repo root or set `IDA_PRO_ZIP` env var
- `run_docker.sh` detects the zip and passes it as a named build context (`ida-stage`)
- IDA Pro license persisted via host bind mount: `~/.idapro-docker/` -> `/home/agent/.idapro/`
- Auto-seed license from `~/.idapro/ida.key` if available (same pattern as BN's `license.dat` seeding)
- `ida-mcp` installed at Docker build time via pip/uv (PyPI package, not a runtime git clone)

### Hex-Rays decompiler
- Auto-detect from IDA license at runtime -- no explicit build arg or config needed
- If agent calls decompile without Hex-Rays license, return a clear error message (don't hide the tools)
- All architectures supported -- no artificial limits on what IDA/Hex-Rays can decompile

### Claude's Discretion
- Python environment isolation strategy (venvs, system-wide, etc.) for BN + IDA + Ghidra coexistence
- Exact ida-mcp installation method (pip vs uv)
- Multi-stage Docker build details for license security
- configure-agent-mcp.sh implementation for three-way detection

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `run_docker.sh`: Binary Ninja zip detection + named build context pattern -- replicate for IDA Pro
- `configure-agent-mcp.sh`: Backend detection + MCP config generation -- extend with IDA detection
- `docker-bin/claude` and `docker-bin/codex`: Agent wrappers -- no changes needed
- `compose.yaml`: Volume mount pattern -- add IDA Pro user directory mount

### Established Patterns
- Conditional install via build args (`INSTALL_BINARY_NINJA=0|1`)
- Named build context for large files (avoids BuildKit 500KB secret limit)
- Host bind mounts for license persistence (`~/.binaryninja-docker/`)
- License seeding from host home directory on first run
- System-wide Python packages via `pip install --break-system-packages`
- MCP config written as JSON to `/agent/.mcp.json` and Codex config

### Integration Points
- `Dockerfile`: New conditional IDA install block (parallel to BN block)
- `run_docker.sh`: IDA zip detection, `IDA_USER_DIR` env var, compose env passthrough
- `compose.yaml`: New volume mount for `~/.idapro-docker/`
- `configure-agent-mcp.sh`: Three-way backend detection (currently two-way: BN or Ghidra)
- `agent-entrypoint.sh`: No changes expected -- calls configure-agent-mcp.sh which handles detection

</code_context>

<specifics>
## Specific Ideas

- Follow Binary Ninja's exact provisioning UX -- zip in repo root, env var override, auto-seed license
- Logging at container start should clearly show: what was detected, what was selected, and why
- README.md should document the new IDA Pro provisioning workflow (user explicitly requested)

</specifics>

<deferred>
## Deferred Ideas

- README.md documentation for IDA Pro setup workflow -- user requested, do after implementation
- User-configurable priority chain via env var (e.g., `DISASM_PRIORITY=ida,bn,ghidra`) -- decided against for now, but could revisit
- Simultaneous multi-backend MCP registration -- decided one-at-a-time for now

</deferred>

---

*Phase: 01-ida-pro-backend*
*Context gathered: 2026-04-08*
