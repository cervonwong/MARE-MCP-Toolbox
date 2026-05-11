---
status: complete
quick_id: 260511-cwf
slug: fix-remote-mcp-security-defaults-localho
completed: 2026-05-11
---

# Quick Task 260511-cwf: Fix Remote MCP Security Defaults - Summary

## Completed

- Implementation commit: `f556fda`
- Changed remote-mode host publishing defaults from all interfaces to localhost.
- Updated README guidance so `MCP_GATEWAY_HOST_BIND=0.0.0.0` is documented as explicit LAN exposure.
- Replaced prefix-based Origin validation with parsed URL host checks for exact loopback hosts.
- Added shared `case_dir` resolution that rejects paths outside the configured status root.
- Applied `case_dir` validation before artifact scripts, workflow scripts, and artifact/report reads.

## Verification

- `uv run pytest tests/test_auth.py tests/test_artifact_tools.py tests/test_workflow_tools.py tests/test_print_config.py tests/test_readme_structure.py` passed: 44 passed.
- `uv run pytest` ran: 156 passed, 10 skipped, 2 failed. The failures are unrelated existing template hygiene checks under `templates/mastra/node_modules`.
- `git diff --check` passed.

## Notes

- Deferred Ghidra fallback layout handling and IDA MCP pinning per the selected scope.
- Existing unrelated worktree changes were preserved.
