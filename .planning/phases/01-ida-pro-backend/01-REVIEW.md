---
phase: 01-ida-pro-backend
reviewed: 2026-04-14T12:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - Dockerfile
  - run_docker.sh
  - compose.yaml
  - docker-bin/configure-agent-mcp.sh
findings:
  critical: 0
  warning: 3
  info: 2
  total: 5
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-04-14T12:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the four core infrastructure files: Dockerfile, run_docker.sh, compose.yaml, and docker-bin/configure-agent-mcp.sh. The code is generally well-structured with proper error handling (`set -euo pipefail`), conditional installation logic for multiple disassembler backends, and correct use of Docker build features (multi-stage builds, named build contexts).

Three warnings were found: a copy-paste bug in the Ghidra MCP fallback path that will reference a nonexistent file, an unpinned Git install of ida-pro-mcp in the Dockerfile, and a pipe-to-shell pattern for installing Claude Code. Two informational items were noted regarding minor robustness concerns in the build script.

No critical security issues were found. The compose.yaml correctly uses elevated capabilities only as needed (SYS_PTRACE for debugging), and sensitive files (licenses, credentials) are handled through host-side volume mounts rather than being baked into the image.

## Warnings

### WR-01: Copy-paste bug in Ghidra MCP args -- both branches identical

**File:** `docker-bin/configure-agent-mcp.sh:85-88`
**Issue:** The if/else on lines 85-88 produces the same `mcp_args` value in both branches. The else branch is reached when `ghidra_headless_mcp.py` does not exist but `pyproject.toml` does (line 82 condition). In that case, `mcp_args` still references the nonexistent `ghidra_headless_mcp.py` file, which will cause the MCP server to fail at runtime.
**Fix:**
```bash
if [ -f "${GHIDRA_ROOT}/ghidra_headless_mcp.py" ]; then
  mcp_args="[\"${GHIDRA_ROOT}/ghidra_headless_mcp.py\"]"
else
  mcp_args="[\"-m\", \"ghidra_headless_mcp\"]"
fi
```
The else branch should use module-based invocation or the correct entry point for the pyproject.toml-based package layout. The exact fix depends on how the ghidra-headless-mcp package exposes its entry point when installed from pyproject.toml.

### WR-02: Unpinned ida-pro-mcp install from GitHub HEAD

**File:** `Dockerfile:132`
**Issue:** `pip install ... "https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip"` installs whatever is on the `main` branch at build time. A breaking change upstream could silently break the container build or runtime behavior. This is especially risky because the build cache (hash-based tag on line 131-132 of run_docker.sh) checksums the Dockerfile but not the remote dependency content.
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
    rm -f /tmp/install-claude.sh; \
    ln -sf /home/agent/.local/bin/claude /usr/local/bin/claude; \
    gosu agent env HOME=/home/agent USER=agent LOGNAME=agent claude --version
```
Alternatively, if Claude Code publishes versioned releases, pin to a specific version URL. Acknowledged that this is a common pattern and the risk is low for a local development tool, but it is worth noting for a security-conscious project.

## Info

### IN-01: xargs without --no-run-if-empty in build checksum

**File:** `run_docker.sh:120`
**Issue:** `find ... | sort | xargs sha256sum` will hang if `find` produces no output, because `sha256sum` with no arguments reads from stdin. In practice this is safe because `docker-bin/` always contains at least `configure-agent-mcp.sh`, but the pattern is fragile.
**Fix:**
```bash
find "$SCRIPT_DIR/docker-bin" -type f -print0 | sort -z | xargs -0 -r sha256sum
```
Using `-print0`/`-0` also handles filenames with spaces, and `-r` (GNU xargs) skips execution when input is empty.

### IN-02: Python version check without assertion on minimum

**File:** `Dockerfile:64`
**Issue:** Line 64 prints the Python version but does not enforce a minimum. The actual version assertion happens later on line 121 (inside the IDA Pro conditional block), but only when `INSTALL_IDA_PRO=1`. The standalone check on line 64 is effectively a no-op -- it always passes regardless of the Python version.
**Fix:** Either remove the comment "Verify Python version (IDA Pro requires 3.12+)" on line 63 to avoid implying enforcement, or add an actual check:
```dockerfile
RUN python3 -c "import sys; v=sys.version_info; assert (v.major, v.minor) >= (3, 12), \
    f'IDA Pro requires Python 3.12+, got {v.major}.{v.minor}'; \
    print(f'Python {v.major}.{v.minor}.{v.micro}')"
```
Though note: enforcing 3.12+ unconditionally would break non-IDA builds on older base images. The current conditional check on line 121 is the correct place for enforcement; the comment on line 63 is simply misleading.

---

_Reviewed: 2026-04-14T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
