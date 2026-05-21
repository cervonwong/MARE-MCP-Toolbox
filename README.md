# MARE-MCP-Toolbox

> Agentic malware analysis on a Kali Linux Docker container with 50+ reverse engineering tools and three disassembler backends (IDA Pro, Binary Ninja, Ghidra), exposed both to in-container agents AND to external MCP clients.

The gateway ships **54 curated MCP tools** by default (61 with dynamic mode enabled, +1 with the env-gated unsafe r2 tool) on top of the active disassembler's native MCP surface, over Streamable HTTP with bearer auth.

## Two ways to use this

| Mode | Who's running | When to use | Entrypoint |
|------|---------------|-------------|------------|
| **Local** | Claude Code or Codex *inside* the container | Hands-on triage from a single workstation; the agent has full filesystem + tool access | `./run_docker.sh` |
| **Remote** | Claude Code on the host, mastra.ai agents, or any MCP client *outside* the container | Multi-client / fleet workflows; CI; integration into your own agent framework | `./run_docker.sh --remote` |

Both modes can run from the same image. Local agents talk to the disassembler MCP backends directly over stdio/SSE; remote clients talk to the gateway over Streamable HTTP with bearer auth. Dynamic-analysis tools (strace, ltrace, qemu-user, gdb sessions) are an MCP-only surface enabled via `./run_docker.sh --remote --dynamic`.

## Prerequisites

- Docker + Docker Compose v2
- Optional: `binaryninja.zip` and/or `idapro.zip` in the repo root for paid disassembler backends (auto-detected at build)
- For remote mode: a host port reachable by your MCP client (default `8080`)
- For the mastra.ai starter: Node.js 20+
- For dynamic mode: host `kernel.yama.ptrace_scope <= 1`; for foreign-arch samples, host-side binfmt registration via `docker run --rm --privileged multiarch/qemu-user-static --reset -p yes`

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

Add `--dynamic` to enable the env-gated dynamic-analysis surface:

```bash
./run_docker.sh --remote --dynamic
```

Lost the scrollback? Re-print the ready-block:

```bash
./run_docker.sh --print-config
```

By default the gateway publishes on `127.0.0.1:8080`. To expose it on all host interfaces:

```bash
MCP_GATEWAY_HOST_BIND=0.0.0.0 ./run_docker.sh --remote
```

## What's in the toolbox

The gateway exposes a curated MCP tool surface in five families plus a transparent disassembler pass-through. Tools are argv-only spawned through a single chokepoint (`ReToolRunner`), cwd-confined to the active `case_dir`, hard-timeouted, output-capped, and auto-captured to `case_dir/tool-logs/<UTC>-<slug>-<rand4>.txt`. Full per-call output is preserved on disk; only a head-truncated preview returns over MCP.

| Family | Count | What's in it |
|--------|------:|--------------|
| **Triage pipeline** (v1.0) | 22 | 13-artifact case pipeline: `run_triage`, `init_case`, `collect_strings`, `collect_imports`, `scan_yara`, `scan_capa`, `rank_signals`, `build_hypothesis`, `update_state`, `resolve_case`, `get_artifact`, `run_deep_analysis`, `generate_report`, `list_cases`, `set_active_case`, `get_active_case`, `list_uploads`, `get_sample_info`, `get_active_backend`, and three disassembler-compat wrappers (`decompile`, `list_functions`, `get_xrefs`) |
| **Constrained shell** (v1.1) | 1 | `run_shell` — bash one-liner inside `case_dir`, runs as a dedicated non-root `mare-shell` UID via `setpriv --reuid --regid --clear-groups --no-new-privs --inh-caps=-all`, env stripped of `MCP_GATEWAY_TOKEN`/API keys/AWS creds, output capped, auto-captured. Confinement is **posture** (cwd + UID + timeout + capture), not OS-level isolation. |
| **Typed static wrappers** (v1.1) | 11 | `run_file`, `run_die`, `run_xxd`, `run_readelf`, `run_objdump`, `run_nm`, `run_rabin2`, `run_capstone_disasm` (typed JSON), `run_ropper` (typed JSON), `run_jq`, `run_yq`. Wrappers exist where parsing/validation pays off; the long tail is `run_shell`. |
| **Artifact helpers** (v1.1) | 5 | `write_artifact`, `append_artifact`, `list_artifacts`, `get_artifact_tree`, `get_tool_log` — read/write the case-dir tree and range-read tool logs without blowing the MCP response cap. |
| **Session-scoped r2** (v1.1) | 4 | `open_r2_session`, `r2_cmd`, `close_r2_session`, `list_sessions` — persistent radare2 analysis state (no re-analysis per call); spawned with `cfg.sandbox=true` at argv-eval time (r2's native one-way latch); dangerous shell-escape regex denylist as defense-in-depth; idle reaper (default 30 min); session cap (default 8 across r2+gdb). |
| **Background jobs** (v1.1) | 4 | `start_tool_job`, `get_tool_job`, `cancel_tool_job`, `list_tool_jobs` — for tools that exceed the 60 s MCP request cap (capa, unblob, binwalk extract, strace, ltrace, qemu_user). Same argv-only / process-group / capture safety as `run_shell`. Cap on in-flight (default 4) and on log size (default 256 MB). |
| **Extraction tier** (v1.1) | 7 | `run_binwalk` (signatures / entropy / extract), `run_unblob`, `run_upx_test`, `run_upx_list`, `run_upx_unpack`, `list_extracted_files`, `promote_extracted_sample` — recursive triage of carved children. Symlink quarantine (`.symlink-target.txt`), archive-bomb cap (default 4 GB), atomic re-upload via sha256 on promote. |
| **Dynamic Lab** (v1.1, env-gated) | 7 | `run_strace`, `run_ltrace`, `run_qemu_user`, `open_gdb_session`, `gdb_exec`, `close_gdb_session`, `get_dynamic_capabilities` — registered iff `MCP_GATEWAY_DYNAMIC_TOOLS=1`. Per-call `unshare --net --ipc --uts`, allowlisted argv profiles, follow-fork reaper, gdb-MI3 prefix allowlist + 15-vector deny regex. |
| **Unsafe r2** (env-gated) | 1 | `open_r2_session_unsafe` — registered iff `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1`. Spawns r2 WITHOUT `cfg.sandbox=true`; WARN-logged on every open; shares the combined session cap. |
| **Backend pass-through** | varies | The pinned disassembler's native MCP tools are merged into `tools/list` under their original names (IDA Pro's ~80 tools when active; BN/Ghidra's surfaces otherwise). Clients call `get_active_backend()` to discover which is active. |

Authenticated HTTP upload (not an MCP tool):

| Endpoint | Purpose |
|----------|---------|
| `POST /upload` | Streaming binary upload with sha256 content-addressing, 1 GB cap (overridable via `MCP_GATEWAY_MAX_UPLOAD_MB`). Stores at `/agent/uploads/<sha256>/<filename>`; returns a `sample_id` reusable by MCP tools as `sample`. Path-traversal and multipart content rejected. |
| `GET /healthz` | Unauthenticated health check (everything else under `/mcp*` and `/upload` requires `Authorization: Bearer <token>`). |

Full per-tool docs (arguments, determinism notes, the IDA Pro native surface): [`mcp-gateway/README.md`](mcp-gateway/README.md).

## Connect Claude Code (host)

After `./run_docker.sh --remote`, the gateway is reachable at
`http://localhost:8080/mcp` (Streamable HTTP, bearer auth). There are two
ways to wire it into a host-side Claude Code install — pick whichever matches
your scope (per-project vs. all projects).

### Option A — `claude mcp add` (recommended; user scope, no JSON editing)

```bash
export MARE_GATEWAY_TOKEN=$(cat /path/to/MARE-MCP-Toolbox/workspace/.mcp-gateway-token)
# or paste from `./run_docker.sh --print-config`

claude mcp add --scope user --transport http mare-toolbox \
  http://localhost:8080/mcp \
  --header "Authorization: Bearer ${MARE_GATEWAY_TOKEN}"
```

This writes the server into `~/.claude.json` so every Claude Code project
inherits it. Replace `--scope user` with `--scope local` (default — current
project only, private to you) or `--scope project` (writes a checked-in
`.mcp.json`, shared with collaborators).

### Option B — project-scoped `.mcp.json` (checked in, shared with team)

A pre-built template ships at
[`templates/claude-code/.mcp.json`](templates/claude-code/.mcp.json):

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

Drop the file into your project root and export the env vars before launching
Claude Code:

```bash
export MARE_GATEWAY_TOKEN=$(cat /path/to/MARE-MCP-Toolbox/workspace/.mcp-gateway-token)
# Optional: override URL if you run on a different host/port.
# export MARE_GATEWAY_URL=http://10.0.0.5:8081/mcp
```

Claude Code expands `${VAR}` / `${VAR:-default}` in `.mcp.json` at startup, so
the token never has to live in version control. Claude Code prompts once per
machine to approve project-scoped servers.

### Verify the connection

```bash
# Unauthenticated health check (returns "ok")
curl -s http://localhost:8080/healthz

# Authenticated tool listing — proves bearer works
claude mcp list                 # should show mare-toolbox as "connected"
# Inside a Claude Code session: /mcp   (lists servers + their tools)
```

If the URL is non-default (different host/port, LAN-exposed, or behind a
reverse proxy), point Claude Code at the right address with
`MARE_GATEWAY_URL=http://host:port/mcp` before launching, or pass the explicit
URL to `claude mcp add`.

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

Connected clients can list and read the 13-artifact pipeline output via the MCP Resources protocol. The walker descends two levels deep over the canonical case subdirs (`tool-logs/`, `extracted/`, `hex/`, `rop/`, `dynamic/`, `qemu/`, `disassembly/`, `decompilation/`, `xrefs/`, `r2-sessions/`):

```
mare://cases/000-mfc42ul.dll/00_sample_profile.md
mare://cases/000-mfc42ul.dll/05_behavior_hypotheses.md
mare://cases/000-mfc42ul.dll/10_reporting_draft.md
mare://cases/000-mfc42ul.dll/CURRENT_STATE.json
mare://cases/000-mfc42ul.dll/tool-logs/2026-04-15T101512Z-run_shell-a1b2.txt
mare://cases/000-mfc42ul.dll/extracted/unblob-2026-04-15T101820Z-c4d5/...
…
```

`resources/list` enumerates everything under `/agent/status/`; `resources/read` returns the artifact content with the appropriate MIME type (`application/json`, `text/markdown`, `text/plain`).

Uploads are NOT exposed as resources — use `list_uploads()` and `get_sample_info()` tool calls instead.

## Recommended analysis workflow

The author-recommended way to approach malware work in this project is the
[`malware-analysis-orchestrator`](workspace/.claude/skills/malware-analysis-orchestrator/)
skill, mirrored for Codex at
[`workspace/.codex/skills/malware-analysis-orchestrator/`](workspace/.codex/skills/malware-analysis-orchestrator/).
It teaches the phased analysis discipline: create a case directory, preserve
raw strings/imports, rank interesting signals, build evidence-backed
hypotheses, plan deeper reverse engineering, route findings to one of seven
W-N deep workflows (packed-binary triage, ELF/PE deep-dive, ROP hunt, dynamic
API trace, firmware unpack, cross-arch IoT triage), and keep `INDEX.md` /
`CURRENT_STATE.json` fresh. The skill encodes IDA-first backend priority and
the v1.1 tool surface (gateway tools when remote, `scripts/` when in-container)
in one dual-mode document.

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
case artifacts. For iterative r2-driven work, use `open_r2_session` so analysis
state (`aaa`, flags, comments) survives across calls. For long-running tools
that would exceed the 60 s MCP request cap, dispatch through
`start_tool_job` and poll via `get_tool_job`.

## Disassembler backends

The gateway pins one backend for its lifetime (priority: **IDA > Binary Ninja >
Ghidra**), then merges that backend's native MCP tools into `tools/list`
under their original names. Clients call `get_active_backend()` to discover
which backend is active and key on `ida` / `bn` / `ghidra` / `none` for
schema-aware tool calls (e.g. IDA's native `decompile(addr, ...)` vs Ghidra's
native `function.decompile`).

- IDA Pro: headless `idalib-mcp` over Streamable HTTP at `127.0.0.1:8745/mcp`
- Binary Ninja: stdio MCP subprocess via `bn-mcp`
- Ghidra: stdio MCP subprocess via `ghidra-mcp` / `pyghidra`

Build with paid backends:

```bash
# Drop binaryninja.zip and/or idapro.zip in the repo root, then:
./run_docker.sh           # local mode, will detect them
./run_docker.sh --remote  # remote mode, ditto
```

Without either, Ghidra is installed by default.

## Background jobs

Tools that can outlive the 60 s MCP request cap dispatch as background jobs:

```python
# Start
res = await mcp.call_tool("start_tool_job", {"tool": "unblob", "args": {
    "case_dir": "/agent/status/000-firmware.bin",
    "sample": "<sha256>",
}})
job_id = res["job_id"]

# Poll
status = await mcp.call_tool("get_tool_job", {"job_id": job_id})
# status: queued | running | done | killed_log_cap | cancelled | error

# Cancel (SIGTERM then SIGKILL after grace period)
await mcp.call_tool("cancel_tool_job", {"job_id": job_id})

# Enumerate
await mcp.call_tool("list_tool_jobs", {"state": "running"})
```

Registered tool specs (long-running side of the gateway): `capa`, `unblob`,
`binwalk_extract`, `strace`, `ltrace`, `qemu_user`, plus the `_sleep_probe`
and `_log_burst_probe` internal smoke-test specs. Each job has a process-group
SIGKILL on cancel, a log-size cap that kills with `status=killed_log_cap`, and
an FIFO eviction policy on the completed-job registry (default 200). All
in-flight jobs are killed on gateway shutdown (in-memory registry).

## Dynamic Mode (env-gated)

Seven dynamic-analysis tools are **registered only when**
`MCP_GATEWAY_DYNAMIC_TOOLS=1` is set at gateway startup. Default-off so the
standard container shape is unchanged from the static-analysis-only mode.

### Opt-in

```bash
./run_docker.sh --remote --dynamic
```

The `--dynamic` flag REQUIRES `--remote` (dynamic tools are an MCP-only surface;
there is no in-container agent path that calls them directly). Running
`--dynamic` without `--remote` exits with `64 EX_USAGE`.

### Tools added when enabled

| Tool | Purpose |
|------|---------|
| `run_strace` | Linux syscall trace via strace, profile-driven argv (`file_io`, `network`, `process`, …) |
| `run_ltrace` | Library-call trace via ltrace (0.7.3 is unmaintained — prefer strace for modern binaries) |
| `run_qemu_user` | Cross-arch user-mode emulation via `qemu-<arch>-static` |
| `open_gdb_session` | Persistent gdb-MI3 session restricted to an MI-prefix allowlist |
| `gdb_exec` | Execute one MI command in an open gdb session |
| `close_gdb_session` | Close a gdb session (idempotent) |
| `get_dynamic_capabilities` | Report startup capability probe results (ptrace_scope, binfmt, netns, qemu arches) |

`run_strace`, `run_ltrace`, and `run_qemu_user` are dispatched as background
jobs (Phase 9 system). `open_gdb_session` / `gdb_exec` / `close_gdb_session`
reuse the Phase 8 session registry.

### Security posture

- **No-net by default.** Each dynamic-tool subprocess runs under per-call
  `unshare --net --ipc --uts --` — no network, no host IPC, no shared UTS.
- **gdb MI allowlist.** `gdb_exec` accepts only allowlisted MI prefixes
  (49-entry allowlist: `-info-`, `-data-evaluate-expression`,
  `-stack-list-frames`, `-exec-run`, `-break-insert`, etc.). `python`, `pi`,
  `-interpreter-exec console`, `source`, `shell`, `!`, `-target-select`,
  `attach`, and 7 other vectors are hard-blocked by a deny regex.
- **Follow-fork reaping.** Setsid grandchildren that escape the runner's
  process group are killed via `/proc/<pid>/task/*/children` recursive scan
  (default depth 8) after each job terminates.
- **Argv-only.** All trace tools spawn via `asyncio.create_subprocess_exec`
  with `start_new_session=True`. `extra_args` are validated against an
  allowlist regex; `-o`, `-D`, `--detach`, `-p`, `--attach`, `-b`,
  `--detach-on` and other escape flags are denied.
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

Inside the container:

```bash
./scripts/probe_dynamic_tools.sh
```

Or query the running gateway via MCP:

```python
await mcp.call_tool("get_dynamic_capabilities")
```

The `app.py` lifespan startup also runs the probe and logs INFO/WARN lines per
capability so operators see missing prerequisites before the first tool call.

### Limitations (v1.1)

- Sessions (r2 + gdb) are shared across all MCP clients with the same bearer
  token (per-`Mcp-Session-Id` keying is v1.2 territory).
- No `allow_network=True` opt-in; sandboxed-network mode (INetSim/FakeDNS) is
  deferred to v1.2.
- qemu-user multi-threaded sample emulation is unreliable (known qemu issue).
- ltrace 0.7.3 is unmaintained; prefer strace for modern binaries.

## Unsafe r2 sessions (env-gated, off by default)

`open_r2_session` spawns r2 with `cfg.sandbox=true` baked into argv before the
sample is opened (r2's native one-way latch — cannot be disabled mid-session).
When you need full r2 capability — `R!`/`!`/`#!` shell escapes, debug-mode
extensions, etc. — set `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1` to register
`open_r2_session_unsafe`. Every open emits a WARN-level audit log line; the
unsafe tool shares the combined r2+gdb session cap. Treat the unsafe surface as
a deliberate, audited opt-in; not for production.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `401 Unauthorized` from Claude Code or mastra | Token rotates per `--remote` start. Refresh: `./run_docker.sh --print-config` and update your env var. |
| `[error] no token file at workspace/.mcp-gateway-token` from `--print-config` | Container isn't running. Start it: `./run_docker.sh --remote`. |
| Port 8080 already in use | `MCP_GATEWAY_HOST_PORT=8081 ./run_docker.sh --remote` |
| `[error] --dynamic requires --remote` | Re-run as `./run_docker.sh --remote --dynamic`. Dynamic tools are MCP-only. |
| `get_dynamic_capabilities` shows `ptrace_scope=2` | On the host: `sudo sysctl -w kernel.yama.ptrace_scope=0`. |
| `run_qemu_user` fails on foreign-arch binary | Register binfmt host-side: `docker run --rm --privileged multiarch/qemu-user-static --reset -p yes`. |
| `tools/list` returns 47 instead of 54 | You're on a stale image — Phase 5's image-hash fix is wired; rerun `./run_docker.sh --remote` to rebuild. |
| Build fails at `[internal] booting buildkit` with `invalid mount config ... docker-desktop-bind-mounts` | Stale Buildx builder state, usually after Docker Desktop/WSL restarts or updates. Recreate it: `docker buildx rm training && docker buildx create --use --name training`, then rerun `./run_docker.sh --remote`. If removal fails, first run `docker rm -f buildx_buildkit_training0`. |
| Mastra `npm install` peer-dep warning on `@mastra/core` | The project pins `@mastra/mcp@~1.3.x`; `@mastra/core` is open to `^1.x`. Warnings are tolerated; if `npm start` fails, downgrade core. |
| Resource list returns no `mare://` URIs | No cases yet. Run a triage first (e.g. via the mastra starter or `tools/call run_triage`). |
| `run_shell` returns ACL error | Container needs the `acl` package and `setfacl` — both are baked in via the Dockerfile. If you see this in CI on a custom base image, verify both are installed. |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Host                                                                            │
│                                                                                 │
│   Claude Code (.mcp.json)        mastra.ai (@mastra/mcp)        any MCP client  │
│              │                            │                             │       │
│              └─────────────── Streamable HTTP (Bearer) ─────────────────┘       │
│                                           │                                     │
│                                  ${HOST_BIND}:${HOST_PORT}                      │
└───────────────────────────────────────────┼─────────────────────────────────────┘
                                            │ (compose port publish)
┌───────────────────────────────────────────┼─────────────────────────────────────┐
│ Kali container (CAP_SYS_PTRACE, seccomp=unconfined)                             │
│                                            │                                    │
│                         ┌──────────────────▼──────────────────┐                 │
│                         │  mcp-gateway (FastMCP, uvicorn)     │                 │
│                         │   • /mcp  /upload  /healthz         │                 │
│                         │   • Bearer auth + Origin DNS-rebind │                 │
│                         │   • 54 / 61 / 55 / 62 native tools  │                 │
│                         │   • Backend pass-through merge      │                 │
│                         └──┬───────┬────────┬─────────┬───────┘                 │
│                            │       │        │         │                         │
│              ReToolRunner  │  SessionRegistry  BackgroundJobRegistry            │
│              (argv-only,   │  (r2 + gdb,       (capa, unblob,                   │
│               cwd-confine, │   idle reaper,     binwalk_extract,                │
│               killpg)      │   cap 8)           strace/ltrace/qemu,             │
│                            │                    cap 4 in-flight)                │
│                            ▼                                                    │
│                  ┌─────────────────────┐                                        │
│                  │ PinnedBackend       │  IDA Pro      → http://127.0.0.1:8745  │
│                  │ ClientSession       │  Binary Ninja → stdio                  │
│                  │ (priority IDA>BN>G) │  Ghidra       → stdio                  │
│                  └─────────────────────┘                                        │
│                                                                                 │
│  /agent/uploads/<sha256>/<filename>   /agent/status/<NNN>-<sample>/<artifact>   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

Key internals (under [`mcp-gateway/src/mcp_gateway/`](mcp-gateway/src/mcp_gateway/)):

- **`runner.py`** — `ReToolRunner` chokepoint. Argv-only `create_subprocess_exec`, `start_new_session=True`, hard timeout, `killpg(SIGKILL)` on timeout/cancel, chunked drain (no PIPE deadlock under 100 MB urandom), head-truncated preview with full output captured to `case_dir/tool-logs/<UTC>-<slug>-<rand4>.txt`. Returns a 12-key JSON result.
- **`artifacts_io.py`** — `confine_to(case_dir, path)` (rejects NUL bytes / traversal / symlink escape), `ensure_subdir`, `tool_log_path`, `ensure_mare_shell_access` (POSIX ACL for the `mare-shell` UID), `EXPANDED_CASE_SUBDIRS` catalog.
- **`sessions/`** — `BaseSession` + kind-aware `SessionRegistry` (cap shared between r2 + gdb), `sessions/r2.py` (driver + `_DANGEROUS_R2_CMD_RE` UX denylist), `sessions/gdb.py` (gdb-MI3 driver with 49-prefix allowlist + 15-vector deny regex). Atomic cap enforcement via `asyncio.BoundedSemaphore` (Phase 13).
- **`jobs.py`** — `BackgroundJobRegistry`, `JobToolSpec`/`Job`/`JobStatus`, `JOB_TOOL_REGISTRY`, log-cap with `MARE_JOB_KILLED_LOG_CAP` marker, FIFO eviction, `proc_callback` extension to `ReToolRunner.run`. Atomic in-flight cap via `asyncio.BoundedSemaphore` (Phase 13).
- **`extraction.py`** — `extraction_dir` minting (`extracted/<engine>-<UTC>Z-<rand4>/`), `_mare_meta.json` sidecar, recursive symlink quarantine, archive-bomb monitor (`_du_sb`, default 4 GB cap, `.MARE_EXTRACT_CAP_EXCEEDED` marker), atomic re-upload with sha256.
- **`dynamic.py`** — capability probes (`ptrace_scope`, `binfmt_misc`, qemu arches, netns feasibility), `wrap_netns` (`unshare --net --ipc --uts`), allowlisted argv profiles + builders, `reap_followfork_strays`.
- **`uploads.py`** — streaming `POST /upload`, sha256 content-addressing, 1 GB cap.
- **`auth.py`** — bearer token generation/load, 0600 token file, Origin DNS-rebind middleware.
- **`tools/`** — MCP tool modules registered by `register_all_tools(mcp)` in `tools/__init__.py`. Order: cases → artifacts → workflows → disasm → resources → re_artifacts → re_static → shell → r2_sessions → jobs → extract → [dynamic if `MCP_GATEWAY_DYNAMIC_TOOLS=1`] → [unsafe r2 if `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1`] → backend_passthrough. `collision_check` runs from `app.py::lifespan` AFTER backend tools are merged.

## Configuration reference

Environment variables read by the gateway (all optional):

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_GATEWAY_TOKEN` | generated | Pin bearer token; if unset a 43-char URL-safe token is generated and logged. |
| `MCP_GATEWAY_TOKEN_FILE` | `/agent/.mcp-gateway-token` | Path the token is written to (mode 0600). |
| `MCP_GATEWAY_HOST` | `127.0.0.1` | Bind host inside the container. |
| `MCP_GATEWAY_PORT` | `8080` | Bind port inside the container. |
| `MCP_GATEWAY_HOST_BIND` | `127.0.0.1` | Host-side bind interface for compose port publishing (set to `0.0.0.0` for LAN). |
| `MCP_GATEWAY_HOST_PORT` | `8080` | Host-side published port. |
| `MCP_GATEWAY_ENABLED` | unset | Dockerfile/entrypoint guard — `1` starts the gateway daemon (remote mode); 0 or unset = skip (local mode = v1 byte-identical). |
| `MCP_GATEWAY_QUIET` | unset | Set `1` to suppress the `[gateway] Bearer token: …` log line. |
| `MCP_GATEWAY_MAX_UPLOAD_MB` | `1024` | `/upload` size cap in MB. |
| `MCP_GATEWAY_DYNAMIC_TOOLS` | unset | `1` enables the seven dynamic-mode tools (set by `./run_docker.sh --dynamic`). |
| `MCP_GATEWAY_R2_UNSAFE_ALLOWED` | unset | `1` registers `open_r2_session_unsafe` (no `cfg.sandbox`); audited via WARN log. |
| `MCP_GATEWAY_RUN_SHELL_MAX_CMD_BYTES` | `32768` | Max UTF-8 byte length of a `run_shell` command. |
| `MCP_GATEWAY_RUNNER_DEFAULT_TIMEOUT_S` | `55.0` | Default per-call timeout for `ReToolRunner` (kept under MCP's 60 s request cap). |
| `MCP_GATEWAY_RUNNER_MAX_LOG_MB` | `256` | Per-tool log-file cap. |
| `MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB` | `256` | Head-preview bytes returned to MCP. |
| `MCP_GATEWAY_RUNNER_STDERR_HEAD_KB` | `64` | Head-preview bytes returned to MCP. |
| `MCP_GATEWAY_MAX_SESSIONS` | `8` | Combined cap across r2 + gdb sessions (atomic via `BoundedSemaphore`). |
| `MCP_GATEWAY_SESSION_IDLE_S` | `1800.0` | Idle reaper threshold for sessions. |
| `MCP_GATEWAY_R2_CMD_TIMEOUT_S` | `30.0` | Per-`r2_cmd` timeout. |
| `MCP_GATEWAY_REAPER_INTERVAL_S` | `60.0` | Session reaper tick. |
| `MCP_GATEWAY_SESSION_OPEN_TIMEOUT_S` | `15.0` | Session open timeout. |
| `MCP_GATEWAY_MAX_JOBS_INFLIGHT` | `4` | Atomic in-flight job cap. |
| `MCP_GATEWAY_MAX_COMPLETED_JOBS` | `200` | FIFO-evicted completed job retention. |
| `MCP_GATEWAY_MAX_JOB_LOG_MB` | `256` | Per-job log cap (over-cap → `status=killed_log_cap`). |
| `MCP_GATEWAY_JOB_TIMEOUT_S` | `3600.0` | Default per-job timeout. |
| `MCP_GATEWAY_JOB_MAX_TIMEOUT_S` | `86400.0` | Hard ceiling for caller-supplied job timeout. |
| `MCP_GATEWAY_JOB_CANCEL_GRACE_S` | `10.0` | SIGTERM → SIGKILL grace period on cancel. |
| `MCP_GATEWAY_MAX_EXTRACT_MB` | `4096` | Archive-bomb cap (per extraction directory). |
| `MCP_GATEWAY_EXTRACT_MONITOR_INTERVAL_S` | `5.0` | `_du_sb` poll interval. |
| `MCP_GATEWAY_LIST_EXTRACT_FILES_PER_EXTRACTION` | `5000` | Max files surfaced per `list_extracted_files` call. |
| `MCP_GATEWAY_DYN_REAP_DEPTH` | `8` | Recursive scan depth for follow-fork stray reaping. |
| `MCP_GATEWAY_DYN_PROBE_TIMEOUT_S` | `3.0` | Per-probe timeout in `get_dynamic_capabilities`. |

## Project layout

```
.
├── Dockerfile                 # Kali base + 50+ RE tools + conditional BN/IDA install
├── run_docker.sh              # Mode selector: local / --remote / --dynamic / --print-config
├── compose.yaml               # Base compose: caps, ports, env passthrough
├── compose.remote.yaml        # Remote overlay: detached, tail -f /dev/null keepalive
├── scripts/
│   ├── compute_image_hash.sh    # Phase 5: content-hash for image cache (covers mcp-gateway/)
│   ├── probe_dynamic_tools.sh   # Phase 11: dynamic-mode capability probe
│   └── probe_extraction_tools.sh# Phase 10: binwalk3/unblob/upx readiness
├── mcp-gateway/               # FastMCP gateway (Python; remote mode)
│   ├── src/mcp_gateway/
│   │   ├── app.py             # FastMCP server + lifespan + Origin/Bearer middleware
│   │   ├── runner.py          # ReToolRunner (Phase 6 chokepoint)
│   │   ├── artifacts_io.py    # confine_to, tool_log_path, EXPANDED_CASE_SUBDIRS
│   │   ├── sessions/          # BaseSession + r2 + gdb (Phase 8/11)
│   │   ├── jobs.py            # BackgroundJobRegistry (Phase 9)
│   │   ├── extraction.py      # extraction_dir + bomb monitor (Phase 10)
│   │   ├── dynamic.py         # Capability probes + argv profiles (Phase 11)
│   │   ├── uploads.py         # /upload streaming endpoint
│   │   ├── auth.py            # Bearer token + Origin DNS-rebind
│   │   ├── backend/           # PinnedBackend ClientSession
│   │   └── tools/             # 54+ MCP tool modules
│   └── tests/                 # Pytest suite (≈ 600 tests, gateway-only)
├── templates/                 # Pre-built client configs
│   ├── claude-code/.mcp.json
│   └── mastra/                # Runnable starter project
└── workspace/                 # Mounted at /agent/ inside the container
    ├── .claude/skills/malware-analysis-orchestrator/
    ├── .codex/skills/malware-analysis-orchestrator/
    ├── examples/              # Bundled malware samples
    └── .mcp-gateway-token     # Auto-written; bearer token for remote mode
```

## Security notes

- The gateway requires a bearer token on every `/mcp` and `/upload` request; `/healthz` is unauthenticated.
- An Origin DNS-rebind middleware rejects cross-origin requests that don't match the bind host.
- Default bind is `127.0.0.1:8080` (localhost only). Set `MCP_GATEWAY_HOST_BIND=0.0.0.0` only when you intentionally need LAN access, and consider a reverse proxy with TLS.
- The container runs with elevated capabilities (`SYS_PTRACE`, `seccomp=unconfined`) for analysis tools — do NOT expose it to the public internet without a reverse proxy you trust.
- `run_shell` runs as a non-root `mare-shell` UID with `--clear-groups --no-new-privs --inh-caps=-all`, but confinement is **posture**, not isolation. A determined attacker controlling the agent can still read the container's world-readable filesystem. Mount-namespace isolation and network egress controls are deferred to v1.2.
- Disassembler licenses (IDA, Binary Ninja) live ONLY on the host bind mount; never baked into images.
- `open_r2_session_unsafe` is opt-in via env var and audited via WARN log; treat it as a deliberate operator escape hatch.

## License & licensing constraints

This project is MIT-licensed. IDA Pro and Binary Ninja licenses are user-provided and never included in image layers — see the `Dockerfile` multi-stage build for the seeding pattern.

## Further reading

- [`mcp-gateway/README.md`](mcp-gateway/README.md) — full per-tool docs (arguments, determinism notes), /upload contract, IDA Pro native tool surface
- [`templates/mastra/README.md`](templates/mastra/README.md) — full mastra starter walkthrough
- [`workspace/.claude/skills/malware-analysis-orchestrator/`](workspace/.claude/skills/malware-analysis-orchestrator/) and [`workspace/.codex/skills/malware-analysis-orchestrator/`](workspace/.codex/skills/malware-analysis-orchestrator/) — the 13-artifact pipeline + W-1..W-7 deep workflows for Claude and Codex
- [`.planning/`](.planning/) — design docs, phase plans, requirements (v1.0 shipped 2026-04-27; v1.1 Phases 5-13 complete pending live runtime UAT)
