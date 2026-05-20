---
phase: 11-dynamic-lab-mode-env-gated
reviewed: 2026-05-20T00:00:00Z
depth: standard
files_reviewed: 27
files_reviewed_list:
  - .gitignore
  - Dockerfile
  - README.md
  - compose.yaml
  - mcp-gateway/src/mcp_gateway/app.py
  - mcp-gateway/src/mcp_gateway/dynamic.py
  - mcp-gateway/src/mcp_gateway/jobs.py
  - mcp-gateway/src/mcp_gateway/sessions/__init__.py
  - mcp-gateway/src/mcp_gateway/sessions/_base.py
  - mcp-gateway/src/mcp_gateway/sessions/gdb.py
  - mcp-gateway/src/mcp_gateway/sessions/r2.py
  - mcp-gateway/src/mcp_gateway/tools/__init__.py
  - mcp-gateway/src/mcp_gateway/tools/dynamic.py
  - mcp-gateway/tests/conftest.py
  - mcp-gateway/tests/fixtures/build_fixtures.sh
  - mcp-gateway/tests/fixtures/dns_lookup.c
  - mcp-gateway/tests/fixtures/setsid_escape.c
  - mcp-gateway/tests/test_dynamic_gate.py
  - mcp-gateway/tests/test_dynamic_jobs.py
  - mcp-gateway/tests/test_dynamic_primitive.py
  - mcp-gateway/tests/test_dynamic_tools.py
  - mcp-gateway/tests/test_gdb_session.py
  - mcp-gateway/tests/test_run_docker_dynamic.py
  - mcp-gateway/tests/test_sessions_package.py
  - mcp-gateway/tests/test_tool_list.py
  - run_docker.sh
  - scripts/probe_dynamic_tools.sh
findings:
  critical: 0
  warning: 10
  info: 15
  total: 25
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-05-20T00:00:00Z
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

Phase 11 adds env-gated dynamic-analysis tools (strace, ltrace, qemu-user, gdb-MI3) to the MCP gateway. The architecture is well-engineered with strong defensive practices:

- **Defense-in-depth for argv:** strict regex allowlist + denylist for `extra_args`, plus per-call `unshare --net --ipc --uts --` wrap.
- **gdb MI allowlist + composite deny regex:** prefix-based allowlist (~50 prefixes) followed by a deny regex that scans for command-injection patterns at `;`/newline/whitespace boundaries.
- **Env-gate at registration:** `MCP_GATEWAY_DYNAMIC_TOOLS=1` gates BOTH the 3 `JobToolSpec` registrations (via primitive-layer import) and the 7 MCP tool wrappers. Default off; container shape unchanged when absent.
- **Capability probe at startup:** populates `dynamic.CAPABILITIES` once; tools consult the slot and return structured `{error, hint}` dicts when prerequisites are missing instead of attempting subprocess work.
- **Post-terminal reaper hook:** `JobToolSpec.post_terminal_hook` extension walks `/proc/<pid>/task/*/children` after killpg to catch `setsid` grandchildren.
- **Tests:** comprehensive; covers env-gate semantics, MI allowlist positive + 19-row deny matrix + composite separators, argv shape, capability probes that never raise, and slow integration tests gated by host tool presence.

No Critical issues were found. The Warnings below are correctness / API-contract / hardening issues worth addressing. Info items are smaller code-quality, doc-accuracy, and resilience notes.

## Warnings

### WR-01: `follow_fork_mode` parameter is accepted but never applied to gdb

**File:** `mcp-gateway/src/mcp_gateway/sessions/gdb.py:194-206, 281-291`
**Issue:** `_open_gdb` accepts a `follow_fork_mode` kwarg defaulting to `"parent"` and stores it on the resulting `GdbSession`. However, the lockdown init batch unconditionally writes `b"-gdb-set follow-fork-mode parent\n"` (`_LOCKDOWN_LINES`, line 202). A caller passing `follow_fork_mode="child"` (which `tools/dynamic.py:293` explicitly validates as allowed) gets a session whose stored `follow_fork_mode="child"` field disagrees with gdb's actual behavior (still follows parent). `open_gdb_session` returns the user-requested value in its response (line 350), masking the discrepancy.
**Fix:** Either reject `"child"` at the MCP boundary until proper support lands, or parameterize the lockdown batch:
```python
def build_lockdown_init_batch(sentinel: str, *, follow_fork_mode: str = "parent") -> bytes:
    if follow_fork_mode not in ("parent", "child"):
        raise ValueError(f"follow_fork_mode must be 'parent' or 'child', got {follow_fork_mode!r}")
    lines = (
        b"-gdb-set confirm off\n",
        ...,
        f"-gdb-set follow-fork-mode {follow_fork_mode}\n".encode("ascii"),
        ...,
    )
    return b"".join(lines) + build_sentinel_emit(sentinel)
```
Then thread the param through `_open_gdb` -> `build_lockdown_init_batch`.

### WR-02: `gdb_exec` references `timed_out` / `raw` outside the try-block that defines them

**File:** `mcp-gateway/src/mcp_gateway/tools/dynamic.py:393-432`
**Issue:** `raw, timed_out = await sess.exec_one(...)` (line 395) assigns inside a `try:` that wraps the `async with sess.lock`. If `sess.exec_one` raises, control jumps to `except Exception as e: return _err_internal(e)` (line 401), so today the unbound-name access at lines 410 / 432 / 467 cannot actually occur. But the structure is fragile: any future refactor that moves the early-return or adds a code path that falls through would expose latent `UnboundLocalError`. The same applies to `raw` referenced at lines 410, 444, 445, 452.
**Fix:** Add defensive defaults before the try block:
```python
raw: bytes = b""
timed_out: bool = False
try:
    async with sess.lock:
        raw, timed_out = await sess.exec_one(cmd, timeout=timeout_s)
        ...
except Exception as e:
    return _err_internal(e)
```

### WR-03: `_DANGEROUS_GDB_RE` `\s`-anchored keywords can false-positive inside `-data-evaluate-expression` strings

**File:** `mcp-gateway/src/mcp_gateway/sessions/gdb.py:116-134`
**Issue:** The deny regex is anchored on `(?:^|;|\n|\s)`. The `\s` anchor matches inside quoted strings passed to `-data-evaluate-expression`. A command like `-data-evaluate-expression "attach 1"` (a string literal that happens to contain the bytes `attach 1`) passes the allowlist (prefix matches `-data-evaluate-expression`), but the deny regex fires on the space-anchored `attach\s`. This rejects safe expressions that contain dangerous substrings. The trade-off (false-positive over false-negative) is defensible but should be explicit.
**Fix:** Tighten anchoring to `(?:^|;|\n)` for CLI-style keywords like `attach`, `python`, `pi`, `shell`, `source`, `!` that can only inject when they begin a fresh command. Keep `\s` for keywords that legitimately appear mid-line (e.g., `-gdb-set logging`). Add an explicit test asserting the chosen behavior on the false-positive class. Alternatively, document the current behavior and known false-positive class in the regex docstring.

### WR-04: `reap_followfork_strays` can mass-kill when `original_pgid == 0`

**File:** `mcp-gateway/src/mcp_gateway/dynamic.py:485-537`
**Issue:** The walker compares `cpgid != original_pgid` to decide which descendants to SIGKILL. If `original_pgid == 0` (degenerate case: `job.pgid` was set to 0, or `os.getpgid` returns 0 in a corner case), the condition matches for EVERY descendant whose pgid is non-zero — i.e., the entire descendant tree gets killed without filtering. `_reaper_hook` (line 547) checks `pgid is None` but not `pgid == 0`.
**Fix:** Add an early-return guard:
```python
def reap_followfork_strays(runner_pid: int, original_pgid: int) -> int:
    if original_pgid <= 0 or runner_pid <= 0:
        log.warning(
            "[dynamic] reap_followfork_strays: refusing degenerate (pid=%d pgid=%d)",
            runner_pid, original_pgid,
        )
        return 0
    ...
```

### WR-05: Race window in `gdb_exec` — lock released before `registry.close()` on timeout

**File:** `mcp-gateway/src/mcp_gateway/tools/dynamic.py:393-437`
**Issue:** After `sess.exec_one` returns `timed_out=True`, `sess.lock` has been released (line 400). Between lock release and `await registry.close(...)` at line 435, a concurrent caller (same bearer token, different MCP client) could acquire `sess.lock` and call `exec_one` on the now-wedged gdb process. The second call reads stale bytes or its own timeout. README:303 mentions sessions are shared across clients, but the specific post-timeout wedge window is a subtler issue.
**Fix:** Mark the session terminated under the lock before release, so concurrent gets fail fast:
```python
async with sess.lock:
    raw, timed_out = await sess.exec_one(cmd, timeout=timeout_s)
    if timed_out:
        sess.closed = True  # or sess.close_reason = "cmd_timeout"; flag visible via registry.get()
    ...
```
The subsequent `registry.close()` becomes the formal cleanup.

### WR-06: `validate_mi_command` allowlist does not require prefix terminator

**File:** `mcp-gateway/src/mcp_gateway/sessions/gdb.py:137-145`
**Issue:** `is_allowed_mi` uses `stripped.startswith(p)`. Today's MI command vocabulary is fixed, but a hypothetical future MI command like `-info-functions-and-attach` would be auto-allowlisted by the `-info-` prefix without any positive review. Defense-in-depth: require the matched prefix to end at a non-identifier boundary (space, EOS, or `-` for prefixes ending in `-`).
**Fix:**
```python
def is_allowed_mi(cmd: str) -> bool:
    stripped = cmd.lstrip()
    for p in _ALLOWED_MI_PREFIXES:
        if stripped == p:
            return True
        if stripped.startswith(p + " "):
            return True
        if p.endswith("-") and stripped.startswith(p):
            tail = stripped[len(p):]
            if tail and (tail[0].isalpha() or tail[0] in ("-", "_")):
                return True
    return False
```

### WR-07: `_probe_qemu` silently drops `PermissionError` without warning

**File:** `mcp-gateway/src/mcp_gateway/dynamic.py:349-383`
**Issue:** `_probe_qemu` catches `(OSError, PermissionError)` on `entry.read_text()` (line 361) and `iterdir()` (line 376) and silently `continue`/`pass`. The resulting `qemu_architectures` may be partial-due-to-permission-error vs partial-due-to-not-installed, with no signal to the operator. Compare with `probe_all()` which appends to `warnings` for ptrace_scope, binfmt, and unshare probes.
**Fix:** Thread a `warnings: list[str]` parameter through `_probe_qemu`, or change the return signature to include a probe-error indicator so the operator-visible startup log distinguishes "no arches installed" from "no arches discoverable".

### WR-08: `_dyn_tool_log_path` does not validate the `subdir` parameter

**File:** `mcp-gateway/src/mcp_gateway/dynamic.py:174-187`
**Issue:** The function validates `slug` against `_DYN_SLUG_RE` and `ext` requires a leading dot, but `subdir` is unvalidated. Today's callers pass hard-coded `"dynamic"` or `"qemu"`, so this is latent — but a future caller passing `subdir="../escape"` would produce a path outside `case_dir`, and `ensure_subdir(case_dir, subdir)` does not catch path-traversal (it uses `Path / subdir` which collapses `..` segments).
**Fix:** Either hard-code subdir to an enum (`Literal["dynamic", "qemu"]`) or validate against `_DYN_SLUG_RE`:
```python
_DYN_SUBDIRS: frozenset[str] = frozenset({"dynamic", "qemu"})
def _dyn_tool_log_path(case_dir, slug, ext, *, subdir):
    if subdir not in _DYN_SUBDIRS:
        raise ValueError(f"subdir must be one of {sorted(_DYN_SUBDIRS)}, got {subdir!r}")
    ...
```

### WR-09: `idalib-mcp` / `mcp-gateway` background processes untracked across entrypoint re-runs

**File:** `Dockerfile:306-318, 338-360` (entrypoint heredoc)
**Issue:** `nohup idalib-mcp ... &` and `nohup mcp-gateway ... &` background processes without writing a pidfile. The port-bound check (`echo > /dev/tcp/...`) handles port-reuse on entrypoint re-entry, but there's no orderly shutdown or stale-process reap. Not Phase 11-specific, but the new `MCP_GATEWAY_DYNAMIC_TOOLS` branch inherits this.
**Fix:** Write PIDs to `/tmp/idalib-mcp.pid` / `/tmp/mcp-gateway.pid` and reap on entrypoint re-entry, or document that `docker compose down && up` is the supported recovery path.

### WR-10: `BackgroundJobRegistry.__aexit__` snapshot can miss jobs inserted just before lock release

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:527-538`
**Issue:** `__aexit__` snapshots `_inflight` under `_lock`, exits the lock, then cancels via `asyncio.gather`. A racing `submit()` that completes its lock-protected insert (lines 575-576) between snapshot exit and drive-task gather is theoretically possible — though `submit()` is only invoked synchronously by tool handlers, and lifespan shutdown ordinarily means no new requests are being served. Defensive hardening only.
**Fix:** Set a `_shutting_down: bool` flag at `__aexit__` entry; `submit()` checks it and rejects with a structured error. Or loop the snapshot until empty.

## Info

### IN-01: Reserved-but-unused variable in `build_qemu_user_argv`

**File:** `mcp-gateway/src/mcp_gateway/dynamic.py:280-288`
**Issue:** `out_path = _dyn_tool_log_path(case_dir, "qemu_user", ".txt", subdir="qemu")` is computed, then `_ = out_path  # reserved` discards it. The function mints a path on every call that never gets written to. Comment explains intent, but the `qemu/` subdir stays empty in practice (qemu output goes to JOBS' `tool-logs/`).
**Fix:** Drop the mint (the `ensure_subdir(case_dir, "qemu")` call satisfies the dir-creation contract) or actually use the path.

### IN-02: `qemu_user` output location doesn't match docs

**File:** `mcp-gateway/src/mcp_gateway/dynamic.py:280-298`, `README.md:230-310` (Dynamic Mode section), `mcp-gateway/src/mcp_gateway/tools/dynamic.py:60`
**Issue:** The disclaimer says output is captured under `case_dir/{dynamic,qemu}/`. In practice qemu_user's stdout/stderr is captured by JOBS to `case_dir/tool-logs/<ts>-qemu_user-<rand4>.log` (jobs.py:560 + tool_log_path). `case_dir/qemu/` is created but never written to. Users writing automation against the documented `qemu/` path will not find their output.
**Fix:** Either (a) update disclaimer + README to clarify qemu output goes to `tool-logs/`, or (b) route qemu output to `qemu/` via shell redirection (but that requires re-introducing a shell wrapper, which fights the argv-only invariant).

### IN-03: `validate_mi_command` raises `ValueError` for type errors instead of `TypeError`

**File:** `mcp-gateway/src/mcp_gateway/sessions/gdb.py:156-157`
**Issue:** `if not isinstance(cmd, str): raise ValueError(...)` — Python convention is `TypeError` for type mismatches. The contract is locked by `test_validate_mi_command_rejects_non_string` which asserts `ValueError`, so changing this is a breaking change.
**Fix:** Document the deliberate choice in the docstring, or update test + function to use `TypeError`.

### IN-04: `_open_gdb` does not re-confine `sample_path`

**File:** `mcp-gateway/src/mcp_gateway/sessions/gdb.py:281-320`
**Issue:** `sample_path` is caller-supplied (resolved via `samples.resolve_sample` upstream in `tools/dynamic.py`). The transcript path uses `confine_to(case_dir, ...)` correctly (line 308), but `sample_path` itself is trusted at this layer. A short comment documenting the trust boundary ("sample_path is pre-validated by tools.samples.resolve_sample") would aid future maintainers.

### IN-05: Test fixtures use invalid profile names that exercise mock paths only

**File:** `mcp-gateway/tests/test_dynamic_tools.py:216, 233, 281`
**Issue:** `run_ltrace(..., profile="default")` and `run_qemu_user(..., profile="default")` use the literal `"default"`, which is NOT a key in `LTRACE_PROFILES` or `QEMU_USER_PROFILES`. The tests pass because `start_tool_job` is mocked, so `build_argv` (which would raise) never runs. Readers may infer `"default"` is a real profile.
**Fix:** Use real profile names: `"library_calls"` for ltrace, `"simple"` for qemu_user.

### IN-06: Hash space in `_dyn_tool_log_path` (`secrets.token_hex(2)`) is small

**File:** `mcp-gateway/src/mcp_gateway/dynamic.py:185-187`
**Issue:** 16-bit randomness gives a 1/65536 collision chance per same-second invocation. Job submission is serialized, so practical collisions are vanishingly rare, but `secrets.token_hex(4)` (32-bit) is a free upgrade matching the Phase 9 / Phase 10 pattern (jobs.py uses `secrets.token_hex(8)` for job IDs).
**Fix:** `rand4 = secrets.token_hex(4)` and rename to `rand8`. Minor naming change; same disk-name length.

### IN-07: `tools/__init__.py` reads env at registration; `dynamic.py` reads same env at import

**File:** `mcp-gateway/src/mcp_gateway/tools/__init__.py:71-74`, `mcp-gateway/src/mcp_gateway/dynamic.py:70`
**Issue:** Two reads of `MCP_GATEWAY_DYNAMIC_TOOLS` at different times — module-import vs `register_all_tools()`. Tests intentionally manipulate the env between these via `_full_reset_modules` + monkeypatch. The double read is deliberate for test ergonomics. A one-line comment in `tools/__init__.py` confirming "yes, re-read here so monkeypatch-after-import works" would aid maintainability.

### IN-08: README "Limitations (v1.1)" — minor wording

**File:** `README.md:301-310`
**Issue:** "(per-`Mcp-Session-Id` keying is v1.2 territory)" — informal phrasing. Per user's commit-message convention (Sentence-cased imperative verbs), this is a doc nit only.

### IN-09: `Dockerfile` does not annotate Phase 11 dynamic-mode prerequisites

**File:** `Dockerfile:43-57`
**Issue:** All Phase 11 prerequisites (`strace`, `ltrace`, `gdb`, `gdb-multiarch`, `qemu-user`, `qemu-user-static`) are already in the apt-install list from earlier phases. No new packages needed — good. A `# Phase 11 dynamic-mode also needs: gdb, strace, ltrace, qemu-user-static (already above)` comment would help future maintainers understand what NOT to remove.

### IN-10: `compose.yaml` env passthrough relies on host shell env

**File:** `compose.yaml:25-35`
**Issue:** Bare env var names (`MCP_GATEWAY_TOKEN`, etc.) inherit the host shell. When operators run `docker compose up` directly (bypassing `run_docker.sh`), vars stay unset and defaults apply. Behavior is intended; no fix needed. Flagged for awareness.

### IN-11: `run_docker.sh --print-config` shows dynamic-mode status from host shell, not container state

**File:** `run_docker.sh:117-129, 96-110`
**Issue:** `print_ready_block` checks `${MCP_GATEWAY_DYNAMIC_TOOLS:-0}` from the operator's CURRENT shell env. After running `./run_docker.sh --remote --dynamic` in one terminal, then `./run_docker.sh --print-config` in another (without exporting the env), the second invocation shows "Dynamic mode: disabled" even though the container has it on.
**Fix:** Either persist a `.mcp-gateway-dynamic-mode` marker file alongside `.mcp-gateway-token`, or have `--print-config` query the running container's env (`docker compose exec kali env | grep MCP_GATEWAY_DYNAMIC_TOOLS`).

### IN-12: `_open_gdb` failure path does not include partial init buffer in error message

**File:** `mcp-gateway/src/mcp_gateway/sessions/gdb.py:354-363`
**Issue:** On init failure (timeout / readuntil exception), the `RuntimeError("gdb init failed: ...")` does not include `init_buf` contents. Operators debugging stuck initialization see the exception type but not what gdb actually emitted before wedging.
**Fix:** Capture first ~512 bytes of `init_buf` into the error message:
```python
preview = bytes(init_buf[:512]).decode("utf-8", errors="replace")
raise RuntimeError(f"gdb init failed: {type(e).__name__}: {e}; init preview: {preview!r}") from e
```

### IN-13: `sessions/__init__.py` force-reloads submodules on package reload

**File:** `mcp-gateway/src/mcp_gateway/sessions/__init__.py:21-28`
**Issue:** The reload loop is justified in the docstring (D-14 env-var re-validation), but it's unusual enough that a future reader will be confused. The intent is well-documented; flagged for awareness. No fix needed.

### IN-14: `gdb_exec` truncate_for_response import is per-call, swallows ImportError

**File:** `mcp-gateway/src/mcp_gateway/tools/dynamic.py:453-457`
**Issue:** `from mcp_gateway.sessions import truncate_for_response` is imported inside the function with broad `except Exception: stdout_head = stdout_text[: 32 * 1024]`. The fallback (`text[:N]` where N is character count, not bytes) is not UTF-8-safe. Probability of the import failing in a deployed container is near-zero (the module is in the same package), so this is defensive over-engineering, but the fallback semantics differ from the success path.
**Fix:** Move the import to the module top (avoid per-call import cost), and let any ImportError propagate naturally (it would indicate a broken install).

### IN-15: `app.py::log_dynamic_probe_result` repeats capability checks already in `dynamic.probe_all`

**File:** `mcp-gateway/src/mcp_gateway/app.py:68-123`
**Issue:** `log_dynamic_probe_result` re-checks each capability and emits its own WARN messages, in parallel with the `warnings` list already populated by `probe_all`. The startup output thus contains both the "OK: netns_feasible" log AND any `caps.warnings` strings emitted at line 122-123. This is intentional (operator sees structured per-capability status + raw warning text), but the duplication risks confusion when warning text disagrees with the explicit per-capability lines.
**Fix:** Either reduce `log_dynamic_probe_result` to only emit the per-capability OK/WARN lines (drop the `for w in caps.warnings` loop), or vice versa. Pick one source of truth.

---

_Reviewed: 2026-05-20T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
