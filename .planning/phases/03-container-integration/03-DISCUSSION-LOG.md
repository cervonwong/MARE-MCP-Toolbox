# Phase 3: Container Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-27
**Phase:** 03-container-integration
**Areas discussed:** Dual-mode launch UX, Host port publishing, Token discoverability, Gateway opt-out switch

---

## Dual-mode launch UX

### Q1: How should remote-mode (gateway-only, no inner shell) be invoked?

| Option | Description | Selected |
|--------|-------------|----------|
| Flag on run_docker.sh | `./run_docker.sh --remote` runs `docker compose up -d` with port publishing; no flag = current `run --rm` interactive shell. One entrypoint, mode selection via flag. | ✓ |
| Separate script | Keep `run_docker.sh` for local; add `run_docker_remote.sh` for detached gateway mode. | |
| Compose profiles only | User runs `docker compose --profile remote up -d` directly. No script change. | |

**User's choice:** Flag on run_docker.sh

### Q2: When a user runs `./run_docker.sh` (local agent mode, no flag), should the gateway port still be published to the host?

| Option | Description | Selected |
|--------|-------------|----------|
| No, ports only on --remote | Local mode = no host port published; gateway runs inside container only. Cleaner; matches INF-05 'unchanged'. | ✓ |
| Yes, always publish 127.0.0.1:8080 | Always publish to host loopback regardless of mode. Simpler compose.yaml. | |

**User's choice:** No, ports only on --remote

### Q3: In remote mode, what runs in the container — only the gateway daemon, or the full image?

| Option | Description | Selected |
|--------|-------------|----------|
| Full image, detached | `docker compose up -d` starts container with keepalive command while agent-entrypoint.sh launches gateway/idalib daemons. All tools available for analysis. | ✓ |
| Gateway-only container | Override command to just run mcp-gateway in foreground. Smaller surface, but loses Kali toolset. | |

**User's choice:** Full image, detached

---

## Host port publishing

### Q1: What host interface should `--remote` mode publish the gateway port to by default?

| Option | Description | Selected |
|--------|-------------|----------|
| 127.0.0.1 only | Default `127.0.0.1:8080:8080` — only host can reach gateway. Matches Phase 2 D-19. | |
| 0.0.0.0 (all interfaces) | Default `0.0.0.0:8080:8080` — any host on the network can reach gateway. | ✓ |

**User's choice:** 0.0.0.0 (all interfaces)
**Notes:** Deliberate deviation from Phase 2 D-19's conservative default. Justified by `--remote` being itself an explicit opt-in, plus mandatory bearer auth on every request. Override path provided via env var.

### Q2: How should host bind be overridden?

| Option | Description | Selected |
|--------|-------------|----------|
| Single env var with full mapping | `MCP_GATEWAY_PUBLISH=127.0.0.1:8080`. One knob, full flexibility. | |
| Separate host/port env vars | `MCP_GATEWAY_HOST_BIND=127.0.0.1` + `MCP_GATEWAY_HOST_PORT=8080`. | ✓ |
| Edit compose.yaml manually | No env override; user edits compose.yaml directly. | |

**User's choice:** Separate host/port env vars

### Q3: Should the in-container gateway listen address be aligned with how the port is published?

| Option | Description | Selected |
|--------|-------------|----------|
| Keep MCP_GATEWAY_HOST=0.0.0.0 in container | Force gateway to bind 0.0.0.0 inside container in remote mode so Docker's port mapping can reach it. | ✓ |
| Keep 127.0.0.1 inside, use docker network | Gateway binds 127.0.0.1 inside container; access via docker exec/socket only. Doesn't actually publish to host. | |

**User's choice:** Keep MCP_GATEWAY_HOST=0.0.0.0 in container (in remote mode)

---

## Token discoverability

### Q1: After `./run_docker.sh --remote`, how should the user discover the bearer token?

| Option | Description | Selected |
|--------|-------------|----------|
| Print after launch | Script waits for /agent/.mcp-gateway-token, prints it with copy-pasteable .mcp.json snippet and curl example. | ✓ |
| Print only the path | Just echo the path; user cats it themselves. | |
| Helper command only | Helper subcommand to print the token anytime; nothing on launch. | |
| Print after launch + helper command | Both. | |

**User's choice:** Print after launch (Recommended)

### Q2: Where should the host-visible token file live?

| Option | Description | Selected |
|--------|-------------|----------|
| workspace/.mcp-gateway-token (current) | Already implemented in Phase 2. Keep as-is. | ✓ |
| Move to repo root .mcp-gateway-token | Higher-visibility location next to compose.yaml. Requires extra mount. | |

**User's choice:** workspace/.mcp-gateway-token (current)

### Q3: When user wants to PIN the token, how is it set?

| Option | Description | Selected |
|--------|-------------|----------|
| MCP_GATEWAY_TOKEN env var | Already wired in compose.yaml from Phase 2 D-16. | ✓ |
| --token flag on run_docker.sh | Add `./run_docker.sh --remote --token=<value>`. | ✓ |
| Token file pre-created on host | If workspace/.mcp-gateway-token exists, use it. Implicit pinning. | |

**User's choice:** Both env var and flag (flag exports the env var for that invocation)
**Notes:** User selected "Other" with explicit "both 1 and 2". Implementation: `--token=<value>` simply sets `MCP_GATEWAY_TOKEN` for the script invocation — same end state, two ergonomic surfaces.

---

## Gateway opt-out switch

### Q1: Should there be a way to disable the gateway daemon at boot?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, MCP_GATEWAY_ENABLED env var | Set `MCP_GATEWAY_ENABLED=0` to skip gateway in agent-entrypoint.sh. | ✓ |
| No, gateway always starts | Phase 2 D-09 always-on; harmless on 127.0.0.1. | |
| Tie it to mode | Gateway only starts in `--remote` mode (script exports the flag). | |

**User's choice:** Yes, MCP_GATEWAY_ENABLED env var (mode-driven default per Q2)

### Q2: Under the chosen opt-out model, what should `./run_docker.sh` (no flag) do by default?

| Option | Description | Selected |
|--------|-------------|----------|
| Gateway off in local mode | Local mode skips gateway daemon. INF-05 = unchanged. | ✓ |
| Gateway on in local mode too | Gateway always running on 127.0.0.1:8080 inside container regardless of mode. | |

**User's choice:** Gateway off in local mode
**Notes:** Refines Phase 2 D-09 ("gateway always-on at boot") — gateway is now mode-gated. Local mode = OFF; `--remote` = ON. Users can override either way by exporting `MCP_GATEWAY_ENABLED` explicitly.

---

## Claude's Discretion

- Exact wording / formatting of the post-`--remote` token print block.
- Polling timeout/interval for waiting on the token file.
- Argument-parsing style in `run_docker.sh` (manual `case` vs `getopts`).
- Keepalive command for remote mode (`tail -f /dev/null` vs `sleep infinity`).
- Whether to add convenience subcommands (`--logs`, `--stop`, standalone `--token`).
- Whether to add a healthcheck to the kali service in compose.yaml.
- Whether to extract a helper script vs keep mode logic inline.

## Deferred Ideas

- Healthcheck on the kali service.
- Compose profiles for local vs remote (rejected; revisitable).
- Multi-container deployments and IPv6 host bind (out of scope).
- README rewrite covering `--remote` workflow → after Phase 4.
- Updating Phase 2 D-09 wording in PROJECT.md/REQUIREMENTS.md to reflect the mode-gated narrowing.
