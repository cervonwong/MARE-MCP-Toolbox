---
status: partial
phase: 08-session-scoped-r2
source: [08-VERIFICATION.md]
started: 2026-05-18T10:18:43Z
updated: 2026-05-18T10:18:43Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Container r2-gated test-suite run
expected: Inside the Kali container, `cd mcp-gateway && pytest tests/test_sessions.py tests/test_r2_sessions.py -x` flips the 15 r2-gated SKIPs into PASSes. Covers SC-1 (aaa/aflj persists), SC-2 (result-shape + json paths), SC-3 (close-idempotent, list-fd_count), SC-4 (reaper, cap, lifespan teardown), SC-5 (lockdown-init, refusal matrix), Pitfall 6 (hung cmd), Pitfall 18 (cancel within 200 ms), D-12 per-command-log shape, D-13 transcript captures.
result: [pending]

### 2. Lifespan teardown smoke test (no zombie r2 processes)
expected: Inside the Kali container, open 2 r2 sessions via the MCP surface, send SIGTERM to the gateway process, then `pgrep -a r2` returns no rows (and no defunct entries in `ps -ef | grep r2`). Confirms SC-4 lifespan-kills-all and the `os.killpg(pgid, SIGKILL)` reaper path at shutdown.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
