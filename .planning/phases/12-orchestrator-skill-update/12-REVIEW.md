---
phase: 12-orchestrator-skill-update
reviewed: 2026-05-20T05:34:52Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - mcp-gateway/tests/test_skill_md_dual_mode.py
  - workspace/.claude/skills/malware-analysis-orchestrator/SKILL.md
  - workspace/.claude/skills/malware-analysis-orchestrator/scripts/update_state.py
  - workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh
  - workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md
  - workspace/.claude/skills/malware-analysis-orchestrator/references/workflow.md
  - workspace/.claude/skills/malware-analysis-orchestrator/references/deep-analysis-checklist.md
  - workspace/.claude/skills/malware-analysis-orchestrator/references/deep-re-workflows.md
  - workspace/.claude/skills/malware-analysis-orchestrator/references/workflows/W-1-packed-binary-triage.md
  - workspace/.claude/skills/malware-analysis-orchestrator/references/workflows/W-2-elf-deep-dive.md
  - workspace/.claude/skills/malware-analysis-orchestrator/references/workflows/W-3-pe-deep-dive.md
  - workspace/.claude/skills/malware-analysis-orchestrator/references/workflows/W-4-rop-gadget-hunt.md
  - workspace/.claude/skills/malware-analysis-orchestrator/references/workflows/W-5-dynamic-api-trace.md
  - workspace/.claude/skills/malware-analysis-orchestrator/references/workflows/W-6-firmware-unpack.md
  - workspace/.claude/skills/malware-analysis-orchestrator/references/workflows/W-7-cross-arch-iot.md
findings:
  blocking: 0
  high: 3
  medium: 4
  low: 4
  nit: 2
  total: 13
status: issues_found
---

# Phase 12: Code Review Report

**Reviewed:** 2026-05-20T05:34:52Z
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

Phase 12 lands the malware-analysis-orchestrator skill v1.1: backend priority swap
(IDA > BN > Ghidra), seven W-N deep-RE workflows, dual-mode prose, dynamic-mode
schema fields, and a CI regression test. The Python CLI extension
(`update_state.py`), the markdown surface (SKILL.md, workflow.md, W-1..W-7,
artifact-spec.md, deep-re-workflows.md, deep-analysis-checklist.md), and the
pytest module are coherent and aligned with the four plans in this phase. Tests
pass 51/52 (the one failing assertion is the acknowledged-out-of-scope
`probe_dynamic_tools.sh` reference in W-7).

The Bash extension to `init_status_tree.sh` (D-16 gateway-mode probe +
scripts-mode fallback) is the weakest area. Three correctness bugs in the
scripts-mode probe path mean `dynamic_capabilities` will silently be
populated incorrectly when the gateway path is unavailable — `probe_rc` always
captures 0 (masked by `|| true` inside command substitution), `qemu_archs`
parsing will never match the project-root probe script's actual output format,
and the curl gateway-mode probe likely cannot speak Streamable HTTP with only
`Content-Type` set (no `Accept: application/json, text/event-stream`). The
container falls through to scripts-mode in the failure case so end-to-end
init still produces a CURRENT_STATE.json with the three new keys at defaults
(this is verified by Plan 03 acceptance criteria), but the capability map will
be empty/incorrect when the probe should have populated it. Severity is HIGH
because dynamic-mode skip behavior in W-5/W-7 keys off these values.

The Python CLI (`update_state.py`) is solid: argparse with `choices=`, explicit
JSON error path with `sys.exit(2)`, isinstance-checked dynamic_capabilities,
read-modify-write that preserves existing values on no-flag invocations.
Backward-compatible.

The test module is well-structured with sensible RED-stub discipline, soft
snapshot warnings, and parametrized W-N coverage. One MEDIUM finding: the
`FALLBACK_RE` `\belse\b` term is permissive enough to mask real fallback
omissions in prose that incidentally contains the word "else". Two LOW
findings on regex robustness and one NIT on subtle f-string assumptions.

The known-out-of-scope `probe_dynamic_tools.sh` path-resolution issue in W-7
is acknowledged and not raised here per the review prompt.

## High

### HI-01: `init_status_tree.sh` — `probe_rc` always 0 due to `|| true` inside command substitution

**File:** `workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh:166-167`
**Issue:**
```bash
probe_out=$("$probe_script" 2>&1 || true)
probe_rc=$?
```
The `|| true` clause inside the command substitution masks the probe script's
exit code, so `$?` after the assignment is the exit code of the command
substitution itself — always 0. Verified empirically:
```
$ out=$(fail_cmd 2>&1 || true); rc=$?; echo "rc=$rc"
rc=0
```
This breaks the intended `if [[ "$probe_rc" -eq 0 && "$dyn_caps_json" != '{}' ]]` gate
on line 199. The branch evaluates only the caps-non-empty condition, so a probe
that runs and partially populates fields but exits non-zero (e.g.,
`probe_dynamic_tools.sh` line 102 sets `fail=1` when qemu-static binaries are
missing, then exits non-zero) is silently treated as success. The user gets
`dynamic_mode_enabled=true` even when the probe explicitly signaled failure.

**Fix:** capture exit status via `PIPESTATUS` or by restructuring to not need
`|| true`:
```bash
# Option A: pipefail-safe, no `|| true`
set +e
probe_out=$("$probe_script" 2>&1)
probe_rc=$?
set -e

# Option B: tee-pattern (preferred — keeps set -e)
probe_out=$("$probe_script" 2>&1; echo "EXIT:$?")
probe_rc=${probe_out##*EXIT:}
probe_out=${probe_out%EXIT:*}
```

### HI-02: `init_status_tree.sh` — `qemu_archs` regex never matches `probe_dynamic_tools.sh` actual output

**File:** `workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh:184`
**Issue:**
```bash
qemu_archs=$(echo "$probe_out" | grep -oP 'qemu-\K[a-z0-9_]+(?=-static)' | jq -R . | jq -sc . 2>/dev/null || echo '[]')
```
The init script assumes `probe_dynamic_tools.sh` emits per-arch tokens like
`qemu-mipsel-static`, `qemu-arm-static`, etc. The actual probe output
(`scripts/probe_dynamic_tools.sh:91-103`) does NOT list arches individually
— it only emits a count summary:
```
[OK]   qemu-*-static binaries available: 3 arches
```
and a `say_info` line: `binfmt_misc: ... explicit qemu-<arch>-static)` (which
contains the literal `<arch>` token, with `<` and `>` chars that don't match
`[a-z0-9_]+`). Result: `qemu_archs` is always `[]` in scripts-mode, even when
qemu binaries are installed. This breaks W-7's fine-grained skip behavior
(`mipsel not in qemu_archs` — the skip will always fire because the array
is empty).

**Fix:** either probe qemu binaries directly in scripts-mode instead of
parsing the probe's stdout, or change `probe_dynamic_tools.sh` to emit
machine-readable arch tokens. Concretely, replace the regex with direct probe:
```bash
qemu_archs_arr=()
for arch in arm aarch64 mips mipsel ppc ppc64 i386 x86_64 riscv64 sparc; do
  if command -v "qemu-${arch}-static" >/dev/null 2>&1; then
    qemu_archs_arr+=("$arch")
  fi
done
qemu_archs=$(printf '%s\n' "${qemu_archs_arr[@]}" | jq -R . | jq -sc . 2>/dev/null || echo '[]')
```

### HI-03: `init_status_tree.sh` — curl POST to `/mcp` lacks required Accept header for Streamable HTTP

**File:** `workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh:130-134`
**Issue:**
```bash
resp=$(curl -sf --max-time 5 -X POST \
         -H "Authorization: Bearer $token" \
         -H "Content-Type: application/json" \
         -d '{"jsonrpc":"2.0",...}' \
         "http://${host}:${port}/mcp" 2>/dev/null || echo '')
```
MCP Streamable HTTP (protocol 2025-03-26) requires clients send
`Accept: application/json, text/event-stream` to negotiate transport.
FastMCP's streamable_http_app() will typically reject (415/406) or return
SSE-framed responses without proper Accept negotiation. The subsequent
`jq -r '.result.content[0].text'` parse assumes a plain JSON-RPC envelope,
which is the wrong assumption for SSE-framed responses. End-to-end the
gateway-mode probe never succeeds, so the code always falls through to
scripts-mode (which itself has HI-01/HI-02 bugs).

The same shape appears in `references/artifact-spec.md:184-191` in the
Re-probe path example — anyone copy-pasting that command will hit the same
issue.

**Fix:**
```bash
resp=$(curl -sf --max-time 5 -X POST \
         -H "Authorization: Bearer $token" \
         -H "Content-Type: application/json" \
         -H "Accept: application/json, text/event-stream" \
         -d '...' \
         "http://${host}:${port}/mcp" 2>/dev/null || echo '')
```
and document in artifact-spec.md that consumers parsing the body may need to
strip an `event: message\ndata: ` prefix if SSE framing is returned. Better:
fetch the response and try both JSON-direct parse and SSE-stripped parse.

## Medium

### ME-01: `test_skill_md_dual_mode.py` — `FALLBACK_RE` `\belse\b` term is broadly permissive

**File:** `mcp-gateway/tests/test_skill_md_dual_mode.py:41`
**Issue:**
```python
FALLBACK_RE = re.compile(r"scripts/|\bfallback\b|\belse\b", re.IGNORECASE)
```
The word "else" appears in prose extremely frequently (control flow snippets,
narrative sentences like "or else ...", "else where ..."). Any
`mcp__mare-toolbox__*` reference whose ±3-line window happens to contain
that word — even in an unrelated sentence — is treated as "has a fallback"
and the dual-mode invariant test passes. This creates false-negatives: a
real fallback omission near unrelated "else" prose silently slips through.
The plan acknowledges this as an intentional regex window choice, but the
risk class is broader than the doc anticipates.

**Fix:** tighten the regex to look for `else` only in code-style contexts
(after `if`/`elif`, with colon, or inside backticks):
```python
FALLBACK_RE = re.compile(
    r"scripts/|\bfallback\b|`else`|^\s*else\b|^\s*else:\s*$",
    re.IGNORECASE | re.MULTILINE,
)
```
Alternatively, drop the `else` term entirely — `scripts/` and `fallback`
cover the actual D-09 pattern, and the W-N tables consistently use one of
those.

### ME-02: `update_state.py` — JSON schema for `dynamic_capabilities` not validated

**File:** `workspace/.claude/skills/malware-analysis-orchestrator/scripts/update_state.py:150-163`
**Issue:** the CLI accepts any JSON object as `--dynamic-caps` and writes it
verbatim. Mismatched shapes (missing `ptrace_scope`, extra keys, wrong types)
will pass through. `artifact-spec.md` documents a fixed shape with four keys
(`ptrace_scope`, `binfmt_misc`, `qemu_archs`, `netns_feasible`), but the CLI
will happily accept `{"foo": "bar"}` and downstream W-5/W-7 skip logic will
then fail on `KeyError`/`TypeError` at agent decision time, not at the write
boundary.

**Fix:** add a minimal type/shape check with a clear error message. The four
top-level keys are stable across Phase 11 and this phase; rejecting unknown
keys is overkill (D-15 says "additive"), but the four documented keys should
be present with the documented types when they appear:
```python
SCHEMA = {
    "ptrace_scope": (int, type(None)),
    "binfmt_misc": (bool,),
    "qemu_archs": (list,),
    "netns_feasible": (bool,),
}
for k, types in SCHEMA.items():
    if k in parsed and not isinstance(parsed[k], types):
        print(f"error: dynamic_capabilities.{k} must be {types}, got {type(parsed[k]).__name__}",
              file=sys.stderr)
        sys.exit(2)
```

### ME-03: `init_status_tree.sh` — INDEX.md note is appended after `update_state.py` rewrites it; lost on re-run

**File:** `workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh:215-223`
**Issue:** `populate_dynamic_caps` calls `update_state.py --probe-dynamic`
(line 210), which calls `update_index()` and rewrites `INDEX.md` (overwrites
via `write_text` at `update_state.py:80`). The probe note (lines 215-223) is
then appended. On any subsequent `update_state.py` invocation (e.g., later
analysis phases), `update_index()` rewrites INDEX.md again, dropping the
probe note. The schema-extension fields in `CURRENT_STATE.json` survive (they
go through the additive-merge path), but the human-readable diagnostic note
documenting *why* dynamic mode is off is silently discarded.

This is partly an issue with the pre-Phase-12 `update_index()` design (full
rewrite), but Phase 12 introduces the probe note that depends on the
append-only assumption.

**Fix:** either (a) write the probe note into a dedicated sidecar file
(`<case_dir>/dynamic/probe-notes.md`) that update_index reads and includes,
or (b) have `update_state.py` accept a `--probe-note <text>` flag and embed
the note into the generated INDEX.md inside the rewrite. Option (b) is
simpler:
```python
parser.add_argument("--probe-note", default=None)
# inside update_index:
if probe_note:
    content.extend(["", "## Dynamic-mode probe note", probe_note])
```

### ME-04: `init_status_tree.sh` — gateway probe response parsing assumes plain JSON-RPC, not SSE-framed

**File:** `workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh:138`
**Issue:** related to HI-03 but worth flagging separately:
```bash
payload=$(echo "$resp" | jq -r '.result.content[0].text // empty' 2>/dev/null || echo '')
```
This assumes `$resp` is a JSON document. If the server returns an SSE stream
(`event: message\ndata: {...}\n\n`), the jq parse fails silently
(`2>/dev/null || echo ''`) and `payload` becomes empty — the script sets
`probe_note="gateway responded but get_dynamic_capabilities payload was empty"`
and falls through to scripts-mode. The user never sees the actual SSE framing
in the diagnostic.

**Fix:** detect SSE framing and strip it:
```bash
if [[ "$resp" == *"event:"*"data:"* ]]; then
    resp=$(echo "$resp" | sed -n 's/^data: //p' | head -1)
fi
payload=$(echo "$resp" | jq -r '.result.content[0].text // empty' 2>/dev/null || echo '')
```

## Low

### LO-01: `update_state.py` — `_read_existing_state` uses `errors="ignore"` and may corrupt non-UTF-8 detection

**File:** `workspace/.claude/skills/malware-analysis-orchestrator/scripts/update_state.py:89`
**Issue:** `json.loads(p.read_text(errors="ignore"))` silently drops invalid
UTF-8 bytes. If CURRENT_STATE.json gets corrupted with non-UTF-8 (unlikely
but possible with binary content from a tool dump), the read returns a
truncated/cleaned string that may then parse as valid JSON of a different
shape — silently. The except clause only catches `JSONDecodeError`.

**Fix:** use `errors="strict"` (default) and add `UnicodeDecodeError` to the
except clause:
```python
try:
    return json.loads(p.read_text(encoding="utf-8"))
except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
    return {}
```

### LO-02: `init_status_tree.sh` — `local probe_rc` declared after assignment, breaking the local-scoping intent

**File:** `workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh:165-167`
**Issue:**
```bash
local probe_out probe_rc
probe_out=$("$probe_script" 2>&1 || true)
probe_rc=$?
```
`local probe_out probe_rc` declares both, but `probe_rc=$?` on line 167
captures the exit status of `local probe_out probe_rc` (the declaration
statement) on line 165, not the command-substitution from line 166. Actually
re-reading: line 165 declares (rc 0), line 166 assigns probe_out (the
substitution has `|| true` so always 0), line 167 captures `$?` which is
the result of line 166's assignment — also always 0. So both HI-01 and this
finding compound: the `$?` is always 0 for two independent reasons.

**Fix:** separate declaration and assignment (and apply HI-01's fix):
```bash
local probe_out=""
local probe_rc=0
set +e
probe_out=$("$probe_script" 2>&1)
probe_rc=$?
set -e
```

### LO-03: `test_skill_md_dual_mode.py` — `ABBREVIATED_RE` does not catch `mcp__mare_toolbox__` (underscore instead of dash)

**File:** `mcp-gateway/tests/test_skill_md_dual_mode.py:42`
**Issue:**
```python
ABBREVIATED_RE = re.compile(r"mcp__mare__(?!toolbox)")  # Pitfall 3
```
This catches `mcp__mare__foo` (the abbreviated form), but does NOT catch
`mcp__mare_toolbox__foo` (underscore instead of dash). The canonical
spelling per D-10 is `mcp__mare-toolbox__` (dash). A doc edit that typos the
dash to underscore would slip through both `ABBREVIATED_RE` (doesn't match
`__mare__`) and `GATEWAY_TOOL_RE` (does match `mare_toolbox`, but with no
abbreviated-prefix gate). The `test_tool_tokens_exist_in_gateway_registry`
test catches it ONLY if `mare_toolbox__foo` is a registered tool name —
which it would NOT be since the registry contains bare tool names like
`run_file` without any `mare-toolbox` or `mare_toolbox` prefix.

Actually re-reading: `_enumerate_gateway_tools()` returns the bare tool name
set, and `TOOL_TOKEN_RE = re.compile(r"mcp__mare[-_]toolbox__([a-z0-9_]+)")`
captures the trailing part. So `mcp__mare_toolbox__run_file` would be
captured and compared against `run_file` in the registry — which would pass
incorrectly because `run_file` IS registered. The underscore-typo would
slip through silently.

**Fix:** add a positive canonical-prefix assertion that catches the
underscore typo, OR make `TOOL_TOKEN_RE` strict (require dash):
```python
TOOL_TOKEN_RE = re.compile(r"mcp__mare-toolbox__([a-z0-9_]+)")  # strict
UNDERSCORE_PREFIX_RE = re.compile(r"mcp__mare_toolbox__")
# In test_no_abbreviated_prefix:
und = UNDERSCORE_PREFIX_RE.findall(text)
assert not und, f"underscore-prefix typo (use `mare-toolbox`, not `mare_toolbox`): {und}"
```

### LO-04: `init_status_tree.sh` — bash globbing of `BASENAME` (pre-existing) can misbehave on names with glob metacharacters

**File:** `workspace/.claude/skills/malware-analysis-orchestrator/scripts/init_status_tree.sh:39-40`
**Issue:** pre-existing code, but worth flagging in this review since the
init script is now load-bearing for the v1.1 schema:
```bash
if compgen -G "$STATUS_ROOT/[0-9][0-9][0-9]-${BASENAME}" >/dev/null 2>&1; then
  for d in "$STATUS_ROOT"/[0-9][0-9][0-9]-"${BASENAME}"; do
```
If a sample filename contains `*`, `?`, or `[`/`]` (legitimate for
analyst-supplied paths and adversary-crafted filenames), the glob expansion
behaves unpredictably and may match unrelated cases. Not a security boundary
(`set -euo pipefail` will catch unbound vars; the variable is interpolated
into a glob pattern, not an argv) but a robustness concern.

**Fix:** quote-safe lookup via `find`:
```bash
mapfile -t matches < <(find "$STATUS_ROOT" -maxdepth 1 -type d \
  -regextype posix-extended -regex ".*/[0-9]{3}-$(printf '%s' "$BASENAME" | sed 's/[][\\.*?+|^$(){}]/\\&/g')$")
```

## Nit

### NI-01: `update_state.py` — `_read_existing_state` discards malformed-file diagnostic

**File:** `workspace/.claude/skills/malware-analysis-orchestrator/scripts/update_state.py:83-91`
**Issue:** when the existing `CURRENT_STATE.json` is malformed JSON, the
function silently returns `{}` and downstream code uses defaults. This
masks corruption — an operator looking at a case dir with mangled state
would see fresh defaults appear, with no warning that the previous content
was unreadable.

**Fix:** emit a stderr warning:
```python
except (json.JSONDecodeError, ValueError) as exc:
    print(f"warning: existing CURRENT_STATE.json at {p} is malformed ({exc}); using defaults",
          file=sys.stderr)
    return {}
```

### NI-02: `references/artifact-spec.md` — example curl in Re-probe path embeds raw `\\n` in the JSON `-d` body inside backticks

**File:** `workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md:187-191`
**Issue:** the docstring example uses nested double-quotes inside a `curl -d`
which is shell-tricky for the reader to copy-paste correctly. Two issues:
(1) the example uses the same `/mcp` POST that has HI-03's Accept-header bug;
(2) the inner JSON has `"name":"get_dynamic_capabilities"` — fine — but the
outer shell concatenation uses double-quotes inside `$(...)`. Some shells
need explicit escaping. Not a bug strictly, but a reader following the doc
will most likely produce a malformed request.

**Fix:** add a single-quoted JSON literal inside the `-d` arg and add the
Accept header:
```bash
--dynamic-caps "$(curl -sf \
    -H "Authorization: Bearer $MCP_GATEWAY_TOKEN" \
    -H 'Accept: application/json, text/event-stream' \
    -H 'Content-Type: application/json' \
    -X POST \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_dynamic_capabilities","arguments":{}}}' \
    "http://127.0.0.1:${MCP_GATEWAY_HOST_PORT:-8080}/mcp" \
  | jq -c '.result.content[0].text | fromjson | {ptrace_scope, binfmt_misc: .binfmt_misc_mounted, qemu_archs: .qemu_architectures, netns_feasible}')"
```

---

## Cross-cutting observations

- **Dual-mode invariant is solid in prose.** Every W-N table cell reviewed
  contains a `fallback` keyword or `scripts/` reference, satisfying D-12.
  The regex window survives in practice; ME-01 is the theoretical
  false-negative risk, not an observed violation.
- **Frontmatter discipline is correct.** SKILL.md description is single-line,
  under 1024 chars (verified ≈700 chars), ends with `.`, mentions IDA Pro
  MCP first per D-01.
- **Tool tokens cross-check.** Spot-checked `mcp__mare-toolbox__*` references
  in W-1..W-7 against the gateway tool surface (re_static, extract,
  r2_sessions, jobs, dynamic) — all referenced names map to registered
  tools.
- **Test scaffolding is sound.** REPO_ROOT walker via `.planning` marker
  (Pitfall 4 mitigation) is in place; PyYAML fallback parse path is correct;
  `UPDATE_SKILL_SNAPSHOT=1` refresh hook works; soft-warning surfaces drift
  without failing CI.
- **No security regressions.** Bearer token read from env only (T-12-02);
  no literal tokens anywhere; subprocess uses argv list (T-12-04); placeholder
  slugs constrained to closed list per W-N file (T-12-03); no `run_shell
  "$..."` interpolation in any skill prose.

_Reviewed: 2026-05-20T05:34:52Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
