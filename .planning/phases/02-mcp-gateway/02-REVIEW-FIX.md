---
phase: 02-mcp-gateway
fixed_at: 2026-04-27T00:00:00Z
review_path: .planning/phases/02-mcp-gateway/02-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-04-27T00:00:00Z
**Source review:** .planning/phases/02-mcp-gateway/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (0 critical + 6 warning; 9 info findings out of scope)
- Fixed: 6
- Skipped: 0

## Fixed Issues

### WR-01: Misleading comment about middleware add-order in `build_app`

**Files modified:** `mcp-gateway/src/mcp_gateway/app.py`
**Commit:** 5befb88
**Applied fix:** Replaced the self-contradictory comment in `build_app` with one that
matches the actual code: documented that Starlette wraps middlewares in add-order so the
LAST one added becomes the OUTERMOST, and that Bearer is added first (inner) followed by
Origin (outer) so the DNS-rebind check runs before auth.

### WR-02: `get_active_backend` reads non-existent `name` attribute first

**Files modified:** `mcp-gateway/src/mcp_gateway/backend/client.py`, `mcp-gateway/src/mcp_gateway/tools/cases.py`
**Commit:** 10f730b
**Applied fix:** Added a public `self.name = backend` alias to `PinnedBackend.__init__` so
the comment in `get_active_backend` is now accurate. Also reordered the lookup chain to
prefer the canonical `.backend` attribute first and fall back to `.name` defensively, and
updated the inline comment to reflect the actual attribute layout.

### WR-03: `disasm.*` handlers forward `sample_path: None` when no sample provided

**Files modified:** `mcp-gateway/src/mcp_gateway/tools/disasm.py`
**Commit:** 31b19b3
**Applied fix:** Built the `args` dict incrementally in `decompile`, `list_functions`, and
`get_xrefs` -- only set the `sample_path` key when `sample is not None`. This prevents
forwarding an explicit `None` to backends that may reject it with a JSON-schema validation
error and lets the backend fall back to its currently-loaded program.

### WR-04: Filename-validation rules diverge between `uploads.py` and `artifacts.py`

**Files modified:** `mcp-gateway/src/mcp_gateway/tools/artifacts.py`
**Commit:** a29bb94
**Applied fix:** `artifacts.get_artifact` now imports and reuses `_is_invalid_filename`
from `uploads.py` so backslash, control characters, empty strings, and leading dot are all
rejected uniformly. Also moved `import os` to the module top, removing the in-function
`import os as _os` (this incidentally addresses IN-06).

### WR-05: `int()` parsing of `MCP_GATEWAY_PORT` / `MCP_GATEWAY_MAX_UPLOAD_MB` raises on bad input

**Files modified:** `mcp-gateway/src/mcp_gateway/uploads.py`, `mcp-gateway/src/mcp_gateway/cli.py`
**Commit:** 800ea86
**Applied fix:** Wrapped both env-var parses with try/except `ValueError` and explicit
range checks. `MCP_GATEWAY_MAX_UPLOAD_MB` now raises `RuntimeError` with a clear message on
non-integer or negative values. Added a `_default_port()` helper in `cli.py` that validates
the integer parse and the 0..65535 range, with descriptive error messages.

### WR-06: `workflows.run_triage` has a 600s timeout for `build_hypothesis`, but the atomic tool uses 60s

**Files modified:** `mcp-gateway/src/mcp_gateway/tools/workflows.py`
**Commit:** 809b949
**Applied fix:** Imported `CASE_TIMEOUT_S` and `FAST_TIMEOUT_S` from `artifacts.py` and
replaced all literal timeouts (60.0 / 600.0) with these constants. Converted the python
loop to an explicit per-step `(name, script, timeout)` tuple list so `rank_signals` keeps
`CASE_TIMEOUT_S` and `build_hypothesis` uses `FAST_TIMEOUT_S`, mirroring the atomic-tool
wrappers. Also updated `run_deep_analysis` to use `FAST_TIMEOUT_S` for consistency.

---

_Fixed: 2026-04-27_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
