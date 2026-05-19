# Phase 9: Background Job System - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 09-background-job-system
**Areas discussed:** Dispatch surface, Progress reporting, Lifecycle policy, get_tool_job result shape

---

## Gray Area Selection

User was asked: "Which gray areas do you want to discuss for Phase 9 (Background Job System)?"

| Option | Description | Selected |
|--------|-------------|----------|
| Dispatch surface | JOBS-01 says start_tool_job(tool, args). Is `tool` a registered typed-tool name (allowlist), a raw argv list, or a callable handle? | ✓ |
| Progress reporting | JOBS-07: MCP `Context.report_progress` is per-request, but jobs outlive requests. How is progress extracted/replayed? | ✓ |
| Lifecycle policy | Status vocabulary, grace period before SIGKILL (JOBS-03), 256 MB log cap (JOBS-05), LRU retention, on-eviction log fate, concurrency cap | ✓ |
| get_tool_job result shape | JOBS-02 says 'head-tail'. Where does tail come from? Streaming-delta or snapshot? Layered onto Phase 6 12-key shape? | ✓ |

**User's choice:** "Choose answers to all as robustly and soundly and common-sensely as you see fit."

**Notes:** User delegated all four areas to Claude's judgment. Decisions were made grounded in:
- Phase 6/8 established patterns (primitive + tools/ split, async-context-manager registry, env-var module constants, layered 12-key result dict, structured error dicts that never raise)
- JOBS-01..07 requirements (in-memory registry, head-tail output, 256 MB log cap, progress notifications, SIGTERM-then-SIGKILL cancellation, CancelledError handling)
- Common-sense defaults (4 in-flight cap, 10s SIGTERM grace, 200-job FIFO retention, 32 KB head + 32 KB tail, capa as the canonical Phase 9 spec)

---

## Dispatch surface (Claude's discretion → decided)

**Decision (CONTEXT.md D-01..D-05):** Allowlist registry of named tool specs, NOT raw argv.

- `start_tool_job(tool: str, kwargs: dict, *, case_dir: str, timeout: float | None = None)` — tool name resolved against module-level `JOB_TOOL_REGISTRY`
- `JobToolSpec` frozen dataclass: `name`, `slug`, `build_argv(case_dir, kwargs) -> list[str]`, `default_timeout_s`, optional `progress_parser`, optional `kwargs_schema`, `description`
- `register_job_tool(spec)` is called at import time by Phase 10/11 modules
- Phase 9 ships ONE user-visible spec (`capa`) plus one internal `_sleep_probe` for tests
- start_tool_job returns immediately with a snapshot dict; never awaits subprocess completion

**Alternatives considered (rejected):**
- Raw argv list: defeats Phase 6 D-01 argv-only-from-trusted-source guarantee; agent could background `rm -rf /`
- Generic callable handle: complicates registration (every tool needs an "as-job" variant) without ergonomic gain

---

## Progress reporting (Claude's discretion → decided)

**Decision (CONTEXT.md D-16..D-18):** Two-tier model.

- **Tier 1:** Each `JobToolSpec` may carry `progress_parser(line: bytes) -> tuple[int, int, str] | None`. The drain loop calls it per-stderr-line and updates the job's progress fields when it returns a tuple.
- **Tier 2:** `get_tool_job(job_id, ctx)` accepts FastMCP-injected `Context`. If `ctx` is present and the job's progress has advanced since this `ctx.session_id` last polled, the handler calls `await ctx.report_progress(current, total, message)` before returning.
- Progress fields (`progress`, `progress_total`, `progress_message`) are always present in the snapshot, always all-None or all-Some.
- Tools without registered parsers have `progress: None` — acceptable per JOBS-07.
- Initial Phase 9 parsers: capa only (if capa emits parseable stderr progress — research phase verifies).

**Alternatives considered (rejected):**
- Server-push notifications outside polling: requires MCP session-scoped notification channels the spec is still maturing on; out of scope for v1.1.
- Tool-specific stdout/stderr parsing baked into tools/jobs.py: violates the registry's "parser lives with the spec" locality; Phase 10 would have to edit Phase 9 code.

---

## Lifecycle policy (Claude's discretion → decided)

**Decision (CONTEXT.md D-06..D-15):**

- **Status vocabulary (7-state):** `pending`, `running`, `succeeded`, `failed`, `cancelled`, `killed_timeout`, `killed_log_cap`. Terminal states are immutable.
- **Cancellation grace:** `MCP_GATEWAY_JOB_CANCEL_GRACE_S` default `10.0` seconds. SIGTERM → wait → SIGKILL on TimeoutError.
- **Job hard timeout:** `MCP_GATEWAY_JOB_TIMEOUT_S` default `3600.0` (1h); ceiling `MCP_GATEWAY_JOB_MAX_TIMEOUT_S` default `86400.0` (24h). Per-call override via `timeout` kwarg.
- **Log cap:** `MCP_GATEWAY_MAX_JOB_LOG_MB` default `256`. Counter-based in drain loop. On exceed: immediate SIGKILL (no SIGTERM grace), status `killed_log_cap`, marker line appended.
- **Concurrency cap:** `MCP_GATEWAY_MAX_JOBS_INFLIGHT` default `4`. Cap-reach returns structured `JobCapReached` error dict (no queueing) — matches Phase 8 D-18.
- **Retention:** `MCP_GATEWAY_MAX_COMPLETED_JOBS` default `200`. FIFO by `ended_at` (documented as "effectively LRU" per JOBS-05 spirit). On eviction, in-memory entry removed but on-disk log + JSON snapshot preserved under `tool-logs/`.

**Alternatives considered (rejected):**
- Queueing on cap-reach: hidden head-of-line blocking; uniformity with Phase 8 wins.
- Deleting log files on eviction: destroys audit trail; violates "case-dir is the source of truth" invariant.
- Periodic stat for log cap: race window where a tool could burst > cap between checks.
- Separate stdout/stderr caps: agents could dodge total cap by splitting output.

---

## get_tool_job result shape (Claude's discretion → decided)

**Decision (CONTEXT.md D-19..D-21):** Snapshot per poll, layered onto Phase 6 D-03's 12-key shape (matches Phase 8 D-11 precedent).

- Base 12 keys from Phase 6 D-03, sentinel-valued while non-terminal
- Job extensions: `job_id`, `tool`, `status`, `started_at`, `ended_at`, `stdout_tail`, `stderr_tail`, `progress`, `progress_total`, `progress_message`, `kwargs`, `case_dir`, `effective_timeout_s`
- `stdout_head` from in-memory drain buffer (default 32 KB via `MCP_GATEWAY_JOB_STDOUT_HEAD_KB`)
- `stdout_tail` from on-disk log file last N bytes (default 32 KB via `MCP_GATEWAY_JOB_STDOUT_TAIL_KB`)
- If log smaller than head+tail combined, `stdout_tail == ""` to avoid duplication
- No streaming/cursor/since-token: every poll returns full snapshot, idempotent, matches "never raises" contract
- Agents wanting whole log use Phase 7 D-25 `get_tool_log(case_dir, log_name, start, length)` range-read

**Alternatives considered (rejected):**
- Streaming-delta with since-token: every agent has to track cursors; non-idempotent polling breaks retry semantics.
- Separate `get_tool_job_output(job_id)` tool just for log content: redundant with the existing Phase 7 D-25 `get_tool_log` surface.

---

## Claude's Discretion

User delegated entire phase to Claude's judgment. The CONTEXT.md "Claude's Discretion" subsection captures specific micro-level items (private helper names, ANSI-strip helper reuse vs. duplication, exact error-hint prose, sleep_probe argv form) that the researcher and planner have flexibility on.

## Deferred Ideas

- Persistent (across-restart) job state — v1.2 (foundations laid via on-disk `.json` snapshots per D-21)
- Per-Mcp-Session-Id job keying — v1.2 (parallel to SESS-05)
- Cross-job dependencies / DAG orchestration — out of scope
- Server-push progress notifications outside polling — out of scope
- Composite `investigate_*` tools — out of scope per PROJECT.md
- Disk-quota-aware log sweeper — out of scope; case-dir is the natural cleanup boundary
