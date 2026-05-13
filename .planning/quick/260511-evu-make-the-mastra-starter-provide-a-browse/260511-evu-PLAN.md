---
status: complete
quick_id: 260511-evu
slug: make-the-mastra-starter-provide-a-browse
created: 2026-05-11
completed: 2026-05-11
---

# Quick Task 260511-evu: Mastra Starter GUI

## Goal

Make `templates/mastra/` usable as both the existing CLI starter and a browser GUI, then run the GUI locally and capture evidence that it opens.

## Success Criteria

- `templates/mastra` keeps the existing CLI happy path: connect, upload, `run_triage`, and `get_artifact`.
- A new GUI command starts a local browser-facing server.
- The GUI can show gateway/tool status and trigger the same sample triage workflow from a browser.
- Template docs explain both CLI and GUI usage.
- Tests/typecheck cover the new scripts/files and the existing tool-call path.
- The GUI is opened locally and screenshot evidence is captured.

## Plan

1. Refactor the Mastra starter workflow into reusable TypeScript helpers.
2. Add a local GUI server and browser UI around those helpers.
3. Update docs and tests for CLI plus GUI mode.
4. Run typecheck/tests, start the GUI, open it with Chrome, and capture a screenshot.

## Completion Evidence

- `npm run typecheck` passed in `templates/mastra`.
- `uv run pytest tests/test_mastra_template.py` passed with 17 tests.
- `uv run pytest tests/test_readme_structure.py` passed with 11 tests.
- Refactored CLI run completed against the live gateway:
  - `Tools available: 22`
  - `Uploaded: be36ce1e79ba6f97038a6f9198057abecf84b38f0ebb7aaa897fd5cf385d702f`
  - `Triage result` included `/agent/status/001-mfc42ul.dll`
  - `Report excerpt: # Reporting Draft`
- GUI server started on `http://127.0.0.1:4112` because port `4111` was already occupied.
- `GET /api/status` returned `ok: true` and `toolsAvailable: 22`.
- `POST /api/analyze-path` returned the sample upload hash, `/agent/status/001-mfc42ul.dll`, and a reporting draft excerpt.
- Chrome opened the GUI and captured `/tmp/mare-mastra-gui.png`.
