---
phase: 260521-k0d
plan: 01
subsystem: docs/config
tags: [quick, docs, config, env, ida, roadmap]
dependency_graph:
  requires: []
  provides:
    - ".env.example for cp-and-go remote-mode setup"
    - "IDA license bind-mount documentation in Dockerfile + compose.yaml"
    - "Honest, pinned upstream IDA tool inventory link in README"
    - "v1.2 milestone scope stub homing all deferred GW-V2-*/DIS-V2-*/v1.1-Future requirements"
  affects:
    - "Operator onboarding (env discoverability)"
    - "Doc honesty (no vague tool counts, no stale backend priority strings)"
    - "Roadmap visibility (deferred requirements have a tracked home)"
tech_stack:
  added: []
  patterns:
    - "Section-grouped .env template with required/optional + default annotations per var"
    - "Comment-only Dockerfile / compose.yaml license-posture annotations (zero behavior change)"
key_files:
  created:
    - ".env.example"
    - ".planning/quick/260521-k0d-doc-quick-wins-env-example-ida-license-d/260521-k0d-SUMMARY.md"
  modified:
    - "compose.yaml"
    - "Dockerfile"
    - ".planning/milestones/v1.0-research/SUMMARY.md"
    - "README.md"
    - ".planning/ROADMAP.md"
decisions:
  - "Default IDA tag pin uses v1.4.0 (latest as of 2026-05-21 per planning-time WebFetch); embedded as '70+ tools' rather than a precise count since the exact count drifts per release"
  - "MCP_GATEWAY_ENABLED=1 is the ONLY un-commented var in .env.example so cp-and-go yields a working remote-mode env; every other var is commented with default-value annotation"
  - "v1.2 ROADMAP stub does NOT add a phases row to the Progress table — phase rows are owned by /gsd-plan-phase after /gsd-new-milestone v1.2 formalises the milestone"
metrics:
  duration_s: 178
  completed: "2026-05-21"
  tasks: 5
  files: 6
  commits: 5
---

# Phase 260521-k0d Plan 01: Doc Quick Wins (.env.example, IDA license docs, README pointer, v1.2 stub) Summary

Landed 5 atomic doc/config quick wins in 5 commits: `.env.example` for remote-mode compose, IDA Pro license-seeding comment blocks in Dockerfile + compose.yaml, the last stale `BN > IDA > Ghidra` string fixed in the v1.0 research SUMMARY, README's vague "~80 IDA Pro tools" claim replaced with a pinned upstream `ida-pro-mcp v1.4.0` inventory link, and a v1.2 milestone scope stub in ROADMAP citing every deferred GW-V2-*/DIS-V2-*/v1.1-Future requirement.

## Commits

| # | Commit  | Message                                                                                            | Files                                                  |
| - | ------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| 1 | 3f0f0cd | Add .env.example for remote-mode compose env vars                                                  | .env.example                                           |
| 2 | fae3ec5 | Document IDA Pro license seeding pattern in Dockerfile and compose.yaml                            | compose.yaml, Dockerfile                               |
| 3 | aedf98a | Fix stale 'BN > IDA > Ghidra' backend priority in v1.0 research SUMMARY                            | .planning/milestones/v1.0-research/SUMMARY.md          |
| 4 | 2c90d80 | Replace vague IDA tool count in README with pinned ida-pro-mcp v1.4.0 inventory link               | README.md                                              |
| 5 | 164a853 | Scope v1.2 milestone stub in ROADMAP citing deferred GW-V2-*/DIS-V2-*/v1.1-Future requirements     | .planning/ROADMAP.md                                   |

## Tasks Executed

### Task 1 — `.env.example` for remote-mode compose (commit 3f0f0cd)

Created `.env.example` at repo root documenting all 15 env vars consumed by `compose.yaml` + `compose.remote.yaml`. Grouped into 5 sections (remote-mode toggle, network binding, auth+uploads, dynamic mode, image/workspace/license paths). Every var carries a `#` comment stating purpose + required/optional + default. Only `MCP_GATEWAY_ENABLED=1` is uncommented so `cp .env.example .env` yields a working remote-mode env file.

### Task 2 — IDA license seeding docs in Dockerfile + compose.yaml (commit fae3ec5)

Added comment-only annotations explaining the IDA Pro / Binary Ninja license bind-mount pattern. In `compose.yaml` a comment block sits immediately above the `volumes:` key explaining the `${IDA_USER_DIR} -> /home/agent/.idapro` mount, default ephemerality, override pattern, and ida.reg / EULA persistence. In `Dockerfile` a comment header at the top (after the syntax directive, before the first FROM) explains the licensing posture, build-arg conditional install, named-build-context vendor archive consumption, runtime bind-mount license persistence, and `ida-accept-eula` first-use flow. Zero behavior change; `docker compose -f compose.yaml config` validates.

### Task 3 — Stale priority string fix in v1.0 research SUMMARY (commit aedf98a)

Replaced the single remaining live `BN > IDA > Ghidra` string in `.planning/milestones/v1.0-research/SUMMARY.md` line 37 with `IDA > BN > Ghidra` + a cross-reference note to `v1.0-REQUIREMENTS.md` line 105 (which documents the correction rationale). Repo-wide post-edit grep across `.planning/milestones/`, `.planning/ROADMAP.md`, `README.md`, `compose*.yaml`, `Dockerfile` returns zero live stale strings (excluding historical "wording corrected from..." prose, which is allowed per the plan's success criteria, and excluding `.planning/quick/260521-k0d-...PLAN.md` which intentionally documents the literal target string).

### Task 4 — README pinned upstream IDA inventory link (commit 2c90d80)

Replaced README.md line 88 `Backend pass-through` row. Removed the unsourced "IDA Pro's ~80 tools when active" claim; replaced with a link to upstream `ida-pro-mcp` v1.4.0 (`https://github.com/mrexodia/ida-pro-mcp/tree/v1.4.0`) and the upstream's own self-described "70+ tools across 13 categories" inventory (categories enumerated: Core, Modification, Memory Reading, Stack Frame, Structure, Debugger, Advanced Analysis, Pattern Matching & Search, Control Flow, Type, Export, Graph, Batch Operations). Also added one-line pointers for BN's `bn-mcp` and Ghidra's `ghidra-mcp` / `pyghidra` native surfaces.

### Task 5 — v1.2 milestone scope stub in ROADMAP (commit 164a853)

Replaced the placeholder "Next milestone not yet scoped" block in `.planning/ROADMAP.md` (3 lines) with a v1.2 scope stub (29 inserted lines): theme statement, "Scope stub — run /gsd-new-milestone v1.2" status note, all 4 GW-V2-* requirements + 2 DIS-V2-* requirements + 7 v1.1 Future Requirements enumerated, explicit out-of-scope carry-forward (custom web UI, OAuth 2.1, ARM64 IDA, raw CLI passthrough), and Next Step pointer. Progress table left untouched — phases are owned by `/gsd-plan-phase` after `/gsd-new-milestone v1.2` formalises the milestone.

## Deviations from Plan

None. Plan executed exactly as written. Every paste-ready code block landed verbatim. Every <verify> automated grep passed on first run. No Rule 1/2/3 auto-fixes needed; no Rule 4 architectural checkpoints triggered.

## Planning Assumptions Validated at Execution Time

- **`ida-pro-mcp v1.4.0` tag** — verified current at 2026-05-21 planning time per the plan's `<interfaces>` block; not bumped (would have violated the "pin against drift" intent if bumped without re-verifying).
- **Single live `BN > IDA > Ghidra` string** — re-grepped at execution time; confirmed exactly one match in `v1.0-research/SUMMARY.md` line 37 (matches planning-time assertion). No additional surprises surfaced.
- **`MCP_GATEWAY_ENABLED` env-var name and 14 sibling vars** — cross-checked against `compose.yaml` lines 24-35; planning <interfaces> count of 14 matched exactly (15 including `IMAGE_TAG` which is consumed by compose's image-tag substitution).

## Authentication Gates

None. All 5 tasks were pure doc/config edits requiring no external service calls.

## Self-Check: PASSED

**Files created/modified verified on disk:**

- FOUND: `.env.example` (73 lines, MCP_GATEWAY_ENABLED=1 + 14 commented sibling vars)
- FOUND: `compose.yaml` (modified — "Licensed disassembler seeding" comment block above `volumes:`)
- FOUND: `Dockerfile` (modified — "Licensed disassemblers (IDA Pro + Binary Ninja)" header after syntax directive)
- FOUND: `.planning/milestones/v1.0-research/SUMMARY.md` (modified — line 37 now reads `IDA > BN > Ghidra`)
- FOUND: `README.md` (modified — line 88 row now links `ida-pro-mcp/tree/v1.4.0` + "70+ tools")
- FOUND: `.planning/ROADMAP.md` (modified — v1.2 stub replaces "Next milestone not yet scoped")

**Commits verified in git log:**

- FOUND: 3f0f0cd (Task 1)
- FOUND: fae3ec5 (Task 2)
- FOUND: aedf98a (Task 3)
- FOUND: 2c90d80 (Task 4)
- FOUND: 164a853 (Task 5)

## Threat Flags

None. All edits are comment/config/doc additions that introduce no new network endpoints, auth paths, file-access patterns, or trust-boundary schema changes.

## Known Stubs

None. All edits are concrete content; the v1.2 ROADMAP stub is intentional scope sketching (called out explicitly in its own "Status: Scope stub" line and final "Next step" pointer).
