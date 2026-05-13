---
status: complete
quick_id: 260511-fam
slug: switch-the-mastra-starter-gui-to-the-def
completed: 2026-05-11
---

# Quick Task 260511-fam Summary

## Result

`templates/mastra/` now opens the default Mastra Studio dashboard instead of a custom GUI page.

## Changes

- Added the official `mastra` CLI dev dependency and `npm run dev` / `npm run studio`.
- Added a Mastra app under `templates/mastra/src/mastra/`.
- Registered:
  - `MARE Malware Analysis Agent`
  - `mare_status`
  - `mare_triage_sample_path`
  - `MARE Toolbox Remote Gateway` MCP server proxy exposing the remote gateway's 22 tools
- Updated the Mastra starter docs and root README to point users to Mastra Studio.
- Added `MARE_AGENT_MODEL`, `MARE_STUDIO_HOST`, and `MARE_STUDIO_PORT` env docs.
- Updated tests to assert Studio structure instead of the custom GUI server.

## Verification

- `npm run typecheck` passed.
- `uv run pytest tests/test_mastra_template.py` passed: 18 passed.
- Mastra Studio started:
  - `Studio: http://127.0.0.1:4113`
  - `API: http://127.0.0.1:4113/api`
- Studio API showed:
  - 1 registered agent: `MARE Malware Analysis Agent`
  - 24 tools on the agent
  - 22 proxied MCP tools on `mare-toolbox-remote`
- Studio tool execution passed:
  - `mare_status`: `ok: true`, `toolsAvailable: 22`
  - `mare_triage_sample_path`: uploaded the bundled sample, returned `/agent/status/001-mfc42ul.dll`, and returned `# Reporting Draft`
- Chrome opened Studio and screenshot evidence exists at `/tmp/mare-mastra-studio-cdp.png`.

## Note

Agent chat execution in Studio requires an LLM provider key. The template defaults
to `MARE_AGENT_MODEL=openai/gpt-4o-mini`, so set `OPENAI_API_KEY` or choose another
model/provider before running agent chat. Studio tool execution does not need an
LLM key.
