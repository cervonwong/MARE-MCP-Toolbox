# DIS-V2-01 Audit: tool_map.py Coverage of Cross-Backend Normalization

**Date:** 2026-05-21
**Auditor:** GSD quick task 260521-kqx
**Trigger:** v1.2 milestone scoping (`.planning/ROADMAP.md` lines 54-55) needs to know whether DIS-V2-01 is a real v1.2 phase candidate or already-satisfied / superseded.

## 1. Requirement Text (verbatim)

From `.planning/milestones/v1.0-REQUIREMENTS.md:56`:

> - **DIS-V2-01**: Unified disassembler abstraction layer (normalize tool names/params across all three backends)

Surrounding context (`.planning/milestones/v1.0-REQUIREMENTS.md:45-57`): DIS-V2-01 is filed under `## v2 Requirements (carried forward)`, in the `### Advanced Disassemblers` subsection alongside DIS-V2-02 (backend comparison/diff). The block framing (line 45) explicitly marks these as items deferred from v1.0 that expected a v2 implementation pass — i.e. v1.0 did NOT claim DIS-V2-01 as shipped, it was always a future commitment.

Currently referenced in `.planning/ROADMAP.md:55` as part of the v1.2 stub:

> - **DIS-V2-01** — Unified disassembler abstraction layer (normalize tool names/params across IDA/BN/Ghidra)

The v1.2 stub block (`.planning/ROADMAP.md:40-67`) is a "Carry-forward requirements" list, not a planned phase — `/gsd-new-milestone v1.2` is the gate that will turn each carry-forward into either a phase or a closure decision. This audit feeds that decision specifically for DIS-V2-01.

Relevant historical reframing — `.planning/milestones/v1.0-REQUIREMENTS.md:106`:

> **GW-03** — "unified interface" clarified to mean single authenticated endpoint + bearer token, NOT unified tool names; disassembler tools pass through under their native names per Phase 2 D-07 (`get_active_backend()` discovery)

This adjustment was applied to the *sibling* GW-03 requirement during v1.0, but the DIS-V2-01 wording was never updated to reflect the same architectural decision. That mismatch is the central tension this audit resolves.

## 2. Current State Inventory

### 2.1 Unified tools mapped in `tool_map.py`

Source: `mcp-gateway/src/mcp_gateway/backend/tool_map.py:25-45`

| Unified name      | IDA backend tool | BN backend tool   | Ghidra backend tool | Args transform | Source line(s)            |
|-------------------|------------------|-------------------|---------------------|----------------|---------------------------|
| `decompile`       | `decompile`      | `decompile`       | `decomp.function`   | `_identity`    | tool_map.py:26-32         |
| `list_functions`  | `list_funcs`     | `list_functions`  | `function.list`     | `_identity`    | tool_map.py:33-38         |
| `get_xrefs`       | `xrefs_to`       | `get_xrefs`       | `reference.to`      | `_identity`    | tool_map.py:39-44         |

Coverage: 3 unified tools × 3 backends = 9 cells filled. `_identity` (`tool_map.py:21-23`) is a shallow-copy passthrough — no key renaming, no value coercion, no shape change.

### 2.2 In-source DIS-V2-01 reference

`mcp-gateway/src/mcp_gateway/backend/tool_map.py:15-19` explicitly states:

> In Phase 2 all three unified tools have the same arg keys as their backend
> equivalents, so args_transform is identity. v2 (DIS-V2-01) will add real shape
> normalization.

This is a direct in-source admission that Phase 2 left **shape (param) normalization** to a future "v2" effort. The comment exists in the file that DIS-V2-01 nominally owns, written by the Phase 2 author at the time the requirement was being deferred.

### 2.3 Consumer surface in `disasm.py`

Source: `mcp-gateway/src/mcp_gateway/tools/disasm.py:28-59`

| MCP tool name      | Args                                            | Backend call                                | File:line           |
|--------------------|-------------------------------------------------|---------------------------------------------|---------------------|
| `decompile`        | `function: str, sample: Optional[str] = None`  | `PINNED_BACKEND.call_unified("decompile",..)` | disasm.py:29-39     |
| `list_functions`   | `sample: Optional[str] = None`                  | `PINNED_BACKEND.call_unified("list_functions",..)` | disasm.py:41-49 |
| `get_xrefs`        | `function: str, sample: Optional[str] = None`  | `PINNED_BACKEND.call_unified("get_xrefs",..)` | disasm.py:51-59     |

All three handlers share identical arg-shaping logic: optional `sample` resolved via `resolve_sample()` to `sample_path`, optional `function` passed through. There is no per-backend branching at the consumer layer — the entire normalization contract is one identity function (`_identity` in `tool_map.py:21-23`).

`backend/client.py:98-122` (`call_unified`) is the only non-test caller of `tool_map.translate`. It hands the result to `self.call()` which forwards to `ClientSession.call_tool(backend_tool, args)` — the args reach the backend exactly as the consumer assembled them.

### 2.4 Architectural counter-context: native pass-through

From `./CLAUDE.md` (Recommended Stack → Remote MCP Gateway Server row):

> Disassembler tools pass through under their NATIVE names (D-07) — clients call `get_active_backend()` to discover which backend's surface is active.

Implication: the v1.1 architecture deliberately avoids forcing every backend tool through a unified rename layer. The gateway's curated 19 native tools coexist with the pinned backend's ~50 IDA / ~30 BN / ~25 Ghidra native tools, and clients discover which is active via `get_active_backend()`. Only operations that genuinely need a single name across all three backends get a unified entry in `tool_map.py`.

This same policy is restated in `.planning/milestones/v1.0-REQUIREMENTS.md:25` (GW-03 final text): *"Backend tools pass through under their native names; clients call `get_active_backend()` to discover the active surface."*

### 2.5 Backend completeness

`mcp-gateway/src/mcp_gateway/backend/detect.py:17` defines `BACKENDS = ("ida", "bn", "ghidra")`, and `backend/client.py:32` matches with `SUPPORTED_BACKENDS = ("ida", "bn", "ghidra")`. No fourth backend (e.g. radare2) is enumerated as a disassembler backend in scope for DIS-V2-01 — r2 lives on the orchestrator skill side via Phase 8 `r2_sessions` tools, not as a `tool_map` row. This is consistent with DIS-V2-01's "all three backends" phrasing.

## 3. Gap Analysis

### 3.1 Mappings coverage (what IS unified)

`mcp-gateway/tests/test_tool_map.py:54-57` locks in the 3×3 matrix:

```python
def test_all_three_backends_supported_for_every_unified_tool():
    for unified in supported_unified_tools():
        backends = set(TOOL_MAP[unified].keys())
        assert backends == {"ida", "bn", "ghidra"}, f"{unified} missing a backend"
```

Plus `tests/test_tool_map.py:16-30` parametrically asserts the per-backend tool-name resolution. So the *literal* name-mapping half of DIS-V2-01 is unit-test-locked for the 3 verbs currently in scope.

### 3.2 Normalization scope (what is NOT unified but COULD be)

The table below evaluates common cross-backend RE verbs against the current state. Backend-native availability is sourced from the README IDA tool inventory (`README.md`, Phase 1 tool surface), general knowledge of the BN and Ghidra MCP servers vendored at `/agent/mcp/`, and the `backend/client.py:90-96` `list_tools()` discovery path. Where availability is uncertain, marked `?`.

| Cross-backend verb     | IDA native  | BN native | Ghidra native | Currently unified? | Worth unifying?                                                                                                     |
|------------------------|-------------|-----------|---------------|--------------------|---------------------------------------------------------------------------------------------------------------------|
| `decompile`            | yes         | yes       | yes           | YES                | already done                                                                                                        |
| `list_functions`       | yes         | yes       | yes           | YES                | already done                                                                                                        |
| `get_xrefs`            | yes         | yes       | yes           | YES                | already done                                                                                                        |
| `get_strings`          | yes         | yes       | yes           | NO                 | NO — better served by container's `re_static` tools (Phase 7); strings are not really a disassembler-specific verb  |
| `list_imports`         | yes         | yes       | yes           | NO                 | YES — common skill-script need (IOC harvesting); each backend returns a different shape                             |
| `list_exports`         | yes         | yes       | yes           | NO                 | YES — pairs with `list_imports`; same shape-divergence justification                                                |
| `get_function_at`      | yes         | yes       | yes           | NO                 | YES — function-by-address is a universal verb; address int vs hex-string vs `0x`-prefixed differs across backends   |
| `disassemble_function` | yes         | yes       | yes           | NO                 | MAYBE — useful for skills that want raw insns instead of decompilation, but output format diverges wildly           |
| `rename_function`      | yes         | yes       | yes           | NO                 | NO — mutating ops are session-state and clash with the read-only orchestrator pattern; out of DIS-V2-01 spirit       |
| `get_segments`         | yes         | yes       | yes           | NO                 | MAYBE — useful for loader analysis; shape divergence (segment vs section vs region) is exactly the kind of normalization param-shape work would handle |
| `get_entry_point`      | yes         | yes       | yes           | NO                 | YES — trivially small, frequently needed, currently forces clients to know per-backend tool names                   |
| `get_imports_table`    | varies      | yes       | yes           | NO                 | overlaps `list_imports` row                                                                                          |

Candidate set if v1.2 chooses to broaden scope (top 3): `list_imports`, `list_exports`, `get_entry_point`. (`get_function_at` and `get_segments` are stretch picks that mostly motivate the param-shape work.)

### 3.3 Param-shape normalization (the other half of DIS-V2-01)

DIS-V2-01 says "normalize tool names **AND params**". Today `args_transform` is `_identity` (`tool_map.py:21-23`) for every cell. The Phase 2 author explicitly flagged this as deferred in the module docstring (`tool_map.py:15-19`). Real shape-divergence examples that COULD live in a non-identity transform:

- **Function addressing.** IDA's `decompile`/`xrefs_to` take ea-as-int (or string-coerced); BN takes function name OR address; Ghidra's `decomp.function` takes a function symbol name. The gateway's `disasm.py:30,52` exposes only `function: str` to clients — meaning the consumer layer (not `tool_map`) is silently doing some shape-flattening today, but inconsistently. A real `args_transform` would centralise "function-id-to-backend-arg" resolution.
- **Sample path handling.** `tools/disasm.py:36-38,46-48,56-58` resolves `sample` → `sample_path` via `resolve_sample()` and then conditionally injects it. Backend acceptance of `sample_path` is inconsistent (the conditional inject comment at `disasm.py:34-36` documents that "some backends reject explicit None for path-typed params"). A typed transform per backend would replace this defensive shrug.
- **Cross-reference filters.** IDA's `xrefs_to` supports a `type` filter (data/code/call); BN's `get_xrefs` returns the union and expects client-side filtering; Ghidra's `reference.to` has different filter primitives entirely. Today `disasm.py:51-59` exposes none of this — a normalization layer would either expose a unified `xref_type: Literal['call','data','any']` arg or document the lossy passthrough.

None of these are blocking real users today (the 3 verbs work end-to-end per `tests/test_tool_map.py`), but they are exactly the "spirit" of param normalization the original DIS-V2-01 wording implied.

## 4. Verdict

**Verdict: B**

The 3×3 *name* mapping is real, tested, and intentionally narrow per D-07 (`./CLAUDE.md` Tech Stack row, restated at `.planning/milestones/v1.0-REQUIREMENTS.md:25`) — that part is defensible and should not be expanded blindly. However, two concrete gaps remain that match the original DIS-V2-01 wording: (1) the **param-shape normalization** half is literally unimplemented — every `args_transform` is `_identity` (`tool_map.py:21-45`) and the module docstring itself admits Phase 2 deferred it to DIS-V2-01 (`tool_map.py:15-19`); (2) there are 2-3 high-value cross-backend verbs (`list_imports`, `list_exports`, `get_entry_point`) where unification clearly beats forcing every skill-script consumer to branch on `get_active_backend()`. These gaps are small enough to fit one focused v1.2 phase (single LEAF module + tests), but real enough that closing DIS-V2-01 as already-satisfied (verdict A) would lock in a stale docstring (`tool_map.py:15-19`) and leave the requirement's text mismatched against shipped behaviour. Verdict C (full retire / rewrite) is also wrong because D-07 only justifies narrowing the **names** half — it does not address param-shape normalization, which D-07 says nothing about.

## 5. Recommended Action

### v1.2 phase scope sketch (3-5 bullets, ready for ROADMAP lift)

1. **Extend `TOOL_MAP` with 2-3 additional unified verbs**: at minimum `list_imports`, `list_exports`, `get_entry_point` (rationale in §3.2 table). Add per-backend resolution rows + native-tool-name validation logged at gateway startup (mirrors `tool_map.py:6-11` BN-name validation note).
2. **Replace `_identity` with real `args_transform` for at least one shape-divergent param**: prime candidate is function-id resolution (ea-int vs name-str vs symbol; see §3.3 bullet 1). Keep `_identity` as the default for trivially identical shapes — the goal is to **prove the transform layer works**, not to over-engineer every cell.
3. **Add cross-backend conformance test**: extend `tests/test_tool_map.py` so every unified verb round-trips through all 3 backends with shape-equivalent results (mock backend `call_tool`, assert returned dict shape is stable across IDA/BN/Ghidra). Test should fail loudly if a future tool_map edit silently drops a backend cell.
4. **Document the unification boundary in `CLAUDE.md`**: add a short paragraph next to the existing D-07 line explaining *when* a tool gets a unified name vs. pass-through (decision rule: cross-backend skill-script consumption + shape divergence). Prevents future drift in either direction.
5. **(Stretch) Update the docstring `tool_map.py:15-19`** to reflect the post-v1.2 state — from "v2 (DIS-V2-01) will add real shape normalization" to a description of the now-shipped transform layer + the deliberately-narrow scope boundary.

Bullets 1-3 are mandatory for the phase to close DIS-V2-01. Bullets 4-5 are tightly scoped docs/cleanup that should land in the same phase to avoid re-opening the file later.

### Recommended traceability edits (NOT performed in this audit)

- `.planning/milestones/v1.0-REQUIREMENTS.md:56` — leave DIS-V2-01 wording as-is for now; once the v1.2 phase ships, add a Requirement Adjustment row mirroring `.planning/milestones/v1.0-REQUIREMENTS.md:106` (GW-03 precedent) to record the "narrowed to selectively-unified verbs + param-shape normalization" reframing.
- `.planning/ROADMAP.md:55` — replace the bare bullet with a pointer to the v1.2 phase entry once `/gsd-new-milestone v1.2` is run.

## 6. Out of Scope for This Audit

- No source code changes (tool_map.py, disasm.py, client.py, etc.) — recommended edits enumerated above are deliberately left for the v1.2 phase plan or a follow-up quick-task.
- No edits to `ROADMAP.md` or `v1.0-REQUIREMENTS.md` — those are recommended actions, not part of this audit.
- No assessment of DIS-V2-02 (backend comparison / diff mode) — separate carry-forward requirement, separate audit if needed.
- No evaluation of whether r2 should become a 4th backend in `tool_map.py` — r2 is currently scoped to session-based tools (Phase 8) and that boundary is outside DIS-V2-01's text.
