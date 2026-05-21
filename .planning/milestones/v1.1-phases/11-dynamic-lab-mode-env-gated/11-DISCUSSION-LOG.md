# Phase 11: Dynamic Lab Mode (env-gated) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 11-dynamic-lab-mode-env-gated
**Areas discussed:** gdb session architecture (module placement + MI allowlist), Network isolation, argv profile design, Mode UX & capability probe

---

## Pre-discussion: gray-area framing

After loading prior context (PROJECT.md, REQUIREMENTS.md, STATE.md, Phases 8/9/10 CONTEXT, research SUMMARY/PITFALLS/ARCHITECTURE), the analysis identified 4 phase-specific gray areas worth deciding before the research/planning agents kick in. These map 1:1 to STATE.md "Pending Todos" Phase 11 entries (per-call netns mechanism, ptrace probe error UX, gdb MI3 allowlist, binfmt detection helper) plus the deferred sessions-package refactor Phase 8 D-05 owed Phase 11.

The user's standing mandate from prior phases — "Choose the most robust, common-sensical, and feature-rich option for all questions" — was re-affirmed in this session as the single-line answer covering all four areas.

---

## Area 1: gdb session architecture (module placement + MI3 allowlist)

| Option | Description | Selected |
|--------|-------------|----------|
| Refactor `sessions.py` → `sessions/` package | Move r2 to `sessions/r2.py`, add `sessions/gdb.py`, hoist shared registry to `sessions/_base.py`. Single SessionRegistry manages both kinds with combined cap of 8. Honors Phase 8 D-05's explicit deferral to Phase 11. | ✓ |
| Add parallel `gdb_sessions.py` | Keep `sessions.py` monolithic for r2; create a peer `gdb_sessions.py` with its own GdbRegistry and lifespan block. Separate cap for gdb. | |
| **MI3 allowlist scope:** strict prefix allowlist | ~50 explicit MI prefixes allowed (`-info-*`, `-data-evaluate-expression`, `-exec-*`, `-break-*`, `-stack-*`, `-thread-*`, `-symbol-info-*`, `-var-*`) + a defense-in-depth deny-regex (`-interpreter-exec console`, `python`, `source`, `attach`, `add-symbol-file`, `!`, `shell`). | ✓ |
| **MI3 allowlist scope:** deny-list only | Allow most MI, block only the known-dangerous (python/shell/source/interpreter-exec). More permissive; easier for analysts. | |

**User's choice:** "most robust, common-sensical, feature-rich" → strict-allowlist + sessions/-package refactor (D-01..D-10 in CONTEXT.md)
**Notes:** Phase 8 D-05 explicitly said Phase 11 owns the rename-only refactor. Strict allowlist is the only posture that prevents future MI extensions from silently widening the escape surface. Combined cap of 8 (r2+gdb) matches research consensus and avoids per-kind config sprawl. gdb runs with `--interpreter=mi3 --quiet --nx --nh`, mandatory `-gdb-set` lockdown batch, MI3 sentinel framing via `-data-evaluate-expression "<sentinel>"`.

---

## Area 2: Network isolation

| Option | Description | Selected |
|--------|-------------|----------|
| Per-call `unshare --net --ipc --uts -- <argv>` argv-wrap | Every dynamic subprocess prepended with `unshare`; gateway itself is NOT unshared. Simple, kernel-managed, no setup. Loopback absent (kernel returns ENETUNREACH cleanly). | ✓ |
| Persistent named netns + `nsenter` | `ip netns add mare-dynamic` at gateway start; each dynamic spawn does `nsenter --net=/var/run/netns/mare-dynamic -- <argv>`. Loopback consistent. | |
| `--network=none` on docker run | Container-wide no-net. Breaks gateway's MCP connectivity. | |
| `iptables -P OUTPUT DROP` inside container | Container-wide block. Breaks the rest of the container. | |

**User's choice:** "most robust, common-sensical, feature-rich" → per-call `unshare` (D-DYN-NET-01)
**Notes:** All four research documents (FEATURES, ARCHITECTURE, PITFALLS §9, SUMMARY) converged on per-call unshare as the no-net mechanism. No loopback inside the netns is intentional (D-DYN-NET-02) — kernel ENETUNREACH > half-resolved state. Mandatory in v1.1 (no per-call opt-out); `allow_network=True` is v1.2 territory per REQUIREMENTS Out of Scope.

---

## Area 3: argv profile design (strace / ltrace / qemu_user)

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: named profiles + escape-hatch `extra_args` with allowlist regex | Profile-name kwarg maps to predefined argv fragments (`file_io`, `network`, `process`, `file_network_process`, `all`, `summary` for strace; analogous for ltrace/qemu). `extra_args: list[str]` validated per-arg against allowlist regex + explicit deny-set (no `-o`, no `-p`, no `-D`/`--detach`). Plus `run_argv` for sample's own argv. | ✓ |
| Named presets only | Profile-name only; no escape hatch. Simple but inflexible. | |
| Freeform with allowlist | No profiles; caller passes full argv, allowlist-validated. Powerful but high friction. | |

**User's choice:** "most robust, common-sensical, feature-rich" → hybrid (D-DYN-PROF-01..D-DYN-PROF-04)
**Notes:** Profiles cover the 80% case (file_network_process for triage, library_calls for ltrace, simple/syscall_strace for qemu). The `extra_args` allowlist regex blocks output redirection (gateway owns `-o`), daemonization (`-D`/`--detach`), and pid-attach (`-p`) — these are gateway responsibilities or out-of-scope. `run_argv` supports samples that need argv.

---

## Area 4: Mode UX & capability probe

| Option | Description | Selected |
|--------|-------------|----------|
| **Sync vs job:** all 3 trace tools always-job | Every `run_strace`/`run_ltrace`/`run_qemu_user` dispatches as a Phase 9 job; returns snapshot dict. Agent polls. | ✓ |
| **Sync vs job:** opt-in `wait=True` | Short traces can run sync (capped 60 s). | |
| **Capability probe failure:** probe + report, never hard-fail | Probe runs at startup, never raises; missing capabilities become None/False fields with WARN-logged warnings. Per-tool calls return structured error dict with actionable hints when their prerequisite is missing. | ✓ |
| **Capability probe failure:** hard-fail gateway start when --dynamic was passed but caps missing | Refuse to start; operator must fix host posture first. | |
| **CURRENT_STATE.json mode marker:** Phase 11 exposes `get_dynamic_capabilities()`; Phase 12 (orchestrator skill update) writes into per-case CURRENT_STATE.json | Phase 11 does NOT touch workspace skill files; clean phase boundary. | ✓ |
| **CURRENT_STATE.json mode marker:** Phase 11 writes a gateway-level `CURRENT_STATE.json` at container start | Couples gateway to orchestrator-skill artifact contract. | |

**User's choice:** "most robust, common-sensical, feature-rich" → always-job + probe-and-report + Phase 12 owns the CURRENT_STATE.json write (D-DYN-DISPATCH-01, D-DYN-CAP-PROBE-01/02, D-DYN-CAP-CURRENTSTATE)
**Notes:** DYN-07 mandates JOBS dispatch for long-running dynamic tools. Hard-fail at startup would prevent operators from running `--dynamic` to see what's broken. The probe is <200 ms (5 sub-probes, each <100 ms typical) and runs unconditionally in both branches so `get_dynamic_capabilities()` works even when dynamic tools aren't registered. Phase 11 exposes the capability; Phase 12's `update_state.py` writes into per-case files (preserves the additive-only invariant from ARCHITECTURE.md).

---

## Claude's Discretion

Locked decisions enumerate alternatives the planner/executor can adjust freely within the constraints. Notable items: exact wording of WARN log lines (D-DYN-PROBE-LOG), whether `STRACE_PROFILES` lives module-level or in submodule, whether `follow_fork_mode="child"` is exposed as `open_gdb_session` kwarg (recommended yes), gdb argv compatibility for `--nh` on pre-9.0 (verify at research; substitute `-iex "set auto-load no"` if needed), whether `tools/dynamic.py` uses module-level coroutines or inside-register (recommended module-level per Phase 10 D-19 precedent).

---

## Deferred Ideas

- `allow_network=True` per-call opt-in — v1.2 (INetSim/FakeDNS)
- Mount-namespace isolation — v1.2 (CAP_SYS_ADMIN cost)
- Coverage-guided dynamic — v1.2+ (afl/libFuzzer)
- Memory snapshot tooling (Volatility) — v1.2+
- Full-VM dynamic — out of scope
- Per-`Mcp-Session-Id` keying of gdb sessions / dynamic jobs — v1.2 (gateway-wide)
- `job_specs/` package refactor — deferred until ~10+ specs or cross-spec sharing pain
- CLI-mode gdb support — explicitly rejected (MI3 only)
- Auto-binfmt registration from inside container — Phase 12 host-side documentation
- Persistent named netns — rejected in favor of per-call `unshare`
- Replay-from-trace (rr, gdb record) — v1.2+
- Sandboxed-network dynamic (INetSim/FakeDNS) — v1.2

See CONTEXT.md `<deferred>` section for full list with rationale.
