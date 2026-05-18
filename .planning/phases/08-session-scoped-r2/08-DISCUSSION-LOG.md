# Phase 8: Session-Scoped r2 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-18
**Phase:** 08-session-scoped-r2
**Areas discussed:** r2 IPC driver, Module layout, Dangerous-command refusal scope, Output capture & format param

---

## Gray area selection

| Option | Description | Selected |
|--------|-------------|----------|
| r2 IPC driver | r2pipe (sync, thread offload) vs raw asyncio + sentinel marker | ✓ |
| Module layout | Flat `sessions.py` + `tools/r2_sessions.py` vs `sessions/` subpackage | ✓ |
| Dangerous command refusal scope | Literal-first-char vs full-string scan including `;`/`|`/newline separators | ✓ |
| Output capture & format param | Auto-`j` + parsed_json vs passthrough hint; per-command log vs transcript vs both | ✓ |

**User's choice:** "Choose the most robust and appropriate option for all questions" — same
mandate as Phases 6 and 7.

---

## r2 IPC driver

| Option | Description | Selected |
|--------|-------------|----------|
| r2pipe (Python lib) | Sync API; requires `anyio.to_thread.run_sync` per call; framing handled by lib | |
| Raw asyncio.create_subprocess_exec + sentinel marker | Tight asyncio integration, no thread offload, sentinel-marker (`?e __MARE_END_<rand>__`) sidesteps prompt parsing | ✓ |

**Decision:** Raw asyncio + per-session-randomized sentinel marker (D-01, D-04).
**Rationale:** r2pipe's sync API would require a thread boundary per call, breaking
the cancellation contract from Phase 6 D-04 (`asyncio.shield(proc.wait())` cannot
interrupt a blocked thread) and complicating per-command timeout enforcement
(Pitfall 6: kill the session on miss). Raw asyncio matches the rest of the gateway's
I/O model and lets timeout/cancel land cleanly through `asyncio.wait_for` + `killpg`.

---

## Module layout

| Option | Description | Selected |
|--------|-------------|----------|
| Flat `sessions.py` + `tools/r2_sessions.py` | Primitive at top, MCP-surface under `tools/` — mirrors Phase 6/7 split | ✓ |
| `sessions/` subpackage with `r2.py` + `registry.py` + `reaper.py` | Pre-built for Phase 11's gdb addition | |

**Decision:** Flat layout (D-05).
**Rationale:** Mirrors `runner.py` + `tools/shell.py` exactly. Phase 11's gdb
addition can refactor `sessions.py` into a `sessions/` subpackage as a rename-only
commit. Premature packaging would create empty-shape speculation.

---

## Dangerous-command refusal scope

| Option | Description | Selected |
|--------|-------------|----------|
| Literal-first-char only | Refuse cmd starting with `!`, `#!`, or `R!` — simple, matches SESS-06 wording verbatim | |
| Full-string scan with regex | `(?:^|;|\||\n)\s*(?:!|#!|R!)` — catches `pdf ; !ls`, `aaa | !whoami`, multi-line embeddings | ✓ |

**Decision:** Full-string scan (D-08).
**Rationale:** r2 natively supports `;` for compound commands and `|` for shell pipes.
Literal-first-char would let `pdf ; !ls` slip past. SESS-06 says "refuse dangerous
shell-escape commands at the wrapper layer" — full-string scan is what actually
satisfies that. Defense-in-depth philosophy carried from Phases 6/7 (Phase 6 D-11
`confine_to` rejects all traversal vectors, not just `..`; Phase 7 D-09 whitelist
over blacklist for env scrub).

---

## Output capture & format param

### Format parameter shape

| Option | Description | Selected |
|--------|-------------|----------|
| `format: Literal["text","json"]` with auto-`j` suffix + best-effort parse | Ergonomic; agent doesn't need to know r2's `j` convention; `parsed_json: None + parse_error` on non-JSON commands | ✓ |
| `format` as passthrough hint (no auto-suffix) | Simpler; agent writes `pdfj` themselves | |

**Decision:** Auto-suffix + `parsed_json` field alongside the Phase 6 12-key shape
(D-10, D-11).
**Rationale:** r2's `j` suffix is universal across query commands. Surfacing it as a
named parameter saves agents from remembering the convention; best-effort parse with
never-throw contract matches Phase 6 D-04's runner-never-raises pattern.

### Per-command vs session-wide capture

| Option | Description | Selected |
|--------|-------------|----------|
| Per-command tool-log only | One `tool-logs/<ts>-r2_cmd-<rand4>.txt` per call — uniform with Phase 6 D-09 | |
| Session-wide transcript only | One append-only `r2-sessions/<sid>-transcript.log` for the whole session | |
| Both | Per-command log (uniform with Phase 6) AND session transcript (replay/audit artifact) | ✓ |

**Decision:** Both (D-12, D-13).
**Rationale:** Per-command logs give agents a uniform `get_tool_log` surface that
matches every other Phase 6/7 wrapper. The session transcript is the
replay/audit artifact — "show me what this analyst did in this session." Storage
and write cost are negligible (one extra append per command). The transcript path
is flat under `r2-sessions/` so Phase 7 D-26's depth-≤-2 resource walker exposes
it as `mare://cases/<case>/r2-sessions/<sid>-transcript.log` without modification.

---

## Claude's Discretion

Sub-decisions left to the planner (within the locked-in constraints):

- ANSI-strip / UTF-8-safe truncate helper hoisting into `artifacts_io.py` if not
  already public
- `r2_cmd` per-call `truncate_kb` kwarg (recommend: omit, use the runner default)
- `list_sessions` extra fields beyond `fd_count` (recommend: omit RSS/CPU for v1.1)
- `session_id` exact byte length — research says 12, planner may pick 16
- Whether refused commands are recorded in the transcript (recommend: yes, footer
  line only — they are pre-protocol, no r2 output to capture)
- Gateway version/build sha in transcript header (recommend: yes if cheap)
- `format="r2"` raw-binary mode (recommend: omit for Phase 8)

---

## Deferred Ideas

(Ideas mentioned that belong in other phases — see `08-CONTEXT.md` `<deferred>`
section for the full list with rationale.)

- Per-`Mcp-Session-Id` keying (`GW-V2-03`) — v1.2
- `sessions/` subpackage refactor — Phase 11 (gdb)
- LRU-evict instead of cap-reject — v1.2 with per-session keying
- Session-restart-recovery — design rejected (in-memory by design)
- r2 plugin support — out of scope (security posture)
- `format="r2"` raw-binary mode — v1.2+ if needed
- r2 session UID drop to `mare-shell` — v1.2 reconsideration
- MCP progress reporting for long r2 commands — r2 doesn't emit progress signals
- Multi-line / heredoc `r2_cmd` transport — yagni; use temp file + `. /tmp/script.r2`
- Auto-checkpointing r2 project state (`Ps`/`Po`) — v1.2+
