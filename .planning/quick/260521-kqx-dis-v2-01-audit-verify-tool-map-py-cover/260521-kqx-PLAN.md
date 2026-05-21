---
phase: quick-260521-kqx
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/quick/260521-kqx-dis-v2-01-audit-verify-tool-map-py-cover/260521-kqx-AUDIT.md
autonomous: true
requirements: [DIS-V2-01]

must_haves:
  truths:
    - "DIS-V2-01 original intent + acceptance criteria are quoted verbatim from v1.0-REQUIREMENTS.md with file:line citation"
    - "Every (unified_tool x backend) mapping in tool_map.py is enumerated in the AUDIT with file:line citations"
    - "Audit distinguishes between intentional native pass-through (per gateway D-07 design) vs. normalized tools, and cites at least one CLAUDE.md / CONTEXT.md location stating the pass-through policy"
    - "Audit produces a single verdict A/B/C with at least 3 sentences of concrete reasoning grounded in the code citations (not speculation)"
    - "If verdict is B (partial), v1.2 phase scope is sketched as 3-5 bullets ready for lift into ROADMAP.md"
    - "If verdict is A or C, an explicit recommendation is given for ROADMAP.md and v1.0-REQUIREMENTS.md edits (without making those edits in this task)"
  artifacts:
    - path: ".planning/quick/260521-kqx-dis-v2-01-audit-verify-tool-map-py-cover/260521-kqx-AUDIT.md"
      provides: "DIS-V2-01 audit report with verdict A/B/C and recommended action"
      contains: "Verdict:"
      min_lines: 80
  key_links:
    - from: "AUDIT.md > 'Requirement Text' section"
      to: ".planning/milestones/v1.0-REQUIREMENTS.md:56"
      via: "verbatim quote + line citation"
      pattern: "v1.0-REQUIREMENTS.md"
    - from: "AUDIT.md > 'Current State Inventory' section"
      to: "mcp-gateway/src/mcp_gateway/backend/tool_map.py:25-45"
      via: "per-mapping enumeration table"
      pattern: "tool_map\\.py"
    - from: "AUDIT.md > 'Gap Analysis' section"
      to: "mcp-gateway/src/mcp_gateway/tools/disasm.py + backend/client.py"
      via: "consumer cross-reference"
      pattern: "disasm\\.py|client\\.py"
    - from: "AUDIT.md > 'Verdict' section"
      to: "v1.2 ROADMAP.md stub (lines 54-56)"
      via: "recommended action statement"
      pattern: "v1\\.2"
---

<objective>
Audit DIS-V2-01 (Unified disassembler abstraction layer — normalize tool names/params across IDA/BN/Ghidra) and produce a single AUDIT.md verdict telling v1.2 milestone planning whether to (A) close DIS-V2-01 as already-satisfied, (B) scope a real v1.2 phase to fill gaps, or (C) retire/rewrite the requirement because v1.1's "native pass-through + get_active_backend" design supersedes it.

Purpose: v1.2 milestone scoping is gated on this decision — without it, the v1.2 ROADMAP stub lines 54-56 cannot be turned into a concrete phase entry. Investigation only; no source code changes.

Output: `.planning/quick/260521-kqx-dis-v2-01-audit-verify-tool-map-py-cover/260521-kqx-AUDIT.md`
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md
@.planning/milestones/v1.0-REQUIREMENTS.md
@.planning/ROADMAP.md
@mcp-gateway/src/mcp_gateway/backend/tool_map.py
@mcp-gateway/src/mcp_gateway/backend/client.py
@mcp-gateway/src/mcp_gateway/tools/disasm.py
@mcp-gateway/src/mcp_gateway/backend/detect.py
@mcp-gateway/tests/test_tool_map.py

<interfaces>
<!-- Pre-loaded code surface the executor will cite. Read the actual files for line numbers — these are anchors only. -->

From mcp-gateway/src/mcp_gateway/backend/tool_map.py:
```python
# 3 unified tools mapped to 3 backends each (9 cells total):
TOOL_MAP = {
    "decompile":      {"ida": ("decompile", _identity),       "bn": ("decompile", _identity),      "ghidra": ("decomp.function", _identity)},
    "list_functions": {"ida": ("list_funcs", _identity),      "bn": ("list_functions", _identity), "ghidra": ("function.list",   _identity)},
    "get_xrefs":      {"ida": ("xrefs_to", _identity),        "bn": ("get_xrefs", _identity),      "ghidra": ("reference.to",    _identity)},
}
# Module docstring line 18-19 EXPLICITLY says:
#   "args_transform is identity ... v2 (DIS-V2-01) will add real shape normalization."
```

From mcp-gateway/src/mcp_gateway/backend/client.py:
```python
SUPPORTED_BACKENDS = ("ida", "bn", "ghidra")  # line 32
# call_unified() resolves unified_name -> tool_map.translate() -> backend call (lines 98-122)
# list_tools() returns NATIVE backend tool definitions (lines 90-96) — used by pass-through path
```

From mcp-gateway/src/mcp_gateway/tools/disasm.py:
```python
# Exactly 3 gateway-side unified tools: decompile, list_functions, get_xrefs.
# Each delegates to PINNED_BACKEND.call_unified(...).
# All have IDENTICAL arg shape across backends — there is no normalization layer beyond name mapping.
```

From CLAUDE.md (Tech Stack — Remote MCP Gateway Server row):
```
"Disassembler tools pass through under their NATIVE names (D-07) — clients call get_active_backend() to discover which backend's surface is active."
```

From .planning/milestones/v1.0-REQUIREMENTS.md (line 56):
```
- **DIS-V2-01**: Unified disassembler abstraction layer (normalize tool names/params across all three backends)
```
</interfaces>

<background_notes>
Existing test_tool_map.py PROVES three things already work:
- All 3 unified tools have mappings for all 3 backends (test_all_three_backends_supported_for_every_unified_tool)
- Translation resolves cleanly for each (unified, backend) pair (test_translate_returns_backend_tool)
- Unknown unified or unknown backend raises KeyError (test_translate_unknown_*_raises)

So the question is NOT "does the mapping work" but "is 3 tools the full scope DIS-V2-01 intended"?

Phase 2 D-07 design context (per CLAUDE.md and tool_map.py docstring): the gateway aggregates ~19 native tools + transparently passes through the pinned backend's surface (so clients see ~50 IDA tools, ~30 BN tools, or ~25 Ghidra tools depending on which backend is active). Only 3 of those are "unified" (renamed/normalized) — the rest pass through with native names.

DIS-V2-01 says "normalize tool names/params across all three backends" — the audit must decide whether 3 unified tools satisfies the SPIRIT of that requirement, or whether the intent was a broader normalization (e.g. all decompiler tools, all xref tools, all string-listing tools, all symbol-lookup tools).
</background_notes>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Produce DIS-V2-01 audit report with verdict</name>
  <files>.planning/quick/260521-kqx-dis-v2-01-audit-verify-tool-map-py-cover/260521-kqx-AUDIT.md</files>
  <action>
Open the files listed in `<context>` and produce a single AUDIT.md following the structure below. Cite file:line for every factual claim. No source code changes in this task.

**Investigation steps (perform in order, then write the report):**

1. **Read DIS-V2-01 requirement text** — open `.planning/milestones/v1.0-REQUIREMENTS.md` and locate the DIS-V2-01 entry (around line 56). Also scan lines 45-58 for the surrounding `## v2 Requirements (carried forward)` context and any adjacent DIS-V2-* requirements. Capture the verbatim text + line number. Check if there is any acceptance criteria, scoping language, or "why" text earlier in the file (Phase 2 RESEARCH.md / CONTEXT.md if referenced).

2. **Read the v1.2 stub** — open `.planning/ROADMAP.md` lines 40-67 (the "📋 v1.2" block). Note exactly how DIS-V2-01 is currently described there (line 55).

3. **Inventory `tool_map.py`** — open `mcp-gateway/src/mcp_gateway/backend/tool_map.py` and enumerate every (unified_name, backend, backend_tool_name) tuple in a markdown table with line citations. Also note the module docstring on line 18-19 which EXPLICITLY says "v2 (DIS-V2-01) will add real shape normalization" — this is a direct in-source admission of what was deferred.

4. **Inventory `disasm.py` consumers** — open `mcp-gateway/src/mcp_gateway/tools/disasm.py` and list every gateway-side tool that uses the unified layer. Note the arg shapes (function, sample, sample_path).

5. **Verify pass-through policy** — quote the relevant lines from `./CLAUDE.md` (Recommended Stack > Remote MCP Gateway Server row) where it says "Disassembler tools pass through under their NATIVE names (D-07)". This is the architectural counter-argument to broadening DIS-V2-01.

6. **Check `detect.py` for backend completeness** — open `mcp-gateway/src/mcp_gateway/backend/detect.py` and confirm IDA/BN/Ghidra are the only three backends. If a fourth backend appears (e.g., radare2 listed in SUPPORTED_BACKENDS), flag it as a gap.

7. **Identify missing-normalization candidates** — for each backend, what *other* common-verb tools exist that are NOT in tool_map.py? You don't need an exhaustive list — 5-10 obvious examples is enough (e.g., `get_strings`, `list_imports`, `disassemble_function`, `rename_function`, `get_segments`). State whether each is currently exposed via native pass-through (per D-07) and whether a unified name would clearly add value or merely add a renaming layer.

8. **Form a verdict (A/B/C)** based on the evidence:
   - **(A)** if 3 unified tools + native pass-through is a defensible interpretation of DIS-V2-01 ("the spirit is satisfied by the architecture, even if literal scope is narrower than the text suggests")
   - **(B)** if there are obvious unified-name candidates beyond the 3 current ones that would have real client value (e.g. cross-backend skill scripts get cleaner)
   - **(C)** if the v1.1 D-07 native-pass-through design *supersedes* DIS-V2-01's original framing and the requirement should be rewritten or retired

**AUDIT.md structure (write this verbatim, fill in the bracketed sections):**

```markdown
# DIS-V2-01 Audit: tool_map.py Coverage of Cross-Backend Normalization

**Date:** 2026-05-21
**Auditor:** GSD quick task 260521-kqx
**Trigger:** v1.2 milestone scoping (ROADMAP.md lines 54-55) needs to know whether DIS-V2-01 is a real v1.2 phase candidate or already-satisfied / superseded.

## 1. Requirement Text (verbatim)

From `.planning/milestones/v1.0-REQUIREMENTS.md` line [N]:
> [quote verbatim]

Surrounding context (lines [X-Y]): [paraphrase the "v2 Requirements (carried forward)" framing — these are explicitly deferred items from v1.0 expecting v2 implementation].

Currently referenced in `.planning/ROADMAP.md` line 55 as part of the v1.2 stub: [quote verbatim].

## 2. Current State Inventory

### 2.1 Unified tools mapped in `tool_map.py`

| Unified name | IDA backend tool | BN backend tool | Ghidra backend tool | Args transform |
|--------------|------------------|-----------------|---------------------|----------------|
| [...]        | [...]            | [...]           | [...]               | [...]          |

Source: `mcp-gateway/src/mcp_gateway/backend/tool_map.py:25-45`

### 2.2 In-source DIS-V2-01 reference

`mcp-gateway/src/mcp_gateway/backend/tool_map.py:18-19` explicitly states:
> [quote the docstring line about "v2 (DIS-V2-01) will add real shape normalization"]

This is a direct in-source admission that Phase 2 left shape-normalization to a future "v2" effort.

### 2.3 Consumer surface in `disasm.py`

[Enumerate the 3 MCP tools defined; cite file:line for each.]

### 2.4 Architectural counter-context: native pass-through

From `./CLAUDE.md` (Tech Stack table, Remote MCP Gateway Server row):
> [quote the "Disassembler tools pass through under their NATIVE names (D-07)" line verbatim]

Implication: the v1.1 architecture deliberately avoids forcing every backend tool through a unified rename layer — clients use `get_active_backend()` to discover which native surface is active.

## 3. Gap Analysis

### 3.1 Mappings coverage (what IS unified)

[Table or bullet list confirming 3/3 backends covered for each of the 3 unified tools — i.e. the 3x3 matrix is complete. Cite `tests/test_tool_map.py:54-57` which already locks this in.]

### 3.2 Normalization scope (what is NOT unified but COULD be)

| Cross-backend verb | IDA native | BN native | Ghidra native | Currently unified? | Worth unifying? |
|--------------------|------------|-----------|---------------|--------------------|--------------------|
| decompile          | yes        | yes       | yes           | YES                | already done       |
| list_functions     | yes        | yes       | yes           | YES                | already done       |
| get_xrefs          | yes        | yes       | yes           | YES                | already done       |
| get_strings        | [...]      | [...]     | [...]         | NO                 | [yes/no + why]     |
| list_imports       | [...]      | [...]     | [...]         | NO                 | [yes/no + why]     |
| disassemble_function | [...]    | [...]     | [...]         | NO                 | [yes/no + why]     |
| rename_function    | [...]      | [...]     | [...]         | NO                 | [yes/no + why]     |
| [add 2-3 more]     | [...]      | [...]     | [...]         | NO                 | [yes/no + why]     |

Native tool names sourced from: README IDA tool inventory + Phase 2 RESEARCH.md (if accessible) + general knowledge of each backend's MCP server. Where a specific tool's existence is uncertain, mark it `?` rather than guessing.

### 3.3 Param-shape normalization (the other half of DIS-V2-01)

DIS-V2-01 says "normalize tool names AND params". Today `args_transform` is `_identity` for every cell (tool_map.py:21-23). Real normalization examples that COULD live there:
- [1-3 examples of where IDA/BN/Ghidra differ in param shape for the same logical tool, e.g. function addressing as int-address vs. name-string, or sample path handling]

## 4. Verdict

**Verdict: [A | B | C]**

[3+ sentences of concrete reasoning grounded in the citations above. Must reference specific lines/decisions, not "feels like".]

## 5. Recommended Action

### If verdict A — DIS-V2-01 already satisfied:
- Mark DIS-V2-01 complete in `.planning/milestones/v1.0-REQUIREMENTS.md` traceability table with note "satisfied by Phase 2 tool_map.py + D-07 native pass-through design".
- Remove DIS-V2-01 from `.planning/ROADMAP.md` v1.2 stub (line 55).
- Remove the "v2 (DIS-V2-01) will add real shape normalization" line from `mcp-gateway/src/mcp_gateway/backend/tool_map.py:18-19` (now stale).

### If verdict B — DIS-V2-01 partial, needs v1.2 phase:

**Sketched v1.2 phase scope (3-5 bullets, ready for ROADMAP lift):**
- [Bullet 1: e.g. "Extend TOOL_MAP with N more unified tools: get_strings, list_imports, disassemble_function, rename_function"]
- [Bullet 2: e.g. "Replace `_identity` arg transforms with real shape normalization for at least one tool that differs across backends"]
- [Bullet 3: e.g. "Add cross-backend conformance test: every unified tool round-trips through all 3 backends with shape-equivalent results"]
- [Bullet 4: optional — backend-specific divergence handling (what happens when a backend lacks a unified verb)]
- [Bullet 5: optional — update orchestrator skill to prefer unified names where available]

### If verdict C — DIS-V2-01 superseded:
- Rewrite DIS-V2-01 in `v1.0-REQUIREMENTS.md` to reflect the actual delivered design: "Selective unification (3 verbs) + native pass-through with `get_active_backend()` discovery".
- Remove DIS-V2-01 from `.planning/ROADMAP.md` v1.2 stub line 55, replace with NEW requirement reflecting any real residual gap (or drop entirely).
- Update `mcp-gateway/src/mcp_gateway/backend/tool_map.py:18-19` docstring to reflect final state instead of pointing at a deferred v2.

## 6. Out of Scope for This Audit

- No source code changes (tool_map.py, disasm.py, etc.) — recommended edits enumerated above are deliberately left for a follow-up quick-task or v1.2 milestone planning.
- No edits to ROADMAP.md or REQUIREMENTS.md — those are recommended actions, not part of this audit.
- No assessment of DIS-V2-02 (backend comparison/diff mode) — separate requirement.
```

Acceptance: every cell in every table is filled in (no `[...]` placeholders left), every quote has a file:line citation, the verdict is exactly one of A/B/C, and the "Recommended Action" section corresponds to the verdict chosen (delete the two non-applicable subsections).
  </action>
  <verify>
    <automated>test -f .planning/quick/260521-kqx-dis-v2-01-audit-verify-tool-map-py-cover/260521-kqx-AUDIT.md && grep -qE "^\*\*Verdict: (A|B|C)\*\*" .planning/quick/260521-kqx-dis-v2-01-audit-verify-tool-map-py-cover/260521-kqx-AUDIT.md && [ $(wc -l < .planning/quick/260521-kqx-dis-v2-01-audit-verify-tool-map-py-cover/260521-kqx-AUDIT.md) -ge 80 ] && ! grep -q '\[\.\.\.\]' .planning/quick/260521-kqx-dis-v2-01-audit-verify-tool-map-py-cover/260521-kqx-AUDIT.md && grep -q 'tool_map.py' .planning/quick/260521-kqx-dis-v2-01-audit-verify-tool-map-py-cover/260521-kqx-AUDIT.md && grep -q 'v1.0-REQUIREMENTS.md' .planning/quick/260521-kqx-dis-v2-01-audit-verify-tool-map-py-cover/260521-kqx-AUDIT.md</automated>
  </verify>
  <done>
- AUDIT.md exists at the expected path
- Contains exactly one of `**Verdict: A**` / `**Verdict: B**` / `**Verdict: C**`
- ≥ 80 lines
- No `[...]` placeholder strings remain (all bracketed slots filled)
- Cites both `tool_map.py` and `v1.0-REQUIREMENTS.md` with file:line
- Recommended-action subsections that don't match the chosen verdict are removed
  </done>
</task>

</tasks>

<verification>
After Task 1:
1. `cat .planning/quick/260521-kqx-dis-v2-01-audit-verify-tool-map-py-cover/260521-kqx-AUDIT.md` — read end-to-end, confirm verdict is defensible from the citations
2. Confirm verdict-specific Recommended Action subsection matches chosen verdict (other two removed)
3. If verdict B, confirm v1.2 phase scope bullets are concrete enough to lift into ROADMAP.md
</verification>

<success_criteria>
- AUDIT.md exists with verdict A, B, or C
- All factual claims cite file:line
- Verdict reasoning grounds in code/docs, not speculation
- Recommended action corresponds to verdict (delete non-applicable subsections)
- User can act on the audit immediately: either mark DIS-V2-01 complete (A), add it as a real v1.2 phase (B), or rewrite the requirement (C) — no further investigation needed
</success_criteria>

<output>
After completion, the AUDIT.md is the deliverable. No SUMMARY.md needed for quick tasks unless the user requests one — the audit itself is the summary. Recommend the user commit with: `Add DIS-V2-01 audit (verdict {A|B|C})`.
</output>
