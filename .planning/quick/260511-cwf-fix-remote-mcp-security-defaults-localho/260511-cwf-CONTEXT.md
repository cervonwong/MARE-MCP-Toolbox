# Quick Task 260511-cwf: Fix remote MCP security defaults - Context

**Gathered:** 2026-05-11
**Status:** Ready for planning

<domain>
## Task Boundary

Fix the selected security batch for the remote MCP gateway:

- Default host port publishing to localhost instead of all interfaces.
- Replace prefix-based Origin validation with parsed, exact host validation.
- Constrain caller-provided `case_dir` values to case directories under `/agent/status`.

</domain>

<decisions>
## Implementation Decisions

### Scope
- User selected option 2: fix the three security-facing issues together.
- Defer Ghidra fallback layout and IDA install pinning to later tasks.

### Exposure Default
- Preserve in-container `MCP_GATEWAY_HOST=0.0.0.0` for Docker port publishing.
- Change host-side `MCP_GATEWAY_HOST_BIND` default to `127.0.0.1`.
- Document `MCP_GATEWAY_HOST_BIND=0.0.0.0` as explicit LAN exposure opt-in.

### Request Validation
- Parse Origin values as URLs and compare exact hostnames, not string prefixes.
- Allow missing Origin and literal `null` for non-browser MCP clients.
- Accept localhost loopback origins only.

### Case Directory Boundary
- Accept only resolved directories under `/agent/status`.
- Reuse the constraint for atomic artifact tools, workflow tools, and artifact reads.

</decisions>

<specifics>
## Specific Ideas

The reported findings referenced:

- `run_docker.sh` remote default for `MCP_GATEWAY_HOST_BIND`
- `compose.yaml` port default
- `README.md` security notes
- `mcp-gateway/src/mcp_gateway/auth.py`
- `mcp-gateway/src/mcp_gateway/tools/artifacts.py`
- `mcp-gateway/src/mcp_gateway/tools/workflows.py`

</specifics>

<canonical_refs>
## Canonical References

- `CLAUDE.md` project context: remote MCP exposure is security-sensitive because the container runs with `SYS_PTRACE` and `seccomp=unconfined`.
</canonical_refs>
