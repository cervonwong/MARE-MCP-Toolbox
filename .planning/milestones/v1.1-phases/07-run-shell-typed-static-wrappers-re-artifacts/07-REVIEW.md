---
phase: 07-run-shell-typed-static-wrappers-re-artifacts
reviewed: 2026-05-13T04:58:48Z
depth: standard
files_reviewed: 19
files_reviewed_list:
  - Dockerfile
  - mcp-gateway/pyproject.toml
  - mcp-gateway/src/mcp_gateway/app.py
  - mcp-gateway/src/mcp_gateway/artifacts_io.py
  - mcp-gateway/src/mcp_gateway/tools/__init__.py
  - mcp-gateway/src/mcp_gateway/tools/backend_passthrough.py
  - mcp-gateway/src/mcp_gateway/tools/collision_check.py
  - mcp-gateway/src/mcp_gateway/tools/re_artifacts.py
  - mcp-gateway/src/mcp_gateway/tools/re_static.py
  - mcp-gateway/src/mcp_gateway/tools/resources.py
  - mcp-gateway/src/mcp_gateway/tools/shell.py
  - mcp-gateway/tests/test_acl_available.py
  - mcp-gateway/tests/test_artifacts_io.py
  - mcp-gateway/tests/test_collision_check.py
  - mcp-gateway/tests/test_re_artifacts.py
  - mcp-gateway/tests/test_re_static.py
  - mcp-gateway/tests/test_resources_phase7.py
  - mcp-gateway/tests/test_run_shell.py
  - mcp-gateway/tests/test_tool_list.py
findings:
  critical: 0
  warning: 6
  info: 7
  total: 13
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-05-13T04:58:48Z
**Depth:** standard
**Files Reviewed:** 19
**Status:** issues_found

## Summary

Phase 7 introduces 17 new MCP tools: `run_shell` (constrained subprocess shell), 11 typed static-RE wrappers, and 5 artifact-control helpers, plus a startup collision check between gateway-native tools and the active disassembler backend. The implementation is generally well-structured and security-conscious: the `run_shell` design layers UID drop (UID 700 mare-shell), `setpriv --no-new-privs --clear-groups --inh-caps=-all`, a built-from-scratch env whitelist, NUL/size validation, cwd pinning, and ACL-based case-dir access; `confine_to()` uniformly rejects path-traversal across writers and readers; the collision check fails loud with `EX_CONFIG` (78) before serving begins. Tests track the design closely with skip-on-host-missing-deps fallbacks.

Six warnings concern real correctness gaps — primarily mismatched intent in `run_xxd` ("full slice" but only head-truncated content is written), reliance on the head-truncated stdout for JSON parse in `run_die`/`run_rabin2`, missing ACL inheritance when `write_artifact` creates intermediate subdirectories before the ACL grant, and a swallowed exception during `RopperService.applyFilter`. Seven info items cover magic numbers, dead-write branches, performance papercuts, and a one-line `mkdir` ordering concern.

No critical (security/data-loss/auth-bypass) issues were found.

## Warnings

### WR-01: `run_xxd` writes truncated head — not "full slice" — to `hex/`

**File:** `mcp-gateway/src/mcp_gateway/tools/re_static.py:178-180`
**Issue:** Comment + module-level rationale states "Write full slice to hex/xxd-<ts>-<rand4>.txt for client retrieval" (re_static.py:177). The actual write uses `result["stdout_head"]`, which the Phase 6 runner has already truncated to `MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB * 1024` (default 256 KB) — the same bytes already in memory. For any xxd run that exceeds the head cap, the persisted artifact silently drops bytes. The runner's separate tool-log already contains the full raw stream; if the goal is "full slice", that file should be referenced (e.g., via `result["log_path"]`) or the xxd output should be re-read from the runner's log.
**Fix:**
```python
# Option A — point clients at the runner's full log:
result["hex_path"] = result["log_path"]

# Option B — if a dedicated hex/ copy is required, copy from the full log:
import shutil
runner_log = Path(resolved_case) / result["log_path"]
hex_file = hex_dir / f"xxd-{_utc_ts()}-{_rand4()}.txt"
shutil.copyfile(runner_log, hex_file)
result["hex_path"] = str(hex_file.relative_to(Path(resolved_case)))
```

### WR-02: `run_die` JSON parse silently truncated when stdout > 256 KB

**File:** `mcp-gateway/src/mcp_gateway/tools/re_static.py:144-154`
**Issue:** `json.loads(result["stdout_head"])` parses the head-capped (default 256 KB) preview, not the full output captured in the runner's `log_path`. DIE JSON output on large/complex binaries can exceed this cap; truncation midway yields `json.JSONDecodeError`, the `detections` list silently degrades to `[]`, and only a free-form `json_parse_error` string surfaces. Callers comparing `detections == []` will treat truncation as "no packer detected" — a meaningful false negative.
**Fix:**
```python
# Read from the full log when the head was truncated:
if result.get("stdout_truncated"):
    full_log = Path(resolve_case_dir(case_dir)) / result["log_path"]
    raw = full_log.read_text(encoding="utf-8", errors="replace")
else:
    raw = result["stdout_head"] or ""
try:
    parsed = json.loads(raw)
    ...
```
Same pattern applies to `run_rabin2` at re_static.py:277-285.

### WR-03: `run_rabin2` JSON parse silently truncated when stdout > 256 KB

**File:** `mcp-gateway/src/mcp_gateway/tools/re_static.py:277-285`
**Issue:** Same root cause as WR-02. `rabin2 -j zz` (string dump) on large samples readily exceeds 256 KB, producing a partial JSON document, a parse error, and `json_output = None`. Clients expecting structured output get nothing while the truncation is hidden behind the runner's `stdout_truncated=True` flag elsewhere in the result.
**Fix:** Same fix as WR-02. Read from `result["log_path"]` when `result["stdout_truncated"]` is True.

### WR-04: `write_artifact` intermediate subdirs created before ACL grant

**File:** `mcp-gateway/src/mcp_gateway/tools/re_artifacts.py:108-110` (and `:145-146` in `append_artifact`)
**Issue:** `target.parent.mkdir(parents=True, exist_ok=True)` runs before `ensure_mare_shell_access(resolved_case)`. The default ACL on `case_dir` is only present after the first `ensure_mare_shell_access` call. On the very first call against a fresh case_dir, if `relpath` introduces a new intermediate directory (e.g., `relpath="subdir1/subdir2/x.txt"`), the freshly-created intermediates do NOT inherit the default ACL — there isn't one yet on case_dir. Subsequent re-runs of `ensure_mare_shell_access` apply the default ACL to `case_dir`, but POSIX ACL inheritance does not retroactively walk pre-existing children, so `subdir1/` and `subdir2/` keep their bare mode-bit ACL only. `mare-shell` cannot then traverse into them via `run_shell`.
**Fix:** Apply ACLs BEFORE the mkdir so newly-created subdirs inherit:
```python
ensure_mare_shell_access(resolved_case)  # moved up
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(data)
```
Or recursively re-apply the ACL to children after the mkdir (more expensive but covers retroactive fixes). The same swap applies to `append_artifact`.

### WR-05: `RopperService.applyFilter` exception swallowed bare

**File:** `mcp-gateway/src/mcp_gateway/tools/re_static.py:395-399`
**Issue:** `except Exception: pass` discards the original exception class, message, and traceback. The comment narrates "ropper filter compile errors are AttributeError/ValueError" — these should be caught explicitly so unrelated failures (memory error, deeper ropper bug, KeyboardInterrupt subclass on some pythons) are not silently absorbed. As written, an agent supplying a malformed filter has no signal that the filter was ignored; the result still contains all gadgets unfiltered.
**Fix:**
```python
if filter:
    try:
        svc.applyFilter(name=resolved_sample, filter=filter)
    except (AttributeError, ValueError, TypeError) as exc:
        # Surface to the agent rather than silently dropping the filter.
        result_filter_error = f"applyFilter failed: {exc}"
    else:
        result_filter_error = None
# attach result_filter_error to the returned dict
```

### WR-06: `confine_to` raises `ValueError` for `case_dir` not existing — but callers (re_artifacts writers) sometimes want to create it

**File:** `mcp-gateway/src/mcp_gateway/tools/re_artifacts.py:91-92,134-135` interacting with `mcp-gateway/src/mcp_gateway/artifacts_io.py:82-86`
**Issue:** `write_artifact`/`append_artifact` call `resolve_case_dir(case_dir)` first (which presumably resolves an existing case under STATUS_ROOT) then `confine_to(resolved_case, relpath)`. `confine_to` calls `.resolve(strict=True)` on the case_dir at artifacts_io.py:82 — so if `resolve_case_dir` ever returns a path that does not yet exist on disk, `confine_to` raises `ValueError("case_dir does not exist")` rather than letting the writer create parent dirs. This is fine today (case_dirs.resolve_case_dir requires the case to exist), but the helper's docstring at re_artifacts.py:88 ("Lazy-create any missing parent directories") suggests an expectation of lazy creation that doesn't extend to the case_dir itself. Confirm this is intentional and document; otherwise an inconsistent failure mode (works once case exists, fails before that) can confuse callers.
**Fix:** Either document at the top of `write_artifact`/`append_artifact` that "case_dir must already exist under STATUS_ROOT — use `init_case` first" or relax `confine_to` for the writers' case_dir specifically. The current design is defensible; the warning is for explicit documentation of the precondition.

## Info

### IN-01: `run_xxd` writes empty file when subprocess failed

**File:** `mcp-gateway/src/mcp_gateway/tools/re_static.py:179-180`
**Issue:** If `xxd` exits non-zero (bad offset / unreadable sample), `result["stdout_head"]` may be empty or contain only stderr-style messages from the shell wrapper. The code unconditionally writes the file to `hex/xxd-<ts>-<rand4>.txt`. Empty/garbage files accumulate in `hex/` across failed calls.
**Fix:** Guard with `if result["exit_code"] == 0 and result["stdout_head"]:` before writing the hex artifact, or include the failure detail in the file body.

### IN-02: `_inproc_result` reports `duration_s` but no `started_at`

**File:** `mcp-gateway/src/mcp_gateway/tools/re_static.py:68-89`
**Issue:** Minor — the function does not record the wall-clock start. For `run_capstone_disasm` / `run_ropper` this is intentional (monotonic clock is fine), but the 12-key shape elsewhere (Phase 6 runner) sets the same `duration_s` from monotonic too, so this is consistent. Worth noting in a follow-up: if any consumer expects ISO timestamps (e.g., for case timelines), neither path provides them.

### IN-03: `_env_int` duplicated across three modules with slightly different semantics

**File:** `mcp-gateway/src/mcp_gateway/tools/re_artifacts.py:46-56`, `mcp-gateway/src/mcp_gateway/tools/resources.py:52-63`, `mcp-gateway/src/mcp_gateway/tools/shell.py:39-47`
**Issue:** Three near-identical `_env_int` helpers, each with a subtly different bound:
- `re_artifacts._env_int`: rejects `< 0`
- `resources._env_int`: rejects `< 0`
- `shell._env_int`: rejects `<= 0`

A future refactor consolidating these should preserve the strict-positive variant for `MAX_CMD_BYTES` (zero would refuse all commands). Until then, the divergence is silent.
**Fix:** Extract a `mcp_gateway._env.read_int(name, default, *, min_value=0)` helper.

### IN-04: `_file_sha256` runs on every paginated call to `get_tool_log`

**File:** `mcp-gateway/src/mcp_gateway/tools/re_artifacts.py:64-70` invoked at `:298,319`
**Issue:** For each paginated read of a large log, the full file is re-streamed through SHA-256 — that's potentially `total_size` bytes hashed per call. Logs up to `MAX_LOG_MB=256MB` mean ~1s of CPU per call on commodity hardware. While the docstring "helps clients verify chunked-read reassembly" justifies including the digest once, computing it every page is wasteful. Performance is out of v1 scope per review policy, but worth recording.
**Fix:** Cache per `(path, st_mtime_ns, st_size)` via `functools.lru_cache`, or include the digest only on the final page (`eof=True`).

### IN-05: `MAX_CMD_BYTES` frozen at import time

**File:** `mcp-gateway/src/mcp_gateway/tools/shell.py:50`
**Issue:** `MAX_CMD_BYTES` is computed once at module import from the env. Tests that change `MCP_GATEWAY_RUN_SHELL_MAX_CMD_BYTES` via `monkeypatch.setenv` mid-suite see no effect; the value sticks at whatever the env was at first import. The module-level comment acknowledges this ("Module-level constant read once at import (Phase 6 pattern)"). Consistent with Phase 6, so not a bug, but a tester writing "make cmd cap 100 and see X fail" will be silently surprised.
**Fix:** Read per-call: `def _max_cmd_bytes() -> int: return _env_int("MCP_GATEWAY_RUN_SHELL_MAX_CMD_BYTES", 32_768)` — costs nanoseconds.

### IN-06: `backend_passthrough.refresh_backend_tools()` called on every cache miss

**File:** `mcp-gateway/src/mcp_gateway/tools/backend_passthrough.py:62-66`
**Issue:** If an agent calls a tool name that's neither gateway-native nor in the cached backend tools (e.g., a typo or a tool the backend dropped), the dispatcher does an extra round-trip to refresh the backend's tool list. A pathological client spraying invalid names exerts amplified network load on the upstream backend. Low risk because the collision check guarantees gateway names are not in the cache, but worth noting.
**Fix:** Throttle the refresh (e.g., min 1s between refreshes), or fall back to `mcp.call_tool` directly which will surface the unknown-tool error.

### IN-07: `get_artifact_tree` exposes case_dir as `name`

**File:** `mcp-gateway/src/mcp_gateway/tools/re_artifacts.py:215`
**Issue:** Root node sets `name = path.name`, which is the case-dir's basename (e.g., `200-write-text`). That's informative but could confuse a client that builds breadcrumbs from `name` alone. Documenting the root-node convention would help.
**Fix:** Either set `name = ""` (root sentinel) or document `"name": "<case basename>"` in the docstring.

---

_Reviewed: 2026-05-13T04:58:48Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
