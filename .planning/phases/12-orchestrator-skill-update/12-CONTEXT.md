# Phase 12: Orchestrator Skill Update - Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Update `workspace/.claude/skills/malware-analysis-orchestrator/` so it (1) reflects
the v1.1 tool surface and the correct backend priority `IDA > Binary Ninja > Ghidra`,
(2) encodes seven deep-RE workflows (W-1..W-7) mapping findings → v1.1 typed
wrappers with `run_shell` fallbacks, (3) preserves dual-mode operation with a
runtime decision rule between gateway tools and local `scripts/`, (4) surfaces
dynamic-mode status in `CURRENT_STATE.json` and skips dynamic-only steps with
explicit reason artifacts when the mode is off, and (5) lands a CI regression
test that fails on unconditional `mcp__mare__*` references with no fallback.

In scope: edits to `workspace/.claude/skills/malware-analysis-orchestrator/`
(SKILL.md, references/, scripts/), one new `mcp-gateway/tests/` test module,
optional thin extensions to existing scripts (`init_status_tree.sh`,
`update_state.py`) for dynamic-capability population.

Out of scope: new MCP tools, new gateway features, modifications to any v1.1
phase primitives (Phases 5-11 are complete), changes to the gateway tool
surface or backend pinning logic.

</domain>

<decisions>
## Implementation Decisions

### Backend Priority Documentation (SKILL-01)

- **D-01:** SKILL.md "Disassembly and Decompilation" section is rewritten to list
  the priority as `IDA Pro MCP > Binary Ninja MCP > Ghidra MCP > r2 (CLI)`,
  matching `mcp-gateway/README.md:71` and `mcp-gateway/src/mcp_gateway/app.py`.
  The v1.0 doc-drift (BN-first ordering in SKILL.md:141-143) is corrected
  everywhere it appears — top-level SKILL.md, `references/workflow.md`,
  `references/deep-analysis-checklist.md`, and the per-workflow files
  (`references/workflows/W-N-*.md`).
- **D-02:** Skill teaches the agent to call `mcp__mare-toolbox__get_active_backend()`
  FIRST when in gateway mode (to discover which backend is actually pinned at
  runtime), then use the backend's NATIVE tool names (e.g., `decompile(addr)`,
  `list_funcs(...)`, `xrefs_to(...)`). The skill carries a short
  legacy-prefix appendix listing `mcp__ida_mcp__*`,
  `mcp__binary_ninja_headless_mcp__*`, `mcp__ghidra_headless_mcp__*` for
  local-script-mode users who wire a disassembler MCP directly in `.mcp.json`
  (current inner-agent default).

### Deep RE Checklists W-1..W-7 (SKILL-02)

- **D-03:** Each of W-1..W-7 lives in its OWN file at
  `workspace/.claude/skills/malware-analysis-orchestrator/references/workflows/W-N-<slug>.md`
  (seven files total). Sources verbatim from `.planning/research/FEATURES.md`
  §W-1..W-7 (lines 223-310) and reformatted for skill consumption:
  - `W-1-packed-binary-triage.md` (packer ID → UPX/commercial/unknown branch → recurse)
  - `W-2-elf-deep-dive.md` (ELF static via rabin2 JSON + readelf modes + nm + r2 session)
  - `W-3-pe-deep-dive.md` (PE flavor of W-2; rabin2 JSON + xxd PE header + capstone + r2)
  - `W-4-rop-gadget-hunt.md` (NX/PIE/RELRO context + ropper structured gadgets)
  - `W-5-dynamic-api-trace.md` (strace/ltrace via jobs + gdb session follow-up)
  - `W-6-firmware-unpack.md` (binwalk → unblob job → promote children → recurse)
  - `W-7-cross-arch-iot.md` (rabin2 → r2 disasm + qemu-user job for behavior)
- **D-04:** A new index file at `references/deep-re-workflows.md` lists all
  seven workflows with one-line summaries + entry conditions (detected format,
  packer detection, content signals, dynamic-mode requirement). SKILL.md
  Workflow Decision Tree (existing section) is extended to route by
  `detected_format` + signals into the appropriate W-N reference file. Agent
  retains override discretion.
- **D-05:** Each W-N file lists steps in three columns or three lines per step:
  - Gateway-mode call (e.g., `mcp__mare-toolbox__run_die(case_dir, sample, deep=true)`)
  - Local-script fallback (e.g., `run_shell die -d <sample>` OR
    `scripts/<helper>.sh <sample>` when an existing script covers it)
  - Expected artifact path under `<case_dir>/`
- **D-06:** `references/deep-analysis-checklist.md` is preserved as the
  component-prioritization framework (existing structure stays) and gains a new
  subsection "Workflow Selection" that points at the W-N files.
  No content overlap: deep-analysis-checklist remains the *framework*; W-N
  files are the *concrete recipes*.

### Dual-Mode Detection & Branching (SKILL-03)

- **D-07:** Mode detection runs ONCE at skill init. The skill probes the MCP
  surface for the sentinel tool **`run_shell`** (canonical because it exists
  only in gateway mode). Secondary confirmation: `get_active_backend` tool
  presence. Result is cached to `<case_dir>/CURRENT_STATE.json` as
  `"mode": "gateway"` or `"mode": "scripts"`. Subsequent steps read this field
  rather than reprobing.
- **D-08:** Branching style is **SKILL.md/references prose-carried** — every
  step in W-1..W-7 lists both the gateway and the scripts/ form per D-05.
  Existing scripts under `workspace/.claude/skills/malware-analysis-orchestrator/scripts/`
  are NOT modified to add mode awareness — they ARE the canonical local-script
  path. Keeps blast radius small + scripts remain independently shell-testable.
- **D-09:** The decision rule the agent applies at each step:
  ```
  if state.mode == "gateway":
      call mcp__mare-toolbox__run_X(...)        # gateway path
  else:
      call scripts/<fallback>.sh ...            # local-script path
      # or: run_shell <tool> ... when no script exists and gateway is up
  ```
  This rule is documented prominently in SKILL.md (new "Dual-Mode Operation"
  section) and repeated per-step in each W-N file.
- **D-10:** The `mare-toolbox` server name in `.mcp.json` is the canonical
  identifier (sourced from `run_docker.sh:66`). Host-side tool prefix is
  `mcp__mare-toolbox__*`. The skill text uses this exact spelling everywhere.

### Regression Test (SKILL-03 CI gate)

- **D-11:** Test file: `mcp-gateway/tests/test_skill_md_dual_mode.py`.
  Reuses the existing pytest scaffolding (conftest, marker discipline) so it
  runs automatically in the gateway's CI. Resolved path discipline:
  test resolves SKILL.md via `Path(__file__).resolve().parents[2] /
  "workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md"` (project
  root anchor; survives both host-side and container-side pytest invocations).
- **D-12:** Detection rule is regex-based, not literal-snapshot:
  - For every line matching `re.compile(r"mcp__mare[-_]\w+__\w+")`, the
    enclosing block (paragraph OR list-item with ± 3 lines of trailing
    context) MUST contain at least one of: the substring `scripts/`,
    the word `fallback` (case-insensitive), or an `else` branch keyword.
  - Failures emit `file:line: <snippet>` for every offending block,
    not just the first.
- **D-13:** Soft snapshot check (advisory only, never fails CI on its own):
  test computes sha256 of SKILL.md and compares to
  `mcp-gateway/tests/snapshots/SKILL.md.sha256`. Drift emits a warning via
  `pytest.warns(UserWarning, ...)` or a captured `print` with a clear
  regenerate-hint message. Refresh path: `UPDATE_SKILL_SNAPSHOT=1 pytest
  mcp-gateway/tests/test_skill_md_dual_mode.py::test_skill_md_snapshot` rewrites
  the .sha256 file.
- **D-14:** Test also exercises the W-N reference files (same regex
  rule applied to every `references/workflows/W-*.md`). Reuses one parametrized
  test function over `(SKILL.md, W-1.md, ..., W-7.md, references/*.md)`.

### Dynamic Mode in CURRENT_STATE.json (SKILL-04)

- **D-15:** `CURRENT_STATE.json` schema gains two fields:
  - `"dynamic_mode_enabled": bool` — fast skip gate at the top level.
  - `"dynamic_capabilities": { "ptrace_scope": int|null, "binfmt_misc": bool,
    "qemu_archs": ["mipsel", "aarch64", ...], "netns_feasible": bool }` — mirrors
    the `get_dynamic_capabilities()` return shape (Phase 11 D-DYN-CAP-PROBE-01).
    Lets W-5/W-7 do fine-grained skips (e.g., skip qemu MIPS run if `mipsel`
    not in `qemu_archs`).
  Both fields are populated at case-init time and re-probable later.
- **D-16:** Population path is mode-aware:
  - **Gateway mode:** `scripts/init_status_tree.sh` (extended) shells out a
    tiny Python or `jq` snippet that calls
    `mcp__mare-toolbox__get_dynamic_capabilities()` via the MCP client and
    populates the two fields. If gateway is up but dynamic mode is off,
    `dynamic_mode_enabled=false` and `dynamic_capabilities={}`. (Alternative
    Claude's-Discretion implementation: the agent itself calls the MCP tool
    and writes via `update_state.py --probe-dynamic` rather than baking MCP
    client logic into a shell script. Planner decides.)
  - **Scripts mode:** `scripts/init_status_tree.sh` invokes the existing
    `scripts/probe_dynamic_tools.sh` (already in the repo at the project root
    — confirm at planning time) and parses its output into the same JSON
    shape. If `probe_dynamic_tools.sh` is absent or fails, `dynamic_mode_enabled=false`
    and a note is appended to `INDEX.md`.
- **D-17:** Re-probe path: `scripts/update_state.py --probe-dynamic` re-runs
  the population logic and updates `CURRENT_STATE.json` in place. Useful when
  operator restarts the container with `--dynamic`.
- **D-18:** Skip behavior for dynamic-only steps: **placeholder artifact +
  INDEX.md note** is MANDATORY (silent skip is forbidden, per the SKILL-04
  acceptance criterion "skipped (with a noted reason)").
  - Placeholder artifact: `<case_dir>/dynamic/<step>-skipped.md` containing
    (1) which step was skipped, (2) the missing capability that caused the
    skip (e.g., "ptrace_scope=2, kernel restricts attach"), and (3) a one-line
    remediation hint ("run `./run_docker.sh --dynamic` and re-init the case").
  - INDEX.md entry: a row in the "skipped steps" subsection (new) listing
    step + reason + placeholder path.

### Claude's Discretion

The planner / executor decides:

- **Exact format inside each W-N file** — three-column markdown table vs.
  numbered list with sub-bullets. As long as gateway + fallback + artifact
  per step are unambiguously present and the regression test passes
  (D-11/D-12).
- **Whether D-16 gateway-mode probe lives in shell (curl + jq against the
  MCP HTTP endpoint with the bearer token) or in Python (importing the
  `mcp` SDK)**. The shell route keeps init_status_tree.sh self-contained;
  the Python route is more robust to MCP protocol changes. Pick during
  planning based on which Phase 5-11 patterns are already established.
- **Soft snapshot mechanism** (D-13) — `pytest.warns` vs. captured-print
  vs. a non-fatal `print` with `pytest.skip` carrying a hint. Whichever
  surfaces drift visibly in CI logs without flaking.
- **Whether `references/agent-roles.md` and `references/interesting-signals.md`
  need updates beyond D-01** — read both during planning; if they reference
  v1.0 tool names that need rewriting for the v1.1 wrappers, fold those
  edits into the same plan. If they're tool-agnostic prose, leave them alone.
- **Exact W-N filename slugs** (e.g., `W-1-packed-binary-triage.md` vs.
  `W1-packed.md`). Pick a consistent convention at planning time; the
  regression test enumerates by glob `W-*.md`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/REQUIREMENTS.md` SKILL-01..SKILL-04 (lines 85-88) — acceptance
  criteria for the four skill update outcomes.
- `.planning/ROADMAP.md` §Phase 12 (lines 158-167) — phase goal, dependencies,
  success criteria.

### Workflow content (W-1..W-7 source of truth)
- `.planning/research/FEATURES.md` §"Deep-RE Workflows (W-1..W-7)" (lines 220-310)
  — verbatim source for W-N step lists, tool calls, and "why this matters for
  v1.1" rationale. Each W-N file under `references/workflows/` is a
  reformatted distillation of one section.
- `.planning/research/SUMMARY.md` (lines 60-65, 216) — confirms the W-1..W-7
  scope and the dual-mode + dynamic-flag + CI test requirements.

### v1.1 tool surface (what the wrappers actually do)
- `mcp-gateway/README.md` §"Gateway tool surface" (lines 50-95) — full
  gateway-native tool table including `get_active_backend`, `decompile`,
  `list_functions`, `get_xrefs`, `set_active_case`, `get_active_case`,
  `list_uploads`, `get_sample_info`.
- `mcp-gateway/README.md` §"Backend-native pass-through" (lines 70-95) —
  backend priority `IDA > Binary Ninja > Ghidra` and the native-name override
  rule (D-02).
- `mcp-gateway/README.md` §"IDA Pro MCP native tools" (lines 81-115) — the
  exact native tool names the skill must teach when IDA is the pinned backend
  (`decompile(addr)`, `list_funcs`, `xrefs_to`, `idalib_*`, etc.).
- `mcp-gateway/src/mcp_gateway/tools/__init__.py` — canonical registration
  order: cases, artifacts, workflows, disasm, resources, re_artifacts,
  re_static, shell, r2_sessions, jobs, extract, dynamic (env-gated),
  backend_passthrough. Use as the master list of what's registered.

### v1.1 wrapper modules (per-tool argv / schema)
- `mcp-gateway/src/mcp_gateway/tools/re_static.py` — 11 static wrappers:
  `run_file`, `run_die`, `run_xxd`, `run_readelf`, `run_objdump`, `run_nm`,
  `run_rabin2`, `run_capstone_disasm`, `run_ropper`, `run_jq`, `run_yq`.
- `mcp-gateway/src/mcp_gateway/tools/extract.py` — 7 extraction tools:
  `run_binwalk`, `run_unblob`, `run_upx_test`, `run_upx_list`, `run_upx_unpack`,
  `list_extracted_files`, `promote_extracted_sample`.
- `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` — 4 r2 session tools:
  `open_r2_session`, `r2_cmd`, `close_r2_session`, `list_sessions`.
- `mcp-gateway/src/mcp_gateway/tools/jobs.py` — 4 job tools:
  `start_tool_job`, `get_tool_job`, `cancel_tool_job`, `list_tool_jobs`.
- `mcp-gateway/src/mcp_gateway/tools/dynamic.py` — 7 env-gated dynamic tools:
  `run_strace`, `run_ltrace`, `run_qemu_user`, `open_gdb_session`, `gdb_exec`,
  `close_gdb_session`, `get_dynamic_capabilities`.
- `mcp-gateway/src/mcp_gateway/tools/shell.py` — `run_shell` (the sentinel
  used by D-07's mode detection).
- `mcp-gateway/src/mcp_gateway/tools/re_artifacts.py` — `write_artifact`,
  `append_artifact`, `list_artifacts`, `get_artifact_tree`, `get_tool_log`.
- `mcp-gateway/src/mcp_gateway/tools/cases.py` — `init_case`, `get_active_case`,
  `set_active_case`, etc.

### Mode + dynamic-mode plumbing
- `run_docker.sh` lines 55-100 — confirms `mare-toolbox` as the canonical
  `.mcp.json` server name (D-10) and the ready-block format the operator sees.
- `run_docker.sh` §dynamic-mode flag — `MCP_GATEWAY_DYNAMIC_TOOLS=1` /
  `./run_docker.sh --dynamic` toggle (Phase 11 D-DYN-FLAG-01).
- `.planning/phases/11-dynamic-lab-mode-env-gated/11-CONTEXT.md` — the
  `get_dynamic_capabilities()` return shape that D-15 mirrors and the
  env-gating semantics (off by default; tools/list adds 7 entries when on).
- `scripts/probe_dynamic_tools.sh` (project root) — reused by D-16 in scripts
  mode to populate `dynamic_capabilities`.

### Current skill state (what we're editing)
- `workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md`
  (275 lines) — current top-level. Backend priority statement lives at
  lines 141-143 and is the primary SKILL-01 target.
- `workspace/.claude/skills/malware-analysis-orchestrator/references/workflow.md`
  (97 lines) — current Phase 0-8 workflow; needs a SKILL-01 sweep for tool
  prefixes and a SKILL-02 cross-reference pointing into W-N files.
- `workspace/.claude/skills/malware-analysis-orchestrator/references/deep-analysis-checklist.md`
  (73 lines) — preserved per D-06; gains a "Workflow Selection" pointer.
- `workspace/.claude/skills/malware-analysis-orchestrator/references/agent-roles.md`,
  `interesting-signals.md`, `artifact-spec.md` — read during planning to
  decide whether they need SKILL-01 sweeps (Claude's Discretion above).
- `workspace/.claude/skills/malware-analysis-orchestrator/scripts/` — nine
  v1.0 scripts (collect_strings.sh, collect_imports.sh, scan_yara.sh,
  scan_capa.sh, init_status_tree.sh, build_hypothesis.py, rank_signals.py,
  resolve_case.sh, update_state.py). Per D-08 these are NOT modified except
  init_status_tree.sh + update_state.py per D-16/D-17 for dynamic-cap
  population.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Existing scripts/ directory** — nine v1.0 helpers cover the local-script
  path for W-2 (strings, imports), capa/YARA scans, and case-dir lifecycle.
  W-N files reuse them as the fallback target.
- **`mcp-gateway/tests/` pytest infrastructure** — conftest, marker discipline,
  resolved-path helpers. The new `test_skill_md_dual_mode.py` plugs in here
  without new test infrastructure (D-11).
- **`get_active_backend` tool** — already exists at gateway-tool level
  (`mcp-gateway/README.md:64`). D-02 just teaches the skill to call it.
- **`get_dynamic_capabilities` tool** — already exists in Phase 11. D-15/D-16
  consume its output shape directly; no new gateway code needed.
- **`scripts/probe_dynamic_tools.sh`** (project root) — Phase 11-era probe.
  Reused in scripts-mode D-16.
- **`CURRENT_STATE.json` artifact** — already part of the case-dir schema
  (`references/artifact-spec.md` likely defines fields). D-15 extends it
  with two new fields; no new artifact file needed.

### Established Patterns
- Per-step gateway-tool + fallback documentation is the established pattern
  in `.planning/research/FEATURES.md` §W-1..W-7. D-05 just lifts that
  pattern into the skill itself.
- Pytest tests resolve project paths via
  `Path(__file__).resolve().parents[N]` (Phase 5-11 precedent). D-11 follows.
- Soft-warning + hard-fail dual checks (Phase 7 collision_check pattern:
  registration ordering hard-fails, but tool-count drift soft-warns at first).
  D-12 (hard) + D-13 (soft) mirrors this idiom.

### Integration Points
- **`mcp-gateway/tests/` pytest collection** picks up
  `test_skill_md_dual_mode.py` automatically — no conftest changes needed.
- **`workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md`** is
  Claude-discovered via the `name:` / `description:` frontmatter; edits
  preserve the frontmatter shape so skill discovery doesn't break.
- **`CURRENT_STATE.json`** is read by `scripts/update_state.py` and by the
  agent itself; both must tolerate the new `dynamic_mode_enabled` and
  `dynamic_capabilities` fields (additive, backward-compatible).

</code_context>

<specifics>
## Specific Ideas

- The "stale v1.0 assumption" called out in PROJECT.md is the
  Binary-Ninja-first ordering and the remote-agent path that referenced
  local `scripts/` rather than gateway tools. Both are addressed by D-01
  (priority fix) and D-07/D-08 (dual-mode prose).
- The regression test's "snapshots SKILL.md" wording in SKILL-03 is
  interpreted as "guards the SKILL.md content invariants", not "literal
  byte-for-byte snapshot" — see D-12/D-13. A literal byte snapshot would
  fail on every legitimate prose edit; the content-rule check is what
  actually catches the regression class the requirement targets.
- The seven W-N files are deliberately small (~30-80 lines each) so the
  agent loads only the ones relevant to the detected sample (per the
  Workflow Decision Tree). Avoids inflating the skill's always-loaded
  footprint with workflows the agent isn't running.

</specifics>

<deferred>
## Deferred Ideas

- **W-5b: Network-aware dynamic trace** — `run_strace` with
  `allow_network=true` against INetSim/FakeDNS. Flagged out of scope for
  v1.1 default in `.planning/research/FEATURES.md` W-5 step 8. Belongs in
  v1.2 alongside any sandboxing infrastructure work.
- **`extract_embedded_files` composite tool** — referenced in FEATURES.md
  W-6 step rationale. Not currently a gateway tool; would belong in a
  future "composite tools" phase if the orchestrator-skill composer pattern
  proves insufficient.
- **Auto-routing into W-N via a Workflow tool** — currently the agent
  routes prose-style via SKILL.md decision tree. A future phase could
  expose `select_workflow(case_dir) -> workflow_id` as a typed gateway
  tool. Out of scope for Phase 12.
- **Mount-namespace isolation for `run_shell`** — already deferred to v1.2
  in REQUIREMENTS.md Out-of-Scope.
- **`mare-toolbox` MCP server name change** — if the canonical name ever
  changes from `mare-toolbox` to something else, the regression test regex
  (`mcp__mare[-_]\w+__\w+`) and SKILL.md prose update accordingly.
  Documented here so the rename is a deliberate decision, not a silent
  drift.

</deferred>

---

*Phase: 12-orchestrator-skill-update*
*Context gathered: 2026-05-20*
