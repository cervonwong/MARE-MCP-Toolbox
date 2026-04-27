---
phase: 03-container-integration
reviewed: 2026-04-27T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - compose.remote.yaml
  - compose.yaml
  - Dockerfile
  - run_docker.sh
findings:
  critical: 0
  warning: 7
  info: 6
  total: 13
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-04-27T00:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Phase 3 wires the dual-mode (`local` vs `--remote`) container experience around the existing Phase 2 gateway. The four files (`run_docker.sh`, `compose.yaml`, `compose.remote.yaml`, `Dockerfile`) are coherent: the `MCP_GATEWAY_ENABLED` guard in the entrypoint correctly suppresses the gateway daemon in local mode, and `compose run --rm` (without `--service-ports`) keeps the published port off the host in local mode, satisfying the no-leak guarantee.

That guarantee is, however, **implicit** — it relies on `docker compose run` ignoring the `ports:` block declared in the shared `compose.yaml`. A future contributor who adds `--service-ports`, switches local mode to `up`, or moves the project to a tool that honors `ports:` differently would silently leak the daemon's port. Worse, even though the daemon does not start, the compose file still sets up the iptables rule on `up`-style invocations.

The most concrete concerns:

1. **Default bind contradicts the documented security policy** — `MCP_GATEWAY_HOST_BIND` defaults to `0.0.0.0` in `run_docker.sh:238`, but `CLAUDE.md` states "Bind MCP port to localhost only by default; explicit opt-in for network exposure." (Warning).
2. **Bearer token always written to stdout** including a ready-to-paste JSON snippet, regardless of bind. The "shell scrollback may retain the bearer token" tip is only printed in the `0.0.0.0` branch. (Warning).
3. **`--token` with no value can crash or silently empty the token** — `shift 2` after a sole `--token` violates `set -e`/`set -u`, and `--token ""` exports an empty string that the gateway treats as "generate fresh", surprising the user. (Warning).
4. **Container-running detection parses JSON with grep** — fragile against `docker compose ps --format json` schema changes; a false negative deletes a still-valid token file. (Warning).
5. **No-leak guarantee is implicit** — `ports:` is declared in the shared compose file rather than only in `compose.remote.yaml`. A regression here silently publishes the daemon's port. (Warning).

No Critical issues were identified: the entrypoint guard logic is sound, no command injection paths surfaced from arg/env handling, and the heredoc construction in `Dockerfile` is properly single-quoted (`<<'EOF'`) so no host-side variable expansion can leak into baked scripts.

## Warnings

### WR-01: Default host bind is `0.0.0.0`, contradicting documented security policy

**File:** `run_docker.sh:236-239`, `compose.yaml:17`
**Issue:** Project `CLAUDE.md` ("Authentication & Security") declares: *"Bind MCP port to localhost only by default; explicit opt-in for network exposure."* But `run_docker.sh` defaults `MCP_GATEWAY_HOST_BIND` to `0.0.0.0` in remote mode, and `compose.yaml`'s `ports:` line uses `0.0.0.0` as its own fallback. Any user who runs `./run_docker.sh --remote` on a laptop on a coffee-shop Wi-Fi exposes the gateway to the LAN by default. The end-of-output warning is helpful but appears *after* the listener is already bound — the ship has sailed by the time the user reads it.

**Fix:** Flip the default. Make `--remote` bind `127.0.0.1` and require an explicit flag (e.g., `--expose-lan` or `MCP_GATEWAY_PUBLIC=1`) to override.

```bash
# run_docker.sh
export MCP_GATEWAY_HOST_BIND="${MCP_GATEWAY_HOST_BIND:-127.0.0.1}"
# Add a --expose-lan flag in the arg parser that sets MCP_GATEWAY_HOST_BIND=0.0.0.0
```

```yaml
# compose.yaml
ports:
  - "${MCP_GATEWAY_HOST_BIND:-127.0.0.1}:${MCP_GATEWAY_HOST_PORT:-8080}:${MCP_GATEWAY_PORT:-8080}"
```

---

### WR-02: Bearer token always printed to stdout (and into a paste-ready snippet)

**File:** `run_docker.sh:303-334`
**Issue:** The "ready" heredoc unconditionally prints the bearer token both as a labeled value (`Token:  ${TOKEN}`) and embedded in a JSON snippet that includes `Bearer ${TOKEN}`. The scrollback-leak warning at lines 335-344 only fires when `MCP_GATEWAY_HOST_BIND=0.0.0.0`. With the (correct) future default of `127.0.0.1`, the token still lands in scrollback — exactly when the user is most likely to demo, screen-share, or paste a terminal log into a bug report.

**Fix:** Always show the warning, and offer a quiet mode that prints the token only to a file (it is already on disk at `$TOKEN_FILE` with 0600). Example:

```bash
if [[ "${MCP_GATEWAY_QUIET:-0}" == "1" ]]; then
  echo "Gateway ready. Token written to: $TOKEN_FILE"
else
  cat <<READY
  ...
  Token:  ${TOKEN}
  ...
READY
  cat <<'WARN'
  Tip: shell scrollback may retain the bearer token; clear it before
       sharing your screen, or rerun with MCP_GATEWAY_QUIET=1.
WARN
fi
```

---

### WR-03: `--token` with no following value crashes under `set -euo pipefail`

**File:** `run_docker.sh:14`
**Issue:** The case branch `--token) export MCP_GATEWAY_TOKEN="${2:-}"; shift 2 ;;` does two surprising things:

1. If the user passes `--token` as the last arg, `${2:-}` evaluates to empty (silent), then `shift 2` is asked to shift two positions when only one remains. Under `set -e`, behavior depends on Bash version — on Bash 4.x+ `shift` past end is a non-fatal warning, but combined with `set -u` later interpolation can break.
2. An empty `MCP_GATEWAY_TOKEN=""` is exported. Many MCP servers treat unset and empty differently: empty often means "no token configured / generate fresh", which silently undoes the user's intent of pinning a token.

**Fix:**

```bash
--token)
  if [[ $# -lt 2 || -z "${2:-}" ]]; then
    echo "[error] --token requires a non-empty value" >&2
    exit 2
  fi
  export MCP_GATEWAY_TOKEN="$2"
  shift 2 ;;
```

Also reject whitespace-only values to avoid header injection if the token ever lands in an HTTP header verbatim.

---

### WR-04: Container-running detection parses JSON with grep

**File:** `run_docker.sh:244-255`
**Issue:** `REMOTE_RUNNING` is computed by piping `docker compose ps --format json kali` through `grep -c '"State":"running"'`. This is fragile in three ways:

1. Recent `docker compose` versions emit either a JSON array or NDJSON (one object per line) depending on minor version; the grep happens to match both, but field ordering or whitespace inside the JSON object (e.g., `"State": "running"` with a space after the colon) breaks the count.
2. If `docker compose ps` errors out, `2>/dev/null | grep -c ... || true` swallows the error and yields `0`. The script then treats "ps failed" identically to "no container running" and **deletes `$TOKEN_FILE`** (line 258) — wiping a still-valid token for an active container.
3. The trailing `|| true` is on the entire pipeline, so even a non-zero `grep` (no match → exit 1) is suppressed; that is intentional but masks every error class.

**Fix:** Use `docker compose ps -q kali` (returns the container ID if up, empty otherwise) or pipe through `jq` and check explicitly. Distinguish the "ps failed" case so the token is preserved:

```bash
if ! ps_out=$(docker compose ... ps -q kali 2>/dev/null); then
  echo "[warn] could not query compose state; preserving existing token" >&2
  REMOTE_RUNNING=1   # conservative: assume running, do not delete token
elif [[ -z "$ps_out" ]]; then
  REMOTE_RUNNING=0
else
  cid=$ps_out
  state=$(docker inspect --format '{{.State.Status}}' "$cid" 2>/dev/null || echo "")
  [[ "$state" == "running" ]] && REMOTE_RUNNING=1 || REMOTE_RUNNING=0
fi
```

---

### WR-05: No-leak guarantee in local mode is implicit and easy to break

**File:** `compose.yaml:16-17`
**Issue:** The `ports:` block lives in the *shared* `compose.yaml`. Local mode's safety from leaking the gateway port relies entirely on the fact that `docker compose run --rm` (without `--service-ports`) ignores `ports:`. This is a behavioral coincidence:

- A future maintainer who switches local mode to `docker compose up` (e.g., to enable a watch loop) will silently expose port 8080 to the host even though the gateway daemon is not running — the iptables NAT rule still gets installed by the compose project.
- A contributor adding `--service-ports` to the local-mode `run` command for a different reason would have the same effect.
- The "tail-keepalive" override in `compose.remote.yaml` proves a remote-only override works; the same pattern should apply to `ports:`.

**Fix:** Move `ports:` (and its three `MCP_GATEWAY_HOST_*` env defaults that are remote-mode-only) out of `compose.yaml` and into `compose.remote.yaml`:

```yaml
# compose.remote.yaml
services:
  kali:
    command: ["tail", "-f", "/dev/null"]
    tty: false
    stdin_open: false
    ports:
      - "${MCP_GATEWAY_HOST_BIND:-127.0.0.1}:${MCP_GATEWAY_HOST_PORT:-8080}:${MCP_GATEWAY_PORT:-8080}"
```

This makes the local-mode no-leak guarantee structural rather than coincidental.

---

### WR-06: Port-collision check is hardcoded to `127.0.0.1`

**File:** `run_docker.sh:262-266`
**Issue:** The pre-flight collision probe `(echo > /dev/tcp/127.0.0.1/${MCP_GATEWAY_HOST_PORT})` always probes loopback regardless of `MCP_GATEWAY_HOST_BIND`. When the user pins the bind to a specific external interface (e.g., `MCP_GATEWAY_HOST_BIND=192.168.1.10`), a clashing listener on that interface is missed, the collision warning never fires, and `docker compose up` fails with a less-friendly bind error. Conversely, if a process is bound only to a non-loopback interface but the user is binding `0.0.0.0`, the actual conflict is missed.

**Fix:**

```bash
PROBE_HOST="${MCP_GATEWAY_HOST_BIND}"
[[ "$PROBE_HOST" == "0.0.0.0" ]] && PROBE_HOST="127.0.0.1"  # 0.0.0.0 not probeable
if [[ "${REMOTE_RUNNING:-0}" -lt 1 ]] \
  && (echo > "/dev/tcp/${PROBE_HOST}/${MCP_GATEWAY_HOST_PORT}") >/dev/null 2>&1; then
  ...
fi
```

---

### WR-07: Empty `MCP_GATEWAY_TOKEN` is propagated to the gateway daemon

**File:** `Dockerfile:319-326` (entrypoint heredoc), `run_docker.sh:278`
**Issue:** Both the wrapper and the entrypoint use `${MCP_GATEWAY_TOKEN:-}`, so an empty string is *always* exported into the gateway's environment. If `mcp-gateway` distinguishes "unset" from "empty" (a common pattern: empty means "explicitly disable auth", whereas unset means "auto-generate"), the daemon could silently boot with no token. This couples Phase 3 correctness to internal Phase 2 semantics that may change.

**Fix:** Forward the variable only when it is non-empty:

```bash
# entrypoint
GATEWAY_ENV=()
[[ -n "${MCP_GATEWAY_TOKEN:-}" ]] && GATEWAY_ENV+=("MCP_GATEWAY_TOKEN=${MCP_GATEWAY_TOKEN}")
gosu "${AGENT_USER}" env HOME="${AGENT_HOME}" "${GATEWAY_ENV[@]}" \
  MCP_GATEWAY_HOST="${GATEWAY_HOST}" \
  ... \
  nohup mcp-gateway --host "${GATEWAY_HOST}" --port "${GATEWAY_PORT}" \
  >"${GATEWAY_LOG}" 2>&1 &
```

Apply the same pattern in `run_docker.sh` so empty doesn't ride through compose env passthrough either.

---

## Info

### IN-01: Token file race — no host-side permission check

**File:** `run_docker.sh:285-295`
**Issue:** The container writes `/agent/.mcp-gateway-token` with mode 0600 inside the container, but the file is bind-mounted from the host. On a multi-user host with permissive `umask`, or if the host directory is on a filesystem that ignores POSIX modes (e.g., some SMB/NTFS mounts via Docker Desktop), other local users could read the token between the container creating it and the user reading it.

**Fix:** After polling for the file, validate its mode and warn if it is world/group readable:

```bash
mode=$(stat -c '%a' "$TOKEN_FILE" 2>/dev/null || echo "")
if [[ -n "$mode" && "$mode" != "600" && "$mode" != "400" ]]; then
  echo "[warn] $TOKEN_FILE is mode $mode; tighten with: chmod 600 \"$TOKEN_FILE\"" >&2
fi
```

---

### IN-02: `--token=` accepts arbitrary content without validation

**File:** `run_docker.sh:13`
**Issue:** `${1#--token=}` strips the prefix and exports whatever remains, including embedded whitespace, newlines (rare via shells but possible), or shell metacharacters. The token eventually ends up in an HTTP `Authorization` header. RFC 7235 disallows newlines/CTLs there, and a token with a CR/LF would let downstream code split headers if the gateway forwards verbatim.

**Fix:** Validate against `^[A-Za-z0-9._~+/=-]{16,}$` (URL-safe base64 charset) or warn:

```bash
if [[ ! "$MCP_GATEWAY_TOKEN" =~ ^[A-Za-z0-9._~+/=-]{16,}$ ]]; then
  echo "[error] --token must be >=16 URL-safe characters" >&2
  exit 2
fi
```

---

### IN-03: `IMAGE_TAG` not exported to the `compose ps` invocation

**File:** `run_docker.sh:244-255`
**Issue:** The `IMAGE_TAG="$SHORT_SHA"` env is set on the `up`/`run` invocations but also on the `ps` query — good. Note however that `compose ps` does not actually use `IMAGE_TAG`; this is just informational. Minor — the env passthrough is consistent across all three compose calls, which is the right default.

**Fix:** No change required, but a comment would help future readers:

```bash
# IMAGE_TAG must match across up/run/ps invocations or compose treats them as
# different service definitions; pass it everywhere.
```

---

### IN-04: Hardcoded `idalib-mcp` port (8745)

**File:** `Dockerfile:284-291`
**Issue:** Port `8745` is hardcoded for the idalib-mcp listener. There is no env-var override path for users who already have a host service on that port (the listener binds 127.0.0.1 inside the container, so collisions are intra-container only — but the value is also hardcoded into the `configure-agent-mcp.sh` script that emits `.mcp.json`). Fine for now; flag for future refactor.

**Fix:** Introduce `IDALIB_MCP_PORT` env with default `8745` and reference it consistently in entrypoint + `configure-agent-mcp.sh`.

---

### IN-05: `compose.remote.yaml` keepalive uses bare `tail -f /dev/null`

**File:** `compose.remote.yaml:8`
**Issue:** With PID 1 = `tail`, side-process termination on `docker stop` relies on Docker's grace-then-SIGKILL flow. `idalib-mcp` and `mcp-gateway`, which are forked from the entrypoint, become children of the no-op tail and never receive the SIGTERM that an init system would broadcast — they just get SIGKILL'd at the end of the grace period. This is fine for stateless MCP servers but loses any chance of graceful shutdown (in-flight uploads, log flush).

**Fix:** Add `init: true` to the kali service in `compose.remote.yaml` so Docker uses `tini` as PID 1 and forwards signals:

```yaml
services:
  kali:
    init: true
    command: ["tail", "-f", "/dev/null"]
```

---

### IN-06: `pull_policy: never` makes ad-hoc `docker compose up` cryptic for new clones

**File:** `compose.yaml:4`
**Issue:** `pull_policy: never` is correct for the wrapper-driven flow (`run_docker.sh` always builds locally), but a contributor who runs `docker compose -f compose.yaml -f compose.remote.yaml up` without the wrapper sees `Error response from daemon: No such image: kali-re-tools:latest` — without context. The wrapper is the supported entry, so this is informational only.

**Fix:** Add a one-line comment at the top of `compose.yaml`:

```yaml
# NOTE: pull_policy=never assumes the image is built locally by run_docker.sh.
# Run `./run_docker.sh` (or `./run_docker.sh --remote`) once before invoking
# `docker compose` directly.
```

---

_Reviewed: 2026-04-27T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
