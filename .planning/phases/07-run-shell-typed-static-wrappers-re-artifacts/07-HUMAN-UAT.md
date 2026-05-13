---
status: partial
phase: 07-run-shell-typed-static-wrappers-re-artifacts
source: [07-VERIFICATION.md]
started: 2026-05-13T05:05:00Z
updated: 2026-05-13T05:05:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Container `mare-shell` UID + ACL revocations
expected: `docker compose run --rm gateway-agent id mare-shell` returns `uid=700(mare-shell) gid=700(mare-shell)`; `getfacl /agent/uploads` shows `user:mare-shell:r-x` access AND default ACL
result: [pending]
why_human: Requires docker build + run round-trip; `mare-shell` does not exist on the executor host. `test_run_shell.py::test_setpriv_uid_drop` SKIPS on host with reason "mare-shell user not present".

### 2. D-35 100 MB `/dev/urandom` slow test inside container
expected: `docker compose run --rm gateway-agent uv run pytest -m slow tests/test_run_shell.py::test_run_shell_100mb_urandom` exits 0 in <60s; output cap + capture function correctly with the real setpriv → mare-shell → bash chain
result: [pending]
why_human: Host lacks `setfacl`, so the slow test is SKIPPED in the local environment (`setfacl unavailable on host; container build installs acl package`).

### 3. MCP Resources visible to remote MCP client
expected: After running a `run_shell` or other captured tool, an external MCP client (Claude Code or mastra) issues `resources/list` and receives entries for both the v1.0 depth-1 artifacts AND new depth-2 `<subdir>/<file>` entries with URIs of form `mare://cases/<case>/<subdir>/<file>`
result: [pending]
why_human: Requires live MCP client roundtrip; mastra e2e suite is already known-failing locally (unrelated Node.js module resolution error, see `deferred-items.md`).

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
