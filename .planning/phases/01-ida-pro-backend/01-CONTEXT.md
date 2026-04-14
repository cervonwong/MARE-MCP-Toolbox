# Phase 1: IDA Pro Backend - Context

**Gathered:** 2026-04-08, **Updated:** 2026-04-14
**Status:** Ready for planning (replanning required — switched from ida-mcp to ida-pro-mcp)

<domain>
## Phase Boundary

Local agents inside the container can use IDA Pro for disassembly and decompilation via headless MCP (idalib-mcp SSE server), with automatic fallback across all three backends (IDA > BN > Ghidra). IDA Pro installs conditionally at build time, license persists via host bind mount, and Python environments coexist without conflicts.

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

### IDA Pro MCP server — ida-pro-mcp (mrexodia)
- **Package**: mrexodia/ida-pro-mcp (NOT jtsylve/ida-mcp)
- **Installation**: `pip install https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip` at Docker build time
- **Headless mode**: Uses `idalib-mcp` command which runs an SSE server on a configurable host/port
- **Transport**: SSE on localhost for Phase 1 (e.g., `http://localhost:8745/sse`). Future phases expose this SSE endpoint externally for remote clients.
- **Binary loading**: Agent starts idalib-mcp per-analysis with the target binary path. No persistent server at container boot. Agent manages the idalib-mcp lifecycle (start, analyze, stop).

### idalib setup (bundled install)
- Install idalib from IDA's own bundled files: `pip install /opt/ida-pro/idalib/python`
- Activate via `py-activate-idalib.py -d /opt/ida-pro`
- Do NOT use the `idapro` package from PyPI (outdated)
- Do NOT use `ida-mcp` from PyPI (wrong package — that's jtsylve's version)

### IDA Pro provisioning
- Zip-at-build-time pattern, same as Binary Ninja -- place `idapro.zip` in repo root or set `IDA_PRO_ZIP` env var
- `run_docker.sh` detects the zip and passes it as a named build context (`ida-stage`)
- IDA Pro license persisted via host bind mount: `~/.idapro-docker/` -> `/home/agent/.idapro/`
- Auto-seed license from `~/.idapro/ida.key` if available (same pattern as BN's `license.dat` seeding)

### MCP config patterns (configure-agent-mcp.sh)
- **BN/Ghidra**: stdio command in `.mcp.json` (existing pattern, unchanged)
- **IDA Pro**: SSE URL in `.mcp.json` (new pattern — `http://localhost:8745/sse`)
- configure-agent-mcp.sh ensures idalib is ready but does NOT start idalib-mcp (agent starts it per-analysis with target binary path)
- The script needs to handle both stdio and SSE config formats

### Hex-Rays decompiler
- Auto-detect from IDA license at runtime -- no explicit build arg or config needed
- If agent calls decompile without Hex-Rays license, return a clear error message (don't hide the tools)
- All architectures supported -- no artificial limits on what IDA/Hex-Rays can decompile

### Claude's Discretion
- Python environment isolation strategy (venvs, system-wide, etc.) for BN + IDA + Ghidra coexistence
- Multi-stage Docker build details for license security
- How agent manages idalib-mcp lifecycle (start/stop wrapper script or direct invocation)
- idalib-mcp port selection strategy (fixed port vs dynamic)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### IDA Pro MCP
- [ida-pro-mcp GitHub](https://github.com/mrexodia/ida-pro-mcp) — Primary MCP server. Check README for current install instructions, CLI flags, and idalib-mcp usage.
- [idalib docs (Hex-Rays)](https://docs.hex-rays.com/user-guide/idalib) — idalib installation and activation procedure

### Existing patterns
- `Dockerfile` — Current BN conditional install block to replicate for IDA
- `run_docker.sh` — BN zip detection and build context pattern to replicate
- `compose.yaml` — Volume mount pattern for license persistence
- `docker-bin/configure-agent-mcp.sh` — Backend detection logic to extend with IDA + SSE config

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `run_docker.sh`: Binary Ninja zip detection + named build context pattern -- replicate for IDA Pro
- `configure-agent-mcp.sh`: Backend detection + MCP config generation -- extend with IDA detection and SSE config format
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
- `configure-agent-mcp.sh`: Three-way backend detection — now handles both stdio (BN/Ghidra) and SSE (IDA) config formats
- `agent-entrypoint.sh`: May need changes to ensure idalib-mcp can be started by the agent

</code_context>

<specifics>
## Specific Ideas

- Follow Binary Ninja's exact provisioning UX -- zip in repo root, env var override, auto-seed license
- Logging at container start should clearly show: what was detected, what was selected, and why
- README.md should document the new IDA Pro provisioning workflow (user explicitly requested)
- For IDA, configure-agent-mcp.sh should verify idalib is activated (not just that the directory exists)

</specifics>

<deferred>
## Deferred Ideas

- README.md documentation for IDA Pro setup workflow -- user requested, do after implementation
- User-configurable priority chain via env var (e.g., `DISASM_PRIORITY=ida,bn,ghidra`) -- decided against for now, but could revisit
- Simultaneous multi-backend MCP registration -- decided one-at-a-time for now
- Exposing idalib-mcp SSE endpoint externally for remote clients -- Phase 2/3 scope

</deferred>

---

*Phase: 01-ida-pro-backend*
*Context gathered: 2026-04-08, updated: 2026-04-14*
