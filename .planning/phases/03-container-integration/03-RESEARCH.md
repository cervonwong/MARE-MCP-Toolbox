# Phase 3: Container Integration - Research

**Researched:** 2026-04-27
**Domain:** Docker Compose dual-mode launch + bash launcher orchestration
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Dual-mode launch UX**
- **D-01:** Mode selection on `run_docker.sh` flag. Default = `docker compose run --rm kali` (interactive bash, byte-identical v1). `--remote` = `docker compose up -d`. One entrypoint, one script — no second launcher file.
- **D-02:** In remote mode the **full image** stays running detached. Inner `command` overridden to long-running keepalive (`tail -f /dev/null` or `sleep infinity`) so `agent-entrypoint.sh` can launch gateway + idalib-mcp daemons; user can `docker exec` for a shell.
- **D-03:** Local mode (no `--remote`) does NOT publish any host port. Remote mode does. INF-05 byte-identical: v1 user sees zero behavioral or network change.

**Host port publishing**
- **D-04:** Remote mode default host bind is **`0.0.0.0:8080:8080`** — published on all host interfaces. User explicitly opts in via `--remote`; bearer auth required on every request.
- **D-05:** Two new env vars: **`MCP_GATEWAY_HOST_BIND`** (default `0.0.0.0`) and **`MCP_GATEWAY_HOST_PORT`** (default `8080`). compose.yaml uses `"${MCP_GATEWAY_HOST_BIND:-0.0.0.0}:${MCP_GATEWAY_HOST_PORT:-8080}:${MCP_GATEWAY_PORT:-8080}"`.
- **D-06:** In remote mode `MCP_GATEWAY_HOST` (in-container bind) is forced to `0.0.0.0` so Docker's port mapping can reach it. `run_docker.sh --remote` exports `MCP_GATEWAY_HOST=0.0.0.0`. In local mode left to Phase 2 default (`127.0.0.1`).

**Token discoverability**
- **D-07:** After `./run_docker.sh --remote`, script polls for `workspace/.mcp-gateway-token` (~10s timeout) and prints to stdout: (a) bearer token, (b) ready-to-paste `.mcp.json` snippet, (c) `curl` example hitting `/mcp`.
- **D-08:** Token file location stays `/agent/.mcp-gateway-token` (container) → `workspace/.mcp-gateway-token` (host). No new mount.
- **D-09:** Token pinning: (a) existing `MCP_GATEWAY_TOKEN` env var, OR (b) new `--token=<value>` flag on `run_docker.sh` that exports `MCP_GATEWAY_TOKEN` for that invocation. If neither, gateway auto-generates.

**Gateway opt-out**
- **D-10:** New env var **`MCP_GATEWAY_ENABLED`** controls whether `agent-entrypoint.sh` starts the gateway daemon. `1` = start; `0` = skip. Refines Phase 2 D-09.
- **D-11:** Default of `MCP_GATEWAY_ENABLED` is **mode-driven by `run_docker.sh`**: local mode exports `=0`; `--remote` exports `=1`. Users can override via explicit env. Inside `agent-entrypoint.sh`, existing gateway-start block wrapped in `if [ "${MCP_GATEWAY_ENABLED:-0}" = "1" ]; then ... fi`. **idalib-mcp startup is NOT touched** by this flag — remains unconditional when IDA installed.

**Backward-compat verification (INF-05)**
- **D-12:** Phase 3 must include smoke test that runs `./run_docker.sh` (no flag) and verifies (a) no host port published, (b) inner shell behaves identically to v1 (`/agent`, env, `claude --version`, `codex --version` succeed), (c) `agent-entrypoint.sh` does not start mcp-gateway daemon.

### Claude's Discretion
- Exact wording / formatting of token-and-snippet print block (D-07).
- Polling timeout and retry interval for waiting on the token file in `--remote` mode.
- Whether `--remote` should print follow-up hints (`docker compose down`, `docker compose logs -f kali`) or leave to README.
- Whether `run_docker.sh` accepts additional convenience flags (`--stop`, `--logs`, `--token` for printing the token of an already-running container).
- Argument parsing style in `run_docker.sh` (manual `case` vs `getopts`).
- The `command:` override for keepalive (`tail -f /dev/null` vs `sleep infinity` vs equivalent).
- Whether to extract a tiny `lib_compose_mode.sh` helper or keep mode logic inline.
- Healthcheck on the kali service (probe `127.0.0.1:8080/health`) — useful but not required.

### Deferred Ideas (OUT OF SCOPE)
- Healthcheck on the kali service in compose.yaml — backlog.
- `run_docker.sh --logs`, `--stop`, `--token` (standalone) convenience subcommands — discretion / planner judgment.
- Multi-container deployments (multiple kali services on different ports) — single-container model.
- IPv6 host bind — IPv4 only.
- Compose profiles for `local` vs `remote` — rejected in favor of script flag.
- Claude Code / mastra.ai client config templates — Phase 4 (CLI-01..CLI-03).
- MCP Resources for case artifacts — Phase 4 (CLI-04).
- README rewrite covering `--remote` workflow — after Phase 4.
- Reverting Phase 2 D-09 wording.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INF-01 | Dual-mode entrypoint supports both local agent mode (existing) and remote MCP gateway mode (new) simultaneously | Standard pattern: single ENTRYPOINT script gates daemons via env var; CMD overridden by compose for remote mode keepalive (Section "Architecture Patterns"). |
| INF-02 | Docker Compose exposes gateway port (default 8080) with configurable mapping | `ports:` block uses `${MCP_GATEWAY_HOST_BIND:-0.0.0.0}:${MCP_GATEWAY_HOST_PORT:-8080}:${MCP_GATEWAY_PORT:-8080}` long-form syntax. `docker compose run` ignores `ports:` by default → no leak into local mode (Section "Compose run vs up port behavior"). |
| INF-05 | Existing local agent workflow (Claude Code/Codex inside container) continues working unchanged | `MCP_GATEWAY_ENABLED=0` in local mode skips gateway daemon; `compose run --rm` does not publish ports without `--service-ports`; D-12 smoke test verifies all three properties (Section "Backward-compat smoke test"). |
</phase_requirements>

## Summary

Phase 3 wires a single Docker image to operate in two opt-in modes from one launcher (`run_docker.sh`): default invocation = local interactive shell (v1-identical), `--remote` flag = detached gateway with host port published. The implementation surface is small: ~3 file edits (compose.yaml, run_docker.sh, agent-entrypoint.sh inside Dockerfile) plus a phase-local smoke test script.

The key technical guarantees come for free from Docker Compose semantics: **`docker compose run` does NOT publish ports defined in `ports:` unless `--service-ports` is passed** [VERIFIED: docs.docker.com/reference/cli/docker/compose/run/, GitHub issue 10138]. This means we can declare the `ports:` block unconditionally in `compose.yaml` and local mode will silently ignore it — no overlay file, no profile, no compose templating gymnastics needed for the port-publish guarantee.

The only real choice point is how to switch the container's `command` between interactive `bash` (local) and a keepalive (`tail -f /dev/null`) for remote. Three viable mechanisms exist; we recommend **explicit `command:` argument on `docker compose up`** (passed by `run_docker.sh` via the existing CLI without an overlay file) since it's the simplest and keeps the local-mode CMD untouched.

**Primary recommendation:** Implement `run_docker.sh --remote` as a branch BEFORE the existing `exec docker compose run` line. In the remote branch: export `MCP_GATEWAY_ENABLED=1`, `MCP_GATEWAY_HOST=0.0.0.0`, `MCP_GATEWAY_HOST_BIND`, `MCP_GATEWAY_HOST_PORT`, run `docker compose up -d` (compose's `ports:` block + the keepalive `command:` activate naturally), poll for `workspace/.mcp-gateway-token` with ~10s timeout, print the token block. Local branch: export `MCP_GATEWAY_ENABLED=0` and run the existing `compose run --rm` line unchanged.

## Standard Stack

### Core (already in image — no new installs needed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Docker Compose v2 | v2.x (CLI plugin) | Container orchestration | Already used in v1; ports/command/env-var-templating are stable APIs. [VERIFIED: docs.docker.com] |
| bash | 5.x | run_docker.sh launcher | Already the script's interpreter. `getopts` and manual `case` both work; manual `case` is preferred for `--long-flag=value` patterns. [ASSUMED based on shell-scripting common practice] |
| jq | optional | Parse `docker compose ps --format json` for smoke test | Available on Kali; not a hard requirement — bash string-grep fallback works. [ASSUMED] |

### Supporting (already in image)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `nohup` + bash subshells | builtin | Daemon launch in agent-entrypoint.sh | Already used by Phase 1 (idalib-mcp) and Phase 2 (mcp-gateway) — pattern unchanged. [VERIFIED: Dockerfile lines 285-322] |
| `gosu` | bundled in image | Drop privileges to `agent` user for daemons | Pattern reused from Phase 2. [VERIFIED: Dockerfile line 315] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Inline `command:` on `docker compose up` CLI | Overlay file `compose.remote.yaml` layered with `-f compose.yaml -f compose.remote.yaml` | Overlay file is cleaner if remote-mode ever grows beyond 1-2 differences (more env vars, different volumes), but for one `command:` override it's overkill. The script-driven approach keeps the compose.yaml a single source of truth. [VERIFIED: docs.docker.com/compose/how-tos/multiple-compose-files/merge/] |
| Inline `command:` on `docker compose up` CLI | Compose `profiles:` (`profile: ["remote"]` on a duplicate service block) | Profiles are explicitly rejected in CONTEXT.md (deferred — script-flag is simpler). |
| Inline `command:` on `docker compose up` CLI | Templated `command:` in compose.yaml gated by `${MCP_GATEWAY_ENABLED}` (e.g., `command: ${COMPOSE_COMMAND:-/bin/bash}`) | Compose **does** support env-var interpolation in `command:` (it's a string field with `${VAR}` expansion), but only as a single-string command (no array form). Risks subtle quoting bugs and ties two unrelated concerns (env var → command shape) together. [VERIFIED: docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/] |
| `tail -f /dev/null` keepalive | `sleep infinity` | Functionally identical. `tail -f /dev/null` is more portable across BusyBox/older bash; `sleep infinity` requires GNU coreutils ≥ 8.0. Kali has both. [ASSUMED based on common practice] Pick `tail -f /dev/null` for max compatibility. |
| Explicit `--remote` flag | `RUN_MODE=remote ./run_docker.sh` env var | Flag is more discoverable in `--help` and matches CONTEXT.md D-01. [Locked decision.] |

## Architecture Patterns

### Recommended Project Structure
```
run_docker.sh                  # ADD: --remote / --token=<value> flag parsing,
                               #      mode-driven env exports, post-up token print block
compose.yaml                   # ADD: ports: block (env-var driven),
                               #      MCP_GATEWAY_ENABLED / HOST_BIND / HOST_PORT env passthrough
Dockerfile (agent-entrypoint.sh, lines 304-328)
                               # ADD: wrap gateway-start block in
                               #      `if [ "${MCP_GATEWAY_ENABLED:-0}" = "1" ]; then ... fi`
.planning/phases/03-container-integration/
├── 03-CONTEXT.md              # (exists)
├── 03-RESEARCH.md             # (this file)
├── smoke-local.sh             # NEW: D-12 smoke test for local-mode no-regression
└── smoke-remote.sh            # NEW: smoke test for remote-mode port + token + curl
```

### Pattern 1: Compose `ports:` block driven by env vars

**What:** Declare the host port mapping with three env-var-substituted parts: host bind interface, host port, container port.

**When to use:** Always. The same block serves both modes — local mode silently ignores it (see "Compose run vs up port behavior" below).

**Example:**
```yaml
# Source: docs.docker.com/reference/compose-file/services/#ports
services:
  kali:
    # ... existing fields unchanged ...
    ports:
      - "${MCP_GATEWAY_HOST_BIND:-0.0.0.0}:${MCP_GATEWAY_HOST_PORT:-8080}:${MCP_GATEWAY_PORT:-8080}"
    environment:
      # ... existing vars ...
      - MCP_GATEWAY_ENABLED       # 0 (local default) | 1 (remote)
      - MCP_GATEWAY_HOST_BIND     # default 0.0.0.0 (host side)
      - MCP_GATEWAY_HOST_PORT     # default 8080 (host side)
```

**Notes:**
- Long-form vs short-form: short-form `"HOST:PORT:CONTAINER"` is sufficient and matches the existing compose.yaml style. Long-form is `target/published/host_ip` keys [VERIFIED: docs.docker.com/reference/compose-file/services/#ports].
- The triple-substitution string MUST be quoted because `:` is the YAML key-value delimiter.

### Pattern 2: `docker compose up -d` with command override (remote mode)

**What:** Pass `command:` override on the CLI so the container runs a long-running keepalive instead of exiting after the bash CMD.

**When to use:** Only in remote mode. Local mode keeps the existing `compose run --rm kali` invocation unchanged (no `command:` override needed — `bash` is already the CMD).

**Example:**
```bash
# Inside run_docker.sh remote-mode branch
exec docker compose \
  --project-directory "$SCRIPT_DIR" \
  -f "$SCRIPT_DIR/compose.yaml" \
  up -d --pull never \
  kali
# Note: compose.yaml already has command: ["/bin/bash"] — but in `up` mode with no
# stdin/tty attached, /bin/bash exits immediately and the container restarts/dies.
# Override the command on this invocation to keep it alive.
```

**Three options for the keepalive override:**

a) **CLI `--no-deps` is NOT a command override.** Compose v2 does NOT have a `--command` flag on `up`. The clean way is to either (i) override CMD in compose.yaml conditionally or (ii) use an overlay file.

b) **Recommended: minimal overlay file `compose.remote.yaml`** (single field):
   ```yaml
   # compose.remote.yaml
   services:
     kali:
       command: ["tail", "-f", "/dev/null"]
       tty: false
       stdin_open: false
   ```
   And in `run_docker.sh --remote` branch:
   ```bash
   docker compose -f "$SCRIPT_DIR/compose.yaml" -f "$SCRIPT_DIR/compose.remote.yaml" up -d kali
   ```
   This keeps local mode (which uses only `compose.yaml`) byte-identical and isolates remote-mode deltas to one file. [VERIFIED: docs.docker.com/compose/how-tos/multiple-compose-files/merge/ — single-value fields like `command` are replaced, not merged.]

c) **Alternative: pass `command:` via `COMPOSE_FILE` chain through env**, but this adds magic and is harder to debug. Do not use.

**Decision: prefer (b)** — overlay file. It's an explicit, reviewable artifact; the planner can grow it later (e.g., to add a healthcheck) without further script changes.

### Pattern 3: `agent-entrypoint.sh` gateway-start block guarded by env var

**What:** Wrap the existing gateway-start block (Dockerfile lines 304-328) in an `if` test, default `0` so manual `docker run` users without compose see no behavior change.

**When to use:** Always. Idempotent guard.

**Example:**
```bash
# Source: existing Dockerfile lines 304-328, with guard added
if [ "${MCP_GATEWAY_ENABLED:-0}" = "1" ]; then
  GATEWAY_HOST="${MCP_GATEWAY_HOST:-127.0.0.1}"
  GATEWAY_PORT="${MCP_GATEWAY_PORT:-8080}"
  GATEWAY_LOG="/tmp/mcp-gateway.log"
  if command -v mcp-gateway >/dev/null 2>&1; then
    if ! (echo > "/dev/tcp/${GATEWAY_HOST}/${GATEWAY_PORT}") >/dev/null 2>&1; then
      echo "[gateway] starting on ${GATEWAY_HOST}:${GATEWAY_PORT} (log: ${GATEWAY_LOG})"
      gosu "${AGENT_USER}" env HOME="${AGENT_HOME}" \
        MCP_GATEWAY_TOKEN="${MCP_GATEWAY_TOKEN:-}" \
        MCP_GATEWAY_HOST="${GATEWAY_HOST}" \
        MCP_GATEWAY_PORT="${GATEWAY_PORT}" \
        MCP_GATEWAY_MAX_UPLOAD_MB="${MCP_GATEWAY_MAX_UPLOAD_MB:-1024}" \
        MCP_GATEWAY_QUIET="${MCP_GATEWAY_QUIET:-}" \
        nohup mcp-gateway --host "${GATEWAY_HOST}" --port "${GATEWAY_PORT}" \
        >"${GATEWAY_LOG}" 2>&1 &
    else
      echo "[gateway] already listening on ${GATEWAY_HOST}:${GATEWAY_PORT} -- skipping"
    fi
  else
    echo "[gateway] warning: mcp-gateway not installed in this image" >&2
  fi
else
  echo "[gateway] MCP_GATEWAY_ENABLED!=1 -- skipping (local mode)"
fi
```

**`set -e` interaction:** The script begins with `set -euo pipefail` (Dockerfile line 262). The new outer `if` does NOT introduce regressions:
- The test `[ "${MCP_GATEWAY_ENABLED:-0}" = "1" ]` is evaluated by `[`, which returns 0 or 1. Inside an `if`, return-1 does NOT trip `set -e`. [VERIFIED: bash man page, "The shell does not exit if the command that fails is part of the command list immediately following an `until` or `while` keyword, part of the test in an `if` statement..."]
- The inner port-collision probe `if ! (echo > /dev/tcp/...)` is similarly safe — already in place since Phase 2 with `set -e` on.
- `nohup ... &` returns immediately (background launch); `set -e` does not see daemon failures. Daemon errors land in `/tmp/mcp-gateway.log` per existing pattern.

**Pitfall callout:** If the planner accidentally writes the outer `if` like `[ ... = "1" ] && ...` (short-circuit chain), then the `&&` chain fails fast under `set -e` when the LHS returns 1 in non-remote mode. Always use the explicit `if ... fi` structure.

### Pattern 4: `run_docker.sh` flag parsing + mode branch

**What:** Manual argument-parse loop at the top of the script (before the existing build logic) that sets `MODE` and exports the token if `--token=...` was passed.

**When to use:** Always.

**Example:**
```bash
# Source: idiomatic bash flag parsing (no upstream — this is project code)
MODE="local"
PASSTHROUGH=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) MODE="remote"; shift ;;
    --token=*) export MCP_GATEWAY_TOKEN="${1#--token=}"; shift ;;
    --token) export MCP_GATEWAY_TOKEN="$2"; shift 2 ;;
    --help|-h)
      cat <<USAGE
Usage: $0 [--remote] [--token=<value>] [-- <bash args for local mode>]
  (no flag)         local mode: docker compose run --rm kali
  --remote          remote mode: docker compose up -d kali, port published
  --token=<value>   pin gateway bearer token (sets MCP_GATEWAY_TOKEN)
USAGE
      exit 0 ;;
    --) shift; PASSTHROUGH=("$@"); break ;;
    *) PASSTHROUGH+=("$1"); shift ;;
  esac
done

# ... existing build logic unchanged ...

# Mode-driven env (defaults match CONTEXT D-11)
if [[ "$MODE" == "remote" ]]; then
  export MCP_GATEWAY_ENABLED="${MCP_GATEWAY_ENABLED:-1}"
  export MCP_GATEWAY_HOST="${MCP_GATEWAY_HOST:-0.0.0.0}"
  export MCP_GATEWAY_HOST_BIND="${MCP_GATEWAY_HOST_BIND:-0.0.0.0}"
  export MCP_GATEWAY_HOST_PORT="${MCP_GATEWAY_HOST_PORT:-8080}"
else
  export MCP_GATEWAY_ENABLED="${MCP_GATEWAY_ENABLED:-0}"
  # MCP_GATEWAY_HOST left to Phase 2 default (127.0.0.1)
fi
```

**Notes:**
- `${VAR:-default}` on the export lines lets users still pre-set the env var to override (CONTEXT D-11).
- Using a positional-arg passthrough array preserves existing behavior of `./run_docker.sh some_command --some-flag` for local mode.

### Anti-Patterns to Avoid

- **Dual launcher scripts.** `run_docker.sh` (local) + `run_docker_remote.sh` (remote) duplicates build logic and license seeding. CONTEXT D-01 explicitly rejects this.
- **Conditional `ports:` in compose.yaml.** Don't try to remove the `ports:` block in local mode — `docker compose run` already ignores it (see Pattern below).
- **Removing `set -e` in agent-entrypoint.sh.** Tempting if the new `if` block trips it, but it doesn't. Don't loosen error handling.
- **Forgetting to override `MCP_GATEWAY_HOST=0.0.0.0` in remote mode.** Phase 2 D-19 sets the in-container default to `127.0.0.1`. Without overriding it, the container is bound to localhost — Docker's port mapping cannot reach it from the host even with `ports:` published. The host-side `0.0.0.0:8080` would forward to `127.0.0.1:8080` *inside* the container, but localhost-bind only accepts loopback connections. The result: published port silently times out. **This is the most likely silent failure mode.**

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token rotation / persistence | Custom token-rewrite script in run_docker.sh | Existing gateway behavior: `MCP_GATEWAY_TOKEN` env wins, else auto-generate; file rewritten 0o600 every gateway start [VERIFIED: mcp-gateway/src/mcp_gateway/auth.py:27-48] | Already correct in Phase 2; just read the file. |
| Host-port detection in smoke test | Parsing `docker ps` text output with sed/awk | `docker compose ps --format json` + jq (or bash grep on `Publishers` field) [VERIFIED: docs.docker.com/reference/cli/docker/compose/ps/] | Stable JSON schema; survives Docker Compose minor-version changes. |
| Dual-mode entrypoint with inner `mode` argument | `agent-entrypoint.sh local` vs `agent-entrypoint.sh remote` | Single entrypoint guarded by `MCP_GATEWAY_ENABLED` env var | Simpler, no command-shape change; matches existing daemon-guard idiom (idalib-mcp port probe). |
| Compose-file templating engine (envsubst, jinja, etc.) | Generating compose.yaml from a template | Native Docker Compose env-var interpolation `${VAR:-default}` [VERIFIED: docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/] | Compose has had this since v1; no template step needed. |
| Polling for token file with custom timeout machinery | Bash loop with timer math | Standard pattern: `for i in $(seq 1 100); do ... sleep 0.1; done` (~10s, 100 iterations × 100ms) | Trivial; no library needed. |

**Key insight:** Compose's `run` vs `up` semantics already give us most of the dual-mode behavior for free. The script's job is to choose between them and surface the token; the gateway already handles the token lifecycle correctly.

## Compose `run` vs `up` Port Behavior (critical for INF-05)

**This is the cornerstone of the local-mode no-leak guarantee. Verify in research, do NOT assume.**

[VERIFIED: docs.docker.com/reference/cli/docker/compose/run/ and GitHub issue docker/compose#10138]

| Command | Default port behavior |
|---------|----------------------|
| `docker compose up [-d]` | **All `ports:` published.** |
| `docker compose run --rm <svc>` | **No `ports:` published unless `--service-ports` flag is passed.** |
| `docker compose run --service-ports <svc>` | All `ports:` published. |

**Quote from Docker docs:** *"When you use `docker compose run` to start a service, by default no service ports get published to the host."* [docs.docker.com/reference/cli/docker/compose/run/]

**Implication for Phase 3:** Declaring `ports:` in `compose.yaml` is SAFE. Local mode (`compose run --rm`) ignores it; remote mode (`compose up -d`) honors it. No conditional compose file, no overlay required just for the port — the overlay is only for the `command:` keepalive.

**Caveat (`depends_on`):** If the kali service had `depends_on:` on another service with its own `ports:`, that dependency's ports WOULD publish even under `compose run`. [VERIFIED: GitHub issue docker/compose#10138.] The current compose.yaml has no `depends_on`, so this is not a concern. **Rule for the planner:** if Phase 3+ ever adds a sidecar service with ports, re-evaluate.

**Smoke-test assertion that proves this:**
```bash
docker compose ps --format json kali | jq '[.[] | .Publishers[]?] | length'
# Expected: 0 in local mode, 1 in remote mode
```

## Token File Race & Polling

**Question:** What's the minimum reliable polling pattern for `run_docker.sh` to wait for `workspace/.mcp-gateway-token` post-`up -d`?

**Findings:**
- Gateway writes token at startup, before binding the HTTP listener. [VERIFIED: mcp-gateway/src/mcp_gateway/auth.py:27-48 — `load_or_generate_token()` is called before `Server.run()`.]
- Token file is opened with `O_TRUNC|O_CREAT|O_WRONLY` mode `0o600` — **always rewritten on every gateway start** [VERIFIED: auth.py:36].
- File contents: token + `\n` (one line, no surrounding whitespace beyond the trailing newline).
- Path on host: `${HOST_PWD}/.mcp-gateway-token` = `<repo>/workspace/.mcp-gateway-token`.

**Stale-file behavior:**
- If a previous run left a token file and `MCP_GATEWAY_TOKEN` is now unset, the gateway generates a NEW token and **overwrites the file**. So the token printed by the script always matches the live gateway. ✓
- If a previous run is still running (compose detects the container exists and is up), `docker compose up -d` is a no-op — the gateway is NOT restarted, and the existing token file is untouched. The script should detect this case and reprint the existing token instead of waiting for a new one. (Idempotence — see below.)

**Recommended polling:**
```bash
TOKEN_FILE="$HOST_PWD/.mcp-gateway-token"
DEADLINE=$(($(date +%s) + 15))   # 15-second budget; gateway boot ~2-5s typical
while [[ ! -s "$TOKEN_FILE" && $(date +%s) -lt $DEADLINE ]]; do
  sleep 0.2
done
if [[ ! -s "$TOKEN_FILE" ]]; then
  echo "[error] gateway token did not appear at $TOKEN_FILE within 15s" >&2
  echo "[error] check: docker compose logs kali" >&2
  exit 1
fi
TOKEN=$(< "$TOKEN_FILE")
TOKEN="${TOKEN%$'\n'}"  # strip trailing newline
```

**Why 15s, not 10s:** Gateway boot includes backend detection + (possibly) backend MCP subprocess spawn + Starlette server startup. On a cold start with idalib-mcp also booting, 5-10s is realistic. 15s is conservative without being annoying. Discretion item per CONTEXT.md.

**Why `[ -s file ]` and not `[ -f file ]`:** A 0-byte file (e.g., gateway crashed mid-write) would falsely satisfy `-f`. `-s` requires non-zero size.

## Idempotence and Re-runs

**Scenario:** User runs `./run_docker.sh --remote` twice in a row.

**Behavior:**
- First call: container does not exist → `docker compose up -d` creates and starts it; gateway boots, token file written; script polls, prints block.
- Second call: container exists and is running → `docker compose up -d` is a no-op (compose detects no changes; logs `Container kali Running`); gateway is unchanged; token file is unchanged.

**Recommended UX:**
```bash
# Detect already-running kali container
RUNNING=$(docker compose ps --format json kali | jq -r '.[] | select(.State == "running") | .Name' | head -1)
if [[ -n "$RUNNING" ]]; then
  echo "[info] kali container already running ($RUNNING) — reprinting token"
  # Read existing token file and print block (skip polling)
else
  docker compose up -d kali
  # poll for token file (see above)
fi
# Either way, print the block
```

**Edge case — token file exists but container is NOT running:** Stale file from a previous `compose down` run. The script's polling will succeed immediately and print the OLD token, which is wrong. Mitigation: after `compose up -d`, wait for the file's mtime to be newer than the script start time, OR delete the file before `up -d`:
```bash
# Pre-up: clear any stale token file so we wait for the fresh one
rm -f "$TOKEN_FILE"
docker compose up -d kali
# poll (now we know any file we see is fresh)
```
**Recommendation:** Delete pre-up. Simpler and removes ambiguity.

## Common Pitfalls

### Pitfall 1: Container-side bind=127.0.0.1 with host-side port=0.0.0.0

**What goes wrong:** User runs `./run_docker.sh --remote`, sees the token, tries `curl http://localhost:8080/mcp` from the host → connection refused or hang.

**Why it happens:** `MCP_GATEWAY_HOST` (in-container bind) defaults to `127.0.0.1` from Phase 2. If `run_docker.sh --remote` doesn't override it, the gateway listens only on the container's loopback. Docker's `-p 0.0.0.0:8080:8080` forwards traffic to `127.0.0.1:8080` *inside* the container — but a 127.0.0.1-bound socket only accepts connections from the same loopback interface. Docker's forwarded traffic appears to come from the docker0 bridge, NOT from the container's own loopback, so the bind rejects the SYN.

**How to avoid:** `run_docker.sh --remote` **MUST** export `MCP_GATEWAY_HOST=0.0.0.0` before invoking compose. CONTEXT.md D-06 mandates this explicitly. Smoke test should verify by checking the gateway log for `starting on 0.0.0.0:8080`.

**Warning signs:** `curl` hangs or returns connection-refused. `docker compose logs kali | grep '\[gateway\] starting'` shows `127.0.0.1:8080` instead of `0.0.0.0:8080`.

### Pitfall 2: Port already published on host (8080 in use by another process)

**What goes wrong:** `docker compose up -d` fails with `bind: address already in use`.

**Why it happens:** Common dev-environment collision. Port 8080 is heavily contested.

**How to avoid:** The error from Docker is clear; no need to pre-empt it in `run_docker.sh`. But the script can detect and emit a friendly hint:
```bash
if (echo > /dev/tcp/127.0.0.1/${MCP_GATEWAY_HOST_PORT:-8080}) >/dev/null 2>&1; then
  echo "[warn] something is already listening on host port ${MCP_GATEWAY_HOST_PORT:-8080}"
  echo "[warn] override with: MCP_GATEWAY_HOST_PORT=8081 ./run_docker.sh --remote"
fi
```

**Warning signs:** Pre-up port probe succeeds → port is taken.

### Pitfall 3: 0.0.0.0 default on shared LAN

**What goes wrong:** User on a coffee-shop wifi runs `--remote`, gateway is now reachable from anyone on the same subnet. Bearer auth protects against unauthenticated access, but the *existence* of the service is fingerprintable.

**Why it happens:** D-04 chooses `0.0.0.0` as the explicit-opt-in default.

**How to avoid:** The token-print block SHOULD include a one-liner warning, e.g.:
```
⚠ Gateway is published on all host interfaces (0.0.0.0:8080).
  On shared/untrusted networks, restrict with:
    MCP_GATEWAY_HOST_BIND=127.0.0.1 ./run_docker.sh --remote
```

**Warning signs:** None at runtime — this is a deployment-config concern.

### Pitfall 4: `compose run` vs `compose up` env-var visibility

**What goes wrong:** `MCP_GATEWAY_ENABLED=0` exported in `run_docker.sh` for local mode doesn't reach the container, gateway daemon starts in local mode, smoke test fails.

**Why it happens:** Compose only forwards env vars that are listed in the service's `environment:` block (without `=value`, this means "pass through from host env if set"). [VERIFIED: docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/]

**How to avoid:** Add `MCP_GATEWAY_ENABLED`, `MCP_GATEWAY_HOST_BIND`, `MCP_GATEWAY_HOST_PORT` to compose.yaml's `environment:` block alongside the existing Phase 2 vars.

**Warning signs:** Smoke test (D-12) catches this directly.

### Pitfall 5: TTY/stdin in remote mode

**What goes wrong:** With `stdin_open: true` + `tty: true` in compose.yaml (current values), `docker compose up -d` may behave oddly (warnings about TTY allocation in detached mode).

**Why it happens:** Those flags are appropriate for `compose run` (interactive shell) but spurious for `up -d`.

**How to avoid:** Set `tty: false` and `stdin_open: false` in `compose.remote.yaml` overlay (alongside the keepalive `command:`). Local mode keeps the original values from compose.yaml.

**Warning signs:** `docker compose up -d` emits a warning `the input device is not a TTY`. Container still runs, but it's noise.

### Pitfall 6: Smoke test running while another local-mode container is up

**What goes wrong:** Test runs `./run_docker.sh` (local mode) while a previous remote-mode container is still up → `compose run` creates a SECOND container instance, may conflict on volume locks or port (if 8080 is reused).

**Why it happens:** `compose run` and `compose up` use different container instances (run creates one-off containers).

**How to avoid:** Smoke test runner should `docker compose down` first to ensure clean state.

**Warning signs:** Test sees stale containers in `docker compose ps`.

## Code Examples

### Example 1: Token print block (D-07)

```bash
# Source: project-specific UX design (CONTEXT.md D-07 + Claude's discretion on wording)
print_remote_ready_block() {
  local token="$1"
  local host_port="${MCP_GATEWAY_HOST_PORT:-8080}"
  local host_bind="${MCP_GATEWAY_HOST_BIND:-0.0.0.0}"
  local display_host
  if [[ "$host_bind" == "0.0.0.0" ]]; then
    display_host="localhost"
  else
    display_host="$host_bind"
  fi
  cat <<READY

═══════════════════════════════════════════════════════════════════
  MARE-MCP-Toolbox Gateway is ready
═══════════════════════════════════════════════════════════════════

  URL:    http://${display_host}:${host_port}/mcp
  Token:  ${token}

  Claude Code .mcp.json snippet:
  ──────────────────────────────────────────────────────────────────
  {
    "mcpServers": {
      "mare-toolbox": {
        "type": "http",
        "url": "http://${display_host}:${host_port}/mcp",
        "headers": {
          "Authorization": "Bearer ${token}"
        }
      }
    }
  }
  ──────────────────────────────────────────────────────────────────

  Smoke test:
    curl -s -H "Authorization: Bearer ${token}" \\
      http://${display_host}:${host_port}/healthz

  Logs:   docker compose logs -f kali
  Stop:   docker compose down

READY
  if [[ "$host_bind" == "0.0.0.0" ]]; then
    cat <<WARN
  ⚠  Gateway is published on ALL host interfaces (0.0.0.0:${host_port}).
     On shared / untrusted networks, restrict with:
       MCP_GATEWAY_HOST_BIND=127.0.0.1 ./run_docker.sh --remote

WARN
  fi
}
```

### Example 2: D-12 smoke test (local mode no-regression)

```bash
#!/usr/bin/env bash
# .planning/phases/03-container-integration/smoke-local.sh
# Verifies INF-05: ./run_docker.sh (no flag) produces v1-identical behavior.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)"

cd "$SCRIPT_DIR"
docker compose -f compose.yaml down --remove-orphans >/dev/null 2>&1 || true

# Run a non-interactive command in local mode (passes through args).
echo "[smoke] running v1-baseline assertions inside container..."
output=$(./run_docker.sh -c '
  set -e
  echo "PWD=$(pwd)"
  echo "USER=$USER"
  echo "HOME=$HOME"
  echo "CLAUDE_VERSION=$(claude --version 2>&1)"
  echo "CODEX_VERSION=$(codex --version 2>&1 || echo MISSING)"
  echo "GATEWAY_PROC=$(pgrep -f mcp-gateway || echo none)"
  echo "GATEWAY_PORT_LISTENING=$(echo > /dev/tcp/127.0.0.1/8080 2>/dev/null && echo yes || echo no)"
') || true
echo "$output"

# Assertions
echo "$output" | grep -qE '^PWD=/agent$'                  || { echo "[fail] cwd != /agent"; exit 1; }
echo "$output" | grep -qE '^USER=agent$'                  || { echo "[fail] USER != agent"; exit 1; }
echo "$output" | grep -qE '^GATEWAY_PROC=none$'           || { echo "[fail] mcp-gateway started in local mode"; exit 1; }
echo "$output" | grep -qE '^GATEWAY_PORT_LISTENING=no$'   || { echo "[fail] gateway port reachable in local mode"; exit 1; }
echo "$output" | grep -qE '^CLAUDE_VERSION='              || { echo "[fail] claude --version missing"; exit 1; }

# Host-side: no published port
PUBS=$(docker compose -f compose.yaml ps --format json kali 2>/dev/null \
  | jq -r '[.[]?.Publishers // [] | .[]] | length' 2>/dev/null || echo 0)
[[ "$PUBS" -eq 0 ]] || { echo "[fail] $PUBS host ports published in local mode"; exit 1; }

echo "[pass] local-mode smoke test green (D-12)"
```

### Example 3: smoke-remote.sh (port + token + curl)

```bash
#!/usr/bin/env bash
# .planning/phases/03-container-integration/smoke-remote.sh
# Verifies INF-01 + INF-02: ./run_docker.sh --remote publishes port and prints valid token.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
cd "$SCRIPT_DIR"

docker compose -f compose.yaml down --remove-orphans >/dev/null 2>&1 || true

echo "[smoke] starting remote mode..."
./run_docker.sh --remote >/tmp/run_docker_remote.out 2>&1 || {
  echo "[fail] run_docker.sh --remote exited non-zero:"
  cat /tmp/run_docker_remote.out
  exit 1
}

# Token file must exist
TOKEN_FILE="workspace/.mcp-gateway-token"
[[ -s "$TOKEN_FILE" ]] || { echo "[fail] no token file at $TOKEN_FILE"; exit 1; }
TOKEN=$(< "$TOKEN_FILE")
TOKEN="${TOKEN%$'\n'}"

# Token block must appear in output
grep -q "Bearer ${TOKEN}\|Token:  ${TOKEN}" /tmp/run_docker_remote.out \
  || { echo "[fail] token not printed by script"; cat /tmp/run_docker_remote.out; exit 1; }

# Host port must be published
PUBS=$(docker compose ps --format json kali | jq -r '[.[]?.Publishers // [] | .[]] | length')
[[ "$PUBS" -ge 1 ]] || { echo "[fail] no host port published in remote mode"; exit 1; }

# Bearer auth: bare request rejected, authenticated accepted
HTTP=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/mcp || echo 000)
[[ "$HTTP" == "401" ]] || echo "[warn] /mcp without auth got $HTTP (expected 401)"

HTTP=$(curl -s -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8080/healthz || echo 000)
[[ "$HTTP" == "200" ]] || { echo "[fail] /healthz with auth got $HTTP (expected 200)"; exit 1; }

# Cleanup
docker compose down >/dev/null 2>&1 || true
echo "[pass] remote-mode smoke test green"
```

### Example 4: compose.remote.yaml overlay

```yaml
# Source: docs.docker.com/compose/how-tos/multiple-compose-files/merge/
# Layered with: docker compose -f compose.yaml -f compose.remote.yaml up -d
services:
  kali:
    command: ["tail", "-f", "/dev/null"]
    tty: false
    stdin_open: false
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `docker-compose` (v1, Python) | `docker compose` (v2, Go plugin) | 2023 | All commands and YAML syntax compatible. Project already uses v2. [VERIFIED: docs.docker.com] |
| Compose `version: '3.8'` top-level field | Omit `version` (current Compose Spec is unversioned) | Compose Spec adoption (2021+) | Project's compose.yaml already has no `version` line. Continue this. [VERIFIED: docs.docker.com/reference/compose-file/version-and-name/] |
| Compose `links:` for inter-service comms | Default network + service name DNS | 2018+ | Not relevant to single-service compose.yaml here. |
| SSE transport for MCP | Streamable HTTP (Protocol 2025-03-26) | June 2025 | Already pinned in Phase 2; clients fall back to SSE. [VERIFIED: CLAUDE.md] |

**Deprecated/outdated:**
- `links:`, `version:` top-level field, `docker-compose` (hyphen) CLI — none used here.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Kali base image has `tail` available (it does — coreutils) | Architecture Patterns | Negligible. `sleep infinity` is an alternative. |
| A2 | Gateway boot completes within 15 seconds in remote mode | Token File Race & Polling | Smoke test would catch via timeout; planner can extend if observed slow. |
| A3 | Compose v2 `--format json` `Publishers` field is stable across point releases | Smoke test, Pitfalls | Field has been in compose ps JSON since v2.x; low risk. Fallback: parse text output. |
| A4 | Manual `case` argument parsing is preferred over `getopts` for `--long-flag=value` | Pattern 4 | Stylistic; either works. |
| A5 | The 0.0.0.0 LAN-exposure warning belongs in the print block (not just docs) | Code Example 1 | Discretion item per CONTEXT.md; planner can move to README. |
| A6 | Pre-deleting the token file before `up -d` is preferable to mtime-based detection | Idempotence | Both work; pre-delete is simpler. |

## Open Questions

1. **Should `run_docker.sh` ever run `compose down` automatically?**
   - What we know: idempotence section recommends NOT auto-downing — surprising for users.
   - What's unclear: should there be a `--restart` flag that forces a fresh container?
   - Recommendation: defer to Claude's discretion (CONTEXT lists `--stop` etc. as discretionary). Don't add unless needed by smoke test design.

2. **Does the smoke-test runner go in `Makefile`, a phase-local script, or `run_docker.sh --test`?**
   - What we know: CONTEXT.md "Claude's Discretion" allows convenience flags.
   - Recommendation: phase-local scripts in `.planning/phases/03-container-integration/smoke-{local,remote}.sh`, executable from a top-level `Makefile` target if one already exists. Keep them OUT of `run_docker.sh` to preserve that script's single responsibility.

3. **Should `compose.remote.yaml` live in repo root or in a subdir?**
   - Recommendation: repo root, alongside `compose.yaml`. Convention is for sibling overlay files.

## Environment Availability

> Phase 3 is purely launcher/wiring work. The container image is already built and contains all needed binaries from Phases 1 and 2.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `docker` CLI v2 with `compose` plugin | All `run_docker.sh` invocations | ✓ (v1 already requires it) | 20.10+ / compose v2.x | — |
| `bash` ≥ 4 | `run_docker.sh` | ✓ | system bash | — |
| `jq` (host-side) | Smoke tests parsing `compose ps --format json` | ✓ on most dev hosts | any | bash text parsing of compose ps output |
| `curl` (host-side) | Smoke test `/healthz` probe | ✓ ubiquitous | any | `wget` |
| `tail` / `sleep infinity` (container) | `compose.remote.yaml` keepalive | ✓ Kali base has both | coreutils | each is the other's fallback |
| `pgrep` (container) | D-12 smoke test gateway-not-running check | ✓ Kali base has procps | any | `ps -ef \| grep mcp-gateway \| grep -v grep` |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** `jq` (rare on minimal hosts) — fallback is bash grep on `Publishers` substring.

## Validation Architecture

> Per `.planning/config.json` `workflow.nyquist_validation: true` — this section is mandatory.
> The orchestrator generates VALIDATION.md from this section.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | bash + standard POSIX tools (no test framework) |
| Config file | none — phase-local scripts |
| Quick run command | `bash .planning/phases/03-container-integration/smoke-local.sh` |
| Full suite command | `bash .planning/phases/03-container-integration/smoke-local.sh && bash .planning/phases/03-container-integration/smoke-remote.sh` |

Existing project test framework: pytest under `mcp-gateway/tests/` — used for Phase 2 unit/integration tests of the gateway code itself. Phase 3 changes are bash/YAML/Dockerfile only; no Python tests apply directly. Smoke tests are integration-level and use bash assertions.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INF-01 | Dual-mode entrypoint: gateway daemon starts in remote, skipped in local | integration (smoke) | `bash smoke-remote.sh && bash smoke-local.sh` | ❌ Wave 0 (both) |
| INF-02 | Gateway port published with configurable mapping | integration (smoke) | `bash smoke-remote.sh` (assertion: `Publishers \| length >= 1`) + override test: `MCP_GATEWAY_HOST_PORT=8081 bash smoke-remote.sh` | ❌ Wave 0 |
| INF-05 | Local agent workflow byte-identical to v1 | integration (smoke) | `bash smoke-local.sh` (assertions: cwd, USER, claude --version, gateway absent, no host port) | ❌ Wave 0 |

**Per-task assertions:**
- compose.yaml edit task: `docker compose config -q` (validates YAML + interpolation succeeds) — runs in <1s.
- agent-entrypoint.sh edit task: shellcheck run on the heredoc, then `docker buildx build` quick rebuild and `docker run --rm -e MCP_GATEWAY_ENABLED=1 ... agent-entrypoint.sh` dry test.
- run_docker.sh edit task: shellcheck + `bash -n run_docker.sh` syntax check.

### Sampling Rate
- **Per task commit:** `bash -n run_docker.sh && docker compose config -q` (~2s)
- **Per wave merge:** `bash smoke-local.sh` (~30s; spins up the container once)
- **Phase gate:** `bash smoke-local.sh && bash smoke-remote.sh` full suite (~90s)

### Wave 0 Gaps
- [ ] `.planning/phases/03-container-integration/smoke-local.sh` — covers INF-05 (and INF-01 negative-case: gateway must NOT start)
- [ ] `.planning/phases/03-container-integration/smoke-remote.sh` — covers INF-01 (positive case) + INF-02 (port + override)
- [ ] `.planning/phases/03-container-integration/compose.remote.yaml` — overlay file required by smoke-remote
- [ ] No new Python test framework needed (mcp-gateway/tests/ untouched by Phase 3)

### Manual / un-automatable
- The 0.0.0.0 LAN-exposure warning is UX text; visual review only (no automated assertion needed).
- The Claude Code `.mcp.json` snippet's correctness against an actual host-side Claude Code session is Phase 4 scope — out of scope for Phase 3.

## Security Domain

> `security_enforcement` is not explicitly disabled in `.planning/config.json` — included by default.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Phase 2 already implements bearer-token auth (`BearerAuthMiddleware`, `hmac.compare_digest`) — Phase 3 does NOT add or weaken auth |
| V3 Session Management | no | Single-user gateway; no sessions per-client beyond MCP transport |
| V4 Access Control | yes (network layer) | Bearer required on `/mcp` and `/upload`; `/healthz` open by design (Phase 2 D-17). Phase 3 publishing the port does not change this. |
| V5 Input Validation | no (Phase 3 has no new request handlers) | Phase 2 owns all request validation |
| V6 Cryptography | partial | Phase 3 surfaces the bearer token in stdout; do NOT log to files outside `/agent` |
| V14 Configuration | yes | Default `0.0.0.0` host bind is a deliberate, documented exposure choice (D-04). Warning in print block. |

### Known Threat Patterns for {bash launcher + Docker host port}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Token leakage via shell history when `--token=<value>` is used | Information Disclosure | The flag exports `MCP_GATEWAY_TOKEN`; shell history MAY capture the value. Document as a known tradeoff; recommend `MCP_GATEWAY_TOKEN=$(...) ./run_docker.sh --remote` or pre-export pattern. |
| Token leakage via `docker compose logs` (printed by gateway) | Information Disclosure | Gateway respects `MCP_GATEWAY_QUIET=1` (Phase 2 D-17) — but the script's print block is the primary surface and is intentional. Mitigation: do NOT add the print block to syslog or shared log files. |
| LAN exposure on `0.0.0.0` default | Spoofing / Information Disclosure | Bearer auth on every protected endpoint (Phase 2). Print-block warning recommends `MCP_GATEWAY_HOST_BIND=127.0.0.1` for shared networks. |
| Port collision on host:8080 → user thinks gateway is down, restarts repeatedly, generating tokens | Denial of Service / DoS-self | Pre-up port probe in `run_docker.sh` emits a friendly error before `compose up`. |
| `docker compose down` while gateway is processing a long upload | Tampering / Data integrity | Gateway uploads are atomic per-sha256 dir (Phase 2 D-13); partial uploads do not corrupt the dedupe store. Phase 3 does not change this. |
| Token file world-readable via host bind mount | Information Disclosure | File is `0o600` and owned by `agent` UID. Host's UID mapping must match (existing `run_docker.sh` pattern). [VERIFIED: mcp-gateway/src/mcp_gateway/auth.py:36,44] |

### Phase 3 specific security notes
- The `--remote` flag is an EXPLICIT user opt-in for network exposure (D-04). The default `./run_docker.sh` invocation has zero network surface.
- No new credentials, secrets, or cryptographic primitives are introduced. Phase 3 only chooses *when* the existing gateway runs.
- The `compose.remote.yaml` overlay is checked into git and contains no secrets.

## Project Constraints (from CLAUDE.md)

The project root `CLAUDE.md` declares a Recommended Stack and a "Do NOT Use" list. Phase 3 must comply:

| Constraint | How Phase 3 Honors It |
|-----------|------------------------|
| Custom FastMCP gateway (not mcp-proxy) | Phase 3 does not change the gateway implementation. |
| Bearer token static auth (not OAuth 2.1) | Token lifecycle unchanged from Phase 2. |
| Streamable HTTP transport (not deprecated SSE) | Endpoint paths and protocol unchanged. |
| Docker network isolation (bind to localhost by default) | Local mode keeps `127.0.0.1` (Phase 2 default). Remote mode `0.0.0.0` is explicit user opt-in via `--remote`. |
| Do NOT use `mcp-proxy` as Phase 2 gateway | Already satisfied by Phase 2; Phase 3 does not introduce new MCP infrastructure. |
| Do NOT use `mcp-remote` (CVE-2025-6514) | Not used. |
| Do NOT use SSE legacy transport | Phase 3 publishes `/mcp` (Streamable HTTP) on port 8080. SSE not exposed. |
| GSD workflow enforcement | Phase 3 progresses via `/gsd-execute-phase`. |

## Sources

### Primary (HIGH confidence)
- [Docker Compose `run` reference](https://docs.docker.com/reference/cli/docker/compose/run/) — confirms `--service-ports` requirement for port publishing
- [Docker Compose `ports:` reference](https://docs.docker.com/reference/compose-file/services/#ports) — short-form and long-form syntax, host bind syntax
- [Docker Compose merge rules](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/) — overlay file `command:` replaces base
- [Docker Compose env-var interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/) — `${VAR:-default}` syntax
- [Docker Compose ps JSON format](https://docs.docker.com/reference/cli/docker/compose/ps/) — `Publishers` array structure
- Existing project code: `mcp-gateway/src/mcp_gateway/auth.py` lines 27-48 (token file lifecycle); `Dockerfile` lines 304-328 (gateway-start block); `compose.yaml` (current env vars); `run_docker.sh` line 199-202 (existing exec line)

### Secondary (MEDIUM confidence)
- [GitHub issue docker/compose#10138](https://github.com/docker/compose/issues/10138) — `compose run` does not enable port-forwarding by default (covers depends_on caveat)
- [GitHub issue docker/compose#11790](https://github.com/docker/compose/issues/11790) — port-mapping behavior nuances in `compose run`
- bash man page on `set -e` interaction with `if`/`while` — verified locally, well-known semantics

### Tertiary (LOW confidence)
- (none — all critical claims verified by primary sources)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Docker Compose v2 behavior is documented and stable
- Architecture: HIGH — single-overlay-file pattern is a documented Docker Compose idiom
- Pitfalls: HIGH — pitfalls 1, 2, 4, 5, 6 are derived from existing code review and verified docs; pitfall 3 is a deliberate D-04 tradeoff
- Token file behavior: HIGH — verified directly in `auth.py` source

**Research date:** 2026-04-27
**Valid until:** 2026-07-27 (90 days; Docker Compose semantics are very stable)

---
*Phase: 03-container-integration*
*Researched: 2026-04-27*
