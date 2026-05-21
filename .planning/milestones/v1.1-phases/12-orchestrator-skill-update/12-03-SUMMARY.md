---
phase: 12
plan: 03
subsystem: orchestrator-skill / dynamic-mode-plumbing
tags: [skill-scripts, dynamic-mode, current-state-schema, schema-extension, SKILL-04]
requires:
  - SKILL.md backend priority IDA > BN > Ghidra > r2 (Plan 12-01)
  - W-N workflow files with dynamic-mode skip semantics (Plan 12-02)
  - mcp-gateway dynamic.py probe_all() returning DynamicCapabilities (Phase 11)
  - scripts/probe_dynamic_tools.sh shell probe (Phase 11)
  - update_state.py v1.0 existing argparse + REQUIRED list + extract_* helpers
provides:
  - CURRENT_STATE.json v1.1 schema with mode/dynamic_mode_enabled/dynamic_capabilities
  - update_state.py --probe-dynamic CLI surface (D-17 re-probe entry point)
  - init_status_tree.sh populate_dynamic_caps function (D-16 case-init probe)
  - references/artifact-spec.md v1.1 schema documentation + re-probe path
  - SKILL-04 requirement satisfied
affects:
  - Plan 12-04 (SKILL.md rewrite): can READ mode/dynamic_mode_enabled at case-init
  - W-5/W-6/W-7 (Plan 12-02): READ dynamic_mode_enabled for fast-skip gate
  - Operators: re-probe ergonomics documented in artifact-spec.md
tech-stack:
  added: []
  patterns:
    - "Additive schema extension (v1.0 keys preserved; v1.1 keys default to safe values)"
    - "Read-modify-write merge: existing CURRENT_STATE.json values preserved when CLI flags omitted"
    - "Mode-aware probe: gateway curl-with-bearer (env-only token) OR scripts probe fallback"
    - "curl --max-time + --retry-connrefused (Pitfall 6 startup-deadlock avoidance)"
    - "jq -c JSON composition (no shell-string concatenation; T-12-05 tampering mitigation)"
    - "INDEX.md probe-note appended on degraded-mode (D-16 operator visibility)"
key-files:
  created: []
  modified:
    - workspace/.claude/skills/malware-analysis-orchestrator/scripts/update_state.py
    - workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh
    - workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md
decisions:
  - "Shell route over Python for populate_dynamic_caps (D-16 + Claude's Discretion + Open Question 1 in 12-RESEARCH.md): init_status_tree.sh is existing entry point; curl+jq pattern mirrors scripts/probe_dynamic_tools.sh"
  - "Project root path is 4 levels up from SKILL_DIR via $SKILL_DIR/../../../.. (workspace/.claude/skills/malware-analysis-orchestrator/ → repo root) — plan's path note was off by one; verified by direct cd"
  - "scripts-mode fallback ptrace_scope grep updated from 'ptrace_scope: <int>' to 'ptrace_scope=<int>' to match actual scripts/probe_dynamic_tools.sh:39 marker format ([OK] ptrace_scope=$scope)"
  - "Rule-2 defensive guard: scripts-mode fallback now requires jq alongside probe script (avoids stray 'command not found' warnings on hosts lacking jq; degrades to dynamic_mode_enabled=false + INDEX.md note)"
metrics:
  duration: 5m26s
  tasks_completed: 3
  files_modified: 3
  commits:
    - e510310: Extend update_state.py with --probe-dynamic flag and three new schema keys (12-03)
    - 3dad871: Extend init_status_tree.sh with populate_dynamic_caps mode-aware probe (12-03)
    - ea20919: Document v1.1 CURRENT_STATE.json schema extension in artifact-spec.md (12-03)
  completed: 2026-05-20
---

# Phase 12 Plan 03: Dynamic-mode Schema Plumbing Summary

**One-liner:** Extended `update_state.py` (62 LoC) + `init_status_tree.sh` (135 LoC) + `artifact-spec.md` (72 LoC) to persist three new CURRENT_STATE.json keys (`mode`, `dynamic_mode_enabled`, `dynamic_capabilities`) via additive v1.1 schema, mode-aware bootstrap probe with bearer-env + retry/timeout discipline, and scripts-mode fallback parsing — turning RED tests `test_update_state_writes_dynamic_fields` and `test_artifact_spec_documents_dynamic_fields` GREEN.

## What Shipped

### Task 1 — update_state.py extension (commit e510310)

- 4 new argparse flags: `--probe-dynamic`, `--mode {gateway,scripts}`, `--dynamic-enabled {true,false}`, `--dynamic-caps <json>`
- 3 new top-level state keys: `mode`, `dynamic_mode_enabled`, `dynamic_capabilities`
- New helper `_read_existing_state()` — read-modify-write merge preserves existing values when CLI flags omitted (additive bootstrap pattern, backward compatible)
- Malformed `--dynamic-caps` JSON exits 2 with `"error: invalid JSON for --dynamic-caps: ..."` message, CURRENT_STATE.json untouched (T-12-09 tampering mitigation)
- Non-object payload rejected with `"--dynamic-caps must be a JSON object, got <type>"`
- Existing print message preserved for no-flag invocation; `--probe-dynamic` adds detailed line listing the three resolved fields
- `import sys` added next to existing `import argparse` / `import json`
- Backward compat verified: `update_state.py --status-dir <dir> --phase test` (no new flags) still works, defaults applied (`mode="scripts"`, `dynamic_mode_enabled=false`, `dynamic_capabilities={}`)

### Task 2 — init_status_tree.sh extension (commit 3dad871)

- New `populate_dynamic_caps()` function (~120 LoC) invoked at case-init time AFTER existing `touch` loop, BEFORE final echo
- Bearer token read from `MCP_GATEWAY_TOKEN` env var only (T-12-02 mitigation); literal-token negative grep = 0 matches
- Gateway-mode probe: curl POST `tools/call` `get_dynamic_capabilities` via `/mcp` Streamable HTTP; healthz probe uses `--max-time 3 --retry 3 --retry-delay 1 --retry-connrefused` (T-12-06 startup-deadlock mitigation, Pitfall 6); tools/call uses `--max-time 5`; total worst-case ≤ 9 s
- Maps gateway DynamicCapabilities fields → skill 4-key schema:
  - `ptrace_scope` → `ptrace_scope`
  - `binfmt_misc_mounted` → `binfmt_misc`
  - `qemu_architectures` → `qemu_archs`
  - `netns_feasible` → `netns_feasible`
- Scripts-mode fallback parses `scripts/probe_dynamic_tools.sh` stdout via `grep -oP` + `jq` (T-12-05: no `eval`, no shell-string composition; values cast through `jq --argjson`)
- INDEX.md probe-note appended when degraded (D-16 operator visibility): mode, dynamic_mode_enabled, reason note
- Calls `update_state.py --probe-dynamic --mode ... --dynamic-enabled ... --dynamic-caps ...` to splice values

### Task 3 — artifact-spec.md schema documentation (commit ea20919)

- CURRENT_STATE.json schema block extended with 3 new keys (v1.1 marker)
- New `#### v1.1 Field semantics` subsection — full prose for `mode`, `dynamic_mode_enabled`, `dynamic_capabilities` plus 4 sub-fields with value semantics (ptrace_scope: 0/1/2/3 enum; binfmt_misc bool; qemu_archs example; netns_feasible meaning)
- New `#### Re-probe path (D-17)` subsection — paste-ready curl/jq one-liner for gateway-mode re-probe, plus scripts-mode fallback note
- New `#### Skipped-steps INDEX.md subsection` — D-18 table showing two example rows (W-5/strace-all + W-7/qemu-mipsel-run)
- Existing sections preserved verbatim (Required Files, Optional Directories, File Content Requirements for 00-10, INDEX.md prose)

## Decisions Made

1. **Shell over Python for populate_dynamic_caps** — D-16 + Claude's Discretion in CONTEXT.md + Open Question 1 in 12-RESEARCH.md all pointed at the shell route; `init_status_tree.sh` is the existing entry point and curl+jq pattern mirrors Phase 11's `scripts/probe_dynamic_tools.sh` (121 LoC precedent). Avoids cascading Python deps inside skill scripts.
2. **Project root depth = 4 levels** — Plan note documented `$SKILL_DIR/../../..` but actual path is `$SKILL_DIR/../../../..` (workspace → .claude → skills → malware-analysis-orchestrator → up four = repo root). Verified by direct `cd` before commit. Plan correctly flagged this requires "adjusting the cd in the function to use the correct depth" — verified and applied.
3. **ptrace_scope grep marker** — `scripts/probe_dynamic_tools.sh:39` emits `[OK] ptrace_scope=$scope` (equals sign, no colon). Plan suggested colon form. Adjusted grep regex to `ptrace_scope=\K-?\d+` accordingly.
4. **jq guard added to scripts-mode branch** — Rule 2 defensive: scripts-mode fallback required `jq` for both `--argjson` composition and probe-output transformation. Added `command -v jq` guard alongside the `-x "$probe_script"` check, with descriptive INDEX.md note. Avoids stray "jq: command not found" stderr lines on minimal hosts and gracefully degrades.

## Tests Flipped GREEN

| Test | Status |
|------|--------|
| `tests/test_skill_md_dual_mode.py::test_update_state_writes_dynamic_fields` | RED → GREEN |
| `tests/test_skill_md_dual_mode.py::test_artifact_spec_documents_dynamic_fields` | RED → GREEN |

Full-suite delta: 536 passed (was 534) — +2 GREEN, matches plan's "test count increased by exactly 2" Nyquist invariant.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Project-root path depth corrected (plan note ambiguous)**
- **Found during:** Task 2
- **Issue:** Plan section under Task 2 Action listed both `$SKILL_DIR/../../..` (described as WRONG — leads to `workspace/.claude/`) and `$SKILL_DIR/../../../..` (correct — repo root). Plan explicitly said "Fix the path in the script accordingly. Use `cd "$SKILL_DIR/../../../.." && pwd` to land at repo root."
- **Fix:** Used 4-level depth `$SKILL_DIR/../../../..` in `populate_dynamic_caps` (verified by smoke test producing valid 3-key CURRENT_STATE.json).
- **Files modified:** workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh
- **Commit:** 3dad871

**2. [Rule 1 - Bug] ptrace_scope grep pattern mismatch with actual probe output**
- **Found during:** Task 2 smoke test
- **Issue:** Plan suggested grep pattern `ptrace_scope:\s*\K-?\d+` (colon-space-int) but `scripts/probe_dynamic_tools.sh:39` actually emits `[OK]   ptrace_scope=$scope (...)`  (equals sign).
- **Fix:** Adjusted regex to `ptrace_scope=\K-?\d+` to match actual probe marker.
- **Files modified:** workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh
- **Commit:** 3dad871

**3. [Rule 2 - Defensive] jq dependency guard for scripts-mode fallback**
- **Found during:** Task 2 smoke test (executor host lacks jq)
- **Issue:** Scripts-mode fallback unconditionally invokes `jq` for `--argjson` and qemu-arch composition. On hosts without jq, the script emitted `jq: command not found` to stderr but still wrote a degraded JSON via `|| echo '{}'`. Cosmetically noisy; operationally functional.
- **Fix:** Added `command -v jq >/dev/null 2>&1` to the `[[ -x "$probe_script" ]]` guard. Updated the probe-note message to mention jq when scripts-mode fails. The Kali container has jq pre-installed (apt), so production environments hit the active path; dev hosts hit the clean fallback.
- **Files modified:** workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh
- **Commit:** 3dad871

## Verification Evidence

### Targeted tests
```
tests/test_skill_md_dual_mode.py::test_update_state_writes_dynamic_fields PASSED
tests/test_skill_md_dual_mode.py::test_artifact_spec_documents_dynamic_fields PASSED
========================= 2 passed, 1 warning in 0.10s =========================
```

### Backward compatibility
```
$ python3 workspace/.claude/skills/malware-analysis-orchestrator/scripts/update_state.py --status-dir /tmp/X --phase test
Updated CURRENT_STATE.json and INDEX.md
$ cat /tmp/X/CURRENT_STATE.json | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["mode"], d["dynamic_mode_enabled"], d["dynamic_capabilities"])'
scripts False {}
```

### Malformed JSON rejected
```
$ python3 .../update_state.py --status-dir /tmp --probe-dynamic --dynamic-caps 'not json'
error: invalid JSON for --dynamic-caps: Expecting value: line 1 column 1 (char 0)
$? = 2
```

### End-to-end smoke test
```
$ tmp=$(mktemp -d) && touch "$tmp/x.bin" && pushd "$tmp" && \
    /.../init_status_tree.sh "$tmp/x.bin" --new
Initialized case directory: status/000-x.bin
RC=0
$ grep -c -E '"mode"|"dynamic_mode_enabled"|"dynamic_capabilities"' status/000-x.bin/CURRENT_STATE.json
3
```

### Token-safety negative grep (T-12-02)
```
$ grep -nE 'Bearer\s+[A-Za-z0-9]{8,}' init_status_tree.sh artifact-spec.md | grep -v '\$MCP_GATEWAY_TOKEN\|\$token'
(no output — zero literal tokens)
```

### Full suite regression check
- 536 passed, 46 skipped, 6 failed.
- The 6 failures are PRE-EXISTING:
  - `test_acl_available.py::test_setfacl_on_path` — Phase 7 host-lacks-setfacl skip pattern (was failing before 12-03)
  - `test_skill_md_dual_mode.py::test_backend_priority_correct` + `test_no_legacy_bn_first_priority` — Plan 12-01 tracked these as pre-existing
  - `jobs/test_errors.py::test_unknown_tool_shape` + 2 in `jobs/test_list_tool_jobs.py` — pass when run in isolation; test-isolation interaction noted in STATE.md Plan 09-04 accumulated context (full-reset pattern)

Verified by checking out HEAD~3 versions of the three Plan 12-03 files and confirming SKILL.md/setfacl failures persisted; jobs failures isolated to full-suite-ordering effect, NOT introduced by this plan.

## Self-Check: PASSED

Files modified:
- FOUND: workspace/.claude/skills/malware-analysis-orchestrator/scripts/update_state.py
- FOUND: workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh
- FOUND: workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md

Commits:
- FOUND: e510310 (Task 1 — update_state.py)
- FOUND: 3dad871 (Task 2 — init_status_tree.sh)
- FOUND: ea20919 (Task 3 — artifact-spec.md)

Success criteria all met:
- [x] update_state.py accepts 4 new flags, writes 3 new schema keys, preserves backward compat, rejects malformed JSON
- [x] init_status_tree.sh invokes populate_dynamic_caps at case-init; gateway probe uses env-only bearer + retry/timeout; scripts fallback parses probe_dynamic_tools.sh; INDEX.md note on failure
- [x] artifact-spec.md documents schema extension with field semantics + re-probe path + skipped-steps subsection
- [x] test_update_state_writes_dynamic_fields GREEN
- [x] test_artifact_spec_documents_dynamic_fields GREEN
- [x] Backward compat: no-flag invocation works; re-init reuses existing case dir
- [x] No literal bearer tokens (T-12-02 negative grep = 0)
- [x] No new regressions (6 pre-existing failures persist; +2 GREEN delta confirmed)
