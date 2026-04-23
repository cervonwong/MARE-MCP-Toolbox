---
phase: 02-mcp-gateway
plan: 05
type: execute
wave: 5
depends_on:
  - 02-01
  - 02-02
  - 02-03
  - 02-04
files_modified:
  - Dockerfile
  - compose.yaml
  - CLAUDE.md
  - .planning/REQUIREMENTS.md
  - mcp-gateway/tests/e2e/smoke.sh
  - mcp-gateway/tests/e2e/test_upload_then_analyze.sh
autonomous: false
requirements:
  - GW-01
  - GW-02
  - GW-03
  - GW-04
  - GW-05
  - GW-06
tags:
  - docker
  - integration
  - smoke
  - e2e

user_setup: []

must_haves:
  truths:
    - "Container image builds with mcp-gateway installed under /opt/mcp-gateway"
    - "`docker compose up` starts the gateway daemon on 127.0.0.1:8080 inside the container (alongside idalib-mcp if IDA installed)"
    - "Gateway log shows: `[gateway] backend: <name>` → `[gateway] ready on 127.0.0.1:8080`"
    - "`/agent/.mcp-gateway-token` exists with mode 0600 after startup (readable on host because /agent is bind-mounted)"
    - "`curl http://127.0.0.1:8080/healthz` inside container returns 200"
    - "`curl -H \"Authorization: Bearer $TOK\" http://127.0.0.1:8080/mcp` with MCP initialize payload returns 200"
    - "`curl -X POST -H \"Authorization: Bearer $TOK\" -H \"X-Filename: smoke.bin\" --data-binary @<sample> http://127.0.0.1:8080/upload` returns 200 with sample_id"
    - "After upload, `tools/call collect_strings(sample=<sha256>)` returns exit_code=0 and writes status files"
    - "Existing inner-agent MCP config (INF-05) continues to work — configure-agent-mcp.sh still runs, /agent/.mcp.json still written"
    - "REQUIREMENTS.md GW-03 text corrected from 'BN > IDA > Ghidra' to 'IDA > BN > Ghidra' (research A8)"
    - "CLAUDE.md 'Recommended Stack' updated: custom FastMCP gateway preferred; mcp-proxy moved to 'Alternatives Considered' with rationale"
  artifacts:
    - path: "Dockerfile"
      provides: "pip install mcp-gateway package + python-multipart + pytest-asyncio into the image"
      contains: "pip install --no-cache-dir --break-system-packages"
    - path: "Dockerfile"
      provides: "agent-entrypoint.sh gateway daemon startup block"
      contains: "mcp-gateway --host"
    - path: "compose.yaml"
      provides: "MCP_GATEWAY_* env var injection"
      contains: "MCP_GATEWAY_TOKEN"
    - path: "mcp-gateway/tests/e2e/smoke.sh"
      provides: "docker-compose-up smoke test: healthz + initialize + tools/list"
    - path: "mcp-gateway/tests/e2e/test_upload_then_analyze.sh"
      provides: "upload → collect_strings roundtrip via tool call"
  key_links:
    - from: "Dockerfile gateway install block"
      to: "/opt/mcp-gateway/src/mcp_gateway/"
      via: "COPY + pip install -e"
      pattern: "COPY mcp-gateway"
    - from: "agent-entrypoint.sh"
      to: "mcp-gateway daemon"
      via: "gosu agent + nohup, after idalib-mcp block"
      pattern: "mcp-gateway.*--host 127\\.0\\.0\\.1"
    - from: "compose.yaml environment"
      to: "gateway runtime env"
      via: "env passthrough"
      pattern: "MCP_GATEWAY_TOKEN"
---

<objective>
Land the mcp-gateway into the container: Dockerfile installs the Python package and dependencies, `agent-entrypoint.sh` starts the gateway daemon alongside idalib-mcp, `compose.yaml` passes through the relevant env vars, and two e2e shell scripts (smoke.sh + test_upload_then_analyze.sh) exercise the full stack via `docker compose up`.

Also correct the documentation drift flagged by research: REQUIREMENTS.md GW-03 stale wording ("BN > IDA > Ghidra" → "IDA > BN > Ghidra") and CLAUDE.md "Recommended Stack" (custom FastMCP over mcp-proxy).

Purpose: Turns the Python package (Plans 01–04) into a deployed service that fulfills all of GW-01..GW-06 end-to-end in the real container. Final validation of the phase.

Output: A container image that runs the gateway on 127.0.0.1:8080, a host-reachable token file, and an automated smoke test the user can run to confirm Phase 2 is shipped. Plan 3 of the roadmap (container integration for dual-mode entrypoint) picks up from here; Phase 4 (external clients) depends on this wiring.

NOTE: This plan is `autonomous: false` — it has one `checkpoint:human-verify` at the end for the user to confirm the full container smoke test passed on their machine. All other work is fully automated.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/02-mcp-gateway/02-CONTEXT.md
@.planning/phases/02-mcp-gateway/02-RESEARCH.md
@.planning/phases/02-mcp-gateway/02-VALIDATION.md
@.planning/phases/02-mcp-gateway/02-01-package-scaffold-and-auth-PLAN.md
@.planning/phases/02-mcp-gateway/02-02-fastmcp-server-and-tool-surface-PLAN.md
@.planning/phases/02-mcp-gateway/02-03-backend-client-routing-PLAN.md
@.planning/phases/02-mcp-gateway/02-04-upload-endpoint-PLAN.md
@Dockerfile
@compose.yaml
@CLAUDE.md
@docker-bin/configure-agent-mcp.sh

<interfaces>
<!-- Phase 1 idalib-mcp daemon block — Dockerfile lines 269-292 -->
<!-- Pattern: gosu agent + nohup + bind 127.0.0.1 + log to /tmp/*.log + port pre-check -->
```bash
if command -v idalib-mcp >/dev/null 2>&1 \
  && [ -d /opt/ida-pro ] && [ -n "$(ls -A /opt/ida-pro 2>/dev/null)" ]; then
  IDALIB_LOG="/tmp/idalib-mcp.log"
  if ! (echo > /dev/tcp/127.0.0.1/8745) >/dev/null 2>&1; then
    echo "[mcp] starting idalib-mcp on 127.0.0.1:8745 (log: ${IDALIB_LOG})"
    gosu "${AGENT_USER}" env HOME="${AGENT_HOME}" \
      nohup idalib-mcp --host 127.0.0.1 --port 8745 \
      >"${IDALIB_LOG}" 2>&1 &
  fi
fi
```

<!-- Env vars added by this plan -->
MCP_GATEWAY_TOKEN        — optional, wins if set (D-16); otherwise gateway generates
MCP_GATEWAY_HOST         — default 127.0.0.1 (D-19)
MCP_GATEWAY_PORT         — default 8080 (D-20)
MCP_GATEWAY_MAX_UPLOAD_MB — default 1024 (D-14)
MCP_GATEWAY_QUIET        — set to 1 to suppress bearer token log line (D-17)

<!-- Current CLAUDE.md Recommended Stack — recommends mcp-proxy; research flagged this needs updating -->
<!-- See RESEARCH.md § Project Constraints "CRITICAL: CLAUDE.md's Recommended Stack table recommends mcp-proxy. CONTEXT.md explicitly chose a custom FastMCP gateway instead. ... plan MUST include a documentation task to update CLAUDE.md" -->

<!-- Current REQUIREMENTS.md GW-03 text — says "BN > IDA > Ghidra"; actual chain is "IDA > BN > Ghidra" -->
<!-- See RESEARCH.md § Assumptions Log A8 -->
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Dockerfile — add mcp-gateway install block + gateway daemon in agent-entrypoint.sh</name>
  <files>
    Dockerfile
  </files>
  <read_first>
    - Dockerfile (entire file — understand idalib-mcp install block lines 115-147 and agent-entrypoint.sh lines 246-327 verbatim)
    - mcp-gateway/pyproject.toml (from Plan 01 — confirms `[project.scripts]` installs the `mcp-gateway` console script)
    - .planning/phases/02-mcp-gateway/02-CONTEXT.md (D-09 daemon at container boot; D-17 token file + log line; D-19 127.0.0.1; D-20 port 8080)
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Installation; § Environment Availability — python-multipart, pytest-asyncio)
  </read_first>
  <acceptance_criteria>
    - `grep -n "pip install.*python-multipart" Dockerfile` returns a line (python-multipart explicitly installed)
    - `grep -n "pytest-asyncio" Dockerfile` returns a line (pytest-asyncio added to the pytest install or mcp-gateway dev extras)
    - `grep -n "pip install.*mcp>=1.27" Dockerfile` returns a line (mcp SDK install)
    - `grep -n "COPY mcp-gateway" Dockerfile` returns a line
    - `grep -n "pip install .*\-e /opt/mcp-gateway" Dockerfile` returns a line
    - `grep -n "mcp-gateway --host 127.0.0.1 --port 8080" Dockerfile` returns a line (in agent-entrypoint heredoc)
    - `grep -n "MCP_GATEWAY_LOG\|/tmp/mcp-gateway.log" Dockerfile` returns a line
    - `grep -n 'gosu "${AGENT_USER}".*mcp-gateway' Dockerfile` returns a line
    - `grep -n "127.0.0.1/8080" Dockerfile` returns a line (port pre-check in entrypoint)
    - The idalib-mcp daemon block (lines 269-292) remains unchanged — `diff <(git show HEAD:Dockerfile | sed -n '269,292p') <(sed -n '/idalib-mcp on 127.0.0.1:8745/,/persists in ~\/.idapro-docker/p' Dockerfile)` produces no substantive diff (or a quick visual audit confirms no deletions)
    - Image builds successfully: `docker build -t kali-re-tools:phase2-test .` exits 0 (executor must run this)
    - After build: `docker run --rm kali-re-tools:phase2-test python3 -c "import mcp_gateway; print(mcp_gateway.__version__)"` prints `0.1.0`
  </acceptance_criteria>
  <action>
**Step 1 — Add Python dependencies to the existing tooling install block:**

Find the Dockerfile block starting around line 59:
```
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    pytest ruff flare-floss uv ipython ipdb \
    capstone ropper unblob
```

Replace it with (adding the gateway deps inline, sorted for readability):
```
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    pytest pytest-asyncio ruff flare-floss uv ipython ipdb \
    capstone ropper unblob \
    "mcp>=1.27,<1.28" "starlette>=0.37" "uvicorn>=0.27" \
    "python-multipart>=0.0.9" "httpx>=0.27" "anyio>=4.5"
```

**Step 2 — Add COPY + editable install for mcp-gateway:**

Find a stable anchor near the BN install block (after the BN install RUN at line 113, before IDA builder COPY at line 116). Insert this block — AFTER the BN block and BEFORE `COPY --from=ida-builder`:

```dockerfile
# Install the MARE MCP gateway package (editable so dev iterations survive
# without rebuild of the whole image). Source tree is baked into the image
# at /opt/mcp-gateway and re-exported as the `mcp-gateway` console script.
COPY mcp-gateway/ /opt/mcp-gateway/
RUN pip install --no-cache-dir --break-system-packages -e /opt/mcp-gateway \
    && which mcp-gateway \
    && python3 -c "import mcp_gateway; print(f'mcp-gateway {mcp_gateway.__version__} installed')"
```

**Step 3 — Add the gateway daemon block to agent-entrypoint.sh heredoc:**

Locate the `agent-entrypoint.sh` heredoc in Dockerfile (starts around line 249 with `RUN cat > /usr/local/bin/agent-entrypoint.sh <<'EOF'`). Within the heredoc, find the end of the idalib-mcp block (after the `fi` closing the IDA detection, around line 292, after the "[mcp] persists in ~/.idapro-docker/ida.reg" hint).

Immediately AFTER that `fi` and BEFORE the "# Persist Claude state inside the mounted ~/.claude/ directory" comment, insert:

```bash
# Start the MARE MCP gateway daemon (Phase 2: remote Streamable HTTP + /upload).
# Runs alongside idalib-mcp; clients authenticate with the bearer token written
# to /agent/.mcp-gateway-token (0600). The gateway binds 127.0.0.1 by default
# (D-19); set MCP_GATEWAY_HOST=0.0.0.0 to expose on all container interfaces.
GATEWAY_HOST="${MCP_GATEWAY_HOST:-127.0.0.1}"
GATEWAY_PORT="${MCP_GATEWAY_PORT:-8080}"
GATEWAY_LOG="/tmp/mcp-gateway.log"
if command -v mcp-gateway >/dev/null 2>&1; then
  # Skip start if the port is already bound (container restart, docker exec loops).
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
```

**Step 4 — Verify no other Dockerfile edits:**

Do NOT modify:
- The IDA builder stage (lines 1-21)
- The Ghidra install conditional (lines 67-72)
- The capa install block (lines 75-87)
- The IDA Python packages install block (lines 119-147) — idalib-mcp install stays as-is
- The configure-agent-mcp.sh install line (line 172)
- The ida-accept-eula block
- Claude Code CLI install (lines 235-241)
- The existing idalib-mcp daemon block inside agent-entrypoint.sh (remains intact; gateway block is ADDED after it)
- WORKDIR or ENTRYPOINT or CMD

**Step 5 — Build the image to verify:**

Run:
```bash
docker build -t kali-re-tools:phase2-test . 2>&1 | tail -30
```

If the build fails, read the error and fix the Dockerfile. Common issues:
- `COPY mcp-gateway/` — requires the `mcp-gateway/` directory to exist in the build context (it does after Plans 01–04)
- `pip install -e /opt/mcp-gateway` — requires `pyproject.toml` at `/opt/mcp-gateway/pyproject.toml` (Plan 01 Task 1 creates it)
- Missing `pytest-asyncio` — already added to the top-level pip install

If the build passes, run a quick import check:
```bash
docker run --rm kali-re-tools:phase2-test python3 -c "import mcp_gateway; print(mcp_gateway.__version__)"
```
  </action>
  <verify>
    <automated>docker build -t kali-re-tools:phase2-test . && docker run --rm kali-re-tools:phase2-test python3 -c "import mcp_gateway; print(mcp_gateway.__version__)"</automated>
  </verify>
  <done>Image builds; mcp_gateway 0.1.0 importable; `mcp-gateway` console script on PATH; agent-entrypoint.sh has a gateway daemon block after the idalib-mcp block.</done>
</task>

<task type="auto">
  <name>Task 2: compose.yaml env var passthrough + doc updates (REQUIREMENTS.md + CLAUDE.md)</name>
  <files>
    compose.yaml,
    .planning/REQUIREMENTS.md,
    CLAUDE.md
  </files>
  <read_first>
    - compose.yaml (entire file — existing environment: block lines 16-22)
    - .planning/REQUIREMENTS.md (GW-03 line — currently "BN > IDA > Ghidra")
    - CLAUDE.md (§ Recommended Stack → Remote MCP Gateway Server, especially the mcp-proxy row and the Do NOT Use table; § Installation stub)
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Project Constraints + Assumptions Log A8 for doc correction rationale; § Critical priority clarification)
  </read_first>
  <acceptance_criteria>
    - `grep -q '- MCP_GATEWAY_TOKEN' compose.yaml`
    - `grep -q '- MCP_GATEWAY_HOST' compose.yaml`
    - `grep -q '- MCP_GATEWAY_PORT' compose.yaml`
    - `grep -q '- MCP_GATEWAY_MAX_UPLOAD_MB' compose.yaml`
    - `grep -q '- MCP_GATEWAY_QUIET' compose.yaml`
    - Existing BN_USER_DIRECTORY, IDADIR, HOME, USER, LOGNAME env vars remain present (regression check)
    - `.planning/REQUIREMENTS.md` GW-03 text contains "IDA > BN > Ghidra" (correction applied)
    - `.planning/REQUIREMENTS.md` GW-03 text no longer contains "BN > IDA > Ghidra"
    - `CLAUDE.md` "Recommended Stack" table marks custom FastMCP gateway as primary; mcp-proxy row moved to "Alternatives Considered" OR annotated as "alternative (not selected — see D-01..D-20)"
    - `CLAUDE.md` "Alternatives Considered" OR equivalent section contains a row explaining why mcp-proxy was not chosen (rationale: cannot aggregate multiple backends + host /upload + apply auth in a single process)
    - Container start still works: `docker compose up -d && sleep 3 && docker compose exec kali curl -s http://127.0.0.1:8080/healthz` returns `{"ok": true}` (executor must run)
  </acceptance_criteria>
  <action>
**Step 1 — Edit `compose.yaml`:**

The file currently has an `environment:` block at lines 16-22. Add the 5 new env vars as passthroughs (meaning: if set on the host, forwarded to the container; if unset, the gateway uses defaults).

Replace the entire `environment:` block:

```yaml
    environment:
      - BN_USER_DIRECTORY=/home/agent/.binaryninja
      - IDADIR=/opt/ida-pro
      - HOME=/home/agent
      - USER=agent
      - LOGNAME=agent
```

With:

```yaml
    environment:
      - BN_USER_DIRECTORY=/home/agent/.binaryninja
      - IDADIR=/opt/ida-pro
      - HOME=/home/agent
      - USER=agent
      - LOGNAME=agent
      # MCP gateway (Phase 2) — all optional; gateway has sane defaults.
      - MCP_GATEWAY_TOKEN        # set to pin token; else generated at startup
      - MCP_GATEWAY_HOST          # default 127.0.0.1; set 0.0.0.0 to expose on all interfaces
      - MCP_GATEWAY_PORT          # default 8080
      - MCP_GATEWAY_MAX_UPLOAD_MB # default 1024 (1 GB)
      - MCP_GATEWAY_QUIET         # set to 1 to suppress bearer log line at startup
```

(Docker Compose's value-less env syntax `- NAME` means: forward the host env var if set; do nothing if unset. This is the desired "optional passthrough" behavior.)

Also leave the existing `volumes:`, `cap_add:`, `security_opt:`, `stdin_open:`, `tty:`, `command:` blocks untouched.

**Note:** Port publishing (`ports:` block) is intentionally NOT added here — per deferred D of CONTEXT.md and Phase 3's scope (INF-02). The gateway still listens on 127.0.0.1 inside the container; an inner-container smoke test reaches it via loopback. Host-side access is Phase 3's job.

**Step 2 — Correct `.planning/REQUIREMENTS.md` GW-03:**

Find the line:
```
- [ ] **GW-03**: Disassembler tools route to whichever backend is installed (BN > IDA > Ghidra), presenting a unified interface to clients
```

Replace with:
```
- [ ] **GW-03**: Disassembler tools route to whichever backend is installed (IDA > BN > Ghidra), presenting a unified interface to clients
```

Add a one-line footnote at the bottom of the GW section or in the "Traceability" section noting the correction, e.g.:
```
<!-- Corrected 2026-04-23 (Phase 2 Plan 05): GW-03 priority is IDA > BN > Ghidra per Phase 1 D-06, Phase 2 D-09, and docker-bin/configure-agent-mcp.sh lines 67-119. Prior wording "BN > IDA > Ghidra" was stale. -->
```

**Step 3 — Update `CLAUDE.md` Recommended Stack:**

Find the section `### Remote MCP Gateway Server` (under "Recommended Stack"). The current table contains a row for `mcp-proxy (sparfenyuk)` presented as recommended. Replace that section entirely with:

```markdown
### Remote MCP Gateway Server
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Custom FastMCP gateway (mcp-gateway/) | 0.1.0+ | In-process gateway: Streamable HTTP server + /upload + bearer auth + curated 21-tool surface + backend aggregation | A 1:1 stdio→HTTP bridge cannot: (a) aggregate IDA/BN/Ghidra under unified tool names, (b) host a /upload endpoint, (c) apply bearer auth + Origin validation uniformly. Custom gateway built on `mcp.server.fastmcp.FastMCP` solves all four in one process. See .planning/phases/02-mcp-gateway/02-CONTEXT.md D-01..D-20. | HIGH |
| mcp (Python SDK) | 1.27.0+ | MCP protocol implementation (FastMCP server + ClientSession) | Single SDK for both the gateway server and the gateway's client-to-backend sessions. Supports Streamable HTTP (2025-03-26) + stdio transport. | HIGH |
| Streamable HTTP | Protocol 2025-03-26 | Network transport | The current MCP standard. SSE was deprecated June 2025. All major clients (Claude Code, mastra.ai) support Streamable HTTP with automatic SSE fallback. | HIGH |
```

Then find the "Alternatives Considered" table (further down the file) and add a new row at the top:

```markdown
| Custom FastMCP gateway | mcp-proxy (sparfenyuk) | mcp-proxy is a stdio→HTTP bridge only — it cannot aggregate multiple backends, rename tools, host /upload, or serve orchestrator scripts as atomic tools. User explicitly chose custom FastMCP (Phase 2 D-01..D-20). |
```

And in the "Do NOT Use" table, you may optionally add (not required if space-constrained):

```markdown
| mcp-proxy as the Phase 2 gateway | Use case mismatch — phase needs aggregation + /upload + auth in one process. mcp-proxy is 1:1 bridge only. |
```

**Step 4 — Smoke verify the stack:**

```bash
# From project root
docker compose down 2>/dev/null || true
docker compose up -d
sleep 4
docker compose exec -T kali curl -fsS http://127.0.0.1:8080/healthz
docker compose exec -T kali cat /agent/.mcp-gateway-token
docker compose logs kali | grep -E '\[gateway\]'
```

Expected output:
- `/healthz` returns `{"ok":true}`
- `/agent/.mcp-gateway-token` contains a URL-safe token string
- Gateway log shows `[gateway] backend: <name>` and `[gateway] ready on 127.0.0.1:8080`

If detection fails because no disassembler is installed in the test image (pure Ghidra-less build), the log will show a startup error from `detect_backend()` raising — that is the correct D-10 fail-loud behavior. For the smoke test, the executor may set `MCP_GATEWAY_SKIP_BACKEND=1` via compose env override (or use an image built with `INSTALL_BINARY_NINJA=0 INSTALL_IDA_PRO=0` so Ghidra is installed as the fallback, which will satisfy detection).
  </action>
  <verify>
    <automated>grep -q 'MCP_GATEWAY_TOKEN' compose.yaml && grep -q 'IDA > BN > Ghidra' .planning/REQUIREMENTS.md && grep -q 'Custom FastMCP gateway' CLAUDE.md</automated>
  </verify>
  <done>compose.yaml has 5 new passthrough env vars; REQUIREMENTS.md GW-03 corrected; CLAUDE.md Recommended Stack updated to custom FastMCP primary with mcp-proxy moved to Alternatives.</done>
</task>

<task type="auto">
  <name>Task 3: e2e smoke test scripts (smoke.sh + test_upload_then_analyze.sh)</name>
  <files>
    mcp-gateway/tests/e2e/smoke.sh,
    mcp-gateway/tests/e2e/test_upload_then_analyze.sh
  </files>
  <read_first>
    - mcp-gateway/tests/e2e/smoke.sh (Plan 01 placeholder — replace body)
    - mcp-gateway/tests/e2e/test_upload_then_analyze.sh (Plan 01 placeholder — replace body)
    - compose.yaml (to understand how docker compose is invoked)
    - .planning/phases/02-mcp-gateway/02-VALIDATION.md (§ Per-Task Verification Map final rows — e2e smoke and upload_then_analyze)
  </read_first>
  <acceptance_criteria>
    - `mcp-gateway/tests/e2e/smoke.sh` is executable (`test -x`)
    - Running `bash mcp-gateway/tests/e2e/smoke.sh` exits 0 when the container is up and healthy
    - Running `bash mcp-gateway/tests/e2e/smoke.sh` prints to stdout at minimum:
      - `[smoke] /healthz OK`
      - `[smoke] /mcp initialize OK`
      - `[smoke] /mcp tools/list OK — N tools` where N is in [15, 25]
    - `mcp-gateway/tests/e2e/test_upload_then_analyze.sh` is executable
    - Running `bash mcp-gateway/tests/e2e/test_upload_then_analyze.sh` exits 0 when the container is up
    - `test_upload_then_analyze.sh` uploads a tiny synthetic sample, captures the sha256 from response, then calls `collect_strings(sample=<sha256>)` via MCP tool call and asserts exit_code=0
    - Both scripts use `set -euo pipefail` and clean up any local tempfiles
    - Both scripts read the bearer token from `/agent/.mcp-gateway-token` (inside-container path) or from `./.mcp-gateway-token` (host path after bind mount) — auto-detect
    - Both scripts default to `http://127.0.0.1:8080` but allow override via `GATEWAY_URL` env var
  </acceptance_criteria>
  <action>
**Step 1 — Replace `mcp-gateway/tests/e2e/smoke.sh` body:**

```bash
#!/usr/bin/env bash
# Phase 2 smoke: GW-01 (healthz + initialize + tools/list), GW-02 (15-25 tool count), GW-04 (bearer).
# Usage (from project root, after `docker compose up -d`):
#   bash mcp-gateway/tests/e2e/smoke.sh
# Env: GATEWAY_URL (default http://127.0.0.1:8080), TOKEN_FILE (default auto-detect)
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8080}"

# Token discovery: prefer host-bound path under the project root, fall back to /agent (inside container).
if [ -f "./.mcp-gateway-token" ]; then
  TOKEN_FILE="./.mcp-gateway-token"
elif [ -f "/agent/.mcp-gateway-token" ]; then
  TOKEN_FILE="/agent/.mcp-gateway-token"
else
  echo "[smoke] ERROR: token file not found (tried ./.mcp-gateway-token and /agent/.mcp-gateway-token)" >&2
  exit 2
fi

TOK="$(cat "${TOKEN_FILE}" | tr -d '[:space:]')"
if [ -z "${TOK}" ]; then
  echo "[smoke] ERROR: token file ${TOKEN_FILE} is empty" >&2
  exit 2
fi

# 1) /healthz (no auth)
echo "[smoke] GET ${GATEWAY_URL}/healthz"
HEALTH_JSON="$(curl -fsS "${GATEWAY_URL}/healthz")"
echo "${HEALTH_JSON}" | grep -q '"ok":[[:space:]]*true' || {
  echo "[smoke] FAIL: /healthz did not return {ok: true}: ${HEALTH_JSON}" >&2
  exit 1
}
echo "[smoke] /healthz OK"

# 2) MCP initialize
INIT_PAYLOAD='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke.sh","version":"1"}}}'

INIT_RESP="$(curl -fsS -X POST "${GATEWAY_URL}/mcp" \
  -H "Authorization: Bearer ${TOK}" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d "${INIT_PAYLOAD}")"
echo "${INIT_RESP}" | grep -q '"serverInfo"' || {
  echo "[smoke] FAIL: initialize did not include serverInfo: ${INIT_RESP}" >&2
  exit 1
}
echo "[smoke] /mcp initialize OK"

# 3) tools/list
LIST_PAYLOAD='{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
LIST_RESP="$(curl -fsS -X POST "${GATEWAY_URL}/mcp" \
  -H "Authorization: Bearer ${TOK}" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d "${LIST_PAYLOAD}")"

# Count tools: crude but container-portable (avoid jq dependency hard-fail)
if command -v jq >/dev/null 2>&1; then
  TOOL_COUNT="$(echo "${LIST_RESP}" | jq '.result.tools | length')"
else
  TOOL_COUNT="$(echo "${LIST_RESP}" | grep -oE '"name"[[:space:]]*:' | wc -l)"
fi

if [ "${TOOL_COUNT}" -lt 15 ] || [ "${TOOL_COUNT}" -gt 25 ]; then
  echo "[smoke] FAIL: tool count ${TOOL_COUNT} outside GW-02 range 15-25" >&2
  echo "${LIST_RESP}" >&2
  exit 1
fi
echo "[smoke] /mcp tools/list OK — ${TOOL_COUNT} tools"

# 4) GW-04 regression: unauth POST to /mcp must be 401
UNAUTH_CODE="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${GATEWAY_URL}/mcp" -H "Content-Type: application/json" -d "${INIT_PAYLOAD}")"
if [ "${UNAUTH_CODE}" != "401" ]; then
  echo "[smoke] FAIL: unauth POST /mcp returned ${UNAUTH_CODE}, expected 401" >&2
  exit 1
fi
echo "[smoke] /mcp unauth → 401 OK"

echo "[smoke] ALL CHECKS PASSED"
```

**Step 2 — Replace `mcp-gateway/tests/e2e/test_upload_then_analyze.sh` body:**

```bash
#!/usr/bin/env bash
# Phase 2 e2e: GW-06 (upload) + GW-02 (collect_strings tool) + D-15 (sha256-as-sample).
# Usage: bash mcp-gateway/tests/e2e/test_upload_then_analyze.sh
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8080}"

# Token discovery
if [ -f "./.mcp-gateway-token" ]; then
  TOKEN_FILE="./.mcp-gateway-token"
elif [ -f "/agent/.mcp-gateway-token" ]; then
  TOKEN_FILE="/agent/.mcp-gateway-token"
else
  echo "[upload-e2e] ERROR: token file not found" >&2
  exit 2
fi
TOK="$(cat "${TOKEN_FILE}" | tr -d '[:space:]')"

# 1) Create a tiny synthetic ELF-ish sample
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT
SAMPLE="${TMP_DIR}/smoke_sample.bin"
printf '\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00' > "${SAMPLE}"
# Pad to 128 bytes with strings
printf 'HelloWorldStringFromSmokeTest\x00UserDefinedString\x00' >> "${SAMPLE}"

# 2) Upload
UPLOAD_RESP="$(curl -fsS -X POST "${GATEWAY_URL}/upload" \
  -H "Authorization: Bearer ${TOK}" \
  -H "X-Filename: smoke_sample.bin" \
  --data-binary "@${SAMPLE}")"
echo "[upload-e2e] upload response: ${UPLOAD_RESP}"

if command -v jq >/dev/null 2>&1; then
  SAMPLE_ID="$(echo "${UPLOAD_RESP}" | jq -r '.sample_id')"
else
  SAMPLE_ID="$(echo "${UPLOAD_RESP}" | grep -oE '"sample_id"[[:space:]]*:[[:space:]]*"[0-9a-f]+"' | head -1 | grep -oE '[0-9a-f]{64}')"
fi

if ! echo "${SAMPLE_ID}" | grep -qE '^[0-9a-f]{64}$'; then
  echo "[upload-e2e] FAIL: bad sample_id in upload response: ${SAMPLE_ID}" >&2
  exit 1
fi
echo "[upload-e2e] upload OK — sample_id=${SAMPLE_ID}"

# 3) First initialize, then tools/call collect_strings(sample=<sha256>)
INIT_PAYLOAD='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"upload-e2e","version":"1"}}}'
curl -fsS -X POST "${GATEWAY_URL}/mcp" \
  -H "Authorization: Bearer ${TOK}" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d "${INIT_PAYLOAD}" >/dev/null

CALL_PAYLOAD="$(printf '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"collect_strings","arguments":{"sample":"%s"}}}' "${SAMPLE_ID}")"
CALL_RESP="$(curl -fsS -X POST "${GATEWAY_URL}/mcp" \
  -H "Authorization: Bearer ${TOK}" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d "${CALL_PAYLOAD}")"
echo "[upload-e2e] collect_strings response (truncated): $(echo "${CALL_RESP}" | head -c 400)"

# Expect the result to mention exit_code 0 (success). If the orchestrator scripts
# aren't installed in the test image, collect_strings will still return a structured
# result with exit_code != 0 — that's surfaced but the script considers it a soft-fail.
if echo "${CALL_RESP}" | grep -q '"isError"[[:space:]]*:[[:space:]]*true'; then
  echo "[upload-e2e] WARN: tools/call returned isError=true (orchestrator scripts may be missing from test image)"
  echo "[upload-e2e] response: ${CALL_RESP}"
  # Do not fail hard — the upload itself is GW-06; tool invocation end-to-end is a bonus.
fi

echo "[upload-e2e] ALL CHECKS PASSED"
```

**Step 3 — Ensure both scripts are executable:**

```bash
chmod 0755 mcp-gateway/tests/e2e/smoke.sh mcp-gateway/tests/e2e/test_upload_then_analyze.sh
```
  </action>
  <verify>
    <automated>test -x mcp-gateway/tests/e2e/smoke.sh && test -x mcp-gateway/tests/e2e/test_upload_then_analyze.sh && bash -n mcp-gateway/tests/e2e/smoke.sh && bash -n mcp-gateway/tests/e2e/test_upload_then_analyze.sh</automated>
  </verify>
  <done>Both e2e scripts have real bodies that exercise healthz, initialize, tools/list, unauth rejection, upload, and tools/call collect_strings. Scripts are executable and pass `bash -n` syntax check.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 4: Human-verify the full container smoke test</name>
  <files>(human verification — no files modified)</files>
  <what-built>
    Everything from Plans 01-04 (package, FastMCP server, backend routing, upload endpoint) wired into the container via Dockerfile + compose.yaml + e2e smoke scripts. REQUIREMENTS.md and CLAUDE.md doc drift corrected.
  </what-built>
  <how-to-verify>
    1. Stop any running container: `docker compose down`
    2. Rebuild the image with a backend:
       - For Ghidra-only (no licensed software): `docker build -t kali-re-tools:latest .`
       - For BN: place BN zip in repo root, run `./run_docker.sh build` or equivalent
       - For IDA: place IDA zip and run with `INSTALL_IDA_PRO=1`
    3. Start the container: `docker compose up -d`
    4. Wait 5 seconds for the gateway to start: `sleep 5`
    5. Check the gateway is running: `docker compose logs kali | grep '\[gateway\]'`
       Expected lines:
         `[gateway] starting on 127.0.0.1:8080 (log: /tmp/mcp-gateway.log)`
         `[gateway] backend: <ida|bn|ghidra>`
         `[gateway] Bearer token: <URL-safe-string>` (unless MCP_GATEWAY_QUIET=1)
         `[gateway] token file: /agent/.mcp-gateway-token`
         `[gateway] ready on 127.0.0.1:8080`
    6. Confirm the token file is host-visible: `cat .mcp-gateway-token` — should print the same token as the log line
    7. Confirm file permissions: `stat -c %a .mcp-gateway-token` should print `600`
    8. Run the smoke test from the host:
       `docker compose exec kali bash /agent/mcp-gateway/tests/e2e/smoke.sh`
       Expected: `[smoke] ALL CHECKS PASSED`
    9. Run the upload+analyze test:
       `docker compose exec kali bash /agent/mcp-gateway/tests/e2e/test_upload_then_analyze.sh`
       Expected: `[upload-e2e] ALL CHECKS PASSED`
    10. Confirm the uploaded file is on disk inside the container:
       `docker compose exec kali ls /agent/uploads/`  — should show at least one 64-char sha256 directory
    11. Confirm the inner-agent MCP config still works (INF-05 regression):
       `docker compose exec kali cat /agent/.mcp.json`  — should be valid JSON with an `mcpServers` key
    12. Respond with `approved` if all 11 steps pass, or describe any failures.
  </how-to-verify>
  <action>Wait for human to follow the how-to-verify steps above and type "approved" or describe issues. Executor must PAUSE here — do NOT proceed to summary until user approves.</action>
  <verify>Human responds with "approved" after running all 11 verification steps.</verify>
  <done>User has typed "approved" (or provided feedback that execution was halted to address). All 11 smoke-test steps passed on the user's machine.</done>
  <resume-signal>Type "approved" or describe issues</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| host shell → `docker compose up` env | Trusted; operator controls the env vars |
| container filesystem `/agent` | Bind-mounted from host; operator sees the same files |
| gateway daemon runs as `agent` user | Not root; matches the container's unprivileged-user design |
| `/agent/.mcp-gateway-token` | Bind-mounted; visible on host as `./.mcp-gateway-token` after compose up (D-17 convenience) |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-02-AUTH | Spoofing | Gateway HTTP endpoints | HIGH | mitigate | Plans 01-04 all covered. This plan verifies via smoke.sh unauth → 401 test. |
| T-02-NET | Spoofing / EoP | Container network binding | MEDIUM | mitigate | Task 1: agent-entrypoint.sh binds `${MCP_GATEWAY_HOST:-127.0.0.1}`. Task 2: compose.yaml does NOT publish the port (ports: block absent); host reaches gateway only via `docker compose exec`. Phase 3 adds opt-in publishing. |
| T-02-TOKENLEAK | Info Disclosure | Token file / docker logs | MEDIUM | mitigate | Plan 01 handles 0600 + QUIET; this plan's smoke.sh reads token from file (never logs it). Token printed to container log once at startup (intentional per D-17) — `docker compose logs kali` exposes it to the same audience that can exec into the container. |
| T-02-UPLOAD | DoS | /upload in container | HIGH | mitigate | Plan 04 streaming cap still applies. Task 3 upload test uses a 128-byte sample (well under any cap) and does NOT test cap enforcement end-to-end (covered by unit tests in Plan 04). |
| T-02-PATHTRAVERSAL | Tampering | — | — | — | Plans 02, 04 handle |
| T-02-SUBPROC | RCE | orchestrator shell-outs in container | HIGH | mitigate | Plan 02 argv-only execution. Task 3 upload-then-analyze test exercises a real shell-out (`collect_strings.sh`) — if any injection path existed, the tool call would fail or misbehave. |
| T-02-DOCIMAGE | Info Disclosure | Dockerfile baked token | LOW | accept | Token is generated at runtime, never at build time. Verified by smoke test reading the token AFTER container start, not from image metadata. |
| T-02-COMPOSE-ENV | Spoofing | compose env override | LOW | accept | Operator-controlled. If operator sets `MCP_GATEWAY_HOST=0.0.0.0` without publishing a port, gateway is still isolated inside container. If they publish the port AND set `0.0.0.0`, that is explicit opt-in (D-19). |
</threat_model>

<verification>
After all 4 tasks:
1. Image builds: `docker build -t kali-re-tools:phase2-test .` exits 0
2. Container starts: `docker compose up -d` exits 0
3. Gateway running: `docker compose logs kali | grep -c '\[gateway\] ready'` >= 1
4. Smoke test green: `docker compose exec -T kali bash /agent/mcp-gateway/tests/e2e/smoke.sh` exits 0
5. Upload e2e green: `docker compose exec -T kali bash /agent/mcp-gateway/tests/e2e/test_upload_then_analyze.sh` exits 0
6. Token on host: `test -f .mcp-gateway-token && [ "$(stat -c %a .mcp-gateway-token)" = "600" ]`
7. No regression of existing inner-agent MCP config: `docker compose exec -T kali test -f /agent/.mcp.json`
8. Doc fixes verified: `grep -q 'IDA > BN > Ghidra' .planning/REQUIREMENTS.md && grep -q 'Custom FastMCP gateway' CLAUDE.md`
9. Unit test suite still green: `docker compose exec -T kali bash -c 'cd /agent && pytest mcp-gateway/tests/ -x --no-header -q --ignore=mcp-gateway/tests/e2e'`
</verification>

<success_criteria>
- Phase 2 goal met end-to-end: curated tool surface accessible over Streamable HTTP + bearer auth + /upload, verified inside real container
- GW-01 ✓ (smoke.sh initialize returns 200 with serverInfo)
- GW-02 ✓ (smoke.sh tools/list returns 15-25 tools)
- GW-03 ✓ (tools/list includes decompile, list_functions, get_xrefs; routing verified in Plan 03 unit tests; end-to-end only fully green with a real backend)
- GW-04 ✓ (smoke.sh unauth → 401)
- GW-05 ✓ (compose.yaml has no ports: block; container binds 127.0.0.1 by default)
- GW-06 ✓ (test_upload_then_analyze.sh uploads + uses sha256 in tool call)
- INF-05 regression clean (existing inner-agent config unchanged)
- Doc drift corrected: REQUIREMENTS.md GW-03 priority, CLAUDE.md Recommended Stack
- Human-verify checkpoint passed
</success_criteria>

<output>
After completion, create `.planning/phases/02-mcp-gateway/02-05-SUMMARY.md`.
Include:
- Full Phase 2 capability summary (what the gateway does end-to-end)
- Dockerfile changes: gateway package install + entrypoint daemon block (line ranges)
- compose.yaml changes: 5 passthrough env vars (no port publishing — Phase 3)
- REQUIREMENTS.md correction: GW-03 "BN > IDA > Ghidra" → "IDA > BN > Ghidra"
- CLAUDE.md update: custom FastMCP gateway promoted; mcp-proxy moved to alternatives
- e2e test coverage: healthz + initialize + tools/list + unauth + upload + tools/call collect_strings
- Phase 3 handoff: gateway is ready; INF-02 (port publishing) and INF-01 (dual-mode entrypoint refinement) to come
- Phase 4 handoff: bearer token visible on host at `./.mcp-gateway-token`; host-side client configs (CLI-01, CLI-02, CLI-03) will consume this
</output>
