# Phase 6: ReToolRunner + artifacts_io Foundation - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Land the chokepoint subprocess primitive (`ReToolRunner`) plus two small
pure helpers (`confine_to`, `ensure_subdir`) that every subsequent v1.1
RE-tool phase will sit on top of. No new MCP-visible tool surface in this
phase: the deliverables are internal in-process Python modules in
`mcp-gateway/src/mcp_gateway/` and their unit tests.

Scope:

- `runner.py::ReToolRunner` — argv-only subprocess execution with cwd
  pinned to a resolved `case_dir`, `start_new_session=True`, hard
  timeout, process-group SIGKILL on timeout or `CancelledError`,
  concurrent stdout/stderr drain with head buffer + file sink, ANSI
  strip + UTF-8-codepoint-boundary truncation, structured JSON return.
- `artifacts_io.py::confine_to(case_dir, path)` — canonical
  path-traversal-rejecting helper, importable by every path-accepting
  tool in v1.1.
- `artifacts_io.py::ensure_subdir(case_dir, name)` — lazy creation of
  the expanded case-dir subdir tree (`tool-logs/`, `extracted/`, `hex/`,
  `rop/`, `dynamic/`, `qemu/`, `disassembly/`, `decompilation/`,
  `xrefs/`); empty subdirs never proliferate.
- Unit tests, including the mandated 100 MB-of-`/dev/urandom` OOM-safety
  test and a `CancelledError`-propagates-to-`killpg` test asserting
  subprocess is dead within 200 ms of cancel.

Explicitly NOT in this phase:

- `tools/shell.py`, `tools/re_static.py`, any new MCP tool registration
  (Phase 7).
- `sessions/` package or session-scoped r2 / gdb (Phase 8).
- `jobs.py` / `BackgroundJobRegistry` (Phase 9).
- Extraction tools, dynamic mode, orchestrator-skill update (Phases
  10-12).
- Mount-namespace isolation, `mare-shell` UID, env scrub (Phase 7,
  where they actually pay off).
- Any change to v1.0's `subprocess_runner.run_script` — the two runners
  coexist by design (converge in v1.2 at the earliest).

</domain>

<decisions>
## Implementation Decisions

### Public API shape

- **D-01:** `ReToolRunner` is exposed as a **class** in `runner.py`. A
  caller constructs an instance with the per-call invariants (`case_dir`,
  default timeout, head-buffer sizes, slug) and then `await
  runner.run(argv)` returns the structured result dict. Class form is
  the primary API.

  *Rationale:* Phase 8 (sessions) and Phase 9 (jobs) need to hold the
  runner across multiple operations and probe its state during
  cancellation; a class encapsulates that without re-passing every
  invariant. Free-function-only would force kwarg sprawl in those
  phases.

- **D-02:** A thin module-level convenience helper `run_tool(case_dir,
  argv, *, slug, timeout=None, env=None, stdout_head_kb=None,
  stderr_head_kb=None) -> dict` is also exported from `runner.py`. It
  constructs a fresh `ReToolRunner` internally and awaits `run(argv)`.
  Phase 7's typed static wrappers — which fire and forget per call —
  use this; Phases 8/9 use the class directly.

  *Rationale:* Keeps the one-shot common case a one-liner while
  preserving the class for stateful callers. Mirrors the
  `anyio.run_process` / `anyio.open_process` pair.

- **D-03:** The structured return dict has these keys, in this order,
  and is locked for Phase 7+ to depend on:

  ```python
  {
      "exit_code": int,            # process returncode; -1 if not exited
      "timed_out": bool,           # true iff hard timeout fired
      "duration_s": float,         # wall-clock from spawn to exit/kill
      "stdout_head": str,          # head-buffered, ANSI-stripped, UTF-8-safe
      "stdout_truncated": bool,    # true iff stdout exceeded head cap
      "stdout_bytes_total": int,   # total bytes the child wrote to stdout
      "stderr_head": str,          # head-buffered, ANSI-stripped, UTF-8-safe
      "stderr_truncated": bool,
      "stderr_bytes_total": int,
      "log_path": str,             # case_dir-relative path to tool-logs/<…>.txt
      "argv": list[str],           # the argv as executed (for audit)
      "slug": str,                 # the caller-supplied slug
  }
  ```

  Tools in later phases layer their own keys on top of this dict
  (e.g., `run_capstone_disasm` adds `instructions: list[CsInsn]`); the
  base keys are never renamed or removed.

- **D-04:** `ReToolRunner.run()` **never raises** on subprocess exit
  state (non-zero exit, timeout, OOM, signal). It always returns the
  dict above; callers inspect `exit_code` / `timed_out`. The runner
  DOES raise on programmer errors before spawn: `FileNotFoundError`
  (argv[0] not on PATH), `ValueError` (empty argv, bad slug, case_dir
  fails confinement), `PermissionError` (cannot write the log file).
  `asyncio.CancelledError` from the caller is re-raised AFTER the
  subprocess has been SIGKILLed and `proc.wait()` has returned —
  shielded with `asyncio.shield(proc.wait())` so cancellation cleanup
  always finishes.

  *Rationale:* Returning a dict on every subprocess outcome is what
  lets Phase 7-11 MCP tools convert one runner result into one MCP
  response shape uniformly. Raising on pre-spawn programmer errors is
  fail-fast and matches `asyncio.create_subprocess_exec`'s own
  contract.

### Module layout

- **D-05:** Two flat modules live at the top of the package, alongside
  the existing `subprocess_runner.py`:

  ```
  mcp-gateway/src/mcp_gateway/runner.py        # ReToolRunner + run_tool
  mcp-gateway/src/mcp_gateway/artifacts_io.py  # confine_to, ensure_subdir, tool_log_path
  ```

  No new `re_runtime/` package, no nesting under `tools/`.

  *Rationale:* The research recommended `runner.py` + `artifacts_io.py`
  by name. The primitives total ~600 LoC; a package wrapper would be
  premature. Top-level placement makes `from mcp_gateway.runner import
  ReToolRunner` and `from mcp_gateway.artifacts_io import confine_to`
  unambiguous across `tools/*.py`, `sessions/*.py`, `jobs.py`.

- **D-06:** `confine_to` is **NOT** merged into
  `mcp_gateway/tools/case_dirs.py`. `case_dirs.resolve_case_dir`
  remains the case-dir specific guard (it knows about `STATUS_ROOT`).
  `confine_to` is a lower-level pure path helper that takes an
  already-resolved `case_dir` and any sub-path. Phase 7+ tools call
  `confine_to(resolve_case_dir(case_dir), user_path)`.

  *Rationale:* Layering. `case_dirs` lives under `tools/` and depends
  on `samples.STATUS_ROOT`; `artifacts_io` is a leaf module with no
  internal gateway dependencies. Mixing them creates an import cycle
  the moment `case_dirs` itself wants to canonicalize a user-supplied
  artifact path.

- **D-07:** `runner.py` MAY import from `artifacts_io` (`confine_to`,
  `ensure_subdir`, `tool_log_path`) but NOT vice versa. `artifacts_io`
  has zero gateway-internal dependencies.

### Config surface and log file naming

- **D-08:** Tunable defaults are read from env vars **once** at module
  import time of `runner.py`, exposed as module-level constants, and
  always per-call overridable via constructor / `run_tool` kwargs.
  Kwarg always wins; env var is only the default. Env names + defaults:

  | Env var                                  | Default | Purpose |
  |------------------------------------------|---------|---------|
  | `MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB`      | `256`   | Bytes of stdout returned in `stdout_head` |
  | `MCP_GATEWAY_RUNNER_STDERR_HEAD_KB`      | `64`    | Bytes of stderr returned in `stderr_head` |
  | `MCP_GATEWAY_RUNNER_DEFAULT_TIMEOUT_S`   | `55.0`  | Default hard timeout when caller omits; chosen to land below the MCP 60 s request cap with margin |
  | `MCP_GATEWAY_RUNNER_MAX_LOG_MB`          | `256`   | Per-invocation log file cap; over-cap kills the subprocess and sets `timed_out=False`, `exit_code=-9`, and a `truncated_log=true` marker (Phase 9 Jobs reuses this cap) |

  All four are sanity-checked at module import (non-negative integers
  / floats); bad values raise `RuntimeError` at gateway startup, never
  silently fall through. Same pattern as
  `uploads._max_bytes`.

- **D-09:** Tool log files are written under
  `case_dir/tool-logs/<timestamp>-<slug>-<rand4>.txt` with the exact
  format:

  - `<timestamp>` = `strftime("%Y%m%dT%H%M%SZ")` in UTC, e.g.
    `20260513T142301Z`. Compact ISO-basic, no colons, lexicographically
    sortable.
  - `<slug>` = caller-supplied required kwarg validated against the
    regex `^[a-z0-9][a-z0-9_-]{0,39}$`; auto-lowercased before
    validation. Auto-derivation from `argv[0]` is forbidden (argv[0]
    might be `env`, `bash`, `/agent/scripts/foo.sh` — too brittle).
  - `<rand4>` = `secrets.token_hex(2)` (4 lowercase hex chars).
    Guarantees uniqueness under same-second concurrent calls without
    nanosecond-suffix ugliness.

  Example final path: `case_dir/tool-logs/20260513T142301Z-run_shell-a3f7.txt`

  The full filename function `tool_log_path(case_dir, slug) -> Path`
  lives in `artifacts_io.py`, is what `ReToolRunner` calls internally,
  and is publicly importable so tests and Phase 9 jobs can construct
  identical paths.

- **D-10:** `log_path` in the runner's return dict is the path as a
  string, **relative to `case_dir`**, not absolute. Phase 7's
  `get_tool_log(case_dir, log_name, …)` tool takes the relative form;
  storing the relative form in the dict avoids leaking host paths
  through the MCP wire and keeps responses host-portable.

### `confine_to` semantics

- **D-11:** Signature: `confine_to(case_dir: str | os.PathLike, path:
  str | os.PathLike) -> Path`. Behavior:

  1. Resolve `case_dir` with `Path(case_dir).resolve(strict=True)` —
     must exist, must be a directory; else `ValueError`.
  2. If `path` is relative, join it onto `case_dir`. If absolute, use
     as-is.
  3. Resolve the joined path with `Path(...).resolve(strict=False)` —
     non-existing leaf is allowed (covers `write_artifact`,
     log-file-creation use cases). Intermediate symlinks are followed
     by `resolve`.
  4. Strict containment: the resolved target must equal `case_dir`
     OR have `case_dir` as a proper parent (use
     `target.is_relative_to(case_dir)` — Python 3.9+, container is
     3.11+). Reject with `ValueError(f"path escapes case_dir:
     {path!r}")` otherwise.
  5. Return the canonical resolved `Path` so the caller can use it
     directly without re-resolving.

- **D-12:** Symlinks **inside** `case_dir` whose target also lies
  inside `case_dir` are allowed (they resolve cleanly under the
  containment check). Symlinks whose target leaves `case_dir` are
  rejected by the realpath comparison in step 4 — no separate `lstat`
  walk needed.

  *Rationale:* `Path.resolve()` already follows symlinks to their
  final target; the containment check is performed on the resolved
  target, not on the link node. This matches the "canonicalize then
  compare prefix" pattern already used at
  `mcp_gateway/tools/artifacts.py:128-131`.

- **D-13:** `confine_to` raises `ValueError` on every rejection path
  (non-existing `case_dir`, traversal escape, NUL byte, etc.) so
  callers can `except ValueError` once. Never raises
  `FileNotFoundError` for the target — non-existing target is the
  legitimate write case.

- **D-14:** `confine_to` does NOT enforce that `case_dir` is under
  `STATUS_ROOT`; that is `resolve_case_dir`'s job. Phase 7+ tools
  invoke them composed: `resolve_case_dir(case_dir)` first, then
  `confine_to(resolved, user_path)`. Keeping the two checks separate
  lets `artifacts_io` be reusable by future code paths that operate
  outside `STATUS_ROOT` (e.g., the uploads dir during
  `promote_extracted_sample`).

### `ensure_subdir` semantics

- **D-15:** `ensure_subdir(case_dir: str | Path, name: str) -> Path`
  creates `case_dir/<name>` with `mkdir(parents=False,
  exist_ok=True)`, validates `name` against the same regex as the
  log-file slug (`^[a-z0-9][a-z0-9_-]{0,39}$`) so only sane subdir
  names are creatable, and returns the resolved Path. Idempotent and
  concurrency-safe (multiple async tasks calling for the same subdir
  race the `mkdir(exist_ok=True)` cleanly).

- **D-16:** A module-level constant
  `artifacts_io.EXPANDED_CASE_SUBDIRS` lists the nine canonical names
  from REQUIREMENTS.md ARTIF-01 (`tool-logs`, `extracted`, `hex`,
  `rop`, `dynamic`, `qemu`, `disassembly`, `decompilation`, `xrefs`)
  so Phase 7+ tools can refer to the same string set
  (`from mcp_gateway.artifacts_io import EXPANDED_CASE_SUBDIRS`) and
  the regression tests can iterate over it. Subdirs are created
  lazily — the constant is a *catalog*, not a "create-all-at-init"
  list.

### Process-group cleanup hardening

- **D-17:** On timeout or `CancelledError`, the runner runs this exact
  sequence (matches Pitfall 4 + Pitfall 18 mitigation in research):

  ```python
  try:
      os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
  except (ProcessLookupError, PermissionError):
      pass
  await asyncio.shield(proc.wait())
  ```

  `asyncio.shield` ensures that even if the runner's own awaiter is
  being cancelled, `proc.wait()` runs to completion so we never leave
  a `<defunct>` zombie or a `Future` warning. SIGTERM-then-SIGKILL is
  NOT used in this phase: the runner is for opaque RE tools where
  graceful shutdown has no defined meaning. Phase 9 (Jobs) will layer
  a SIGTERM grace period on top for user-cancel via
  `cancel_tool_job`.

- **D-18:** Follow-fork stragglers (`strace -f`, `qemu-user`
  multithread) are NOT scanned by Phase 6's runner — that scan
  (`/proc/<pid>/task/*/children`) belongs in the Dynamic Lab Mode
  phase (Phase 11) where follow-fork tools actually ship. Phase 6's
  runner kills the immediate pgroup only; the runner contract
  documents this so Phase 11 knows it owns the straggler-scan
  addition.

### Test design

- **D-19:** Tests live at `mcp-gateway/tests/test_runner.py` and
  `mcp-gateway/tests/test_artifacts_io.py`, following the existing
  pytest layout (18 v1.0 files + Phase 5's `test_image_hash.py`).

- **D-20:** Required test cases — every Success Criterion gets at
  least one assertion:

  - **SC-1 (chokepoint integrity):** runner spawns argv-only via
    `asyncio.create_subprocess_exec`; assertion grep on the runner
    source rejects `shell=True` (same pattern as
    `test_run_script_never_uses_shell_true`).
  - **SC-1 (cwd-confine):** runner CWD equals the resolved `case_dir`
    (subprocess prints `os.getcwd()`; tested against
    `Path(case_dir).resolve()`).
  - **SC-1 (timeout + pgroup SIGKILL):** spawn `sleep 60`,
    `timeout=0.5`, assert `timed_out=True`, `exit_code` reflects
    SIGKILL, `proc.returncode is not None` within 200 ms.
  - **SC-1 (cancel propagation):** wrap a long-running spawn in a
    task, cancel the task, assert subprocess is dead within 200 ms
    (the Pitfall 18 contract).
  - **SC-2 (return shape):** every key in D-03 present; types match;
    `argv` and `slug` echoed correctly.
  - **SC-3 (auto-capture):** stdout/stderr written to `tool-logs/`
    path returned in `log_path`; head-truncated preview in the dict
    matches the first N bytes of the file (with ANSI stripped).
  - **SC-4 (100 MB urandom):** spawn
    `bash -c "head -c 104857600 /dev/urandom"`; assert subprocess
    exits cleanly under a generous test timeout (60 s); assert
    runner RSS growth stays bounded (sample
    `resource.getrusage(RUSAGE_CHILDREN).ru_maxrss` before/after,
    delta < 32 MB — confirms head buffer + file sink, no full-buffer
    `communicate()`); assert `stdout_bytes_total == 104857600` and
    `stdout_truncated is True`.
  - **SC-5 (confine_to):** matrix test covering:
    `case_dir/foo.txt` (allowed, relative); `case_dir/sub/bar.txt`
    not-yet-existing (allowed); `case_dir/../../etc/passwd`
    (rejected); absolute path outside case_dir (rejected); symlink
    inside case_dir pointing inside (allowed); symlink inside
    case_dir pointing to `/etc/passwd` (rejected); NUL byte in
    `path` (rejected).
  - **D-09 log naming:** path format regex enforced; collision in
    the same second resolves via `rand4` suffix without overwriting.

- **D-21:** Tests are hermetic — they use `tmp_path` for case-dirs,
  never touch real `STATUS_ROOT`, and the 100 MB urandom test uses
  the `slow` pytest marker so it can be gated in CI if it ever
  becomes a flake (it shouldn't; bash + head + /dev/urandom is
  millisecond-deterministic).

### Claude's Discretion (within these constraints)

- Exact internal layout of the concurrent stream drainer
  (`anyio.create_task_group` vs `asyncio.gather` of two coroutines) —
  both are acceptable as long as PIPE deadlock is impossible.
- Whether `ensure_subdir` validates that the parent `case_dir` is
  itself under `STATUS_ROOT` — recommended NO (callers compose with
  `resolve_case_dir`), but planner may add it defensively if it
  doesn't bloat the API.
- ANSI-strip implementation: a stdlib regex
  (`re.compile(r"\x1b\[[0-9;]*[A-Za-z]")`) is preferred over a new
  dep; planner may pull in a tiny dep iff the regex misses a known
  RE-tool sequence (unlikely for `objdump`, `strings`, `xxd`).
- Whether the log file is opened once per call (recommended,
  `open(log_path, "ab", buffering=0)`) or written via a `Path.write_bytes`
  loop. Either is fine as long as partial writes are flushed before
  the runner returns.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase spec
- `.planning/ROADMAP.md` §"Phase 6: ReToolRunner + artifacts_io Foundation" — 5 success criteria
- `.planning/REQUIREMENTS.md` §Foundation — FOUND-02, FOUND-03, FOUND-04
- `.planning/PROJECT.md` §"Current Milestone: v1.1 Remote RE Tool Expansion" — Internal `ReToolRunner` bullet

### Research consensus (cross-document positions)
- `.planning/research/SUMMARY.md` §"Recommended Stack" — confirms argv-only `asyncio.create_subprocess_exec`, `start_new_session=True`, `os.killpg` + `asyncio.shield(proc.wait())`, concurrent stream drain pattern
- `.planning/research/SUMMARY.md` §"Phase 2: ReToolRunner + artifacts_io.py Foundation" — phase-level rationale and consumer mapping (Phases 7-11 layer over this)
- `.planning/research/SUMMARY.md` §"Critical Pitfalls" — top-five pitfalls this phase addresses (1 PIPE deadlock, 3 ANSI/slow-loris, 4 process-group cleanup, 12 head+log_path return, 17 tool-name convention, 18 FastMCP cancel propagation)
- `.planning/research/ARCHITECTURE.md` — full additive-changes diagram (no v1.0 file rewritten in Phase 6)
- `.planning/research/PITFALLS.md` §Pitfalls 1, 3, 4, 12, 18 — mitigation contracts the runner must implement
- `.planning/research/STACK.md` — confirms no new pip deps needed for this phase (all primitives are stdlib + `anyio` already pinned)
- `.planning/research/FEATURES.md` §"Must have" — ReToolRunner listed as second non-negotiable after F-1

### Code to modify or extend
- `mcp-gateway/src/mcp_gateway/subprocess_runner.py` — **do NOT modify**; reference implementation for `start_new_session=True` + `killpg(SIGKILL)` patterns the new runner mirrors
- `mcp-gateway/src/mcp_gateway/tools/case_dirs.py` — existing `resolve_case_dir`; composed with `confine_to` by Phase 7+ tools, not replaced
- `mcp-gateway/src/mcp_gateway/tools/artifacts.py:115-139` — existing canonicalize-and-compare-prefix pattern in `get_artifact` (the inline ancestor of `confine_to`)
- `mcp-gateway/src/mcp_gateway/uploads.py:31-66` — reference pattern for env-var-with-default + `_max_bytes`-style sanity check at module import (template for D-08 config knobs)

### Test pattern references
- `mcp-gateway/tests/test_subprocess_runner_shell_safety.py` (or equivalent grep-the-source test if filename differs — search for `test_run_script_never_uses_shell_true`) — the `shell=True`-rejection pattern that `test_runner.py` should mirror for SC-1 chokepoint integrity
- `mcp-gateway/tests/test_print_config.py` — established hermetic-subprocess test pattern
- `mcp-gateway/tests/test_image_hash.py` — Phase 5's hermetic test layout (clean env, `tmp_path` fixture, single fixture per test); same discipline applies here

### Constraint references
- `CLAUDE.md` §Constraints — the licensing rule (IDA/Binja zips not baked into images) is not directly relevant to Phase 6 but rules out any test that would require launching a real disassembler
- `.planning/STATE.md` §"v1.1 design decisions (newly added)" — top-level decision rows that this phase implements

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- **`mcp-gateway/src/mcp_gateway/subprocess_runner.py`** — the v1.0
  runner. Lines 52-67 show the exact `create_subprocess_exec` +
  `start_new_session=True` + `os.killpg(SIGKILL)` + `await proc.wait()`
  pattern. Copy the structure, then layer in stream-drain, head
  buffer + file sink, `asyncio.shield`, and the structured return
  dict. Do NOT modify `subprocess_runner.py` itself — it is the
  orchestrator-script runner and stays as-is.
- **`mcp-gateway/src/mcp_gateway/tools/artifacts.py:115-139`** — the
  inline canonicalize-and-compare-prefix path-traversal guard in
  `get_artifact`. This phase generalizes that into the standalone
  `confine_to`. The two surfaces should remain semantically
  equivalent after the refactor (a planner-discretion follow-up may
  rewrite `get_artifact` to call `confine_to`, but that's not
  required by Phase 6).
- **`mcp-gateway/src/mcp_gateway/tools/case_dirs.py`** —
  `resolve_case_dir` is the STATUS_ROOT-aware case-dir guard.
  `confine_to` deliberately does not duplicate this; the two compose.
- **`mcp-gateway/src/mcp_gateway/uploads.py:31-66`** — the
  env-var-with-default-and-startup-validation pattern (`_max_bytes`).
  This is the template for the four runner config knobs in D-08.

### Established patterns
- All v1.0 subprocess work uses `asyncio.create_subprocess_exec` with
  `start_new_session=True`; bash-style invocations are
  forbidden (regression tests grep the source for `shell=True`).
  Phase 6 inherits this.
- All v1.0 tests are pytest under `mcp-gateway/tests/`. Single
  fixture per test (Phase 5 confirmed this discipline). `tmp_path`
  is the standard hermetic-FS fixture.
- Env vars influencing runtime defaults are read once at module
  import and validated at startup (`uploads._max_bytes` model). The
  four runner knobs in D-08 follow the same pattern.
- `set -euo pipefail`-style strictness in bash scripts is the v1.0
  convention; Phase 6 introduces no new bash scripts.
- Module-level constants are UPPER_SNAKE; functions are
  lower_snake; classes are PascalCase. No deviations.

### Integration points
- After Phase 6, `runner.py` is the import target for every Phase 7
  tool module (`from mcp_gateway.runner import ReToolRunner` or
  `from mcp_gateway.runner import run_tool`). Phase 9 (jobs) will
  hold a `ReToolRunner` instance per job.
- `artifacts_io.confine_to` is the import target for every
  path-accepting tool in v1.1 — Phase 7's `write_artifact`,
  `append_artifact`, `get_tool_log`; Phase 10's
  `promote_extracted_sample`; Phase 11's dynamic-mode tools that
  resolve sample paths.
- `artifacts_io.ensure_subdir` is invoked lazily on first write by
  every tool that produces output in a tracked subdir; never at
  case-dir creation time. The `EXPANDED_CASE_SUBDIRS` constant is
  iterated in Phase 7's `get_artifact_tree` and in the
  regression test that asserts no empty subdirs leak into a
  freshly-created case-dir.
- No change to `app.py::lifespan` in this phase. Phase 8 adds the
  SessionRegistry block; Phase 9 adds the BackgroundJobRegistry
  block. Phase 6 has no runtime singletons.

</code_context>

<specifics>
## Specific Ideas

- User instruction at discuss-phase: "Choose the best and most
  robust architecture for me." All decisions above are Claude's
  recommended defaults under that mandate. The planner and executor
  may adjust *within* the constraints (Claude's Discretion bullets);
  the locked decisions (D-01..D-21) are the contract Phase 7+
  consumers will assume.
- Defense-in-depth philosophy carried forward from Phase 5: prefer
  the broader prune list, the explicit `LC_ALL=C` style choice —
  here it manifests as: explicit slug regex (not "anything goes"),
  explicit `rand4` collision suffix (not "trust the second"),
  explicit pre-spawn argument validation that raises (not silent
  defaults), four named env knobs (not magic numbers).
- The 55 s default timeout (D-08) is deliberately below the MCP 60 s
  request cap by 5 s so a timed-out tool always gets to return its
  head+log_path dict over MCP rather than the gateway losing the
  race. Phase 9 Jobs callers will override to a much larger value
  (or `None` for unbounded) because they're polled, not awaited.
- The `rand4` collision suffix uses 16 bits of entropy. At the
  contemplated invocation rate (handfuls per second, never
  thousands), birthday collisions are astronomically improbable
  within a single second; the suffix is correctness, not security.
- The `EXPANDED_CASE_SUBDIRS` catalog is intentionally an iterable
  constant rather than an enum so test files can do
  `for name in EXPANDED_CASE_SUBDIRS:
  assert not (case_dir / name).exists()` without enum-value
  ceremony.

</specifics>

<deferred>
## Deferred Ideas

- **Convergence of `subprocess_runner.run_script` and
  `ReToolRunner` into one runner** — already on the v1.2+ deferred
  list (see `.planning/REQUIREMENTS.md` §Future Requirements).
  Phase 6 explicitly does not touch the v1.0 runner; cosmetic
  deduplication is needless risk during a foundational phase.
- **Follow-fork straggler scan**
  (`/proc/<runner_pid>/task/*/children` for `strace -f` / qemu
  multithread) — belongs in Phase 11 (Dynamic Lab Mode) where
  follow-fork tools actually ship. Phase 6's runner contract
  documents that it kills the immediate pgroup only, so Phase 11
  knows it owns this addition.
- **SIGTERM-then-SIGKILL grace period** — Phase 6 uses SIGKILL only
  (opaque RE tools have no defined graceful-shutdown). Phase 9
  (Jobs) layers a SIGTERM grace period on top for user-driven
  cancellation via `cancel_tool_job`. Don't pre-implement here.
- **Per-`Mcp-Session-Id` keying** — already deferred to v1.2 at the
  milestone level; not Phase 6's concern (Phase 6 has no per-call
  state to key).
- **Mount-namespace isolation for the runner subprocess** — Phase 7
  scope (where `run_shell` is introduced) and even there explicitly
  deferred to v1.2. Phase 6's runner has no mount-namespace logic.
- **Per-call `tool-logs/<ts>-<slug>-<rand>.txt` rotation** — already
  on the v1.2+ deferred list. v1.1 caps per-job logs (Phase 9) but
  does not rotate per-call captures.
- **Adopting `confine_to` inside existing
  `tools/artifacts.py::get_artifact`** — semantically equivalent
  rewrite, no behavior change. Permitted but not required by
  Phase 6; if not done here, plan as a quick task during Phase 7.

</deferred>

---

*Phase: 06-retoolrunner-artifacts-io-foundation*
*Context gathered: 2026-05-13*
