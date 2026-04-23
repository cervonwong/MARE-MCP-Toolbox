# Phase 2: MCP Gateway - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-23
**Phase:** 02-mcp-gateway
**Areas discussed:** Tool surface strategy, Gateway ↔ backend architecture, File upload mechanism, Auth token lifecycle

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Tool surface strategy | GW-02: The 15-25 tools — composite vs atomic vs layered | ✓ |
| Gateway ↔ backend architecture | GW-03: Proxy to existing MCP servers vs own logic vs hybrid | ✓ |
| File upload mechanism | GW-06: MCP base64 vs HTTP endpoint vs bind mount | ✓ |
| Auth token lifecycle | GW-04: Token source, exposure, scope, binding | ✓ |

**User's choice:** All four areas selected for deep discussion.

---

## Tool surface strategy

### Q1: Overall tool surface style

| Option | Description | Selected |
|--------|-------------|----------|
| Layered mix | Both high-level workflow tools AND atomic pipeline tools | ✓ |
| Atomic only | Only granular pipeline-step tools | |
| Composite only | Only high-level workflow tools | |

**User's choice:** Layered mix (Recommended)

### Q2: Atomic-tier granularity (re-asked after user asked for clarification)

| Option | Description | Selected |
|--------|-------------|----------|
| One tool per artifact file | e.g., collect_strings_raw → 01_strings_raw.txt, etc. ~13 atomic tools | ✓ |
| One tool per script | Mirrors scripts/ dir exactly (fewer tools, bundles steps) | |
| Grouped by analysis stage | 3-4 atomic tools: collect, analyze, report | |

**User's choice:** One tool per artifact file (Recommended)
**Notes:** First iteration of the question was unclear to the user ("i don't get this question"); re-asked with concrete examples tied to the 13-artifact pipeline file names.

### Q3: Tool naming convention

| Option | Description | Selected |
|--------|-------------|----------|
| Dotted namespace | e.g., triage.run, strings.collect, disasm.decompile_function | |
| Underscored flat | e.g., triage_run, collect_strings, scan_yara | |
| Verb-first | e.g., run_triage, decompile, list_functions, fetch_strings | ✓ |

**User's choice:** Verb-first (diverged from recommendation; recommendation was Dotted namespace)

### Q4: Expose case/session state as tools

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, as tools | case.list, case.get_artifact, case.set_active | ✓ |
| No, leave implicit | Stateless, client manages case dirs | |
| You decide | Claude picks | |

**User's choice:** Yes, as tools (Recommended)

---

## Gateway ↔ backend architecture

### Q1: Disassembler tool routing

| Option | Description | Selected |
|--------|-------------|----------|
| MCP client to backend | Gateway is MCP CLIENT to idalib-mcp / BN stdio / Ghidra stdio; aggregates + renames tools | ✓ |
| Direct Python API | Gateway imports idalib / BN API / pyghidra in-process | |
| Subprocess + JSON | Gateway shells out to short-lived scripts | |

**User's choice:** MCP client to backend (Recommended)

### Q2: Non-disassembler pipeline implementation

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse scripts/ | Gateway shells out to orchestrator skill's scripts/ — single source | ✓ |
| Port to Python calls | Rewrite scripts into Python functions | |
| Hybrid | Reuse scripts for I/O; port interpretation to Python | |

**User's choice:** Reuse scripts/ (Recommended)

### Q3: BN/Ghidra stdio MCP lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| Persistent subprocess at gateway start | Long-lived piped stdio subprocess | ✓ |
| Per-request subprocess | Spawn fresh per tool call | |
| Share with local agent | Multiplex an existing inner-agent MCP server | |

**User's choice:** Persistent subprocess at gateway start (Recommended)

### Q4: Gateway startup & backend detection

| Option | Description | Selected |
|--------|-------------|----------|
| Entrypoint + detect at boot | Started by agent-entrypoint.sh; reuses configure-agent-mcp.sh detection logic; backend pinned | ✓ |
| On-demand (first request) | Lazy-start when port 8080 receives traffic | |
| Systemd-style supervisor | supervisord-like manager | |

**User's choice:** Entrypoint + detect at boot (Recommended)

---

## File upload mechanism

### Q1: Upload transport

| Option | Description | Selected |
|--------|-------------|----------|
| MCP tool, base64 chunks | upload_sample(chunk, offset, total_size) over MCP messages | |
| Separate HTTP upload endpoint | POST /upload on same port, returns sample_id | ✓ |
| Presigned path + shared mount | Bind-mount writable /samples; client drops file out-of-band | |

**User's choice:** Separate HTTP upload endpoint (diverged from recommendation; recommendation was MCP base64 chunks)

### Q2: Sample storage

| Option | Description | Selected |
|--------|-------------|----------|
| /agent/uploads/<sha256>/<name> | Content-hashed dir under workspace volume; dedupes | ✓ |
| Ephemeral /tmp | /tmp/gateway-samples/, wiped on reboot | |
| Bind-mounted host dir | Mount host dir as /agent/uploads | |

**User's choice:** /agent/uploads/<sha256>/<name> (Recommended)

### Q3: Size limit

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable, default 100 MB | Env var MCP_GATEWAY_MAX_UPLOAD_MB=100 default | |
| No limit | Unlimited upload size | |
| You decide | Claude picks | |

**User's choice:** "default 1GB" (free text) — user picked configurable cap but raised the default from 100 MB to 1 GB.

### Q4: Sample resolution in tools

| Option | Description | Selected |
|--------|-------------|----------|
| Both | Tools accept either uploaded sample_id (sha) OR local container path | ✓ |
| Upload only for remote | Remote clients must always upload | |
| Local paths only | Upload tool just writes to /agent/uploads and returns the path | |

**User's choice:** Both (Recommended)

---

## Auth token lifecycle

### Q1: Token source

| Option | Description | Selected |
|--------|-------------|----------|
| Either (env var wins, else auto-gen) | Use MCP_GATEWAY_TOKEN if set, otherwise generate random | ✓ |
| Always auto-generated | Fresh token every container start, ignore env | |
| User-supplied only | Refuse to start without env var | |

**User's choice:** Either (env var wins, else auto-gen) (Recommended)

### Q2: Token exposure

| Option | Description | Selected |
|--------|-------------|----------|
| File + log line | Write to /agent/.mcp-gateway-token AND log one-line message (MCP_GATEWAY_QUIET=1 suppresses log) | ✓ |
| Log only | stdout only, no host file | |
| File only | No log message | |

**User's choice:** File + log line (Recommended)

### Q3: Token scope

| Option | Description | Selected |
|--------|-------------|----------|
| Single token | One token for all tools + upload endpoint | ✓ |
| Per-tool scopes | Token claims restrict callable tools | |
| You decide | Claude picks | |

**User's choice:** Single token (Recommended)

### Q4: Network binding default

| Option | Description | Selected |
|--------|-------------|----------|
| Env var toggle | MCP_GATEWAY_HOST=0.0.0.0 opts into exposure; default 127.0.0.1 | ✓ |
| Compose port mapping only | Always bind 0.0.0.0; rely on compose port publish for exposure | |
| Two-flag (host + port) | Separate MCP_GATEWAY_HOST and MCP_GATEWAY_PORT | |

**User's choice:** Env var toggle (Recommended)

---

## Final check

| Option | Description | Selected |
|--------|-------------|----------|
| Ready for context | Write CONTEXT.md with decisions captured so far | ✓ |
| Explore more gray areas | Continue discussion on concurrency/errors/port details | |

**User's choice:** Ready for context

## Claude's Discretion

- Concurrency / session-isolation model for simultaneous remote clients (deferred to v2 per GW-V2-03)
- Error serialization format (MCP error codes, payload shape) — follow MCP spec defaults
- Logging level/format — compose-log-friendly
- FastMCP composition details (tool registration, middleware order, auth placement)
- Backend subprocess restart policy
- Inter-process transport detail between gateway and BN/Ghidra stdio MCP servers
- Exact argument names for each of the ~20 tools

## Deferred Ideas

All deferred ideas from this discussion are listed in CONTEXT.md's `<deferred>` section. Key items: MCP Resources (Phase 4), MCP Prompts / dynamic notifications / multi-session (v2), unified disassembler abstraction & comparison mode (v2), Claude Code / mastra.ai client templates (Phase 4), compose.yaml port publishing (Phase 3), dual-mode entrypoint tuning (Phase 3).
