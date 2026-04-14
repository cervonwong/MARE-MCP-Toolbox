---
status: partial
phase: 01-ida-pro-backend
source: [01-VERIFICATION.md]
started: 2026-04-14T14:35:00Z
updated: 2026-04-14T14:35:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Verify idalib-mcp command after build
expected: `which idalib-mcp` returns a valid path inside a container built with `INSTALL_IDA_PRO=1` and a valid IDA zip
result: [pending]

### 2. Run IDA Pro MCP tools end-to-end
expected: `open_database`, `list_functions`, `decompile("main")` succeed on a test binary via SSE transport at localhost:8745
result: [pending]

### 3. Python import coexistence (IDA + Binary Ninja)
expected: Build with both `INSTALL_BINARY_NINJA=1` and `INSTALL_IDA_PRO=1`, verify independent Python imports succeed without conflicts
result: [pending]

### 4. License persistence across restarts
expected: Bind mount keeps `ida.key`/`ida.hexlic` alive after container stop/start
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
