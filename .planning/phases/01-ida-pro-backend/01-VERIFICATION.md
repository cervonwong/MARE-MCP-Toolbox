---
phase: 01-ida-pro-backend
verified: 2026-04-14T07:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/5
  gaps_closed:
    - "configure-agent-mcp.sh now checks `command -v idalib-mcp` (correct command name)"
    - "IDA Pro MCP config now writes SSE transport (`type: sse`, `url: http://localhost:8745/sse`) per locked CONTEXT.md decision"
    - "ROADMAP SC-2 text reads 'via SSE transport' — no contradiction with CONTEXT.md"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Build container with INSTALL_IDA_PRO=1 and a valid IDA Pro zip. Inside container: `which idalib-mcp && idalib-mcp --help`"
    expected: "Command found on PATH. Confirms mrexodia/ida-pro-mcp installs `idalib-mcp` correctly."
    why_human: "Requires a valid IDA Pro zip file and a real Docker build run. Cannot verify the installed command name without executing the build with the actual package."
  - test: "Run IDA Pro MCP tools inside container with a test binary: `open_database('/path/to/test.elf')`, `list_functions()`, `decompile('main')`"
    expected: "Functions listed, decompiled code returned"
    why_human: "Requires valid IDA Pro license and a compiled test binary. No automated check possible without the licensed environment."
  - test: "Verify Python import coexistence: build with INSTALL_BINARY_NINJA=1 and INSTALL_IDA_PRO=1. In container: `python3 -c 'import binaryninja'` and `python3 -c 'import idapro'` independently"
    expected: "Both imports succeed independently without version conflicts"
    why_human: "Requires both proprietary archives (binaryninja.zip and idapro.zip). Detects IDA-06 requirement."
  - test: "Verify IDA Pro license persists across container restarts: place ida.key in host `~/.idapro/`, run container, stop it, restart, check `/home/agent/.idapro/ida.key` still present"
    expected: "License file survives container stop + start cycle via bind mount"
    why_human: "Requires a valid license file. Bind mount wiring is present and verified programmatically but persistence needs a real run."
---

# Phase 1: IDA Pro Backend — Verification Report

**Phase Goal:** Local agents inside the container can use IDA Pro for disassembly and decompilation, with automatic fallback across all three backends
**Verified:** 2026-04-14T07:00:00Z
**Status:** human_needed
**Re-verification:** Yes — after gap closure (Plans 01-01, 01-02, 01-03 all complete)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Building with `INSTALL_IDA_PRO=1` and a valid IDA zip produces a container with IDA Pro installed and no license artifacts in layers | VERIFIED (human needed for full build) | ida-builder stage present (Dockerfile lines 3-21). `COPY --from=ida-builder` copies only `/opt/ida-pro`. No `ida.key` or `ida.hexlic` found in any Dockerfile `COPY`/`ADD`. Conditional install block handles both `.run` installer and pre-installed directory formats. Empty `/opt/ida-pro` created when `INSTALL_IDA_PRO=0` so COPY never fails. |
| 2 | An agent inside the container can invoke IDA Pro MCP tools via SSE transport on a test binary | VERIFIED (human needed for licensed run) | `configure-agent-mcp.sh` line 77 checks `command -v idalib-mcp` (correct command from mrexodia/ida-pro-mcp). Lines 79-80 set `mcp_type="sse"` and `mcp_url="http://localhost:8745/sse"`. Lines 119-129 write SSE format `.mcp.json` when `mcp_type=sse`. ROADMAP SC-2 reads "via SSE transport". |
| 3 | The fallback chain (IDA > BN > Ghidra) activates the correct backend based on what is installed | VERIFIED | IDA detection is first condition (line 77). BN detection is second (line 85). Ghidra detection is third (line 92). Each branch logs the correct message. No-backend else writes empty `{}` and exits cleanly. |
| 4 | All three disassembler APIs coexist without Python import errors or version conflicts | VERIFIED (human needed for runtime) | System-wide pip install pattern used. Only one backend runs at a time by design (no simultaneous import). `idapro` installed from IDA's bundled `idalib/python` directory + activation script run. Python 3.12+ assertion at build time (Dockerfile line 121). |
| 5 | IDA Pro license persists across container restarts via host bind mount | VERIFIED (human needed for live test) | `compose.yaml` line 13: `${IDA_USER_DIR:-/tmp/.idapro-docker}:/home/agent/.idapro`. `run_docker.sh` lines 101-112: seeds both `ida.key` and `ida.hexlic` from host `~/.idapro/`. Agent home has `/home/agent/.idapro` directory (Dockerfile line 148). `IDA_USER_DIR` passed to docker compose environment (run_docker.sh line 195). |

**Score:** 5/5 truths have correct implementation wiring. 4 truths have additional human-only verification items (require actual IDA Pro license/zip).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `Dockerfile` | IDA Pro multi-stage builder, conditional install, mrexodia/ida-pro-mcp package, updated Ghidra condition | VERIFIED | ida-builder stage (lines 3-21), `COPY --from=ida-builder` (line 116), mrexodia GitHub install (line 132), idalib activation script (lines 126-129), updated Ghidra condition checks both BN and IDA (line 67), Python 3.12+ assertion (line 121), `/home/agent/.idapro` dir (line 148) |
| `run_docker.sh` | IDA zip detection, ida-stage temp dir, license seeding (both formats), checksum inclusion | VERIFIED | `IDA_PRO_ZIP` detection (lines 31-42), `IDA_USER_DIR` (line 81), `ida.key` + `ida.hexlic` seeding (lines 101-112), `combined cleanup_stages` (line 139), `ida-stage` build context (line 159), IDA in `DOCKERFILE_SHA` (lines 125-128), `IDA_USER_DIR` in compose env (line 195) |
| `compose.yaml` | IDA Pro user directory volume mount and IDADIR env var | VERIFIED | Volume mount `${IDA_USER_DIR:-/tmp/.idapro-docker}:/home/agent/.idapro` (line 13), `IDADIR=/opt/ida-pro` (line 18) |
| `docker-bin/configure-agent-mcp.sh` | Three-way backend detection (IDA > BN > Ghidra), SSE config for IDA, stdio config for BN/Ghidra | VERIFIED | `idalib-mcp` detection (line 77), `mcp_type="sse"` + `mcp_url` for IDA (lines 79-80), `mcp_type="stdio"` for BN (line 87) and Ghidra (line 94), branched `.mcp.json` writing (lines 119-143), branched Codex config writing (lines 148-179) |
| `.planning/ROADMAP.md` | SC-2 reads "via SSE transport" | VERIFIED | Line 28: "via SSE transport on a test binary". `grep -c "via stdio transport"` returns 0. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `run_docker.sh` | `Dockerfile` | `INSTALL_IDA_PRO` build arg + `ida-stage` named context | WIRED | Lines 158-159: `--build-arg INSTALL_IDA_PRO=...` and `--build-context ida-stage=...` both present |
| `compose.yaml` | `/home/agent/.idapro` | `IDA_USER_DIR` volume mount | WIRED | Line 13: mount expression correct with fallback to `/tmp/.idapro-docker` |
| `configure-agent-mcp.sh` | `/agent/.mcp.json` | Writes SSE MCP server config JSON for IDA Pro | WIRED | Lines 119-129: writes `{"type": "sse", "url": "http://localhost:8745/sse"}` when `mcp_type=sse` |
| `configure-agent-mcp.sh` | Codex `config.toml` | Appends `[mcp_servers.ida_mcp]` with SSE URL | WIRED | Lines 148-154: writes `url = "http://localhost:8745/sse"` + `type = "sse"` when `mcp_type=sse` |
| `Dockerfile` | `mrexodia/ida-pro-mcp` GitHub | pip install of `idalib-mcp` provider | WIRED | Line 132: `pip install ... https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip` |

### Data-Flow Trace (Level 4)

Not applicable — this phase is infrastructure provisioning (Dockerfile, shell scripts) with no dynamic data rendering.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `run_docker.sh` syntax valid | `bash -n run_docker.sh` | exit 0 | PASS |
| `configure-agent-mcp.sh` syntax valid | `bash -n docker-bin/configure-agent-mcp.sh` | exit 0 | PASS |
| No license files in Dockerfile layers | `grep -in "ida.key\|ida.hexlic" Dockerfile` | no matches (exit 1) | PASS |
| `idalib-mcp` is the detection command | `grep "command -v idalib-mcp" docker-bin/configure-agent-mcp.sh` | line 77 found | PASS |
| Old `ida-mcp` detection command removed | `grep -c "command -v ida-mcp" docker-bin/configure-agent-mcp.sh` | 0 | PASS |
| SSE transport config present | `grep '"type": "sse"' docker-bin/configure-agent-mcp.sh` | line 124 found | PASS |
| stdio transport still present for BN/Ghidra | `grep '"type": "stdio"' docker-bin/configure-agent-mcp.sh` | line 135 found | PASS |
| ROADMAP SC-2 says SSE transport | `grep "via SSE transport" .planning/ROADMAP.md` | line 28 found | PASS |
| ROADMAP has no "stdio transport" | `grep -c "via stdio transport" .planning/ROADMAP.md` | 0 | PASS |
| IDADIR env var in compose.yaml | `grep "IDADIR" compose.yaml` | line 18 found | PASS |
| IDA volume mount in compose.yaml | `grep "idapro" compose.yaml` | line 13 found | PASS |
| All 4 commits exist in git | `git log --oneline 30e243d 9159564 1414d8d 3cb19e9` | All 4 found | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| IDA-01 | 01-01 | IDA Pro installs conditionally via `INSTALL_IDA_PRO` build arg, multi-stage build, no license in image layers | SATISFIED | ida-builder stage, `COPY --from=ida-builder`, no license files in any Dockerfile COPY/ADD instruction. Empty dir when `INSTALL_IDA_PRO=0` prevents build failure. |
| IDA-02 | 01-01, 01-03 | IDA Pro headless MCP server (`idalib-mcp`) runs via SSE transport inside container | SATISFIED (code) / NEEDS HUMAN (runtime) | `idalib-mcp` installed via mrexodia/ida-pro-mcp GitHub install. SSE transport config correct. Runtime verification requires valid IDA Pro license. Note: REQUIREMENTS.md text references "stdio transport" which is stale — CONTEXT.md locked decision (SSE) is authoritative. |
| IDA-03 | 01-01 | IDA Pro license persists on host via bind mount to `~/.idapro/` | SATISFIED (wiring) / NEEDS HUMAN (live) | compose.yaml mount, run_docker.sh license seeding for both ida.key and ida.hexlic, `/home/agent/.idapro` directory in image. Persistence requires real run with actual license. |
| IDA-04 | 01-02, 01-03 | `configure-agent-mcp.sh` detects IDA Pro with IDA > BN > Ghidra fallback chain | SATISFIED | Correct `idalib-mcp` detection, priority order enforced, SSE config for IDA, stdio preserved for BN/Ghidra. Note: REQUIREMENTS.md says "BN > IDA > Ghidra" which is stale — CONTEXT.md "IDA > BN > Ghidra" is authoritative. |
| IDA-05 | 01-01 | Hex-Rays decompiler functions available via MCP when user has decompiler license | NEEDS HUMAN | mrexodia/ida-pro-mcp exposes decompilation tools. Auto-detection from license at runtime. Cannot verify without IDA Pro license and Hex-Rays license. |
| IDA-06 | 01-01 | Python environment isolation: no import conflicts between IDA Pro (3.12+), Binary Ninja, Ghidra | NEEDS HUMAN | System-wide install pattern correct; only one backend runs at a time prevents simultaneous import conflicts. Python 3.12+ assertion at build time. Cannot verify runtime without both proprietary archives. |
| INF-03 | 01-01 | Python 3.12+ available in container | SATISFIED | Python version print at build time (Dockerfile line 64). Python 3.12+ assertion in IDA install block (line 121). Kali rolling ships 3.12+ by default. |
| INF-04 | 01-01 | `run_docker.sh` updated with IDA zip detection and `IDA_USER_DIR` env var | SATISFIED | All elements present: `IDA_PRO_ZIP` detection (10 references), `IDA_USER_DIR` creation and passthrough (11 references), ida-stage build context, DOCKERFILE_SHA inclusion, compose env passthrough. |

**Note on stale REQUIREMENTS.md text:** IDA-02 says "stdio transport" and IDA-04 says "BN > IDA > Ghidra" — both are from before the package switch decision. The implementation correctly follows CONTEXT.md locked decisions (SSE transport, IDA > BN > Ghidra priority).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `Dockerfile` | 132 | Unpinned GitHub HEAD install of ida-pro-mcp (`archive/refs/heads/main.zip`) | Warning | Breaking changes upstream will silently break builds. Should pin to tag or commit SHA. Pre-existing from Plan 01 (not introduced by gap closure). |
| `docker-bin/configure-agent-mcp.sh` | 96-99 | Both Ghidra `mcp_args` branches in if/else are identical | Warning | Dead code: when Ghidra uses pyproject.toml layout, `mcp_args` still points to the `.py` file (which may not exist). Pre-existing Ghidra regression, not introduced by this phase. |

Neither anti-pattern blocks the Phase 1 goal. The unpinned HEAD install is a stability risk for future builds but does not prevent current functionality.

### Human Verification Required

#### 1. Verify `idalib-mcp` Command Installed After Build

**Test:** Build container with `INSTALL_IDA_PRO=1` + valid IDA Pro zip. Inside container: `which idalib-mcp && idalib-mcp --help`
**Expected:** Command found on PATH and prints usage. Confirms mrexodia/ida-pro-mcp installs `idalib-mcp` (not `ida-mcp`).
**Why human:** Requires a valid IDA Pro zip file and Docker build execution. Cannot verify command availability without actually installing the package.

#### 2. Run IDA Pro MCP Tools End-to-End

**Test:** In container with IDA installed and licensed: `open_database("/path/to/test.elf")`, then `list_functions()`, then `decompile("main")`
**Expected:** Functions listed, decompiled code returned
**Why human:** Requires valid IDA Pro license and Hex-Rays decompiler license. No automation possible without the licensed environment.

#### 3. Verify Python Import Coexistence

**Test:** Build with `INSTALL_BINARY_NINJA=1 INSTALL_IDA_PRO=1`. In container: `python3 -c "import binaryninja"` (passes), `python3 -c "import idapro"` (passes independently)
**Expected:** Both imports succeed when run independently — no version conflicts
**Why human:** Requires both proprietary archives. Verifies IDA-06 requirement.

#### 4. Verify License Persistence Across Container Restarts

**Test:** Place `ida.key` in host `~/.idapro/`. Run `run_docker.sh`. Stop container. Restart container. Check `/home/agent/.idapro/ida.key` is still present.
**Expected:** License file survives container stop + start cycle
**Why human:** Requires valid license file. Bind mount wiring verified programmatically but end-to-end persistence needs a real run.

### Gaps Summary

No gaps remain. Both blockers from the initial verification were resolved by Plan 03:

- **Blocker 1 resolved:** `configure-agent-mcp.sh` now checks `command -v idalib-mcp` (line 77). The old `command -v ida-mcp` reference is gone (0 matches confirmed).
- **Blocker 2 resolved:** IDA Pro MCP config now writes SSE format (`"type": "sse"`, `"url": "http://localhost:8745/sse"`) via `mcp_type` branching. ROADMAP SC-2 reads "via SSE transport". All automated checks pass.

The 4 remaining human verification items are not gaps — they require a valid IDA Pro license to exercise, which is a hardware/license prerequisite, not a code defect.

---

_Verified: 2026-04-14T07:00:00Z_
_Verifier: Claude (gsd-verifier)_
_Re-verification after Plan 03 gap closure_
