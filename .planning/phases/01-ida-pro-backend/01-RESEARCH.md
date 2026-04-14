# Phase 1: IDA Pro Backend - Research

**Researched:** 2026-04-08
**Domain:** IDA Pro headless integration, Docker multi-disassembler coexistence, MCP stdio transport
**Confidence:** HIGH

## Summary

Phase 1 adds IDA Pro as a third disassembler backend inside the MARE-MCP-Toolbox container, following the exact provisioning pattern established by Binary Ninja (zip-at-build-time, named build context, host bind mount for license persistence). The `ida-mcp` package (v2.1.0, jtsylve) provides a headless MCP server over stdio transport with 60+ tools, running on idalib (IDA-as-a-library) without requiring the IDA GUI.

The primary technical challenges are: (1) installing IDA Pro from a user-provided archive in a multi-stage Docker build that never leaks license artifacts into intermediate layers, (2) setting up idalib's Python module (`idapro` from PyPI + `py-activate-idalib.py` activation script) correctly within the container, (3) ensuring Python environment isolation between three disassembler backends that all use Python, and (4) extending `configure-agent-mcp.sh` from two-way to three-way backend detection with the priority chain IDA > BN > Ghidra.

**Primary recommendation:** Mirror the Binary Ninja provisioning pattern exactly (zip detection in `run_docker.sh`, named build context `ida-stage`, conditional install via `INSTALL_IDA_PRO` build arg), install `ida-mcp` via pip at build time, set `IDADIR` environment variable pointing to the IDA installation directory, and install the `idapro` PyPI package + run the activation script during the Docker build.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- All three disassemblers (BN, IDA, Ghidra) can coexist in the same image via independent build args (`INSTALL_BINARY_NINJA`, `INSTALL_IDA_PRO`)
- Ghidra is only installed when neither BN nor IDA is enabled (not always-on fallback)
- Only one disassembler active at a time -- fallback chain picks the highest-priority installed backend
- No simultaneous MCP server registration -- one backend per session
- Priority order: IDA > BN > Ghidra (IDA preferred when installed)
- No manual override via env var -- priority chain only
- Log which backend was selected at container start (e.g., "Using IDA Pro (highest priority installed)")
- If the selected backend fails to start (e.g., license issue), fail with a clear warning -- do NOT silently fall back to the next backend
- Zip-at-build-time pattern, same as Binary Ninja -- place `idapro.zip` in repo root or set `IDA_PRO_ZIP` env var
- `run_docker.sh` detects the zip and passes it as a named build context (`ida-stage`)
- IDA Pro license persisted via host bind mount: `~/.idapro-docker/` -> `/home/agent/.idapro/`
- Auto-seed license from `~/.idapro/ida.key` if available (same pattern as BN's `license.dat` seeding)
- `ida-mcp` installed at Docker build time via pip/uv (PyPI package, not a runtime git clone)
- Hex-Rays auto-detect from IDA license at runtime -- no explicit build arg or config needed
- If agent calls decompile without Hex-Rays license, return a clear error message (don't hide the tools)
- All architectures supported -- no artificial limits on what IDA/Hex-Rays can decompile

### Claude's Discretion
- Python environment isolation strategy (venvs, system-wide, etc.) for BN + IDA + Ghidra coexistence
- Exact ida-mcp installation method (pip vs uv)
- Multi-stage Docker build details for license security
- configure-agent-mcp.sh implementation for three-way detection

### Deferred Ideas (OUT OF SCOPE)
- README.md documentation for IDA Pro setup workflow -- user requested, do after implementation
- User-configurable priority chain via env var (e.g., `DISASM_PRIORITY=ida,bn,ghidra`) -- decided against for now
- Simultaneous multi-backend MCP registration -- decided one-at-a-time for now
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| IDA-01 | IDA Pro installs conditionally via `INSTALL_IDA_PRO` build arg using multi-stage Docker build (license never in image layers) | Multi-stage build pattern with named build context `ida-stage`, parallel to existing `binja-stage` pattern. IDA installer runs in builder stage, only installation directory copied to final image. |
| IDA-02 | IDA Pro headless MCP server (`ida-mcp`) runs via stdio transport inside container | `ida-mcp` v2.1.0 from PyPI, runs headless via idalib, stdio transport. Command: `ida-mcp` or `python3 -m ida_mcp`. Requires `IDADIR` env var and `idapro` package activation. |
| IDA-03 | IDA Pro license persists on host via bind mount to `~/.idapro/` | Host `~/.idapro-docker/` bind-mounted to `/home/agent/.idapro/`. License file is `ida.key` or `ida.hexlic`. Auto-seed from `~/.idapro/ida.key`. |
| IDA-04 | `configure-agent-mcp.sh` detects IDA Pro and registers MCP server with fallback chain: IDA > BN > Ghidra | Extend existing two-way detection to three-way. Check for IDA installation (`IDADIR` set + `ida-mcp` command available), then BN, then Ghidra. |
| IDA-05 | Hex-Rays decompiler functions available via MCP when user has decompiler license | ida-mcp exposes decompilation tools automatically. If Hex-Rays license is absent, IDA returns an error on decompile calls -- no special handling needed. |
| IDA-06 | Python environment isolation prevents conflicts between IDA Pro (3.12+), Binary Ninja, and Ghidra APIs | System-wide pip install is sufficient -- only one backend runs at a time. The `idapro` package, `binaryninja` package, and `pyghidra` package can coexist as installed Python packages. Conflicts only arise at runtime import, and since only one MCP server runs at a time, this is avoided. |
| INF-03 | Python 3.12+ available in container for ida-mcp compatibility | Kali rolling ships Python 3.12 by default as of 2024.4. Verify at build time with `python3 --version` check. |
| INF-04 | `run_docker.sh` updated with IDA Pro zip detection and `IDA_USER_DIR` env var for license persistence | Mirror Binary Ninja pattern: detect `idapro.zip` in repo root, create `ida-stage` temp dir, pass as named build context. Add `IDA_USER_DIR` env var for compose. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ida-mcp | 2.1.0 | Headless IDA Pro MCP server (stdio) | Best-in-class: 60+ tools, multi-binary supervisor/worker model, idalib-based, PyPI-installable, MIT license |
| idapro | 0.0.7 | Python bindings for idalib | Official Hex-Rays package, enables IDA-as-a-library usage without GUI |
| IDA Pro | 9.0+ | Disassembler/decompiler engine | Required by ida-mcp; user provides installer |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uv | latest | Python package manager | Already in container; use for ida-mcp install for speed |
| pip | system | Fallback package manager | Already in container; alternative to uv |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ida-mcp (jtsylve) | ida-headless-mcp (zboralski) | Fewer tools (~30 vs 60+), less active development |
| ida-mcp (jtsylve) | ida-pro-mcp (mrexodia) | Requires IDA GUI running (plugin-based), not headless -- incompatible with Docker |
| System-wide Python | Virtual environments per backend | Unnecessary complexity since only one backend runs at a time |

**Installation (inside container at build time):**
```bash
# Install idapro Python package from the IDA installation
pip install --no-cache-dir --break-system-packages /opt/ida-pro/idalib/python/
# Activate idalib
python3 /opt/ida-pro/py-activate-idalib.py -d /opt/ida-pro
# Install ida-mcp from PyPI
pip install --no-cache-dir --break-system-packages ida-mcp
```

## Architecture Patterns

### IDA Pro Installation in Docker (Multi-Stage Build)

The IDA Pro Linux distribution comes as a `.run` installer file. The user will provide this (or a zip containing it) as `idapro.zip` in the repo root. The Dockerfile must:

1. **Builder stage**: Extract and run the installer in a disposable stage
2. **Final stage**: Copy only the installation directory (no installer, no license artifacts)

```dockerfile
# Builder stage -- extract and install IDA Pro
FROM kalilinux/kali-rolling:latest AS ida-builder
RUN --mount=type=bind,from=ida-stage,target=/tmp/ida-stage \
    set -eux; \
    zipfile="$(find /tmp/ida-stage -maxdepth 1 -name '*.zip' -print -quit)"; \
    tmpdir="$(mktemp -d)"; \
    unzip -q "${zipfile}" -d "${tmpdir}"; \
    installer="$(find "${tmpdir}" -maxdepth 1 -name '*.run' -print -quit)"; \
    if [ -n "${installer}" ]; then \
      chmod +x "${installer}"; \
      "${installer}" --mode unattended --prefix /opt/ida-pro; \
    else \
      # Assume zip contains pre-installed IDA directory
      mv "${tmpdir}"/* /opt/ida-pro/ || mv "${tmpdir}"/ida* /opt/ida-pro/; \
    fi; \
    rm -rf "${tmpdir}"

# Final stage -- copy IDA installation only (no license, no installer)
# In the main FROM block:
COPY --from=ida-builder /opt/ida-pro /opt/ida-pro
```

**Key insight:** The `.run` installer supports `--mode unattended --prefix /path` for non-interactive installation. If the user provides a pre-installed directory zipped up (more likely for Docker workflows), just extract and move.

### IDA Pro Detection in configure-agent-mcp.sh

The three-way detection must follow the locked priority: IDA > BN > Ghidra.

```bash
# Detection order: IDA Pro > Binary Ninja > Ghidra
if [ -d "/opt/ida-pro" ] && command -v ida-mcp >/dev/null 2>&1; then
  mcp_name="ida_mcp"
  mcp_command="ida-mcp"
  mcp_args="[]"
  mcp_env="{\"IDADIR\": \"/opt/ida-pro\"}"
  echo "[mcp] Using IDA Pro (highest priority installed)"
elif [ -f /opt/binaryninja/scripts/install_api.py ] && ...; then
  # existing BN detection
  echo "[mcp] Using Binary Ninja (IDA Pro not installed)"
elif ...; then
  # existing Ghidra detection
  echo "[mcp] Using Ghidra (neither IDA Pro nor Binary Ninja installed)"
fi
```

### Ghidra Conditional Installation Change

Currently Ghidra installs when `INSTALL_BINARY_NINJA != 1`. This must change to: Ghidra installs when neither BN nor IDA is enabled.

```dockerfile
# Install Ghidra only when no commercial disassembler is enabled
RUN if [ "${INSTALL_BINARY_NINJA}" != "1" ] && [ "${INSTALL_IDA_PRO}" != "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends ghidra \
      && rm -rf /var/lib/apt/lists/* \
      && python3 -m pip install --no-cache-dir --break-system-packages pyghidra; \
    fi
```

### run_docker.sh IDA Pro Detection Pattern

Mirror the Binary Ninja pattern exactly:

```bash
# IDA Pro archive: optional for build-time headless install
IDA_PRO_ZIP="${IDA_PRO_ZIP:-}"
if [[ -z "$IDA_PRO_ZIP" && -f "$SCRIPT_DIR/idapro.zip" ]]; then
  IDA_PRO_ZIP="$SCRIPT_DIR/idapro.zip"
fi
INSTALL_IDA_PRO=0
if [[ -n "$IDA_PRO_ZIP" && -f "$IDA_PRO_ZIP" ]]; then
  INSTALL_IDA_PRO=1
  echo "[info] using IDA Pro archive: $IDA_PRO_ZIP"
fi

# IDA Pro user directory persistence
IDA_USER_DIR="${IDA_USER_DIR:-$HOME/.idapro-docker}"
mkdir -p "$IDA_USER_DIR"

# Seed IDA license from host
if [[ ! -f "$IDA_USER_DIR/ida.key" && -f "$HOME/.idapro/ida.key" ]]; then
  cp "$HOME/.idapro/ida.key" "$IDA_USER_DIR/ida.key"
  echo "[info] copied IDA Pro ida.key into $IDA_USER_DIR"
fi
```

### compose.yaml Volume Mount Addition

```yaml
volumes:
  - "${IDA_USER_DIR:-/tmp/.idapro-docker}:/home/agent/.idapro"
```

### Anti-Patterns to Avoid
- **Baking license into Docker layers:** Never copy `ida.key` or `ida.hexlic` into any Docker layer. Use bind mounts only.
- **Silent fallback on failure:** If IDA is selected but fails to start (bad license, missing idalib), do NOT fall back to BN. Fail loudly with a clear error.
- **Runtime git clone of ida-mcp:** Install from PyPI at build time. The MCP repos for BN and Ghidra use git clones -- do NOT follow that pattern for IDA.
- **Running the .run installer as root in the final image:** Use a builder stage so the installer and its temp files never persist.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IDA MCP server | Custom IDAPython script server | ida-mcp 2.1.0 from PyPI | 60+ tools, supervisor/worker architecture, battle-tested |
| IDA binary analysis API | Direct idalib calls | ida-mcp's tool surface | Handles database lifecycle, worker management, error handling |
| idalib Python setup | Manual .so path manipulation | `idapro` PyPI package + `py-activate-idalib.py` | Official Hex-Rays method, handles platform detection |
| MCP stdio transport | Custom stdin/stdout protocol | ida-mcp built-in stdio | Already implements MCP spec correctly |

**Key insight:** ida-mcp handles all the complexity of idalib's threading limitations (all API calls must happen on the thread that imported `idapro`) via its supervisor/worker architecture. Do not attempt to use idalib directly.

## Common Pitfalls

### Pitfall 1: idalib Thread Affinity
**What goes wrong:** idalib requires all IDA API calls happen on the thread that imported the `idapro` module. Violating this causes segfaults.
**Why it happens:** idalib is not thread-safe by design.
**How to avoid:** Use ida-mcp which handles this via subprocess workers. Never import `idapro` outside of ida-mcp's managed context.
**Warning signs:** Random segfaults during analysis.

### Pitfall 2: IDADIR Not Set or Wrong Path
**What goes wrong:** ida-mcp fails to start with "could not locate IDA" error.
**Why it happens:** IDA installed in non-standard location (`/opt/ida-pro`) which isn't in the auto-detection paths.
**How to avoid:** Always set `IDADIR=/opt/ida-pro` in the container environment and in MCP server config.
**Warning signs:** ida-mcp startup failure, `import idapro` fails.

### Pitfall 3: License File Location
**What goes wrong:** IDA starts but immediately fails with license error.
**Why it happens:** IDA looks for license in `~/.idapro/` which must be properly bind-mounted.
**How to avoid:** Bind mount `~/.idapro-docker/` to `/home/agent/.idapro/` and seed license file on first run.
**Warning signs:** "No license found" errors in ida-mcp output.

### Pitfall 4: Python Version Mismatch
**What goes wrong:** `ida-mcp` or `idapro` fails to import with version errors.
**Why it happens:** ida-mcp requires Python 3.12+. If the container's Python is older, installation succeeds but runtime fails.
**How to avoid:** Verify `python3 --version` >= 3.12 during Docker build. Kali rolling (2024.4+) ships 3.12 by default.
**Warning signs:** `SyntaxError` or `ImportError` on ida-mcp startup.

### Pitfall 5: Ghidra Still Installing When IDA Is Enabled
**What goes wrong:** Both IDA and Ghidra installed, wasting ~500MB+ of image space.
**Why it happens:** Current Dockerfile only checks `INSTALL_BINARY_NINJA` for Ghidra condition.
**How to avoid:** Update Ghidra condition to check both `INSTALL_BINARY_NINJA` and `INSTALL_IDA_PRO`.
**Warning signs:** Larger-than-expected image size, `pyghidra` importable when only IDA was requested.

### Pitfall 6: ida-mcp Installation Without idapro Activation
**What goes wrong:** `ida-mcp` installs fine but crashes on startup because idalib is not activated.
**Why it happens:** The `idapro` PyPI package needs activation via `py-activate-idalib.py` to know where IDA is installed.
**How to avoid:** Run the activation script during Docker build after installing IDA and the `idapro` package.
**Warning signs:** `ModuleNotFoundError: No module named 'ida_idaapi'` or similar.

### Pitfall 7: Build Context Checksum Not Including IDA
**What goes wrong:** Changing the IDA zip doesn't trigger a rebuild.
**Why it happens:** `run_docker.sh` checksum calculation doesn't include the IDA zip.
**How to avoid:** Add `INSTALL_IDA_PRO` flag and IDA zip checksum to the `DOCKERFILE_SHA` calculation.
**Warning signs:** Stale image used after updating IDA Pro version.

## Code Examples

### ida-mcp MCP Configuration (Claude Code .mcp.json)
```json
{
  "mcpServers": {
    "ida_mcp": {
      "type": "stdio",
      "command": "ida-mcp",
      "args": [],
      "env": {
        "IDADIR": "/opt/ida-pro"
      }
    }
  }
}
```
Source: ida-mcp GitHub README + PyPI docs

### ida-mcp Environment Variables
```bash
# Required: point to IDA installation
IDADIR=/opt/ida-pro

# Optional: limit concurrent database workers (default: unlimited)
IDA_MCP_MAX_WORKERS=4

# Optional: worker idle timeout in minutes (default: 30)
IDA_MCP_IDLE_TIMEOUT=30

# Optional: enable arbitrary IDAPython script execution
# IDA_MCP_ALLOW_SCRIPTS=1

# Optional: log verbosity (default: WARNING)
IDA_MCP_LOG_LEVEL=INFO
```
Source: ida-mcp GitHub README

### ida-mcp Basic Workflow (what the agent does)
```
1. open_database("/path/to/binary")
2. wait_for_analysis()  -- blocks until IDA auto-analysis completes
3. list_functions()     -- get all function names/addresses
4. decompile("main")   -- Hex-Rays decompilation (requires license)
5. close_database()     -- cleanup
```
Source: ida-mcp GitHub README

### IDA Pro .run Installer Unattended Mode
```bash
chmod +x ida-pro_*.run
./ida-pro_*.run --mode unattended --prefix /opt/ida-pro
```
Source: Hex-Rays blog (Igor's tip of the week #63)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| IDAPython scripts via idat (headless) | idalib (IDA as a library) | IDA Pro 9.0 (2024) | No need for idat binary, direct Python API access |
| ida-mcp 1.x (fewer tools) | ida-mcp 2.1.0 (supervisor/worker, 60+ tools) | March 2026 | Multi-database support, better tool coverage |
| Manual idapro setup | `idapro` PyPI package (0.0.7) | October 2025 | Official Hex-Rays distribution, pip-installable |

**Deprecated/outdated:**
- `idat` / `idat64` headless execution: Replaced by idalib for programmatic use
- ida-mcp 1.x: Superseded by 2.x with supervisor/worker architecture

## Open Questions (RESOLVED)

1. **IDA Pro Archive Format** — RESOLVED: Plan 01-01 Task 1 supports both `.run` installer and pre-installed directory.
   - What we know: User decided "zip-at-build-time pattern, same as Binary Ninja" with `idapro.zip`
   - What's unclear: Whether the zip contains the `.run` installer or a pre-installed IDA directory. The `.run` installer needs `--mode unattended --prefix /path` to extract. A pre-installed directory just needs to be moved.
   - Recommendation: Support both formats in the Dockerfile. Try to find a `.run` file first; if not found, assume pre-installed directory. Document that either format works.

2. **IDA License File Name** — RESOLVED: Plan 01-01 Task 2 seeds both `ida.key` and `ida.hexlic`.
   - What we know: CONTEXT.md says "auto-seed from `~/.idapro/ida.key`"
   - What's unclear: IDA 9.x may use `ida.hexlic` instead of `ida.key` for newer license formats
   - Recommendation: Seed both `ida.key` and `ida.hexlic` if either exists on the host. Check for both files.

3. **py-activate-idalib.py Location** — RESOLVED: Plan 01-01 Task 1 uses `find` to locate dynamically.
   - What we know: Script is somewhere in the IDA installation directory
   - What's unclear: Exact path varies between IDA versions (`/opt/ida-pro/py-activate-idalib.py` or `/opt/ida-pro/idalib/python/py-activate-idalib.py`)
   - Recommendation: Use `find` to locate the script during Docker build, fail with clear error if not found.

4. **idapro PyPI Package vs IDA's Bundled Python Package** — RESOLVED: Plan 01-01 Task 1 installs from local `idalib/python/` + runs activation script.
   - What we know: There's both a PyPI `idapro` package (0.0.7) and a local package in `idalib/python/` within the IDA installation
   - What's unclear: Whether the PyPI package is sufficient alone or if the local install + activation script is still needed
   - Recommendation: Install from the local `idalib/python/` directory (more reliable for matching IDA version) AND run the activation script. The PyPI package may be a shim that still needs activation.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | bash + docker build verification |
| Config file | none -- test via Docker build + container startup |
| Quick run command | `docker build --build-arg INSTALL_IDA_PRO=1 ...` (build succeeds) |
| Full suite command | Build container + run `ida-mcp --help` inside + verify `configure-agent-mcp.sh` output |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IDA-01 | IDA installs conditionally, no license in layers | integration | `docker build` with/without `INSTALL_IDA_PRO=1` | No -- Wave 0 |
| IDA-02 | ida-mcp runs via stdio | smoke | `docker run ... ida-mcp --help` | No -- Wave 0 |
| IDA-03 | License persists via bind mount | manual-only | Requires valid IDA license on host | N/A |
| IDA-04 | Three-way fallback detection | unit | `docker run ... configure-agent-mcp.sh && cat /agent/.mcp.json` | No -- Wave 0 |
| IDA-05 | Hex-Rays decompile available | manual-only | Requires valid Hex-Rays license + test binary | N/A |
| IDA-06 | No Python import conflicts | smoke | `docker run ... python3 -c "import ida_mcp"` (with IDA); verify no import errors | No -- Wave 0 |
| INF-03 | Python 3.12+ available | unit | `docker run ... python3 -c "import sys; assert sys.version_info >= (3,12)"` | No -- Wave 0 |
| INF-04 | run_docker.sh detects IDA zip | unit | Place dummy zip, run detection logic, check env vars | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** Verify Docker build succeeds with `INSTALL_IDA_PRO=1`
- **Per wave merge:** Full build + container startup + MCP config verification
- **Phase gate:** All automated checks pass, manual license verification documented

### Wave 0 Gaps
- [ ] Test script for `configure-agent-mcp.sh` three-way detection (no IDA license needed -- just checks detection logic)
- [ ] Test script for `run_docker.sh` IDA zip detection (mock zip file)
- [ ] Docker build verification script (build with `INSTALL_IDA_PRO=0` and `INSTALL_IDA_PRO=1`)

## Sources

### Primary (HIGH confidence)
- [ida-mcp PyPI](https://pypi.org/project/ida-mcp/) - v2.1.0, April 2026, installation and requirements
- [ida-mcp GitHub (jtsylve)](https://github.com/jtsylve/ida-mcp) - README, usage, environment variables, tool count
- [ida-mcp 2.0 announcement](https://jtsylve.blog/post/2026/03/25/Announcing-ida-mcp-2) - supervisor/worker architecture, technical details
- [idapro PyPI](https://pypi.org/project/idapro/) - v0.0.7, official Hex-Rays Python package
- [idalib docs](https://docs.hex-rays.com/user-guide/idalib) - setup, activation script, Python module installation
- [IDA installer CLI options](https://hex-rays.com/blog/igors-tip-of-the-week-63-ida-installer-command-line-options) - unattended mode, prefix option

### Secondary (MEDIUM confidence)
- [Kali Linux 2024.4 release](https://www.kali.org/blog/kali-linux-2024-4-release/) - Python 3.12 default in Kali rolling
- [Install IDA docs](https://docs.hex-rays.com/getting-started/install-ida) - Linux installation procedures
- [HCLI install docs](https://hcli.docs.hex-rays.com/user-guide/installing-ida/) - installer details

### Tertiary (LOW confidence)
- IDA Pro directory structure details (based on installer conventions, not directly verified in a container)
- `py-activate-idalib.py` exact location within IDA 9.x installations (varies by version)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - ida-mcp v2.1.0 verified on PyPI, idapro package verified, installation methods documented
- Architecture: HIGH - existing BN pattern in codebase is well-understood and directly replicable for IDA
- Pitfalls: MEDIUM - idalib activation and license file locations need validation during implementation
- Python isolation: HIGH - only one backend runs at a time, system-wide install is sufficient

**Research date:** 2026-04-08
**Valid until:** 2026-05-08 (stable -- ida-mcp 2.1.0 is recent, patterns are established)
