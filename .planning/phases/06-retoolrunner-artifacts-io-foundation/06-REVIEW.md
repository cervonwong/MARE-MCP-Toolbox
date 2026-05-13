---
phase: 06-retoolrunner-artifacts-io-foundation
reviewed: 2026-05-13T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - mcp-gateway/src/mcp_gateway/artifacts_io.py
  - mcp-gateway/src/mcp_gateway/runner.py
  - mcp-gateway/tests/test_runner.py
  - mcp-gateway/tests/test_artifacts_io.py
  - mcp-gateway/pyproject.toml
findings:
  critical: 0
  warning: 3
  info: 6
  total: 9
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-05-13
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Phase 6 lands the chokepoint subprocess primitive (`ReToolRunner`) and the
leaf path helpers (`confine_to`, `ensure_subdir`, `tool_log_path`) on the
contract specified in CONTEXT.md D-01..D-21. Implementation is faithful to
the design: argv-only spawn, `start_new_session=True`, concurrent
stdout/stderr drains with head buffers + raw file sink, ANSI strip + UTF-8
boundary truncation on head only, `os.killpg(getpgid(...), SIGKILL)` +
`asyncio.shield(proc.wait())` on both `TimeoutError` and `CancelledError`,
import-time env-var validation, and the locked 12-key D-03 return shape.

The code is generally tight and well-commented. No Critical defects were
found: shell-injection is structurally prevented (no `shell=True`,
argv-only spawn), path-traversal in `confine_to` is correctly enforced via
`Path.resolve()` + `is_relative_to`, head buffers + log caps bound memory
growth, and cleanup paths handle the documented termination contracts.

Warnings center on three real defense-in-depth gaps:
1. `ensure_subdir` does not perform a containment check on its mkdir
   target — a pre-planted symlink at `case_dir/<name>` pointing outside
   `case_dir` would silently redirect writes (and `runner.run` always
   calls `ensure_subdir(case_dir, "tool-logs")` then opens the log file
   via the resolved symlink).
2. There is a small but real window between `await
   asyncio.create_subprocess_exec(...)` returning and entering the `try`
   block where the synchronous `open(log_abs, "ab", buffering=0)` happens
   without subprocess cleanup protection — if `open()` raises
   (`PermissionError`, `OSError`, disk full), the freshly-spawned child
   is leaked. This is also true on cancellation if the cancel is delayed
   into the open call's underlying syscalls, though Python `open()` is
   not an asyncio cancellation point.
3. The `_truncate_to_utf8_boundary` fallback returns `buf[:cut]` after 4
   walk-back iterations regardless of whether `buf[cut]` is still a
   continuation byte. Valid UTF-8 cannot trigger this (max 3
   continuation bytes follow a leader), but invalid UTF-8 input can
   leave the prefix ending mid-codepoint. The downstream
   `decode(errors="replace")` masks the artifact, so the impact is
   cosmetic — flagging as Warning because the docstring promises the
   prefix "end[s] on a UTF-8 codepoint boundary".

Info items cover minor code-quality and test-strength observations.

## Warnings

### WR-01: `ensure_subdir` silently follows symlink to outside case_dir

**File:** `mcp-gateway/src/mcp_gateway/artifacts_io.py:100-115`
**Issue:** `ensure_subdir` calls `target.mkdir(parents=False,
exist_ok=True)` and then returns `target.resolve(strict=True)`. If a
symlink already exists at `case_dir/<name>` pointing to e.g. `/etc`,
`mkdir(exist_ok=True)` raises `FileExistsError` because the path exists
(but is not a directory) — actually `exist_ok=True` only suppresses
`FileExistsError` when the existing entry IS a directory. So if the
symlink target is an existing directory (e.g. `/etc`), `mkdir` swallows
the error, and `target.resolve(strict=True)` returns the symlink
realpath outside `case_dir`. `ReToolRunner.run` immediately calls
`ensure_subdir(self._case_dir, "tool-logs")` (runner.py:210), then opens
`tool_log_path(...)` for append. The append happens under the resolved
realpath — outside the case dir.

This is the same symlink-escape vector that `confine_to` defends against
for arbitrary paths; `ensure_subdir` should compose with `confine_to` or
perform an explicit containment check before returning. The Phase 6
threat model claims T-6-03 (symlink escape) is mitigated, but only for
`confine_to` — `ensure_subdir` is not covered.

Attacker model context: case_dirs are created by the gateway under
STATUS_ROOT, so a pre-planted symlink requires either an earlier
filesystem-write vulnerability or operator misconfiguration. Risk is
defense-in-depth, not exploit-imminent. Flagging as Warning rather than
Critical because the gateway controls the case_dir filesystem layout.

**Fix:**
```python
def ensure_subdir(case_dir: str | Path, name: str) -> Path:
    lowered = _validate_slug(name)
    case_path = Path(case_dir).resolve(strict=True)
    target = case_path / lowered
    target.mkdir(parents=False, exist_ok=True)
    resolved = target.resolve(strict=True)
    # Defense-in-depth: refuse if the resolved target escapes case_dir
    # via a pre-planted symlink.
    if not (resolved == case_path or resolved.is_relative_to(case_path)):
        raise ValueError(
            f"ensure_subdir target escapes case_dir: "
            f"{lowered!r} resolves to {resolved}"
        )
    return resolved
```
No new test required — `test_confine_to_rejects_escaping_symlink` documents
the pattern; an analogous `test_ensure_subdir_rejects_escaping_symlink`
would be welcome but is not blocking.

### WR-02: Open-file leak window between spawn and try-block

**File:** `mcp-gateway/src/mcp_gateway/runner.py:216-229`
**Issue:** The current flow is:

```python
proc = await asyncio.create_subprocess_exec(...)   # line 217
timed_out = False
with open(log_abs, "ab", buffering=0) as sink:     # line 229
    try:
        ...
```

If `open(log_abs, "ab", buffering=0)` raises (e.g. `PermissionError`,
`OSError("No space left on device")`, `IsADirectoryError` if a directory
got planted at the log path), the exception propagates out of `run()`
WITHOUT executing the cleanup path. The freshly spawned child process
continues running, orphaned. The runner contract (D-04) says
`PermissionError` is a legitimate pre-spawn programmer-error raise — but
the `open` here is post-spawn.

Concretely: this leaks a child process and (worse) a child whose stdout
and stderr PIPEs are now unowned by any drain, so they fill the kernel
pipe buffer and the child will eventually block on write. The runner
"forgets" the child.

Phase 6's required tests do not exercise this path (no test forces
`open()` to fail post-spawn), so the defect is latent.

**Fix:** Wrap the spawn + log-open in a single try/finally so the
subprocess gets cleaned up on any post-spawn failure:

```python
proc = await asyncio.create_subprocess_exec(...)
sink = None
try:
    sink = open(log_abs, "ab", buffering=0)
    try:
        ...  # existing drain/timeout/cancel logic
    finally:
        sink.close()
except BaseException:
    # If we spawned but failed to set up the drain pipeline,
    # kill the orphan and reap it before re-raising.
    if proc.returncode is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        await asyncio.shield(proc.wait())
    raise
```
Alternatively (cleaner): open the log file BEFORE the spawn — the file
path is already known, opening it can't fail because of subprocess
state, and a failed open then never starts a child.

### WR-03: `_truncate_to_utf8_boundary` can return a non-boundary prefix on invalid UTF-8

**File:** `mcp-gateway/src/mcp_gateway/runner.py:82-98`
**Issue:** The walk-back loop runs up to 4 times. After the loop, the
function unconditionally returns `buf[:cut]` even though `cut` may still
point at a continuation byte. The docstring states the function returns
"the largest prefix of buf with length <= n ending on a UTF-8 codepoint
boundary" — this is false for inputs containing 5+ consecutive
continuation bytes (impossible in valid UTF-8 but possible from
garbage/binary output).

For valid UTF-8 input, the loop always exits via the `return buf[:cut]`
branch inside the loop (because a leader byte appears within 3 backsteps),
so the bug is unreachable for legitimate text. For binary or malformed
input, the resulting prefix may end mid-pseudo-codepoint; the subsequent
`decode("utf-8", errors="replace")` substitutes U+FFFD, so users see
garbage replacement chars rather than truncated text. Functionally
benign; documentation/contract violation.

**Fix:** Either tighten the docstring ("...assuming valid UTF-8 input;
invalid input may be truncated mid-byte and rendered with U+FFFD on
decode"), or make the fallback safer by searching backward until a
leader byte or position 0 is reached:

```python
def _truncate_to_utf8_boundary(buf: bytes, n: int) -> bytes:
    if n >= len(buf):
        return buf
    cut = n
    # UTF-8 codepoints are at most 4 bytes; walk back at most 4 steps
    # to find a leader. If we don't find one within 4 steps, the input
    # is not valid UTF-8 at this offset — fall back to the conservative
    # cut at n - 4 (errors="replace" handles the rest at decode).
    for _ in range(4):
        if cut == 0 or (buf[cut] & 0xC0) != 0x80:
            return buf[:cut]
        cut -= 1
    return buf[:cut]  # documented: may end mid-codepoint on invalid UTF-8
```
The first conditional inside the loop now also handles `cut == 0`
uniformly. Behavior change is minimal; risk is low.

## Info

### IN-01: `ReToolRunner.__init__` validates slug via side-effectful `tool_log_path` call

**File:** `mcp-gateway/src/mcp_gateway/runner.py:192`
**Issue:** Eager slug validation is implemented as `_ =
artifacts_io.tool_log_path(self._case_dir, slug)`. This calls
`secrets.token_hex(2)` and `datetime.now()` purely to trigger the slug
regex. Wasteful (negligible cost) and obfuscates intent.
**Fix:** Expose `_validate_slug` from `artifacts_io` (rename to
`validate_slug` without the leading underscore, or add a thin public
wrapper) and call it directly:
```python
from mcp_gateway.artifacts_io import validate_slug
self._slug = validate_slug(slug)  # raises ValueError on bad input
```

### IN-02: Untyped `case_dir` parameter in `ReToolRunner.__init__` and `run_tool`

**File:** `mcp-gateway/src/mcp_gateway/runner.py:171, 291`
**Issue:** Both `case_dir` parameters lack type annotations; the plan
(`06-03-PLAN.md`) specifies `str | Path`. `confine_to` and other
neighbors annotate consistently as `str | os.PathLike`.
**Fix:** Add `case_dir: str | os.PathLike` (and `import os` is already
present) for consistency and IDE/typecheck signal.

### IN-03: No upper-bound validation on `stdout_head_kb` / `stderr_head_kb` kwargs

**File:** `mcp-gateway/src/mcp_gateway/runner.py:197-202`
**Issue:** `stdout_head_kb` and `stderr_head_kb` constructor kwargs are
accepted as `Optional[int]` with no range check. Negative values produce
a degenerate (empty + truncated) head buffer; pathologically large
values would multiply by 1024 into a large `bytearray` allocation cap.
Module-level constants are validated by `_env_int` (non-negative); the
kwarg overrides escape that check.
**Fix:** Add a tiny validator at the top of `__init__`:
```python
def _check_head_kb(name: str, v: Optional[int]) -> None:
    if v is not None and (v < 0 or v > 64 * 1024):  # 64 MB hard cap
        raise ValueError(f"{name}={v}; must be 0..65536")
_check_head_kb("stdout_head_kb", stdout_head_kb)
_check_head_kb("stderr_head_kb", stderr_head_kb)
```

### IN-04: `test_log_capture_and_head_alignment` does not assert byte counts or truncation flag

**File:** `mcp-gateway/tests/test_runner.py:105-117`
**Issue:** The capture test verifies log file contents and stdout_head
prefix but does not assert `result["stdout_bytes_total"] == 12` or
`result["stdout_truncated"] is False`. Weakens the SC-3 coverage —
regressions to the byte counter or truncation flag would not be caught
here.
**Fix:** Add the missing asserts:
```python
assert result["stdout_bytes_total"] == 12  # len("line1\nline2\n")
assert result["stdout_truncated"] is False
assert result["stderr_bytes_total"] == 0
```

### IN-05: `test_cancel_propagates_to_killpg` 200 ms budget may flake on loaded CI

**File:** `mcp-gateway/tests/test_runner.py:65-78`
**Issue:** `elapsed < 0.2` is a tight bound that includes Python
interpreter overhead, asyncio scheduling, SIGKILL delivery, kernel reap,
and `proc.wait()` return. On a heavily loaded CI runner, this can flake.
The D-20 contract is genuinely "<200 ms," but tests typically pad such
budgets.
**Fix:** Either keep the assertion and accept occasional flake retries,
or relax to `< 0.5` with a comment that the D-20 contract is 200 ms but
the test allows a 2.5x CI-noise margin. The 100 ms `await asyncio.sleep`
before cancel also assumes the subprocess started — on very slow
systems, `sleep 60` may not even be a running PID yet. Could add a
brief polling loop to confirm `proc.pid` is alive before cancelling.

### IN-06: Unused `time` import in `tests/test_artifacts_io.py`

**File:** `mcp-gateway/tests/test_artifacts_io.py:9`
**Issue:** `import time` is present but `time` is never referenced. Dead
import.
**Fix:** Remove the line.

---

_Reviewed: 2026-05-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
