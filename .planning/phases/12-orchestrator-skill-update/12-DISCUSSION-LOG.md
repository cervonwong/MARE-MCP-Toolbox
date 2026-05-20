# Phase 12: Orchestrator Skill Update - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 12-orchestrator-skill-update
**Areas discussed:** W-1..W-7 layout & content, Dual-mode detection & branching, Regression test + tool prefix nomenclature, Dynamic mode in CURRENT_STATE.json

**Discussion mode:** User-delegated auto-select — "use the most common sense, robust, and feature-rich option for all questions." Claude chose the recommended option for every decision and recorded the rationale inline.

---

## W-1..W-7 Layout & Content

| Option | Description | Selected |
|--------|-------------|----------|
| One file `references/deep-re-workflows.md` | Single monolithic file with all seven workflows | |
| Seven separate files under `references/workflows/W-N-*.md` + one index | Each W-N self-contained, lazy-loaded; index summarises and routes | ✓ |
| Expand existing `references/deep-analysis-checklist.md` | Fold W-N content into the existing checklist file | |

**User's choice:** Seven separate files + index (D-03, D-04, D-06).
**Notes:** Lazy loading keeps the always-loaded skill footprint small. SKILL.md's existing Workflow Decision Tree is extended to route to the right W-N file by detected format / signals. Existing deep-analysis-checklist.md is preserved as the component-prioritisation framework with a "Workflow Selection" pointer to the W-N files.

---

## Dual-Mode Detection & Branching

| Option | Description | Selected |
|--------|-------------|----------|
| Probe `tools/list` for sentinel tool `run_shell` | Canonical runtime probe; cache to CURRENT_STATE.json | ✓ |
| Check env var (e.g., `MARE_MODE=gateway`) | Operator-set; brittle if env drifts | |
| Check a marker file at known path | Filesystem-based; can stale on container restart | |

**User's choice:** tools/list probe with `run_shell` sentinel + secondary `get_active_backend` confirm; cached to `CURRENT_STATE.json.mode` (D-07).
**Notes:** tools/list is the canonical truth. Env vars and marker files can lie if the operator changes the runtime without resetting state. Caching avoids per-step reprobing.

| Option | Description | Selected |
|--------|-------------|----------|
| SKILL.md/references prose carries branching at each step | Scripts unchanged; prose has if/else per step | ✓ |
| Modify existing scripts to be mode-aware | Each shell script checks mode and either runs or hands off to MCP tool | |
| New wrapper layer (`scripts/dual_<tool>.sh`) that dispatches | Adds an indirection layer between agent and underlying tool | |

**User's choice:** Prose-carried branching; scripts/ remain canonical local-script path unmodified (D-08).
**Notes:** Smallest blast radius. Scripts stay independently testable. The W-N files (D-05) carry per-step gateway + fallback + artifact-path triples.

---

## Regression Test + Tool Prefix Nomenclature

| Option | Description | Selected |
|--------|-------------|----------|
| `mcp-gateway/tests/test_skill_md_dual_mode.py` | Reuses existing pytest scaffolding & CI | ✓ |
| New `workspace/tests/` directory | Workspace-scoped tests; needs new CI wiring | |
| Top-level `tests/` directory | Project-root tests; needs new CI wiring | |

**User's choice:** `mcp-gateway/tests/test_skill_md_dual_mode.py` (D-11).
**Notes:** Zero new CI infrastructure; the gateway test suite already runs.

| Option | Description | Selected |
|--------|-------------|----------|
| Literal byte-for-byte SKILL.md snapshot | Hard fail on any prose change | |
| Regex content rule: every `mcp__mare[-_]*__*` must co-occur with `scripts/`, `fallback`, or `else` within ±3 lines | Catches the regression class without flaking on prose edits | ✓ |
| AST-style markdown parsing with semantic block analysis | Most precise but heaviest implementation | |

**User's choice:** Regex content rule (D-12) with soft sha256 snapshot as advisory drift signal (D-13). Refresh via `UPDATE_SKILL_SNAPSHOT=1` env var.
**Notes:** The SKILL-03 requirement literally says "snapshots SKILL.md and fails CI on unconditional mcp__mare__* references with no fallback." The content rule directly enforces the second clause; the sha256 soft-snapshot covers the literal "snapshots" wording without making prose edits flake CI.

| Option | Description | Selected |
|--------|-------------|----------|
| Separate Direct-Backend vs Via-Gateway sections | Two parallel sets of instructions | |
| Unified `get_active_backend`-first block with legacy-prefix appendix | Single canonical path; appendix for users wiring backend MCP directly | ✓ |
| Drop the prefix nomenclature entirely | Rely on tool discovery alone | |

**User's choice:** Unified `get_active_backend`-first block + short legacy-prefix appendix (D-02).
**Notes:** The agent calls `mcp__mare-toolbox__get_active_backend()` first (gateway mode), then uses native names (`decompile`, `list_funcs`, `xrefs_to`) regardless of which backend is pinned. Legacy prefixes (`mcp__ida_mcp__*`, `mcp__binary_ninja_headless_mcp__*`, `mcp__ghidra_headless_mcp__*`) listed in appendix for users in local-script mode with direct .mcp.json wiring.

---

## Dynamic Mode in CURRENT_STATE.json

| Option | Description | Selected |
|--------|-------------|----------|
| Top-level boolean `dynamic_mode_enabled` only | Fast gate; coarse-grained | |
| Nested `dynamic_capabilities` dict only | Fine-grained; verbose | |
| Both (boolean + dict mirroring `get_dynamic_capabilities()`) | Fast skip + fine-grained granular skip for W-5/W-7 | ✓ |

**User's choice:** Both (D-15).
**Notes:** Boolean is the cheap gate for "is dynamic mode on at all"; capability dict (ptrace_scope, binfmt_misc, qemu_archs, netns_feasible) lets W-5/W-7 do precise skips (e.g., skip qemu MIPS run if mipsel not in qemu_archs).

| Option | Description | Selected |
|--------|-------------|----------|
| Populated at skill/case init only | Snapshot at init; can stale | |
| Always re-probed every step | Most fresh; expensive | |
| At init + re-probe on demand via `scripts/update_state.py --probe-dynamic` | Init snapshot with deliberate refresh seam | ✓ |

**User's choice:** Init + on-demand re-probe (D-16, D-17).
**Notes:** Fresh data at case start; analyst can refresh after a container restart with `--dynamic` without rebuilding the case.

| Option | Description | Selected |
|--------|-------------|----------|
| Silent skip with no artifact | Leaves no breadcrumb | |
| INDEX.md note only | Single-file breadcrumb | |
| Placeholder artifact at the expected step path + INDEX.md note | Both step-local and index-level breadcrumbs; informative | ✓ |

**User's choice:** Placeholder artifact + INDEX.md note (D-18).
**Notes:** Placeholder lives at `<case_dir>/dynamic/<step>-skipped.md` with missing-capability reason and remediation hint. Reader sees the skip both when walking dynamic/ and when scanning INDEX.md.

---

## Claude's Discretion

- Exact in-file format for W-N entries (three-column table vs. numbered list with sub-bullets).
- Whether the gateway-mode dynamic-capability probe (D-16) lives in shell (curl + jq against the MCP HTTP endpoint with the bearer token) or Python (MCP SDK client).
- Soft-snapshot drift mechanism (pytest.warns vs. captured print vs. non-fatal pytest.skip).
- Whether `references/agent-roles.md` / `interesting-signals.md` need v1.1 sweeps (read at planning time and decide).
- Exact W-N filename slug convention (regression test enumerates by glob `W-*.md`).

## Deferred Ideas

- W-5b network-aware dynamic trace (INetSim/FakeDNS) — v1.2.
- `extract_embedded_files` composite tool — v1.2 if needed.
- `select_workflow` as a typed MCP tool — future "composite tools" phase if prose routing proves insufficient.
- Mount-namespace isolation for `run_shell` — already deferred to v1.2 in REQUIREMENTS.md.
- `mare-toolbox` server-name rename — would require regex + prose updates; document as deliberate decision if/when it happens.
