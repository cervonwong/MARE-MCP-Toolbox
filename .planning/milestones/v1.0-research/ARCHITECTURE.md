# Architecture Patterns

**Domain:** Agentic malware analysis platform with remote MCP server capability
**Researched:** 2026-04-08

## Recommended Architecture

### High-Level Overview

The system operates in two modes simultaneously from a single Docker container:

```
+------------------------------------------------------------------+
|  HOST MACHINE                                                     |
|                                                                   |
|  Claude Code  <---.mcp.json (url: http)--+                       |
|  mastra.ai   <--MCPClient (url: http)----+                       |
|                                          |                        |
|  +---------------------------------------v----------------------+ |
|  |  KALI DOCKER CONTAINER               :8080 (MCP Gateway)    | |
|  |                                                              | |
|  |  +------------------+     +-----------------------------+    | |
|  |  | MCP Gateway      |     | Local Agent Mode            |   | |
|  |  | (FastMCP/Python)  |     | (Claude Code / Codex)       |   | |
|  |  | Streamable HTTP  |     | .mcp.json -> stdio backends |   | |
|  |  +--------+---------+     +-------------+---------------+    | |
|  |           |                             |                    | |
|  |           v                             v                    | |
|  |  +--------------------------------------------------+       | |
|  |  |          Tool Router / Registry                    |       | |
|  |  |  (maps MCP tool calls to container executables)    |       | |
|  |  +----+------------+------------+-----+---------+----+       | |
|  |       |            |            |     |         |            | |
|  |       v            v            v     v         v            | |
|  |  +---------+ +---------+ +------+ +-----+ +--------+        | |
|  |  | Binary  | | Ghidra  | | IDA  | | RE  | | YARA/  |        | |
|  |  | Ninja   | | Headless| | Pro  | | CLI | | Capa/  |        | |
|  |  | MCP     | | MCP     | | MCP  | | 50+ | | Strings|        | |
|  |  | (stdio) | | (stdio) | |(stdio)| |tools| | etc    |        | |
|  |  +---------+ +---------+ +------+ +-----+ +--------+        | |
|  +--------------------------------------------------------------+ |
+------------------------------------------------------------------+
```

### Component Boundaries

| Component | Responsibility | Communicates With | Transport |
|-----------|---------------|-------------------|-----------|
| **MCP Gateway** | Exposes container tools over Streamable HTTP; handles auth, session management | External clients (Claude Code, mastra.ai), Tool Router | HTTP :8080 inbound, internal function calls to router |
| **Tool Router/Registry** | Maps MCP tool names to backend executables; dispatches calls; collects results | MCP Gateway, all tool backends | Internal Python function calls |
| **Binary Ninja MCP** | Disassembly/decompilation via BN headless | Tool Router | stdio (existing `binary_ninja_headless_mcp.py`) |
| **Ghidra MCP** | Disassembly/decompilation via Ghidra headless | Tool Router | stdio (existing `ghidra_headless_mcp.py`) |
| **IDA Pro MCP** | Disassembly/decompilation via IDA idalib | Tool Router | stdio (via `ida-mcp` or `idalib-mcp`) |
| **RE CLI Tools** | 50+ command-line RE tools (strings, YARA, capa, ssdeep, etc.) | Tool Router | subprocess/exec |
| **Local Agent Mode** | Claude Code/Codex running inside container | Disassembler MCPs via stdio, CLI tools directly | stdio, subprocess |
| **configure-agent-mcp.sh** | Detects available backends, writes .mcp.json for local agents | Filesystem, disassembler detection | Shell script (existing) |

### Dual-Mode Operation

Both modes share the same container and tool backends. The key design principle: **the MCP Gateway is an additional entry point, not a replacement for local agent mode.**

- **Local mode:** Agent runs inside container, calls disassembler MCP servers via stdio, calls CLI tools directly. Unchanged from v1.
- **Remote mode:** External client connects to MCP Gateway over HTTP. Gateway translates MCP tool calls into the same backend invocations local agents use.

## Data Flow

### Mode 1: Local Agent (Existing -- No Changes)

```
Claude Code (inside container)
  -> reads .mcp.json (stdio config for BN/Ghidra/IDA)
  -> spawns MCP server process via stdio
  -> sends tool call (e.g., "decompile function at 0x401000")
  -> receives result
  -> also calls CLI tools directly (subprocess)
```

### Mode 2: Remote MCP Client (New)

```
Claude Code (host) / mastra.ai
  -> HTTP POST to http://localhost:8080/mcp
  -> MCP Gateway receives JSON-RPC tool call
  -> Tool Router identifies backend:
     - Disassembler tool? -> Dispatch to BN/Ghidra/IDA MCP subprocess
     - CLI tool? -> Execute subprocess, capture output
     - Orchestrator tool? -> Run multi-step analysis pipeline
  -> Gateway returns result via Streamable HTTP response
  -> (optionally upgrades to SSE for long-running operations)
```

### Data Flow: Sample Upload and Analysis

```
External Client                    MCP Gateway              Tool Router
     |                                 |                        |
     |-- tools/call: upload_sample --> |                        |
     |   (binary payload, base64)      |-- save to /agent/--- >|
     |                                 |                        |
     |-- tools/call: triage ---------> |-- run strings -------> |
     |                                 |-- run file ----------> |
     |                                 |-- run die ------------> |
     |                                 |-- run ssdeep ---------> |
     |                                 |<-- aggregate results --|
     |<-- structured triage result --- |                        |
     |                                 |                        |
     |-- tools/call: decompile ------> |-- dispatch to IDA ---> |
     |   (func_addr: 0x401000)         |   (stdio subprocess)   |
     |<-- decompiled C code ---------- |<-- result -------------|
```

## Component Details

### MCP Gateway (New Component -- Core of v2)

**Technology:** Python with `mcp` SDK (FastMCP), Streamable HTTP transport.

**Why FastMCP Python (not TypeScript, not custom):**
- The existing tool ecosystem is Python-based (disassembler MCPs, orchestrator scripts)
- FastMCP provides Streamable HTTP out of the box: `mcp.run(transport="streamable-http")`
- The Python MCP SDK v1.8.0+ supports the 2025-03-26 protocol spec with Streamable HTTP
- Both SSE backward compat and Streamable HTTP from a single server instance
- Stateless mode (`stateless_http=True`) available for scalability

**Architecture pattern:**

```python
from mcp.server.fastmcp import FastMCP

gateway = FastMCP("mare-toolbox", stateless_http=True)

@gateway.tool()
async def triage_sample(file_path: str) -> str:
    """Run initial triage: file type, strings, hashes, DIE, capa."""
    # Orchestrates multiple CLI subprocess calls
    ...

@gateway.tool()
async def decompile_function(binary_path: str, address: str) -> str:
    """Decompile a function using the active disassembler backend."""
    # Routes to whichever disassembler is available
    ...

# Expose on port 8080, path /mcp
gateway.run(transport="streamable-http", host="0.0.0.0", port=8080, mount_path="/mcp")
```

**Key design decisions:**
- Expose orchestrator-level operations (triage, decompile, scan_yara), NOT raw CLI wrappers
- The gateway aggregates results from multiple tools into coherent responses
- Curated tool surface (~15-25 high-value tools) not 190+ raw IDA tools

### Tool Router / Disassembler Selection

**Current pattern** (from `configure-agent-mcp.sh`): Priority order is Binary Ninja > Ghidra. Whichever is detected first wins.

**Extended pattern for v2:** Priority order becomes Binary Ninja > IDA Pro > Ghidra. The selection logic runs at container startup and sets an environment variable or writes a config file.

```bash
# Detection priority (in configure-agent-mcp.sh)
if [ -f /opt/binaryninja/... ]; then
    DISASSEMBLER=binja
elif [ -f /opt/idapro/idat64 ] || python3 -c "import ida_idaapi" 2>/dev/null; then
    DISASSEMBLER=ida
elif command -v ghidra >/dev/null; then
    DISASSEMBLER=ghidra
fi
```

**The Tool Router** (Python module used by MCP Gateway) reads this selection and dispatches decompilation/disassembly calls accordingly. It does NOT expose three separate sets of disassembler tools -- it exposes a unified interface:

| Tool Name | Description | Routes To |
|-----------|-------------|-----------|
| `decompile_function` | Decompile function at address | Active disassembler backend |
| `list_functions` | List all functions in binary | Active disassembler backend |
| `get_xrefs` | Get cross-references | Active disassembler backend |
| `rename_function` | Rename a function | Active disassembler backend |
| `get_disassembly` | Get assembly for address range | Active disassembler backend |

This unified interface means external clients do not need to know which disassembler is running.

### IDA Pro Integration (New Backend)

**Recommended approach:** Use `mrexodia/ida-pro-mcp` with `idalib-mcp` headless mode.

**Why this project over alternatives:**
- Most mature (mrexodia is a well-known RE tool author)
- Supports both stdio and SSE/HTTP transports
- `idalib` approach = no GUI dependency, true headless operation
- `--isolated-contexts` for safe multi-agent concurrent access
- Active development, recently updated

**Alternative considered:** `jtsylve/ida-mcp` (ida-mcp 2.0) -- 190 tools, stdio only, per-database subprocess isolation. More comprehensive tool surface but stdio-only limits remote use. Could be used as the stdio backend for local agent mode.

**Installation pattern (mirrors Binary Ninja):**
- IDA Pro installer/zip provided by user at build time (never in image)
- `INSTALL_IDA_PRO` build arg controls conditional install
- `idalib` Python bindings installed during build
- License file mounted at runtime via volume (same as BN license.dat pattern)

```dockerfile
ARG INSTALL_IDA_PRO=0

# Install IDA Pro headless from user-provided archive
RUN --mount=type=bind,from=ida-stage,target=/tmp/ida-stage \
    set -eux; \
    if [ "${INSTALL_IDA_PRO}" != "1" ]; then exit 0; fi; \
    # Extract and install IDA to /opt/idapro
    # Install idalib Python bindings
    ...
```

**Runtime volumes:**
```yaml
volumes:
  - "${IDA_USER_DIR:-/tmp/.idapro-docker}:/home/agent/.idapro"
```

### Authentication and Security

The container already runs with `SYS_PTRACE` and `seccomp=unconfined` -- it handles malware. The MCP Gateway adds network exposure, requiring:

1. **Bind to localhost only by default** (`--host 127.0.0.1`). Docker port mapping (`-p 8080:8080`) controls external access.
2. **Bearer token auth** via environment variable (`MCP_AUTH_TOKEN`). Gateway validates `Authorization: Bearer <token>` header on every request.
3. **No TLS in container** -- rely on Docker network isolation or a reverse proxy for production use.

```python
# Gateway auth middleware
@gateway.middleware
async def check_auth(request, call_next):
    expected = os.environ.get("MCP_AUTH_TOKEN")
    if expected and request.headers.get("Authorization") != f"Bearer {expected}":
        raise HTTPException(401, "Unauthorized")
    return await call_next(request)
```

## Client Integration

### Claude Code on Host

`.mcp.json` at project root on host machine:

```json
{
  "mcpServers": {
    "mare-toolbox": {
      "type": "http",
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer ${MARE_MCP_TOKEN}"
      }
    }
  }
}
```

Claude Code reads this, connects via Streamable HTTP, and the container's tools appear as available MCP tools in the session.

### mastra.ai

```typescript
import { MCPClient } from "@mastra/mcp";

const mcpClient = new MCPClient({
  servers: {
    "mare-toolbox": {
      url: new URL("http://localhost:8080/mcp"),
      requestInit: {
        headers: {
          Authorization: `Bearer ${process.env.MARE_MCP_TOKEN}`,
        },
      },
    },
  },
});

// Get tools for agent
const tools = await mcpClient.getTools();
const agent = new Agent({
  name: "malware-analyst",
  tools,
  // ...
});
```

## Docker Compose Changes

```yaml
services:
  kali:
    image: "kali-re-tools:${IMAGE_TAG:-latest}"
    pull_policy: never
    working_dir: /agent
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
    ports:
      - "${MCP_PORT:-8080}:8080"  # NEW: expose MCP gateway
    volumes:
      - "${HOST_PWD:-.}:/agent"
      - "${BINARY_NINJA_USER_DIR:-/tmp/.binaryninja-docker}:/home/agent/.binaryninja"
      - "${IDA_USER_DIR:-/tmp/.idapro-docker}:/home/agent/.idapro"  # NEW
      - "${CLAUDE_USER_DIR:-/tmp/.claude-docker}:/home/agent/.claude"
      - "${CODEX_USER_DIR:-/tmp/.codex-docker}:/home/agent/.codex"
    environment:
      - BN_USER_DIRECTORY=/home/agent/.binaryninja
      - HOME=/home/agent
      - USER=agent
      - LOGNAME=agent
      - MCP_AUTH_TOKEN=${MCP_AUTH_TOKEN:-}  # NEW
      - MCP_GATEWAY_ENABLED=${MCP_GATEWAY_ENABLED:-1}  # NEW
    stdin_open: true
    tty: true
    command: ["/bin/bash"]
```

## Patterns to Follow

### Pattern 1: Unified Disassembler Interface
**What:** Single set of MCP tools that route to whichever disassembler is installed
**When:** Always, for the MCP Gateway tool surface
**Why:** External clients should not need to know or care which backend is active. The tool names stay stable; only the implementation changes.

### Pattern 2: Orchestrator-Level Tool Granularity
**What:** Expose high-level operations (triage, decompile, yara_scan) not raw CLI wrappers
**When:** For the remote MCP tool surface
**Why:** An LLM calling `triage_sample` and getting structured results is far more useful than calling `strings`, `file`, `ssdeep`, and `die` separately and having to parse each output. The container already has orchestrator logic for this in the analysis skill.

### Pattern 3: Conditional Install via Build Args
**What:** `INSTALL_IDA_PRO=0|1` build arg, same pattern as `INSTALL_BINARY_NINJA`
**When:** IDA Pro Dockerfile integration
**Why:** Proven pattern in this project. User provides archive at build time, build arg controls whether it is installed. License mounted at runtime.

### Pattern 4: Entrypoint Gateway Launch
**What:** Start MCP Gateway process in entrypoint alongside existing setup
**When:** Container startup with `MCP_GATEWAY_ENABLED=1`
**Why:** The gateway should start automatically when the container runs. Background process managed by entrypoint script. Local agent mode continues to work in the foreground.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Exposing Raw Disassembler MCP Servers Over Network
**What:** Forwarding mrexodia/ida-pro-mcp's 100+ tools directly through the gateway
**Why bad:** Floods the LLM context window with tool descriptions, most of which are too low-level to be useful from an external client. Each disassembler has different tool names, breaking the unified interface.
**Instead:** Curate 15-25 high-value tools in the gateway that delegate to the appropriate backend.

### Anti-Pattern 2: Running Disassembler MCP Servers as Separate HTTP Services
**What:** Running BN MCP on :8001, Ghidra MCP on :8002, IDA MCP on :8003
**Why bad:** Adds unnecessary complexity. Multiple ports to manage, multiple processes, client needs to know which port. The existing stdio pattern works well for backend communication.
**Instead:** Keep disassembler MCPs as stdio subprocesses. Only the gateway listens on a network port.

### Anti-Pattern 3: Modifying the Existing Local Agent Workflow
**What:** Changing how Claude Code/Codex inside the container accesses tools
**Why bad:** Working system. Local agents already have `.mcp.json` with stdio transport to their disassembler. No reason to route them through HTTP.
**Instead:** Local agents keep stdio. Gateway is a parallel path for external clients only.

### Anti-Pattern 4: Baking Secrets Into Images
**What:** Including IDA/BN license files, API keys, or auth tokens in Docker images
**Why bad:** Security risk, licensing violation, breaks caching
**Instead:** Mount licenses via volumes, pass tokens via environment variables.

## Scalability Considerations

| Concern | Single User | Multi-Agent | Production |
|---------|-------------|-------------|------------|
| Concurrent analysis | Sequential | `--isolated-contexts` on IDA MCP | Multiple container replicas |
| Gateway load | Negligible | Single process fine | Add uvicorn workers |
| Binary storage | /agent mount | /agent mount | Shared volume or object store |
| Disassembler licensing | 1 seat | 1 seat (serial access) | 1 seat per container replica |

## Suggested Build Order

Dependencies flow top-to-bottom; each phase builds on the previous.

### Phase 1: IDA Pro Backend Integration
- Extend Dockerfile with conditional IDA Pro install (mirrors Binary Ninja pattern)
- Extend `configure-agent-mcp.sh` to detect IDA Pro and configure stdio MCP
- Extend `run_docker.sh` to handle IDA Pro archive and license mount
- Clone `mrexodia/ida-pro-mcp` or `jtsylve/ida-mcp` into `mcp/` directory
- **Dependency:** None. Can be built and tested entirely within existing local agent mode.
- **Validation:** Local Claude Code inside container can use IDA Pro for decompilation.

### Phase 2: MCP Gateway Foundation
- Create `gateway/` directory with FastMCP-based Python server
- Implement Tool Router with unified disassembler interface
- Wrap 15-25 curated RE tools as MCP tool functions
- Add bearer token auth middleware
- Test with MCP Inspector or `curl` against Streamable HTTP endpoint
- **Dependency:** Phase 1 (IDA backend should exist for testing all three backends)
- **Validation:** Can call `triage_sample` and `decompile_function` via HTTP.

### Phase 3: Container Integration and Dual-Mode
- Modify entrypoint to optionally start MCP Gateway as background process
- Update `compose.yaml` with port mapping and new env vars
- Update `run_docker.sh` for new IDA volumes and gateway config
- Ensure local agent mode still works unchanged alongside gateway
- **Dependency:** Phase 2 (gateway must exist to integrate)
- **Validation:** Container starts, gateway listens on :8080, local `claude` still works via stdio.

### Phase 4: External Client Integration
- Create host-side `.mcp.json` template for Claude Code
- Document mastra.ai MCPClient configuration
- Test end-to-end: Claude Code on host -> HTTP -> gateway -> IDA/BN/Ghidra -> result
- Test mastra.ai agent workflow consuming container tools
- **Dependency:** Phase 3 (dual-mode must work)
- **Validation:** Full round-trip from host Claude Code through to decompilation result.

## Sources

- [mrexodia/ida-pro-mcp](https://github.com/mrexodia/ida-pro-mcp) - IDA Pro MCP with idalib headless mode (HIGH confidence)
- [jtsylve/ida-mcp 2.0](https://jtsylve.blog/post/2026/03/25/Announcing-ida-mcp-2) - Alternative headless IDA MCP (MEDIUM confidence)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) - FastMCP with Streamable HTTP (HIGH confidence)
- [MCP Transport Spec 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) - Streamable HTTP standard (HIGH confidence)
- [Claude Code MCP Docs](https://code.claude.com/docs/en/mcp) - `.mcp.json` with `type: "http"` and `url` (HIGH confidence)
- [Mastra MCP Overview](https://mastra.ai/docs/mcp/overview) - MCPClient with URL transport (HIGH confidence)
- [Cloudflare Streamable HTTP Blog](https://blog.cloudflare.com/streamable-http-mcp-servers-python/) - Python Streamable HTTP patterns (MEDIUM confidence)
