# MARE-MCP-Toolbox — Mastra.ai Starter

A runnable [@mastra/mcp](https://www.npmjs.com/package/@mastra/mcp) client that
exercises the full triage happy path against a running MARE-MCP-Toolbox gateway.
It includes both the original CLI flow and a Mastra Studio project so you can
use the default Mastra dashboard.

## Prerequisites

- Node.js 20+ (`node --version`)
- A running gateway: open Docker Desktop first, or make sure Docker Engine is
  running, then from the repo root run `./run_docker.sh --remote`
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
Report excerpt: # Reporting Draft ...
```

## Mastra Studio

Start Mastra Studio:

```bash
npm run dev
```

Then open:

```text
http://127.0.0.1:4111
```

Studio uses the same `MARE_GATEWAY_TOKEN` and `MARE_GATEWAY_URL` values as the
CLI. In Studio:

- Open **Tools** and run `mare_status` to verify the gateway and list toolbox tools.
- Run `mare_triage_sample_path` with `../../workspace/examples/samples/mfc42ul.dll`
  to exercise upload, `run_triage`, and `get_artifact`.
- Open **Agents**, select `MARE Malware Analysis Agent`, and ask it to run the
  bundled sample. Studio shows each tool call and the run progress while the
  agent works.
- Open **MCP Servers** to inspect the proxied `MARE Toolbox Remote Gateway`
  tool surface.

If port `4111` is already in use, set `MARE_STUDIO_PORT` in `.env` and open
that port instead.

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
const toolsets = await mcp.listToolsets();
const tools = toolsets.mare;          // tools["run_triage"], etc.
```

## What the starter does

1. Connects to the gateway via Streamable HTTP with bearer auth.
2. Uploads a sample binary to `/upload` (returns sha256).
3. Calls `run_triage` with the sha256.
4. Reads the resulting `10_reporting_draft.md` via `get_artifact`.
5. Registers Mastra Studio tools, an agent, and a proxied MCP server under
   `src/mastra/`.

Tool availability and behavior are documented in
[`../../mcp-gateway/README.md`](../../mcp-gateway/README.md): the Mastra helper
tools are `mare_status` and `mare_triage_sample_path`, while the proxied gateway
MCP tools include deterministic script wrappers plus the active backend's
native MCP tools. When IDA is active, that includes the full `mrexodia/ida-pro-mcp`
tool surface reported by the backend.

## Gotchas

- **Token rotates per `--remote` start.** If you get 401, run
  `./run_docker.sh --print-config` to see the current token.
- **`@mastra/mcp` is pinned to `~1.3.x`** (project policy — see `CLAUDE.md`).
  Don't bump to caret-range without updating the test matrix.
- **Use `MCPClient` from `@mastra/mcp`, not older combined client patterns** —
  `MCPClient` is the current API used by this starter.
- **Agent runs need a model provider key.** The default `MARE_AGENT_MODEL` is
  `openai/gpt-4o-mini`, so set `OPENAI_API_KEY` before chatting with the agent
  in Studio. The Tools tab can still run `mare_status` and `mare_triage_sample_path`
  without a model key.
- **Do not add any npm MCP proxy/bridge package** — several have known CVEs (command injection).
  The gateway's native `type: "http"` Streamable HTTP transport replaces them.
