---
status: awaiting_human_verify
trigger: "r2-cmd-timeout: MCP r2_cmd 30s timeout on freshly-opened r2 sessions"
created: 2026-05-21T00:00:00Z
updated: 2026-05-21T00:00:00Z
---

## Current Focus

hypothesis: ROOT CAUSE FOUND — `r2 -q0` is actually two flags (`-q` quiet + `-0` "print \x00 after init and every command"). The `\x00` byte gets prefixed to lines coming through stdout. `exec_one`'s line-loop compares `line == (sentinel + "\n").encode()` exactly, but the actual line is `b"\x00MARE_SENTINEL_...\n"` — equality fails forever, loop times out at 30s. Init path works because it uses `readuntil(sentinel_bytes)` (substring match, prefix-tolerant).
test: Removed `-0` from argv in repro_r2_timeout_no0.py and verified exec_one's line-loop matches sentinel in 0.001s. Confirmed via `r2 -h` that `-0` means "print \x00 after init and every command" — the Phase 8 D-02 doc misread `-q0` as a single combined flag.
expecting: Removing `-0` (changing `-q0` to `-q` in argv) fixes the bug without any other code changes; the explicit `?e <sentinel>` mechanism already provides delimiting, so the `\x00` separator was redundant.
next_action: Apply fix in mcp-gateway/src/mcp_gateway/sessions/r2.py — change argv `"-q0"` → `"-q"`. Re-run repro. Add regression test that exercises the real r2 subprocess (not monkey-patched).

## Symptoms

expected: After `open_r2_session` returns success, `r2_cmd` with `?V` returns r2's version string within ~1s.
actual: `open_r2_session` succeeds; first `r2_cmd` hangs exactly 30s (MCP_GATEWAY_R2_CMD_TIMEOUT_S default); `R2Session.exec_one` returns timed_out=True; session reaped.
errors: No exceptions; clean timeout.
reproduction: |
  1. Container running with r2 6.0.5
  2. Open r2 session via gateway
  3. Call r2_cmd with cmd="?V"
  4. Observe 30s hang
started: Discovered 2026-05-21 during Phase 14 Plan 04 HARDEN-03 live arm UAT.

## Eliminated

- hypothesis: (A) r2 stdout block-buffered on pipes
  evidence: Repro showed all four output lines arrive in 0.000s after `?V` — no buffering delay. The bug is in the line-comparison logic, not flush timing.
  timestamp: 2026-05-21T (after first repro)

- hypothesis: (B) cfg.sandbox=true blocks a syscall used by flushing
  evidence: With `-0` present, even before any user command, the init batch's sentinel line ALSO has a leading `\x00`; init worked only because readuntil does substring match. The sandbox is not implicated — the `\x00` prefix is r2's intentional `-0` output protocol, not a sandbox side-effect.
  timestamp: 2026-05-21T (after r2 -h flag check)

- hypothesis: (C) proc.stdin.drain() race
  evidence: First-line of `?V` output arrived in <1ms — drain/wakeup is not the problem.
  timestamp: 2026-05-21T

## Evidence

- timestamp: 2026-05-21T initial-readthrough
  checked: mcp-gateway/src/mcp_gateway/sessions/r2.py:105-127 (exec_one) vs 235-245 (init batch).
  found: KEY DIFFERENCE — init batch uses readuntil(sentinel_bytes), exec_one uses readuntil(b"\n") line-by-line + equality.
  implication: A substring-vs-exact-match asymmetry could matter if r2 emits extra bytes adjacent to the sentinel.

- timestamp: 2026-05-21T repro-1 (with -q0, sandbox=True)
  checked: Direct Python repro spawned `r2 -2 -q0 ... /bin/ls` and ran exec_one for `?V`.
  found: Lines arrived instantly (0.000s each); content was b'\x00radare2 6.0.5 ...', b'birth: ...', b'options: ...', b'\x00MARE_SENTINEL_d42b463f7eb8e434\n'. exec_one timed out at 5.006s because sentinel_line == b'MARE_SENTINEL_...\n' but actual line == b'\x00MARE_SENTINEL_...\n'.
  implication: NULL BYTE prefix breaks the exact-match comparison. Root cause identified.

- timestamp: 2026-05-21T raw-r2-probe
  checked: `r2 -2 -q0 ... /bin/ls << EOF` heredoc piped to xxd.
  found: Output started with `00 00 53 45 4e 54 49 4e 45 4c 0a 00 72 61 64 61 ...` — `\x00\x00SENTINEL\n\x00rada...`. Confirms r2 emits `\x00` after init AND after every command.
  implication: This is the documented behavior of `-0`, not a bug in r2.

- timestamp: 2026-05-21T r2-flag-help
  checked: `r2 -h | grep -E "\-[02Q]"`.
  found: ` -0           print \x00 after init and every command`. `-q0` is `-q` (quiet) + `-0` (null-byte separator). Phase 8 D-02 docs mis-describe `-q0` as a combined "no rc / no init" flag — that's `-N`, not `-q0`.
  implication: The `-0` flag was almost certainly added by mistake (misreading of r2's compact flag syntax). The `?e <sentinel>` framing provides delimiting; `-0` is redundant.

- timestamp: 2026-05-21T repro-2 (with -q only, sandbox=True)
  checked: Direct Python repro spawned `r2 -2 -q ... /bin/ls`, same exec_one logic.
  found: init sentinel in 0.046s, exec_one for `?V` matched sentinel in 0.001s. ALL FOUR OUTPUT LINES ARE CLEAN (no `\x00` prefix): b'radare2 6.0.5 ...', b'birth: ...', b'options: ...', b'MARE_SENTINEL_...\n'.
  implication: Removing `-0` fixes the bug end-to-end with no other changes needed.

- timestamp: 2026-05-21T git-archaeology
  checked: `git log -S "-q0"` and original Phase 8 commit 8829c3b + 08-CONTEXT.md line 86-92.
  found: -q0 has been in the argv since the original Phase 8 commit; documented as "quiet mode, do not read ~/.radare2rc / project files; avoids leaking user state into a session. Equivalent to 'no init.'". This intent is achieved by `-q` alone — the `-0` is an unintended side-effect of misreading r2's flag syntax.
  implication: No prior phase relied on the `\x00` separator behavior; safe to remove `-0`.

## Resolution

root_cause: |
  The r2 argv `["r2", "-2", "-q0", ...]` was misparsed during Phase 8 D-02 as a
  single "quiet/no-init" flag. r2 actually treats `-q0` as TWO flags:
    -q   quiet mode (no prompt) and quit after -i
    -0   print \x00 after init and every command
  The `-0` causes r2 to prefix every command's output with a NUL byte, so the
  per-command sentinel line emitted by `?e <sentinel>\n` arrives on stdout as
  b"\x00<sentinel>\n" (with a leading \x00). R2Session.exec_one's loop reads
  line-by-line via `readuntil(b"\n")` and compares `line == (sentinel + "\n").encode()`
  exactly — the \x00 prefix breaks the equality, the loop never terminates, and
  asyncio.wait_for trips the 30s timeout. The init batch was unaffected because it
  uses `readuntil((sentinel + "\n").encode())` — a substring match that tolerates
  the \x00 prefix — so open_r2_session succeeded but the FIRST r2_cmd always timed
  out. The bug evaded the test suite because (a) all r2_sessions tool tests
  monkey-patch resolve_case_dir via `_case_dirs_mod` but tools/r2_sessions.py uses
  `from .case_dirs import resolve_case_dir` (re-bound at import, monkey-patch
  bypassed), so they ERROR out before reaching real r2, and (b) the one real-r2
  test (test_sandbox_active_when_open_r2) is marked @pytest.mark.slow and was not
  run as part of the default suite.
fix: |
  Single character change in mcp-gateway/src/mcp_gateway/sessions/r2.py: argv
  element "-q0" -> "-q". Removes the unintended NUL-byte separator; keeps the
  intended "quiet, no prompt" behavior. The explicit `?e <sentinel>` framing
  already delimits commands, so the `-0` separator was redundant from day one.
  Added regression coverage:
    - tests/test_r2_argv.py::test_argv_no_null_byte_separator_flag[True/False]
      (unit test asserting -0 and -q0 are not in argv; runs in 5ms, no r2 needed)
    - tests/test_r2_sandbox_integration.py::test_sandbox_active_when_open_r2
      already exercised this path but was @slow; with the fix in place, it now
      passes (previously timed out at 10s, asserting against not timed_out).
  Updated the in-source comment block above the argv to document the flag
  history and the rationale for dropping `-0`.
verification: |
  Pre-fix (baked container source with "-q0"):
    - test_sandbox_active_when_open_r2 FAILS with "r2 cmd timed out" at 10s.
    - test_argv_no_null_byte_separator_flag[True/False] FAILS (both args).
    - Direct Python repro (repro_r2_timeout.py) shows ?V output arriving in
      0.000s but with \x00 prefixes; sentinel never matches; times out at 5s.
  Post-fix (source patched to "-q"):
    - test_sandbox_active_when_open_r2 PASSES in 0.06s (exec_one("e cfg.sandbox")
      returns b"true\n" promptly).
    - test_argv_no_null_byte_separator_flag PASSES (both parametrizations).
    - test_r2_fix.py end-to-end (real r2 via the actual _open_r2 + exec_one code
      path): opens in 0.061s, ?V matches sentinel in 0.001s, ?e hello-world
      in 0.001s, e cfg.sandbox returns b"true\n" — security boundary still
      latched after the change.
    - Full test_r2_argv.py + test_r2_sandbox_integration.py (9 tests): all pass.
    - Broader sweep (excluding pre-existing unrelated failures in
      test_capa_integration.py path-prefix and test_skill_md_dual_mode.py YAML):
      625 passed, no regressions introduced by this fix.
  Toggle-test: reverting the fix in the baked install brings both the new
  regression tests AND the existing integration test back to failing, then
  re-applying the fix flips them all to passing. Tests are causally tied to
  the fix.
files_changed:
  - mcp-gateway/src/mcp_gateway/sessions/r2.py
  - mcp-gateway/tests/test_r2_argv.py
