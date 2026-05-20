---
phase: 11-dynamic-lab-mode-env-gated
plan: 01
subsystem: refactor
tags: [sessions, dataclass, package-refactor, gdb-prep, phase-8-compat]

requires:
  - phase: 08-session-scoped-r2
    provides: monolithic sessions.py (R2Session, SessionRegistry, _DANGEROUS_R2_CMD_RE, env-var constants, cap-reject + reaper machinery)
provides:
  - sessions/ package with _base.py (BaseSession dataclass + SessionRegistry + env constants + ANSI helpers + make_sentinel factory) and r2.py (R2Session subclass + _open_r2 driver + _DANGEROUS_R2_CMD_RE)
  - kind-aware SessionRegistry.open(kind="r2"|"gdb") with default "r2" for backward compat
  - explicit-name re-export __init__.py preserving entire Phase 8 public surface
  - 10 new regression tests in tests/test_sessions_package.py locking the refactor invariants
  - 5 new require-helpers (_require_gdb_or_skip, _require_strace_or_skip, _require_ltrace_or_skip, _require_qemu_user_or_skip, _require_netns_or_skip) for Phase 11 Plans 02-06
affects: [11-02 dynamic capabilities, 11-03 gdb session driver, 11-04 dynamic tools, 11-05 lifespan wiring, 11-06 e2e]

tech-stack:
  added: []
  patterns:
    - "Package-as-shim refactor pattern: monolithic module -> package with explicit-name re-export __init__.py + LEAF submodule + kind-specific driver submodule; force-reload submodules from __init__ so importlib.reload(pkg) propagates env-var validation"
    - "Dataclass-inheritance discipline for kind-aware sessions: BaseSession with kind-agnostic fields (all defaulted at the tail), subclass adds kind-specific fields with defaults (Python 3.11 dataclass rule)"
    - "Deferred-import dispatch in SessionRegistry.open: `if kind == 'gdb': from .gdb import _open_gdb` inside method body so the gdb module need not exist until Plan 03"

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/sessions/__init__.py
    - mcp-gateway/src/mcp_gateway/sessions/_base.py
    - mcp-gateway/src/mcp_gateway/sessions/r2.py
    - mcp-gateway/tests/test_sessions_package.py
  modified:
    - mcp-gateway/tests/conftest.py
  deleted:
    - mcp-gateway/src/mcp_gateway/sessions.py

key-decisions:
  - "Force-reload submodules from sessions/__init__.py to preserve Phase 8 importlib.reload(sessions) env-validation semantics (RuntimeError on bad MCP_GATEWAY_SESSION_IDLE_S=-5)"
  - "BaseSession.kind is Literal['r2','gdb'] with default 'r2'; R2Session re-declares kind='r2' as a frozen-literal default to keep mypy/grep audit honest"
  - "_open_r2 takes the registry as first positional arg (registry._lock, registry._sessions, etc.) so the dispatch in SessionRegistry.open is a single-line forward; symmetric pattern for Plan 03's _open_gdb"
  - "Sentinel factory make_sentinel() extracted to _base.py (was inline secrets.token_hex(4) in Phase 8); Plan 03's gdb driver reuses identical __MARE_END_<8hex>__ generator"

patterns-established:
  - "sessions/__init__.py re-exports are explicit-name (not wildcard) for grep-friendly auditing per RESEARCH.md Pitfall #11"
  - "list() snapshot includes the new 'kind' field for cross-kind callers; r2-only callers harmlessly ignore the extra key"
  - "sample_sha256 access in registry.list() uses getattr(sess, 'sample_sha256', '') so kind-agnostic iteration does not crash on future gdb sessions without that exact attr name"

requirements-completed: [DYN-05]

duration: ~6 min
completed: 2026-05-20
---

# Phase 11 Plan 01: sessions/ package refactor Summary

**Promoted monolithic 458-line sessions.py into a sessions/ package (_base.py + r2.py + __init__.py) with BaseSession dataclass and kind-aware SessionRegistry, unlocking Plan 03's gdb driver without breaking any Phase 8/9/10 caller.**

## Performance

- **Duration:** ~6 min (2026-05-20T00:24:56Z → 2026-05-20T00:30:47Z)
- **Started:** 2026-05-20T00:24:56Z
- **Completed:** 2026-05-20T00:30:47Z
- **Tasks:** 2 (both atomic, TDD: RED test commit then GREEN refactor commit)
- **Files created:** 4 (sessions/__init__.py, sessions/_base.py, sessions/r2.py, tests/test_sessions_package.py)
- **Files modified:** 1 (tests/conftest.py)
- **Files deleted:** 1 (sessions.py)

**Line counts (post-refactor):**

| File | LoC |
|------|-----|
| sessions/__init__.py | 60 |
| sessions/_base.py | 361 |
| sessions/r2.py | 225 |
| tests/test_sessions_package.py | 142 |
| **Total package** | **646** |

The package is larger than the monolithic 458 LoC because it adds the BaseSession dataclass (14 fields), make_sentinel() factory, kind-dispatch in SessionRegistry.open, and explicit re-export bookkeeping.

## Accomplishments

- **Phase 8 public surface preserved byte-identical via re-exports** — every name in CLAUDE.md / app.py / tools/r2_sessions.py / session_state.py / test_sessions.py imports unchanged. `from mcp_gateway.sessions import SessionRegistry, MAX_SESSIONS, SESSION_IDLE_S, REAPER_INTERVAL_S` (the exact app.py:22-27 import) keeps working.
- **BaseSession dataclass landed** with 14 kind-agnostic fields; R2Session subclasses it with sample_sha256 + sample_path additions; future GdbSession (Plan 03) subclasses BaseSession symmetrically.
- **SessionRegistry.open gained `kind: Literal['r2','gdb']` kwarg** with default `"r2"`. All existing Phase 8/9/10 callers (which never pass `kind`) keep working unchanged.
- **`make_sentinel()` factory extracted** to `_base.py` so Plan 03's gdb driver reuses the identical `__MARE_END_<8hex>__` generator semantics.
- **10 new regression tests** lock the refactor invariants (re-export identity, BaseSession field set, R2Session subclassing, kind kwarg signature, no-legacy-sessions.py, reload determinism).
- **5 new require-helpers added to conftest.py** for Phase 11 Plans 02-06: `_require_gdb_or_skip`, `_require_strace_or_skip`, `_require_ltrace_or_skip`, `_require_qemu_user_or_skip(arch='arm')`, `_require_netns_or_skip` (probe via `unshare --net true`).

## Task Commits

1. **Task 1: Wave-0 regression tests + conftest fixtures** — `b0138cb` (test)
2. **Task 2: Delete sessions.py; create sessions/ package** — `c6b5b5b` (refactor)

## Files Created/Modified

- `mcp-gateway/src/mcp_gateway/sessions/__init__.py` — explicit-name re-export of every Phase 8 + Phase 11 symbol; force-reloads `_base` + `r2` on package reload so `importlib.reload(sessions)` keeps Phase 8 env-validation semantics.
- `mcp-gateway/src/mcp_gateway/sessions/_base.py` — BaseSession dataclass; SessionRegistry (kind-aware open); SessionCapReached; 5 env-var module constants; `_env_int`/`_env_float`; ANSI/UTF-8 helpers; `make_sentinel()`. LEAF — no `mcp_gateway.*` imports beyond stdlib.
- `mcp-gateway/src/mcp_gateway/sessions/r2.py` — R2Session dataclass (subclass of BaseSession); `_DANGEROUS_R2_CMD_RE` + `check_dangerous_cmd`; `_open_r2(registry, ...)` driver extracted verbatim from Phase 8 SessionRegistry.open body.
- `mcp-gateway/tests/test_sessions_package.py` (NEW) — 10 regression tests covering re-export identity, BaseSession dataclass shape, R2Session subclassing, reload determinism, kind kwarg signature, no-legacy-sessions.py invariant.
- `mcp-gateway/tests/conftest.py` (MODIFIED) — added 5 `_require_*_or_skip` helpers for Phase 11 Plans 02-06; preserved existing `_require_r2_or_skip` and fixture bodies unchanged.
- `mcp-gateway/src/mcp_gateway/sessions.py` (DELETED) — its 458 lines are now in `sessions/_base.py` (~290 lines of the original) + `sessions/r2.py` (~168 lines of the original).

## Decisions Made

- **Force-reload submodules from `sessions/__init__.py`** (4 lines at the top of __init__.py): `for _submod in ("mcp_gateway.sessions._base", "mcp_gateway.sessions.r2"): if _m := sys.modules.get(_submod): importlib.reload(_m)`. This preserves the Phase 8 D-14 invariant that `importlib.reload(mcp_gateway.sessions)` re-evaluates env vars — Python's default `from X import Y` semantics would have skipped the re-execution.
- **Dataclass inheritance via tail-defaulted fields**: BaseSession's fields with defaults (`command_count=0, closed=False, close_reason=None, kind="r2"`) live at the tail; R2Session adds `sample_sha256=""` and `sample_path=Path()` (default_factory) so the Python 3.11 dataclass rule ("no non-default after default") is honoured. Callers always pass both via keyword in `_open_r2`.
- **`_open_r2` is a module-level function, not a method** on R2Session. Symmetry with future `_open_gdb` and clean kind-dispatch in `SessionRegistry.open` (`if kind == "r2": return await _open_r2(self, ...)`).
- **List() snapshot adds `"kind"` field** to every entry. Phase 8 test_r2_sessions.py never checks for or against extra keys, so this is non-breaking. Cross-kind callers (Plan 03+) can distinguish r2 vs gdb sessions without a new tool.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Force-reload submodules to preserve Phase 8 env-validation reload semantics**
- **Found during:** Task 2 (post-refactor regression test run)
- **Issue:** Phase 8 test `test_sessions.py::test_env_var_bad_value_raises` does `monkeypatch.setenv("MCP_GATEWAY_SESSION_IDLE_S", "-5"); importlib.reload(mcp_gateway.sessions)` and expects RuntimeError. With the new package layout, `reload(sessions)` re-executes `__init__.py` which does `from ._base import ...`; Python's `from X import Y` only fetches Y from `sys.modules` — it does NOT re-execute `_base.py`. So the env-var validation never re-ran, and the test failed with `Failed: DID NOT RAISE <class 'RuntimeError'>`.
- **Fix:** Added a 4-line `for _submod in (...): if sys.modules.get(_submod): importlib.reload(_submod)` block at the top of `sessions/__init__.py` (before the `from ._base import ...` block). This forces `_base.py` and `r2.py` to re-execute whenever the package is reloaded.
- **Files modified:** `mcp-gateway/src/mcp_gateway/sessions/__init__.py`
- **Verification:** `pytest tests/test_sessions.py::test_env_var_bad_value_raises` passes; the 10 new regression tests still pass.
- **Committed in:** `c6b5b5b` (Task 2 commit; deviation fix landed in the same atomic refactor commit)

---

**Total deviations:** 1 auto-fixed (1 bug — preserved Phase 8 contract that would otherwise have silently regressed)
**Impact on plan:** Necessary correctness fix to honour Phase 8 D-14 reload semantics. No scope creep — the fix is 4 lines inside the existing `__init__.py` Task 2 was already creating.

## Issues Encountered

- **Phase 8 reload-semantics drift** (resolved during Task 2 — see Deviation #1 above). The first run of `pytest tests/test_sessions.py tests/test_r2_sessions.py` post-refactor showed exactly one failure in `test_env_var_bad_value_raises`. Fixed in the same commit as Task 2.
- **Host-environment unrelated failures** (out of scope): `tests/test_acl_available.py::test_setfacl_on_path` fails on this host because `setfacl` is not installed (acl pkg ships in the container build, not on the WSL executor). Pre-existing per Phase 7-08 SUMMARY. NOT touched by this refactor.
- **Test-isolation flakiness** (out of scope, transient): when running the full non-slow suite, `tests/jobs/test_errors.py::test_unknown_tool_shape` and `tests/jobs/test_list_tool_jobs.py::test_specs_*` reported failures that disappeared when each file was run in isolation. This is a pre-existing test-ordering issue (jobs registry monkeypatching across modules) unrelated to the sessions refactor.

## Verification

All <verification> commands from the plan pass:

- `pytest mcp-gateway/tests/test_sessions_package.py mcp-gateway/tests/test_sessions.py mcp-gateway/tests/test_r2_sessions.py mcp-gateway/tests/test_tool_list.py -x` → **21 passed, 15 skipped (host r2 missing)** exit 0.
- `[ ! -f mcp-gateway/src/mcp_gateway/sessions.py ]` → DELETED.
- `python -c "import mcp_gateway.sessions; import mcp_gateway.sessions._base; import mcp_gateway.sessions.r2; print('OK')"` → `OK`.
- `python -c "from mcp_gateway.sessions import SessionRegistry; import inspect; sig = inspect.signature(SessionRegistry.open); assert 'kind' in sig.parameters and sig.parameters['kind'].default == 'r2'; print('OK')"` → `OK`.
- `python -c "from mcp_gateway.sessions import SessionRegistry, R2Session, MAX_SESSIONS, SESSION_IDLE_S, REAPER_INTERVAL_S, R2_CMD_TIMEOUT_S, SESSION_OPEN_TIMEOUT_S, _DANGEROUS_R2_CMD_RE, check_dangerous_cmd, SessionCapReached, strip_ansi, truncate_for_response; print('OK')"` → `OK`.

## Backward-compat exercise

The plan's <output> field asks: "whether the `kind='r2'` backward-compat dispatch is exercised by any existing Phase 8 test." Verified YES — `tests/test_r2_sessions.py::sessions_with_open` calls `registry.open(case_dir=..., sample_sha256=..., sample_path=..., init_commands=None, open_timeout_s=15.0)` WITHOUT a `kind` kwarg. On hosts with r2 installed, this exercises the `if kind == "r2":` branch via the default. On this host the test correctly skips (no r2 binary), but the signature inspection test (`test_registry_open_accepts_kind_kwarg`) confirms the default is in place.

## Dataclass inheritance — no issue hit

The plan flagged a potential Python 3.11 dataclass-inheritance issue ("requires kw-only OR all-fields-with-defaults"). Resolution: BaseSession orders all defaulted fields at the tail (`command_count=0, closed=False, close_reason=None, kind="r2"`) and R2Session's added fields BOTH have defaults (`sample_sha256=""`, `sample_path=dataclasses.field(default_factory=Path)`). No `kw_only=True` needed; standard inheritance works on Python 3.12.

## Self-Check: PASSED

- `mcp-gateway/src/mcp_gateway/sessions/__init__.py` — FOUND
- `mcp-gateway/src/mcp_gateway/sessions/_base.py` — FOUND
- `mcp-gateway/src/mcp_gateway/sessions/r2.py` — FOUND
- `mcp-gateway/tests/test_sessions_package.py` — FOUND
- `mcp-gateway/src/mcp_gateway/sessions.py` — DELETED (confirmed via `[ ! -f ... ]`)
- Commit `b0138cb` (Task 1) — FOUND in git log
- Commit `c6b5b5b` (Task 2) — FOUND in git log

## Next Phase Readiness

- **Plan 02 (dynamic capability probe + env-gate)** can build on the new `sessions/_base.py` LEAF discipline; no further session-package changes needed.
- **Plan 03 (gdb session driver)** will add `sessions/gdb.py` next to `r2.py`, define `GdbSession(BaseSession)`, `_open_gdb(registry, ...)`, and `GDB_OPEN_TIMEOUT_S` / `GDB_CMD_TIMEOUT_S` env constants. The plan-03 work also extends `sessions/__init__.py` with three new re-exports.
- **Tool-count invariant** (`test_tool_list.py::test_tool_count_in_range`) unchanged — still 54 gateway-native tools (no MCP surface added by this refactor).

---
*Phase: 11-dynamic-lab-mode-env-gated*
*Completed: 2026-05-20*
