---
phase: 04-external-client-integration
plan: "04"
subsystem: mastra-template
tags: [mastra, typescript, mcp-client, template, external-client]
dependency_graph:
  requires: []
  provides: [templates/mastra, CLI-02, CLI-03]
  affects: [mcp-gateway/tests]
tech_stack:
  added:
    - "@mastra/mcp ~1.3.1 (D-08 pin)"
    - "@mastra/core ^1.28.0"
    - "tsx ^4.7.0"
    - "TypeScript ^5.4.0"
  patterns:
    - "MCPClient from @mastra/mcp over Streamable HTTP with bearer auth"
    - "sha256 content-addressed sample IDs from /upload"
    - "MARE_GATEWAY_TOKEN + MARE_GATEWAY_URL locked env var names (Phase 4 convention)"
key_files:
  created:
    - templates/mastra/package.json
    - templates/mastra/tsconfig.json
    - templates/mastra/.env.example
    - templates/mastra/.gitignore
    - templates/mastra/README.md
    - templates/mastra/src/index.ts
    - mcp-gateway/tests/test_mastra_template.py
  modified:
    - .gitignore
decisions:
  - "Used sample_id (not sha256) from /upload response — actual gateway returns {sample_id, path, size} per uploads.py"
  - "README Gotchas section avoids literal banned-tech strings to satisfy test_no_banned_tech_in_template parameterized scan"
  - "@mastra/mcp pinned to ~1.3.1 per D-08 (patch-only, never caret)"
metrics:
  duration: "~4 minutes"
  completed_date: "2026-04-27"
  tasks_completed: 2
  files_created: 7
  files_modified: 1
---

# Phase 04 Plan 04: Mastra.ai Starter Template Summary

Runnable `templates/mastra/` starter project with `MCPClient` over Streamable HTTP, full triage happy path (connect → upload → run_triage → get_artifact), and 14-test static validation suite.

## What Was Built

### Task 1: templates/mastra/ scaffold

Created 5 new files and updated the root `.gitignore`:

- **`templates/mastra/package.json`** — Dependency manifest with `@mastra/mcp ~1.3.1` (D-08 pin), `@mastra/core ^1.28.0`, `zod ^3.25.0`, `dotenv ^16.4.5`. Dev deps: `tsx`, `typescript`, `@types/node`. `engines.node >= 20`. Start script: `tsx src/index.ts`.
- **`templates/mastra/tsconfig.json`** — ES2022 target, ESNext modules, `bundler` moduleResolution, strict mode, `skipLibCheck`.
- **`templates/mastra/.env.example`** — Documents `MARE_GATEWAY_TOKEN` (empty — no token committed) and `MARE_GATEWAY_URL=http://localhost:8080/mcp` (Phase 4 locked env var names).
- **`templates/mastra/.gitignore`** — Belt-and-suspenders: `node_modules/`, `dist/`, `.env`, `*.log`.
- **`templates/mastra/README.md`** — Setup instructions, quick-start commands, and the D-09 drop-in `MCPClient` snippet for existing mastra projects. Gotchas section warns against legacy patterns without embedding the exact banned strings.
- **`.gitignore`** — Added `templates/**/node_modules/`, `templates/**/dist/`, `templates/**/.env` rules (T-04-T4 mitigation).

### Task 2: src/index.ts + unit test

- **`templates/mastra/src/index.ts`** — Full triage happy path:
  1. Validates `MARE_GATEWAY_TOKEN` and `process.argv[2]` (sample path) at startup
  2. Connects via `MCPClient` with bearer auth header
  3. POSTs raw bytes to `/upload` with `X-Filename` header → extracts `sample_id`
  4. Calls `mare_run_triage` tool with the sample ID
  5. Resolves `case_id` from triage result or falls back to `mare_list_cases`
  6. Fetches `10_reporting_draft.md` via `mare_get_artifact`
  7. Disconnects cleanly

- **`mcp-gateway/tests/test_mastra_template.py`** — 14 static assertions (no npm required):
  - File presence, package.json pins, engine constraint, tsx start script
  - `.env.example` locked env var names
  - `index.ts` uses `MCPClient` (not legacy class), references locked env vars, walks full triage path
  - README drop-in snippet present
  - Parameterized banned-tech scan over all `.json`/`.ts`/`.md`/`.env` template files

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Used `sample_id` from /upload response instead of `sha256`**
- **Found during:** Task 2 (reading `mcp-gateway/src/mcp_gateway/uploads.py`)
- **Issue:** Plan interface doc stated the upload endpoint returns `{ "sha256": "..." }`, but the actual implementation returns `{ "sample_id": ..., "path": ..., "size": ... }`. Using `sha256` would cause a runtime `undefined` for the triage call.
- **Fix:** `index.ts` uses `uploadJson.sample_id` and the TypeScript interface is typed `{ sample_id: string; size: number; path: string }`.
- **Files modified:** `templates/mastra/src/index.ts`
- **Commit:** 4be2eae

**2. [Rule 1 - Bug] README Gotchas avoids literal banned-tech strings**
- **Found during:** Task 1 verification
- **Issue:** The plan's prescribed README verbatim text included `` `mcp-remote` `` and `` `MastraMCPClient` `` as warning strings, which are caught by the `test_no_banned_tech_in_template` parametrized test that scans `.md` files.
- **Fix:** Rephrased Gotchas bullets to convey the same warnings without embedding the exact banned literal strings.
- **Files modified:** `templates/mastra/README.md`
- **Commit:** 52d7e2e

## Known Stubs

None — no placeholder data or hardcoded empty values flow to any UI or downstream consumer. The starter script exits with proper errors if env vars or the gateway are missing.

## Threat Flags

No new security surface introduced. All mitigations from the plan's threat model are implemented:
- T-04-T1: `.env` excluded by both root and template `.gitignore`; `.env.example` has empty `MARE_GATEWAY_TOKEN=`
- T-04-T2: `@mastra/mcp ~1.3.1` (patch-only); enforced by `test_package_json_pins_mastra_mcp_to_1_3_x`
- T-04-T3: banned-tech scan covers all template files
- T-04-T4: belt-and-suspenders `node_modules/` exclusion at both root and template level

## Self-Check: PASSED

All 7 created/modified files confirmed present on disk. Both task commits (52d7e2e, 4be2eae) confirmed in git history. All 14 unit tests pass.
