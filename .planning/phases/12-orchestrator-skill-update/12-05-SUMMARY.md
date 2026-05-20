---
phase: 12-orchestrator-skill-update
plan: 05
subsystem: orchestrator-skill / dynamic-mode-populate
tags: [gap-closure, hi-01, hi-02, hi-03, dynamic-mode, mcp-streamable-http, skill-scripts]
requirements: [SKILL-03, SKILL-04]
gap_closure: true
dependency-graph:
  requires:
    - 12-04-SUMMARY.md (SKILL.md v1.1 rewrite; baseline sha256 anchor)
    - 12-03-SUMMARY.md (populate_dynamic_caps populated in init_status_tree.sh)
    - scripts/probe_dynamic_tools.sh (Phase 11 / repo root)
  provides:
    - "HI-01 fix: probe_rc captured via set +e / rc=$? / set -e pattern"
    - "HI-02 fix: qemu_archs detected by direct command -v loop, no probe-output parsing"
    - "HI-03 fix: Accept: application/json, text/event-stream header on curl + awk SSE-prefix-strip"
    - "Skill-side scripts/probe_dynamic_tools.sh wrapper that exec's repo-root probe"
    - "artifact-spec.md Re-probe example carries Accept header + SSE strip (mirrors init_status_tree.sh)"
  affects:
    - W-5 dynamic-only step skip decisions (depend on dynamic_mode_enabled correctness)
    - W-7 fine-grained skip (depends on qemu_archs correctness)
tech-stack:
  added: []
  patterns:
    - "set +e / rc=$? / set -e pattern to capture exit code under `set -euo pipefail`"
    - "Direct command -v loop over known arch list (instead of fragile regex parsing of human-readable probe output)"
    - "MCP Streamable HTTP (2025-03-26) curl example with Accept header + SSE normalization"
    - "Thin skill-side wrapper that exec's a canonical repo-root script"
key-files:
  created:
    - workspace/.claude/skills/malware-analysis-orchestrator/scripts/probe_dynamic_tools.sh
  modified:
    - workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh
    - workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md
decisions:
  - "Chose option (b) — skill-side wrapper exec'ing repo-root probe — over (a) absolute path in W-7 doc or (c) test path-resolver change; least invasive, no test changes, no doc contortions, creates a natural skill-side affordance"
  - "qemu_archs detection moved OUT of probe-output parsing and INTO direct command -v loop because scripts/probe_dynamic_tools.sh only emits a count summary (no per-arch tokens)"
  - "Used the awk single-pass form for SSE normalization (idempotent on plain JSON; correctly strips SSE framing when present)"
  - "Used the two-line intermediate `$resp` variable form in artifact-spec.md for unambiguous markdown rendering of nested awk single-quoted programs"
key-decisions:
  - "Skill-side probe_dynamic_tools.sh wrapper (option b) chosen over W-7 doc edit (option a) or test resolver change (option c)"
  - "qemu_archs computed by direct command -v loop (not by parsing probe output)"
  - "SSE normalization implemented as idempotent awk pass; survives both application/json and text/event-stream responses"
metrics:
  duration: 145s
  task_count: 1
  file_count: 3
  completed: "2026-05-20T06:40:19Z"
---

# Phase 12 Plan 05: Phase 12 Gap Closure — HI-01/HI-02/HI-03 Fixes + Skill-Side Probe Wrapper Summary

**One-liner:** Closes the three HIGH-severity correctness bugs in `populate_dynamic_caps` (broken probe_rc capture, unmatchable qemu_archs regex, missing MCP Streamable HTTP Accept header + SSE strip), echoes the HI-03 fix into the documented operator example in artifact-spec.md, and adds a thin skill-side `scripts/probe_dynamic_tools.sh` wrapper so the W-7 reference resolves under the test path resolver — bringing Phase 12 from 51/52 GREEN to **52/52 GREEN**.

## Scope

This plan was a targeted gap-closure pass requested by `12-VERIFICATION.md`:

- **Gap 1 (SKILL-04 partial)** — `populate_dynamic_caps` in `init_status_tree.sh` had three correctness bugs that silently degraded the dynamic-mode populate path under `set -euo pipefail`:
  - **HI-01:** `probe_rc=$?` always captured `0` because the preceding command substitution contained `|| true`. The `if [[ "$probe_rc" -eq 0 ... ]]` gate at line ~199 therefore always evaluated true on a failed probe — so a probe that exited 1 was silently treated as success, and `dynamic_mode_enabled=true` was written even when capabilities were missing.
  - **HI-02:** The grep regex `qemu-\K[a-z0-9_]+(?=-static)` never matched the actual `scripts/probe_dynamic_tools.sh` output, because the probe emits only a count summary (`qemu-*-static binaries available: N arches`), not per-arch tokens. Result: `qemu_archs=[]` in scripts-mode even when `qemu-mipsel-static` etc. were on PATH — breaking W-7 fine-grained skip.
  - **HI-03:** The gateway-mode `curl POST /mcp` was missing the `Accept: application/json, text/event-stream` header required by MCP Streamable HTTP (protocol 2025-03-26). FastMCP rejects or SSE-frames such responses; the subsequent `jq` parse assumed plain JSON-RPC envelope, so the gateway path silently never succeeded end-to-end. The same broken example was also documented for operators in `references/artifact-spec.md`.

- **Gap 2 (1 RED test in phase regression suite)** — `test_scripts_references_resolve` was RED because `W-7-cross-arch-iot.md:29` references `scripts/probe_dynamic_tools.sh` which existed only at the repo root, not in the skill's `scripts/` dir. Resolution chosen: option (b) — add a thin skill-side wrapper that exec's the repo-root probe.

## Concrete Edits

### 1. HI-01 fix in `init_status_tree.sh::populate_dynamic_caps`

Replaced the `|| true` + `$?` pair (which silently always-zeros the rc under `set -euo pipefail`) with the `set +e` / `rc=$?` / `set -e` pattern:

```bash
local probe_out probe_rc
set +e
probe_out=$("$probe_script" 2>&1)
probe_rc=$?
set -e
```

The downstream gate at the bottom of the scripts-mode branch (`if [[ "$probe_rc" -eq 0 && "$dyn_caps_json" != '{}' ]]; then dyn_enabled='true' ...`) now correctly distinguishes probe-success from probe-failure.

### 2. HI-02 fix in `init_status_tree.sh::populate_dynamic_caps`

Replaced the never-matching `grep -oP 'qemu-\K[a-z0-9_]+(?=-static)'` regex (which keyed off output the probe does not emit) with a direct `command -v` loop over the SAME arch list the repo-root probe uses (`scripts/probe_dynamic_tools.sh:93`):

```bash
local _qemu_archs_tmp=()
local _arch
for _arch in arm aarch64 mips mipsel ppc ppc64 i386 x86_64 riscv64 sparc; do
  if command -v "qemu-${_arch}-static" >/dev/null 2>&1; then
    _qemu_archs_tmp+=("$_arch")
  fi
done
if [[ ${#_qemu_archs_tmp[@]} -gt 0 ]]; then
  qemu_archs=$(printf '%s\n' "${_qemu_archs_tmp[@]}" | jq -R . | jq -sc . 2>/dev/null || echo '[]')
else
  qemu_archs='[]'
fi
```

This is robust to any future format change in the probe's output and produces the exact array shape consumed by W-7's fine-grained skip.

### 3. HI-03 fix in `init_status_tree.sh::populate_dynamic_caps`

Added the `Accept: application/json, text/event-stream` header to the gateway-mode `curl POST /mcp` and an idempotent awk pass that strips `data: ` SSE-prefix lines before the downstream jq parse:

```bash
resp=$(curl -sf --max-time 5 -X POST \
         -H "Authorization: Bearer $token" \
         -H "Content-Type: application/json" \
         -H "Accept: application/json, text/event-stream" \
         -d '{"jsonrpc":"2.0","id":1,...}' \
         "http://${host}:${port}/mcp" 2>/dev/null || echo '')
if [[ -n "$resp" ]]; then
  resp=$(printf '%s' "$resp" | awk '
    /^data: / { sub(/^data: /, ""); sse=1; print; next }
    { if (!sse) print }
  ' | tr -d '\r')
  ...
```

The awk pass is idempotent on plain JSON responses (no `data: ` lines → all lines emitted unchanged) and correctly strips SSE framing when present.

### 4. HI-03 echo fix in `references/artifact-spec.md`

The Re-probe path example previously documented the same broken curl shape (no Accept header, no SSE strip). Replaced it with the two-line `$resp`-intermediate form that mirrors the structure now in `init_status_tree.sh`:

```bash
resp=$(curl -sf -H "Authorization: Bearer $MCP_GATEWAY_TOKEN" \
            -X POST -H "Content-Type: application/json" \
            -H "Accept: application/json, text/event-stream" \
            -d '{"jsonrpc":"2.0","id":1,...}' \
            http://127.0.0.1:${MCP_GATEWAY_HOST_PORT:-8080}/mcp)
scripts/update_state.py --status-dir <case_dir> --probe-dynamic \
  --mode gateway --dynamic-enabled true \
  --dynamic-caps "$(printf '%s' "$resp" | awk '/^data: /{sub(/^data: /, ""); sse=1; print; next} {if (!sse) print}' | tr -d '\r' \
                  | jq -c '.result.content[0].text|fromjson|{ptrace_scope, binfmt_misc:.binfmt_misc_mounted, qemu_archs:.qemu_architectures, netns_feasible}')"
```

The two-line form avoids the markdown-rendering ambiguity of nested single-quoted awk programs inside a `$(...)` substitution, and matches the structure already in `init_status_tree.sh`.

### 5. New `workspace/.claude/skills/malware-analysis-orchestrator/scripts/probe_dynamic_tools.sh`

A 25-line thin wrapper that resolves the repo-root probe path (5 levels up from `SKILL_DIR/scripts/`) and `exec`'s it with `"$@"` passthrough. Includes a clear `[WARN]` and `exit 2` when the repo-root probe is missing or non-executable, so callers see a deterministic failure mode rather than an opaque `set -euo pipefail` abort.

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
REPO_PROBE="$REPO_ROOT/scripts/probe_dynamic_tools.sh"
...
exec "$REPO_PROBE" "$@"
```

Path verification (5 levels):
- L0: `…/scripts/`
- L1: `…/malware-analysis-orchestrator/`
- L2: `…/skills/`
- L3: `…/.claude/`
- L4: `…/workspace/`
- L5: repo root ✓

Confirmed against the live tree:
```
$ cd workspace/.claude/skills/malware-analysis-orchestrator/scripts && cd ../../../../.. && pwd
/home/cervon/Code/MARE-MCP-Toolbox
```

## Acceptance Criteria Status

All 17 acceptance criteria from `12-05-PLAN.md` PASS:

| # | Criterion | Result |
|---|-----------|--------|
| 1 | `grep -F "set +e"` in init returns ≥1 match | PASS (1 match at line 174) |
| 2 | `\|\| true` on `probe_out=` removed | PASS (count = 0) |
| 4 | `command -v "qemu-...` present | PASS (line 199) |
| 5 | Arch list `arm aarch64 mips mipsel ...` present | PASS (line 198) |
| 6 | Broken `qemu-\K[a-z0-9_]+` regex absent | PASS (grep rc=1) |
| 7 | Accept header in init: count ≥1 | PASS (count = 1) |
| 8 | Accept header in artifact-spec: count ≥1 | PASS (count = 1) |
| 9 | SSE-strip logic in init present | PASS (lines 138-141) |
| 10 | SSE-strip logic in artifact-spec present | PASS (lines 187, 196) |
| 11 | Wrapper exists AND is executable | PASS (rwxr-xr-x) |
| 12 | Wrapper contains `exec` | PASS (3 matches) |
| 13 | Wrapper ≥ 8 lines | PASS (25 lines) |
| 14 | `bash -n init_status_tree.sh` exit 0 | PASS |
| 15 | `bash -n probe_dynamic_tools.sh` exit 0 | PASS |
| 16 | `pytest test_skill_md_dual_mode.py` 52 passed | PASS (52 passed, 0 failed) |
| 17 | SKILL.md sha256 unchanged | PASS (`5b88955c…` matches baseline) |

(Criterion 3 is a documentation runtime test that the plan marked optional in favor of line-range inspection; verified by reading lines 195-203 of init_status_tree.sh — the gate `if [[ "$probe_rc" -eq 0 && "$dyn_caps_json" != '{}' ]]` is intact and now sees a correctly-captured rc.)

## Test Results

```text
$ mcp-gateway/.venv/bin/python -m pytest mcp-gateway/tests/test_skill_md_dual_mode.py -q
....................................................                     [100%]
52 passed, 1 warning in 0.77s
```

Before this plan: **51 passed, 1 failed** (`test_scripts_references_resolve` RED on `scripts/probe_dynamic_tools.sh` missing).
After this plan: **52 passed, 0 failed**.

## SKILL.md Snapshot Drift Check

SKILL.md was NOT touched by this plan. Verified:

```text
$ sha256sum workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md
5b88955c64e09db189a22a3c1c2e97298468f7fce81c7ef484d9cf5d85f233ab  …/SKILL.md
$ cat mcp-gateway/tests/snapshots/SKILL.md.sha256
5b88955c64e09db189a22a3c1c2e97298468f7fce81c7ef484d9cf5d85f233ab
```

Both match — no baseline drift.

## Deviations from Plan

None. The plan's `<action>` block specified the awk single-pass form for the SSE strip in `init_status_tree.sh` and the two-line `$resp`-intermediate form for `artifact-spec.md`; both were applied verbatim. The probe wrapper was created with the exact content specified in the plan and `chmod +x`'d as recommended.

## Files Touched

| File | Change | Lines |
|------|--------|-------|
| `workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh` | HI-01 + HI-02 + HI-03 fixes inside `populate_dynamic_caps` | +50 / −7 (net +43) |
| `workspace/.claude/skills/malware-analysis-orchestrator/scripts/probe_dynamic_tools.sh` | NEW thin wrapper that exec's the repo-root probe | +25 |
| `workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md` | Re-probe curl example: Accept header + awk SSE strip via two-line `$resp` form | +12 / −1 (net +11) |

## Commits

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Fix HI-01/02/03 + skill-side probe wrapper + artifact-spec.md Accept header echo | `3a2c0e8` |

## Self-Check: PASSED

- File existence verified:
  - `workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh` — FOUND
  - `workspace/.claude/skills/malware-analysis-orchestrator/scripts/probe_dynamic_tools.sh` — FOUND (executable)
  - `workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md` — FOUND
- Commit existence verified: `3a2c0e8` in `git log --oneline`
- Regression suite: 52 passed, 0 failed
- SKILL.md sha256 baseline: matches live SKILL.md
