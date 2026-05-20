---
phase: 12
slug: orchestrator-skill-update
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-20
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (mcp-gateway test suite) |
| **Config file** | `mcp-gateway/pyproject.toml` (existing) |
| **Quick run command** | `cd mcp-gateway && pytest tests/test_skill_md_dual_mode.py -q` |
| **Full suite command** | `cd mcp-gateway && pytest -q` |
| **Estimated runtime** | ~5–15 seconds (quick), ~30–60 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run quick run command (`pytest tests/test_skill_md_dual_mode.py -q`)
- **After every plan wave:** Run full suite (`pytest -q`)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

> The planner will fill this table during PLAN.md authoring. Every task that
> modifies SKILL.md, references/, scripts/, or the new test file MUST have an
> `<automated>` command (typically `pytest tests/test_skill_md_dual_mode.py::<case> -q`
> or a `grep -E` invariant check against the modified file).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | SKILL-01 | — | Doc-only edits; no runtime behavior change | content invariant | `pytest mcp-gateway/tests/test_skill_md_dual_mode.py::test_backend_priority_order -q` | ❌ W0 | ⬜ pending |
| 12-01-02 | 01 | 1 | SKILL-02 | — | Skill content additions are skill-discovery-safe | content invariant | `pytest mcp-gateway/tests/test_skill_md_dual_mode.py::test_workflow_index_present -q` | ❌ W0 | ⬜ pending |
| 12-01-03 | 01 | 1 | SKILL-03 | — | Regression test enforces fallback-or-script for every `mcp__mare-toolbox__*` reference | unit + regex | `pytest mcp-gateway/tests/test_skill_md_dual_mode.py::test_mare_toolbox_refs_have_fallback -q` | ❌ W0 | ⬜ pending |
| 12-01-04 | 01 | 1 | SKILL-04 | — | `CURRENT_STATE.json` carries `dynamic_mode_enabled` + `dynamic_capabilities`; skipped steps emit placeholder + INDEX.md row | schema + grep | `pytest mcp-gateway/tests/test_skill_md_dual_mode.py::test_skill_documents_dynamic_skip_behavior -q` + `grep -E 'dynamic_mode_enabled' workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Task IDs above are placeholder — the planner replaces them with actual task IDs
> per the produced PLAN.md files. Each requirement (SKILL-01..04) MUST have at
> least one task with an `<automated>` command in this table.

---

## Wave 0 Requirements

- [ ] `mcp-gateway/tests/test_skill_md_dual_mode.py` — new pytest module per D-11..D-14 with test cases:
    - `test_backend_priority_order` (SKILL-01) — verifies `IDA > Binary Ninja > Ghidra` ordering in SKILL.md text
    - `test_workflow_index_present` (SKILL-02) — verifies `references/deep-re-workflows.md` exists and lists W-1..W-7
    - `test_mare_toolbox_refs_have_fallback` (SKILL-03 hard fail) — regex `mcp__mare[-_]\w+__\w+` enclosing block must contain `scripts/`, `fallback`, or `else`
    - `test_skill_md_snapshot` (SKILL-03 soft) — sha256 advisory check with `UPDATE_SKILL_SNAPSHOT=1` refresh path
    - `test_skill_documents_dynamic_skip_behavior` (SKILL-04) — verifies SKILL.md/references describe placeholder artifact + INDEX.md row pattern for dynamic-only step skips
- [ ] `mcp-gateway/tests/snapshots/SKILL.md.sha256` — soft snapshot baseline (created during Wave 0 stub)
- [ ] `mcp-gateway/tests/conftest.py` — no changes needed (existing pytest collection picks up new test file)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Skill is discovered by Claude when SKILL.md frontmatter is intact | SKILL-01..04 | Skill discovery happens client-side in Claude Code; no programmatic test exists in this repo | After edits land, open Claude Code in the project root and verify the `malware-analysis-orchestrator` skill is available via `/help` skill list |
| Agent routing through Workflow Decision Tree picks the correct W-N file for a sample format | SKILL-02 | The decision-tree application is an agent runtime behavior, not a code path; tests can only assert prose is present, not that the agent obeys it | Run the skill against a known PE sample, observe agent reads `W-3-pe-deep-dive.md`; repeat for ELF (W-2), packed UPX binary (W-1), firmware blob (W-6) |
| End-to-end dual-mode behavior (gateway vs scripts) | SKILL-03 | Requires running the gateway container in two configurations | (a) Run skill against `run_docker.sh` (gateway mode) — `CURRENT_STATE.json` mode=`gateway`; (b) Run skill with disassembler MCP wired directly in `.mcp.json` (scripts mode) — `CURRENT_STATE.json` mode=`scripts` |
| Dynamic-capability probe populates `CURRENT_STATE.json` when gateway is started with `--dynamic` | SKILL-04 | Requires the dynamic-mode container; CI can mock but cannot exercise `ptrace_scope` / `binfmt_misc` faithfully | Start container with `./run_docker.sh --dynamic`, init a new case, assert `dynamic_mode_enabled=true` and `dynamic_capabilities.qemu_archs` is non-empty |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (the new pytest module + snapshot file)
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
