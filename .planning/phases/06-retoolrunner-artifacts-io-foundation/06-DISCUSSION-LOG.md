# Phase 6: ReToolRunner + artifacts_io Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 6-retoolrunner-artifacts-io-foundation
**Areas discussed:** Public API shape, Module layout, Config + log naming, confine_to semantics (all under Claude's-Discretion mandate)

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Public API shape | Class instance vs module-level function for `ReToolRunner`; what every Phase 7-11 tool module imports | ✓ (resolved by Claude discretion) |
| Module layout | Two flat modules `runner.py` + `artifacts_io.py` vs `re_runtime/` package vs merging `confine_to` into existing `tools/case_dirs.py` | ✓ (resolved by Claude discretion) |
| Config + log naming | Env-var names/defaults, per-call override policy, exact `tool-logs/<timestamp>-<slug>.txt` format | ✓ (resolved by Claude discretion) |
| confine_to semantics | Realpath strictness, treatment of not-yet-created targets, symlink policy, return shape | ✓ (resolved by Claude discretion) |

**User's choice:** "Choose the best and most robust architecture for me." (verbatim)

**Notes:** Claude proceeded under the Phase 5 precedent — all four gray areas were resolved with Claude-recommended defaults, with each decision's rationale captured in CONTEXT.md so the planner can verify the trade-offs rather than re-derive them.

---

## Public API shape

| Option | Description | Selected |
|--------|-------------|----------|
| Class-only `ReToolRunner` | One construct-then-`await runner.run(argv)` form | ✓ (primary) |
| Free function only | `await run_tool(case_dir, argv, ...)` flat function | ✓ (also exposed, thin wrapper) |
| Class + module-level convenience | Class for Phase 8/9 stateful holders, free function for Phase 7 one-shots | ✓ (combined recommendation, D-01 + D-02) |

**Notes:** Class for stateful callers (sessions hold a runner across cancel hooks; jobs hold a runner across `get_tool_job` polls); thin `run_tool(...)` free function for fire-and-forget Phase 7 wrappers. Return-dict shape locked at D-03 so it never re-shapes across phases. Pre-spawn programmer errors raise; post-spawn states (timeout, non-zero exit) return a dict (D-04).

---

## Module layout

| Option | Description | Selected |
|--------|-------------|----------|
| Two flat modules at package top | `mcp_gateway/runner.py` + `mcp_gateway/artifacts_io.py` (research wording) | ✓ (D-05) |
| New `re_runtime/` package | Nested package with `runner.py`, `paths.py`, `subdirs.py` | (rejected — premature for ~600 LoC) |
| Merge `confine_to` into `tools/case_dirs.py` | One path-guard surface | (rejected — creates import-layering inversion) |

**Notes:** Top-level flat modules keep imports unambiguous and prevent the `case_dirs ↔ artifacts_io` cycle that would otherwise appear once `case_dirs` wants to canonicalize an artifact path. `runner.py` may depend on `artifacts_io.py`, not vice versa (D-07).

---

## Config + log naming

| Option | Description | Selected |
|--------|-------------|----------|
| Hardcoded constants | 256 KB / 64 KB / 55 s / 256 MB inlined; no env vars | (rejected — Phase 9 jobs need to tune) |
| Env-var-only globals | Set at startup, no per-call overrides | (rejected — Phase 7 needs slug-specific timeouts) |
| Env-var defaults + per-call kwarg override | Read once at module import, kwarg wins | ✓ (D-08) |

**Notes:** Four env knobs (`MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB`, `..._STDERR_HEAD_KB`, `..._DEFAULT_TIMEOUT_S`, `..._MAX_LOG_MB`) with hard-validated defaults at module import. 55 s default timeout is deliberately below the 60 s MCP request cap by 5 s.

| Option | Description | Selected |
|--------|-------------|----------|
| Epoch-ms timestamp | `1747142581123-slug.txt` | (rejected — not human-readable) |
| Compact ISO basic UTC | `20260513T142301Z-<slug>-<rand4>.txt` | ✓ (D-09) |
| Hyphen-separated readable | `2026-05-13_14-23-01-slug.txt` | (rejected — colons/underscores inconsistent across host FSes) |

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-derived slug (argv[0] basename) | No required kwarg | (rejected — argv[0] is `env`/`bash`/path-to-script too often) |
| Caller-supplied required slug, regex-validated | `^[a-z0-9][a-z0-9_-]{0,39}$`, auto-lowercased | ✓ (D-09) |

| Option | Description | Selected |
|--------|-------------|----------|
| Same-second collision: bump to nanosecond | `20260513T142301.123456789Z-slug.txt` | (rejected — ugly filename, OS clock-monotonicity dependence) |
| Same-second collision: 4-hex-char suffix | `secrets.token_hex(2)` → `-a3f7` | ✓ (D-09) |

**Notes:** `log_path` in the return dict is stored relative to `case_dir` (D-10) so the wire response never leaks host paths.

---

## confine_to semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Strict-only: target must exist | `Path.resolve(strict=True)` | (rejected — blocks `write_artifact` use case) |
| Lenient: accept non-existing leaf | `Path.resolve(strict=False)` for target, `strict=True` for case_dir | ✓ (D-11) |

| Option | Description | Selected |
|--------|-------------|----------|
| Reject all symlinks via `lstat` walk | Defensive but expensive | (rejected — realpath comparison catches escapes) |
| Allow symlinks; rely on realpath containment | Symlink fine if resolved target stays inside case_dir | ✓ (D-12) |

| Option | Description | Selected |
|--------|-------------|----------|
| Validate-only, return None on success | Caller re-resolves the path | (rejected — duplicate work) |
| Validate and return canonical resolved Path | Caller uses it directly | ✓ (D-11) |

| Option | Description | Selected |
|--------|-------------|----------|
| `confine_to` also enforces STATUS_ROOT scope | One-stop guard | (rejected — couples `artifacts_io` to `samples`) |
| Keep separate; callers compose `resolve_case_dir` + `confine_to` | Layer cleanly | ✓ (D-14) |

---

## Claude's Discretion

- Concurrent-stream-drain primitive: `anyio.create_task_group` vs `asyncio.gather` of two reader coroutines — both acceptable; planner picks.
- Whether `ensure_subdir` defensively re-validates parent is under STATUS_ROOT (recommended NO; callers compose with `resolve_case_dir`).
- ANSI-strip implementation: stdlib regex preferred, no new dep unless a real RE-tool sequence misses.
- Log file open style: `open(log_path, "ab", buffering=0)` vs append-chunks — either is fine if partial writes flush before return.

## Deferred Ideas

- Convergence of `subprocess_runner.run_script` with `ReToolRunner` (v1.2+).
- Follow-fork straggler scan via `/proc/<pid>/task/*/children` (Phase 11).
- SIGTERM-then-SIGKILL grace period (Phase 9 Jobs).
- Per-`Mcp-Session-Id` keying (v1.2).
- Mount-namespace isolation for the runner subprocess (v1.2).
- Per-call log rotation (v1.2+).
- Refactoring `tools/artifacts.py::get_artifact` to call `confine_to` (allowed but not required by Phase 6).
