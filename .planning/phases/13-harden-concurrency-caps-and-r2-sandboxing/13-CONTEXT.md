# Phase 13: Harden concurrency caps and r2 sandboxing - Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Two independent hardening tracks landing in one phase:

**Track A — Concurrency atomicity.** Replace the check-then-insert TOCTOU
pattern in cap enforcement with `asyncio.BoundedSemaphore` so two concurrent
callers can never both observe `count < cap` and both proceed past it.
Affects:

1. `SessionRegistry._open_r2` (sessions/r2.py:131-134 cap check, :220-222 insert)
2. `SessionRegistry._open_gdb` (sessions/gdb.py — same pattern, combined cap)
3. `BackgroundJobRegistry.submit` (jobs.py:549-554 cap check, :575-576 insert)

**Track B — r2 sandboxing.** Stop fighting r2's parser with regex blacklists.
Delegate enforcement to r2's native `cfg.sandbox` and add a separate
env-gated tool surface for callers that legitimately need writes or plugins.

**Explicitly NOT changed by this phase:**
- The combined r2+gdb session cap (`MCP_GATEWAY_MAX_SESSIONS=8`) stays combined
- The global job inflight cap stays one number (no per-kind caps)
- `gdb` MI-allowlist + `_DANGEROUS_GDB_RE` (different threat surface; not a parser arms race)
- Gateway authz/authn (Phase 2 territory; future v1.2+)
- `gdb` session lifecycle beyond cap enforcement
- New r2 features; only the safety boundary changes

</domain>

<decisions>
## Implementation Decisions

### Concurrency atomicity (Track A)

- **D-01:** **Reservation primitive = `asyncio.BoundedSemaphore`** sized to the
  cap. Acquire BEFORE spawn, release on spawn failure and on close. Apply to
  three sites:
  1. `SessionRegistry` — one `BoundedSemaphore(MAX_SESSIONS)` covering r2+gdb
     combined (matches Phase 11 D-02 combined-cap decision)
  2. `BackgroundJobRegistry` — one `BoundedSemaphore(_max_inflight)`

  Rationale: BoundedSemaphore (not plain Semaphore) raises `ValueError` on
  over-release, surfacing cleanup bugs at runtime in tests. Decouples the
  registry mutation lock from the cap counter, so two callers reserving slots
  do not block each other waiting for spawn. Lock-held-across-spawn was
  rejected — r2 init batch is several seconds, would serialize legitimate
  concurrent opens. Synthetic-placeholder pattern was rejected — semaphore
  is the canonical stdlib primitive for exactly this case.

- **D-02:** **Failure-cleanup contract for the reservation.** Strict
  acquire/release pairing — release happens at exactly two points:

  1. In an `except` block when spawn or registration fails (release the slot
     so the cap state reflects reality)
  2. In `close()` for the normal lifecycle (release the slot when the session
     or job terminates — `idle`/`shutdown`/`user`/`killed_*` all count as close)

  Release does **not** happen in `SessionRegistry.__aexit__` or registry
  teardown — the semaphore's lifetime tracks the registry's lifetime, and
  individual slot releases pair with spawn outcomes, not registry shutdown.
  Tests must cover: cancel-during-spawn, OSError-during-spawn, OOM-during-init,
  reaper-closes-idle, shutdown-closes-active.

- **D-03:** **Cap-reject error contract is preserved verbatim.** When the
  semaphore is at cap, raise the existing `SessionCapReached` / `JobCapReached`
  with the same `to_dict()` shape so the four-shape error contract (Phase 9
  D-15) and the SESS-04/JOBS-06 surfaces are unchanged for callers. The
  acquire is `await self._sem.acquire()` with a 0-second non-blocking probe
  via `if self._sem.locked()` — if the semaphore is at cap, raise immediately
  with the cap-error dict instead of blocking. **No queueing.**

- **D-04:** **`count_open()` and `list()` semantics unchanged.** These read
  from `self._sessions` / `self._inflight` (the dict), not from the
  semaphore's internal counter. The semaphore is the *gate*; the dict is the
  *truth*. Operators reading `list_sessions()` / `list_tool_jobs()` see the
  same shape as before.

- **D-05:** **Sessions cap stays combined (r2+gdb=8).** Phase 11 D-02
  established the combined cap; the semaphore replaces the racy counter
  without changing semantics. No per-kind session caps.

- **D-06:** **Jobs cap stays global.** Keep one `_max_inflight` semaphore.
  Per-kind caps (capa/unblob/strace separate) was rejected — phase boundary
  is "harden", not "redesign caps". If capa-vs-strace starvation becomes
  real, that is a v1.2 phase.

### r2 sandboxing (Track B)

- **D-07:** **Sandbox enforced via argv `-e` flags, not init-batch lines.**
  Update r2 spawn in `sessions/r2.py::_open_r2` from
  ```
  r2 -2 -q0 <sample>
  ```
  to
  ```
  r2 -2 -q0 -e cfg.sandbox=true -e cfg.sandbox.grain=disk,files,exec,io <sample>
  ```
  Rationale: r2 processes `-e` BEFORE opening the binary, so the sandbox is
  active before any binary metadata (e.g., autoload hooks) can execute.
  Init-batch lines (current location of `scr.interactive=false` etc.) run
  AFTER `-q0` opens the binary — too late for sandbox to protect open-time
  surface. Argv is also visible in `ps` and audit logs so operators can
  verify sandbox is on without running r2 commands.

- **D-08:** **Sandbox grain = `disk,files,exec,io`.** Matches r2's canonical
  "no escape" recipe per upstream docs. Blocks file writes, file open
  outside cwd, `!`-shell-escape exec, and r2's internal IO redirection.
  Sockets not enabled (no network in static analysis use case).

- **D-09:** **Old `_DANGEROUS_R2_CMD_RE` filter is kept, frozen, and
  reframed.** Do NOT delete sessions/r2.py:43-44. Do NOT extend it. Update
  docstring + module comment to make clear:
  > "Sandbox is the security boundary. This regex is an early-fail UX layer
  > that gives a clearer error than r2's sandbox-refused output for the
  > common `!` / `R!` / `#!` cases. Do not add new patterns — every addition
  > re-enters the parser arms race that motivated Phase 13."

  Rationale: ~5 LOC, near-zero maintenance, catches obvious mistakes with
  actionable error BEFORE bytes hit r2. Phase 8 defense-in-depth philosophy
  (D-08/D-09: full-string scan, not literal-first-char) is preserved.
  Removing it would lose the actionable error message; keeping it without
  reframing risks giving false confidence. Freezing it solves both.

- **D-10:** **Unsafe r2 opt-in = separate tool, env-gated registration.**
  New tool `open_r2_session_unsafe` registered iff
  `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1` at gateway startup. Mirrors Phase 11
  DYN-01 pattern. Unsafe session = `cfg.sandbox=false` (sandbox fully off),
  *plus* the argv stays otherwise identical (`-2 -q0`, lockdown init batch
  for `scr.*` still applied).

  Rationale: separate tool surface makes `tools/list` not advertise the
  capability unless explicitly enabled — auditable from outside the
  container. Easier to grep logs for `open_r2_session_unsafe` than to parse
  `unsafe=True` flag values. SKILL.md can pin "triage uses
  `open_r2_session`; only `open_r2_session_unsafe` when you legitimately
  need writes/plugins." A flag-on-existing-tool would have made audit
  harder (every `open_r2_session` call's args must be inspected).

  When `MCP_GATEWAY_R2_UNSAFE_ALLOWED` is unset/false, the tool is not
  registered and `tools/list` does not include it. Tool count: 54/61 today
  (dynamic off/on) → 54/61 + 1 when unsafe-allowed env is set.

- **D-11:** **Unsafe-session opens logged at WARN.** When
  `open_r2_session_unsafe` is invoked, the lifecycle log line is at
  `logging.WARN` (not INFO like normal opens). Includes
  `session_id`, `sample_sha256[:8]`, `case_dir`. Audit-trail-friendly:
  operators tailing logs see unsafe usage at the configured WARN visibility
  without inspecting every INFO line.

- **D-12:** **`SessionRegistry` distinguishes safe vs unsafe via the existing
  `kind` field is NOT extended.** Instead, the r2 driver takes a new
  `sandbox: bool = True` kwarg in `_open_r2`. `open_r2_session_unsafe`
  calls `registry.open(kind="r2", ..., sandbox=False)`. Avoids polluting
  the kind enum with a security-bit; keeps the kind axis (`r2`/`gdb`)
  orthogonal to the sandbox axis.

### Claude's Discretion

- Failure-cleanup test matrix (D-02): Claude picks the exact pytest
  ids/parametrize shapes during planning. Coverage requirement is locked
  (cancel/oserror/oom/idle/shutdown × sessions/jobs) but the harness layout
  is implementation detail.
- Exact log format for unsafe-open WARN line (D-11): structure left to
  planner. The fields list is locked; the f-string is not.
- Whether to keep `_DANGEROUS_R2_CMD_RE` exactly as-is or strip down to the
  three literal prefixes (`!`/`R!`/`#!`) (D-09): Claude picks. The "do not
  extend" rule is locked; whether the current full-string scan stays or
  simplifies is a tactical call.
- Whether the BoundedSemaphore lives on `SessionRegistry`/`BackgroundJobRegistry`
  as a `self._sem` attr vs. a module-level singleton: Claude picks. Attr is
  the obvious choice; flag here in case planner finds a reason to differ.

### Folded Todos

None — no pending todos matched this phase's scope.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### r2 sandbox semantics (Track B authority)

- `https://book.rada.re/configuration_variables/cfg.html` — r2 `cfg.sandbox`
  + `cfg.sandbox.grain` reference. Grain values: `none`, `disk`,
  `files`, `exec`, `io`, `disk-read`. `disk,files,exec,io` is the canonical
  "no escape" recipe.
- `r2 -h` output — confirms `-e key=val` is processed BEFORE binary open
  (researcher must verify with the container's r2 version)

### Prior-phase decisions to read (concurrency primitive context)

- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` §D-08, §D-09 —
  current `_DANGEROUS_R2_CMD_RE` rationale and per-command refusal contract.
  D-09 says "session lock held only briefly during regex check, before any
  bytes written to r2's stdin" — Phase 13 must preserve this property.
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` §D-18 —
  `SessionCapReached` error dict shape. **D-03 above** requires this dict
  shape unchanged.
- `.planning/phases/09-background-job-system/09-CONTEXT.md` §D-15 —
  four-shape error contract for jobs (tools never raise). Cap-reach goes
  through this contract.
- `.planning/phases/09-background-job-system/09-CONTEXT.md` §D-05 step 5 —
  current cap-check site in `BackgroundJobRegistry.submit`.
- `.planning/phases/11-dynamic-lab-mode-env-gated/11-CONTEXT.md` (DYN-01
  env-gated tool registration pattern) — **D-10 above** mirrors this for
  `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1`.

### Code locations the planner must touch

- `mcp-gateway/src/mcp_gateway/sessions/_base.py:163-257` — `SessionRegistry`
  class, `open()` dispatch, `count_open()`. Add `self._sem`.
- `mcp-gateway/src/mcp_gateway/sessions/r2.py:111-225` — `_open_r2` driver.
  Add sandbox argv flags (D-07). Add `sandbox: bool = True` kwarg (D-12).
  Reservation acquire+release wrapper.
- `mcp-gateway/src/mcp_gateway/sessions/r2.py:43-59` — frozen regex +
  reframed docstring (D-09).
- `mcp-gateway/src/mcp_gateway/sessions/gdb.py` — `_open_gdb` driver. Same
  reservation acquire+release pattern via shared `registry._sem`.
- `mcp-gateway/src/mcp_gateway/jobs.py:540-580` — `submit()` cap check +
  register. Add `self._sem`. Pair acquire with release at every terminal-
  state transition in `_spawn_and_drive` finalization.
- `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` — register
  `open_r2_session_unsafe` MCP tool iff env gate is set.

### Test-surface anchors

- `mcp-gateway/tests/` — existing tests for session cap and job cap. Phase
  13 must keep them GREEN unchanged (cap-reject error dict shape preserved)
  AND add concurrency atomicity tests (the new requirement).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`SessionRegistry._lock` + `count_open()`** (sessions/_base.py:182, :211) —
  Stays. The lock now protects dict mutation only; the semaphore protects
  the cap. Both are needed; they are orthogonal.
- **`SessionCapReached` / `JobCapReached` exception classes**
  (sessions/_base.py:138-153; jobs.py:200-218) — Stay verbatim. Their
  `to_dict()` payload is the public cap-reject contract per D-03.
- **`MCP_GATEWAY_MAX_SESSIONS` env var** (_base.py:71) — Continues to feed
  the cap size; just feeds `BoundedSemaphore(MAX_SESSIONS)` instead of
  `>=` comparison.
- **Phase 11 env-gated tool registration pattern** (DYN-01) — Direct
  template for D-10 `open_r2_session_unsafe`.

### Established Patterns

- **Argv-only subprocess spawn** (Phase 6 D-04 via `ReToolRunner`; carried
  to sessions/r2.py:144-151). Phase 13's sandbox argv flags extend the
  same argv list — no shell, no quoting concerns.
- **Env-gated optional features** (Phase 11 DYN-01) — Tool registered iff
  env=1, gateway logs the mode at startup. D-10/D-11 reuse this exactly.
- **Defense-in-depth retention** (Phase 6 D-11 `confine_to`; Phase 7 D-09
  whitelist-vs-blacklist; Phase 8 D-08 full-string scan) — D-09 freezes
  the regex rather than deleting it, in keeping with this lineage.

### Integration Points

- **Existing tool `open_r2_session`** — Add a `sandbox: bool = True` kwarg
  in the driver layer (D-12) but the MCP tool surface adds NO new arg.
  Tool always calls `_open_r2(..., sandbox=True)`. Backward compatible.
- **New tool `open_r2_session_unsafe`** — Same signature as
  `open_r2_session` (case_dir, sample, init_commands), calls
  `_open_r2(..., sandbox=False)`. Registered conditionally per D-10.
- **Reaper loop** (sessions/_base.py:342-361) — Closes idle sessions via
  `self.close()`. D-02 requires `close()` to release the semaphore, so
  the reaper continues to be the single sink for cap-slot release on
  idle.
- **Job `_spawn_and_drive` finalization** — Every terminal-state transition
  (`succeeded`/`failed`/`cancelled`/`killed_timeout`/`killed_log_cap`)
  must release the semaphore exactly once. The LRU eviction of completed
  jobs does NOT release the semaphore again (releases pair with terminal
  transition, not with dict eviction).

</code_context>

<specifics>
## Specific Ideas

- The user's framing in the stub is correct and adopted: "Replace
  check-then-insert with `asyncio.BoundedSemaphore`. Acquire before
  spawn, release on teardown (including failure paths). Collapses the
  race window to zero." D-01 + D-02 lock this in.
- The user's framing on r2 filter is also adopted: "Blacklisting r2
  syntax is a losing game because the parser keeps growing." D-09's
  "freeze, do not extend" rule encodes this directly into the
  contract — future agents reading this code will see the rule before
  they get any ideas.
- Pattern parity with `MCP_GATEWAY_DYNAMIC_TOOLS=1` (Phase 11) was the
  deciding factor for D-10's env-gated separate-tool shape: operators
  already understand this idiom from dynamic mode.

</specifics>

<deferred>
## Deferred Ideas

- **Per-kind job caps** (capa/unblob/strace separate) — Deferred to v1.2
  if starvation becomes measurable.
- **Per-kind session caps** (r2 separate from gdb) — Deferred; Phase 11
  combined cap is the working assumption.
- **gdb dangerous-command filter audit** — `_DANGEROUS_GDB_RE` works
  against a different threat surface (MI-mode-bound, allowlist-first,
  per Phase 11). Not in scope; revisit only if gdb similarly accumulates
  bypasses.
- **Sandbox grain expansion to allow sockets** — Not needed for the
  static-analysis use case. If a future tool ever needs sockets inside
  r2, this becomes a new gray area at that time.
- **Audit log channel separate from gateway logs** for unsafe-session
  opens — Deferred; WARN-level logging in the gateway log is sufficient
  for v1.1. Structured audit feed is v1.2+.

### Reviewed Todos (not folded)

None — no pending todos surfaced for this phase.

</deferred>

---

*Phase: 13-harden-concurrency-caps-and-r2-sandboxing*
*Context gathered: 2026-05-20*
