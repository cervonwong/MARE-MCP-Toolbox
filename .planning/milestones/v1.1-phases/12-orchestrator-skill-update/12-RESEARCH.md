# Phase 12: Orchestrator Skill Update - Research

**Researched:** 2026-05-20
**Domain:** Claude Code skill authoring + MCP tool surface documentation + pytest regression discipline
**Confidence:** HIGH

## Summary

Phase 12 is a documentation-and-regression-test phase, not a code phase. All decisions are locked in `12-CONTEXT.md` (D-01..D-18). The phase rewrites `workspace/.claude/skills/malware-analysis-orchestrator/` (SKILL.md + 5 references files + 7 new W-N files + 1 new index) and adds one regression test under `mcp-gateway/tests/`. Two scripts in the skill (`init_status_tree.sh`, `update_state.py`) get thin extensions for `dynamic_mode_enabled` / `dynamic_capabilities` population in `CURRENT_STATE.json`.

Every claim in this document is verified against in-repo sources. The v1.1 tool surface is locked at 54 baseline / 61 with `MCP_GATEWAY_DYNAMIC_TOOLS=1` (regression-tested in `mcp-gateway/tests/test_tool_list.py`). The pytest scaffolding, marker discipline, path-resolution pattern, and soft-warn precedent (Phase 8/9) all exist and are reused without modification.

**Primary recommendation:** Treat CONTEXT.md D-01..D-18 as the spec; this research supplies the verified file paths, exact tool names, and concrete patterns the planner needs to write tasks. Pick `caplog`/`UserWarning` for D-13 soft snapshot to mirror the existing `test_collision_check.py` / `test_auth.py` `caplog.set_level()` pattern — both exist in the codebase.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Backend Priority Documentation (SKILL-01)**
- **D-01:** SKILL.md "Disassembly and Decompilation" section is rewritten to list priority as `IDA Pro MCP > Binary Ninja MCP > Ghidra MCP > r2 (CLI)`, matching `mcp-gateway/README.md:71` and `mcp-gateway/src/mcp_gateway/app.py`. The v1.0 doc-drift (BN-first ordering in SKILL.md:141-143) is corrected everywhere it appears — top-level SKILL.md, `references/workflow.md`, `references/deep-analysis-checklist.md`, and the per-workflow files (`references/workflows/W-N-*.md`).
- **D-02:** Skill teaches the agent to call `mcp__mare-toolbox__get_active_backend()` FIRST when in gateway mode (to discover which backend is actually pinned at runtime), then use the backend's NATIVE tool names (e.g., `decompile(addr)`, `list_funcs(...)`, `xrefs_to(...)`). Carries a short legacy-prefix appendix listing `mcp__ida_mcp__*`, `mcp__binary_ninja_headless_mcp__*`, `mcp__ghidra_headless_mcp__*` for local-script-mode users.

**Deep RE Checklists W-1..W-7 (SKILL-02)**
- **D-03:** Each W-1..W-7 lives in its OWN file at `references/workflows/W-N-<slug>.md` (seven files total). Sources verbatim from `.planning/research/FEATURES.md` §W-1..W-7 (lines 223-310), reformatted for skill consumption.
- **D-04:** A new index file at `references/deep-re-workflows.md` lists all seven workflows with one-line summaries + entry conditions. SKILL.md Workflow Decision Tree is extended to route by `detected_format` + signals into the appropriate W-N file. Agent retains override discretion.
- **D-05:** Each W-N file lists steps with three columns (or three lines per step): Gateway-mode call, Local-script fallback, Expected artifact path.
- **D-06:** `references/deep-analysis-checklist.md` is preserved as the component-prioritization framework (existing structure stays) and gains a new "Workflow Selection" subsection that points at the W-N files. No content overlap.

**Dual-Mode Detection & Branching (SKILL-03)**
- **D-07:** Mode detection runs ONCE at skill init. Skill probes the MCP surface for sentinel tool `run_shell` (canonical because it exists only in gateway mode). Secondary confirmation: `get_active_backend` tool presence. Result is cached to `<case_dir>/CURRENT_STATE.json` as `"mode": "gateway"` or `"mode": "scripts"`. Subsequent steps read this field rather than reprobing.
- **D-08:** Branching style is SKILL.md/references prose-carried — every step in W-1..W-7 lists both the gateway and the scripts/ form per D-05. Existing scripts under `workspace/.claude/skills/malware-analysis-orchestrator/scripts/` are NOT modified for mode awareness — they ARE the canonical local-script path.
- **D-09:** Decision rule applied at each step:
  ```
  if state.mode == "gateway":
      call mcp__mare-toolbox__run_X(...)
  else:
      call scripts/<fallback>.sh ...
      # or: run_shell <tool> ... when no script exists and gateway is up
  ```
- **D-10:** The `mare-toolbox` server name in `.mcp.json` is canonical (sourced from `run_docker.sh:66`). Host-side tool prefix is `mcp__mare-toolbox__*`. Skill text uses this exact spelling everywhere.

**Regression Test (SKILL-03 CI gate)**
- **D-11:** Test file: `mcp-gateway/tests/test_skill_md_dual_mode.py`. Path resolution via `Path(__file__).resolve().parents[2] / "workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md"`.
- **D-12:** Detection rule regex-based, not literal-snapshot: For every line matching `re.compile(r"mcp__mare[-_]\w+__\w+")`, the enclosing block (paragraph OR list-item with ± 3 lines of trailing context) MUST contain at least one of: substring `scripts/`, word `fallback` (case-insensitive), or `else` branch keyword. Failures emit `file:line: <snippet>` for every offending block.
- **D-13:** Soft snapshot check (advisory only, never fails CI on its own): test computes sha256 of SKILL.md and compares to `mcp-gateway/tests/snapshots/SKILL.md.sha256`. Drift emits a warning via `pytest.warns(UserWarning, ...)` or captured `print`. Refresh path: `UPDATE_SKILL_SNAPSHOT=1 pytest ...::test_skill_md_snapshot` rewrites the .sha256 file.
- **D-14:** Test also exercises the W-N reference files (same regex applied to every `references/workflows/W-*.md`). Reuses one parametrized test function over `(SKILL.md, W-1.md, ..., W-7.md, references/*.md)`.

**Dynamic Mode in CURRENT_STATE.json (SKILL-04)**
- **D-15:** `CURRENT_STATE.json` schema gains:
  - `"dynamic_mode_enabled": bool`
  - `"dynamic_capabilities": { "ptrace_scope": int|null, "binfmt_misc": bool, "qemu_archs": [...], "netns_feasible": bool }` — mirrors `get_dynamic_capabilities()` return shape.
- **D-16:** Population path is mode-aware:
  - Gateway mode: `scripts/init_status_tree.sh` shells out to call `mcp__mare-toolbox__get_dynamic_capabilities()` via MCP client (shell+curl+jq OR Python `mcp` SDK). If gateway is up but dynamic mode off, `dynamic_mode_enabled=false`, `dynamic_capabilities={}`.
  - Scripts mode: `scripts/init_status_tree.sh` invokes existing `scripts/probe_dynamic_tools.sh` and parses output into the same JSON shape. Failure → `dynamic_mode_enabled=false` + INDEX.md note.
- **D-17:** Re-probe path: `scripts/update_state.py --probe-dynamic` re-runs the population logic and updates `CURRENT_STATE.json` in place.
- **D-18:** Skip behavior for dynamic-only steps: **placeholder artifact + INDEX.md note** is MANDATORY:
  - Placeholder: `<case_dir>/dynamic/<step>-skipped.md` containing (1) which step, (2) missing capability, (3) one-line remediation hint.
  - INDEX.md entry: row in new "skipped steps" subsection (step + reason + placeholder path).

### Claude's Discretion

- Exact format inside each W-N file (three-column table vs. numbered list).
- Whether D-16 gateway-mode probe lives in shell (curl + jq) or Python (`mcp` SDK).
- Soft snapshot mechanism (D-13): `pytest.warns` vs. captured-print vs. `pytest.skip` carrying hint.
- Whether `references/agent-roles.md` and `references/interesting-signals.md` need updates beyond D-01.
- Exact W-N filename slugs (e.g., `W-1-packed-binary-triage.md` vs. `W1-packed.md`); regex enumerates by `W-*.md` glob.

### Deferred Ideas (OUT OF SCOPE)

- W-5b: Network-aware dynamic trace (`allow_network=true` against INetSim/FakeDNS) — v1.2.
- `extract_embedded_files` composite tool — future "composite tools" phase.
- Auto-routing into W-N via a Workflow tool (`select_workflow(case_dir) -> workflow_id`).
- Mount-namespace isolation for `run_shell` — v1.2.
- `mare-toolbox` MCP server name change — would require regex + prose update.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SKILL-01 | Reflect backend priority `IDA > BN > Ghidra` (correcting v1.0 doc drift) | Verified canonical priority in `mcp-gateway/README.md:71` ("IDA > Binary Ninja > Ghidra"). Current SKILL.md:141-143 has BN-first ordering and lists `mcp__ida_mcp__*` is missing; `mcp__binary_ninja_headless_mcp__*` and `mcp__ghidra_headless_mcp__*` are documented. Files needing sweep: SKILL.md (lines 102, 141-143, 159-164, 208-260), references/workflow.md (no current refs but cross-reference will land here), references/deep-analysis-checklist.md (no current refs, gains "Workflow Selection" subsection per D-06), references/agent-roles.md (tool-agnostic; likely no edits), references/interesting-signals.md (tool-agnostic; likely no edits), W-N files (new, all must use correct priority). |
| SKILL-02 | Encode W-1..W-7 deep RE checklists mapping findings → tools, with `run_shell` fallbacks | Source material verbatim in `.planning/research/FEATURES.md` §W-1..W-7 (lines 220-310). Verified all referenced wrappers exist on the v1.1 tool surface: `run_file`, `run_die`, `run_xxd`, `run_rabin2`, `run_readelf`, `run_nm`, `run_capstone_disasm`, `run_ropper`, `run_jq`, `run_yq` (re_static.py); `run_binwalk`, `run_unblob`, `run_upx_test/list/unpack`, `list_extracted_files`, `promote_extracted_sample` (extract.py); `open_r2_session`, `r2_cmd`, `close_r2_session` (r2_sessions.py); `start_tool_job`, `get_tool_job`, `cancel_tool_job`, `list_tool_jobs` (jobs.py); `run_strace`, `run_ltrace`, `run_qemu_user`, `open_gdb_session`, `gdb_exec`, `close_gdb_session` (dynamic.py, env-gated); `write_artifact`, `append_artifact` (re_artifacts.py); `run_shell` (shell.py). |
| SKILL-03 | Dual-mode operation preserved per-step; regression test fails CI on unconditional `mcp__mare__*` with no fallback | Existing pytest infrastructure (`mcp-gateway/tests/conftest.py`, marker discipline, `Path(__file__).resolve().parents[N]` pattern) reusable as-is. No new test scaffolding needed. The regex `r"mcp__mare[-_]\w+__\w+"` matches the `mcp__mare-toolbox__*` prefix used everywhere downstream (verified against `run_docker.sh:66`). Caplog/`pytest.warns` precedent exists in `test_collision_check.py` and `test_auth.py`. |
| SKILL-04 | Mark dynamic mode in `CURRENT_STATE.json`; skip dynamic-only steps with noted reason | `get_dynamic_capabilities()` return shape (verified in `mcp-gateway/src/mcp_gateway/dynamic.py:304-319` DynamicCapabilities dataclass) provides: `probed_at`, `dynamic_mode_enabled`, `ptrace_scope`, `ptrace_traceme_works`, `binfmt_misc_mounted`, `qemu_architectures` (tuple), `qemu_static_binaries` (tuple), `netns_feasible`, `unshare_path`, `gdb_path`, `gdb_version`, `strace_path`, `ltrace_path`, `warnings`. D-15 schema is a documented subset. `scripts/probe_dynamic_tools.sh` (project root, verified present at `scripts/probe_dynamic_tools.sh:1-121`) produces parseable `[OK]/[WARN]/[INFO]` lines and exit code 0/1 — scripts-mode source. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

**Project root `CLAUDE.md`:**
- Recommended stack pinned: `mcp-gateway` 0.1.0+ (custom FastMCP), `mcp` Python SDK 1.27.0+, Streamable HTTP transport, bearer-token auth. Skill text MUST use these exact identifiers and not introduce alternatives.
- `mcp-gateway/pyproject.toml` pins `mcp>=1.27,<1.28` — D-13 snapshot mechanism may rely on `pytest.warns` (stable across 1.27.x) but the regression test itself uses `mcp.server.fastmcp` only indirectly (it just reads markdown files).
- "Do NOT Use" includes `MastraMCPClient` (legacy), `mcp-remote` (CVE-2025-6514), SSE transport (deprecated), `mcp-proxy` for the gateway role — the skill should not reference any of these.
- GSD Workflow Enforcement: file edits must go through GSD phases — this phase is the entry point for all skill changes.

**`workspace/CLAUDE.md` (inner-agent CLAUDE.md, runs INSIDE the container):**
- Inner agent auto-discovers skills from `.claude/skills/`. SKILL.md frontmatter (`name:`/`description:`) MUST be preserved verbatim shape so skill discovery stays unbroken. (Current frontmatter at SKILL.md:1-4 verified.)
- Inner agent operates in scripts-mode by default (`.mcp.json` configures the disassembler MCP backend directly). The skill's scripts-mode path must remain executable from the inner agent's perspective.
- Inner agent's workspace layout: samples at workspace root, `status/` for case dirs, `mcp/` for backend repos. Skill scripts already assume this layout (`init_status_tree.sh:33` uses `STATUS_ROOT="status"`).

## Standard Stack

### Core (in-repo, no install needed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | >=8 (per `mcp-gateway/pyproject.toml`) | Regression test framework | [VERIFIED: pyproject.toml] Already used for 39 existing gateway tests. Reuse without addition. |
| pytest-asyncio | >=0.23 | Async test mode | [VERIFIED: pyproject.toml] `asyncio_mode = "auto"`. Phase 12 test is sync (file reading), so async is unused but framework loaded. |
| mcp (Python SDK) | >=1.27,<1.28 | MCP protocol if D-16 takes Python route | [VERIFIED: pyproject.toml] Available; required for `ClientSession` if init_status_tree.sh goes Python. |
| Python stdlib `re`, `pathlib`, `hashlib`, `json`, `subprocess` | 3.12+ | Test logic + dynamic-cap probe parsing | [VERIFIED: project uses Python 3.12.3] No new deps. |

### Supporting (skill-side, runs inside container)
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| bash | 5.x | scripts/init_status_tree.sh, update_state.py invocations | scripts mode; gateway-mode init_status_tree.sh also shells out |
| jq | bundled in Kali | Parse MCP JSON response in shell-route D-16 | If D-16 takes shell-curl route to call `get_dynamic_capabilities()` |
| curl | bundled in Kali | Hit `http://127.0.0.1:8080/mcp` with bearer token | If D-16 takes shell-curl route |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pytest.warns(UserWarning, ...)` for D-13 soft snapshot | `caplog.set_level(WARNING, ...)` + `caplog.records` inspection | `caplog` matches existing precedent in `test_collision_check.py:83` + `test_auth.py:75`. Either works; `caplog` is more visible in CI logs because pytest prints captured WARN+ records by default. |
| shell+curl+jq for D-16 gateway-mode probe | Python script importing `mcp.client.streamable_http.streamablehttp_client` | Shell route keeps `init_status_tree.sh` self-contained, no new Python dep. Python route is more robust to MCP protocol changes but adds a new module. **Recommendation: shell route**, mirroring the existing `scripts/probe_dynamic_tools.sh` pattern (bash + grep + read). |
| `pytest.warns(UserWarning)` for D-13 | Captured `print()` checked via `capsys.readouterr().out` | `print()` is even less ceremony but doesn't have a structured assertion target. `pytest.warns` is preferred when refresh-hint visibility matters. |
| Three-column markdown table per W-N step | Numbered list with three sub-bullets per step | Markdown table renders more compact, easier to grep "step | gateway-call | scripts-call | artifact"; sub-bullet list flows more naturally in narrative prose. Either passes D-12 regex check. **Recommendation: table** for explicit per-row gateway/scripts/artifact mapping. |

**Installation:** None. All tooling is already in the gateway dev env and Kali container.

**Version verification:**
```bash
python3 --version       # 3.12.3 [VERIFIED]
pytest --version        # available via pyproject.toml extra [VERIFIED]
grep "mcp>=" /home/cervon/Code/MARE-MCP-Toolbox/mcp-gateway/pyproject.toml  # mcp>=1.27,<1.28 [VERIFIED]
```

## Architecture Patterns

### Recommended Project Structure (no changes; in-place edits)
```
workspace/.claude/skills/malware-analysis-orchestrator/
├── SKILL.md                              # EDIT (D-01, D-02, D-04 decision tree, dual-mode section)
├── references/
│   ├── workflow.md                       # EDIT (D-01 sweep, D-04 W-N cross-reference)
│   ├── deep-analysis-checklist.md        # EDIT (D-06 "Workflow Selection" subsection)
│   ├── deep-re-workflows.md              # NEW (D-04 index)
│   ├── workflows/
│   │   ├── W-1-packed-binary-triage.md   # NEW (D-03)
│   │   ├── W-2-elf-deep-dive.md          # NEW (D-03)
│   │   ├── W-3-pe-deep-dive.md           # NEW (D-03)
│   │   ├── W-4-rop-gadget-hunt.md        # NEW (D-03)
│   │   ├── W-5-dynamic-api-trace.md      # NEW (D-03)
│   │   ├── W-6-firmware-unpack.md        # NEW (D-03)
│   │   └── W-7-cross-arch-iot.md         # NEW (D-03)
│   ├── agent-roles.md                    # PROBABLY UNCHANGED (tool-agnostic; review-only)
│   ├── interesting-signals.md            # PROBABLY UNCHANGED (tool-agnostic; review-only)
│   └── artifact-spec.md                  # EDIT (D-15: extend CURRENT_STATE.json schema doc)
├── scripts/
│   ├── init_status_tree.sh               # EXTEND (D-16: populate dynamic_mode_enabled + dynamic_capabilities)
│   ├── update_state.py                   # EXTEND (D-17: --probe-dynamic flag + new fields in JSON)
│   ├── collect_strings.sh                # NO CHANGE (D-08)
│   ├── collect_imports.sh                # NO CHANGE (D-08)
│   ├── scan_yara.sh                      # NO CHANGE (D-08)
│   ├── scan_capa.sh                      # NO CHANGE (D-08)
│   ├── build_hypothesis.py               # NO CHANGE (D-08)
│   ├── rank_signals.py                   # NO CHANGE (D-08)
│   └── resolve_case.sh                   # NO CHANGE (D-08)
└── assets/                               # NO CHANGE
mcp-gateway/tests/
├── test_skill_md_dual_mode.py            # NEW (D-11..D-14)
└── snapshots/
    └── SKILL.md.sha256                   # NEW (D-13 soft snapshot baseline)
```

### Pattern 1: Markdown frontmatter preservation
**What:** Claude's skill auto-discovery reads `name:` and `description:` from YAML frontmatter at the top of SKILL.md.
**When to use:** Every SKILL.md edit.
**Verified format (from workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md:1-4):**
```markdown
---
name: malware-analysis-orchestrator
description: Structured malware triage and reverse-engineering orchestration for PE, ELF, and Mach-O binaries with strict artifact dumping to a status folder. Use when requests involve malware sample analysis, strings triage, API/import analysis, behavioral hypothesis generation, component mapping, deep-analysis planning, Binary Ninja MCP usage, Ghidra MCP usage, or role-based orchestration (orchestrator/planner/reporter) with complete intermediate outputs.
---
```
**Recommendation:** The `description:` field currently mentions "Binary Ninja MCP usage, Ghidra MCP usage" — extend to "IDA Pro MCP, Binary Ninja MCP, or Ghidra MCP usage" without breaking the discovery surface. Single-line; YAML scalars don't tolerate raw newlines without `>-` folding.

### Pattern 2: Per-step gateway+fallback documentation (D-05)
**What:** Each step in a W-N file documents three things: gateway-mode call, scripts-mode fallback, expected artifact path.
**Source:** Established in `.planning/research/FEATURES.md` §W-1..W-7. D-05 lifts that pattern into skill files.
**Example (W-2 step 2, three-line form):**
```markdown
2. Static metadata harvest (rabin2 -j all)
   - Gateway: `mcp__mare-toolbox__run_rabin2(case_dir, sample, command="all", json=true)`
   - Scripts: `scripts/collect_imports.sh <sample>` (writes 03_imports_raw.txt with rabin2 imports/libs)
   - Artifact: `<case_dir>/00_sample_profile.md` (rabin2 section) + `<case_dir>/tool-logs/rabin2-*.json`
```

**Example (three-column table form):**
```markdown
| # | Step | Gateway-mode | Scripts-mode fallback | Artifact |
|---|------|--------------|------------------------|----------|
| 2 | Static metadata | `mcp__mare-toolbox__run_rabin2(case_dir, sample, command="all", json=true)` | `scripts/collect_imports.sh <sample>` | `<case_dir>/00_sample_profile.md`, `tool-logs/rabin2-*.json` |
```

**Recommendation:** Table form for the W-N files (denser, regex-friendlier). Prose form for SKILL.md sections quoting one step inline.

### Pattern 3: pytest path resolution from project root (verified)
**What:** Reach across the repo boundary from `mcp-gateway/tests/test_*.py` to project-root assets.
**Source:** `mcp-gateway/tests/test_readme_structure.py:13`: `REPO_ROOT = Path(__file__).resolve().parents[2]`. Two-parents-up because `mcp-gateway/tests/test_X.py → mcp-gateway/tests/ → mcp-gateway/ → REPO_ROOT`.
**Example for D-11:**
```python
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "workspace/.claude/skills/malware-analysis-orchestrator"
SKILL_MD = SKILL_DIR / "SKILL.md"
WORKFLOW_FILES = sorted(SKILL_DIR.glob("references/workflows/W-*.md"))
REFS = [SKILL_DIR / "references" / name for name in ("workflow.md", "deep-analysis-checklist.md", "deep-re-workflows.md")]
```

### Pattern 4: Soft-warn precedent
**What:** Tests that surface advisory drift without failing CI.
**Source:** `mcp-gateway/tests/test_collision_check.py:83`: `caplog.set_level(logging.ERROR, logger="mcp_gateway.collision_check")`. `mcp-gateway/tests/test_auth.py:71-77`: same `caplog` idiom.
**Recommendation for D-13:**
```python
import warnings
def test_skill_md_snapshot():
    actual = hashlib.sha256(SKILL_MD.read_bytes()).hexdigest()
    snap = SKILL_DIR.parent.parent.parent.parent.parent / "mcp-gateway/tests/snapshots/SKILL.md.sha256"
    # ...path adjusted; use REPO_ROOT helper
    if os.environ.get("UPDATE_SKILL_SNAPSHOT") == "1":
        snap.write_text(actual + "\n")
        return
    expected = snap.read_text().strip() if snap.exists() else ""
    if actual != expected:
        warnings.warn(
            f"SKILL.md sha256 drift: actual={actual} expected={expected}. "
            f"Refresh: UPDATE_SKILL_SNAPSHOT=1 pytest mcp-gateway/tests/test_skill_md_dual_mode.py::test_skill_md_snapshot",
            UserWarning,
        )
```
This emits a UserWarning that surfaces in pytest's warning summary at end-of-run. No `pytest.warns(...)` ctx-manager needed (that's for asserting expected warnings).

### Anti-Patterns to Avoid

- **Literal byte snapshot of SKILL.md as the hard test.** Every legitimate prose edit would fail the test. D-12 (regex content rule) is the hard gate; D-13 (sha256) is advisory.
- **Adding `if/else` in scripts/*.sh to make them mode-aware.** Per D-08, scripts ARE the canonical local-script path. Don't fork them. The skill prose carries the mode decision.
- **Pre-loading all W-N files in SKILL.md.** Per Specifics in CONTEXT.md, W-N files are deliberately small (~30-80 lines each) so the agent loads only relevant ones via the Workflow Decision Tree. SKILL.md should reference, not inline.
- **Renaming the `mare-toolbox` MCP server key.** Locked in `run_docker.sh:66`. Changing it cascades through every skill file AND the regression-test regex.
- **Calling `mcp__mare__*` (legacy / wrong prefix).** Canonical prefix is `mcp__mare-toolbox__*` derived from the `.mcp.json` key. D-12 regex `mcp__mare[-_]\w+__\w+` accommodates both spellings but the prose must use `mare-toolbox`.
- **Re-probing dynamic capabilities in every W-N step.** Per D-07, mode + capability probe runs ONCE at skill init; subsequent steps READ `CURRENT_STATE.json`. The re-probe path (D-17) is operator-triggered, not per-step.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Detect dynamic-mode capabilities | New shell probe in init_status_tree.sh | Reuse `scripts/probe_dynamic_tools.sh` (project root, 121 lines, Phase 11) for scripts-mode; call `mcp__mare-toolbox__get_dynamic_capabilities()` for gateway-mode | Phase 11 already shipped this probe; it tests unshare, ptrace_scope, gdb, strace, ltrace, binfmt_misc + F flag, qemu-*-static binaries, SYS_PTRACE. Re-implementing risks drift from the canonical capability shape. |
| Compute backend-tool surface at runtime | Hardcode IDA/BN/Ghidra tool lists in SKILL.md | Skill teaches the agent to call `mcp__mare-toolbox__get_active_backend()` first, then use native tool names | Backend wins on name collisions (gateway D-14). Skill prose cannot anticipate which backend is pinned in any given container start. |
| Parse MCP JSON-RPC in shell for D-16 gateway probe | New JSON parser in bash | `jq` (bundled in Kali) + `curl --silent -H "Authorization: Bearer $TOKEN" ...` | `jq` is the project's existing JSON tool; `tools/__init__.py` registers `run_jq` for the agent path. |
| Test that SKILL.md mentions every tool | New surface-coverage test | Existing `mcp-gateway/tests/test_tool_list.py::test_atomic_tools_map_to_scripts` already enforces 1:1 between scripts/ and tools/ at gateway level | Surface coverage is a gateway concern. The skill regression test is narrower: enforce dual-mode prose per occurrence. |
| Manage W-N decision routing | New `select_workflow(case_dir) -> workflow_id` MCP tool | Prose-style decision tree in SKILL.md routed by `detected_format` + signals | Out of scope per CONTEXT.md `<deferred>`. v1.1 keeps the orchestrator skill as the composer. |
| Track skipped dynamic steps | New artifact convention | Reuse existing INDEX.md sectioning + add `<case_dir>/dynamic/<step>-skipped.md` placeholders per D-18 | INDEX.md already has "Missing Artifacts" section (`update_state.py:73`); D-18's "skipped steps" subsection extends that pattern. |

**Key insight:** Phase 12 is glue documentation — every primitive it touches already exists in the gateway or in the existing scripts. Don't invent new building blocks; map the existing ones.

## Runtime State Inventory

> Phase 12 includes file additions/edits but is NOT a rename/refactor. Runtime state risk is LOW. Categories audited explicitly:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — case dirs use `status/<NNN>-<filename>/` (relative paths); no databases, no embedded sample IDs in renamed strings. `CURRENT_STATE.json` schema extension is additive (D-15) — backward compatible by definition. | None — `update_state.py:92-107` builds the JSON from scratch each call, so older case dirs auto-upgrade on next `--phase` invocation. |
| Live service config | `mare-toolbox` server name in `.mcp.json` (canonical per D-10, `run_docker.sh:66`) — referenced in skill prose but unchanged in this phase. No external services have the old skill content cached. | None. Skill is loaded fresh each Claude Code session via filesystem read. |
| OS-registered state | None — skill is not registered with systemd, launchd, or any OS task scheduler. Discovery is via Claude Code reading `.claude/skills/` at session start. | None. |
| Secrets/env vars | `MCP_GATEWAY_TOKEN` (existing, no rename) — referenced if D-16 takes shell-curl route. `MCP_GATEWAY_DYNAMIC_TOOLS` env var (existing, no rename) — read by `dynamic.probe_all()`. `UPDATE_SKILL_SNAPSHOT` is a NEW env var introduced by D-13 for snapshot refresh. Document in test docstring. | Document new `UPDATE_SKILL_SNAPSHOT` env var in test docstring + `mcp-gateway/tests/README.md` if one exists. |
| Build artifacts / installed packages | No installed packages reference the skill. `mcp-gateway/tests/` is collected by pytest at runtime — new `test_skill_md_dual_mode.py` is picked up automatically (no conftest changes needed per CONTEXT.md Integration Points). | None. |

**Nothing found in category:** Explicitly verified — no stored data, OS state, or build-artifact churn risks from this phase.

## Common Pitfalls

### Pitfall 1: Frontmatter break
**What goes wrong:** Editing SKILL.md's `description:` field can introduce a multi-line YAML scalar or stray colons that break Claude's skill discovery parser.
**Why it happens:** Markdown editors don't enforce YAML syntax; long single-line descriptions tempt newlines.
**How to avoid:** Keep `name:` and `description:` on single lines. Validate after edit: `python3 -c "import yaml,sys; print(next(yaml.safe_load_all(open('SKILL.md'))))"`.
**Warning signs:** Skill stops auto-discovering; inner agent doesn't load `malware-analysis-orchestrator`.

### Pitfall 2: Regex false-positive in code blocks
**What goes wrong:** D-12 regex `mcp__mare[-_]\w+__\w+` matches inside fenced code blocks where there's no narrative `scripts/`/fallback context, even though the example is correct.
**Why it happens:** A code-fenced example calling `mcp__mare-toolbox__run_die(...)` in isolation may not have "scripts/" in its ±3 lines.
**How to avoid:** Either (a) keep ±3-line window wide enough that the surrounding prose introduces the example with "Gateway-mode" or "scripts-mode fallback below", or (b) ensure every code fence is paired with a fallback fence within the same paragraph/list-item block. Recommended: paragraph-level scope check, not just ±3 lines.
**Warning signs:** Test fails on a SKILL.md that is *intuitively* correct.

### Pitfall 3: `mcp__mare__*` vs `mcp__mare-toolbox__*` ambiguity
**What goes wrong:** D-12 regex deliberately matches both `mcp__mare__X` and `mcp__mare-toolbox__X` via `mare[-_]\w+`. Prose author writes `mcp__mare__run_die` (legacy/abbreviated), test passes because it has a `scripts/` fallback in the block, but the runtime tool call FAILS because the actual prefix is `mcp__mare-toolbox__run_die`.
**Why it happens:** The regex is content-shape, not name-correctness.
**How to avoid:** Add a second narrower test or a lint rule: every occurrence of `mcp__mare__` (without `-toolbox`) is an error. Or assert the prefix is exactly `mcp__mare-toolbox__` in the regex.
**Warning signs:** Skill prose passes regex but agent reports "tool not found" on first invocation.
**Recommendation:** Tighten the regex for the dual-mode check to `r"mcp__mare-toolbox__\w+"`. Use the broader `mare[-_]` pattern only in a separate test that flags any abbreviated form as a hard fail.

### Pitfall 4: `parents[2]` brittleness on test relocation
**What goes wrong:** If a future refactor moves `mcp-gateway/tests/` (e.g., to `mcp-gateway/src/mcp_gateway/tests/`), `parents[2]` walks to the wrong root.
**Why it happens:** Path math hardcodes directory depth.
**How to avoid:** Helper inside the test module: `REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".planning").is_dir())`.
**Warning signs:** Test imports succeed but assertion targets read empty/wrong files.

### Pitfall 5: Stale `dynamic_capabilities` in CURRENT_STATE.json
**What goes wrong:** Operator starts container without `--dynamic`, runs init, gets `dynamic_mode_enabled=false`. Later restarts container with `--dynamic` but forgets to re-init. Agent reads stale JSON, skips dynamic steps unnecessarily.
**Why it happens:** D-17 re-probe is operator-triggered, not automatic.
**How to avoid:** Document the re-probe explicitly in SKILL.md and add a one-liner remediation in W-5/W-6/W-7: "If skipped due to dynamic_mode_enabled=false but you've since enabled it, run `scripts/update_state.py --probe-dynamic --status-dir <case_dir>`".
**Warning signs:** Dynamic mode is on but skill behaves as if it's off; CURRENT_STATE.json shows `probed_at` from a previous session.

### Pitfall 6: Init_status_tree.sh gateway-mode probe deadlock
**What goes wrong:** If D-16 takes the shell+curl route AND the gateway is starting up when init_status_tree.sh runs, the curl call hangs or returns 503, init_status_tree.sh exits with junk JSON.
**Why it happens:** MCP gateway has a startup delay (lifespan probe runs `probe_all()` synchronously); during that window the HTTP endpoint may not be ready.
**How to avoid:** Add a `curl --max-time 3 --retry 5 --retry-delay 1 --retry-connrefused` pattern, treat any non-200 as "probe failed → write `dynamic_mode_enabled=false` + INDEX.md note", per D-16.
**Warning signs:** First-run case dirs after `./run_docker.sh --remote --dynamic` show `dynamic_mode_enabled=false` despite dynamic mode being enabled.

### Pitfall 7: W-N file count drift vs test parametrization
**What goes wrong:** D-14 enumerates W-N files by glob `references/workflows/W-*.md`. Adding W-8 in a future phase silently extends the test surface; removing W-3 silently shrinks it.
**Why it happens:** Glob-based enumeration is convenient but doesn't pin the expected count.
**How to avoid:** Assert `len(WORKFLOW_FILES) == 7` at the top of the test parametrization. Future W-N additions require both a new file AND a test bump (intentional review point).
**Warning signs:** Test passes after someone deletes W-4 because the remaining six all conform.

### Pitfall 8: `description:` length growing too long
**What goes wrong:** Adding "IDA Pro MCP, Binary Ninja MCP, Ghidra MCP usage" to the description pushes it past a token-budget threshold for Claude's skill auto-discovery selection.
**Why it happens:** Description field is used for skill selection prompts; very long descriptions reduce signal-to-noise.
**How to avoid:** Keep the description action-oriented and tool-aware but not exhaustive. Verify final length is comparable to the current 461 characters.
**Warning signs:** Skill is no longer selected when user asks "analyze this malware sample" — Claude picks a more concise skill.

## Code Examples

Verified patterns from existing project sources.

### Example 1: Reading SKILL.md with regex-based content check (D-12)
```python
# Source: pattern from mcp-gateway/tests/test_readme_structure.py:18-21
# Adapted for SKILL.md dual-mode check.
from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_MD = REPO_ROOT / "workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md"

GATEWAY_TOOL_RE = re.compile(r"mcp__mare[-_]\w+__\w+")
FALLBACK_RE = re.compile(r"scripts/|\bfallback\b|\belse\b", re.IGNORECASE)

def check_dual_mode(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_number, snippet) for offending blocks."""
    lines = path.read_text(encoding="utf-8").splitlines()
    offenses = []
    for i, line in enumerate(lines):
        if not GATEWAY_TOOL_RE.search(line):
            continue
        # ±3-line window
        lo = max(0, i - 3)
        hi = min(len(lines), i + 4)
        window = "\n".join(lines[lo:hi])
        if not FALLBACK_RE.search(window):
            offenses.append((i + 1, line.strip()))
    return offenses

def test_skill_md_has_fallback_for_every_gateway_tool():
    offenses = check_dual_mode(SKILL_MD)
    assert not offenses, "missing dual-mode fallback:\n" + "\n".join(
        f"  {SKILL_MD.name}:{ln}: {snip}" for ln, snip in offenses
    )
```

### Example 2: Parametrized check across SKILL.md + W-N + references (D-14)
```python
import pytest

WORKFLOW_FILES = sorted((REPO_ROOT / "workspace/.claude/skills/malware-analysis-orchestrator"
                                     / "references/workflows").glob("W-*.md"))
REF_FILES = [
    REPO_ROOT / "workspace/.claude/skills/malware-analysis-orchestrator/references/workflow.md",
    REPO_ROOT / "workspace/.claude/skills/malware-analysis-orchestrator/references/deep-re-workflows.md",
]
ALL_FILES = [SKILL_MD, *WORKFLOW_FILES, *REF_FILES]

def test_workflow_count_locked():
    """Pitfall 7: assert exactly 7 W-N files; drift requires test bump."""
    assert len(WORKFLOW_FILES) == 7, (
        f"expected 7 W-N workflow files (W-1..W-7), found {len(WORKFLOW_FILES)}: "
        f"{[p.name for p in WORKFLOW_FILES]}"
    )

@pytest.mark.parametrize("doc", ALL_FILES, ids=lambda p: p.name)
def test_dual_mode_invariant(doc: Path):
    """D-14: every gateway-tool reference in skill docs has a fallback in context."""
    offenses = check_dual_mode(doc)
    assert not offenses, (
        f"\nDual-mode regression in {doc.relative_to(REPO_ROOT)}:\n"
        + "\n".join(f"  L{ln}: {snip}" for ln, snip in offenses)
    )
```

### Example 3: Soft snapshot via UserWarning (D-13)
```python
import hashlib
import os
import warnings

SNAPSHOT_FILE = REPO_ROOT / "mcp-gateway/tests/snapshots/SKILL.md.sha256"

def test_skill_md_snapshot():
    actual = hashlib.sha256(SKILL_MD.read_bytes()).hexdigest()
    if os.environ.get("UPDATE_SKILL_SNAPSHOT") == "1":
        SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_FILE.write_text(actual + "\n")
        return  # Refresh-mode is always green.
    if not SNAPSHOT_FILE.is_file():
        warnings.warn(
            f"SKILL.md snapshot missing at {SNAPSHOT_FILE.relative_to(REPO_ROOT)}. "
            f"Create with: UPDATE_SKILL_SNAPSHOT=1 pytest "
            f"mcp-gateway/tests/test_skill_md_dual_mode.py::test_skill_md_snapshot",
            UserWarning,
        )
        return
    expected = SNAPSHOT_FILE.read_text().strip()
    if actual != expected:
        warnings.warn(
            f"SKILL.md sha256 drift detected.\n"
            f"  actual:   {actual}\n"
            f"  expected: {expected}\n"
            f"  refresh:  UPDATE_SKILL_SNAPSHOT=1 pytest "
            f"mcp-gateway/tests/test_skill_md_dual_mode.py::test_skill_md_snapshot",
            UserWarning,
        )
```

### Example 4: init_status_tree.sh extension for dynamic-cap population (D-16, shell route)
```bash
# Source: pattern from scripts/probe_dynamic_tools.sh:7 (set -euo pipefail discipline)
# Appended to workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh

populate_dynamic_caps() {
  local case_dir="$1"
  local mode="scripts"  # default
  local dyn_enabled="false"
  local dyn_caps_json="{}"

  # Mode detection (D-07): is the gateway up AND reachable?
  if [[ -n "${MCP_GATEWAY_TOKEN:-}" ]] \
     && curl -sf --max-time 3 -H "Authorization: Bearer ${MCP_GATEWAY_TOKEN}" \
            "http://127.0.0.1:${MCP_GATEWAY_HOST_PORT:-8080}/healthz" >/dev/null 2>&1; then
    mode="gateway"
    # Call get_dynamic_capabilities via MCP HTTP. Returns JSON-RPC; jq extracts the result.
    local resp
    resp=$(curl -sf --max-time 5 -X POST \
             -H "Authorization: Bearer ${MCP_GATEWAY_TOKEN}" \
             -H "Content-Type: application/json" \
             -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
                  "params":{"name":"get_dynamic_capabilities","arguments":{}}}' \
             "http://127.0.0.1:${MCP_GATEWAY_HOST_PORT:-8080}/mcp" 2>/dev/null || echo '{}')
    dyn_enabled=$(echo "$resp" | jq -r '.result.content[0].text // "{}" | fromjson | .dynamic_mode_enabled // false' 2>/dev/null || echo "false")
    dyn_caps_json=$(echo "$resp" | jq -c '.result.content[0].text // "{}" | fromjson | {ptrace_scope, binfmt_misc: .binfmt_misc_mounted, qemu_archs: .qemu_architectures, netns_feasible}' 2>/dev/null || echo "{}")
  elif [[ -x "../../scripts/probe_dynamic_tools.sh" ]]; then
    # Scripts-mode path (D-16): parse probe_dynamic_tools.sh stdout.
    # ... parse [OK]/[WARN] lines into the same JSON shape.
    :
  fi

  # Splice into CURRENT_STATE.json via update_state.py --probe-dynamic
  python3 "$SCRIPT_DIR/update_state.py" --status-dir "$case_dir" \
          --probe-dynamic --mode "$mode" \
          --dynamic-enabled "$dyn_enabled" --dynamic-caps "$dyn_caps_json"
}
```

### Example 5: update_state.py extension (D-15/D-17)
```python
# Source: extends workspace/.claude/skills/malware-analysis-orchestrator/scripts/update_state.py
# New args: --probe-dynamic, --mode, --dynamic-enabled, --dynamic-caps
# New keys in state dict: mode, dynamic_mode_enabled, dynamic_capabilities

parser.add_argument("--probe-dynamic", action="store_true")
parser.add_argument("--mode", choices=["gateway", "scripts"], default=None)
parser.add_argument("--dynamic-enabled", default="false")
parser.add_argument("--dynamic-caps", default="{}")
# ...
state.update({
    "mode": args.mode or _existing_mode_or_default(status_dir),  # D-07
    "dynamic_mode_enabled": args.dynamic_enabled.lower() == "true",
    "dynamic_capabilities": json.loads(args.dynamic_caps),
})
```

## State of the Art

| Old Approach (v1.0 skill) | Current Approach (v1.1 skill) | When Changed | Impact |
|---------------------------|-------------------------------|--------------|--------|
| Backend priority `Binary Ninja > Ghidra > r2` (no IDA mention in SKILL.md:141-143) | `IDA Pro MCP > Binary Ninja MCP > Ghidra MCP > r2 (CLI)` per `mcp-gateway/README.md:71` and `app.py` | Phase 1 (IDA backend land), needs propagation now | Doc-drift fix; clients see the same priority gateway enforces |
| `import binaryninja` direct Python API forbidden; use `mcp__binary_ninja_headless_mcp__*` | Use `mcp__mare-toolbox__get_active_backend()` first, then backend-native names (`decompile(addr)`, `list_funcs`, `xrefs_to`) — backend wins on collision | Phase 2 (gateway pass-through) + Phase 7 (collision check) | Backend-native schema reaches the agent; gateway no longer obscures backend richness |
| Local-only scripts mode; SKILL.md "Quick Start" runs `scripts/*` directly | Dual-mode: `run_shell` sentinel detects gateway; W-N files list both forms per step | Phase 7 (`run_shell` lands) + Phase 12 (skill encodes) | Same skill works for inner-container agent (scripts) AND host Claude Code (gateway) |
| No deep-RE workflow catalog | Seven workflow files (W-1..W-7) routed via Workflow Decision Tree | Phase 12 | Agent has explicit recipes for packed/ELF/PE/ROP/dynamic/firmware/cross-arch cases |
| `CURRENT_STATE.json` schema with 7 top-level fields | Adds `mode`, `dynamic_mode_enabled`, `dynamic_capabilities` (3 new, additive) | Phase 12 (D-15) | Subsequent steps can fast-skip dynamic-only work without re-probing |
| Dynamic-only step silently skipped if tooling absent | Placeholder artifact `<case_dir>/dynamic/<step>-skipped.md` + INDEX.md row with reason | Phase 12 (D-18) | Reports never lose track of what was skipped and why |

**Deprecated/outdated:**
- SKILL.md:141-143 BN-first ordering — replaced by IDA-first (D-01)
- SKILL.md:208-260 "Binary Ninja MCP Guidance" + "Ghidra MCP Guidance" as separate equal-weight sections — collapse into a single "Disassembly Backend Guidance" section that defers to `get_active_backend()` (D-02), with the legacy-prefix appendix relegated to a sub-section
- The `tool prefix mcp__binary_ninja_headless_mcp__*` and `mcp__ghidra_headless_mcp__*` callouts at SKILL.md:141-142 — these are still valid for scripts-mode (inner agent wiring backends directly in `.mcp.json`) but must be flagged "scripts-mode only" with `mcp__mare-toolbox__*` documented as the gateway-mode prefix

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `caplog`/`pytest.warns(UserWarning)` will surface visibly in the gateway's CI logs (mirrors `test_collision_check.py` precedent) | Architecture Patterns - Soft-warn | Drift goes unnoticed; soft snapshot becomes a silent no-op. Mitigation: planner verifies CI output format during implementation. |
| A2 | `mcp-gateway/tests/` collects `test_skill_md_dual_mode.py` automatically without conftest changes | Anti-Patterns + Code Examples | Test isn't run in CI. Mitigation: pytest collects all `test_*.py` by default; verify by adding the test and running `pytest mcp-gateway/tests/ --collect-only`. |
| A3 | The MCP `tools/call` JSON-RPC shape for `get_dynamic_capabilities` returns the dataclass-asdict view at `.result.content[0].text` (as JSON-encoded string) | Code Examples - Example 4 | Shell-route D-16 returns "{}" defaults instead of real caps. Mitigation: planner verifies actual JSON-RPC return shape against an MCP smoke test, or switches to Python route. |
| A4 | The `description:` field in SKILL.md frontmatter tolerates the addition of "IDA Pro MCP" without breaking discovery | Pitfall 8 | Skill is no longer auto-discovered. Mitigation: keep description as a single line, validate with `yaml.safe_load`. |
| A5 | `parents[2]` from `mcp-gateway/tests/test_skill_md_dual_mode.py` resolves to project root | Pattern 3 + Code Examples | Test reads empty files. **Verified by inspection of `mcp-gateway/tests/test_readme_structure.py:13`** — already uses this exact pattern. **Promoted to [VERIFIED].** |
| A6 | `references/agent-roles.md` and `references/interesting-signals.md` are tool-agnostic prose and need NO edits beyond Claude's Discretion review | Project Structure | If they reference legacy tool names, regression test fails. **Mitigation: planner reads both files (already done in this research — confirmed tool-agnostic except `references/interesting-signals.md` mentions tool names ('strings', 'rabin2', 'capa', 'readelf', 'nm') as raw CLI names, not MCP prefixes — no edits needed).** **Promoted to [VERIFIED].** |
| A7 | The W-N files do not need to enumerate every backend-native tool (IDA's 50+ tools); they reference `decompile`, `list_functions`, `xrefs_to` and direct the agent to call `get_active_backend()` for the rest | D-02 application | Agent doesn't discover the deeper IDA surface (idalib_*, find_regex, callgraph). Acceptable — skill is for orchestration, not backend reference. |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed.

(Three assumptions remain after promotion: A1, A2, A3, A4, A7 — all low-risk and verifiable during planning.)

## Open Questions

1. **D-16 shell vs Python route for gateway-mode dynamic-cap probe.**
   - What we know: `mcp-gateway/pyproject.toml` ships `mcp>=1.27`; `curl` + `jq` are in Kali; both paths are viable.
   - What's unclear: which path generates fewer cascading edits. Shell route adds ~30 LoC to `init_status_tree.sh`. Python route adds a new `scripts/probe_gateway_caps.py` module.
   - Recommendation: **shell route** — `init_status_tree.sh` is the existing entry point; mirroring `scripts/probe_dynamic_tools.sh:1-121` keeps the pattern consistent. If the JSON-RPC shape proves brittle (A3), fall back to Python in a follow-up plan.

2. **D-13 soft-warn surface in CI: `pytest.warns` vs `warnings.warn(UserWarning)` vs captured `print`.**
   - What we know: gateway tests use `caplog` for log-level checks (`test_collision_check.py:83`, `test_auth.py:75`). Pytest's default config emits a "warnings summary" at the end of every run.
   - What's unclear: whether CI is configured to fail on UserWarning (`-W error::UserWarning`). `mcp-gateway/pyproject.toml` does not set warning filters.
   - Recommendation: **`warnings.warn(..., UserWarning)`** because (a) it surfaces in pytest's end-of-run summary without ctx-manager assertion, (b) it doesn't require capsys/caplog setup, (c) refresh hint stays visible. Add a small pytest filterwarnings comment to the test docstring explaining the soft-warn pattern.

3. **W-N file naming convention.**
   - What we know: D-03 examples use `W-1-packed-binary-triage.md`. D-14 regex uses glob `W-*.md` (and `references/workflows/W-*.md`).
   - What's unclear: is the canonical separator `-` (kebab-case) or do we tolerate `W1-packed.md` (no leading dash)?
   - Recommendation: pin **`W-N-<slug>.md`** (e.g., `W-1-packed-binary-triage.md`) — explicit dash matches CONTEXT.md examples and `W-*.md` glob handles both spellings. Document the convention in `references/deep-re-workflows.md` (the new index) so future additions don't drift.

4. **Should the dual-mode regex tighten to `mcp__mare-toolbox__\w+` (excluding the abbreviated `mcp__mare__`)?**
   - What we know: Pitfall 3 above identifies the abbreviated form as a runtime-fail trap.
   - Recommendation: keep the broad regex (`mare[-_]\w+`) for the dual-mode check (catches both spellings and ensures fallback), AND add a separate test `test_skill_md_no_abbreviated_prefix` that grep-asserts NO occurrence of `mcp__mare__` (without `-toolbox`). Two tests, two invariants, no false-positive collision.

5. **Should `references/artifact-spec.md` be updated to document the new `mode`, `dynamic_mode_enabled`, and `dynamic_capabilities` fields in the CURRENT_STATE.json schema?**
   - What we know: `references/artifact-spec.md:118-135` documents the current 7-field schema verbatim.
   - Recommendation: **YES.** D-15 extends the schema; the spec must reflect it. Add it as a planner-discretion edit to the same phase.

## Environment Availability

> This phase edits markdown + adds one Python test. External dependency surface is narrow.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12.3 | Test file, update_state.py extension | ✓ | 3.12.3 | — |
| pytest >=8 | Regression test | ✓ (in pyproject.toml) | per project | — |
| `re`, `hashlib`, `pathlib` (stdlib) | Test file | ✓ | stdlib | — |
| `curl` | D-16 shell route gateway probe (inside container) | ✓ in Kali | — | Python route via `mcp` SDK |
| `jq` | D-16 shell route JSON parse | ✓ in Kali | — | Python route or inline python3 -c |
| `bash` 5.x | init_status_tree.sh extension | ✓ in Kali | — | — |
| MCP gateway running | Gateway-mode probe path | Conditional (operator runs `./run_docker.sh --remote`) | — | scripts-mode `probe_dynamic_tools.sh` |
| `mcp` Python SDK | If D-16 takes Python route | ✓ in mcp-gateway pyproject.toml | >=1.27,<1.28 | shell route |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** MCP gateway HTTP endpoint may not be reachable from inner agent's init_status_tree.sh invocation — handled by D-16 fallback to scripts-mode (probe_dynamic_tools.sh).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8 + pytest-asyncio >=0.23 (already configured in `mcp-gateway/pyproject.toml`) |
| Config file | `mcp-gateway/pyproject.toml` `[tool.pytest.ini_options]` (asyncio_mode=auto) |
| Quick run command | `cd mcp-gateway && pytest tests/test_skill_md_dual_mode.py -x` |
| Full suite command | `cd mcp-gateway && pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SKILL-01 | Backend priority `IDA > BN > Ghidra > r2` appears in SKILL.md, workflow.md, deep-analysis-checklist.md, all W-N files | content-grep | `pytest mcp-gateway/tests/test_skill_md_dual_mode.py::test_backend_priority_correct -x` | ❌ Wave 0 |
| SKILL-01 | Legacy BN-first ordering (`Binary Ninja MCP server -- primary tool`) is absent | negative-grep | `pytest ...::test_no_legacy_bn_first_priority -x` | ❌ Wave 0 |
| SKILL-02 | All 7 W-N files exist at `references/workflows/W-*.md` with correct slug convention | file-presence + count assert | `pytest ...::test_workflow_count_locked -x` | ❌ Wave 0 |
| SKILL-02 | Each W-N file mentions at least one v1.1 wrapper (`run_file`, `run_die`, `run_rabin2`, `run_strace`, etc.) appropriate to its workflow | per-W-N content-grep | `pytest ...::test_wn_files_reference_v1_1_wrappers -x` | ❌ Wave 0 |
| SKILL-03 | Every `mcp__mare[-_]\w+__\w+` reference in SKILL.md + W-N files + workflow.md + deep-re-workflows.md has a fallback within ±3 lines (D-12) | regex + window check | `pytest ...::test_dual_mode_invariant -x` (parametrized over all skill files) | ❌ Wave 0 |
| SKILL-03 | No occurrence of abbreviated `mcp__mare__` (without `-toolbox`) | negative-grep | `pytest ...::test_no_abbreviated_prefix -x` | ❌ Wave 0 |
| SKILL-03 | SKILL.md sha256 matches snapshot baseline (soft) | sha256 + UserWarning | `pytest ...::test_skill_md_snapshot -x` | ❌ Wave 0 |
| SKILL-03 | Frontmatter (`name:` `description:`) is parseable YAML and contains `name: malware-analysis-orchestrator` | YAML parse | `pytest ...::test_skill_md_frontmatter_intact -x` | ❌ Wave 0 |
| SKILL-04 | `update_state.py` accepts `--probe-dynamic` and writes `dynamic_mode_enabled` + `dynamic_capabilities` keys to CURRENT_STATE.json | sub-process spawn + JSON read | `pytest ...::test_update_state_writes_dynamic_fields -x` | ❌ Wave 0 |
| SKILL-04 | `init_status_tree.sh` populates the two new fields end-to-end on a tmp case dir | sub-process + JSON read; skip if no gateway + no probe_dynamic_tools.sh | `pytest ...::test_init_populates_dynamic_caps -x` | ❌ Wave 0 (may skip on CI host) |
| SKILL-04 | `references/artifact-spec.md` documents the new schema fields | content-grep on `dynamic_mode_enabled` | `pytest ...::test_artifact_spec_documents_dynamic_fields -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest mcp-gateway/tests/test_skill_md_dual_mode.py -x` (the targeted file)
- **Per wave merge:** `cd mcp-gateway && pytest tests/ -x --ignore=tests/e2e` (full unit suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`, including `tests/e2e` if present and feasible on the executor host.

### Wave 0 Gaps
- [ ] `mcp-gateway/tests/test_skill_md_dual_mode.py` — covers SKILL-01..04 (single test module per CONTEXT.md D-11)
- [ ] `mcp-gateway/tests/snapshots/SKILL.md.sha256` — created on first `UPDATE_SKILL_SNAPSHOT=1` run; test tolerates absence with UserWarning
- [ ] No new conftest needed — existing `mcp-gateway/tests/conftest.py` is reused

## Sources

### Primary (HIGH confidence)
- `mcp-gateway/README.md` — backend priority statement (line 71), gateway-native tool table (lines 44-67), IDA native tool list (lines 81-170+)
- `mcp-gateway/src/mcp_gateway/dynamic.py:304-319` — `DynamicCapabilities` dataclass shape (verified the D-15 schema)
- `mcp-gateway/src/mcp_gateway/tools/dynamic.py:504-528` — `get_dynamic_capabilities()` tool body, refresh semantics
- `mcp-gateway/src/mcp_gateway/tools/*` — full enumeration of v1.1 wrapper names (re_static.py 11, extract.py 7, r2_sessions.py 4, jobs.py 4, dynamic.py 7, re_artifacts.py 5, shell.py 1)
- `mcp-gateway/tests/test_tool_list.py:53-89` — canonical 54/61 tool surface counts
- `mcp-gateway/tests/conftest.py` — pytest fixtures + `_require_*_or_skip` helpers reusable in new test
- `mcp-gateway/tests/test_readme_structure.py:13` — verified `Path(__file__).resolve().parents[2]` precedent
- `mcp-gateway/tests/test_collision_check.py:83`, `test_auth.py:75` — caplog soft-warn precedent
- `mcp-gateway/pyproject.toml` — pytest>=8, pytest-asyncio>=0.23, mcp>=1.27,<1.28, asyncio_mode=auto
- `run_docker.sh:66, 95-104` — `mare-toolbox` canonical server name, dynamic-mode ready-block
- `scripts/probe_dynamic_tools.sh` (project root, 121 lines) — Phase 11 probe reused by D-16 scripts mode
- `workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md` (275 lines) — current skill content
- `workspace/.claude/skills/malware-analysis-orchestrator/references/*.md` — all 5 reference files read end-to-end
- `workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh` + `update_state.py` — verified extension points
- `.planning/research/FEATURES.md` lines 223-310 — W-1..W-7 source material (verbatim source for W-N files)
- `.planning/research/SUMMARY.md` lines 60-65, 216 — confirms W-1..W-7 scope + dual-mode + CI test requirement
- `.planning/REQUIREMENTS.md` lines 85-88 — SKILL-01..04 acceptance criteria
- `.planning/ROADMAP.md` lines 158-167 — Phase 12 goal and success criteria
- `.planning/phases/11-dynamic-lab-mode-env-gated/11-CONTEXT.md` (via STATE.md history) — D-DYN-CAP-PROBE-01 semantics
- `CLAUDE.md` (project root, full read) — recommended stack, "Do NOT Use" list, GSD workflow enforcement
- `workspace/CLAUDE.md` — inner-agent context, skill auto-discovery, default scripts-mode

### Secondary (MEDIUM confidence)
- None — every claim cross-referenced against in-repo source.

### Tertiary (LOW confidence)
- A1, A3, A4: assumptions documented in Assumptions Log, low-impact, verifiable during planning.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Python 3.12.3, pytest>=8, pytest-asyncio>=0.23 all verified in `pyproject.toml`; no new dependencies introduced.
- Architecture: HIGH — every pattern (frontmatter, parents[2], caplog/warnings, three-column step, init_status_tree.sh extension) has explicit precedent in the codebase.
- Pitfalls: HIGH — six of eight pitfalls are derived from concrete sources (Pitfall 4 from `test_readme_structure.py`, Pitfall 5 from `dynamic.probe_all()` semantics, Pitfall 6 from MCP lifespan startup, Pitfall 7 from glob enumeration logic, Pitfall 8 from frontmatter mechanics). Pitfalls 1-3 are foreseen from D-12 regex shape + ambiguity analysis.

**Research date:** 2026-05-20
**Valid until:** Phase 12 closeout (no external API dependencies; only changes if `mcp-gateway/` tool surface shifts, which is locked under v1.1 and regression-tested at 54/61).
