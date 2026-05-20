# MARE-MCP-Toolbox

> Agentic malware analysis on a Kali Linux Docker container with 50+ reverse engineering tools and three disassembler backends (IDA Pro, Binary Ninja, Ghidra), exposed both to in-container agents AND to external MCP clients.

## Two ways to use this

| Mode | Who's running | When to use | Entrypoint |
|------|---------------|-------------|------------|
| **Local** | Claude Code or Codex *inside* the container | Hands-on triage from a single workstation; the agent has full filesystem + tool access | `./run_docker.sh` |
| **Remote** | Claude Code on the host, mastra.ai agents, or any MCP client *outside* the container | Multi-client / fleet workflows; CI; integration into your own agent framework | `./run_docker.sh --remote` |

Both modes can run from the same image. Local agents talk to the disassembler MCP backends directly over stdio/SSE; remote clients talk to the gateway over Streamable HTTP with bearer auth.

## Prerequisites

- Docker + Docker Compose v2
- Optional: `binaryninja.zip` and/or `idapro.zip` in the repo root for paid disassembler backends (auto-detected at build)
- For remote mode: a host port reachable by your MCP client (default `8080`)
- For the mastra.ai starter: Node.js 20+

## Quick start — local mode

The default `./run_docker.sh` invocation builds the image (if needed) and drops you into an interactive Kali shell. Claude Code and Codex are pre-wired to the disassembler backend via `.mcp.json` inside the container.

```bash
./run_docker.sh
# inside the container:
claude   # or: codex
```

Drop sample binaries into the `workspace/` directory; they show up at `/agent/` inside the container.

## Quick start — remote mode

Open Docker Desktop first, or make sure Docker Engine is running. Then
`./run_docker.sh --remote` brings the container up detached, generates a fresh
bearer token, and prints a ready-block with everything you need to connect:

```bash
./run_docker.sh --remote
# ═══════════════════════════════════════════════════════════════════
#   MARE-MCP-Toolbox Gateway is ready
# ═══════════════════════════════════════════════════════════════════
#
#   URL:    http://localhost:8080/mcp
#   Token:  <generated-bearer-token>
#
#   Claude Code .mcp.json snippet:
#     ...
```

Lost the scrollback? Re-print the ready-block:

```bash
./run_docker.sh --print-config
```

By default the gateway publishes on `127.0.0.1:8080`. To expose it on all host interfaces:

```bash
MCP_GATEWAY_HOST_BIND=0.0.0.0 ./run_docker.sh --remote
```

## Connect Claude Code (host)

A pre-built config template ships at [`templates/claude-code/.mcp.json`](templates/claude-code/.mcp.json):

```json
{
  "mcpServers": {
    "mare-toolbox": {
      "type": "http",
      "url": "${MARE_GATEWAY_URL:-http://localhost:8080/mcp}",
      "headers": {
        "Authorization": "Bearer ${MARE_GATEWAY_TOKEN}"
      }
    }
  }
}
```

Drop it into your project root (or merge into `~/.claude/.mcp.json` for user scope), export the token, and Claude Code will pick up the gateway:

```bash
export MARE_GATEWAY_TOKEN=$(cat workspace/.mcp-gateway-token)
# or paste from `./run_docker.sh --print-config`
```

## Connect mastra.ai

A runnable starter project ships at [`templates/mastra/`](templates/mastra/):

```bash
cd templates/mastra
cp .env.example .env
# paste your token into MARE_GATEWAY_TOKEN
npm install
npm start ../../workspace/examples/samples/mfc42ul.dll
```

To use the default Mastra Studio dashboard instead:

```bash
npm run dev
# open http://localhost:4111
```

Studio shows the starter's `mare_status` and `mare_triage_sample_path` tools,
the `MARE Malware Analysis Agent`, and the proxied MARE MCP server surface.

Already have a mastra project? Use the drop-in snippet from [`templates/mastra/README.md`](templates/mastra/README.md):

```typescript
import { MCPClient } from "@mastra/mcp";
const mcp = new MCPClient({
  servers: {
    mare: {
      url: new URL(process.env.MARE_GATEWAY_URL ?? "http://localhost:8080/mcp"),
      requestInit: {
        headers: { Authorization: `Bearer ${process.env.MARE_GATEWAY_TOKEN}` },
      },
    },
  },
});
const toolsets = await mcp.listToolsets();
const tools = toolsets.mare;
```

## Browse case artifacts (MCP Resources)

Connected clients can list and read the 13-artifact pipeline output via the MCP Resources protocol:

```
mare://cases/000-mfc42ul.dll/00_sample_profile.md
mare://cases/000-mfc42ul.dll/05_behavior_hypotheses.md
mare://cases/000-mfc42ul.dll/10_reporting_draft.md
mare://cases/000-mfc42ul.dll/CURRENT_STATE.json
…
```

`resources/list` enumerates all cases under `/agent/status/`; `resources/read` returns the artifact content with the appropriate MIME type (`application/json`, `text/markdown`, `text/plain`).

Uploads are NOT exposed as resources — use `list_uploads()` and `get_sample_info()` tool calls instead.

## Recommended analysis workflow

The author-recommended way to approach malware work in this project is the
[`malware-analysis-orchestrator`](workspace/.claude/skills/malware-analysis-orchestrator/)
skill, mirrored for Codex at
[`workspace/.codex/skills/malware-analysis-orchestrator/`](workspace/.codex/skills/malware-analysis-orchestrator/).
It teaches the phased analysis discipline: create a case directory, preserve raw
strings/imports, rank interesting signals, build evidence-backed hypotheses,
plan deeper reverse engineering, and keep `INDEX.md` / `CURRENT_STATE.json`
fresh.

Local Claude Code or Codex inside the container can discover those skills from
`/agent/.claude/skills/` or `/agent/.codex/skills/`. Remote Claude Code,
mastra.ai, and other MCP clients do not automatically receive local skills over
MCP; they see tool names, schemas, descriptions, and resources. If you want a
remote agent to follow the same discipline, give it this skill or equivalent
prompt guidance in the host project or agent definition.

The initial triage pass is intentionally script-driven. `run_triage` composes
`init_case`, `collect_strings`, `collect_imports`, `scan_yara`, `scan_capa`,
`rank_signals`, `build_hypothesis`, and `update_state`. These gateway-native
tools do not call an LLM; they run fixed Python/Bash helpers and are
deterministic or mostly deterministic for the same sample, case state, tool
versions, and rule sets. The AI-controlled part is deciding what to run next,
how to interpret the artifacts, and which deeper questions to pursue.

After triage, use `get_active_backend()` and the active IDA, Binary Ninja, or
Ghidra MCP tools for deeper analysis: inspect prioritized functions, decompile
or disassemble them, pull xrefs and call graphs, recover types/structures,
annotate findings, and write the resulting component inventory, interaction
model, deep-analysis plan, priority queue, and reporting draft back into the
case artifacts.

## Disassembler backends

The gateway pins one backend for its lifetime (priority: IDA > Binary Ninja >
Ghidra), then merges that backend's native MCP tools into `tools/list`. Clients
call `get_active_backend()` to discover which backend is active. See
[`mcp-gateway/`](mcp-gateway/) for the agent-callable gateway tools,
determinism notes, backend pass-through behavior, and the full IDA Pro MCP
native tool list.

Build with paid backends:

```bash
# Drop binaryninja.zip and/or idapro.zip in the repo root, then:
./run_docker.sh           # local mode, will detect them
./run_docker.sh --remote  # remote mode, ditto
```

Without either, Ghidra is installed by default.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `401 Unauthorized` from Claude Code or mastra | Token rotates per `--remote` start. Refresh: `./run_docker.sh --print-config` and update your env var. |
| `[error] no token file at workspace/.mcp-gateway-token` from `--print-config` | Container isn't running. Start it: `./run_docker.sh --remote`. |
| Port 8080 already in use | `MCP_GATEWAY_HOST_PORT=8081 ./run_docker.sh --remote` |
| Build fails at `[internal] booting buildkit` with `invalid mount config ... docker-desktop-bind-mounts` | Stale Buildx builder state, usually after Docker Desktop/WSL restarts or updates. Recreate it: `docker buildx rm training && docker buildx create --use --name training`, then rerun `./run_docker.sh --remote`. If removal fails, first run `docker rm -f buildx_buildkit_training0`. |
| Mastra `npm install` peer-dep warning on `@mastra/core` | The project pins `@mastra/mcp@~1.3.x`; `@mastra/core` is open to `^1.x`. Warnings are tolerated; if `npm start` fails, downgrade core. |
| Resource list returns no `mare://` URIs | No cases yet. Run a triage first (e.g. via the mastra starter or `tools/call run_triage`). |

## Project layout

```
.
├── Dockerfile                # Kali base + 50+ RE tools + conditional BN/IDA install
├── run_docker.sh             # Mode selector: local / --remote / --print-config
├── compose.yaml              # Local mode compose
├── compose.remote.yaml       # Remote mode overlay (port publishing)
├── mcp-gateway/              # FastMCP gateway (Python; remote mode)
├── templates/                # Pre-built client configs (Phase 4)
│   ├── claude-code/
│   │   └── .mcp.json
│   └── mastra/
│       └── …                 # runnable starter project
└── workspace/                # Mounted at /agent/ inside the container
    ├── examples/             # Bundled malware samples
    └── .mcp-gateway-token    # Auto-written; bearer token for remote mode
```

## Security notes

- The gateway requires a bearer token on every `/mcp` and `/upload` request.
- Default bind is `127.0.0.1:8080` (localhost only). Set `MCP_GATEWAY_HOST_BIND=0.0.0.0` only when you intentionally need LAN access.
- The container runs with elevated capabilities (`SYS_PTRACE`, `seccomp=unconfined`) for analysis tools — do NOT expose it to the public internet without a reverse proxy you trust.
- Disassembler licenses (IDA, Binary Ninja) live ONLY on the host bind mount; never baked into images.

## Dynamic Mode (env-gated)

The container ships seven dynamic-analysis tools that are **registered only when**
`MCP_GATEWAY_DYNAMIC_TOOLS=1` is set at gateway startup. Default-off so the standard
container shape is byte-identical to the static-analysis-only mode.

### Opt-in

```bash
./run_docker.sh --remote --dynamic
```

The `--dynamic` flag REQUIRES `--remote` (dynamic tools are an MCP-only surface;
there is no in-container agent path that calls them directly).

### Tools added when enabled

| Tool | Purpose |
|------|---------|
| `run_strace` | Linux syscall trace via strace, profile-driven argv (file_io, network, process, etc.) |
| `run_ltrace` | Library-call trace via ltrace (ltrace 0.7.3 is unmaintained — prefer strace) |
| `run_qemu_user` | Cross-arch user-mode emulation via qemu-`<arch>`-static |
| `open_gdb_session` | Persistent gdb-MI3 session restricted to an MI-prefix allowlist |
| `gdb_exec` | Execute one MI command in an open gdb session |
| `close_gdb_session` | Close a gdb session (idempotent) |
| `get_dynamic_capabilities` | Report startup capability probe results (ptrace_scope, binfmt, netns, qemu arches) |

### Security posture

- **No-net by default.** Each dynamic-tool subprocess runs under per-call
  `unshare --net --ipc --uts --` — no network, no host IPC, no shared UTS.
- **gdb MI allowlist.** `gdb_exec` accepts only allowlisted MI prefixes
  (`-info-`, `-data-evaluate-expression`, `-stack-list-frames`, `-exec-run`,
  `-break-insert`, etc.). `python`, `-interpreter-exec console`, `source`,
  `!`, and other escapes are hard-blocked.
- **Follow-fork reaping.** Setsid grandchildren that escape the runner's process
  group are killed via `/proc/<pid>/task/*/children` recursive scan after each
  job terminates.
- **Argv-only.** All trace tools spawn via `asyncio.create_subprocess_exec`
  with `start_new_session=True`. `extra_args` are validated against an
  allowlist regex; `-o`, `-D`, `--detach`, `-p`, `--attach`, `-b`,
  `--detach-on` flags are denied.
- **Sample resolution.** All trace tools accept `sample_sha256` (hex string)
  only; the sha256 is resolved to an absolute path under `uploads/` or the
  active `case_dir/`. Path traversal is impossible at the MCP boundary.
- **Host prerequisites.**
  - `kernel.yama.ptrace_scope <= 1` on the host (run `sudo sysctl -w
    kernel.yama.ptrace_scope=0` if needed).
  - Docker container uses `--cap-add=SYS_PTRACE` and
    `--security-opt seccomp=unconfined` (pinned in `compose.yaml`).
  - For foreign-arch samples via binfmt, register host-side with `F` flag:
    `docker run --rm --privileged multiarch/qemu-user-static --reset -p yes`.

### Readiness check

Inside the container, run:

```bash
./scripts/probe_dynamic_tools.sh
```

Or query the running gateway via MCP:

```python
await mcp.call_tool("get_dynamic_capabilities")
```

### Limitations (v1.1)

- Sessions are shared across all MCP clients with the same bearer token
  (per-`Mcp-Session-Id` keying is v1.2 territory).
- No `allow_network=True` opt-in; sandboxed-network mode (INetSim/FakeDNS)
  is deferred to v1.2.
- qemu-user multi-threaded sample emulation is unreliable (known qemu issue).
- ltrace 0.7.3 is unmaintained; the orchestrator should prefer strace for
  modern binaries.

## License & licensing constraints

This project is MIT-licensed. IDA Pro and Binary Ninja licenses are user-provided and never included in image layers — see the `Dockerfile` multi-stage build for the seeding pattern.

## Further reading

- [`mcp-gateway/`](mcp-gateway/) — gateway internals, tool surface, /upload contract
- [`templates/mastra/README.md`](templates/mastra/README.md) — full mastra starter walkthrough
- [`workspace/.claude/skills/malware-analysis-orchestrator/`](workspace/.claude/skills/malware-analysis-orchestrator/) and [`workspace/.codex/skills/malware-analysis-orchestrator/`](workspace/.codex/skills/malware-analysis-orchestrator/) — the 13-artifact pipeline for Claude and Codex
- [`.planning/`](.planning/) — design docs, phase plans, requirements
