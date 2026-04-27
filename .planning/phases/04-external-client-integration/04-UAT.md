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
- [ ] Command exits 0
- [ ] Stdout shows the ready-block: `MARE-MCP-Toolbox Gateway is ready`, with a `URL:` and `Token:` line
- [ ] `docker compose ps` shows `kali` in `running` state
- [ ] `cat workspace/.mcp-gateway-token` returns a non-empty token string

FAIL -> fix the gateway boot before proceeding (`docker compose logs kali`).

---

## 2. Verify --print-config reproduces the ready-block

Action:
```bash
./run_docker.sh --print-config
```

PASS criteria:
- [ ] Exits 0
- [ ] Stdout contains the same `MARE-MCP-Toolbox Gateway is ready` block as step 1
- [ ] The `Token:` value matches the one in `workspace/.mcp-gateway-token`

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
- [ ] `.mcp.json` is in the directory you'll launch Claude Code from (or in `~/.claude/`)
- [ ] `echo $MARE_GATEWAY_TOKEN` prints a non-empty value
- [ ] `echo $MARE_GATEWAY_URL` prints `http://localhost:8080/mcp` (or your custom URL)

---

## 4. Open Claude Code and verify connection

Action: Launch Claude Code (CLI or app) from the directory containing `.mcp.json` (Choice A) or with global config (Choice B).

In Claude Code, check the MCP panel (or `/mcp` command):

PASS criteria:
- [ ] `mare-toolbox` server appears in the MCP panel
- [ ] Status shows **connected** / **ready** (NOT "error", NOT "stopped")
- [ ] No red 401 / "unauthorized" indicator
- [ ] Tool count is at least 22 (Phase 2 surface) — backend passthrough may add more

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
- [ ] Claude Code visibly invokes the `list_uploads` tool (UI shows tool-call indicator)
- [ ] Result is a JSON array (possibly empty if no prior uploads)
- [ ] No error rendered

Optional follow-up: ask it to call `get_active_backend` and confirm the response shape `{ "backend": "ida" | "bn" | "ghidra" | "none" }`.

---

## 6. Browse a resource

Prerequisite: at least one case directory must exist under `/agent/status/`. If you've never run a triage, do so first via the mastra starter or by asking Claude Code to call `mare_run_triage` against `/agent/examples/samples/mfc42ul.dll`.

In a Claude Code chat:

```
List the MCP resources from the mare-toolbox server.
```

PASS criteria:
- [ ] Claude Code returns a list of `mare://cases/<case>/<artifact>` URIs
- [ ] At least one URI ends in `.json`, `.md`, or `.txt`

Then ask:

```
Read the resource mare://cases/<your-case>/CURRENT_STATE.json and show me the content.
```

PASS criteria:
- [ ] Content renders (JSON shape from `artifact-spec.md` — `sample_path`, `phase`, `artifacts`, etc.)
- [ ] No traversal-rejection error for legitimate URIs

---

## 7. Negative — wrong token rejected

Action:
```bash
export MARE_GATEWAY_TOKEN=obviously-wrong-token-xyz
```

Restart Claude Code (or trigger an MCP reload).

PASS criteria:
- [ ] `mare-toolbox` shows error / 401 / disconnected
- [ ] No tool calls succeed

Restore the real token (`export MARE_GATEWAY_TOKEN=$(cat <repo-root>/workspace/.mcp-gateway-token)`) and confirm the connection comes back.

---

## 8. Cleanup

```bash
docker compose down
unset MARE_GATEWAY_TOKEN MARE_GATEWAY_URL
# clear shell scrollback if you exposed the token publicly
```

---

## Signoff

When ALL boxes above are checked:

- [ ] **CLI-01 manual UAT: PASSED** — _signed_ ____________ _date_ ___________

If any box failed, file a gap-closure note in the relevant phase-04 SUMMARY and re-run after the fix.

---

## Related artifacts

- Automated raw-MCP smoke (CI-friendly, complementary): [`mcp-gateway/tests/e2e/test_claude_code_smoke.py`](../../mcp-gateway/tests/e2e/test_claude_code_smoke.py)
- The CC config template under test: [`templates/claude-code/.mcp.json`](../../templates/claude-code/.mcp.json)
- The runtime print helper: `./run_docker.sh --print-config` (run_docker.sh)
