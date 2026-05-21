# Phase 13: Harden concurrency caps and r2 sandboxing — Research

**Researched:** 2026-05-20
**Domain:** asyncio concurrency primitives (BoundedSemaphore TOCTOU fix) + radare2 `cfg.sandbox` semantics + env-gated MCP tool registration
**Confidence:** HIGH on the asyncio + env-gated-registration tracks; HIGH on the r2 grain semantics with a **CRITICAL CORRECTION** to CONTEXT.md D-07/D-08 (grain values are an ALLOWLIST, not a blocklist — `disk,files,exec,io` as currently specified does NOT achieve "no escape")

## Summary

Two independent tracks land in one phase, each with very different risk profiles.

**Track A — Concurrency atomicity.** `asyncio.BoundedSemaphore` is the canonical stdlib primitive for cap enforcement. Python 3.11+'s asyncio.Semaphore was rewritten (post-bpo-90155) to be cancellation-safe — `await sem.acquire()` interrupted by `CancelledError` does not leak a slot — so the canonical try/except + explicit release pattern is correct. `sem.locked()` returns True iff the semaphore cannot be acquired immediately (i.e., the cap is reached), which is the exact non-blocking probe CONTEXT.md D-03 needs. `BoundedSemaphore.release()` raises `ValueError` on over-release, surfacing cleanup bugs at runtime — this is the intended safety property of D-01.

**Track B — r2 sandbox semantics.** A close read of radare2's source code reveals that **CONTEXT.md D-07's argv `-e cfg.sandbox.grain=disk,files,exec,io` does NOT achieve the intended "no escape" recipe.** The grain values are an ALLOWLIST (categories that REMAIN ENABLED when sandbox is on), not a blocklist. The current spec actually ALLOWS disk, files, and exec, and only blocks socket/network/environ/hidden. Additionally, `io` is not a valid grain value (the valid set is: `all`, `none`, `disk`, `files`, `exec`, `socket`, `network`, `environ`, `hidden`). **The correct "no escape" recipe is `cfg.sandbox.grain=none`** (block everything) — or, if r2 needs to read its own input file at all, the minimal grain required for that. The planner MUST raise this with the user before locking the spawn argv, because the security boundary that CONTEXT.md D-07/D-08 claim is not the boundary the proposed argv actually creates.

**Primary recommendation:** Plan Track A as written (D-01..D-06) — the primitive choice is correct. For Track B, **flag the grain-semantics mismatch as an Open Question** and let the discuss-phase loop resolve `grain=none` vs `grain=<minimal allowlist>` before any spawn-argv code is written. The env-gated `open_r2_session_unsafe` tool (D-10/D-12) and the frozen-regex reframing (D-09) are independent of the grain question and can plan as written.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Concurrency atomicity (Track A):**

- **D-01: Reservation primitive = `asyncio.BoundedSemaphore`** sized to the cap. Acquire BEFORE spawn, release on spawn failure and on close. Apply to three sites:
  1. `SessionRegistry` — one `BoundedSemaphore(MAX_SESSIONS)` covering r2+gdb combined (matches Phase 11 D-02 combined-cap decision)
  2. `BackgroundJobRegistry` — one `BoundedSemaphore(_max_inflight)`

  Rationale: BoundedSemaphore (not plain Semaphore) raises `ValueError` on over-release, surfacing cleanup bugs at runtime in tests. Decouples the registry mutation lock from the cap counter, so two callers reserving slots do not block each other waiting for spawn. Lock-held-across-spawn was rejected — r2 init batch is several seconds, would serialize legitimate concurrent opens. Synthetic-placeholder pattern was rejected — semaphore is the canonical stdlib primitive for exactly this case.

- **D-02: Failure-cleanup contract for the reservation.** Strict acquire/release pairing — release happens at exactly two points:
  1. In an `except` block when spawn or registration fails (release the slot so the cap state reflects reality)
  2. In `close()` for the normal lifecycle (release the slot when the session or job terminates — `idle`/`shutdown`/`user`/`killed_*` all count as close)

  Release does **not** happen in `SessionRegistry.__aexit__` or registry teardown — the semaphore's lifetime tracks the registry's lifetime, and individual slot releases pair with spawn outcomes, not registry shutdown. Tests must cover: cancel-during-spawn, OSError-during-spawn, OOM-during-init, reaper-closes-idle, shutdown-closes-active.

- **D-03: Cap-reject error contract is preserved verbatim.** When the semaphore is at cap, raise the existing `SessionCapReached` / `JobCapReached` with the same `to_dict()` shape so the four-shape error contract (Phase 9 D-15) and the SESS-04/JOBS-06 surfaces are unchanged for callers. The acquire is `await self._sem.acquire()` with a 0-second non-blocking probe via `if self._sem.locked()` — if the semaphore is at cap, raise immediately with the cap-error dict instead of blocking. **No queueing.**

- **D-04: `count_open()` and `list()` semantics unchanged.** These read from `self._sessions` / `self._inflight` (the dict), not from the semaphore's internal counter. The semaphore is the *gate*; the dict is the *truth*. Operators reading `list_sessions()` / `list_tool_jobs()` see the same shape as before.

- **D-05: Sessions cap stays combined (r2+gdb=8).** Phase 11 D-02 established the combined cap; the semaphore replaces the racy counter without changing semantics. No per-kind session caps.

- **D-06: Jobs cap stays global.** Keep one `_max_inflight` semaphore. Per-kind caps (capa/unblob/strace separate) was rejected — phase boundary is "harden", not "redesign caps".

**r2 sandboxing (Track B):**

- **D-07: Sandbox enforced via argv `-e` flags, not init-batch lines.** Update r2 spawn from `r2 -2 -q0 <sample>` to `r2 -2 -q0 -e cfg.sandbox=true -e cfg.sandbox.grain=disk,files,exec,io <sample>`. (**See Pitfall 1 below — `grain=disk,files,exec,io` does NOT mean what CONTEXT.md says it means. Planner MUST resolve before locking argv.**)

- **D-08: Sandbox grain = `disk,files,exec,io`.** CONTEXT.md claims this matches r2's canonical "no escape" recipe. **Research finding contradicts this** — see Pitfall 1.

- **D-09: Old `_DANGEROUS_R2_CMD_RE` filter is kept, frozen, and reframed.** Do NOT delete sessions/r2.py:43-44. Do NOT extend it. Update docstring + module comment to reframe the regex as a UX layer over the sandbox security boundary.

- **D-10: Unsafe r2 opt-in = separate tool, env-gated registration.** New tool `open_r2_session_unsafe` registered iff `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1` at gateway startup. Mirrors Phase 11 DYN-01 pattern. Unsafe session = `cfg.sandbox=false` (sandbox fully off), argv otherwise identical.

- **D-11: Unsafe-session opens logged at WARN.** Lifecycle log line at `logging.WARN` (not INFO). Includes `session_id`, `sample_sha256[:8]`, `case_dir`.

- **D-12: `SessionRegistry` distinguishes safe vs unsafe via a new `sandbox: bool = True` kwarg in `_open_r2`.** Avoids polluting the `kind` enum with a security-bit. `open_r2_session_unsafe` calls with `sandbox=False`; existing `open_r2_session` always calls with `sandbox=True`.

### Claude's Discretion

- Failure-cleanup test matrix (D-02): pytest ids/parametrize shapes are Claude's call. Coverage requirement is locked (cancel/oserror/oom/idle/shutdown × sessions/jobs) but the harness layout is implementation detail.
- Exact log format for unsafe-open WARN line (D-11): structure left to planner. Field list is locked; the f-string is not.
- Whether to keep `_DANGEROUS_R2_CMD_RE` exactly as-is or strip down to the three literal prefixes (D-09): Claude picks. The "do not extend" rule is locked.
- Whether the BoundedSemaphore lives on `SessionRegistry`/`BackgroundJobRegistry` as a `self._sem` attr vs. a module-level singleton: Claude picks. Attr is the obvious choice.

### Deferred Ideas (OUT OF SCOPE)

- **Per-kind job caps** (capa/unblob/strace separate) — Deferred to v1.2.
- **Per-kind session caps** (r2 separate from gdb) — Deferred; combined cap is the working assumption.
- **gdb dangerous-command filter audit** — `_DANGEROUS_GDB_RE` works against a different threat surface; not in scope.
- **Sandbox grain expansion to allow sockets** — Not needed for static-analysis use case.
- **Audit log channel separate from gateway logs** for unsafe-session opens — Deferred to v1.2+.
</user_constraints>

<phase_requirements>
## Phase Requirements

Phase 13 has no requirement IDs in REQUIREMENTS.md (TBD per ROADMAP.md Phase 13 entry). The phase is a hardening-only follow-on to v1.1 Phases 8, 9, 11; its acceptance is driven entirely by CONTEXT.md decisions D-01..D-12. Suggested requirement IDs the planner may propose to the user during plan-check:

| Proposed ID | Description | Research Support |
|-------------|-------------|------------------|
| HARDEN-01 | Cap-enforcement is atomic across concurrent callers (no TOCTOU) — `SessionRegistry` r2+gdb | Standard Stack: `asyncio.BoundedSemaphore` (Python 3.11+ cancellation-safe); Code Examples §1 |
| HARDEN-02 | Cap-enforcement is atomic across concurrent callers — `BackgroundJobRegistry.submit` | Same as HARDEN-01, applied to `jobs.py:549-554` |
| HARDEN-03 | r2 spawn is sandboxed at argv-eval time (BEFORE binary open) via `cfg.sandbox=true` | r2 source (`cb_cfgsanbox`); argv `-e` ordering verified |
| HARDEN-04 | r2 sandbox grain is the minimal allowlist for static-analysis use case (NO sockets, NO network, NO exec-helpers) | r2 source `R_SANDBOX_GUARD` macro + `cb_cfgsanbox_grain` parser — **grain semantics correction pending Open Question 1** |
| HARDEN-05 | `_DANGEROUS_R2_CMD_RE` is frozen with reframed docstring (security boundary clearly identified as sandbox, not regex) | CONTEXT.md D-09 |
| HARDEN-06 | `open_r2_session_unsafe` tool is registered iff `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1` at gateway startup; `tools/list` does not include it when unset | Phase 11 DYN-01 pattern (verified in `tools/__init__.py:64-74`) |
| HARDEN-07 | Cap-reject error dict shape (`SessionCapReached.to_dict()`, `JobCapReached.to_dict()`) is byte-identical to pre-Phase-13 | sessions/_base.py:147-153, jobs.py:205-211 — preserved verbatim |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Recommended Stack pins**: `mcp>=1.27,<1.28`; Python 3.11+; mcp-gateway 0.1.0 (in-process FastMCP gateway). Track A's `asyncio.BoundedSemaphore` is stdlib; no new pip deps. Track B's `-e cfg.sandbox=...` adds two argv tokens to an existing argv list; no new pip deps. Phase 13 introduces zero new project dependencies.
- **Security**: Container runs with elevated capabilities (SYS_PTRACE, seccomp=unconfined). r2 sandbox is in-process within the gateway's privilege boundary; it is the ONLY isolation between an analyst's r2 command and the host's filesystem/exec capabilities (the container does not give r2 a separate user/namespace). Reframing the regex as a UX layer (D-09) and switching to `cfg.sandbox` enforcement (D-07) move the security boundary from a parser arms race into r2's hardened C-level guards.
- **Transport / backward compatibility**: Phase 13 does not change MCP transport or `.mcp.json` shape. The only client-visible delta is +1 tool when `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1` (54→55 baseline, 61→62 with dynamic-mode also on).
- **GSD workflow enforcement**: All edits must go through a GSD command. Phase 13 is planned via `/gsd-plan-phase 13` after this research lands.
- **Licensing constraints**: IDA Pro / Binary Ninja licensing — unchanged by Phase 13 (this phase touches r2 only).

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `asyncio.BoundedSemaphore` (stdlib) | Python 3.11+ | Cap reservation primitive | The canonical stdlib primitive for "N concurrent users, fail if exceeded." Cancellation-safe since 3.10's rewrite (bpo-90155 / Python issue #90155); raises `ValueError` on over-release, surfacing cleanup bugs at runtime. `[VERIFIED: docs.python.org/3.11/library/asyncio-sync.html — "Bounded Semaphore is a version of Semaphore that raises a ValueError in release() if it increases the internal counter above the initial value"]` |
| `asyncio.Semaphore.locked()` (stdlib) | Python 3.11+ | Non-blocking cap probe | "Returns True if semaphore can not be acquired immediately." Exact match for CONTEXT.md D-03's "0-second non-blocking probe." `[VERIFIED: docs.python.org/3.11/library/asyncio-sync.html]` |
| radare2 `cfg.sandbox` | Container-bundled (Kali apt `radare2`) | In-process security boundary for r2 | r2's native sandbox guards: blocks `system()` calls, upper-directory file opens, and (with grain narrowing) socket/network/exec/disk operations at the libr-level. `[VERIFIED: github.com/radareorg/radare2 libr/util/sandbox.c R_SANDBOX_GUARD macro + libr/core/cconfig.c cb_cfgsanbox]` |
| `radare2` argv `-e key=val` | radare2 ≥ 5.0 | Pre-binary-open config eval | r2's command-line `-e` flag evaluates config vars at argv-parse time, BEFORE the positional binary argument is opened. Documented usage: `r2 -e scr.color=0 -e io.cache=true /bin/ls` — `io.cache` MUST be set before file open for cache to apply, proving the ordering. `[CITED: book.rada.re/first_steps/commandline_flags.html]` |
| Existing `tools/__init__.py` env-gate pattern | 0.1.0 | Conditional tool registration | Lines 71-74 are the verbatim template for D-10's `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1` gate. `[VERIFIED: codebase grep — mcp-gateway/src/mcp_gateway/tools/__init__.py:64-74]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `logging` (stdlib) | — | WARN-level unsafe-session log line (D-11) | Existing `log = logging.getLogger("mcp_gateway.sessions.r2")` at sessions/r2.py:34 — use `log.warning(...)` directly. No structured-log helper exists in the codebase. `[VERIFIED: grep "log\.\(info\|warning\|warn\)" mcp-gateway/src/mcp_gateway — all sites use plain logger methods]` |
| `pytest-asyncio>=0.23` | 0.23+ | Concurrency tests | Already in `pyproject.toml [project.optional-dependencies] dev`. `asyncio_mode = "auto"` in `pyproject.toml [tool.pytest.ini_options]` — no `@pytest.mark.asyncio` needed but commonly used for clarity. `[VERIFIED: mcp-gateway/pyproject.toml lines 22 + 32-34]` |
| `asyncio.gather(*tasks, return_exceptions=True)` (stdlib) | Python 3.11+ | Test idiom for N concurrent acquire callers | Pattern already used in `sessions/_base.py:206` (shutdown sweep) and `jobs.py:532-535` (shutdown cancel). Use the SAME idiom for "open 9 concurrent sessions against cap=8, exactly 1 must SessionCapReached." `[VERIFIED: codebase grep]` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asyncio.BoundedSemaphore` | Plain `asyncio.Semaphore` | Plain Semaphore silently accepts over-release. BoundedSemaphore raises ValueError on over-release — the noisy-on-cleanup-bug property D-01 calls out explicitly. The 1-line type change is the point. |
| `BoundedSemaphore` | `asyncio.Lock` held across spawn | Spawn (r2 takes 2-5s; gdb similar) would serialize legitimate concurrent opens. CONTEXT.md explicitly rejects this. |
| `BoundedSemaphore` | Synthetic-placeholder pattern (insert a `None` into the dict pre-spawn, replace on success, pop on failure) | Adds two dict mutations + a placeholder type to the registry surface for no benefit over the stdlib semaphore. CONTEXT.md D-01 rejects. |
| Argv `-e cfg.sandbox=true` | Init-batch line `e cfg.sandbox=true` after open | Init batch runs AFTER `-q0` opens the binary. Sandbox would not protect open-time surface (binary autoload hooks, format-handler plugin loads). CONTEXT.md D-07 correct rationale. |
| `grain=none` (proposed) | `grain=disk,files,exec,io` (CONTEXT.md D-08 current) | **Critical: see Pitfall 1.** Current value does NOT block disk/files/exec. Open Question 1 for the planner. |

**Installation:** No new packages. All primitives are stdlib + existing codebase patterns.

**Version verification:**

- `asyncio.BoundedSemaphore`: ships in CPython, no version pin needed beyond the existing `requires-python = ">=3.11"` in pyproject.toml. `[VERIFIED: cited above]`
- `radare2 cfg.sandbox`: shipped in r2 since the 2.x series (2018+); the grain bitmask field has been stable since 4.x. The Kali base image's `radare2` package (Dockerfile:46 `nasm radare2 ascii bsdextrautils`) provides r2 ≥ 5.x as of mid-2025. `[CITED: github.com/radareorg/radare2/blob/master/libr/include/r_util/r_sandbox.h — R_SANDBOX_GRAIN_* macros defined]` `[ASSUMED: exact r2 version in the running container — see Open Question 4]`

## Architecture Patterns

### Recommended Project Structure

No structural changes. Phase 13 edits 6 files in place:

```
mcp-gateway/src/mcp_gateway/
├── sessions/
│   ├── _base.py      # +self._sem: BoundedSemaphore in __init__; release in close()
│   ├── r2.py         # cap-check site (lines 131-134) → sem.locked() probe + acquire
│   │                 # spawn argv lines 144-151 → add 4 argv tokens
│   │                 # frozen regex docstring (lines 38-59)
│   │                 # add sandbox: bool = True kwarg to _open_r2
│   └── gdb.py        # cap-check site (lines 301-304) → same sem.locked() probe + acquire
├── jobs.py           # submit() cap-check (lines 549-554) → sem; +release in _mark_terminal
│                     # also release in _spawn_and_drive except blocks
└── tools/
    ├── r2_sessions.py    # +open_r2_session_unsafe handler (passes sandbox=False)
    └── __init__.py       # +env-gate block (mirror of dynamic-mode lines 64-74)
```

### Pattern 1: BoundedSemaphore acquire-before-spawn

**What:** Replace `if registry.count_open() >= registry._max: raise` with a semaphore probe + acquire BEFORE the long-running spawn.

**When to use:** Every site where a cap-counter is checked and then a dict is mutated, and the spawn between those two steps can yield to the event loop.

**Example:**

```python
# Source: synthesis of CONTEXT.md D-01..D-04 + sessions/_base.py:163-258 current shape
# In SessionRegistry.__init__:
self._sem: asyncio.BoundedSemaphore = asyncio.BoundedSemaphore(max_sessions)

# In sessions/r2.py::_open_r2 (replaces lines 131-134):
# D-03: probe first, raise the legacy error dict if at cap.
if registry._sem.locked():
    raise SessionCapReached(registry._max, registry.count_open(), registry.list())
await registry._sem.acquire()
try:
    # ... existing spawn + lockdown + register dict mutation ...
    async with registry._lock:
        registry._sessions[session_id] = sess
    return sess
except BaseException:
    # D-02: release the slot on ANY spawn / register failure path.
    registry._sem.release()
    raise

# In SessionRegistry.close(), AFTER killpg + proc.wait():
# D-02: release the slot exactly once on lifecycle teardown.
if not _slot_already_released:  # idempotency guard — see Pitfall 5
    registry._sem.release()
```

**Why `try/except BaseException` and not `try/except Exception`?** Because CONTEXT.md D-02 explicitly calls out `CancelledError` (which is a `BaseException` in Python 3.8+, NOT an `Exception`). The cancel-during-spawn test in CONTEXT.md is exactly this case — without `BaseException`, a cancelled spawn leaks a slot.

### Pattern 2: r2 argv with sandbox flags pre-binary

**What:** Insert sandbox `-e` flags BEFORE the positional sample path in the argv list.

**When to use:** Any `r2` subprocess spawn that should run sandboxed.

**Example:**

```python
# Source: synthesis of CONTEXT.md D-07 + r2 cmdline-flag docs
# Replaces sessions/r2.py:144-151 (current spawn call)
if sandbox:
    argv = [
        "r2", "-2", "-q0",
        "-e", "cfg.sandbox=true",
        "-e", f"cfg.sandbox.grain={SANDBOX_GRAIN}",  # see Open Question 1 for value
        str(sample_path),
    ]
else:
    # D-12: unsafe path — sandbox fully off; argv otherwise identical.
    argv = ["r2", "-2", "-q0", str(sample_path)]

proc = await asyncio.create_subprocess_exec(
    *argv,
    cwd=str(case_dir),
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    start_new_session=True,
)
```

**Why this order works:** r2's main parses argv left-to-right. The `-e` flags are processed via `r_config_eval` BEFORE `r_core_file_open` is called on the positional binary argument. This is the documented r2 idiom (`r2 -e io.cache=true /bin/ls` only works because `io.cache` is set pre-open). `[VERIFIED: book.rada.re/first_steps/commandline_flags.html, github.com/radareorg/radare2/blob/master/libr/core/cconfig.c cb_cfgsanbox]`

### Pattern 3: Env-gated tool registration (mirror of Phase 11 DYN-01)

**What:** Conditionally call `module.register(mcp)` only when an env var is set to `"1"`.

**When to use:** Optional tool surfaces that should NOT appear in `tools/list` unless explicitly enabled.

**Example (verbatim from `tools/__init__.py:64-74` — the template for D-10):**

```python
# Phase 11 D-DYN-IMPORT-01: env-gated conditional registration of dynamic-mode surface.
# When MCP_GATEWAY_DYNAMIC_TOOLS=1, tools/dynamic.py is imported (which transitively
# imports mcp_gateway.dynamic, registering 3 JobToolSpecs via register_job_tool at
# module import time). When unset, neither the 7 tools nor the 3 specs leak.
# Placed AFTER jobs.register/extract.register so dynamic JobToolSpecs enter a
# populated JOB_TOOL_REGISTRY, and BEFORE backend_passthrough so the merged
# tools/list handler sees the gateway-native surface first.
import os as _os
if _os.environ.get("MCP_GATEWAY_DYNAMIC_TOOLS") == "1":
    from . import dynamic as dynamic_tools
    dynamic_tools.register(mcp)
```

**Phase 13's mirror (D-10):** Add one block after the r2_sessions.register line (line 61) — or wherever the planner prefers, ordering does not matter for unsafe-r2 since it doesn't depend on Job specs:

```python
# Phase 13 D-10: env-gated unsafe-r2 tool registration.
# When MCP_GATEWAY_R2_UNSAFE_ALLOWED=1, open_r2_session_unsafe is registered.
# Unsafe tool calls _open_r2(sandbox=False); WARN-log on every open per D-11.
if _os.environ.get("MCP_GATEWAY_R2_UNSAFE_ALLOWED") == "1":
    from . import r2_sessions as _r2sess  # already imported above; re-imported for clarity
    _r2sess.register_unsafe(mcp)
```

The `register_unsafe(mcp)` function lives in `tools/r2_sessions.py`; the existing `register(mcp)` stays unchanged. This keeps the safe-vs-unsafe registration sites obviously distinct.

### Anti-Patterns to Avoid

- **`async with sem:`-only context-manager pattern for cap reservation.** Looks clean, but the cap-reject path needs to raise the `SessionCapReached`/`JobCapReached` dict-shaped error BEFORE blocking on acquire. `async with` blocks the caller until a slot frees — that violates D-03 "No queueing." Use the explicit `if locked(): raise; await acquire()` pattern instead.
- **Releasing the semaphore in `SessionRegistry.__aexit__`.** D-02 explicitly forbids this: the semaphore's lifetime tracks the registry's lifetime, and individual releases pair with spawn outcomes. Releasing every slot at __aexit__ would double-release on top of the per-close releases.
- **Hand-rolled cap-counter atomicity (e.g., `asyncio.Lock` held across spawn).** The reason to use a semaphore is precisely to decouple the lock from the spawn duration. Rejecting this is locked in D-01.
- **Adding new patterns to `_DANGEROUS_R2_CMD_RE`.** D-09 freezes this regex. Any new pattern is a sign that the sandbox is being treated as defense-in-depth — wrong direction. Sandbox is THE boundary; regex is UX.
- **Treating `grain=disk,files,exec,io` as the security recipe.** It is not — see Pitfall 1.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic cap check + increment under async concurrency | A custom counter + Lock + sleep loop | `asyncio.BoundedSemaphore` | Stdlib primitive, Python 3.11+ cancellation-safe, raises ValueError on over-release (free cleanup-bug detection). |
| r2-command sandboxing | Per-command regex blacklist (the current `_DANGEROUS_R2_CMD_RE`) | r2 native `cfg.sandbox` | Parser arms race. r2's `;`, `|`, `R!`, `#!`, future `@<addr>` syntax, custom escape modes — every new r2 release potentially adds a bypass. The C-level sandbox is enforced inside r2's libr at the syscall-wrapping layer (`r_sandbox_*`), beyond reach of command-syntax tricks. |
| Pre-binary-open sandbox setup | Init batch (`e cfg.sandbox=true\n`) after the prompt | Argv `-e cfg.sandbox=true <sample>` | Init batch runs AFTER binary open. Sandbox doesn't protect open-time surface (autoload, format plugins). Argv `-e` is processed before file open per r2's documented idiom. |
| Env-gated optional tool registration | A boolean kwarg `unsafe=True` on the existing tool | Separate tool `open_r2_session_unsafe` registered only when env=1 | Audit-friendliness — operators grepping logs for unsafe usage see the tool name, not a flag value. `tools/list` doesn't advertise the capability unless enabled. CONTEXT.md D-10 rationale. |

**Key insight:** Every "don't hand-roll" in this phase is about moving a security or correctness invariant from an application-level guess into a primitive that's been hardened by either CPython (semaphore) or radare2 itself (cfg.sandbox). Phase 13 is structurally about LESS gateway code holding the boundary, not more.

## Runtime State Inventory

Phase 13 is a refactor + small-feature-add phase, not a rename. Most categories are empty:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no datastore schemas change. The in-memory `_sessions` / `_inflight` dicts are recreated each gateway startup. `[VERIFIED: SessionRegistry.__init__ at sessions/_base.py:175-183, BackgroundJobRegistry.__init__ at jobs.py:506-518]` | None |
| Live service config | None — Phase 13 does not change any external service (no n8n, no Datadog, no tunnel names). | None |
| OS-registered state | None — no Task Scheduler / launchd / pm2 / systemd registrations changed. | None |
| Secrets / env vars | **New env var: `MCP_GATEWAY_R2_UNSAFE_ALLOWED`** — read once at gateway startup in `tools/__init__.py`. Default unset = unsafe tool NOT registered. No secret material; this is a feature gate, not a credential. | Document in README dynamic-mode section (alongside `MCP_GATEWAY_DYNAMIC_TOOLS`); add to compose.yaml env-passthrough list if container env is the surface. |
| Build artifacts / installed packages | None — no new pip deps; pyproject.toml unchanged. | None |

**Nothing found in category:** Stored data, live service config, OS-registered state, and build artifacts are all explicitly verified empty by codebase + CONTEXT.md inspection.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `r2` (radare2 CLI) | Test suite (existing) and runtime (existing); Phase 13 only changes its argv | ✗ on executor host | — | `_require_r2_or_skip` (already present at tests/conftest.py:11-17) skips r2-dependent tests on hosts without r2; container runs the real path |
| Python 3.11+ asyncio.BoundedSemaphore | Track A | ✓ | stdlib | — |
| pytest-asyncio | Track A concurrency tests | ✓ (declared in pyproject.toml dev extras) | ≥0.23 | — |
| `MCP_GATEWAY_R2_UNSAFE_ALLOWED` env var | Track B D-10 | n/a (gateway-defined) | — | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** `r2` on executor host — fallback is the existing skip-helper pattern. Tests must continue to use `_require_r2_or_skip()` for any test that exercises real r2 spawn. The pure-asyncio concurrency tests for Track A (which use `_sleep_probe` jobs or a mock spawn callable) do NOT need r2 and should run on every executor.

## Common Pitfalls

### Pitfall 1 (CRITICAL — open question for planner): `cfg.sandbox.grain` semantics are an ALLOWLIST, not a blocklist

**What goes wrong:** CONTEXT.md D-08 specifies `cfg.sandbox.grain=disk,files,exec,io` as r2's "no escape" recipe. Implemented as-is, this argv would ALLOW disk/files/exec operations and BLOCK only sockets, network, environ, and hidden-file access. Additionally, `io` is not a valid grain value — only `all`, `none`, `disk`, `files`, `exec`, `socket`, `network`, `environ`, `hidden` are recognized.

**Why it happens:** The grain string is parsed by `cb_cfgsanbox_grain` in `libr/core/cconfig.c` using `strstr(node->value, "<keyword>")` for each recognized keyword. The resulting bitmask is passed to `r_sandbox_grain(mask)` which sets `G_graintype = mask & R_SANDBOX_GRAIN_ALL`. The guard macro `R_SANDBOX_GUARD(x,y)` then checks `if (G_enabled && !(G_graintype & x)) return y` — operations are BLOCKED when the requested grain bit is NOT in the active mask. The bits enumerated in `libr/include/r_util/r_sandbox.h` are:

```c
#define R_SANDBOX_GRAIN_NONE (0)
#define R_SANDBOX_GRAIN_SOCKET (1)
#define R_SANDBOX_GRAIN_DISK (2)
#define R_SANDBOX_GRAIN_FILES (4)
#define R_SANDBOX_GRAIN_EXEC (8)
#define R_SANDBOX_GRAIN_ENVIRON (16)
#define R_SANDBOX_GRAIN_NETWORK (32)
#define R_SANDBOX_GRAIN_HIDDEN (64)
#define R_SANDBOX_GRAIN_ALL UT32_MAX
```

The r2 help message confirms the semantics verbatim:

> `e cfg.sandbox.grain=arg[,arg...]` — *select which sandbox permissions stay enabled*. `all = allow every sandbox grain`, `none = block every optional grain`, `disk = allow low-level file descriptors and file open operations`, `files = allow stdio-style file and directory access`, `exec = allow process execution and kill/system helpers`, `socket = allow socket creation`, `network = allow non-localhost network connections`, `environ = allow environment variable read/write`, `hidden = allow reading hidden files`.

`[VERIFIED: libr/util/sandbox.c, libr/include/r_util/r_sandbox.h, libr/core/cconfig.c — all fetched via raw.githubusercontent.com on 2026-05-20]`

**How to avoid:** The planner MUST resolve this with the user before locking the argv. Recommended replacement specs (Open Question 1 lists these):

- **Maximum-block (most paranoid):** `cfg.sandbox=true` with NO grain override (default grain = `all` = all categories allowed, BUT `cfg.sandbox=true` ALONE still blocks `r_sandbox_system` calls and `..` path traversal — the cfg.sandbox docstring says "disables systems and open on upper directories"). This means: with default grain, `cfg.sandbox=true` blocks the `!shell` escape path AND `..`-traversal, but allows file open of in-cwd files (necessary for the case-dir-bound sample analysis r2 is doing). This is probably the right "no escape for the static-analysis use case" recipe.
- **Explicit blocklist:** `cfg.sandbox.grain=none` blocks every optional grain (the strictest). Will likely break r2's ability to read its own input sample, because file open is gated by `R_SANDBOX_GRAIN_FILES`. Untested — may be too strict.
- **Targeted allow (most surgical):** `cfg.sandbox.grain=files,disk` (allow sample-reading; block exec, socket, network, environ). This MAY be the actual "no escape for r2 static analysis" recipe — needs in-container experimental verification.

**Warning signs:** If the test in CONTEXT.md (`!ls` returns r2's sandbox-refused message) PASSES with the current `grain=disk,files,exec,io` value, it would be passing for the wrong reason — `grain=...,exec,...` ALLOWS exec, so `!ls` should NOT be blocked by grain; it would only be blocked by the `cfg.sandbox=true` base sandbox's `r_sandbox_system` guard. The test must specifically prove that BOTH `cfg.sandbox=true` AND a grain that BLOCKS exec are needed. The current spec satisfies only the former.

### Pitfall 2: `await self._sem.acquire()` cancellation under Python < 3.10

**What goes wrong:** Pre-3.10 asyncio.Semaphore had a bug where cancelling a waiter that had been notified (slot was about to be theirs) leaked the slot. Subsequent acquirers would block forever even though no one was holding the slot.

**Why it happens:** The old implementation used a deque of futures; cancelling a future that had just been resolved didn't put the slot back into the pool.

**How to avoid:** Project pins `requires-python = ">=3.11"` so this bug is structurally avoided. Add a one-line invariant comment near the semaphore initializer: `# requires Python 3.10+ asyncio.Semaphore cancellation-safety (bpo-90155 fix)`. If you ever see `pyproject.toml` regress below 3.10, the comment surfaces the cost.

**Warning signs:** Cancel-during-spawn tests (D-02 mandates one) appearing to PASS on one Python and FAIL on another. Lock the version in tests; do not test only on the latest Python.

`[VERIFIED: github.com/python/cpython/issues/90155 — "asyncio.Semaphore waiters deque doesn't work", fix landed in 3.10]`

### Pitfall 3: Race between `_sem.locked()` check and `_sem.acquire()`

**What goes wrong:** Between `if self._sem.locked(): raise` and the next line `await self._sem.acquire()`, the event loop can yield. By the time `await` runs, another coroutine has acquired and the slot is gone — `acquire()` will block instead of raising.

**Why it happens:** `locked()` is a snapshot. There's no atomic "test-and-acquire-or-fail" primitive in asyncio.Semaphore.

**How to avoid:** **Acquire with a try/except + non-blocking check at the failure point.** The cleanest pattern is to call `acquire_nowait()` if it exists — it does not on stdlib semaphore. Two reasonable substitutes:

- **Probe-then-acquire under registry lock** (the lock that already exists at sessions/_base.py:182). Acquire the lock briefly: `async with registry._lock: if registry._sem.locked(): raise SessionCapReached(...); await registry._sem.acquire()`. The lock serializes the probe + acquire so the race is closed. The lock is held only across the `acquire()` call itself, which is instant when the semaphore has slots available (since locked() said so). This is essentially a 2-line atomic gate.
- **Try/except wait_for(acquire, timeout=0.0)** — `asyncio.wait_for(sem.acquire(), timeout=0.0)` raises `asyncio.TimeoutError` immediately if the cap is reached, without blocking. Translate the TimeoutError into `SessionCapReached`. This works but is more obscure than the lock pattern.

The first pattern matches the existing code shape (which already holds `registry._lock` around cap-check + insert at sessions/r2.py:131-134 and sessions/gdb.py:301-304). The diff is minimal.

**Warning signs:** Concurrency tests where two callers race the cap-reach boundary report inconsistent results (sometimes both succeed, sometimes one blocks instead of failing fast).

### Pitfall 4: Releasing the semaphore twice

**What goes wrong:** `BoundedSemaphore.release()` raises `ValueError` on over-release. Two paths could release the same slot: (a) spawn-failure except block releases, then close() is called on a partially-constructed session and tries to release again; (b) reaper closes an idle session, then `__aexit__` also tries to close.

**Why it happens:** The semaphore lifecycle has multiple branches; if any branch reaches close() after the slot is already released, ValueError surfaces.

**How to avoid:** Track release state on the session/job:

```python
# On BaseSession / Job, add a flag:
_slot_released: bool = False

# In SessionRegistry.close():
if not sess._slot_released:
    try:
        registry._sem.release()
        sess._slot_released = True
    except ValueError:
        log.exception("[sessions] semaphore over-release on close(%s)", session_id)
        sess._slot_released = True  # defensive — never retry
```

Or — cleaner — make the spawn-failure except block raise WITHOUT releasing, and have `close()` be the SOLE release point. This requires the failure-path to call `await self.close(sid)` (which already does killpg + waited cleanup) and then re-raise. CONTEXT.md D-02 says "release happens at exactly two points: spawn-failure except AND close()" — but ALSO says "release does not happen in __aexit__." So the two release sites are mutually exclusive in practice (a session is either born-then-closed OR spawn-failed-and-released-immediately, never both). The flag guards against accidental double-release if the code mutates.

**Warning signs:** Tests that simulate spawn failure followed by a close-call on the same session_id raise unexpected `ValueError`. Or shutdown tests trip ValueError when a reaper-closed-idle session also gets shutdown-closed by `__aexit__`'s gather.

### Pitfall 5: Reaper closing a session that was already closed (idempotent close() must not release twice)

**What goes wrong:** `SessionRegistry.close(sid)` is already idempotent — it returns `already_closed=True` if `sess.closed` is True. But under the new semaphore regime, the idempotent path MUST NOT release the slot again.

**Why it happens:** The current close() at sessions/_base.py:259-314 has TWO early-return paths: (a) `sess is None` at line 262-268, (b) `sess.closed` at line 269-278. Adding `registry._sem.release()` to close() without guarding these paths over-releases.

**How to avoid:** Put `registry._sem.release()` ONLY in the live-close branch (after line 282 `async with self._lock: sess.closed = True; sess.close_reason = reason`). The early-return idempotent branches must NOT touch the semaphore. The `_slot_released` flag from Pitfall 4 belt-and-braces this.

**Warning signs:** Test that calls `close(sid)` twice in quick succession (legitimate idempotency check from Phase 8 D-21) raises ValueError on the second call.

`[VERIFIED: codebase grep — sessions/_base.py::close is structured exactly as described; the two idempotent returns are at lines 262-268 and 269-278]`

### Pitfall 6: `_spawn_and_drive` finalization paths — enumerate before releasing

**What goes wrong:** `BackgroundJobRegistry.submit` acquires the semaphore. The drive task `_spawn_and_drive` runs and eventually transitions to a terminal status (succeeded / failed / cancelled / killed_timeout / killed_log_cap). Each terminal transition must release the slot exactly once.

**Enumerated terminal-state transition paths in `_spawn_and_drive` (jobs.py:623-687):**

1. **Drain completed naturally, cancel_requested set** → `job.status = "cancelled"` (line 672)
2. **Drain completed naturally, log_cap exceeded** → `job.status = "killed_log_cap"` (line 674)
3. **Drain completed naturally, exit code 0** → `job.status = "succeeded"` (line 676)
4. **Drain completed naturally, exit code nonzero** → `job.status = "failed"` (line 678)
5. **asyncio.TimeoutError caught at line 655** → `await self.cancel(job, reason="timeout"); job.status = "killed_timeout"; return` (lines 657-659)
6. **asyncio.CancelledError caught at line 660** → killpg + `job.status = "cancelled"; raise` (lines 661-668)
7. **Any other Exception caught at line 680** → `job.status = "failed"` (line 683)

All seven paths converge at the `finally:` block at line 684-687: `job.ended_at_*` set, then `await self._mark_terminal(job)`. **The cleanest single-release site is `_mark_terminal`** (jobs.py:689-720) — it runs unconditionally for every terminal transition. Add `self._sem.release()` at the END of `_mark_terminal` (after dict move + LRU eviction).

There is ONE additional release site: the `except` block in `submit()` itself, for the case where the cap check passes (semaphore acquired) but the `case_dir_path.resolve(strict=True)` / `ensure_subdir` / `tool_log_path` / `Job(...)` constructor raises before the drive task is created. In that path, `_spawn_and_drive` never runs, so `_mark_terminal` is never reached. The release must happen in `submit()`'s except block.

**How to avoid double-release:** Use the `_slot_released` flag on the Job dataclass (mirrors Pitfall 4 approach for sessions).

**Warning signs:** Long-soak tests where many jobs complete (any state) — after N+1 cycles where N = cap, the (N+1)th submit blocks indefinitely (slot leak: count drift) OR raises ValueError on release (over-release).

### Pitfall 7: Reaper iteration changes during shutdown sweep

**What goes wrong:** `SessionRegistry.__aexit__` (sessions/_base.py:193-209) calls `asyncio.gather(*[self.close(sid, reason="shutdown") for sid in open_ids])`. If the reaper was mid-iteration (cancelled but not yet awaited at the await asyncio.sleep), there's a tiny window where `close(sid)` could be called by both __aexit__ AND the reaper's most-recent stale_ids loop.

**Why it happens:** `__aexit__` cancels the reaper task FIRST (line 196-200) and awaits it before the shutdown sweep. This is correct — the reaper's CancelledError unwinds before any sweep close() runs. **The current code is already safe.** Listed here only to document why double-close from reaper+shutdown won't be a new Phase 13 problem.

**How to avoid:** Don't change `__aexit__`'s reaper-cancel-then-sweep ordering. The `_slot_released` flag still belt-and-braces it.

**Warning signs:** Shutdown tests log "[sessions] reaper failed to close" exceptions after the registry has exited. Not Phase 13-introduced if it happens.

### Pitfall 8: r2 init-batch lines that try to RE-ENABLE sandbox don't override argv `-e`

**What goes wrong:** The init batch at sessions/r2.py:155-161 sets `e scr.interactive=false; e scr.color=0; e scr.html=0; e cfg.user=mare`. A future agent might add `e cfg.sandbox=false` to the init batch thinking it gives them a workaround. They CANNOT undo the argv `-e cfg.sandbox=true` from inside the r2 prompt, because `r_sandbox_disable()` at libr/util/sandbox.c specifically guards against turning sandbox OFF once enabled (the `G_disabled = true` flag is a one-way latch).

**Why it happens:** r2 designs cfg.sandbox specifically as a one-way enable. The intent is exactly this — once on, never off in the same process.

**How to avoid:** No code change needed. Document in the reframed regex docstring: "cfg.sandbox=true is one-way; an init-batch line cannot turn it off. The only way to get a no-sandbox r2 session is to spawn a NEW process via open_r2_session_unsafe (D-10/D-12)."

**Warning signs:** Test that tries `r2_cmd(sid, "e cfg.sandbox=false")` expects sandbox-disabled behavior afterward. It won't get it — the cmd will silently no-op or emit an error message. Catch this in a positive-control test.

`[VERIFIED: libr/util/sandbox.c — r_sandbox_disable() returns the current state without altering G_enabled if G_disabled is already set]`

### Pitfall 9: WARN logging uses `log.warning(...)` not `log.warn(...)`

**What goes wrong:** Python's `logging.Logger.warn()` is deprecated and removed in some 3.13+ codepaths. Always use `logger.warning(...)`.

**How to avoid:** D-11 implementation uses `log.warning(...)` (matches the codebase idiom — see existing usage at sessions/_base.py:189 `log.info(...)`).

**Warning signs:** Newer Python versions emit `DeprecationWarning: The 'warn' function is deprecated, use 'warning' instead`.

### Pitfall 10: Test harness for "9 concurrent open_r2_session calls vs cap=8" must use real r2 OR a mock spawn

**What goes wrong:** A naive concurrency test for D-01 would call `await asyncio.gather(*[open_r2_session(...) for _ in range(9)])` — but real r2 takes 2-5 seconds to spawn + run lockdown, so the test takes 18+ seconds. Worse, on hosts without r2, it skips entirely and the cap behavior is never exercised in CI.

**How to avoid:** Two test layers:

1. **Primitive layer (no r2 required):** Test `SessionRegistry._sem` directly by injecting a fake `_open_<kind>` driver that just sleeps and registers a stub session. Drives 9 concurrent calls; asserts exactly 1 raises `SessionCapReached`. Pattern already used in tests/jobs/test_errors.py for the job cap test (uses `_sleep_probe` job spec).
2. **Integration layer (r2 required, slow):** Use `_require_r2_or_skip` and run 2-3 concurrent opens against cap=2 with the real r2 binary. Mark `@pytest.mark.slow` so CI fast-path skips.

The same pattern applies to jobs: use `_sleep_probe` (already registered, takes a `seconds` kwarg) for the primitive concurrency tests.

**Warning signs:** Test runtime balloons past 30s for the concurrency test file. If it does, the test is using real r2 where it shouldn't.

## Code Examples

### Example 1: BoundedSemaphore initialization on SessionRegistry

```python
# Source: synthesis of CONTEXT.md D-01 + sessions/_base.py:175-183 current shape
# Edit sessions/_base.py:175 (SessionRegistry.__init__):

def __init__(self, *, max_sessions: int, idle_s: float, reaper_interval_s: float):
    self._max = max_sessions
    self._idle_s = idle_s
    self._reaper_interval_s = reaper_interval_s
    self._sessions: dict[str, BaseSession] = {}
    self._lock = asyncio.Lock()
    self._reaper_task: Optional[asyncio.Task] = None
    # Phase 13 D-01: cap-enforcement primitive.
    # Requires Python 3.10+ asyncio.Semaphore cancellation-safety (bpo-90155 fix).
    # BoundedSemaphore raises ValueError on over-release — fails loud on cleanup bugs.
    self._sem: asyncio.BoundedSemaphore = asyncio.BoundedSemaphore(max_sessions)
```

### Example 2: Atomic cap-check + acquire in `_open_r2` (replaces lines 130-134)

```python
# Source: synthesis of CONTEXT.md D-01, D-02, D-03 + sessions/r2.py:130-134 + Pitfall 3 fix

# OLD (race-prone):
#   async with registry._lock:
#       if registry.count_open() >= registry._max:
#           raise SessionCapReached(...)
#       session_id = secrets.token_urlsafe(12)

# NEW (atomic — lock briefly bridges the probe-and-acquire pair):
async with registry._lock:
    if registry._sem.locked():
        raise SessionCapReached(registry._max, registry.count_open(), registry.list())
    await registry._sem.acquire()         # instantaneous: locked() said False
    session_id = secrets.token_urlsafe(12)

# Then wrap the rest of the spawn+register in try/except BaseException:
try:
    # ... ensure_subdir, transcript_path, sentinel, proc spawn, init batch,
    #     init_commands loop, registry._sessions insert ...
    return sess
except BaseException:
    # D-02: release on spawn-failure path. Catches CancelledError + Exception.
    registry._sem.release()
    sess._slot_released = True  # Pitfall 4 guard for the close() path
    raise
```

### Example 3: Release in close() — single-site idempotent

```python
# Source: synthesis of CONTEXT.md D-02 + sessions/_base.py:259-314 + Pitfall 5 fix
# Edit sessions/_base.py::close, AFTER line 282 (the "sess.closed = True" branch):

async def close(self, session_id: str, *, reason: str = "user") -> dict:
    sess = self._sessions.get(session_id)
    if sess is None:
        # Idempotent branch — DO NOT release the semaphore here.
        return {... "already_closed": True ...}
    if sess.closed:
        # Idempotent branch — DO NOT release here either (the original close did).
        return {... "already_closed": True ...}

    # Live-close branch — THIS is the single release point.
    async with self._lock:
        sess.closed = True
        sess.close_reason = reason

    try:
        os.killpg(sess.pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        await asyncio.shield(sess.proc.wait())
    except Exception:
        pass

    # ... transcript footer write ...

    # Phase 13 D-02: release the slot AT MOST ONCE per session lifecycle.
    if not getattr(sess, "_slot_released", False):
        try:
            self._sem.release()
            sess._slot_released = True
        except ValueError:
            # Defensive — log and stop, never retry (Pitfall 4).
            log.exception("[sessions] semaphore over-release on close(%s)", session_id)
            sess._slot_released = True
    return { ... }
```

### Example 4: r2 spawn argv with sandbox

```python
# Source: synthesis of CONTEXT.md D-07 + D-12 + Open Question 1 placeholder
# Edit sessions/r2.py::_open_r2 (lines 144-151).

# Module-level constant for the grain value — single source of truth.
# OPEN QUESTION 1: value below is a PLACEHOLDER; the planner must lock the final
# grain string with the user before any code lands. See Pitfall 1 for the rationale.
# Current proposal: empty string ("") means "do not pass cfg.sandbox.grain at all,
# rely on cfg.sandbox=true's default protection (no r_sandbox_system, no upper-dir
# file opens). This works for static-analysis r2 because sample-reading uses
# r_sandbox_open on an already-confined cwd."
SANDBOX_GRAIN_DEFAULT: str = ""  # OR "files,disk" if file read requires explicit allow

async def _open_r2(
    registry,
    *,
    case_dir: Path,
    sample_sha256: str,
    sample_path: Path,
    init_commands: Optional[list[str]],
    open_timeout_s: float,
    sandbox: bool = True,   # D-12: new kwarg; default True preserves Phase 8 callers
) -> R2Session:
    # ... existing dangerous-cmd check on init_commands ...
    # ... existing cap-check (now via Example 2 pattern) ...
    # ... existing transcript_path / sentinel setup ...

    # Phase 13 D-07: argv sandbox flags inserted BEFORE the positional sample.
    base_argv = ["r2", "-2", "-q0"]
    if sandbox:
        sandbox_argv = ["-e", "cfg.sandbox=true"]
        if SANDBOX_GRAIN_DEFAULT:
            sandbox_argv += ["-e", f"cfg.sandbox.grain={SANDBOX_GRAIN_DEFAULT}"]
    else:
        sandbox_argv = []
    argv = [*base_argv, *sandbox_argv, str(sample_path)]

    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(case_dir),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    # ... rest unchanged ...
```

### Example 5: `open_r2_session_unsafe` and env-gated registration

```python
# Source: synthesis of CONTEXT.md D-10 + D-11 + Phase 11 DYN-01 pattern
# (a) Add a new MCP handler in tools/r2_sessions.py:

async def open_r2_session_unsafe(
    case_dir: str,
    sample: str,
    *,
    init_commands: Optional[list[str]] = None,
    open_timeout: Optional[float] = None,
) -> dict:
    """Open an UNSANDBOXED r2 session (use only when writes/plugins are required).

    UNSAFE: r2's cfg.sandbox is DISABLED. r2 commands can run !shell escapes,
    open arbitrary files, exec processes, and write outside case_dir. Use the
    sandboxed `open_r2_session` for triage and analysis; only reach for this
    tool when you genuinely need r2 to write project files, load plugins, or
    run external scripts. Every open is logged at WARN.

    Registered iff `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1` at gateway startup.

    {_FULL_DISCLAIMER}
    """
    registry = _require_registry()
    resolved_case = Path(resolve_case_dir(case_dir))
    sample_path = Path(resolve_sample(sample))
    sample_sha = hashlib.sha256(sample_path.read_bytes()).hexdigest()

    for ic in (init_commands or []):
        check_dangerous_cmd(ic)  # D-09 frozen regex still runs as UX layer
    timeout = open_timeout if open_timeout is not None else sessions.SESSION_OPEN_TIMEOUT_S

    try:
        sess = await registry.open(
            case_dir=resolved_case,
            sample_sha256=sample_sha,
            sample_path=sample_path,
            init_commands=init_commands,
            open_timeout_s=timeout,
            sandbox=False,        # D-12: drives _open_r2 with sandbox=False
        )
    except SessionCapReached as e:
        return e.to_dict()

    # D-11: WARN-level audit log line.
    log.warning(
        "[r2_sessions] unsafe session opened: session_id=%s sample_sha256=%s case_dir=%s",
        sess.session_id, sample_sha[:8], str(sess.case_dir),
    )
    return {
        "session_id": sess.session_id,
        "case_dir": str(sess.case_dir),
        "sample_sha256": sess.sample_sha256,
        "sample_path": str(sess.sample_path),
        "transcript_path": str(sess.transcript_path.relative_to(sess.case_dir)),
        "opened_at": sess.opened_iso,
        "max_sessions": sessions.MAX_SESSIONS,
        "open_count": len(registry.list()),
        "init_command_count": len(init_commands or []),
        "warnings": ["r2 sandbox is DISABLED for this session"],
    }

# Splice disclaimer (matches r2_cmd / open_r2_session pattern).
open_r2_session_unsafe.__doc__ = (open_r2_session_unsafe.__doc__ or "").replace(
    "{_FULL_DISCLAIMER}", _SESS_05_DISCLAIMER_FULL
)


def register_unsafe(mcp: FastMCP) -> None:
    """Register the env-gated unsafe-r2 tool. Called iff MCP_GATEWAY_R2_UNSAFE_ALLOWED=1."""
    mcp.tool()(open_r2_session_unsafe)


# (b) Add the env-gate block in tools/__init__.py, AFTER r2_sessions.register(mcp) at line 61:

# Phase 13 D-10: env-gated unsafe-r2 tool. Default unset = tool NOT registered.
# tools/list does not include open_r2_session_unsafe unless this env is "1".
if _os.environ.get("MCP_GATEWAY_R2_UNSAFE_ALLOWED") == "1":
    r2_sessions.register_unsafe(mcp)
```

### Example 6: Job semaphore in `BackgroundJobRegistry`

```python
# Source: synthesis of CONTEXT.md D-01, D-02 + jobs.py:506-583 current shape
# Edit jobs.py::__init__:

def __init__(self, *, max_inflight: int, cancel_grace_s: float, max_completed: int):
    self._max_inflight = max_inflight
    self._cancel_grace_s = cancel_grace_s
    self._max_completed = max_completed
    self._inflight: dict[str, Job] = {}
    self._completed: "collections.OrderedDict[str, Job]" = collections.OrderedDict()
    self._lock: asyncio.Lock = asyncio.Lock()
    # Phase 13 D-01: cap-enforcement primitive (mirror of SessionRegistry).
    self._sem: asyncio.BoundedSemaphore = asyncio.BoundedSemaphore(max_inflight)

# Edit jobs.py::submit (lines 540-583):

async def submit(self, *, spec: JobToolSpec, kwargs: dict,
                 case_dir_resolved: str, effective_timeout_s: float) -> Job:
    """Register a new Job + start its drive task. Raises JobCapReached when cap hit."""
    async with self._lock:
        if self._sem.locked():
            raise JobCapReached(inflight=len(self._inflight), cap=self._max_inflight)
        await self._sem.acquire()
        job_id = secrets.token_hex(8)
        while job_id in self._inflight or job_id in self._completed:
            job_id = secrets.token_hex(8)
    try:
        case_dir_path = Path(case_dir_resolved)
        ensure_subdir(case_dir_path, "tool-logs")
        argv = spec.build_argv(case_dir_path, kwargs)
        log_abs = tool_log_path(case_dir_path, spec.slug)
        log_rel = str(log_abs.relative_to(case_dir_path))

        job = Job(...)  # unchanged constructor
        async with self._lock:
            self._inflight[job_id] = job
        job._drive_task = asyncio.create_task(self._spawn_and_drive(job), ...)
        return job
    except BaseException:
        # D-02: release on pre-spawn failure (constructor / Path resolve / ensure_subdir).
        self._sem.release()
        raise

# Edit jobs.py::_mark_terminal — single sink for all terminal-state transitions.
# Add release at the END, after dict move + LRU eviction:

async def _mark_terminal(self, job: Job) -> None:
    # ... existing post_terminal_hook + snapshot + json write ...
    async with self._lock:
        self._inflight.pop(job.job_id, None)
        self._completed[job.job_id] = job
        while len(self._completed) > self._max_completed:
            evicted_id, _ = self._completed.popitem(last=False)
            log.info("[jobs] FIFO-evicted completed job %s", evicted_id)
    # Phase 13 D-02: release the slot exactly once per job lifecycle.
    if not getattr(job, "_slot_released", False):
        try:
            self._sem.release()
            job._slot_released = True
        except ValueError:
            log.exception("[jobs] semaphore over-release on _mark_terminal(%s)", job.job_id)
            job._slot_released = True
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `if count >= cap: raise` + dict-mutate-later (TOCTOU race) | `BoundedSemaphore` acquire-before-spawn (atomic) | Phase 13 (this) | Two concurrent callers can no longer both observe `count < cap` and both proceed. Pure correctness fix; user-visible behavior identical when not in contention. |
| Regex blacklist as r2's primary security boundary | `cfg.sandbox=true` at r2 argv eval time | Phase 13 (this) | Boundary moves from a parser arms race into r2's libr-level guards. Regex stays as UX layer (clear error before bytes hit r2). |
| `asyncio.Semaphore` (pre-3.10) cancellation behavior | `asyncio.Semaphore` cancellation-safe (3.10+) | Python 3.10 (bpo-90155) | Project pin `requires-python>=3.11` already covers this. The cancellation race that motivated some "we can't use semaphore" arguments is fixed upstream. |
| `r2 -2 -q0 <sample>` direct spawn (no sandbox flags) | `r2 -2 -q0 -e cfg.sandbox=true [-e cfg.sandbox.grain=...] <sample>` | Phase 13 (this) | Sandbox now active BEFORE binary open (autoload hooks, format plugins protected). |

**Deprecated/outdated:**

- **`logging.Logger.warn(...)`** — deprecated since Python 3.4; removed from some 3.13+ codepaths. Use `logger.warning(...)`. Phase 13 D-11 already uses the correct name.
- **SSE-only MCP transport** — already addressed in v1.0 (CLAUDE.md). Phase 13 makes no transport changes.
- **`asyncio.Semaphore` cancellation pre-bpo-90155** — fixed in Python 3.10. The cancellation race that motivated some workaround patterns no longer applies.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The container's r2 version supports `cfg.sandbox.grain` (added in r2 4.x). The Kali base image's `radare2` package is ≥ 5.x as of mid-2025 | Standard Stack `radare2 cfg.sandbox` row | LOW — if grain is unsupported, the `-e cfg.sandbox.grain=...` line emits a warning and is ignored. The `cfg.sandbox=true` still applies. Phase 13 verification step should `r2 -V` inside the container as a Wave 0 probe. |
| A2 | r2 processes argv `-e` flags strictly before the positional binary argument (no exception for sandbox-specific flags) | Code Examples §4, Architecture Patterns §2 | LOW — documented r2 idiom, verified by `io.cache` ordering in r2 docs. If wrong, the sandbox would activate AFTER autoload — still better than init-batch, but the D-07 rationale weakens. |
| A3 | The combined-cap semantics of Phase 11 D-02 imply a single `BoundedSemaphore(MAX_SESSIONS)` on the registry covers BOTH r2 and gdb opens uniformly | Standard Stack + Code Example 1 | LOW — verified by reading sessions/_base.py:163-258: there's one `self._max`, one dict, kind dispatch happens inside `open()` so the cap-check is per-registry, not per-kind. |
| A4 | The `_slot_released` flag pattern (Pitfall 4) is acceptable to add as a new field on `BaseSession` and `Job` dataclasses | Code Examples 3 + 6 | LOW — dataclass field addition is backward-compatible. The field has a default `False`, so existing constructors keep working. |
| A5 | `_DANGEROUS_R2_CMD_RE` test coverage at tests/test_sessions.py + tests/test_r2_sessions.py is the complete inventory of tests that touch the regex | Existing Test Surfaces (below) | LOW — codebase grep matched only those two files; no other test file imports `_DANGEROUS_R2_CMD_RE` or `check_dangerous_cmd`. |

## Open Questions

1. **CRITICAL — `cfg.sandbox.grain` value (Pitfall 1).** CONTEXT.md D-08 says `disk,files,exec,io`, but r2 source code shows grain is an ALLOWLIST and `io` is not a valid value. The actual "no escape for static analysis" recipe is one of:

   - (a) `cfg.sandbox=true` with NO grain override — relies on r2's default `cfg.sandbox.grain=all` (all categories enabled) plus the base sandbox's `r_sandbox_system` and upper-dir-open blocks. Allows r2 to read its sample, blocks `!`shell escapes and `..` traversal.
   - (b) `cfg.sandbox.grain=files,disk` — explicitly allow sample-read + low-level FD access; block exec, socket, network, environ, hidden.
   - (c) `cfg.sandbox.grain=none` — block everything optional. May break sample-read; needs in-container verification.

   **Action:** Researcher recommends (a) for the static-analysis use case (fewer footguns, default-protective). Planner MUST raise as an Open Question in the plan-check loop. The fix is a 1-token edit at argv-build time; the cost of getting it wrong is "we shipped a phase claiming to harden, but the boundary is weaker than the regex it replaced."

2. **Slot release on idempotent close (Pitfall 5).** The `_slot_released` flag is the safe-for-future-edits implementation, but a stricter design (CONTEXT.md hints at "release pairs with spawn outcome, NOT with dict eviction") would put release entirely in the spawn-success path's eventual close-fired state machine. Either works; planner picks. Researcher recommends the flag — it's auditable and immune to future close() refactors.

3. **Pre-spawn failure path in `submit()` (Pitfall 6).** Between `await self._sem.acquire()` and `asyncio.create_task(_spawn_and_drive)`, four operations can fail: `Path(case_dir_resolved).resolve(strict=True)` (FileNotFoundError), `ensure_subdir` (PermissionError), `spec.build_argv` (could raise on bad kwargs — already validated upstream, but defense in depth), `tool_log_path` (OSError). The except-BaseException block releases the slot. Planner should add explicit unit tests for at least two of these synthetic failure injections.

4. **Container r2 version probe.** Phase 13 should include a Wave 0 test that runs `r2 -V` inside the container and asserts version ≥ 5.0 (or whatever minimum gives `cfg.sandbox.grain`). The test can be `@pytest.mark.skipif(not in_container)` — host CI executors skip it. This converts Assumption A1 into a verified invariant.

5. **WARN-log format for D-11.** The fields are locked (`session_id, sample_sha256[:8], case_dir`); the format string is not. Researcher recommends `log.warning("[r2_sessions] unsafe session opened: session_id=%s sample_sha256=%s case_dir=%s", ...)` — matches existing codebase idiom (sessions/_base.py:189 style). Planner can refine.

6. **Should `open_r2_session_unsafe` go through the SAME cap as `open_r2_session`?** D-05 says the cap is combined across r2+gdb. The unsafe path opens r2 just like the safe path. Researcher confirms YES — the unsafe tool's `registry.open(...)` call shares the same `self._sem`, so the cap is uniform. No new flag needed; falls out of D-12's plumbing.

## Environment Availability

(Reprinted from Step 2.6 above — single source of truth for the planner's env-availability table.)

## Validation Architecture

`workflow.nyquist_validation: true` is the default (config.json does not set it false). Including this section.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest>=8` + `pytest-asyncio>=0.23` (declared in pyproject.toml dev extras) |
| Config file | `mcp-gateway/pyproject.toml [tool.pytest.ini_options]` — `asyncio_mode = "auto"`, `testpaths = ["tests"]` |
| Quick run command | `cd mcp-gateway && pytest tests/test_sessions.py tests/test_r2_sessions.py tests/jobs/test_errors.py -x -m "not slow"` |
| Full suite command | `cd mcp-gateway && pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HARDEN-01 | Cap-atomic SessionRegistry (r2+gdb) — N concurrent callers, exactly 1 cap-rejected | concurrency unit | `pytest tests/test_sessions_concurrency.py -x -k "test_n_concurrent_opens_exactly_one_rejected"` | ❌ Wave 0 — new file |
| HARDEN-01 | Cancel-during-spawn releases the slot | concurrency unit | `pytest tests/test_sessions_concurrency.py -x -k "test_cancel_during_spawn_releases_slot"` | ❌ Wave 0 |
| HARDEN-01 | OSError-during-spawn releases the slot | concurrency unit | `pytest tests/test_sessions_concurrency.py -x -k "test_oserror_during_spawn_releases_slot"` | ❌ Wave 0 |
| HARDEN-01 | OOM-during-init releases the slot (mocked) | concurrency unit | `pytest tests/test_sessions_concurrency.py -x -k "test_oom_during_init_releases_slot"` | ❌ Wave 0 |
| HARDEN-01 | Reaper-closes-idle releases the slot | concurrency unit | `pytest tests/test_sessions_concurrency.py -x -k "test_reaper_idle_releases_slot"` | ❌ Wave 0 |
| HARDEN-01 | Shutdown-closes-active releases the slot (or registry exits without ValueError) | concurrency unit | `pytest tests/test_sessions_concurrency.py -x -k "test_shutdown_active_releases_or_clean_exit"` | ❌ Wave 0 |
| HARDEN-02 | Cap-atomic BackgroundJobRegistry — N concurrent submits, exactly 1 cap-rejected | concurrency unit | `pytest tests/jobs/test_concurrency.py -x -k "test_n_concurrent_submits_exactly_one_rejected"` | ❌ Wave 0 |
| HARDEN-02 | All 5 terminal-state transitions release exactly once | concurrency unit | `pytest tests/jobs/test_concurrency.py -x -k "test_terminal_transitions_release_exactly_once"` | ❌ Wave 0 |
| HARDEN-02 | Cancel-during-submit-pre-spawn releases the slot | concurrency unit | `pytest tests/jobs/test_concurrency.py -x -k "test_cancel_pre_spawn_releases"` | ❌ Wave 0 |
| HARDEN-03 | r2 spawn argv includes `-e cfg.sandbox=true` BEFORE `<sample>` | unit (argv-builder) | `pytest tests/test_r2_argv.py -x -k "test_argv_sandbox_flag_present_before_sample"` | ❌ Wave 0 |
| HARDEN-03 | r2 sandbox is active at binary open (positive control: `r2_cmd("!ls")` returns r2's sandbox-refused output, NOT the regex pre-filter output) | integration (requires r2) | `pytest tests/test_r2_sandbox_integration.py -x -k "test_sandbox_blocks_shellescape" -m "slow or not slow"` | ❌ Wave 0 — requires r2 in container |
| HARDEN-04 | grain value matches Open Question 1's locked decision | unit (argv-builder) | `pytest tests/test_r2_argv.py -x -k "test_argv_grain_value"` | ❌ Wave 0 — depends on OQ1 resolution |
| HARDEN-05 | `_DANGEROUS_R2_CMD_RE` is unchanged + docstring reframed | snapshot + grep | `pytest tests/test_sessions.py -x -k "test_dangerous_regex_frozen"` | ✅ existing test_sessions.py needs new test added |
| HARDEN-06 | `open_r2_session_unsafe` NOT in tools/list when env unset | env-gate unit | `pytest tests/test_tool_list.py -x -k "test_unsafe_r2_absent_baseline"` | ✅ existing file — extend parametrize |
| HARDEN-06 | `open_r2_session_unsafe` IS in tools/list when `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1` | env-gate unit | `pytest tests/test_tool_list.py -x -k "test_unsafe_r2_present_with_env"` | ✅ extend parametrize |
| HARDEN-06 | Unsafe-tool open emits WARN log line with required fields | log-capture | `pytest tests/test_r2_sessions.py -x -k "test_unsafe_open_warn_log"` | ❌ Wave 0 — extends existing file |
| HARDEN-07 | `SessionCapReached.to_dict()` shape byte-identical to pre-Phase-13 | snapshot | `pytest tests/test_sessions.py -x -k "test_session_cap_reached_dict_shape"` | ✅ existing test_cap_reject — add explicit shape-snapshot assertion |
| HARDEN-07 | `JobCapReached.to_dict()` shape byte-identical to pre-Phase-13 | snapshot | `pytest tests/jobs/test_errors.py -x -k "test_cap_reached_shape"` | ✅ existing — already asserts the dict shape; extend with byte-snapshot |

### Sampling Rate

- **Per task commit:** `pytest tests/test_sessions_concurrency.py tests/jobs/test_concurrency.py tests/test_r2_argv.py -x -m "not slow"` — runs in < 10 seconds, covers the primitive-layer concurrency contract.
- **Per wave merge:** `pytest tests/ -x -m "not slow"` — full non-slow suite (~120 tests, ~30 seconds).
- **Phase gate:** Full suite green (`pytest -x`) inside the container (where r2 is available for HARDEN-03 integration test); on the dev host, the integration test skips via `_require_r2_or_skip`.

### Wave 0 Gaps

- [ ] `mcp-gateway/tests/test_sessions_concurrency.py` — new file, covers HARDEN-01 (6 test cases: cap-atomic, cancel, oserror, oom-mock, reaper-idle, shutdown-active)
- [ ] `mcp-gateway/tests/jobs/test_concurrency.py` — new file, covers HARDEN-02 (3 test cases: cap-atomic via `_sleep_probe`, all-5-terminals release-exactly-once, cancel-pre-spawn)
- [ ] `mcp-gateway/tests/test_r2_argv.py` — new file, covers HARDEN-03 + HARDEN-04 argv-builder unit tests (no r2 spawn — string assertions only)
- [ ] `mcp-gateway/tests/test_r2_sandbox_integration.py` — new file, covers HARDEN-03 integration (`@pytest.mark.slow`; gated by `_require_r2_or_skip`)
- [ ] `mcp-gateway/tests/test_sessions.py` — extend with `test_dangerous_regex_frozen` (snapshot of `_DANGEROUS_R2_CMD_RE.pattern` against a frozen string) AND `test_session_cap_reached_dict_shape` (assert the exact dict keys + types of `SessionCapReached.to_dict()`)
- [ ] `mcp-gateway/tests/test_r2_sessions.py` — extend with `test_unsafe_open_warn_log` (uses `caplog` to capture WARN-level emission)
- [ ] `mcp-gateway/tests/test_tool_list.py` — extend `EXPECTED_TOOLS_BASELINE` (54) and `EXPECTED_TOOLS_DYNAMIC` (61) with a third parametrize axis: `MCP_GATEWAY_R2_UNSAFE_ALLOWED ∈ {None, "1"}`. Adds `open_r2_session_unsafe` to expected sets when env=1. Tool-count delta: +1 per unsafe-allowed.
- [ ] No new framework install needed — pytest + pytest-asyncio already declared.

## Security Domain

`security_enforcement` is not set false in config.json (security defaults to on).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Unchanged from CLAUDE.md "Recommended Stack > Authentication & Security": bearer token. Phase 13 adds no new authn surface. |
| V3 Session Management | yes | The new `MCP_GATEWAY_R2_UNSAFE_ALLOWED` env gate IS a session-scope control (audit-friendly registration toggle). Standard control: env-gate at startup, log enablement, document the boundary. Pattern matches Phase 11 DYN-01. |
| V4 Access Control | yes | Unsafe-r2 is a higher-privilege capability; the tool surface itself enforces "must be enabled" by being absent from `tools/list` when env is unset. Standard control: deny-by-default tool registration. |
| V5 Input Validation | yes (existing) | `check_dangerous_cmd` (frozen — D-09) and `validate_mi_command` (gdb side, untouched) — both already exist. Phase 13 does NOT introduce new input. |
| V6 Cryptography | no | No crypto change. |

### Known Threat Patterns for `mcp-gateway` + r2 in this phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| TOCTOU race in cap-check + insert allowing > cap concurrent sessions | Denial of Service (resource exhaustion) | `BoundedSemaphore` atomicity — Phase 13 Track A |
| r2 command-syntax bypass of regex blacklist (`pdf ; !ls`, `aflj | !whoami`, future `;` / `|` / `R!` variants) leading to host-side `system()` execution | Tampering, Elevation of Privilege | r2 `cfg.sandbox=true` at argv-eval time — Phase 13 Track B (subject to grain-value resolution per Open Question 1) |
| r2 autoload-hook / format-handler exec on binary open BEFORE init batch runs | Elevation of Privilege (pre-config exec) | Sandbox flags via argv `-e`, processed BEFORE binary open — Phase 13 D-07 |
| Unsafe-tool registration leaking to clients who didn't request it | Information Disclosure (unintended capability advertisement) | Env-gated registration default-off — Phase 13 D-10; tool absent from `tools/list` unless `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1` |
| Over-release of semaphore leading to silent ValueError → uncaught exception in close() path | Denial of Service (cleanup-path crash) | `_slot_released` flag + try/except wrap + log.exception — Pitfalls 4, 5 |
| Unsafe-session usage not audit-trailed | Repudiation | D-11 WARN log line with `session_id, sample_sha256[:8], case_dir` |

## Existing Test Surfaces (the planner must keep these GREEN)

Codebase grep `"SessionCapReached\|MAX_SESSIONS\|JobCapReached\|_DANGEROUS_R2\|cap.reached\|session cap"` matched:

| Test file | Touch points | Phase-13 expected behavior |
|-----------|--------------|----------------------------|
| `mcp-gateway/tests/test_sessions.py` | `test_cap_reject` (line 70) — opens N+1 against cap=2, expects `SessionCapReached` with `to_dict()` shape | STAY GREEN — D-03/D-07 preserve `SessionCapReached.to_dict()` byte-identical. |
| `mcp-gateway/tests/test_sessions_package.py` | imports of `SessionCapReached`, MAX_SESSIONS constant | STAY GREEN — symbol names unchanged. |
| `mcp-gateway/tests/test_gdb_session.py` | gdb cap-reject path | STAY GREEN — same shared `self._sem` covers gdb. |
| `mcp-gateway/tests/jobs/test_errors.py` | `test_cap_reached_shape` (line 34) — open N+1 jobs, asserts cap-reached dict shape | STAY GREEN — D-03 preserves `JobCapReached.to_dict()` byte-identical. |
| `mcp-gateway/tests/test_tools_jobs_smoke.py` | smoke test of jobs surface incl. cap behavior | STAY GREEN — surface unchanged. |
| `mcp-gateway/tests/test_tool_list.py` | EXPECTED_TOOLS baseline 54 / dynamic 61 | EXTEND — add `MCP_GATEWAY_R2_UNSAFE_ALLOWED` axis (+1 each). |
| `mcp-gateway/tests/test_r2_sessions.py` | r2 spawn argv assertions, regex-refusal cases | EXTEND — new test for `test_unsafe_open_warn_log`; existing regex-refusal tests STAY GREEN (regex unchanged). |
| `mcp-gateway/tests/jobs/conftest.py` + `tests/jobs/test_*` | `registry_factory` fixture that builds BackgroundJobRegistry per-test | STAY GREEN — fixture API unchanged. Phase 13 adds `self._sem` to the registry but doesn't change `__init__` signature. |

**No test file imports `_DANGEROUS_R2_CMD_RE` by name** (confirms Assumption A5). The dangerous-cmd refusal is tested via the public surface (`r2_cmd("!ls")` raises ValueError).

## Sources

### Primary (HIGH confidence)

- **r2 source** — `github.com/radareorg/radare2`:
  - `libr/util/sandbox.c` — `R_SANDBOX_GUARD` macro; `r_sandbox_grain(mask)` function; `G_graintype = R_SANDBOX_GRAIN_ALL` default.
  - `libr/include/r_util/r_sandbox.h` — full `R_SANDBOX_GRAIN_*` constants enumeration (NONE/SOCKET/DISK/FILES/EXEC/ENVIRON/NETWORK/HIDDEN/ALL).
  - `libr/core/cconfig.c` — `cb_cfgsanbox_grain` parser; `help_msg_grain` help table; `SETCB("cfg.sandbox.grain", "all", ..., "select sandbox permissions to keep enabled (all, none, disk, files, exec, socket, network, environ, hidden)")`.
- **Python asyncio docs** — `docs.python.org/3.11/library/asyncio-sync.html` — BoundedSemaphore ValueError-on-over-release; locked() returns True when "semaphore can not be acquired immediately".
- **Python bug-tracker** — `github.com/python/cpython/issues/90155` — asyncio.Semaphore cancellation fix landed in 3.10.
- **r2 docs** — `book.rada.re/first_steps/commandline_flags.html` — `-e` flag processed at startup; idiom `r2 -e io.cache=true /bin/ls` showing pre-binary-open ordering.
- **Codebase (verified by grep)**:
  - `mcp-gateway/src/mcp_gateway/sessions/_base.py:163-258` — `SessionRegistry` class; cap-check at sessions/r2.py:131-134 + sessions/gdb.py:301-304.
  - `mcp-gateway/src/mcp_gateway/jobs.py:506-583` — `BackgroundJobRegistry` + `submit` cap site at lines 549-554.
  - `mcp-gateway/src/mcp_gateway/jobs.py:623-720` — `_spawn_and_drive` terminal-state paths; `_mark_terminal` single sink.
  - `mcp-gateway/src/mcp_gateway/tools/__init__.py:64-74` — env-gated registration template (Phase 11 DYN-01).
  - `mcp-gateway/tests/conftest.py:11-17` — `_require_r2_or_skip` helper.

### Secondary (MEDIUM confidence)

- **r2-mcp commit** — `github.com/radareorg/radare2-mcp/commit/482cde6` — confirms default grain `exec,socket` for the r2-mcp project specifically; clarifies that listing a category means "keep this enabled (allowed)."
- **r2wiki** — `r2wiki.readthedocs.io/en/latest/tools/radare2/` — general sandbox / grain documentation summary.

### Tertiary (LOW confidence)

- **WebSearch on Python semaphore cancellation patterns** — synthesized into Pitfalls 2 + 3; primary source for the canonical pattern remains the asyncio docs + bpo-90155 thread (HIGH).

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — every primitive verified against either official Python docs or r2 source code.
- Architecture: HIGH — Code Examples 1-6 are direct synthesis of CONTEXT.md decisions against existing codebase shape (every line number cited is from the actual repo).
- Pitfalls: HIGH on Pitfalls 1, 4, 5, 6 (verified from source). HIGH on Pitfall 2 (verified bpo). HIGH on Pitfalls 3, 8, 9, 10 (codebase + docs). Pitfall 7 is informational (no change needed; currently safe).
- r2 grain semantics correction (Pitfall 1): HIGH — confirmed against three independent r2 source artifacts (`sandbox.c`, `r_sandbox.h`, `cconfig.c`). This is the most important finding in this research.

**Research date:** 2026-05-20
**Valid until:** 2026-06-20 (30 days — stable C-level r2 semantics + stdlib asyncio behavior; no fast-moving APIs in the dependency chain)
