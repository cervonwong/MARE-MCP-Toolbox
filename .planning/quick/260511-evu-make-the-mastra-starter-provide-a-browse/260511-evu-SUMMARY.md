---
status: complete
quick_id: 260511-evu
slug: make-the-mastra-starter-provide-a-browse
completed: 2026-05-11
---

# Quick Task 260511-evu Summary

## Result

`templates/mastra/` now supports both the existing CLI starter and a local browser GUI.

## Changes

- Added reusable Mastra/MCP workflow helpers in `templates/mastra/src/mare.ts`.
- Kept `templates/mastra/src/index.ts` as the CLI entrypoint, now backed by the shared helpers.
- Added `templates/mastra/src/server.ts`, a localhost GUI server with:
  - `GET /api/status`
  - `POST /api/analyze-path`
  - `POST /api/analyze-bytes`
  - browser UI for status, path-based triage, file-upload triage, and report display
- Added `npm run gui` and `npm run gui:open`.
- Updated Mastra README/root README and static template tests for GUI mode.

## Verification

- `npm run typecheck` passed.
- `uv run pytest tests/test_mastra_template.py` passed: 17 passed.
- `uv run pytest tests/test_readme_structure.py` passed: 11 passed.
- Live CLI run against `http://127.0.0.1:8080/mcp` completed:
  - 22 tools listed
  - sample uploaded
  - `run_triage` returned `/agent/status/001-mfc42ul.dll`
  - `get_artifact` returned `# Reporting Draft`
- Live GUI API run completed:
  - `GET /api/status` returned `ok: true`, `toolsAvailable: 22`
  - `POST /api/analyze-path` returned the upload hash, case dir, and report excerpt
- Chrome opened the GUI and captured `/tmp/mare-mastra-gui.png`.

## Runtime State

- GUI server is running at `http://127.0.0.1:4112`.
- Port `4111` was already occupied, so `4112` was used.
