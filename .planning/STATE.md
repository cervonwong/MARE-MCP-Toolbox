---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Remote RE Tool Expansion
status: executing
stopped_at: Completed 05-01-PLAN.md (locale-stable sort in image-hash subshell)
last_updated: "2026-05-12T05:54:18.493Z"
last_activity: 2026-05-12
progress:
  total_phases: 8
  completed_phases: 0
  total_plans: 3
  completed_plans: 1
  percent: 33
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-12 — v1.1 Remote RE Tool Expansion scoped)

**Core value:** Automated malware triage and deep analysis via AI agents with full access to professional RE tooling — accessible both from inside the container and from external MCP clients.
**Current focus:** Phase 05 — f-1-image-hash-fix

## Current Position

Milestone: v1.1 Remote RE Tool Expansion
Phase: 05 (f-1-image-hash-fix) — EXECUTING
Plan: 2 of 3
Status: Ready to execute
Last activity: 2026-05-12

Progress: [          ] 0% (0/8 phases complete)

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

**v1.1 roadmap decisions (2026-05-12):**

- Adopted research-consensus 8-phase structure (Phases 5-12) verbatim — all 4 research streams converged on this ordering
- Phase 5 (F-1) lands first to unblock every subsequent gateway edit (UAT failure mode 2026-05-11)
- `ReToolRunner` (Phase 6) precedes all consumers; chokepoint primitive validated under wrappers (Phase 7) before sessions/jobs build on it
- Sessions (Phase 8) before Jobs (Phase 9) — same lifespan-registry pattern, r2 validates plumbing at lower complexity than gdb
- Extraction (Phase 10) depends on Jobs (unblob on multi-GB firmware exceeds 60 s MCP cap)
- Dynamic Mode (Phase 11) last among code phases — reuses session plumbing for gdb and job system for long traces
- Orchestrator Skill Update (Phase 12) very last — references all primitives

**Carryover from v1.0:**

- F-1: `run_docker.sh:209-222` `DOCKERFILE_SHA` does not include `mcp-gateway/src/` — gateway-package edits never trigger image rebuild. Now scoped as Phase 5 (FOUND-01).
- [Phase 05-f-1-image-hash-fix]: Inline LC_ALL=C prefix per sort invocation in run_docker.sh image-hash subshell (vs. global export) — keeps locale intent visible at call site

### Pending Todos

- Plan Phase 5 (F-1 Image-Hash Fix) via `/gsd-plan-phase 5`
- Resolve open decisions flagged in research/SUMMARY.md during phase planning:
  - Phase 7: `run_shell` env whitelist contents, `mare-shell` UID primary group ACL on existing case-dirs
  - Phase 8: session resource caps (default 30 min idle, cap 8 sessions per consensus)
  - Phase 9: job log retention/rotation policy
  - Phase 11: per-call netns mechanism, ptrace probe error UX, gdb MI3 command allowlist, binfmt detection helper
- Research flag: `/gsd-research-phase 11` recommended before planning Dynamic Lab Mode (6 distinct pitfalls cluster in that phase)

### Blockers/Concerns

- F-1 (Phase 5) must land before substantive gateway edits, otherwise every subsequent phase hits the "edited gateway, container still has old code" trap that burned 2026-05-11 UAT
- Security boundary needs explicit documentation in v1.1 README: shell is real but cwd-confined to case_dir, no network unless dynamic mode + opt-in, every invocation captured
- Dynamic mode UX surface (`./run_docker.sh --dynamic` ergonomics, env var documentation, mode visibility in `CURRENT_STATE.json`) needs design during Phase 11 planning, not just implementation
- Mount-namespace isolation for `run_shell` deferred to v1.2 (would require CAP_SYS_ADMIN); v1.1 posture-only confinement documented as known limitation

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
| Phase 05-f-1-image-hash-fix P01 | 2min | 1 tasks | 1 files |

## Session Continuity

Last session: 2026-05-12T05:54:18.486Z
Stopped at: Completed 05-01-PLAN.md (locale-stable sort in image-hash subshell)
Resume file: None
