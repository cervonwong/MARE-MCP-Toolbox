---
status: partial
phase: 11-dynamic-lab-mode-env-gated
source: [11-VERIFICATION.md]
started: 2026-05-20T01:55:00Z
updated: 2026-05-20T01:55:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Live tool-count over MCP
expected: After `./run_docker.sh --remote --dynamic` against the rebuilt container, `tools/list` over MCP returns exactly 61 tools (54 baseline + 7 dynamic). CURRENT_STATE.json marking is explicitly deferred to Phase 12 per D-DYN-CAP-CURRENTSTATE.
result: [pending]

### 2. get_dynamic_capabilities + run_strace end-to-end
expected: Inside the rebuilt Kali container (seccomp=unconfined, SYS_PTRACE), `get_dynamic_capabilities()` returns a populated `DynamicCapabilities` dataclass with `netns_feasible=true`; `run_strace` on a sample produces strace output in `case_dir/dynamic/`.
result: [pending]

### 3. Slow JOBS integration tests inside container
expected: `test_strace_via_jobs_roundtrip` confirms ENETUNREACH (netns isolation); `test_setsid_grandchild_reaped` confirms setsid grandchild is killed; `test_qemu_user_arm_roundtrip` confirms arm ELF executes under qemu-arm-static. All three skip cleanly on host but pass inside container.
result: [pending]

### 4. gdb MI allowlist runtime enforcement
expected: `open_gdb_session` then `gdb_exec` with a blocked command (e.g., `python print(1)`) returns an error dict containing "gdb-MI command refused"; a safe command like `-info-functions` returns MI output. Requires real gdb binary inside container.
result: [pending]

### 5. probe_dynamic_tools.sh READY verdict
expected: `scripts/probe_dynamic_tools.sh` reports READY when run inside the rebuilt container (SYS_PTRACE + seccomp=unconfined + strace/ltrace/qemu-user-static/gdb all installed).
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
