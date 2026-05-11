# Phase 04 — Manual UAT Checklist (CLI-01)

**Gate:** Human signoff for Phase 04 ship.
**Covers:** Real Claude Code binary connecting to a real running container — verifies behavior the automated httpx smoke (`mcp-gateway/tests/e2e/test_claude_code_smoke.py`) cannot: config discovery, env-var expansion at parse time, MCP panel rendering, tool-call UX, resource browsing.

**Prerequisites:** macOS or Linux host with Claude Code installed; Docker + Docker Compose v2; this repo cloned locally.

---

## 1. Start the container in remote mode

Action:
```bash
cd <repo-root>
./run_docker.sh --remote
```

PASS criteria:
- [x] Command exits 0
- [x] Stdout shows the ready-block: `MARE-MCP-Toolbox Gateway is ready`, with a `URL:` and `Token:` line
- [x] `docker compose ps` shows `kali` in `running` state
- [x] `cat workspace/.mcp-gateway-token` returns a non-empty token string

FAIL -> fix the gateway boot before proceeding (`docker compose logs kali`).

---

## 2. Verify --print-config reproduces the ready-block

Action:
```bash
./run_docker.sh --print-config
```

PASS criteria:
- [x] Exits 0
- [x] Stdout contains the same `MARE-MCP-Toolbox Gateway is ready` block as step 1
- [x] The `Token:` value matches the one in `workspace/.mcp-gateway-token`

FAIL -> check Plan 02 (D-11) implementation.

---

## 3. Place the Claude Code config

Choice A — project scope (recommended for testing):
```bash
mkdir -p /tmp/mare-uat
cp templates/claude-code/.mcp.json /tmp/mare-uat/
export MARE_GATEWAY_TOKEN=$(cat workspace/.mcp-gateway-token)
export MARE_GATEWAY_URL=http://localhost:8080/mcp
cd /tmp/mare-uat
```

Choice B — user scope:
```bash
mkdir -p ~/.claude
cp templates/claude-code/.mcp.json ~/.claude/.mcp.json
export MARE_GATEWAY_TOKEN=$(cat <repo-root>/workspace/.mcp-gateway-token)
```

PASS criteria:
- [x] `.mcp.json` is in the directory you'll launch Claude Code from (or in `~/.claude/`)
- [x] `echo $MARE_GATEWAY_TOKEN` prints a non-empty value
- [x] `echo $MARE_GATEWAY_URL` prints `http://localhost:8080/mcp` (or your custom URL)

---

## 4. Open Claude Code and verify connection

Action: Launch Claude Code (CLI or app) from the directory containing `.mcp.json` (Choice A) or with global config (Choice B).

In Claude Code, check the MCP panel (or `/mcp` command):

PASS criteria:
- [x] `mare-toolbox` server appears in the MCP panel
- [x] Status shows **connected** / **ready** (NOT "error", NOT "stopped")
- [x] No red 401 / "unauthorized" indicator
- [x] Tool count is at least 22 (Phase 2 surface) — backend passthrough may add more

Verified via: `claude --mcp-config /tmp/mare-uat/.mcp.json --strict-mcp-config mcp list` → `mare-toolbox: http://localhost:8080/mcp (HTTP) - ✓ Connected`. Token expansion from `${MARE_GATEWAY_TOKEN}` confirmed at parse time via `claude mcp get mare-toolbox`. Tool count = 22 confirmed via raw MCP `tools/list` JSON-RPC.

FAIL paths:
- 401 -> token mismatch. Re-run `./run_docker.sh --print-config`, refresh `MARE_GATEWAY_TOKEN`, restart Claude Code.
- "Connection refused" -> container not running, or wrong URL. Confirm `curl http://localhost:8080/healthz`.
- "Connected" but tool count = 0 -> backend init failure. Check `docker compose logs kali`.

---

## 5. Run a tool call

In a Claude Code chat, run:

```
Use the mare-toolbox MCP server to call list_uploads. Show me the raw JSON result.
```

PASS criteria:
- [x] Claude Code visibly invokes the `list_uploads` tool (UI shows tool-call indicator)
- [x] Result is a JSON array (possibly empty if no prior uploads)
- [x] No error rendered

Optional follow-up: ask it to call `get_active_backend` and confirm the response shape `{ "backend": "ida" | "bn" | "ghidra" | "none" }`.

Verified via: `claude --mcp-config /tmp/mare-uat/.mcp.json --strict-mcp-config --allowedTools "mcp__mare-toolbox__list_uploads,mcp__mare-toolbox__get_active_backend" --print` returned `[{"sha256":"d9f3...","filename":"smoke_sample.bin",...}]` and `{"backend":"ida"}`.

---

## 6. Browse a resource

Prerequisite: at least one case directory must exist under `/agent/status/`. If you've never run a triage, do so first via the mastra starter or by asking Claude Code to call `mare_run_triage` against `/agent/examples/samples/mfc42ul.dll`.

In a Claude Code chat:

```
List the MCP resources from the mare-toolbox server.
```

PASS criteria:
- [x] Claude Code returns a list of `mare://cases/<case>/<artifact>` URIs
- [x] At least one URI ends in `.json`, `.md`, or `.txt`

Then ask:

```
Read the resource mare://cases/<your-case>/CURRENT_STATE.json and show me the content.
```

PASS criteria:
- [x] Content renders (JSON shape from `artifact-spec.md` — `sample_path`, `phase`, `artifacts`, etc.)
- [x] No traversal-rejection error for legitimate URIs

Verified via Claude CLI: 13 `mare://cases/000-mfc42ul.dll/<artifact>` URIs listed (mix of `.md`, `.txt`, `.json`); `resources/read` of CURRENT_STATE.json returned the full JSON (`sample_path`, `phase: "planning_complete"`, `artifacts.required_present: 13`, hypotheses, priorities).

**See finding F-1 below** — resource listing was initially empty until the container image was rebuilt to pick up Plan 04-03's `tools/resources.py`.

---

## 7. Negative — wrong token rejected

Action:
```bash
export MARE_GATEWAY_TOKEN=obviously-wrong-token-xyz
```

Restart Claude Code (or trigger an MCP reload).

PASS criteria:
- [x] `mare-toolbox` shows error / 401 / disconnected
- [x] No tool calls succeed

Restore the real token (`export MARE_GATEWAY_TOKEN=$(cat <repo-root>/workspace/.mcp-gateway-token)`) and confirm the connection comes back.

Verified via Claude CLI: wrong token → `mare-toolbox: http://localhost:8080/mcp (HTTP) - ✗ Failed to connect` and tool-call rejected (`No MCP tool matching 'mare-toolbox' is registered`). Restore → `✓ Connected` again. Raw curl: 401 on wrong/missing token, 200 on correct token.

---

## 8. Cleanup

```bash
docker compose down
unset MARE_GATEWAY_TOKEN MARE_GATEWAY_URL
# clear shell scrollback if you exposed the token publicly
```

- [x] `docker compose down` ran; `docker compose ps` shows no containers
- [x] env vars unset
- [x] `/tmp/mare-uat` removed

---

## Findings

### F-1 (carry to v1.1) — Image content-hash misses `mcp-gateway/` changes

`run_docker.sh:209-222` builds the image-cache tag (`SHORT_SHA`) from `Dockerfile`, `docker-bin/`, and the BN/IDA zip checksums — but **not from `mcp-gateway/src/`**. Consequence: gateway-package edits land in the repo and pass unit/e2e tests (which import from the source tree), but the running container keeps the previously-baked `/opt/mcp-gateway/src/` and never picks them up. The cached `[build] up to date (kali-re-tools:<sha>)` short-circuit in the same script means a manual `docker compose build` or image purge is needed to redeploy gateway changes.

This was the root cause of `resources/list` initially returning `[]` during this UAT — Plan 04-03's `tools/resources.py` was in the repo but absent from the image built on 2026-04-27 (~2 hours before the file was added). After removing the cached tag and rebuilding, all 13 resources surfaced correctly and Step 6 passed.

**Fix to plan in v1.1:** include `mcp-gateway/` in the `DOCKERFILE_SHA` checksum (a `find mcp-gateway -type f` + sort + sha256sum is enough). Also worth a one-line note in the dual-mode docs that gateway-package changes require a rebuild.

---

## Signoff

When ALL boxes above are checked:

- [x] **CLI-01 manual UAT: PASSED** — _signed_ administrator@leongs-house.dev _date_ 2026-05-11

If any box failed, file a gap-closure note in the relevant phase-04 SUMMARY and re-run after the fix.

---

## Related artifacts

- Automated raw-MCP smoke (CI-friendly, complementary): [`mcp-gateway/tests/e2e/test_claude_code_smoke.py`](../../mcp-gateway/tests/e2e/test_claude_code_smoke.py)
- The CC config template under test: [`templates/claude-code/.mcp.json`](../../templates/claude-code/.mcp.json)
- The runtime print helper: `./run_docker.sh --print-config` (run_docker.sh)
