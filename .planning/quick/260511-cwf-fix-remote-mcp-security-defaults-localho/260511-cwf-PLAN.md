---
status: in_progress
quick_id: 260511-cwf
slug: fix-remote-mcp-security-defaults-localho
created: 2026-05-11
---

# Quick Task 260511-cwf: Fix Remote MCP Security Defaults

## Goal

Reduce remote MCP exposure by making localhost publishing the default, validating browser origins by exact parsed host, and ensuring gateway case-directory tools cannot operate outside `/agent/status`.

## Tasks

1. Update host bind defaults and documentation.
   - Files: `run_docker.sh`, `compose.yaml`, `README.md`
   - Action: default `MCP_GATEWAY_HOST_BIND` to `127.0.0.1`; make `0.0.0.0` an explicit opt-in in docs and warnings.
   - Verify: inspect affected lines and run relevant print-config/readme tests if available.

2. Harden Origin validation.
   - Files: `mcp-gateway/src/mcp_gateway/auth.py`, `mcp-gateway/tests/test_auth.py`
   - Action: parse Origin with `urlsplit`; allow only exact loopback hosts and reject malformed or prefix-bypass origins.
   - Verify: add tests for `localhost.evil.com`, malformed origins, and allowed localhost variants.

3. Constrain case_dir to `/agent/status`.
   - Files: `mcp-gateway/src/mcp_gateway/tools/artifacts.py`, `mcp-gateway/src/mcp_gateway/tools/workflows.py`, related tests
   - Action: normalize caller-provided case dirs through a shared helper before passing to scripts or reading artifacts.
   - Verify: add unit tests rejecting arbitrary directories and preserving valid `/agent/status/...` argv values.
