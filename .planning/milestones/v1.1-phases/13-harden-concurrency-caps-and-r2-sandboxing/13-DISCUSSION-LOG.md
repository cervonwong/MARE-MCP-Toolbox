# Phase 13: Harden concurrency caps and r2 sandboxing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 13-harden-concurrency-caps-and-r2-sandboxing
**Areas discussed:** Reservation primitive, Jobs cap granularity, Sandbox + old filter, Unsafe r2 opt-in

---

## Pre-discussion routing

| Option | Description | Selected |
|--------|-------------|----------|
| Update it | Review and revise existing context | |
| View it | Show me what's already there before deciding | ✓ |
| Skip | Use the existing stub as-is and exit | |

**User's choice:** View it → after viewing, "Update with full discuss"

| Option | Description | Selected |
|--------|-------------|----------|
| Update with full discuss | Treat existing file as roadmap stub. Load prior context, scout codebase, identify gray areas, rewrite CONTEXT.md | ✓ |
| Just resolve the 3 open questions | Skip codebase scout — only ask about the three explicit open questions | |
| Skip | Use the existing stub as-is and exit | |

**User's choice:** Update with full discuss

**Notes:** Existing 13-CONTEXT.md was a roadmap stub (problem statement +
proposed direction + three explicit open questions), not a discuss-phase output.

---

## Gray-area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Reservation primitive | BoundedSemaphore vs Lock-across-spawn vs synthetic placeholder | ✓ |
| Jobs cap granularity | One global `_max_inflight` vs per-kind caps | ✓ |
| Sandbox + old filter | argv `-e cfg.sandbox=true …` vs init-batch vs hybrid; rip out regex vs keep | ✓ |
| Unsafe r2 opt-in | `unsafe=True` flag vs separate tool vs env-gated permission | ✓ |

**User's choice:** "choose the best answer for each of your questions" — delegated
all four to Claude's discretion.

**Notes:** User explicitly delegated all decisions. Claude presented a
six-decision recommendation block (D-01..D-06+ later expanded to D-01..D-12)
before locking, with the option to revisit any of three high-impact decisions
(reservation primitive, unsafe tool shape, sandbox grain).

---

## Reservation primitive (Track A core)

| Option | Description | Selected |
|--------|-------------|----------|
| `asyncio.BoundedSemaphore` | Acquire before spawn, release on failure/teardown. Stdlib canonical primitive. BoundedSemaphore raises on over-release | ✓ |
| `asyncio.Lock` held across spawn | Simpler but serializes opens — r2 init batch is several seconds, blocks legitimate concurrent agents | |
| Synthetic placeholder entry | Insert "reserving" entry into `_sessions`/`_inflight` under lock before spawn, replace or remove after | |

**User's choice:** BoundedSemaphore (per blanket delegation)
**Notes:** Recorded as D-01. Failure-cleanup contract (D-02) makes release
pair with spawn-outcome or close, not with registry shutdown. Cap-reject
contract (D-03) preserves existing `SessionCapReached.to_dict()` /
`JobCapReached.to_dict()` shapes — no queueing on the semaphore.

---

## Jobs cap granularity

| Option | Description | Selected |
|--------|-------------|----------|
| One global `_max_inflight` | Status quo. Single semaphore covers all job kinds | ✓ |
| Per-kind caps | capa, unblob, strace each independent — no kind starves another | |
| Hybrid: global + per-kind subcaps | Global N + per-kind floors/ceilings | |

**User's choice:** One global (per blanket delegation)
**Notes:** Recorded as D-06. Rationale: phase boundary is "harden", not
"redesign caps". Per-kind starvation has not been observed. If it becomes
measurable, that is a v1.2 phase. Stub Q2 explicitly asked this — answered.

---

## Sessions cap granularity (added by Claude during analysis)

| Option | Description | Selected |
|--------|-------------|----------|
| Stay combined (r2+gdb=8) | Phase 11 D-02 working assumption | ✓ |
| Split per-kind | Separate `MAX_R2_SESSIONS` and `MAX_GDB_SESSIONS` | |

**User's choice:** Stay combined (per blanket delegation)
**Notes:** Recorded as D-05. Semaphore replaces the racy counter; semantics
unchanged.

---

## Sandbox enforcement layer

| Option | Description | Selected |
|--------|-------------|----------|
| Argv `-e` flags | `r2 -2 -q0 -e cfg.sandbox=true -e cfg.sandbox.grain=disk,files,exec,io <sample>` — processed BEFORE binary open | ✓ |
| Init-batch lines | Add `e cfg.sandbox=true` etc. to the existing `scr.*` lockdown init batch | |
| Hybrid | Argv flags + redundant init-batch lines | |

**User's choice:** Argv flags (per blanket delegation)
**Notes:** Recorded as D-07. Argv `-e` processes BEFORE binary open, so the
sandbox is active before any open-time autoload hooks. Init-batch runs after
`-q0` opens the binary — too late. Argv is also visible in `ps` for audit.

---

## Sandbox grain selection

| Option | Description | Selected |
|--------|-------------|----------|
| `disk,files,exec,io` | r2's canonical "no escape" recipe — blocks writes, file open outside cwd, `!`-shell, IO redirection | ✓ |
| `disk,files,exec,io,socket` | Add socket block (not needed — no network in static analysis) | |
| Narrower (`exec,disk` only) | Minimal sandbox — risk of allowing IO redirection bypass | |

**User's choice:** `disk,files,exec,io` (per blanket delegation)
**Notes:** Recorded as D-08. Matches r2 upstream's recommended grain set
for sandboxed analysis.

---

## Old `_DANGEROUS_R2_CMD_RE` regex migration

| Option | Description | Selected |
|--------|-------------|----------|
| Rip out same commit | Clean removal — sandbox is the boundary, no point keeping a leaky proxy | |
| Keep one release as belt-and-suspenders | Then remove in v1.2 | |
| Keep permanently, frozen, reframed | Defense-in-depth UX layer; freeze at current shape; never extend | ✓ |

**User's choice:** Keep frozen, reframed (per blanket delegation)
**Notes:** Recorded as D-09. ~5 LOC, near-zero maintenance. Catches obvious
`!` / `R!` / `#!` cases with actionable error BEFORE bytes hit r2. **Critical
caveat encoded in the docstring:** "Sandbox is the security boundary. This
regex is an early-fail UX layer. Do not add new patterns — every addition
re-enters the parser arms race that motivated Phase 13." Stub Q3 explicitly
asked this — answered.

---

## Unsafe r2 opt-in surface

| Option | Description | Selected |
|--------|-------------|----------|
| `unsafe=True` flag on `open_r2_session` | Existing tool gets one more kwarg | |
| Separate tool `open_r2_session_unsafe`, env-gated registration | Registered iff `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1`. Mirrors Phase 11 DYN-01 pattern | ✓ |
| Env-gated permission only (kwarg + env) | Existing tool, `unsafe=True` only honored when env is set | |
| Drop unsafe entirely | No escape hatch in v1.1 | |

**User's choice:** Separate tool, env-gated (per blanket delegation)
**Notes:** Recorded as D-10 + D-11 + D-12. `tools/list` does not advertise
the capability unless env is set — auditable from outside the container.
WARN-level logging on every unsafe-open. Unsafe = `cfg.sandbox=false` (full
off — simpler than partial grain). Driver layer takes `sandbox: bool = True`
kwarg (D-12) instead of polluting the `kind` enum. Stub Q1 explicitly asked
this — answered.

---

## Final confirmation

| Option | Description | Selected |
|--------|-------------|----------|
| Lock all six and write | Persist D-01..D-06+ and write CONTEXT.md + this log | ✓ |
| Revisit D-01 reservation | Reconsider primitive choice | |
| Revisit D-06 unsafe tool | Reconsider tool-shape choice | |
| Revisit D-04 sandbox grain | Reconsider grain set | |

**User's choice:** Lock all six and write
**Notes:** Final decision matrix expanded to D-01..D-12 in CONTEXT.md to
cover sub-decisions (failure cleanup contract, cap-reject error shape,
list/count semantics, sandbox kwarg location, audit logging).

---

## Claude's Discretion

- Failure-cleanup test matrix (D-02): exact pytest ids/parametrize shapes
  during planning. Coverage requirement is locked
  (cancel/oserror/oom/idle/shutdown × sessions/jobs); harness layout is
  implementation detail.
- Exact log format for unsafe-open WARN line (D-11): structure left to
  planner. Field list (`session_id`, `sample_sha256[:8]`, `case_dir`) is
  locked; the f-string is not.
- Whether to keep `_DANGEROUS_R2_CMD_RE` exactly as-is or strip down to the
  three literal prefixes (D-09): planner picks. "Do not extend" rule is
  locked; current full-string scan vs. stripped form is a tactical call.
- Whether the BoundedSemaphore lives on `SessionRegistry` /
  `BackgroundJobRegistry` as a `self._sem` attr vs. a module-level
  singleton: planner picks. Attr is the obvious default; flag here in case
  planner finds a reason to differ.

## Deferred Ideas

- Per-kind job caps (capa/unblob/strace) — v1.2 if starvation becomes measurable
- Per-kind session caps (r2 vs gdb) — Phase 11 combined cap is working assumption
- gdb dangerous-command filter audit — different threat surface; not in scope
- Sandbox grain expansion to allow sockets — not needed for static analysis
- Audit log channel separate from gateway logs for unsafe-session opens —
  WARN-level logging in gateway log is sufficient for v1.1; structured audit
  feed is v1.2+
