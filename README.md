# Agentic Malware Analysis

Automated deep malware reverse engineering driven by AI agents. A Kali-based Docker environment pairs 50+ RE tools with MCP-connected disassembler backends ([Binary Ninja][binary-ninja-headless-mcp] or [Ghidra][ghidra-headless-mcp]) and a structured multi-phase orchestrator skill that turns a raw binary into a case directory of ranked evidence, validated hypotheses, component maps, and a prioritized deep-analysis plan -- with no human interaction required. Ready for [Claude Code][claude-code] and [Codex CLI][codex-cli].

See the companion blog post [Building a Pipeline for Agentic Malware Analysis][blog-post] for background, a case study, and evaluation.

## Why

Initial malware analysis involves a number of routine steps: collecting hashes and compiler artifacts, extracting strings, inspecting imports, running YARA and capa, correlating the results, and identifying code areas for closer inspection. These steps provide the basis for deeper analysis, but they are often repetitive and time-consuming.

This repository automates much of that workflow. The orchestrator skill collects and organizes analysis artifacts, highlights relevant signals, generates evidence-backed hypotheses, builds a basic component model, and prepares a prioritized deep-analysis plan. All intermediate results are stored in a per-sample case directory on disk, making the workflow easier to resume and review.

Via MCP, the agent can also use Binary Ninja or Ghidra to inspect functions, follow cross-references, and tie findings to concrete code locations. The result is a structured starting point for follow-up analysis rather than ad hoc triage alone.

## Features

- Kali Linux container with 50+ RE and malware analysis tools
- Automatic MCP backend selection with priority chain (IDA Pro > Binary Ninja > Ghidra)
- `malware-analysis-orchestrator` skill for Claude Code and Codex CLI
- Helper scripts for strings, imports, YARA, capa, signal ranking, hypothesis generation
- Bundled YARA rules (crypto, anti-debug/anti-VM, capabilities, packer -- from [Yara-Rules/rules][yara-rules], GPL-2.0)
- Native config files for Claude Code and Codex with aggressive defaults
- Persistent state across container rebuilds (BN license, Claude auth, Codex auth)
- PE, ELF, and Mach-O support
- Content-hash-based image caching

## Prerequisites

- Docker with `buildx`
- Anthropic API key or Claude account (for Claude Code) or OpenAI API key (for Codex)
- Recommended (choose one disassembler): IDA Pro 9+ Linux archive with a valid `.hexlic`, or Binary Ninja Linux zip with a headless-capable license — see [Setup](#setup). Without either, Ghidra is installed as a fallback.

## Quick Start

> **Important:** `run_docker.sh` mounts the `workspace/` subdirectory into the container at `/agent`. The agents run with full permissions (configured via native settings files and the entrypoint script) by design, so the agent can read, write, and execute anything in that directory. Only files inside `workspace/` are visible to the agent.

```bash
git clone https://github.com/mrphrazer/agentic-malware-analysis.git
cd agentic-malware-analysis
cp /path/to/idapro.zip ./idapro.zip                   # optional; highest priority if present
cp /path/to/binaryninja_linux.zip ./binaryninja.zip   # optional; used if IDA Pro is absent
./run_docker.sh                                        # falls back to Ghidra if neither zip is present
```

What happens:

1. Prepares a Docker Buildx builder
2. Disassembler selection by priority: if `idapro.zip` is present, IDA Pro (headless `idalib-mcp`, Streamable HTTP on `127.0.0.1:8745`) is installed and selected; else if `binaryninja.zip` is present, Binary Ninja and its MCP server (stdio transport) are installed; otherwise Ghidra and its MCP server (stdio transport) are installed as a fallback
3. Clones the selected MCP server repo into `workspace/mcp/`
4. Builds the image (or reuses a cached one based on content hash)
5. Seeds BN license, Claude credentials, and Codex credentials from host directories
6. Launches the container with `workspace/` mounted at `/agent`

Inside the container:

```bash
claude   # or: codex
```

Extract the included example sample and start an analysis with the orchestrator skill:

```bash
cd examples && unzip -P infected samples.zip && cd ..
```

Then prompt the agent:

```
Analyze the malware in examples/samples/mfc42ul.dll -- Give me a detailed overview
of the sample's functionality and features, together with the corresponding code
locations.
```

See [examples/README.md](examples/README.md) for sample details and background.

## Setup

Backend priority order at build time is **IDA Pro > Binary Ninja > Ghidra**. The first available option is installed and registered with the agent. Only one backend is active per container.

### IDA Pro (highest priority)

IDA Pro 9+ is supported through the headless [ida-pro-mcp][ida-pro-mcp] server (`idalib-mcp`), which speaks MCP over **Streamable HTTP** on `127.0.0.1:8745` (the same server also exposes `/sse` on the same port for clients that prefer SSE; Codex uses that). If `idapro.zip` is present at build time, IDA Pro is installed and selected ahead of Binary Ninja and Ghidra. The entrypoint auto-starts `idalib-mcp` as a background process when the image is built with IDA Pro.

To use IDA Pro, place your IDA 9+ Linux archive in the repository root **before** running `run_docker.sh`:

```bash
cp /path/to/idapro.zip ./idapro.zip
```

The file must be named `idapro.zip`. Alternatively, point to it explicitly:

```bash
IDA_PRO_ZIP=/path/to/idapro.zip ./run_docker.sh
```

**License:** IDA Pro 9.x ships a single `ida.hexlic` file (the legacy `ida.key` format was retired with IDA 8). Place your license at `~/.idapro/ida.hexlic` on the host; `run_docker.sh` copies it into a Docker-specific directory (`~/.idapro-docker/` by default) that is mounted into the container at `/home/agent/.idapro`. The license is never baked into the image. If you still have a legacy `ida.key`, drop it next to the `.hexlic`; both are seeded when present. To use a different host directory:

```bash
IDA_USER_DIR=/path/to/idapro-user-dir ./run_docker.sh
```

**One-time batch-mode EULA acceptance:** IDA Pro has two separate EULAs — the GUI one and a batch/headless one that `idalib-mcp` requires. If `idalib_open()` fails with `License not yet accepted, cannot run in batch mode`, run the bundled helper **once** inside the container:

```bash
ida-accept-eula
```

This launches Hex-Rays' first-party `idat` binary in batch mode, which triggers IDA Pro's own EULA prompt — accept it once and the flag is persisted in `~/.idapro/ida.reg`. Because that directory is bind-mounted from `~/.idapro-docker/` on the host, the acceptance survives every future container build and run on that host.

The helper is a thin wrapper around the official `idat -A -c -B <stub>` invocation; no third-party code touches the license state. Auto-accepting non-interactively is not supported by Hex-Rays (there is no documented env var or API), so the first-run step remains manual by design.

### Binary Ninja

Binary Ninja provides substantially better analysis results than Ghidra through its [headless MCP server][binary-ninja-headless-mcp]. It is used when no IDA Pro archive is present. If neither IDA Pro nor Binary Ninja is present, the environment falls back to Ghidra automatically.

To use Binary Ninja, place your Linux headless zip in the repository root **before** running `run_docker.sh`:

```bash
cp /path/to/binaryninja_linux.zip ./binaryninja.zip
```

The file must be named `binaryninja.zip`. Alternatively, point to it explicitly:

```bash
BINARY_NINJA_ZIP=/path/to/binaryninja.zip ./run_docker.sh
```

Binary Ninja requires a valid `license.dat`. On first run, `run_docker.sh` copies your existing license from `~/.binaryninja/license.dat` into a Docker-specific directory (`~/.binaryninja-docker/`) that is mounted into the container at `/home/agent/.binaryninja`. The license is never baked into the image. To use a different host directory:

```bash
BINARY_NINJA_USER_DIR=/path/to/binaryninja-user-dir ./run_docker.sh
```

### Claude Code Authentication

`run_docker.sh` maintains a persistent Claude state directory at `~/.claude-docker/` on the host, mounted into the container at `/home/agent/.claude`. On first run, it seeds credentials from `~/.claude/.credentials.json` if available. You can also log in inside the container with `claude auth`; credentials persist across container rebuilds in the mounted directory. To use a different host directory:

```bash
CLAUDE_USER_DIR=/path/to/claude-dir ./run_docker.sh
```

### Codex CLI Authentication

`run_docker.sh` maintains a persistent Codex state directory at `~/.codex-docker/` on the host, mounted into the container at `/home/agent/.codex`. On first run, it seeds credentials from `~/.codex/auth.json` if available. You can also log in inside the container with `codex login`; credentials persist across container rebuilds in the mounted directory. To use a different host directory:

```bash
CODEX_USER_DIR=/path/to/codex-dir ./run_docker.sh
```

## Docker Environment

### Installed Tooling

**Fingerprinting:** `file`, `sha256sum`, `md5sum`, `ssdeep`, `die`/`diec`, `yara`, `capa`

**String extraction:** `strings`, `floss` (FLARE-FLOSS), `rabin2`

**Disassembly and analysis:** `radare2`, `binwalk`, `gdb`/`gdb-multiarch`, `capstone` (Python)

**Binary utilities:** `objdump`, `readelf`, `nm`, `patchelf`, `elfutils`

**Hex editors:** `hexedit`, `bvi`, `xxd`, `ht`, `hexwalk`

**Dynamic analysis:** `strace`, `ltrace`, `qemu-user`

**Build tools:** `gcc`, `g++`, `clang`, `lldb`, `lld`, `llvm`, `cmake`, `nasm`

**Python:** Python 3, `pip`, `venv`, `ipython`, `ipdb`, `uv`

**Data processing:** `jq`, `yq`

**Extraction:** `upx`, `unblob`, `ropper`

**Node.js:** Node.js 22

**Agent CLIs:** Claude Code, Codex CLI

**Conditional (by priority):** IDA Pro 9+ headless via `idalib-mcp` (if `idapro.zip` provided) _or_ Binary Ninja headless + Python API (if `binaryninja.zip` provided) _or_ Ghidra + `pyghidra` (fallback)

### Runtime Configuration

- Working directory: `/agent`
- User: `agent` (non-root, passwordless sudo)
- Capabilities: `SYS_PTRACE`, `seccomp=unconfined`
- Volume mounts:
  - Host `workspace/` → `/agent`
  - BN user dir → `/home/agent/.binaryninja`
  - IDA user dir → `/home/agent/.idapro` (holds `ida.hexlic`)
  - Claude state dir → `/home/agent/.claude`
  - Codex state dir → `/home/agent/.codex`

## MCP Integration

The environment automatically selects and configures one MCP backend following the priority chain **IDA Pro > Binary Ninja > Ghidra**.

- **IDA Pro installed** → [ida-pro-mcp][ida-pro-mcp] (registered as `ida_mcp`, Streamable HTTP at `http://127.0.0.1:8745/mcp`; Codex connects to `/sse` on the same server)
- **No IDA, Binary Ninja installed** → [binary-ninja-headless-mcp][binary-ninja-headless-mcp] (registered as `binary_ninja_headless_mcp`, stdio transport)
- **Neither present** → [ghidra-headless-mcp][ghidra-headless-mcp] (registered as `ghidra_headless_mcp`, stdio transport)

`configure-agent-mcp.sh` detects which disassembler is present inside the container (checking `idalib-mcp` on PATH first, then Binary Ninja, then Ghidra) and writes the correct `.mcp.json` (Claude Code) and Codex config. For IDA Pro, the config uses `"type": "sse"` with the `idalib-mcp` server URL; for BN/Ghidra it uses `"type": "stdio"`. Binary Ninja and Ghidra MCP servers are cloned at runtime by `run_docker.sh` into `workspace/mcp/`; IDA Pro's MCP server is installed directly from PyPI/GitHub during the image build.

Override the upstream repos:

```bash
BINJA_MCP_REPO_URL=https://github.com/mrphrazer/binary-ninja-headless-mcp.git ./run_docker.sh
GHIDRA_MCP_REPO_URL=https://github.com/mrphrazer/ghidra-headless-mcp.git ./run_docker.sh
```

## Malware Analysis Orchestrator

The `malware-analysis-orchestrator` skill drives a structured, multi-phase malware analysis workflow. It is available for both [Claude Code](workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md) and [Codex CLI](workspace/.codex/skills/malware-analysis-orchestrator/SKILL.md).

### Workflow Stages

1. **Intake and fingerprinting** -- hashes, file type, packer/compiler detection, YARA scan, capa scan
2. **Raw strings collection** -- `strings`, `rabin2`, `floss` with source tags
3. **Raw API/import collection** -- `rabin2`, format-specific tools (PE/ELF/Mach-O)
4. **Signal filtering and ranking** -- score and rank interesting strings and imports by capability
5. **Hypothesis generation** -- cross-link evidence, generate behavior hypotheses with confidence and evidence
6. **Component inventory and interaction modeling** -- infer components, map data/control flow
7. **Deep analysis planning and prioritization** -- ordered tasks with target functions, expected findings, stop criteria
8. **Reporting** -- executive summary, technical findings, IOCs, open questions

### Case Directory

Each analysis creates a persistent per-sample directory at `status/<NNN>-<filename>/` containing 13 required artifact files:

| # | File | Content |
|---|------|---------|
| 1 | `00_sample_profile.md` | Hashes, file type, packer, YARA, capa results |
| 2 | `01_strings_raw.txt` | All extracted strings with source tags |
| 3 | `02_strings_interesting.md` | Ranked interesting strings with categories |
| 4 | `03_imports_raw.txt` | Full import tables with source tags |
| 5 | `04_imports_interesting.md` | Suspicious API clusters by capability |
| 6 | `05_behavior_hypotheses.md` | Hypotheses with confidence and evidence |
| 7 | `06_component_inventory.md` | Inferred components with roles and evidence |
| 8 | `07_interaction_model.md` | Data and control flow between components |
| 9 | `08_deep_analysis_plan.md` | Ordered deep-analysis tasks |
| 10 | `09_priority_queue.md` | Priority queue with rationale and blockers |
| 11 | `10_reporting_draft.md` | Executive summary and technical findings |
| 12 | `INDEX.md` | Artifact list, timestamps, missing items |
| 13 | `CURRENT_STATE.json` | Machine-readable phase and progress state |

This externalized state is what makes the workflow resilient to context-window compaction: the agent reads case files back from disk instead of relying on conversation history.

### Helper Scripts

| Script | Purpose |
|--------|---------|
| `init_status_tree.sh` | Create or reuse a case directory for a sample |
| `collect_strings.sh` | Run `strings`, `rabin2 -zz`, `floss` and write raw output |
| `collect_imports.sh` | Run `rabin2 -i` and format-specific import tools |
| `scan_yara.sh` | Scan sample with bundled YARA rules |
| `scan_capa.sh` | Run capa for ATT&CK/MBC capability identification |
| `rank_signals.py` | Score and rank interesting strings and imports |
| `build_hypothesis.py` | Generate baseline behavior hypotheses (optional) |
| `update_state.py` | Update `CURRENT_STATE.json` with phase transitions |
| `resolve_case.sh` | Resolve the latest case directory for a sample |

### Bundled YARA Rules

Four rule sets from [Yara-Rules/rules][yara-rules] (GPL-2.0):

- `crypto_signatures.yar` -- cryptographic algorithm and constant detection
- `antidebug_antivm.yar` -- anti-debug and anti-VM technique detection
- `capabilities.yar` -- malicious capability detection
- `packer_compiler_signatures.yar` -- packer and compiler signature detection

### Roles

- **Orchestrator** -- drives phases, enforces artifact completeness, schedules parallel collection
- **Planner** -- consumes intermediate evidence, generates hypotheses, defines deep-analysis priorities
- **Reporter** -- produces executive and technical summaries with traceable evidence

## Agent Defaults

Aggressive defaults are applied via native config files and the container entrypoint script (`configure-agent-mcp.sh`), not wrapper scripts.

### Claude Code

- Default model: `opus`
- Default effort: `high`
- Default permissions: bypass all prompts
- Configured at user level (`~/.claude/settings.json`) by the entrypoint script
- See [Claude Code Authentication](#claude-code-authentication) for credential setup

### Codex CLI

- Default model: `gpt-5.4`
- Default reasoning: `xhigh`
- Default permissions: full auto-approval, no sandbox
- Features: `multi_agent`, `child_agents_md`
- Configured at user level (`~/.codex/config.toml`) by the entrypoint script
- See [Codex CLI Authentication](#codex-cli-authentication) for credential setup

## Customization

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `IDA_PRO_ZIP` | `./idapro.zip` | Path to IDA Pro 9+ Linux archive |
| `IDA_USER_DIR` | `~/.idapro-docker` | IDA Pro license (`ida.hexlic`) and user settings |
| `BINARY_NINJA_ZIP` | `./binaryninja.zip` | Path to Binary Ninja Linux zip |
| `BINARY_NINJA_USER_DIR` | `~/.binaryninja-docker` | BN license, settings, and plugins |
| `CLAUDE_USER_DIR` | `~/.claude-docker` | Claude auth and state |
| `CODEX_USER_DIR` | `~/.codex-docker` | Codex auth and state |
| `BINJA_MCP_REPO_URL` | `https://github.com/mrphrazer/binary-ninja-headless-mcp.git` | Binary Ninja MCP repo |
| `GHIDRA_MCP_REPO_URL` | `https://github.com/mrphrazer/ghidra-headless-mcp.git` | Ghidra MCP repo |

### Running Specific Commands

```bash
./run_docker.sh claude
./run_docker.sh codex
./run_docker.sh python3 -c 'import sys; print(sys.version)'
```

## Repository Layout

```
.
├── Dockerfile
├── compose.yaml
├── run_docker.sh
├── docker-bin/
│   └── configure-agent-mcp.sh
├── workspace/
│   ├── CLAUDE.md
│   ├── .claude/skills/malware-analysis-orchestrator/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   ├── references/
│   │   └── assets/
│   │       ├── yara_rules/
│   │       └── status_templates/
│   ├── .codex/
│   │   ├── agents/openai.yaml
│   │   └── skills/malware-analysis-orchestrator/
│   │       ├── SKILL.md
│   │       ├── scripts/
│   │       ├── references/
│   │       └── assets/
│   │           ├── yara_rules/
│   │           └── status_templates/
│   └── examples/
│       ├── README.md
│       └── samples.zip
├── blogs/
└── README.md
```

Note: `workspace/mcp/` and `workspace/status/` are created at runtime and gitignored.


## Limitations

- Agent runs are non-deterministic -- repeated analyses of the same sample may produce different results
- Context-window constraints limit single-pass depth; the orchestrator mitigates this with externalized state
- Agents may produce overconfident or incorrect claims -- expert validation is required
- The orchestrator focuses on static analysis; dynamic analysis tools are available but not orchestrated
- The container runs with elevated permissions by design (see Security)

## Security

- `SYS_PTRACE` and `seccomp=unconfined` are required for debugging and dynamic analysis -- intentional
- Agent config defaults to full permissions inside the container sandbox -- by design for autonomous analysis
- MCP communication is unauthenticated (stdio transport for BN/Ghidra; local-only Streamable HTTP on `127.0.0.1:8745` for IDA Pro)
- Do not expose the container to untrusted networks or users
- Binary Ninja and IDA Pro licenses are stored on the host, not in the image; the proprietary archives (`idapro.zip`, `binaryninja*.zip`) are gitignored

## Contact

Tim Blazytko ([@mr_phrazer](https://x.com/mr_phrazer))

[binary-ninja-headless-mcp]: https://github.com/mrphrazer/binary-ninja-headless-mcp
[ghidra-headless-mcp]: https://github.com/mrphrazer/ghidra-headless-mcp
[ida-pro-mcp]: https://github.com/mrexodia/ida-pro-mcp
[claude-code]: https://docs.anthropic.com/en/docs/claude-code
[codex-cli]: https://github.com/openai/codex
[blog-post]: https://synthesis.to/2026/03/18/agentic_malware_analysis.html
[yara-rules]: https://github.com/Yara-Rules/rules
