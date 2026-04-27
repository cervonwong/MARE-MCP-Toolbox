---
phase: 03-container-integration
plan: 01
subsystem: container-launcher
tags: [docker, compose, dual-mode, mcp-gateway, smoke-tests]
requires: [phase-02-mcp-gateway]
provides:
  - dual-mode-launcher (run_docker.sh: local + --remote)
  - compose-overlay (compose.remote.yaml keepalive)
  - mode-gated-gateway (Dockerfile MCP_GATEWAY_ENABLED guard)
  - phase-3-smoke-suite (smoke-local.sh, smoke-remote.sh, smoke-all.sh)
affects:
  - run_docker.sh
  - compose.yaml
  - compose.remote.yaml
  - Dockerfile (agent-entrypoint.sh heredoc)
tech-stack:
  added: [docker-compose-overlay]
  patterns: [pre-up-token-cleanup, post-up-token-polling, mode-driven-env]
key-files:
  created:
    - compose.remote.yaml
    - .planning/phases/03-container-integration/scripts/lib_assert.sh
    - .planning/phases/03-container-integration/scripts/smoke-local.sh
    - .planning/phases/03-container-integration/scripts/smoke-remote.sh
    - .planning/phases/03-container-integration/scripts/smoke-all.sh
  modified:
    - run_docker.sh
    - compose.yaml
    - Dockerfile
key-decisions:
  - D-01..D-12 from 03-CONTEXT.md honored verbatim
  - Smoke-script bugs auto-fixed under Rule 1 (REPO_ROOT depth, bash -c wrapper, pgrep -x, pipefail-safe pubs count, HTTP-listener race)
requirements: [INF-01, INF-02, INF-05]
metrics:
  tasks-completed: 9
  files-created: 5
  files-modified: 3
  duration-from-resume: ~10min
  completed: 2026-04-27
---

# Phase 3 Plan 01: Container Integration Summary

Dual-mode container launcher (local interactive shell vs detached remote MCP gateway) wired through one image with mode selection via `./run_docker.sh --remote`.

## What Was Built

A single `kali-re-tools` Docker image now serves two completely separate UX modes from one entrypoint, gated by `MCP_GATEWAY_ENABLED`:

- **Local mode (default)** — `./run_docker.sh` runs `docker compose run --rm kali` and drops the user into an interactive bash at `/agent` as `agent`. Gateway daemon NOT started; no host port published. Byte-identical to v1.
- **Remote mode** — `./run_docker.sh --remote` runs `docker compose -f compose.yaml -f compose.remote.yaml up -d kali` detached, the gateway binds `0.0.0.0:8080` in-container, port `${MCP_GATEWAY_HOST_BIND:-0.0.0.0}:${MCP_GATEWAY_HOST_PORT:-8080}` is published on the host, and a print block (URL + bearer token + ready-to-paste `.mcp.json` snippet + curl example + teardown hint + 0.0.0.0 warning) is rendered to stdout.

Idempotence: re-running `--remote` against a live container reprints the existing token without restarting the gateway (token file is preserved; otherwise it is removed pre-up to defeat stale-token races).

## Files

### Created

| File | Purpose |
|------|---------|
| `compose.remote.yaml` | Phase 3 D-02 overlay: `command: ["tail","-f","/dev/null"]`, `tty:false`, `stdin_open:false`. Replaces the base CMD per Compose merge rules so `up -d` keeps the full image running detached. |
| `.planning/phases/03-container-integration/scripts/lib_assert.sh` | Shared bash assertion helpers (`assert_contains`, `assert_no_match`, `assert_exit_0`, `assert_eq`) sourced by smoke scripts. |
| `.planning/phases/03-container-integration/scripts/smoke-local.sh` | D-12 / INF-05 backstop: asserts `PWD=/agent`, `USER=agent`, no `mcp-gateway` proc, port 8080 not listening, claude/codex CLIs intact, no host ports published. |
| `.planning/phases/03-container-integration/scripts/smoke-remote.sh` | INF-01 + INF-02 end-to-end: gateway log shows bind to `0.0.0.0:`, host port published, token printed, `/mcp` 401 without auth, `/healthz` 200 with auth, idempotent re-run reprints same token. |
| `.planning/phases/03-container-integration/scripts/smoke-all.sh` | Orchestrator with shared trap-cleanup. |

### Modified

| File | Change |
|------|--------|
| `run_docker.sh` | Added `--remote`/`--token=<value>`/`--token <value>`/`--help` flag parsing; mode-aware exec block: local mode unchanged byte-for-byte except for prepended `MCP_GATEWAY_ENABLED=0`; remote mode exports `MCP_GATEWAY_ENABLED=1`, `MCP_GATEWAY_HOST=0.0.0.0`, `MCP_GATEWAY_HOST_BIND`/`HOST_PORT`, deletes stale token (skip if container already running), pre-up host-port collision warning, `compose -f compose.yaml -f compose.remote.yaml up -d`, 15s/200ms token poll, D-07 print block. |
| `compose.yaml` | Added `ports:` block driven by `${MCP_GATEWAY_HOST_BIND:-0.0.0.0}:${MCP_GATEWAY_HOST_PORT:-8080}:${MCP_GATEWAY_PORT:-8080}` and three new env-passthrough names: `MCP_GATEWAY_ENABLED`, `MCP_GATEWAY_HOST_BIND`, `MCP_GATEWAY_HOST_PORT`. (Compose `run --rm` ignores `ports:` without `--service-ports`, so this is local-mode-safe.) |
| `Dockerfile` | Wrapped the gateway-start block in `agent-entrypoint.sh` with `if [ "${MCP_GATEWAY_ENABLED:-0}" = "1" ]; then ... else echo "[gateway] MCP_GATEWAY_ENABLED!=1 -- skipping (local mode)"; fi`. The idalib-mcp launch block remains unguarded (D-11). |

## Verification Evidence

### `bash .planning/phases/03-container-integration/scripts/smoke-local.sh` — exit 0

```
[pass] D-12(b): cwd /agent unchanged
[pass] D-12(b): USER=agent unchanged
[pass] D-12(c): no mcp-gateway daemon in local mode
[pass] D-12(c): gateway port NOT listening in local mode
[pass] D-12(b): claude CLI available
[pass] D-12(b): codex CLI available
[pass] D-12(a): no host ports published in local mode

[smoke] local-mode green (D-12 / INF-05)
```

Container output during the local-mode run included `[gateway] MCP_GATEWAY_ENABLED!=1 -- skipping (local mode)` confirming the Dockerfile guard fires.

### `bash .planning/phases/03-container-integration/scripts/smoke-remote.sh` — exit 0

```
[pass] D-07: Bearer token printed
[pass] D-07: .mcp.json snippet contains 'type' key
[pass] D-07: URL printed
[pass] D-07: teardown hint printed
[pass] D-07: curl example printed
[pass] INF-02: host port published (Publishers=1)
[pass] INF-01: gateway log shows bind to 0.0.0.0
[pass] gateway HTTP listener accepting connections
[pass] /mcp without auth returned 401 (not 200)
[pass] /healthz reachable (200)
[pass] Idempotent re-run: token unchanged
[pass] Idempotent re-run: token reprinted

[smoke] remote-mode green (INF-01 + INF-02)
```

Print block from `./run_docker.sh --remote`:
```
═══════════════════════════════════════════════════════════════════
  MARE-MCP-Toolbox Gateway is ready
═══════════════════════════════════════════════════════════════════

  URL:    http://localhost:8080/mcp
  Token:  5xOuD-hAEYJTqqk4vNfUVitQ9wPmkwQa91JK2_wB8lU

  Claude Code .mcp.json snippet:
  {
    "mcpServers": {
      "mare-toolbox": {
        "type": "http",
        "url": "http://localhost:8080/mcp",
        "headers": { "Authorization": "Bearer 5xOuD-hAEYJTqqk4vNfUVitQ9wPmkwQa91JK2_wB8lU" }
      }
    }
  }

  ⚠  Gateway is published on ALL host interfaces (0.0.0.0:8080)
```

## Requirements Closed

- **INF-01** (gateway daemon starts in remote mode) — verified by `smoke-remote.sh` "gateway log shows bind to 0.0.0.0" + HTTP listener accept.
- **INF-02** (port published with configurable mapping) — verified by `Publishers=1` in `compose ps --format json`; `MCP_GATEWAY_HOST_BIND`/`HOST_PORT` env-driven mapping confirmed by interpolated compose config.
- **INF-05** (no v1 regressions) — verified by `smoke-local.sh` byte-identical assertions: PWD=/agent, USER=agent, no gateway proc, port 8080 not listening, claude/codex intact, zero host ports published.

## Deviations from Plan

### Auto-fixed Issues (Rule 1 — bug fixes uncovered during Wave 2)

The Wave 0 stubs created by prior tasks contained five bugs that surfaced only when the smoke scripts were executed end-to-end. All were auto-fixed inline (Rule 1) without changing test semantics. Each fix was committed atomically.

**1. [Rule 1 — Bug] Smoke-script `REPO_ROOT` depth was 3, should be 4**
- **Found during:** Task 2.1
- **Issue:** Scripts live at `.planning/phases/03-container-integration/scripts/` (4 levels deep) but the original `cd ../../..` only walked up 3 levels, yielding `<repo>/.planning` and breaking the subsequent `source lib_assert.sh`.
- **Fix:** `../../..` → `../../../..` in `smoke-local.sh`, `smoke-remote.sh`, and `smoke-all.sh`.
- **Commit:** `75589cb`

**2. [Rule 1 — Bug] `./run_docker.sh -c '<script>'` does not implicitly invoke bash**
- **Found during:** Task 2.1
- **Issue:** The Dockerfile entrypoint runs `exec gosu agent "$@"` verbatim. `compose run` replaces the CMD `["/bin/bash"]` when args are passed, so `-c '<script>'` is dispatched as a literal program name (`exec: "-c": executable file not found`).
- **Fix:** Smoke-local now calls `./run_docker.sh bash -c '<script>'`.
- **Commit:** `0dd7c8f`

**3. [Rule 1 — Bug] `pgrep -f mcp-gateway` matches the smoke probe itself**
- **Found during:** Task 2.1
- **Issue:** The probe's argv contains the literal string `mcp-gateway` as part of its bash command line, so `pgrep -f` matches itself plus the surrounding bash. False-positive `GATEWAY_PROC=1`.
- **Fix:** Switched to `pgrep -x mcp-gateway` (exact `comm` match — does not scan argv).
- **Commit:** `0dd7c8f`

**4. [Rule 1 — Bug] `pubs` count concatenated under `set -euo pipefail`**
- **Found during:** Task 2.1
- **Issue:** Inside `pubs=$(... | grep -o ... | wc -l || echo 0)`, `grep -o` exits 1 when there are no matches, pipefail propagates the failure, `wc -l` already printed `0`, then `|| echo 0` appended another `0` — yielding `pubs=0\n0` and a failed `assert_eq "$pubs" "0"`.
- **Fix:** Locally disabled `-e` and `pipefail` around the count block; stripped stray newlines/whitespace post-count. Same fix applied to both `smoke-local.sh` and `smoke-remote.sh`.
- **Commit:** `0dd7c8f`

**5. [Rule 1 — Bug] HTTP-listener vs token-file race in `smoke-remote.sh`**
- **Found during:** Task 2.2
- **Issue:** Phase 2's gateway writes the token file BEFORE binding the HTTP listener. The smoke script polled the token file then immediately curl'd `/healthz` — the listener wasn't accepting yet, curl returned `RC=7` (`couldn't connect`), and the assertions failed with code `000`. Additionally `curl ... || echo 000` appended a fallback after curl already emitted the connect-fail code, producing concatenated `000\n000` output.
- **Fix:** Added a 10s/200ms HTTP-readiness poll on `/healthz` (no auth — Phase 2 D-17 makes it open) before the auth assertions. Switched curl invocations from `... || echo 000` to `...) || HTTP=000` so we get either curl's code or the fallback, never both.
- **Commit:** `80d8ec5`

### No deviations from D-01..D-12 (decisions in 03-CONTEXT.md)

All locked decisions from `03-CONTEXT.md` are honored verbatim by the implementation. No architectural changes (no Rule 4 invocations).

## Threat-Model Dispositions Achieved

| Threat ID | Plan Disposition | Runtime Status |
|-----------|------------------|----------------|
| T-INF-EXPOSURE | mitigate | ✓ `smoke-remote.sh` step asserts `/mcp` returns 401 without auth (Bearer enforced); 0.0.0.0 bind warning printed in the ready-block |
| T-INF-LOCALMODE-LEAK | mitigate (3 defenses) | ✓ All three: `MCP_GATEWAY_ENABLED=0` exported in local mode (run_docker.sh); Dockerfile guard wraps gateway-start; smoke-local asserts `GATEWAY_PROC=none` AND `GATEWAY_PORT_LISTENING=no` |
| T-INF-TOKEN-PRINT | accept | Print block includes the documented warning ("shell scrollback may retain the bearer token; clear it before sharing your screen") |
| T-INF-STALE-TOKEN | mitigate | `rm -f $TOKEN_FILE` runs pre-`up` only when no container is already running (idempotence carve-out); 15s/200ms poll for fresh token; smoke-remote idempotence asserts same-token-on-re-run |
| T-INF-TOKEN-FLAG-HISTORY | accept | `--token=<value>` documented in `--help` |
| T-INF-PORT-COLLISION-DOS | mitigate | Pre-up `/dev/tcp/127.0.0.1/${MCP_GATEWAY_HOST_PORT}` probe emits the override hint when port is taken |

## Commits

Pre-resume (committed by prior executor agent):
- `c89b6ac` feat(03-01): add bash assertion helper library for Phase 3 smoke scripts
- `b3fd22a` test(03-01): add smoke-local.sh for D-12 / INF-05 no-regression backstop
- `b72bef4` test(03-01): add smoke-remote.sh for INF-01 + INF-02 + idempotence
- `12a9bbc` test(03-01): add smoke-all.sh orchestrator with shared trap-cleanup
- `cdfbc3b` feat(03-01): add ports block and MCP_GATEWAY_ENABLED/HOST_BIND/HOST_PORT passthrough to compose.yaml
- `cd9c1ff` feat(03-01): add compose.remote.yaml overlay with keepalive command for detached remote mode
- `9bb1c6e` feat(03-01): wrap gateway-start block in MCP_GATEWAY_ENABLED guard for local-mode no-leak (D-10/D-11)

Resumed-execution commits (this session):
- `ed9ad46` feat(03-01): add --remote/--token flag parsing, mode-driven env, post-up token print block to run_docker.sh (D-01..D-09)
- `75589cb` fix(03-01): correct REPO_ROOT depth in Phase 3 smoke scripts (4 levels up, not 3)
- `0dd7c8f` fix(03-01): smoke scripts — bash -c invocation, pgrep -x, pipefail-safe pubs count
- `80d8ec5` fix(03-01): smoke-remote — wait for gateway HTTP listener (race vs token file)

## Self-Check: PASSED

All claimed files exist on disk. All 11 commits resolve in `git log --all`.

- Files verified: `compose.remote.yaml`, `lib_assert.sh`, `smoke-local.sh`, `smoke-remote.sh`, `smoke-all.sh`, `03-01-SUMMARY.md`, `run_docker.sh`, `compose.yaml`, `Dockerfile`.
- Commits verified: `c89b6ac`, `b3fd22a`, `b72bef4`, `12a9bbc`, `cdfbc3b`, `cd9c1ff`, `9bb1c6e`, `ed9ad46`, `75589cb`, `0dd7c8f`, `80d8ec5`.
- End-to-end smoke evidence: both `smoke-local.sh` and `smoke-remote.sh` exited 0 with all `[pass]` lines printed (full transcripts captured above).

