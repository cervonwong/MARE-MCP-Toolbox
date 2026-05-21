# Roadmap: MARE-MCP-Toolbox v2

## Milestones

- ✅ **v1.0 Remote MCP Foundation** — Phases 1-4 (shipped 2026-04-27) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Remote RE Tool Expansion** — Phases 5-14 (shipped 2026-05-21) — see [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)

## Phases

<details>
<summary>✅ v1.0 Remote MCP Foundation (Phases 1-4) — SHIPPED 2026-04-27</summary>

- [x] Phase 1: IDA Pro Backend (3/3 plans)
- [x] Phase 2: MCP Gateway (5/5 plans)
- [x] Phase 3: Container Integration (1/1 plan)
- [x] Phase 4: External Client Integration (7/7 plans)

Full details: [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)

</details>

<details>
<summary>✅ v1.1 Remote RE Tool Expansion (Phases 5-14) — SHIPPED 2026-05-21</summary>

- [x] Phase 5: F-1 Image-Hash Fix (3/3 plans) — completed 2026-05-12
- [x] Phase 6: ReToolRunner + artifacts_io Foundation (3/3 plans) — completed 2026-05-13
- [x] Phase 7: run_shell + Typed Static Wrappers + re_artifacts (8/8 plans) — completed 2026-05-13
- [x] Phase 8: Session-Scoped r2 (5/5 plans) — completed 2026-05-18
- [x] Phase 9: Background Job System (5/5 plans) — completed 2026-05-19
- [x] Phase 10: Extraction Tier (5/5 plans) — completed 2026-05-19
- [x] Phase 11: Dynamic Lab Mode (env-gated) (6/6 plans) — completed 2026-05-20
- [x] Phase 12: Orchestrator Skill Update (5/5 plans) — completed 2026-05-20
- [x] Phase 13: Harden concurrency caps and r2 sandboxing (4/4 plans) — completed 2026-05-20
- [x] Phase 14: Close v1.1 Milestone Gaps (4/4 plans) — completed 2026-05-21

Full details: [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)

</details>

### 📋 v1.2 — Multi-Tenant Gateway + Spec Catch-up (Planned, Not Yet Started)

**Status:** Scope stub. Run `/gsd-new-milestone v1.2` to formally open the milestone, then `/gsd-plan-phase` per requirement cluster.

**Theme:** Catch up on MCP-spec features deferred from v1.0/v1.1 (Prompts, progress notifications, per-session keying) and harden long-tail operational concerns surfaced by v1.1 retrospectives.

**Carry-forward requirements** (sourced from `milestones/v1.0-REQUIREMENTS.md` v2 carry-forward block and `milestones/v1.1-REQUIREMENTS.md` Future Requirements list — these are the orphans v1.2 must home):

Advanced Gateway (from v1.0 archive):
- **GW-V2-01** — MCP Prompts expose orchestrator workflow as prompt templates (full triage, deep analysis)
- **GW-V2-02** — Dynamic notifications push analysis progress to connected clients
- **GW-V2-03** — Multi-session support: per-`Mcp-Session-Id` keying of sessions and jobs so multiple clients run independent analyses concurrently (also tracked in v1.1 Future Requirements)
- **GW-V2-04** — Database/session lifecycle management with configurable timeouts and cleanup

Advanced Disassemblers (from v1.0 archive):
- **DIS-V2-01** — Unified disassembler abstraction layer (normalize tool names/params across IDA/BN/Ghidra)
- **DIS-V2-02** — Backend comparison mode (run same analysis on multiple disassemblers + diff results)

Deferred operational concerns (from v1.1 Future Requirements, `milestones/v1.1-REQUIREMENTS.md` lines 139-146):
- Background job persistence across gateway restart
- Mount-namespace isolation for `run_shell` (if `CAP_SYS_ADMIN` becomes acceptable)
- Per-call `tool-logs/` rotation policy
- Sandboxed-network dynamic mode (INetSim/FakeDNS opt-in)
- Convergence of v1.0 `subprocess_runner.run_script` and v1.1 `ReToolRunner` into one runner
- Memory snapshot tooling (Volatility)
- Coverage-guided dynamic / fuzzing hooks

**Not in scope** (out-of-scope items from v1.0/v1.1 archives remain out-of-scope unless explicitly re-evaluated): custom web UI, OAuth 2.1, ARM64 IDA, raw CLI passthrough.

**Next step:** `/gsd-new-milestone v1.2` to formalise this stub into a proper REQUIREMENTS.md + ROADMAP.md split.

## Progress

| Phase                          | Milestone | Plans | Status      | Completed  |
|--------------------------------|-----------|-------|-------------|------------|
| 1. IDA Pro Backend             | v1.0      | 3/3   | Complete    | 2026-04-27 |
| 2. MCP Gateway                 | v1.0      | 5/5   | Complete    | 2026-04-27 |
| 3. Container Integration       | v1.0      | 1/1   | Complete    | 2026-04-27 |
| 4. External Client Integration | v1.0      | 7/7   | Complete    | 2026-04-27 |
| 5. F-1 Image-Hash Fix          | v1.1      | 3/3   | Complete    | 2026-05-12 |
| 6. ReToolRunner Foundation     | v1.1      | 3/3   | Complete    | 2026-05-13 |
| 7. run_shell + Static Wrappers | v1.1      | 8/8   | Complete    | 2026-05-13 |
| 8. Session-Scoped r2           | v1.1      | 5/5   | Complete    | 2026-05-18 |
| 9. Background Job System       | v1.1      | 5/5   | Complete    | 2026-05-19 |
| 10. Extraction Tier            | v1.1      | 5/5   | Complete    | 2026-05-19 |
| 11. Dynamic Lab Mode           | v1.1      | 6/6   | Complete    | 2026-05-20 |
| 12. Orchestrator Skill Update  | v1.1      | 5/5   | Complete    | 2026-05-20 |
| 13. Hardening + r2 Sandboxing  | v1.1      | 4/4   | Complete    | 2026-05-20 |
| 14. Close v1.1 Gaps            | v1.1      | 4/4   | Complete    | 2026-05-21 |
