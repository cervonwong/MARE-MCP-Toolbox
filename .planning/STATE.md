---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Remote RE Tool Expansion
status: defining_requirements
stopped_at: "Milestone scoped 2026-05-12 — proceeding to research/requirements/roadmap"
last_updated: "2026-05-12T00:00:00.000Z"
last_activity: 2026-05-12
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-12 — v1.1 Remote RE Tool Expansion scoped)

**Core value:** Automated malware triage and deep analysis via AI agents with full access to professional RE tooling — accessible both from inside the container and from external MCP clients.
**Current focus:** Defining requirements for v1.1 (Remote RE Tool Expansion). Goal is analyst-parity through MCP: constrained `run_shell` + typed wrappers + session-scoped r2/gdb + env-gated dynamic mode.

## Current Position

Milestone: v1.1 Remote RE Tool Expansion
Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-05-12 — Milestone v1.1 started, PROJECT.md updated with goal + target features

Progress: [          ] 0%

## Performance Metrics

**Velocity:**

- Total plans completed (v1.0): 16
- v1.1 plans completed: 0

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

**v1.1 design decisions (newly added):**

- Expose a constrained `run_shell` over MCP — safety from cwd-confinement + timeout + output cap + auto-capture, not argv allowlisting
- Typed wrappers exist for discoverability and structured output (capstone JSON, ropper bounds, r2/gdb sessions), not as the exclusive surface
- Session-scoped r2 and gdb — iterative analyst workflow needs shared analysis state
- Dynamic mode env-gated default-off (`MCP_GATEWAY_DYNAMIC_TOOLS=1`, surfaced via `./run_docker.sh --dynamic`)
- Composite `investigate_*` MCP tools dropped — orchestrator skill is the composer

**Carryover from v1.0:**

- F-1: `run_docker.sh:209-222` `DOCKERFILE_SHA` does not include `mcp-gateway/src/` — gateway-package edits never trigger image rebuild. To be fixed first in v1.1.

### Pending Todos

None yet.

### Blockers/Concerns

- F-1 must land before substantive gateway edits, otherwise every subsequent phase hits the "edited gateway, container still has old code" trap that burned 2026-05-11 UAT
- Security boundary needs explicit documentation in v1.1 README: shell is real but cwd-confined to case_dir, no network unless dynamic mode + opt-in, every invocation captured
- Dynamic mode UX surface (`./run_docker.sh --dynamic` ergonomics, env var documentation, mode visibility in `CURRENT_STATE.json`) needs design during planning, not just implementation

### Quick Tasks Completed (v1.0 era)

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260414-el8 | Refactor: create workspace/ directory, move skills to native .claude/.codex locations, update mount config and README | 2026-04-14 | dfa6cdb | [260414-el8-refactor-create-workspace-directory-move](./quick/260414-el8-refactor-create-workspace-directory-move/) |
| 260414-fsg | Replace docker-bin wrappers with native config files for Claude and Codex | 2026-04-14 | 3b3c981 | [260414-fsg-replace-docker-bin-wrappers-with-native-](./quick/260414-fsg-replace-docker-bin-wrappers-with-native-/) |
| 260414-iee | Move Claude/Codex config from workspace project-level to user-level via configure-agent-mcp.sh | 2026-04-14 | a89af30 | [260414-iee-move-claude-codex-config-from-workspace-](./quick/260414-iee-move-claude-codex-config-from-workspace-/) |
| 260423-f3k | Fix inner agent statusline paths (/workspace -> /agent) | 2026-04-23 | bdae5ea | [260423-f3k-fix-inner-agent-statusline-paths-workspa](./quick/260423-f3k-fix-inner-agent-statusline-paths-workspa/) |
| 260511-cwf | Fix remote MCP security defaults: localhost host bind, exact Origin validation, and case_dir confinement | 2026-05-11 | f556fda | [260511-cwf-fix-remote-mcp-security-defaults-localho](./quick/260511-cwf-fix-remote-mcp-security-defaults-localho/) |
| 260511-evu | Make the Mastra starter provide a browser GUI in addition to the existing CLI, and verify by opening the GUI | 2026-05-11 | uncommitted | [260511-evu-make-the-mastra-starter-provide-a-browse](./quick/260511-evu-make-the-mastra-starter-provide-a-browse/) |
| 260511-fam | Switch the Mastra starter GUI to the default Mastra Studio dashboard with a registered MARE agent and tools | 2026-05-11 | uncommitted | [260511-fam-switch-the-mastra-starter-gui-to-the-def](./quick/260511-fam-switch-the-mastra-starter-gui-to-the-def/) |

## Session Continuity

Last session: 2026-05-12T00:00:00.000Z
Stopped at: v1.1 milestone scoping in /gsd-new-milestone — moving to research decision then requirements
Resume file: None
