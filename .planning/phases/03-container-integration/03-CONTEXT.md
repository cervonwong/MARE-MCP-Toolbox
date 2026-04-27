# Phase 3: Container Integration - Context

**Gathered:** 2026-04-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire the container so it operates in two distinct, opt-in modes from a single image: **local mode** (current `docker compose run --rm` interactive shell — inner Claude Code/Codex agents work exactly as in v1) and **remote mode** (`docker compose up -d` detached, MCP gateway port published to host, bearer token surfaced to user). One launcher script (`run_docker.sh`) selects the mode via flag. Existing local agent workflows must remain byte-identical to v1 (INF-05).

Out of scope (later phases): Claude Code / mastra.ai client config templates and end-to-end client workflows (Phase 4 — CLI-01..CLI-04), MCP Resources for case artifacts (Phase 4 — CLI-04), README/user-docs rewrite (treated as part of Phase 4 or a follow-up doc plan).

</domain>

<decisions>
## Implementation Decisions

### Dual-mode launch UX
- **D-01:** Mode selection lives on `run_docker.sh` as a flag. Default invocation `./run_docker.sh` keeps the existing v1 behavior verbatim: `docker compose run --rm kali` with an interactive `/bin/bash` shell. Adding `--remote` switches the script to `docker compose up -d` (detached, port published, token printed). One entrypoint, one script — no second launcher file.
- **D-02:** In remote mode the **full image** stays running detached. The inner `command` is overridden to a long-running keepalive (e.g. `tail -f /dev/null` or `sleep infinity`) so `agent-entrypoint.sh` can launch the gateway + idalib-mcp daemons; the user can `docker exec` into the container if they want a shell. Rationale: gateway tools shell out to the orchestrator scripts and the full Kali toolset, so a stripped "gateway-only" container would lose the analysis surface it exists to expose.
- **D-03:** Local mode (no `--remote`) does NOT publish any host port. Remote mode does. This makes INF-05 byte-identical: a v1 user who has never heard of the gateway sees zero behavioral or network change.

### Host port publishing
- **D-04:** Remote mode default host bind is **`0.0.0.0:8080:8080`** — published on all host interfaces. The user explicitly opts into remote mode via `--remote`, and the gateway requires bearer auth on every request (Phase 2 D-12, GW-04), so a LAN-reachable default is consistent with the "you asked for remote" intent. Users on shared networks can override to `127.0.0.1` via the env var below.
- **D-05:** Two separate env vars control host-side publishing: **`MCP_GATEWAY_HOST_BIND`** (default `0.0.0.0`) and **`MCP_GATEWAY_HOST_PORT`** (default `8080`). compose.yaml uses `"${MCP_GATEWAY_HOST_BIND:-0.0.0.0}:${MCP_GATEWAY_HOST_PORT:-8080}:${MCP_GATEWAY_PORT:-8080}"`. These are NEW env vars; they sit alongside Phase 2's existing `MCP_GATEWAY_PORT` (in-container port) and `MCP_GATEWAY_HOST` (in-container bind address) without collision.
- **D-06:** In remote mode the in-container gateway bind (`MCP_GATEWAY_HOST`) is forced to `0.0.0.0` so Docker's port mapping can reach it. (Container-side `127.0.0.1` is unreachable from the host even when `ports:` is published.) `run_docker.sh --remote` exports `MCP_GATEWAY_HOST=0.0.0.0` before invoking compose. In local mode this var is left to its Phase 2 default (`127.0.0.1`).

### Token discoverability
- **D-07:** After `./run_docker.sh --remote` brings the container up, the script polls for `workspace/.mcp-gateway-token` (with a short timeout, e.g. ~10s) and then prints a ready-to-use block to stdout containing: (a) the bearer token value, (b) a copy-pasteable `.mcp.json` snippet for Claude Code (`type: "http"`, `url`, `Authorization: Bearer <token>` header), and (c) a `curl` example hitting `/mcp` with the token. This is the user's first-time-onboarding moment.
- **D-08:** Token file location stays at `/agent/.mcp-gateway-token` (container) → `workspace/.mcp-gateway-token` (host) per Phase 2 D-17. No new mount, no symlink, no move. The print block is a UX layer on top of the existing file.
- **D-09:** Pinning the token is supported via TWO mechanisms: (a) the existing `MCP_GATEWAY_TOKEN` env var (Phase 2 D-16, already wired in compose.yaml), and (b) a new `--token=<value>` flag on `run_docker.sh` that simply exports `MCP_GATEWAY_TOKEN` for that invocation. The flag is pure ergonomics — same end state. If neither is set, gateway auto-generates and writes to the token file at startup.

### Gateway opt-out
- **D-10:** A new env var **`MCP_GATEWAY_ENABLED`** controls whether `agent-entrypoint.sh` starts the gateway daemon. `1` = start; `0` = skip. This refines Phase 2 D-09 (which said "always on at container boot") — the gateway is now mode-gated rather than absolute.
- **D-11:** Default value of `MCP_GATEWAY_ENABLED` is **mode-driven, set by `run_docker.sh`**: local mode (no flag) exports `MCP_GATEWAY_ENABLED=0`; `--remote` exports `MCP_GATEWAY_ENABLED=1`. Users can override either way by exporting the var explicitly before invoking the script. Inside `agent-entrypoint.sh`, the existing gateway-start block is wrapped in `if [ "${MCP_GATEWAY_ENABLED:-0}" = "1" ]; then ... fi`. idalib-mcp startup is NOT touched by this flag — it is required by inner agents in local mode and remains unconditional when IDA is installed (Phase 1).

### Backward-compat verification (INF-05)
- **D-12:** Phase 3 must include a smoke test that runs `./run_docker.sh` (no flag) and verifies (a) no host port is published (`docker compose ps` shows no `0.0.0.0:8080->8080/tcp`), (b) the inner shell behaves identically to v1 (`/agent`, environment, `claude --version`, `codex --version` succeed), and (c) `agent-entrypoint.sh` does not start the mcp-gateway daemon (no `mcp-gateway` process inside the container). Without this check, INF-05 is unverifiable.

### Claude's Discretion
- Exact wording / formatting of the token-and-snippet print block (D-07).
- Polling timeout and retry interval for waiting on the token file in `--remote` mode.
- Whether `--remote` should print a follow-up hint (`docker compose down` to stop, `docker compose logs -f kali` to tail) or leave that to README docs.
- Whether `run_docker.sh` should accept additional convenience flags (`--stop`, `--logs`, `--token` for printing the token of an already-running container) — planner can add if low-cost.
- Argument parsing style in `run_docker.sh` (manual `case` vs `getopts`).
- The `command:` override in compose.yaml for keepalive (`tail -f /dev/null` vs `sleep infinity` vs equivalent).
- Whether to extract a tiny `lib_compose_mode.sh` helper or keep the mode logic inline in `run_docker.sh`.
- Healthcheck on the kali service in compose.yaml (probe `127.0.0.1:8080/health` or similar) — useful but not required by INF-01..INF-05.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level specs
- `.planning/PROJECT.md` — Core value, dual-mode constraint, security/licensing constraints
- `.planning/REQUIREMENTS.md` — INF-01 (dual-mode entrypoint), INF-02 (compose port), INF-05 (no local-mode regressions)
- `.planning/ROADMAP.md` — Phase 3 goal, success criteria, depends-on Phase 2
- `CLAUDE.md` (project root) — Recommended Stack: Streamable HTTP gateway on port 8080, bearer auth, Docker network isolation; "Do NOT Use" list

### Prior phase context
- `.planning/phases/01-ida-pro-backend/01-CONTEXT.md` — idalib-mcp transport (`/mcp` on 127.0.0.1:8745), backend priority chain, "no silent fallback" policy (Phase 1 D-06)
- `.planning/phases/02-mcp-gateway/02-CONTEXT.md` — Gateway architecture, env vars (`MCP_GATEWAY_TOKEN/HOST/PORT/MAX_UPLOAD_MB/QUIET`), token file location (D-17), 127.0.0.1 default in-container bind (D-19), gateway-as-MCP-client model (D-06..D-10), pass-through tool surface (D-07)

### Existing code to modify / extend
- `compose.yaml` — Add `ports:` block driven by `MCP_GATEWAY_HOST_BIND`/`MCP_GATEWAY_HOST_PORT`; possibly add a keepalive `command:` override for `--remote` (or have `run_docker.sh` set it via `COMPOSE_*` overlay / `-f` chain). Existing env block already has `MCP_GATEWAY_*` vars wired (Phase 2).
- `run_docker.sh` — Add `--remote` and `--token=<value>` flag parsing; switch between `compose run --rm` (local) and `compose up -d` (remote); export mode-driven env (`MCP_GATEWAY_ENABLED`, `MCP_GATEWAY_HOST`, `MCP_GATEWAY_HOST_BIND`, `MCP_GATEWAY_HOST_PORT`); after `up -d`, wait for and print the token block.
- `Dockerfile` lines 304-328 (`agent-entrypoint.sh` gateway start block) — Wrap existing gateway start in `if [ "${MCP_GATEWAY_ENABLED:-0}" = "1" ]; then ... fi`. Default of `0` matches v1 behavior when env is absent (manual `docker run` users). Leave idalib-mcp block untouched.
- `Dockerfile` `ENTRYPOINT` / `CMD` (lines 366-367) — Confirm the entrypoint cleanly handles both `bash` (local) and a long-running keepalive (remote). Likely no change needed since CMD is overridden by compose.

### MCP / network references
- [MCP Transports spec (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — Streamable HTTP transport (already pinned in Phase 2)
- [Docker Compose `ports`](https://docs.docker.com/reference/compose-file/services/#ports) — Long-form vs short-form syntax, host bind interface
- [Docker Compose `profiles`](https://docs.docker.com/reference/compose-file/services/#profiles) — Considered but rejected; flag-on-script is simpler

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Existing argument plumbing in `run_docker.sh`** (line 202: `exec docker compose ... run --rm --pull never kali "$@"`): Shows how the script forwards positional args to the kali service. Phase 3 will branch BEFORE this exec line on `--remote`. Most of the script (image build, env setup, license seeding) is mode-agnostic and stays unchanged.
- **Phase 2 token file pattern** (`/agent/.mcp-gateway-token`, written by gateway at startup, world-readable as a regular file with 0600 perms owned by `agent`, surfaced on host via the `${HOST_PWD}:/agent` bind mount). The file appears ~immediately after gateway boot, so polling with a short timeout is reliable.
- **Existing daemon-start block** in `agent-entrypoint.sh` (Dockerfile lines 304-328): Already does `command -v mcp-gateway` check, port collision check, and nohup background start with gosu. Phase 3 only needs to wrap it in an `MCP_GATEWAY_ENABLED` guard — no rewrites.
- **Compose env var passthrough pattern** (compose.yaml lines 22-27): `MCP_GATEWAY_TOKEN` etc. listed without `=value` so they pass through from the host environment if set. New vars (`MCP_GATEWAY_ENABLED`, `MCP_GATEWAY_HOST_BIND`, `MCP_GATEWAY_HOST_PORT`) follow the same pattern.

### Established Patterns
- **Conditional behavior via env var with sane default**: `${VAR:-default}` shell expansion in compose.yaml and entrypoint scripts. Phase 3's `MCP_GATEWAY_ENABLED` and `MCP_GATEWAY_HOST_BIND` follow this.
- **License/state files surfaced through the workspace bind mount**: existing `${HOST_PWD}:/agent` mount means files written inside the container appear on the host at `workspace/<name>`. Token file already uses this — no new mount needed.
- **Daemon startup with port-collision guard**: `(echo > /dev/tcp/HOST/PORT)` test before nohup-launch. Same pattern is reused for both idalib-mcp and the gateway.
- **`run_docker.sh` reuses one image for many invocations**: Hash-tagged image build + convenience `:latest` tag. Mode switch is a runtime concern only; no rebuild needed.

### Integration Points
- **`compose.yaml`**: New `ports:` block (host bind + host port via env), new env vars listed (`MCP_GATEWAY_ENABLED`, `MCP_GATEWAY_HOST_BIND`, `MCP_GATEWAY_HOST_PORT`). The `command:` for keepalive in `--remote` mode is best handled by `run_docker.sh` setting it explicitly (e.g. `compose run` vs `compose up` already differ in command-attach behavior; `up` uses the image CMD which is `bash`. Need either a `command:` override on `up`, or a tiny secondary compose file `compose.remote.yaml` layered with `-f`).
- **`run_docker.sh`**: New `--remote` and `--token=<value>` flag parsing at the top (before the existing build logic). After build, branch:
  - Local: existing `exec docker compose run --rm` (unchanged)
  - Remote: `docker compose up -d`, then wait for token file, then print the snippet block
- **`Dockerfile` agent-entrypoint.sh**: Wrap gateway start in `MCP_GATEWAY_ENABLED` guard. No other changes.
- **Token print logic**: Lives in `run_docker.sh` post-`up` block (host-side bash). Reads `workspace/.mcp-gateway-token` (waits up to N seconds). Easy to keep as a plain function in the script.

</code_context>

<specifics>
## Specific Ideas

- The `--remote` first-run output should look approachable — something a user new to the project can paste straight into their host `.mcp.json` without reading docs. Roughly: a header line, the token, a fenced JSON block with the `.mcp.json` snippet, and a one-line curl smoke test.
- Tearing down the remote container should be a vanilla `docker compose down` — don't invent a new stop subcommand. The print block can mention this.
- "Local mode unchanged" is the strongest constraint: if there's any doubt whether a change to compose.yaml or `agent-entrypoint.sh` could leak into local mode, default to "no leak" and verify with the D-12 smoke test.
- Bearer token is the sole auth mechanism (Phase 2 D-12, D-18). Phase 3 should not add a second auth surface (e.g., per-user accounts, OAuth).
- The chosen 0.0.0.0 default in `--remote` mode (D-04) deviates from Phase 2 D-19's 127.0.0.1 default, but only at the host-publish boundary. The in-container default (Phase 2 D-19) stays 127.0.0.1 in local mode. The deviation is intentional and tied to the explicit `--remote` opt-in.

</specifics>

<deferred>
## Deferred Ideas

- **Healthcheck on the kali service** (compose.yaml `healthcheck:` probing `/mcp` or `/health`) — useful for orchestration, but neither INF-01 nor INF-02 requires it. Add to backlog.
- **`run_docker.sh --logs`, `--stop`, `--token` (standalone) convenience subcommands** — left to Claude's discretion / planner judgment. Not required for INF-01..INF-05.
- **Multi-container deployments** (multiple kali services on different ports) — out of scope; single-container model assumed.
- **IPv6 host bind** — out of scope; default to IPv4 (`0.0.0.0`).
- **Compose profiles for `local` vs `remote`** — considered and rejected in favor of a flag on `run_docker.sh`. If the script-flag approach proves awkward in practice, profiles can be revisited.
- **Claude Code / mastra.ai client config templates** — Phase 4 (CLI-01, CLI-02, CLI-03).
- **MCP Resources for case artifacts** — Phase 4 (CLI-04).
- **README rewrite covering the new `--remote` workflow** — treat as documentation work after Phase 4 (so docs cover both gateway-up and client-side config in one pass).
- **Reverting Phase 2 D-09 wording** ("gateway always-on at boot") — Phase 3 D-10/D-11 narrows this to mode-gated. Update PROJECT.md Key Decisions or REQUIREMENTS.md if needed during execute-phase, otherwise let the chained CONTEXT.md docs serve as the trail.

</deferred>

---

*Phase: 03-container-integration*
*Context gathered: 2026-04-27*
