# MARE-MCP-Toolbox — Mastra.ai Starter

A runnable [@mastra/mcp](https://www.npmjs.com/package/@mastra/mcp) client that
exercises the full triage happy path against a running MARE-MCP-Toolbox gateway.

## Prerequisites

- Node.js 20+ (`node --version`)
- A running gateway: from the repo root, run `./run_docker.sh --remote`
- Your bearer token: `cat workspace/.mcp-gateway-token` (or copy it from the
  `--remote` ready-block printed at startup)

## Quick start

```bash
cp .env.example .env
# Edit .env and paste your token into MARE_GATEWAY_TOKEN.

npm install
npm start ../../workspace/examples/samples/mfc42ul.dll
```

You should see:

```
Tools available: <N>
Uploaded: <sha256>
Triage result: { ... }
Report excerpt: # Report ...
```

## Drop-in snippet (existing mastra project)

If you already have a mastra project, paste this into your code instead of
cloning the whole template. Set `MARE_GATEWAY_TOKEN` and `MARE_GATEWAY_URL` in
your environment.

```typescript
import { MCPClient } from "@mastra/mcp";

const mcp = new MCPClient({
  servers: {
    mare: {
      url: new URL(process.env.MARE_GATEWAY_URL ?? "http://localhost:8080/mcp"),
      requestInit: {
        headers: { Authorization: `Bearer ${process.env.MARE_GATEWAY_TOKEN}` },
      },
    },
  },
});
const tools = await mcp.getTools();   // tools["mare_run_triage"], etc.
```

## What the starter does

1. Connects to the gateway via Streamable HTTP with bearer auth.
2. Uploads a sample binary to `/upload` (returns sha256).
3. Calls `mare_run_triage` with the sha256.
4. Reads the resulting `10_reporting_draft.md` via `mare_get_artifact`.

## Gotchas

- **Token rotates per `--remote` start.** If you get 401, run
  `./run_docker.sh --print-config` to see the current token.
- **`@mastra/mcp` is pinned to `~1.3.x`** (project policy — see `CLAUDE.md`).
  Don't bump to caret-range without updating the test matrix.
- **Use `MCPClient`, not the legacy `Mastra` + `MCPClient` combined class** — the
  old combined class was deprecated; `MCPClient` from `@mastra/mcp` is the current API.
- **Do not add any npm MCP proxy/bridge package** — several have known CVEs (command injection).
  The gateway's native `type: "http"` Streamable HTTP transport replaces them.
