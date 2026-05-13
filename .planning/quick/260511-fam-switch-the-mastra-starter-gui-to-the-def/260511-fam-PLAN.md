---
status: complete
quick_id: 260511-fam
slug: switch-the-mastra-starter-gui-to-the-def
created: 2026-05-11
completed: 2026-05-11
---

# Quick Task 260511-fam: Mastra Studio Dashboard

## Goal

Replace the custom Mastra starter GUI direction with the default Mastra Studio dashboard flow. The starter should run under `mastra dev`, expose MARE tools in Studio, and register an agent so Studio can show tool calls and run progress.

## Source Notes

- Mastra docs say Studio starts with `npm run dev` or `mastra dev` and opens at `http://localhost:4111`.
- Studio shows agents, workflows, tools, MCP servers, and tool call traces/progress.
- Manual install requires `mastra` as a dev dependency and `src/mastra/index.ts` exporting a `Mastra` instance.

## Plan

1. Add Mastra Studio project structure under `templates/mastra/src/mastra/`.
2. Wrap the existing MARE gateway workflow helpers as Mastra tools and register an agent.
3. Replace custom GUI scripts/docs/tests with `mastra dev`/Studio instructions.
4. Install/update npm dependencies, run typecheck/tests, start Studio, and open/capture it.

## Completion Evidence

- Added `mastra` CLI and `npm run dev` / `npm run studio` scripts.
- Added `src/mastra/index.ts`, `MARE Malware Analysis Agent`, Studio tools, and proxied MCP server registration.
- Updated `@mastra/core` to a CLI-compatible 1.32.x release while keeping `@mastra/mcp` pinned to `~1.3.1`.
- Mastra Studio starts at `http://127.0.0.1:4113` in this workspace because another project already uses port `4111`.
- Studio API proof:
  - `GET /api/agents` shows `MARE Malware Analysis Agent` with 24 tools.
  - `GET /api/mcp/mare-toolbox-remote/tools` shows 22 proxied MARE MCP tools, including `mare_run_triage`.
  - `POST /api/agents/mare-agent/tools/mare_status/execute` returns `ok: true`, `toolsAvailable: 22`.
  - `POST /api/agents/mare-agent/tools/mare_triage_sample_path/execute` returns the sample hash, `/agent/status/001-mfc42ul.dll`, and `# Reporting Draft`.
- Chrome opened Mastra Studio and captured `/tmp/mare-mastra-studio-cdp.png`.
