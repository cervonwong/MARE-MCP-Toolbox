---
phase: 02-mcp-gateway
reviewed: 2026-04-27T00:00:00Z
depth: standard
files_reviewed: 39
files_reviewed_list:
  - CLAUDE.md
  - Dockerfile
  - compose.yaml
  - mcp-gateway/README.md
  - mcp-gateway/pyproject.toml
  - mcp-gateway/src/mcp_gateway/__init__.py
  - mcp-gateway/src/mcp_gateway/__main__.py
  - mcp-gateway/src/mcp_gateway/_version.py
  - mcp-gateway/src/mcp_gateway/app.py
  - mcp-gateway/src/mcp_gateway/auth.py
  - mcp-gateway/src/mcp_gateway/backend/__init__.py
  - mcp-gateway/src/mcp_gateway/backend/client.py
  - mcp-gateway/src/mcp_gateway/backend/detect.py
  - mcp-gateway/src/mcp_gateway/backend/tool_map.py
  - mcp-gateway/src/mcp_gateway/cli.py
  - mcp-gateway/src/mcp_gateway/session_state.py
  - mcp-gateway/src/mcp_gateway/subprocess_runner.py
  - mcp-gateway/src/mcp_gateway/tools/__init__.py
  - mcp-gateway/src/mcp_gateway/tools/artifacts.py
  - mcp-gateway/src/mcp_gateway/tools/cases.py
  - mcp-gateway/src/mcp_gateway/tools/disasm.py
  - mcp-gateway/src/mcp_gateway/tools/samples.py
  - mcp-gateway/src/mcp_gateway/tools/workflows.py
  - mcp-gateway/src/mcp_gateway/uploads.py
  - mcp-gateway/tests/__init__.py
  - mcp-gateway/tests/conftest.py
  - mcp-gateway/tests/e2e/smoke.sh
  - mcp-gateway/tests/e2e/test_upload_then_analyze.sh
  - mcp-gateway/tests/test_artifact_tools.py
  - mcp-gateway/tests/test_auth.py
  - mcp-gateway/tests/test_cli.py
  - mcp-gateway/tests/test_detect.py
  - mcp-gateway/tests/test_sample_resolution.py
  - mcp-gateway/tests/test_server_init.py
  - mcp-gateway/tests/test_tool_list.py
  - mcp-gateway/tests/test_tool_map.py
  - mcp-gateway/tests/test_tool_routing.py
  - mcp-gateway/tests/test_uploads.py
  - mcp-gateway/tests/test_workflow_tools.py
findings:
  critical: 0
  warning: 6
  info: 9
  total: 15
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-04-27T00:00:00Z
**Depth:** standard
**Files Reviewed:** 39
**Status:** issues_found

## Summary

Phase 02 (MCP Gateway) delivers a well-structured custom FastMCP gateway with bearer auth,
Origin validation, streaming uploads, sha256-based content addressing, and unified
disassembler tool routing. The codebase shows strong attention to security: constant-time
bearer comparison via `hmac.compare_digest`, path-traversal defenses in `samples.py` and
`get_artifact`, argv-only subprocess execution (no shell), 0600 token file mode, streaming
uploads with size cap enforcement during the stream, and content-addressed dedup.

Test coverage is broad (auth, uploads, tool registration, routing, traversal, lifespan
wiring). E2E smoke tests gate the main protocol entry points.

**No Critical issues found.** The findings below are mostly correctness nits, edge-case
robustness gaps, and minor cosmetic inconsistencies. The most notable items:

- A misleading inline comment about middleware ordering in `app.py` that contradicts the
  actual code (behavior is correct, comment is wrong).
- A latent attribute-name inconsistency in `cases.get_active_backend()` that depends on a
  defensive fallback to keep working.
- Filename-validation rules differ slightly between `uploads.py` and `artifacts.py`.
- A few timeout values diverge between `workflows.run_triage` and the equivalent atomic
  `artifacts.py` tools.

## Warnings

### WR-01: Misleading comment about middleware add-order in `build_app`

**File:** `mcp-gateway/src/mcp_gateway/app.py:128-131`
**Issue:**
The inline comment claims:

> "Order matters: Starlette runs middleware in REVERSE add order for requests,
> so add Bearer last (innermost) to run first; add Origin before Bearer (outermost)."

But the code adds Bearer FIRST and Origin SECOND, contradicting the comment's "add Bearer
last" instruction. In Starlette, middleware added later wraps earlier ones, so the actual
runtime order is: Origin (outermost, runs first) → Bearer (inner, runs second). That order
is correct (and confirmed by `test_healthz_open_ignores_origin`), but the comment is
self-contradictory and will confuse the next reader. Either the comment or the code has the
wrong rationale.

**Fix:** Replace the comment to match what the code actually does:
```python
# Starlette wraps middlewares in add-order: the LAST one added becomes the
# OUTERMOST (runs first on a request). Add Bearer first (inner: runs second),
# then Origin (outer: runs first → DNS-rebind check before auth).
app.add_middleware(BearerAuthMiddleware, token=token)
app.add_middleware(OriginMiddleware)
```

### WR-02: `get_active_backend` reads non-existent `name` attribute first

**File:** `mcp-gateway/src/mcp_gateway/tools/cases.py:88-93`
**Issue:**
The handler does:
```python
name = getattr(pinned, "name", None) or getattr(pinned, "backend", None) or "unknown"
```
With a header comment `"PinnedBackend exposes a `name` attribute (str) per Plan 03."`
However, `backend/client.py:43` actually exposes `self.backend = backend` (no `.name`).
The fallback chain rescues correctness, but the primary lookup will always miss and the
comment is wrong. This indicates either drift between Plan 03 and Plan 05 or a copy-paste
mistake — a future refactor that "cleans up" the fallback could break the behavior silently.

**Fix:** Either rename the attribute on `PinnedBackend` for clarity:
```python
class PinnedBackend:
    def __init__(self, backend: str):
        ...
        self.backend = backend
        self.name = backend  # public alias
```
…or simplify the lookup and update the comment:
```python
# PinnedBackend.backend is the canonical attribute (see backend/client.py).
name = getattr(pinned, "backend", "unknown")
return {"backend": str(name)}
```

### WR-03: `disasm.*` handlers forward `sample_path: None` when no sample provided

**File:** `mcp-gateway/src/mcp_gateway/tools/disasm.py:34-38, 45-48, 55-58`
**Issue:**
When the client omits the `sample` argument, `sample_path` becomes `None`, and the call
`PINNED_BACKEND.call_unified("decompile", {"function": function, "sample_path": None})`
forwards an explicit `None` to the backend. Some backend MCP servers (especially IDA via
idalib-mcp and Ghidra) may reject `None` for a path-typed parameter, returning a confusing
JSON-schema validation error instead of "use the active program."
This is exercised in tests only with a captured fake backend; real backends were not part
of this review.

**Fix:** Drop the key entirely when there is no sample, so the backend uses its current
loaded program:
```python
args = {"function": function}
if sample is not None:
    args["sample_path"] = resolve_sample(sample)
return await session_state.PINNED_BACKEND.call_unified("decompile", args)
```
Apply the same change to `list_functions` and `get_xrefs`.

### WR-04: Filename-validation rules diverge between `uploads.py` and `artifacts.py`

**File:** `mcp-gateway/src/mcp_gateway/tools/artifacts.py:100` vs `mcp-gateway/src/mcp_gateway/uploads.py:46-58`
**Issue:**
`uploads._is_invalid_filename` rejects backslash (`\`), control chars, empty strings, and
leading dot — a fairly thorough allowlist. `artifacts.get_artifact` only rejects `/`, `..`,
and leading dot. A request like `get_artifact(case_dir=..., artifact_name="foo\\bar")`
passes the artifacts check on Linux (where `\\` is a legitimate filename character) but
would be inconsistent with how the system validates filenames elsewhere. More importantly,
control characters (e.g., `\n`) in `artifact_name` slip through.

**Fix:** Reuse the same predicate, or extract a shared helper:
```python
# In artifacts.py
from ..uploads import _is_invalid_filename

if _is_invalid_filename(artifact_name):
    raise ValueError("artifact_name must be a simple filename without separators or controls")
```
(Promote `_is_invalid_filename` to public — drop the leading underscore — if it's reused.)

### WR-05: `int()` parsing of `MCP_GATEWAY_PORT` / `MCP_GATEWAY_MAX_UPLOAD_MB` raises on bad input

**File:** `mcp-gateway/src/mcp_gateway/cli.py:22` and `mcp-gateway/src/mcp_gateway/uploads.py:36`
**Issue:**
A misconfigured environment variable (e.g., `MCP_GATEWAY_PORT=abc` or
`MCP_GATEWAY_MAX_UPLOAD_MB=-1`) causes an unhandled `ValueError` at startup or first upload
respectively. The user gets a stack trace instead of a clear "bad config" message.
For `MAX_UPLOAD_MB`, negative or zero values silently produce a 0-byte cap (any non-empty
upload returns 413), which is technically "working" but is non-obvious.

**Fix:** Wrap and validate at the boundary:
```python
def _max_bytes() -> int:
    raw = os.environ.get("MCP_GATEWAY_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))
    try:
        mb = int(raw)
    except ValueError as e:
        raise RuntimeError(f"MCP_GATEWAY_MAX_UPLOAD_MB must be an integer, got {raw!r}") from e
    if mb < 0:
        raise RuntimeError(f"MCP_GATEWAY_MAX_UPLOAD_MB must be >= 0, got {mb}")
    return mb * 1024 * 1024
```
Apply the same pattern to `cli.build_parser` for `--port` defaulting.

### WR-06: `workflows.run_triage` has a 600s timeout for `build_hypothesis`, but the atomic tool uses 60s

**File:** `mcp-gateway/src/mcp_gateway/tools/workflows.py:54` vs `mcp-gateway/src/mcp_gateway/tools/artifacts.py:77`
**Issue:**
`run_triage` calls `build_hypothesis.py` with `timeout=600.0` (the loop reuses one timeout
for both `rank_signals.py` and `build_hypothesis.py`). The atomic tool wrapper for the same
script uses `FAST_TIMEOUT_S = 60.0`. Same script, two different timeout policies — whichever
is "right," the inconsistency is a latent bug: a regression in one script will be detectable
via the atomic tool but invisible (timed-out at 10 minutes) via `run_triage`, or vice versa.

**Fix:** Use a per-step timeout map mirroring the atomic-tool values, or consolidate
constants in one place:
```python
PY_STEPS = [
    ("rank_signals",     "rank_signals.py",     CASE_TIMEOUT_S),
    ("build_hypothesis", "build_hypothesis.py", FAST_TIMEOUT_S),
]
for name, py_script, timeout in PY_STEPS:
    ...
    r = await run_script(argv, cwd="/agent", timeout=timeout)
```

## Info

### IN-01: `BearerAuthMiddleware.PROTECTED_PREFIXES` matches by prefix substring, not path component

**File:** `mcp-gateway/src/mcp_gateway/auth.py:57, 64`
**Issue:**
`request.url.path.startswith("/mcp")` would protect a hypothetical future route like
`/mcpfoo` even though that's almost certainly unintended. Same for `/uploads` (plural).
Currently no such routes exist, so this is purely defensive future-proofing.

**Fix:**
```python
PROTECTED_PREFIXES = ("/mcp/", "/upload", "/upload/")
# Or check both exact match and trailing slash:
path = request.url.path
if not (path == "/mcp" or path.startswith("/mcp/") or
        path == "/upload" or path.startswith("/upload/")):
    return await call_next(request)
```

### IN-02: `cases.list_uploads` filter `len(sha_dir.name) == 64` does not require hex

**File:** `mcp-gateway/src/mcp_gateway/tools/cases.py:51`
**Issue:**
A 64-character non-hex directory under `/agent/uploads/` would still appear in
`list_uploads()`. Cosmetic only — the upload handler always creates hex-named dirs.

**Fix:**
```python
if sha_dir.is_dir() and re.fullmatch(r"[0-9a-f]{64}", sha_dir.name):
    ...
```

### IN-03: `tests/__init__.py` is empty (size 0)

**File:** `mcp-gateway/tests/__init__.py`
**Issue:**
The file is empty (Read tool reported "file exists but is shorter than the provided
offset 1"). That is fine for a test package marker, but ruff/flake8 in some configurations
flag the file. No action required if the project's lint config is happy.

**Fix:** Either delete (modern pytest doesn't require an `__init__.py` in `tests/`) or add
a one-line docstring `"""mcp-gateway test suite."""` to silence linters.

### IN-04: `uploads.py` does not `fsync` written data before responding 200

**File:** `mcp-gateway/src/mcp_gateway/uploads.py:118-152`
**Issue:**
After `tmp.write(chunk)` and `shutil.move`, no fsync is called. On a host crash within
seconds of a successful upload, the gateway claimed `200 OK` for data that may not have hit
disk. For Phase 2's local/team use case this is acceptable (matches typical web-app
semantics) but worth noting.

**Fix:** Add an explicit fsync inside the temp-file finalize block before the rename:
```python
finally:
    tmp.flush()
    os.fsync(tmp.fileno())
    tmp.close()
```

### IN-05: TOCTOU race between `target.exists()` and `shutil.move`

**File:** `mcp-gateway/src/mcp_gateway/uploads.py:142-152`
**Issue:**
Two concurrent uploads of the same byte content both pass the `target.exists()` check
(False), then race to `shutil.move(tmp.name, str(target))`. The second move silently
overwrites. Because content is identical and 0644 is set after, the visible result is
correct, but file mtime/inode flips and one tmp file is implicitly clobbered. Not a real
bug, just non-obvious.

**Fix:** Use `os.rename` with `O_EXCL` semantics or rename inside a try/except:
```python
try:
    os.link(tmp.name, str(target))   # fails if target exists
    os.unlink(tmp.name)
except FileExistsError:
    os.unlink(tmp.name)               # dedupe: drop tmp
```

### IN-06: `artifacts.get_artifact` re-imports `os` as `_os`

**File:** `mcp-gateway/src/mcp_gateway/tools/artifacts.py:104`
**Issue:**
`import os as _os` inside the function while the module never imports `os` at the top.
Either the module-top should import `os`, or the local import should be removed in favor
of using `pathlib` consistently (`Path.resolve(strict=False)`). Cosmetic; works fine.

**Fix:** Move to top-level:
```python
# top of artifacts.py
import os
...
real_case = os.path.realpath(case_dir)
real_full = os.path.realpath(str(full))
```

### IN-07: `workflows.generate_report` has no path-traversal check on `case_dir`

**File:** `mcp-gateway/src/mcp_gateway/tools/workflows.py:77-82`
**Issue:**
`Path(case_dir) / "10_reporting_draft.md"` accepts any absolute path, then reads it. The
caller is trusted (authenticated MCP client), so this is a low-priority defense-in-depth
note. `get_artifact` does enforce a containment check.

**Fix:** Same canonicalization pattern used in `get_artifact`:
```python
real_case = os.path.realpath(case_dir)
if not real_case.startswith(str(STATUS_ROOT.resolve()) + os.sep):
    return {"error": "case_dir must be under STATUS_ROOT"}
```

### IN-08: `samples.resolve_sample` picks `sorted(...)[0]` when a sha256 dir has multiple files

**File:** `mcp-gateway/src/mcp_gateway/tools/samples.py:49-52`
**Issue:**
Per D-13 there is only ever one file per hash, but if two uploads with different filenames
slip in (e.g., older data), the alphabetical first wins silently. A warning log line would
help diagnose surprising behavior.

**Fix:**
```python
if len(candidates) > 1:
    log.warning("[samples] multiple files for sha256=%s -- picking %s", sample, candidates[0].name)
return _resolve_allowed(candidates[0])
```

### IN-09: `tests/test_artifact_tools.py` and `test_workflow_tools.py` reach into FastMCP private `_tool_manager._tools`

**File:** `mcp-gateway/tests/test_artifact_tools.py:46-50`, `mcp-gateway/tests/test_workflow_tools.py:46-50`
**Issue:**
Acknowledged in the file with a TODO comment + pinned `mcp>=1.27,<1.28` range. The argv-shape
tests legitimately need direct function access; switching them to `call_tool` would couple
them to MCP transport details. Just flagging that the next SDK upgrade is a known break-point.

**Fix:** No change recommended for Phase 2. When the SDK is bumped, replace these with
`create_connected_server_and_client_session` and assert on captured `run_script` argv via
the `monkeypatch` only (drop the direct `.fn` extraction).

---

_Reviewed: 2026-04-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
