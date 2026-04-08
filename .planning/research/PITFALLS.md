# Pitfalls Research

**Domain:** Agentic malware analysis toolbox with IDA Pro integration and remote MCP server capability
**Researched:** 2026-04-08
**Confidence:** MEDIUM-HIGH (verified with official docs, project repos, and MCP specification)

## Critical Pitfalls

### Pitfall 1: IDA Pro License Baked Into Docker Image or Layer Cache

**What goes wrong:**
The IDA Pro license file (`.hexlic`) or HCLI API key gets embedded in a Docker image layer. Even if deleted in a later layer, it remains recoverable via `docker history` or layer extraction. This violates Hex-Rays licensing terms and creates a security incident if the image is ever pushed to a registry.

**Why it happens:**
Developers copy the license file with `COPY` or pass `HCLI_API_KEY` as a build arg without using multi-stage builds. Docker build args are visible in image metadata. The existing Binary Ninja pattern in this project uses `--mount=type=bind,from=binja-stage` which is correct, but IDA's HCLI-based install flow is different -- HCLI downloads and installs IDA using an API key, which means the key is used during build, not just a zip file.

**How to avoid:**
- Use multi-stage Docker builds. The official HCLI Dockerfile (github.com/HexRaysSA/ida-hcli) demonstrates this: install IDA in a builder stage, then copy only the installation directory to the final image. The API key never touches the final image.
- Pass `HCLI_API_KEY` as a `--build-arg` and ensure the stage that uses it is NOT the final stage.
- Use `--mount=type=secret` for the API key if single-stage is unavoidable.
- Never use `ENV HCLI_API_KEY` -- that persists in image metadata.
- The `.hexlic` license files end up in `~/.idapro/` -- ensure this directory is either volume-mounted at runtime or carefully handled in multi-stage copy.

**Warning signs:**
- `docker history` shows layers containing license-related files or API key args
- Image size unexpectedly large (full IDA installer left in cache)
- `HCLI_API_KEY` visible in `docker inspect`

**Phase to address:**
IDA Pro integration phase. Must be designed into the Dockerfile from the start -- retrofitting multi-stage builds after the fact means rebuilding the entire image pipeline.

---

### Pitfall 2: IDA Pro Requires x86_64 -- No ARM64 Support in idalib/HCLI

**What goes wrong:**
The Docker image fails to build on ARM64 hosts (Apple Silicon Macs, ARM CI runners). IDA Pro's idalib and HCLI do not support Linux ARM64. The official HCLI Dockerfile explicitly sets `--platform=linux/amd64`.

**Why it happens:**
The existing project Dockerfile does not pin a platform -- it builds for the host architecture. Binary Ninja and Ghidra both support ARM64 on Linux, so this hasn't been an issue. But IDA Pro's native libraries are x86_64-only on Linux.

**How to avoid:**
- When `INSTALL_IDA=1`, force `--platform=linux/amd64` for the IDA installation stage or the entire build.
- Document that IDA Pro variant requires x86_64 Docker (or emulation via Rosetta/QEMU).
- Consider a conditional platform pin: only force amd64 when IDA is being installed, allowing the base image to remain multi-arch for Binary Ninja/Ghidra-only builds.
- Test on ARM64 hosts early to confirm Rosetta/QEMU emulation performance is acceptable.

**Warning signs:**
- Build failures on Apple Silicon or ARM-based CI
- `exec format error` when running IDA binaries in container
- HCLI download returning "unsupported platform" errors

**Phase to address:**
IDA Pro integration phase, specifically the Dockerfile modifications.

---

### Pitfall 3: Exposing Remote MCP Server Without Authentication on a Privileged Container

**What goes wrong:**
The container runs with `SYS_PTRACE` and `seccomp=unconfined` (required for RE tooling like strace/gdb). Exposing an unauthenticated MCP server on this container gives any network-reachable attacker full access to shell execution, filesystem operations, and malware samples. Bitsight research found approximately 1,000 exposed MCP servers with zero authorization in the wild.

**Why it happens:**
The MCP specification states authorization is "OPTIONAL." Developers focus on getting the transport working first and defer authentication. The stdio-to-HTTP bridge tools (like mcp-proxy or custom wrappers) often don't include auth middleware by default. The existing compose.yaml does not expose any ports, so this isn't a current issue -- but adding remote MCP transport requires port exposure.

**How to avoid:**
- Implement authentication from day one. Bearer token auth is the simplest approach: generate a random token, require it in the `Authorization` header, validate in the MCP server middleware.
- Bind to `127.0.0.1` by default, not `0.0.0.0`. Require explicit configuration to bind to all interfaces.
- Place a reverse proxy (Traefik, nginx) in front of the MCP endpoint for TLS termination and auth.
- Consider the "curated tool surface" requirement from PROJECT.md -- expose only orchestrator-level operations, never raw `exec` or shell tools.
- Use Docker network isolation: put the MCP server on a dedicated Docker network, not the host network.

**Warning signs:**
- Port binding to `0.0.0.0` in compose.yaml without corresponding auth configuration
- MCP tool list includes shell/exec/filesystem tools without access controls
- No TLS configured (credentials sent in cleartext)

**Phase to address:**
Remote MCP server phase. Authentication architecture must be designed before the first port is exposed.

---

### Pitfall 4: IDA Pro's idalib Threading Model Causes Silent Database Corruption

**What goes wrong:**
idalib (which ida-mcp 2.0 uses) cannot safely handle concurrent access to the same IDA database from multiple threads or processes. If two MCP tool calls arrive simultaneously and touch the same database, the `.idb`/`.i64` file can become corrupted silently. Unlike a crash, corruption may not be detected until a later analysis step produces wrong results.

**Why it happens:**
MCP servers handle requests concurrently by default. The ida-mcp project addresses this with a supervisor/worker architecture (one subprocess per database), but custom wrappers or simpler integrations may not. The existing Binary Ninja MCP server in this project likely has similar constraints but Binary Ninja's headless API is thread-safe for read operations.

**How to avoid:**
- Use ida-mcp (jtsylve/ida-mcp) which already implements per-database process isolation with a supervisor pattern.
- If building a custom wrapper, enforce single-writer access per database file. Use file locks or a request queue.
- Set `IDA_MCP_IDLE_TIMEOUT` appropriately (default 30 min) to avoid zombie worker processes consuming memory.
- Never share `.idb`/`.i64` files between concurrent analysis sessions.

**Warning signs:**
- Multiple IDA processes touching the same `.idb` file
- Decompilation results that differ between runs on the same binary
- Worker process count growing unboundedly

**Phase to address:**
IDA Pro integration phase. The choice between ida-mcp (which handles this) vs. a custom wrapper determines whether this is a design concern or an implementation detail.

---

### Pitfall 5: Python Environment Conflicts Between Three Disassembler APIs

**What goes wrong:**
Binary Ninja, Ghidra (via pyghidra), and IDA Pro (via idalib/IDAPython) all install Python packages into the same `site-packages`. IDA Pro 9.x requires a specific Python version (currently 3.12 or 3.13, depending on build). Binary Ninja's `install_api.py` installs a `.pth` file. pyghidra has its own Java bridge dependencies. These can conflict: version pinning collisions, namespace pollution, or one tool's `install_api.py` overwriting another's path modifications.

**Why it happens:**
The current Dockerfile installs everything system-wide with `--break-system-packages`. This works fine with two tools but three independent API installations into the same Python increases collision probability. IDA's idalib is particularly sensitive -- it links against a specific Python shared library and fails if the wrong version is loaded.

**How to avoid:**
- Use isolated Python virtual environments per disassembler backend. Each MCP server process should activate its own venv.
- Alternatively, since each backend runs as a separate MCP server process, ensure each process sets `PYTHONPATH` to include only its own dependencies.
- Pin the system Python version to match IDA's requirement (currently Python 3.12 or 3.13 for IDA 9.x). Verify compatibility with Binary Ninja and pyghidra before upgrading.
- The official HCLI Dockerfile uses `python:3.13-slim` as its base -- confirm this matches the Kali rolling Python version.

**Warning signs:**
- `import binaryninja` fails after IDA installation (or vice versa)
- `import idaapi` raises version mismatch errors
- Different tools work in isolation but fail when installed together
- `python3 --version` doesn't match IDA's compiled Python version

**Phase to address:**
IDA Pro integration phase. Test the three-way coexistence before moving to the remote MCP server phase.

---

### Pitfall 6: Using Deprecated SSE Transport Instead of Streamable HTTP

**What goes wrong:**
The MCP specification (2025-03-26 revision) deprecated the HTTP+SSE transport in favor of Streamable HTTP. Building on SSE means: authentication tokens in URL query strings (security risk), persistent connections that bypass auth re-validation, no standard CORS handling, and eventual client incompatibility as SSE support is removed.

**Why it happens:**
Many existing MCP server examples and tutorials still use SSE (it was the standard until mid-2025). Libraries like the Python MCP SDK may default to SSE transport. Developers copy-paste SSE examples without checking the current spec.

**How to avoid:**
- Use Streamable HTTP transport exclusively for the remote MCP endpoint.
- Claude Code supports `--transport http` for remote servers. Mastra's MCPClient supports `url` parameter for remote HTTP endpoints.
- Implement the MCP endpoint as a single HTTP path accepting POST and GET, per the spec.
- Validate the `Origin` header on all incoming requests (DNS rebinding prevention, per spec MUST requirement).
- Include `Mcp-Session-Id` for stateful session management.

**Warning signs:**
- Server code imports SSE-specific libraries or sets up `/sse` endpoint
- Client configuration uses `type: "sse"` instead of `type: "http"`
- Authentication passed via URL query parameters

**Phase to address:**
Remote MCP server phase. Transport selection is the first architectural decision.

---

### Pitfall 7: MCP Tool Surface Exposes Raw Container Capabilities

**What goes wrong:**
The remote MCP server exposes tools that directly wrap container CLI commands (e.g., `run_command`, `read_file`, `write_file`). Since the container has SYS_PTRACE, seccomp=unconfined, and 50+ RE tools, this effectively gives remote clients unrestricted shell access to a malware analysis environment. A prompt injection in any connected AI agent could exfiltrate malware samples or pivot to other systems.

**Why it happens:**
The fastest path to "it works" is wrapping every container tool as an MCP tool. The PROJECT.md explicitly warns against this ("Curated MCP tool surface -- expose orchestrator-level operations, not raw CLI wrappers"), but it's tempting to skip curation during development.

**How to avoid:**
- Define the MCP tool surface as orchestrator-level operations: `triage_binary`, `get_strings`, `run_yara`, `decompile_function`, `get_capa_results` -- not `exec`, `read_file`, or `shell`.
- Implement tools as purpose-built functions that call the underlying tools internally, with input validation and output sanitization.
- Use an allowlist pattern: only explicitly registered tools are exposed, never auto-discovered CLI wrappers.
- Rate-limit expensive operations (decompilation, full analysis).

**Warning signs:**
- MCP tool list includes generic `execute_command` or `shell` tools
- Tools accept arbitrary file paths without validation
- No distinction between internal (agent-inside-container) and external (remote client) tool surfaces

**Phase to address:**
Remote MCP server phase. The tool surface design must be completed before exposing the server.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| System-wide pip install for all three disassembler APIs | Simple Dockerfile, fast builds | Version conflicts as any tool upgrades Python requirements | Never once IDA is added -- use venvs or isolated processes |
| Single MCP server process for all backends | Less infrastructure to manage | One backend crash kills all tools; can't scale backends independently | Early prototyping only, never in remote-exposed mode |
| Hardcoded bearer token for MCP auth | Quick to implement | Token rotation requires container rebuild; no per-client access control | MVP/local development only |
| Skipping TLS (plain HTTP) for MCP transport | No cert management complexity | Credentials sent in cleartext; man-in-the-middle on any non-localhost network | Only when bound to 127.0.0.1 (localhost-only access) |
| Mounting IDA license directory as Docker volume | Simple license management | License file accessible to any process in container; volume persists across rebuilds | Acceptable -- this is the recommended pattern (same as Binary Ninja) |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| IDA Pro via HCLI in Docker | Using `HCLI_API_KEY` as `ENV` or single-stage build arg | Multi-stage build: install in builder stage, copy `/opt/ida` to final stage. API key never in final image. |
| ida-mcp (jtsylve/ida-mcp) | Assuming it uses idat/idat64 headless | ida-mcp 2.0 uses idalib, not idat. Requires IDA 9+ with idalib support. Different binary, different setup. |
| Claude Code remote MCP | Setting `type: "sse"` in `.mcp.json` | Use `type: "http"` with `url` pointing to the MCP endpoint. SSE is deprecated. Example: `{"type": "http", "url": "http://localhost:3000/mcp", "headers": {"Authorization": "Bearer $TOKEN"}}` |
| Claude Code MCP auth headers | Hardcoding secrets in `.mcp.json` | Use environment variable expansion: `"Authorization": "Bearer ${MCP_TOKEN}"`. Claude Code supports `${VAR}` and `${VAR:-default}` syntax. |
| Mastra.ai MCPClient | Using `command` transport for container tools | Use `url` transport for remote container. Mastra's MCPClient supports `url` parameter for HTTP endpoints. |
| Mastra.ai tool names | Ignoring tool name collisions between backends | Namespace MCP tools by backend: `binja_decompile`, `ida_decompile`, `ghidra_decompile`. Mastra silently skips collisions. |
| Dual-mode operation (local stdio + remote HTTP) | Running two separate MCP server processes with duplicated tool logic | Single tool implementation, two transport adapters. The MCP SDK supports multiple transports on the same server. |
| Docker port exposure | Binding MCP port to `0.0.0.0` in compose.yaml | Bind to `127.0.0.1:PORT:PORT` unless explicit remote access is configured with auth + TLS. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| IDA idalib spawning one subprocess per binary | Memory exhaustion, OOM kills | Set `IDA_MCP_IDLE_TIMEOUT` to auto-cleanup idle workers (default 30 min). Monitor worker count. | >5-10 concurrent binaries on 8GB RAM container |
| Full decompilation of large binaries via MCP | Requests timing out, client disconnects | Implement per-function decompilation, not whole-binary. Use MCP streaming (SSE within Streamable HTTP) for long operations. | Binaries >10MB with 1000+ functions |
| Three disassembler backends loaded simultaneously | Container memory exceeds Docker limits | Make backends lazy-load: only start the requested backend's MCP process on first use. | Always, if all three are started eagerly |
| Ghidra headless analysis startup time | First MCP call takes 30-60 seconds (JVM startup + analysis) | Pre-analyze on binary upload, cache `.gpr` project files. Or document the cold-start delay. | Every first call per binary |
| Streaming large decompilation output over HTTP | Client buffers entire response before processing | Use SSE streaming within Streamable HTTP POST responses. Send per-function results as SSE events. | Functions with >10K lines of decompiled output |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| No Origin header validation on MCP endpoint | DNS rebinding attack: malicious website triggers MCP calls to localhost container | Validate Origin header on all requests (MCP spec MUST requirement). Reject requests with unexpected origins. |
| Exposing malware samples via MCP file tools | Attacker exfiltrates samples, reuses them | MCP tools should never return raw binary content. Return analysis results (strings, hashes, decompiled code) not file bytes. |
| MCP server on same network as malware execution | Lateral movement from analyzed malware to MCP clients | Static analysis only (per PROJECT.md scope). Never execute analyzed binaries. Network-isolate the container. |
| Using the same auth token for all clients | Compromise of one client exposes entire system | Generate per-client tokens. Log which client made which request. Support token revocation. |
| `IDA_MCP_ALLOW_SCRIPTS=1` on remote-facing server | Arbitrary IDAPython code execution by any authenticated client | Never enable `IDA_MCP_ALLOW_SCRIPTS` for remote-facing MCP. Only enable for local agent-inside-container mode. |

## "Looks Done But Isn't" Checklist

- [ ] **IDA Pro install:** License works in container -- verify by running `idalib` analysis on a test binary, not just checking file existence
- [ ] **Remote MCP server:** Auth works end-to-end -- test with `curl` that unauthenticated requests are rejected with 401/403, not just that authenticated ones succeed
- [ ] **Claude Code integration:** `.mcp.json` with `type: "http"` actually connects -- test with `claude mcp list` showing the remote server's tools, not just that the config file parses
- [ ] **Mastra.ai integration:** Tools are callable, not just listed -- invoke a decompilation tool from a Mastra agent and verify the result, as tool listing can succeed even when execution fails
- [ ] **Dual-mode operation:** Both modes work simultaneously -- start an agent inside the container AND connect Claude Code from outside, run tools on both, verify no deadlocks or resource contention
- [ ] **Three backends coexistence:** All three Python APIs import without error in their respective processes -- run `python3 -c "import binaryninja"`, `python3 -c "import idaapi"`, and `python3 -c "import pyghidra"` from within the container
- [ ] **Session management:** MCP sessions survive client reconnection -- disconnect and reconnect Claude Code, verify in-progress analysis state is preserved
- [ ] **Container memory:** All three backends can run simultaneously within Docker memory limits -- load a binary in each and monitor `docker stats`

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| License leaked in Docker image | HIGH | Revoke license immediately via Hex-Rays portal. Rebuild all images with multi-stage build. Rotate HCLI API key. Audit registry for leaked images. |
| Python environment corrupted | MEDIUM | Rebuild Docker image. Switch to venv-per-backend architecture. Test imports for each backend. |
| MCP server compromised (no auth) | HIGH | Take container offline. Audit all accessed files. Rotate all API keys. Implement auth before bringing back online. Review malware sample inventory. |
| IDA database corruption | LOW | Delete corrupted `.idb`/`.i64` files. Re-analyze from original binary. Ensure single-writer access going forward. |
| SSE transport already implemented | MEDIUM | Refactor to Streamable HTTP. Update client configs. Most MCP SDK versions support both -- change transport adapter, keep tool logic. |
| Wrong Python version for idalib | MEDIUM | Pin system Python to match IDA's requirement. May require changing Kali base image version or installing Python from source. Test all three backends after change. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| License in Docker image | IDA Pro integration | `docker history` shows no license artifacts in any layer of final image |
| x86_64-only IDA Pro | IDA Pro integration | Build succeeds with `--platform=linux/amd64`; document ARM64 limitation |
| Unauthenticated MCP server | Remote MCP server | `curl` without auth header returns 401; with token returns 200 |
| idalib threading/corruption | IDA Pro integration | Concurrent MCP calls produce consistent results; no `.idb` corruption |
| Python environment conflicts | IDA Pro integration | All three `import` statements succeed in their respective processes |
| Deprecated SSE transport | Remote MCP server | Server responds to POST on MCP endpoint; no `/sse` endpoint exists |
| Raw tool surface exposure | Remote MCP server | `mcp list-tools` shows only curated orchestrator tools, no shell/exec |
| DNS rebinding | Remote MCP server | Request with forged Origin header is rejected |
| Memory exhaustion (3 backends) | Remote MCP server | `docker stats` under load shows memory within configured limits |

## Sources

- [ida-mcp 2.0 announcement (jtsylve, 2026-03-25)](https://jtsylve.blog/post/2026/03/25/Announcing-ida-mcp-2)
- [ida-mcp-rs (blacktop)](https://github.com/blacktop/ida-mcp-rs)
- [HCLI official Dockerfile](https://github.com/HexRaysSA/ida-hcli/blob/main/docs/advanced/docker/Dockerfile)
- [HCLI documentation - Installing IDA](https://hcli.docs.hex-rays.com/user-guide/installing-ida/)
- [MCP Specification - Transports (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [Bitsight - Exposed MCP Servers](https://www.bitsight.com/blog/exposed-mcp-servers-reveal-new-ai-vulnerabilities)
- [Auth0 - Why MCP deprecated SSE](https://auth0.com/blog/mcp-streamable-http/)
- [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp)
- [Mastra MCP overview](https://mastra.ai/docs/mcp/overview)
- [blacktop/docker-idapro](https://github.com/blacktop/docker-idapro)
- [docker-ida (intezer)](https://github.com/intezer/docker-ida)
- [IDA and common Python issues (Hex-Rays)](https://hex-rays.com/blog/ida-and-common-python-issues)
- [Hex-Rays idalib documentation](https://docs.hex-rays.com/user-guide/idalib)

---
*Pitfalls research for: MARE-MCP-Toolbox v2 -- IDA Pro + Remote MCP Server*
*Researched: 2026-04-08*
