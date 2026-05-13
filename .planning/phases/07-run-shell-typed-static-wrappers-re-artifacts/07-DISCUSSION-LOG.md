# Phase 7: run_shell + Typed Static Wrappers + re_artifacts - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 07-CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 07-run-shell-typed-static-wrappers-re-artifacts
**Areas discussed:** mare-shell UID + ACL strategy, run_shell env whitelist contents, Tool-name collision: hard-fail mechanics, Tool API surface (modules + wrappers + helpers)

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| mare-shell UID + ACL strategy | UID drop mechanism + case_dir ACLs + backfill + /agent filesystem visibility | ✓ |
| run_shell env whitelist contents | Exact env vars surviving scrub before bash -c | ✓ |
| Tool-name collision: hard-fail mechanics | Reverses v1.0 "backend wins"; lifespan-level RuntimeError | ✓ |
| Tool API surface (modules + wrappers + helpers) | Module split + wrapper signatures + artifact helper semantics + Resources expansion | ✓ |

**User selected:** All four gray areas.

---

## mare-shell UID + ACL strategy

### Q1: UID drop mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| gosu mare-shell bash -c | Already in image; same pattern as agent-entrypoint.sh | |
| setpriv --reuid + --clear-groups + --no-new-privs + --inh-caps=-all | More defense-in-depth knobs; util-linux already present | ✓ |
| runuser -u mare-shell | PAM-aware; resets HOME/SHELL via pwd lookup | |

**User's choice:** "choose recommended, most robust" → setpriv (defense-in-depth tips it over gosu).
**Notes:** D-01 codifies the exact argv. `--clear-groups` wipes supplementary groups, `--no-new-privs` blocks setuid escalation (relevant under SYS_PTRACE + seccomp=unconfined), `--inh-caps=-all` drops inheritable caps.

### Q2: Case_dir writability for mare-shell

| Option | Description | Selected |
|--------|-------------|----------|
| POSIX ACL: setfacl -m + default ACL | Fine-grained, no group-membership broadening; default-ACL inherits to new files | ✓ |
| chmod 2770 + chgrp + group membership | Simpler but requires mare-shell in agent group or vice-versa | |
| Bind-mount with uid remap | Needs CAP_SYS_ADMIN; explicitly deferred to v1.2 | |

**User's choice:** "choose most robust" → POSIX ACL with default ACL.
**Notes:** D-03 commits to `setfacl -m u:agent:rwx,g:mare-shell:rwx,o::--- <case_dir>` + the `-d` default-ACL variant. `acl` package added to Dockerfile apt list (D-04).

### Q3: ACL backfill for pre-existing case-dirs

| Option | Description | Selected |
|--------|-------------|----------|
| Lazy: ensure_mare_shell_access() on first run_shell / write_artifact | Amortized to first call; no startup walk | ✓ |
| Eager backfill in lifespan | Linear startup cost; one bad case-dir blocks gateway start | |
| Both: eager + lazy | Belt-and-suspenders but wasteful | |

**User's choice:** "choose most robust" → Lazy.
**Notes:** D-05 + D-06 commit to lazy. helper raises RuntimeError on setfacl failure, never silently degrades.

### Q4: /agent filesystem visibility for mare-shell

| Option | Description | Selected |
|--------|-------------|----------|
| Group-based revocation: token chmod 0400 root:root + uploads RO ACL + default elsewhere | Minimum-viable + token-secure | |
| Aggressive: revoke token + all .idapro/.binaryninja/.codex/.claude + /root | Defense-in-depth; full secret quarantine | ✓ |
| Permissive: revoke only the token | Lazy; leaks shell config + history | |

**User's choice:** "choose most robust for future questions too" → Aggressive revocation.
**Notes:** D-07 codifies the full file-permission table. D-08 codifies the three regression tests (id, token-cat, env-grep).

---

## Carry-forward mandate

User's "choose most robust for future questions too" was applied to:

- **Env whitelist (D-09/D-10):** Whitelist (build from scratch), 9-key set including 2 MARE_* introspection vars. Explicit exclude list documents what stays out (with a regression test asserting it).
- **Collision policy (D-11..D-15):** Hard-fail at lifespan, RuntimeError → exit code 78 (EX_CONFIG). Scope = all gateway-native tools (not just run_*). Reverses backend_passthrough.py:8 "backend wins."
- **Module split (D-16/D-17):** 4 files (shell, re_static, re_artifacts, collision_check). Research-recommended 3 + 1 small collision module.
- **Wrapper APIs (D-18..D-20):**
  - readelf takes sections allowlist; objdump/nm take enum modes; rabin2 always `-j` JSON-first.
  - capstone + ropper in-process via Python libs with `_inproc_result` shim for shape uniformity.
  - 2 new pip deps pinned in pyproject.toml.
- **Artifact helpers (D-21..D-27):**
  - write_artifact supports text + binary; default `overwrite=False`.
  - get_artifact_tree recursive with `MAX_FILES=1024` + `MAX_DEPTH=8` caps.
  - get_tool_log bytes-by-offset with `next_offset` for paged reads.
  - MCP Resources expose all 9 EXPANDED_CASE_SUBDIRS at depth ≤ 2 (cap 1024 resources).
- **run_shell details (D-28..D-32):** `bash -c` (NOT -lc); cmd-size cap; NUL-byte rejection; no argv allowlisting (Pitfall 2 stance).
- **Tests (D-33..D-35):** One test file per module + tests/fixtures/ with small public-domain binaries + Phase 6's 100 MB urandom test rerun at the run_shell layer.

---

## Claude's Discretion

Items where the planner / executor may decide within constraints:
- `_inproc_result` helper module placement (re_static.py vs artifacts_io.py)
- Specific extra flags on readelf allowlist (e.g., `-n`, `-V`)
- Pinning mare-shell UID to 700 vs letting useradd pick
- Including sha256 in get_tool_log response
- Result-size caps on run_jq / run_yq beyond runner default
- Whether MARE_SAMPLE_PATH is omitted vs empty-string when sample is unresolvable

## Deferred Ideas

- Mount-namespace isolation (CAP_SYS_ADMIN cost; v1.2)
- Per-Mcp-Session-Id mare-shell keying (GW-V2-03; v1.2)
- Sandboxed-network mode (Phase 11)
- Recursive `extracted/<sub>/<file>` resources (Phase 10)
- Composite shell-helper wrappers (Phase 12 orchestrator skill)
- get_artifact refactor to use confine_to (Phase 6 deferred)
- run_strings as typed wrapper (out of scope per REQUIREMENTS)
- capstone/ropper as CLI subprocesses (D-19 rejected)
- run_shell argv-pattern detection (Pitfall 2 stance)
