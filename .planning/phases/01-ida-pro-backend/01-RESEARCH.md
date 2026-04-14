# Phase 1: IDA Pro Backend - Research

**Researched:** 2026-04-08, **Updated:** 2026-04-14
**Domain:** IDA Pro headless integration, Docker multi-disassembler coexistence, MCP SSE transport
**Confidence:** HIGH

## Summary

Phase 1 adds IDA Pro as a third disassembler backend inside the MARE-MCP-Toolbox container, following the exact provisioning pattern established by Binary Ninja (zip-at-build-time, named build context, host bind mount for license persistence). The `ida-pro-mcp` package (mrexodia) provides a headless MCP server via `idalib-mcp` command that runs an SSE server on a configurable host/port, using idalib (IDA-as-a-library) without requiring the IDA GUI.

The primary technical challenges are: (1) installing IDA Pro from a user-provided archive in a multi-stage Docker build that never leaks license artifacts into intermediate layers, (2) setting up idalib's Python module (installed from IDA's bundled `idalib/python` directory + `py-activate-idalib.py` activation script) correctly within the container, (3) ensuring Python environment isolation between three disassembler backends that all use Python, and (4) extending `configure-agent-mcp.sh` from two-way to three-way backend detection with the priority chain IDA > BN > Ghidra.

**Primary recommendation:** Mirror the Binary Ninja provisioning pattern exactly (zip detection in `run_docker.sh`, named build context `ida-stage`, conditional install via `INSTALL_IDA_PRO` build arg), install `ida-pro-mcp` from GitHub at build time, set `IDADIR` environment variable pointing to the IDA installation directory, and install idalib from IDA's bundled `idalib/python` directory + run the activation script during the Docker build.

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
- **Package**: mrexodia/ida-pro-mcp (NOT jtsylve/ida-mcp). Install from GitHub: `pip install https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip`
- **Headless mode**: `idalib-mcp` command runs an SSE server on configurable host/port
- **Transport**: SSE on localhost for Phase 1 (e.g., `http://localhost:8745/sse`)
- **idalib setup**: Install from IDA's bundled `idalib/python` directory (NOT PyPI `idapro` package). Activate via `py-activate-idalib.py -d /opt/ida-pro`.
- Hex-Rays auto-detect from IDA license at runtime -- no explicit build arg or config needed
- If agent calls decompile without Hex-Rays license, return a clear error message (don't hide the tools)
- All architectures supported -- no artificial limits on what IDA/Hex-Rays can decompile

### Claude's Discretion
- Python environment isolation strategy (venvs, system-wide, etc.) for BN + IDA + Ghidra coexistence
- Multi-stage Docker build details for license security
- How agent manages idalib-mcp lifecycle (start/stop wrapper script or direct invocation)
- idalib-mcp port selection strategy (fixed port vs dynamic)

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
| IDA-02 | IDA Pro headless MCP server (`idalib-mcp` from ida-pro-mcp, mrexodia) runs via SSE transport inside container | `idalib-mcp` command from ida-pro-mcp (mrexodia). Runs headless via idalib, SSE transport on configurable host/port (default `http://localhost:8745/sse`). Requires `IDADIR` env var and idalib activation. |
| IDA-03 | IDA Pro license persists on host via bind mount to `~/.idapro/` | Host `~/.idapro-docker/` bind-mounted to `/home/agent/.idapro/`. License file is `ida.key` or `ida.hexlic`. Auto-seed from `~/.idapro/ida.key`. |
| IDA-04 | `configure-agent-mcp.sh` detects IDA Pro and registers MCP server with fallback chain: IDA > BN > Ghidra | Extend existing two-way detection to three-way. Check for IDA installation (`/opt/ida-pro` dir + `idalib-mcp` command available + idalib activated), then BN, then Ghidra. IDA uses SSE config; BN/Ghidra use stdio. |
| IDA-05 | Hex-Rays decompiler functions available via MCP when user has decompiler license | ida-pro-mcp exposes decompilation tools automatically. If Hex-Rays license is absent, IDA returns an error on decompile calls -- no special handling needed. |
| IDA-06 | Python environment isolation prevents conflicts between IDA Pro (3.12+), Binary Ninja, and Ghidra APIs | System-wide pip install is sufficient -- only one backend runs at a time. The idalib, `binaryninja` package, and `pyghidra` package can coexist as installed Python packages. Conflicts only arise at runtime import, and since only one MCP server runs at a time, this is avoided. |
| INF-03 | Python 3.12+ available in container for ida-pro-mcp compatibility | Kali rolling ships Python 3.12 by default as of 2024.4. Verify at build time with `python3 --version` check. |
| INF-04 | `run_docker.sh` updated with IDA Pro zip detection and `IDA_USER_DIR` env var for license persistence | Mirror Binary Ninja pattern: detect `idapro.zip` in repo root, create `ida-stage` temp dir, pass as named build context. Add `IDA_USER_DIR` env var for compose. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ida-pro-mcp (mrexodia) | latest (GitHub) | Headless IDA Pro MCP server (SSE via idalib-mcp) | 50+ tools, supports both GUI plugin and headless idalib modes. Headless `idalib-mcp` runs an SSE server -- already network-accessible. Active development. |
| idalib (bundled) | from IDA install | Python bindings for idalib | Installed from IDA's `idalib/python` directory. Activated via `py-activate-idalib.py`. Must be first import in scripts. |
| IDA Pro | 9.0+ | Disassembler/decompiler engine | Required by ida-pro-mcp; user provides installer |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uv | latest | Python package manager | Already in container; use for package install for speed |
| pip | system | Fallback package manager | Already in container; alternative to uv |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ida-pro-mcp (mrexodia) | ida-mcp (jtsylve) | jtsylve's version has 190+ tools and stdio transport, but ida-pro-mcp's headless idalib mode with built-in SSE server better fits the remote MCP architecture (no proxy needed). User preference -- locked decision. |
| ida-pro-mcp (mrexodia) | ida-headless-mcp (zboralski) | Less mature, fewer tools (~30 vs 50+), less active development |
| System-wide Python | Virtual environments per backend | Unnecessary complexity since only one backend runs at a time |

**Installation (inside container at build time):**
```bash
# Install idalib Python package from the IDA installation's bundled files
pip install --no-cache-dir --break-system-packages /opt/ida-pro/idalib/python/
# Activate idalib
python3 /opt/ida-pro/py-activate-idalib.py -d /opt/ida-pro
# Install ida-pro-mcp from GitHub (mrexodia)
pip install --no-cache-dir --break-system-packages \
  "https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip"
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

The three-way detection must follow the locked priority: IDA > BN > Ghidra. IDA uses SSE transport; BN and Ghidra use stdio.

```bash
# Detection order: IDA Pro > Binary Ninja > Ghidra
if [ -d "/opt/ida-pro" ] && command -v idalib-mcp >/dev/null 2>&1; then
  # Validate idalib activation
  if ! python3 -c "import ida_idaapi" 2>/dev/null; then
    echo "[mcp] ERROR: IDA Pro is installed but idalib is not activated" >&2
    exit 1
  fi
  mcp_name="ida_pro_mcp"
  mcp_type="sse"
  mcp_url="http://localhost:8745/sse"
  mcp_env="{\"IDADIR\": \"/opt/ida-pro\"}"
  echo "[mcp] Using IDA Pro (highest priority installed)"
elif [ -f /opt/binaryninja/scripts/install_api.py ] && ...; then
  # existing BN detection (stdio)
  echo "[mcp] Using Binary Ninja (IDA Pro not installed)"
elif ...; then
  # existing Ghidra detection (stdio)
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
- **Using ida-mcp from PyPI (jtsylve):** Locked decision -- use ida-pro-mcp from mrexodia via GitHub install.
- **Using idapro from PyPI:** Install idalib from IDA's bundled `idalib/python` directory instead.
- **Running the .run installer as root in the final image:** Use a builder stage so the installer and its temp files never persist.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| IDA MCP server | Custom IDAPython script server | ida-pro-mcp (mrexodia) `idalib-mcp` command | 50+ tools, headless idalib mode, built-in SSE server |
| IDA binary analysis API | Direct idalib calls | ida-pro-mcp's tool surface | Handles database lifecycle, error handling |
| idalib Python setup | Manual .so path manipulation | Bundled `idalib/python` package + `py-activate-idalib.py` | Official Hex-Rays method, handles platform detection |
| MCP SSE transport | Custom SSE server wrapper | idalib-mcp built-in SSE server | Already implements MCP SSE transport correctly |

**Key insight:** ida-pro-mcp's `idalib-mcp` handles all the complexity of idalib setup and provides a ready-to-use SSE server. Do not attempt to use idalib directly or build custom transport wrappers.

## Common Pitfalls

### Pitfall 1: idalib Thread Affinity
**What goes wrong:** idalib requires all IDA API calls happen on the thread that imported the `idapro` module. Violating this causes segfaults.
**Why it happens:** idalib is not thread-safe by design.
**How to avoid:** Use ida-pro-mcp's `idalib-mcp` which handles this internally. Never import `idapro` outside of ida-pro-mcp's managed context.
**Warning signs:** Random segfaults during analysis.

### Pitfall 2: IDADIR Not Set or Wrong Path
**What goes wrong:** idalib-mcp fails to start with "could not locate IDA" error.
**Why it happens:** IDA installed in non-standard location (`/opt/ida-pro`) which isn't in the auto-detection paths.
**How to avoid:** Always set `IDADIR=/opt/ida-pro` in the container environment and in MCP server config.
**Warning signs:** idalib-mcp startup failure, `import ida_idaapi` fails.

### Pitfall 3: License File Location
**What goes wrong:** IDA starts but immediately fails with license error.
**Why it happens:** IDA looks for license in `~/.idapro/` which must be properly bind-mounted.
**How to avoid:** Bind mount `~/.idapro-docker/` to `/home/agent/.idapro/` and seed license file on first run.
**Warning signs:** "No license found" errors in idalib-mcp output.

### Pitfall 4: Python Version Mismatch
**What goes wrong:** idalib-mcp or idalib fails to import with version errors.
**Why it happens:** ida-pro-mcp requires Python 3.12+. If the container's Python is older, installation succeeds but runtime fails.
**How to avoid:** Verify `python3 --version` >= 3.12 during Docker build. Kali rolling (2024.4+) ships 3.12 by default.
**Warning signs:** `SyntaxError` or `ImportError` on idalib-mcp startup.

### Pitfall 5: Ghidra Still Installing When IDA Is Enabled
**What goes wrong:** Both IDA and Ghidra installed, wasting ~500MB+ of image space.
**Why it happens:** Current Dockerfile only checks `INSTALL_BINARY_NINJA` for Ghidra condition.
**How to avoid:** Update Ghidra condition to check both `INSTALL_BINARY_NINJA` and `INSTALL_IDA_PRO`.
**Warning signs:** Larger-than-expected image size, `pyghidra` importable when only IDA was requested.

### Pitfall 6: idalib Not Activated After Install
**What goes wrong:** ida-pro-mcp installs fine but idalib-mcp crashes on startup because idalib is not activated.
**Why it happens:** The idalib Python package needs activation via `py-activate-idalib.py` to know where IDA is installed.
**How to avoid:** Run the activation script during Docker build after installing IDA and the idalib package.
**Warning signs:** `ModuleNotFoundError: No module named 'ida_idaapi'` or similar.

### Pitfall 7: Build Context Checksum Not Including IDA
**What goes wrong:** Changing the IDA zip doesn't trigger a rebuild.
**Why it happens:** `run_docker.sh` checksum calculation doesn't include the IDA zip.
**How to avoid:** Add `INSTALL_IDA_PRO` flag and IDA zip checksum to the `DOCKERFILE_SHA` calculation.
**Warning signs:** Stale image used after updating IDA Pro version.

## Code Examples

### idalib-mcp MCP Configuration (Claude Code .mcp.json — SSE transport)
```json
{
  "mcpServers": {
    "ida_pro_mcp": {
      "type": "sse",
      "url": "http://localhost:8745/sse",
      "env": {
        "IDADIR": "/opt/ida-pro"
      }
    }
  }
}
```
Source: ida-pro-mcp GitHub README (idalib-mcp headless mode)

### idalib-mcp Environment Variables
```bash
# Required: point to IDA installation
IDADIR=/opt/ida-pro
```
Source: ida-pro-mcp GitHub README

### idalib-mcp Basic Usage
```bash
# Start idalib-mcp SSE server (agent starts this per-analysis)
idalib-mcp --host localhost --port 8745

# Or with a target binary
idalib-mcp /path/to/binary --host localhost --port 8745
```
Source: ida-pro-mcp GitHub README

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
| ida-mcp (jtsylve) stdio transport | ida-pro-mcp (mrexodia) idalib-mcp SSE | User decision 2026-04-14 | Built-in SSE server, better fit for remote MCP architecture |
| Manual idapro setup | Bundled `idalib/python` package | October 2025 | Official Hex-Rays distribution, pip-installable from IDA install dir |

**Deprecated/outdated:**
- `idat` / `idat64` headless execution: Replaced by idalib for programmatic use
- ida-mcp (jtsylve): Not selected -- ida-pro-mcp (mrexodia) chosen per user locked decision
- `idapro` PyPI package: Not used -- install from IDA's bundled `idalib/python` directory instead

## Open Questions (RESOLVED)

1. **IDA Pro Archive Format** -- RESOLVED: Plan 01-01 Task 1 supports both `.run` installer and pre-installed directory.
   - What we know: User decided "zip-at-build-time pattern, same as Binary Ninja" with `idapro.zip`
   - What's unclear: Whether the zip contains the `.run` installer or a pre-installed IDA directory. The `.run` installer needs `--mode unattended --prefix /path` to extract. A pre-installed directory just needs to be moved.
   - Recommendation: Support both formats in the Dockerfile. Try to find a `.run` file first; if not found, assume pre-installed directory. Document that either format works.

2. **IDA License File Name** -- RESOLVED: Plan 01-01 Task 2 seeds both `ida.key` and `ida.hexlic`.
   - What we know: CONTEXT.md says "auto-seed from `~/.idapro/ida.key`"
   - What's unclear: IDA 9.x may use `ida.hexlic` instead of `ida.key` for newer license formats
   - Recommendation: Seed both `ida.key` and `ida.hexlic` if either exists on the host. Check for both files.

3. **py-activate-idalib.py Location** -- RESOLVED: Plan 01-01 Task 1 uses `find` to locate dynamically.
   - What we know: Script is somewhere in the IDA installation directory
   - What's unclear: Exact path varies between IDA versions (`/opt/ida-pro/py-activate-idalib.py` or `/opt/ida-pro/idalib/python/py-activate-idalib.py`)
   - Recommendation: Use `find` to locate the script during Docker build, fail with clear error if not found.

4. **idalib Python Package Source** -- RESOLVED: Plan 01-01 Task 1 installs from local `idalib/python/` + runs activation script.
   - What we know: There's both a PyPI `idapro` package (0.0.7) and a local package in `idalib/python/` within the IDA installation
   - What's unclear: Whether the PyPI package is sufficient alone or if the local install + activation script is still needed
   - Recommendation: Install from the local `idalib/python/` directory (more reliable for matching IDA version) AND run the activation script. Do NOT use the PyPI `idapro` package per locked decision.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | bash + docker build verification |
| Config file | none -- test via Docker build + container startup |
| Quick run command | `docker build --build-arg INSTALL_IDA_PRO=1 ...` (build succeeds) |
| Full suite command | Build container + run `idalib-mcp --help` inside + verify `configure-agent-mcp.sh` output |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IDA-01 | IDA installs conditionally, no license in layers | integration | `docker build` with/without `INSTALL_IDA_PRO=1` | No -- post-phase |
| IDA-02 | idalib-mcp runs via SSE | smoke | `docker run ... idalib-mcp --help` | No -- post-phase |
| IDA-03 | License persists via bind mount | manual-only | Requires valid IDA license on host | N/A |
| IDA-04 | Three-way fallback detection (IDA > BN > Ghidra) | unit | `docker run ... configure-agent-mcp.sh && cat /agent/.mcp.json` | No -- post-phase |
| IDA-05 | Hex-Rays decompile available | manual-only | Requires valid Hex-Rays license + test binary | N/A |
| IDA-06 | No Python import conflicts | smoke | `docker run ... python3 -c "import ida_idaapi"` (with IDA); verify no import errors | No -- post-phase |
| INF-03 | Python 3.12+ available | unit | `docker run ... python3 -c "import sys; assert sys.version_info >= (3,12)"` | No -- post-phase |
| INF-04 | run_docker.sh detects IDA zip | unit | Place dummy zip, run detection logic, check env vars | No -- post-phase |

### Sampling Rate
- **Per task commit:** Verify Docker build succeeds with `INSTALL_IDA_PRO=1`
- **Per wave merge:** Full build + container startup + MCP config verification
- **Phase gate:** All automated checks pass, manual license verification documented

## Sources

### Primary (HIGH confidence)
- [ida-pro-mcp GitHub (mrexodia)](https://github.com/mrexodia/ida-pro-mcp) - GUI plugin + headless idalib, SSE transport, 50+ tools
- [idalib docs (Hex-Rays)](https://docs.hex-rays.com/user-guide/idalib) - setup, activation script, Python module installation
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
- Standard stack: HIGH - ida-pro-mcp (mrexodia) verified on GitHub, idalib bundled package verified, installation methods documented
- Architecture: HIGH - existing BN pattern in codebase is well-understood and directly replicable for IDA
- Pitfalls: MEDIUM - idalib activation and license file locations need validation during implementation
- Python isolation: HIGH - only one backend runs at a time, system-wide install is sufficient

**Research date:** 2026-04-08, updated 2026-04-14
**Valid until:** 2026-05-14 (stable -- ida-pro-mcp is actively maintained, patterns are established)
