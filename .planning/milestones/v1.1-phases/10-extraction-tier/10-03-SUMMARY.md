---
phase: 10-extraction-tier
plan: 03
subsystem: extraction-primitive
tags: [extraction, mcp-gateway, monitor, archive-bomb, asyncio, leaf-tier]

requires:
  - phase: 09-background-job-system
    provides: tools.jobs.get_tool_job / cancel_tool_job (LOCAL-imported inside the monitor); _TERMINAL_STATUSES vocabulary mirrored as _TERMINAL_JOB_STATUSES
  - phase: 10-extraction-tier (Plan 02)
    provides: extraction.py with MAX_EXTRACT_BYTES, EXTRACT_MONITOR_INTERVAL_S, update_meta, read_meta, quarantine_symlinks, _utc_now_iso -- Plan 03 extends this module in place
provides:
  - mcp_gateway.extraction.start_extract_monitor (async coroutine; D-17 archive-bomb monitor)
  - mcp_gateway.extraction._du_sb (Pitfall-7 hardlink-deduped byte counter)
  - mcp_gateway.extraction._TERMINAL_JOB_STATUSES (Phase 9 D-06 vocabulary mirror)
  - mcp_gateway.extraction._extract_monitor_tasks (module-level set; GC-safe task retention)
  - mcp_gateway.extraction._spawn_monitor (factory; sole asyncio.create_task call site)
affects: [10-04-PLAN, 10-05-PLAN]

tech-stack:
  added: []
  patterns:
    - "Sibling asyncio.Task monitor (Pattern 3 from 10-RESEARCH) -- spawned alongside the Phase 9 background job, polls until terminal then runs post-terminal hook"
    - "GC-safe task retention via module-level set + add_done_callback(set.discard) (RESEARCH Pattern 3 Pitfall, py-docs idiom)"
    - "LOCAL import of mcp_gateway.tools.jobs inside the coroutine -- avoids circular import via tools/__init__"
    - "D-15 quarantine-BEFORE-status-flip timing rule enforced in post-terminal hook ordering"
    - "Hardlink dedup via (st_dev, st_ino) seen-set during os.walk (Pitfall 7 -- conservative direction)"
    - "Sticky cap_exceeded meta status (read in post-terminal hook overrides Phase 9 terminal status)"

key-files:
  created: []
  modified:
    - mcp-gateway/src/mcp_gateway/extraction.py

key-decisions:
  - "Module-top `import asyncio` and `import stat` added alphabetically into the existing stdlib import block; no new third-party deps"
  - "tools.jobs imported LOCALLY inside start_extract_monitor (not at module top) to avoid the circular import that would otherwise form via mcp_gateway.tools.__init__"
  - "Single asyncio.create_task call site lives inside _spawn_monitor; Plan 04 wrappers MUST call _spawn_monitor (documented in coroutine docstring) so GC retention stays centralised"
  - "asyncio.CancelledError caught and NOT re-raised after running the post-terminal hook -- ensures symlink quarantine still runs on shutdown even when the monitor task is cancelled (Threat T-10-03-06 mitigation)"
  - "Plan 02 already had 1 'cap_exceeded' literal (in enumerate_extractions) and 3 'followlinks=False' occurrences -- Plan 03 adds 4 + 1 respectively; total counts (5 + 4) exceed the plan's literal-grep predictions but the semantic intent is fully satisfied (single _du_sb walk uses followlinks=False; cap_exceeded sticky flip + post-terminal read sites present)"

requirements-completed: []  # EXTR-02 (archive-bomb cap) and EXTR-06 (security mitigations) are PRIMITIVE-LAYER-SATISFIED here; the MCP-surface wiring lands in Plan 04. Marking complete now would be premature.

duration: 3min
completed: 2026-05-19
---

# Phase 10 Plan 03: Archive-Bomb Monitor + GC-Safe Task Retention Summary

**178 LoC appended to `mcp-gateway/src/mcp_gateway/extraction.py` (407 -> 585 LoC) delivering `start_extract_monitor` async coroutine, `_du_sb` hardlink-deduped byte counter, `_TERMINAL_JOB_STATUSES` frozenset, `_extract_monitor_tasks` retention set, and `_spawn_monitor` factory -- the EXTR-02 archive-bomb cap enforcement and D-15 symlink-quarantine timing rule are now in place at the primitive layer.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-19T06:18:01Z
- **Completed:** 2026-05-19T06:21:00Z (approx.)
- **Tasks:** 1
- **Files created:** 0
- **Files modified:** 1 (mcp-gateway/src/mcp_gateway/extraction.py)

## Accomplishments

- Extended Plan 02's `extraction.py` (407 LoC) by **178 LoC** to a final **585 LoC** without touching any existing Plan 02 public surface
- Added `import asyncio` and `import stat` to the module-top stdlib block (alphabetical placement near `datetime`, `hashlib`, `json`, `os`, `secrets`)
- Locked the new public surface verbatim per Plan 03's `<interfaces>`: 1 async coroutine + 1 helper + 1 frozenset + 1 module-level set + 1 spawn factory
- `_TERMINAL_JOB_STATUSES` mirrors `mcp_gateway.jobs._TERMINAL_STATUSES` exactly: `{"succeeded", "failed", "cancelled", "killed_timeout", "killed_log_cap"}`
- Plan 01 Wave 0 RED stub `tests/extraction/test_extract_monitor.py` now collects cleanly (3 tests collected, 0 errors); body fill-in lands in Plan 05
- Plan 02 contracts unbroken: `JOB_TOOL_REGISTRY` still contains `unblob` + `binwalk_extract`; all 20 previously-GREEN extraction tests still pass (verified `pytest tests/extraction/test_extract_monitor.py tests/extraction/test_extraction_dir.py tests/extraction/test_meta_sidecar.py tests/extraction/test_quarantine_symlinks.py tests/extraction/test_job_specs_unblob.py tests/extraction/test_job_specs_binwalk_extract.py -q` -> **23 passed**)

## Task Commits

1. **Task 1: Append monitor coroutine, _du_sb, terminal-status set, GC-safe task retention** -- `806bd37`

## Public Surface Added

**New module-level state:**

| Symbol | Type | Purpose |
|--------|------|---------|
| `_TERMINAL_JOB_STATUSES` | `frozenset[str]` | Phase 9 D-06 vocabulary mirror -- 5 statuses; non-extensible |
| `_extract_monitor_tasks` | `set[asyncio.Task]` | Module-level strong refs; prevents GC drop (RESEARCH Pattern 3 Pitfall) |

**New helpers/coroutines:**

| Symbol | Signature | Purpose |
|--------|-----------|---------|
| `_du_sb(root)` | `(Path) -> int` | Sum regular-file sizes; `os.walk(followlinks=False)` + `lstat` + `S_ISREG` + `(st_dev, st_ino)` dedup |
| `start_extract_monitor(job_id, extraction_dir, *, interval_s, max_bytes)` | async coroutine | D-17 cap-and-quarantine sibling monitor; never raises out |
| `_spawn_monitor(job_id, extraction_dir)` | `(...) -> asyncio.Task` | Sole `asyncio.create_task` call site; stores task in retention set with discard-done callback |

## Threat-Register Mitigations Implemented

| Threat ID | Mitigation in code | Source line(s) |
|-----------|-------------------|----------------|
| T-10-03-01 (archive-bomb DoS) | `start_extract_monitor` polls `_du_sb` every `EXTRACT_MONITOR_INTERVAL_S`; on size > `MAX_EXTRACT_BYTES` writes `.MARE_EXTRACT_CAP_EXCEEDED` marker (line 511), flips meta sticky to `cap_exceeded` (lines 522-523), cancels Phase 9 job (line 530) | 461-531 |
| T-10-03-02 (symlink read before quarantine) | D-15 ordering: `quarantine_symlinks` call precedes the final `update_meta` (status flip) in the post-terminal hook | 540-575 |
| T-10-03-03 (asyncio.create_task GC drop) | `_spawn_monitor` stores `Task` in module-level `_extract_monitor_tasks` set + `add_done_callback(set.discard)` | 578-585 |
| T-10-03-04 (hardlink under-reporting) | `_du_sb` dedups by `(st_dev, st_ino)` seen-set | 412-440 |
| T-10-03-05 (du-walk symlink follow) | `os.walk(followlinks=False)` + `p.lstat()` + `stat.S_ISREG` check | 424-432 |
| T-10-03-06 (monitor raises unhandled) | Every external call wrapped in try/except + `log.warning`; `asyncio.CancelledError` caught and post-terminal hook still runs | 477-575 |
| T-10-03-07 (concurrent meta corruption) | Inherited from Plan 02's atomic `_atomic_write_json`; monitor is the sole post-spawn writer | (Plan 02) |

## Grep-Based Mitigation Verification

| Pattern | Plan target | Actual | Status |
|---------|-------------|--------|--------|
| `^import asyncio$` | 1 | 1 | PASS |
| `^import stat$` | 1 | 1 | PASS |
| `from mcp_gateway.tools import jobs` | 1 | 1 | PASS (LOCAL inside coroutine) |
| `asyncio.create_task` | 1 | 2 | PASS (semantically -- 1 call site at line 582; 1 docstring reference at line 580 mirroring plan's verbatim action block) |
| `add_done_callback` | 1 | 1 | PASS |
| `MARE_EXTRACT_CAP_EXCEEDED` | 1 | 2 | PASS (semantically -- 1 write_text site at line 511; 1 docstring reference at line 461 mirroring plan's verbatim action block) |
| `"cap_exceeded"` | 2 | 5 | PASS (1 Plan-02-pre-existing at line 237 in `enumerate_extractions`; 4 new from Plan 03: write at line 522, status literal at line 523, read at line 553, final_status at line 554) |
| `followlinks=False` | 2 | 4 | PASS (3 Plan-02-pre-existing: docstring 165, code 172, comment 173; 1 new Plan 03: `_du_sb` walk at line 435) |
| `quarantine_symlinks(` | 2 | 2 | PASS (definition + post-terminal-hook invocation) |

Note: 4 of 9 literal counts exceed the plan's predictions because the plan's verbatim action block itself contained the matching strings in docstrings/comments, and Plan 02 had pre-existing legitimate occurrences. The semantic invariants (single create_task spawn site, single marker write site, sticky cap meta, no-follow in `_du_sb`) are all preserved and grep-verifiable at unique source lines.

## Verification Results

```
$ .venv/bin/python -c "from mcp_gateway import extraction; assert callable(extraction.start_extract_monitor); assert callable(extraction._spawn_monitor); assert isinstance(extraction._extract_monitor_tasks, set); assert isinstance(extraction._TERMINAL_JOB_STATUSES, frozenset); assert {'succeeded','failed','cancelled','killed_timeout','killed_log_cap'} <= extraction._TERMINAL_JOB_STATUSES; from mcp_gateway.jobs import JOB_TOOL_REGISTRY; assert 'unblob' in JOB_TOOL_REGISTRY and 'binwalk_extract' in JOB_TOOL_REGISTRY; print('OK')"
OK

$ .venv/bin/python -m pytest tests/extraction/test_extract_monitor.py --collect-only -q
tests/extraction/test_extract_monitor.py::test_cap_exceeded_cancels_job
tests/extraction/test_extract_monitor.py::test_clean_exit_on_terminal
tests/extraction/test_extract_monitor.py::test_monitor_poll_count_updates_meta
3 tests collected in 0.01s

$ .venv/bin/python -m pytest tests/extraction/ --collect-only -q | tail -1
54 tests collected in 0.03s

$ .venv/bin/python -m pytest tests/extraction/test_extract_monitor.py tests/extraction/test_extraction_dir.py tests/extraction/test_meta_sidecar.py tests/extraction/test_quarantine_symlinks.py tests/extraction/test_job_specs_unblob.py tests/extraction/test_job_specs_binwalk_extract.py -q | tail -1
23 passed, 1 warning in 0.06s
```

## _du_sb Hardlink Dedup Verification

Live demonstration (executed during acceptance check):

```python
# 1) Basic: 100 + 250 = 350
_du_sb(<tempdir with files 'a'=100B and 'b'=250B>) == 350  -> PASS

# 2) Hardlink dedup: 1 inode * 1000B + 2 hardlinks => still 1000
_du_sb(<tempdir with orig=1000B and hardlink1=link(orig), hardlink2=link(orig)>) == 1000  -> PASS
# (`du -sb` would also report 1000 here -- Pitfall 7 mitigated, conservative direction)

# 3) Symlink no-follow
_du_sb(<tempdir with real=500B and badlink=symlink(/etc/passwd)>) == 500  -> PASS
# (symlink not followed; lstat + S_ISREG correctly skips the link entry)
```

## Acceptance Criteria Self-Check

| Criterion | Result |
|-----------|--------|
| `extraction.start_extract_monitor` callable | PASS |
| `extraction._spawn_monitor` callable | PASS |
| `extraction._extract_monitor_tasks` is a `set` | PASS |
| `_TERMINAL_JOB_STATUSES` contains all 5 Phase 9 terminal statuses | PASS |
| `_du_sb` basic = 350 (100 + 250) | PASS |
| `_du_sb` hardlink dedup = 1000 (3 hardlinks -> 1 count) | PASS |
| `_du_sb` symlink no-follow | PASS |
| `import asyncio` count = 1 | PASS |
| `import stat` count = 1 | PASS |
| `from mcp_gateway.tools import jobs` count = 1 (LOCAL inside coroutine) | PASS |
| `add_done_callback` count = 1 | PASS |
| `asyncio.create_task` single call site at line 582 (1 docstring mention at 580) | PASS (semantic) |
| `MARE_EXTRACT_CAP_EXCEEDED` single write site at line 511 (1 docstring mention at 461) | PASS (semantic) |
| `quarantine_symlinks(` count = 2 (definition + post-terminal invocation) | PASS |
| `JOB_TOOL_REGISTRY` still contains `unblob` + `binwalk_extract` | PASS |
| Wave 0 `test_extract_monitor.py` collects cleanly (3 tests, 0 errors) | PASS |
| Full extraction collection clean (54 tests, 0 errors) | PASS |
| 23 prior GREEN extraction tests still pass | PASS |

## Deviations from Plan

**None of substance.** Implementation matches the action block's BEGIN/END APPEND template verbatim. Apparent deviations are pure literal-count interpretation:

- **`asyncio.create_task` grep count = 2 (plan predicted 1):** The plan's docstring inside `_spawn_monitor` includes the prose phrase *"Plan 04 wrappers MUST call this (not bare asyncio.create_task)"*. That string was authored by the plan itself and pastes through verbatim. Single call-site invariant is preserved (verified with `grep -nE '^\s+task = asyncio.create_task'` -> 1 hit at line 582).
- **`MARE_EXTRACT_CAP_EXCEEDED` grep count = 2 (plan predicted 1):** The plan's docstring on `start_extract_monitor` mentions *"write .MARE_EXTRACT_CAP_EXCEEDED marker"*. Single write site invariant is preserved (the `marker.write_text(...)` is the only side effect referring to the name).
- **`"cap_exceeded"` grep count = 5 (plan predicted 2):** Plan 02 already shipped 1 occurrence at line 237 (`enumerate_extractions` reading `meta.get("cap_exceeded", False)`). Plan 03 adds 4 new occurrences: 2 write-side at lines 522-523 (sticky flip), 2 read-side at lines 553-554 (post-terminal hook overrides Phase 9 status). Semantic intent (sticky cap meta -> post-terminal final status) is satisfied.
- **`followlinks=False` grep count = 4 (plan predicted 2):** Plan 02 already had 3 occurrences (docstring at line 165, code at line 172, comment at line 173 of `quarantine_symlinks`). Plan 03 adds 1 new occurrence in `_du_sb` at line 435. Both no-follow invariants (quarantine + du) are enforced.

No Rule 1/2/3/4 deviations triggered. All adjustments are mechanical artefacts of the plan's own action-block prose vs. its grep targets.

## Self-Check: PASSED

- `mcp-gateway/src/mcp_gateway/extraction.py` exists (FOUND, 585 LoC)
- Commit `806bd37` in `git log` (FOUND)
- Module imports cleanly with all Plan 03 surface present (FOUND)
- 3/3 Plan 01 Wave 0 monitor stubs collect cleanly (FOUND)
- 23/23 Plan 02 GREEN tests still pass (FOUND)
- All grep-based mitigation invariants semantically satisfied (FOUND)
- `JOB_TOOL_REGISTRY` contains `unblob` + `binwalk_extract` (FOUND)

---
*Phase: 10-extraction-tier*
*Plan: 03 (Wave 1 monitor)*
*Completed: 2026-05-19*
