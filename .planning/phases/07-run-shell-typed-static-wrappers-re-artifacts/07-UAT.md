---
status: testing
phase: 07-run-shell-typed-static-wrappers-re-artifacts
source: [07-01-SUMMARY.md, 07-02-SUMMARY.md, 07-03-SUMMARY.md, 07-04-SUMMARY.md, 07-05-SUMMARY.md, 07-06-SUMMARY.md, 07-07-SUMMARY.md, 07-08-SUMMARY.md, 07-HUMAN-UAT.md]
started: 2026-05-15T00:00:00Z
updated: 2026-05-15T00:00:00Z
---

## Current Test

number: 1
name: Cold Start Smoke Test
expected: |
  Kill any running gateway container/service. Rebuild image from scratch (./run_docker.sh or docker compose build --no-cache).
  Container boots without errors. `acl` apt package present (`which setfacl` -> /usr/bin/setfacl).
  `mare-shell` user exists at UID 700 (`id mare-shell` -> uid=700(mare-shell) gid=700(mare-shell)).
  Bearer token file is 0400 root:root (`ls -l /agent/.mcp-gateway-token`).
  MCP gateway starts and `tools/list` returns 39 tools (22 v1.0 + 17 Phase 7).
awaiting: user response

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running gateway container/service. Rebuild image from scratch (./run_docker.sh or docker compose build --no-cache). Container boots without errors. `acl` apt package present (`which setfacl` -> /usr/bin/setfacl). `mare-shell` user exists at UID 700 (`id mare-shell` -> uid=700(mare-shell) gid=700(mare-shell)). Bearer token file is 0400 root:root (`ls -l /agent/.mcp-gateway-token`). MCP gateway starts and `tools/list` returns 39 tools (22 v1.0 + 17 Phase 7).
result: [pending]

### 2. Container mare-shell UID + ACL revocations
expected: `docker compose run --rm gateway-agent id mare-shell` returns `uid=700(mare-shell) gid=700(mare-shell)`; `getfacl /agent/uploads` shows `user:mare-shell:r-x` access AND default ACL inheritance entries; dotdirs `/root/.idapro` `/root/.binaryninja` are mode 0700 (mare-shell cannot read license files).
result: [pending]

### 3. D-35 100 MB /dev/urandom slow test inside container
expected: `docker compose run --rm gateway-agent uv run pytest -m slow tests/test_run_shell.py::test_run_shell_100mb_urandom` exits 0 in <60s; runner chokepoint correctly caps stdout (`stdout_truncated is True`, `stdout_bytes_total >= 100 MB`) under the real setpriv -> mare-shell -> bash chain. Confirms no PIPE-deadlock regression.
result: [pending]

### 4. MCP Resources visible to remote MCP client (depth-2 walk)
expected: From outside the container, an MCP client (Claude Code or mastra) connects to the gateway, runs `init_case` + a captured tool (e.g., `run_xxd` or `run_file`), then `resources/list`. Response includes BOTH v1.0 depth-1 artifacts AND new depth-2 entries with URIs `mare://cases/<case>/<subdir>/<file>` for tool-logs / hex / rop / disassembly subdirs. Hidden files (.gsd_state) are NOT exposed. Files past depth-2 (extracted/sub/deep.bin) are NOT exposed.
result: [pending]

### 5. Collision-check hard-fail at gateway startup
expected: With PINNED_BACKEND set to a backend whose `tool_cache` contains a name that collides with a gateway-native tool (e.g., simulate by registering a fake `decompile` in the backend), the gateway lifespan REFUSES to start: process exits with code 78 (EX_CONFIG); logs include `FATAL:` line with sorted collision name list and backend label; uvicorn does NOT proceed to serve requests.
result: [pending]

### 6. run_shell drops to mare-shell UID and cannot read token
expected: From an MCP client inside the container (or via the gateway), call `run_shell(case_dir=<case>, cmd="id; cat /agent/.mcp-gateway-token; printenv | grep -E 'TOKEN|SECRET'")`. Response shows `uid=700(mare-shell) gid=700(mare-shell)` (NOT root, NOT agent), `cat` of the token file FAILS with permission denied, and env grep shows ZERO secrets (env was rebuilt from `_RUN_SHELL_ALLOWED_KEYS` whitelist).
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps

[none yet]
