# mcp-gateway

MARE-MCP-Toolbox gateway: a curated MCP tool surface exposed over Streamable HTTP.

Bridges an in-container disassembler backend (IDA Pro, Binary Ninja, or Ghidra —
auto-detected via priority chain) to external MCP clients (Claude Code host,
mastra.ai, etc.) with bearer-token auth and Origin validation.

## Install

```bash
pip install -e mcp-gateway/
```

## Run

```bash
mcp-gateway --host 127.0.0.1 --port 8080
```

## Environment variables

- `MCP_GATEWAY_TOKEN` — bearer token (if unset, a 43-char URL-safe token is generated and logged)
- `MCP_GATEWAY_TOKEN_FILE` — path to write the token (default `/agent/.mcp-gateway-token`, mode 0600)
- `MCP_GATEWAY_HOST` — bind host (default `127.0.0.1`)
- `MCP_GATEWAY_PORT` — bind port (default `8080`)
- `MCP_GATEWAY_MAX_UPLOAD_MB` — max upload size in MB (enforced by Plan 04)
- `MCP_GATEWAY_QUIET` — set to `1` to suppress the `[gateway] Bearer token: ...` log line

## Auth

All requests to `/mcp*` and `/upload` require:

    Authorization: Bearer <token>

`/healthz` is intentionally open for health checks.
