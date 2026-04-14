---
phase: 01-ida-pro-backend
reviewed: 2026-04-14T14:30:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - Dockerfile
  - run_docker.sh
  - compose.yaml
  - docker-bin/configure-agent-mcp.sh
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-04-14T14:30:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the four core infrastructure files: Dockerfile, run_docker.sh, compose.yaml, and docker-bin/configure-agent-mcp.sh. The code is generally well-structured with proper error handling (`set -euo pipefail`), conditional installation logic for multiple disassembler backends, and correct use of Docker build features (multi-stage builds, named build contexts).

One critical issue was found: the IDA Pro MCP backend is configured as an SSE client pointing to `localhost:8745`, but nothing in the entrypoint or configure script actually starts the `idalib-mcp` server process. The MCP client will connect to a server that is not running, making the IDA Pro backend non-functional at runtime.

Three warnings were found: a copy-paste bug in the Ghidra MCP fallback path, an unpinned Git install of ida-pro-mcp, and a pipe-to-shell pattern for Claude Code installation. Two informational items address minor robustness concerns.

No other security issues were found. The compose.yaml correctly limits elevated capabilities to what is needed (SYS_PTRACE for debugging), and sensitive files (licenses, credentials) are handled through host-side volume mounts rather than being baked into the image.

## Critical Issues

### CR-01: idalib-mcp SSE server is never started -- IDA Pro backend is non-functional

**File:** `docker-bin/configure-agent-mcp.sh:77-83`
**Issue:** When IDA Pro is detected, the script writes an MCP client config with `"type": "sse"` and `"url": "http://localhost:8745/sse"` (lines 119-129). However, neither the configure script nor the container entrypoint (`agent-entrypoint.sh` in the Dockerfile, lines 174-222) launches the `idalib-mcp` SSE server as a background process. The MCP client (Claude Code or Codex) will attempt to connect to a server that is not listening, and the IDA Pro backend will be completely non-functional.

The Binary Ninja and Ghidra backends use `"type": "stdio"` where the MCP client spawns the server process directly. The IDA Pro backend uses `"type": "sse"` which requires a separately running server, but no code starts it.

**Fix:** Start `idalib-mcp` as a background process before the MCP client config is consumed. Add to the entrypoint script (after `configure-agent-mcp.sh` runs) or to `configure-agent-mcp.sh` itself:
```bash
# In agent-entrypoint.sh, after configure-agent-mcp.sh:
if command -v idalib-mcp >/dev/null 2>&1 && [ -d "/opt/ida-pro" ] && [ "$(ls -A /opt/ida-pro 2>/dev/null)" ]; then
  echo "[mcp] starting idalib-mcp SSE server on port 8745"
  gosu "${AGENT_USER}" idalib-mcp --port 8745 &
  # Give the server a moment to bind
  sleep 1
fi
```
Alternatively, consider whether `idalib-mcp` can be used in stdio mode (like the other backends) to avoid needing a background process and the associated lifecycle management.

## Warnings

### WR-01: Copy-paste bug in Ghidra MCP args -- both branches produce identical value

**File:** `docker-bin/configure-agent-mcp.sh:96-99`
**Issue:** The if/else on lines 96-99 produces the same `mcp_args` value in both branches. The else branch is reached when `ghidra_headless_mcp.py` does not exist but `pyproject.toml` and the `ghidra_headless_mcp/` package directory do (line 92 condition). In that case, `mcp_args` still references the nonexistent `ghidra_headless_mcp.py` file, which will cause the MCP server to fail at runtime.
**Fix:**
```bash
if [ -f "${GHIDRA_ROOT}/ghidra_headless_mcp.py" ]; then
  mcp_args="[\"${GHIDRA_ROOT}/ghidra_headless_mcp.py\"]"
else
  mcp_args="[\"-m\", \"ghidra_headless_mcp\"]"
fi
```
The else branch should use module-based invocation (`python3 -m ghidra_headless_mcp`) or the correct entry point for the pyproject.toml-based package layout. The exact fix depends on how the ghidra-headless-mcp package exposes its entry point.

### WR-02: Unpinned ida-pro-mcp install from GitHub HEAD

**File:** `Dockerfile:132`
**Issue:** `pip install ... "https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip"` installs whatever is on the `main` branch at build time. A breaking change upstream could silently break the container build or runtime behavior. This is especially risky because the build cache (hash-based tag in run_docker.sh) checksums the Dockerfile content but not remote dependency content, so a cached image may differ from a fresh build.
**Fix:**
```dockerfile
pip install --no-cache-dir --break-system-packages \
  "https://github.com/mrexodia/ida-pro-mcp/archive/refs/tags/v1.0.0.zip"
```
Pin to a specific release tag or commit SHA. If no stable release exists yet, pin to a commit hash:
```dockerfile
pip install --no-cache-dir --break-system-packages \
  "https://github.com/mrexodia/ida-pro-mcp/archive/abc1234def5678.zip"
```

### WR-03: Piping curl output to bash for Claude Code install

**File:** `Dockerfile:161`
**Issue:** `curl -fsSL https://claude.ai/install.sh | bash` executes arbitrary remote code at build time. If the install script URL is compromised or serves different content, the container image is compromised. While `curl -f` fails on HTTP errors, it does not verify content integrity.
**Fix:** Download the script first, verify its checksum, then execute:
```dockerfile
RUN set -eux; \
    curl -fsSL https://claude.ai/install.sh -o /tmp/install-claude.sh; \
    echo "<expected_sha256>  /tmp/install-claude.sh" | sha256sum -c -; \
    chmod +x /tmp/install-claude.sh; \
    gosu agent env HOME=/home/agent USER=agent LOGNAME=agent /tmp/install-claude.sh; \
    rm -f /tmp/install-claude.sh
```
Alternatively, if Claude Code publishes versioned releases, pin to a specific version URL. Acknowledged that this is a common pattern and the risk is lower for a local development tool, but worth noting for a security-conscious project.

## Info

### IN-01: xargs without --no-run-if-empty in build checksum

**File:** `run_docker.sh:120`
**Issue:** `find ... | sort | xargs sha256sum` will hang if `find` produces no output, because `sha256sum` with no arguments reads from stdin. In practice this is safe because `docker-bin/` always contains at least `configure-agent-mcp.sh`, but the pattern is fragile if the directory is ever emptied.
**Fix:**
```bash
find "$SCRIPT_DIR/docker-bin" -type f -print0 | sort -z | xargs -0 -r sha256sum
```
Using `-print0`/`-0` also handles filenames with spaces, and `-r` (GNU xargs) skips execution when input is empty.

### IN-02: Misleading comment on Python version check

**File:** `Dockerfile:63-64`
**Issue:** Line 63 comments "Verify Python version (IDA Pro requires 3.12+)" but line 64 only prints the version without enforcing a minimum. The actual version assertion happens on line 121 inside the `INSTALL_IDA_PRO=1` conditional block. The standalone check on line 64 always passes regardless of Python version, making the comment misleading.
**Fix:** Either update the comment to match reality:
```dockerfile
# Print Python version for build log
RUN python3 -c "import sys; v=sys.version_info; print(f'Python {v.major}.{v.minor}.{v.micro}')"
```
Or remove the standalone check entirely, since the conditional check on line 121 is the correct enforcement point.

---

_Reviewed: 2026-04-14T14:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
