---
status: partial
phase: 10-extraction-tier
source: [10-VERIFICATION.md]
started: 2026-05-19T06:57:19Z
updated: 2026-05-19T06:57:19Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. End-to-end recursive triage via Claude Code MCP client
expected: After image rebuild + gateway start, an external MCP client can call run_binwalk(mode='extract') on a firmware fixture, then list_extracted_files on the case, then promote_extracted_sample on a carved child, then run analysis tools (run_strings, run_file, etc.) on the resulting first-class case dir. Promotion produces a case dir under STATUS_ROOT.
result: [pending]

### 2. Archive-bomb cap aborts mid-extraction in a live container
expected: With MCP_GATEWAY_MAX_EXTRACT_MB=64 set, running extraction on a hand-crafted zip-bomb causes the monitor to write .MARE_EXTRACT_CAP_EXCEEDED marker, flip meta status=cap_exceeded, and cancel the job within one EXTRACT_MONITOR_INTERVAL_S poll.
result: [pending]

### 3. Probe script in-container output confirms binwalk3 / unblob / upx version + flag shapes
expected: Running `bash /agent/scripts/probe_extraction_tools.sh` after the next `./run_docker.sh` rebuild prints binwalk3 version (resolving Assumption A1), confirms --depth flag is absent in binwalk3 (Assumption A2), and shows unblob + upx versions. `apt-cache policy binwalk3` succeeds.
result: [pending]

### 4. Three slow-integration tests pass in-container
expected: `pytest tests/extraction/ -m slow` in the Kali container with binwalk3/unblob/upx on PATH — test_extract_mode_dispatches_job (binwalk), test_report_json_parsed (unblob), test_unpack_writes_output (upx) all PASS.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
