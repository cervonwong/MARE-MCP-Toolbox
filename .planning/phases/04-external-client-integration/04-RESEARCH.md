# Phase 4: External Client Integration - Research

**Researched:** 2026-04-27
**Domain:** MCP Resources, Streamable HTTP clients (Claude Code + mastra.ai), Python httpx-based e2e testing, Bash heredoc refactor
**Confidence:** HIGH

## Summary

Phase 4 wires external MCP clients (Claude Code, mastra.ai) to the running gateway and adds case-artifact browsing via MCP Resources. All major architectural decisions are LOCKED in `04-CONTEXT.md` (D-01..D-16); this research is **prescriptive implementation guidance**, not exploration.

The work splits cleanly into four implementation seams: (1) a new `tools/resources.py` module that registers `mare://cases/<case>/<artifact>` resources via FastMCP's `@mcp.resource()` decorator + a low-level `list_resources` handler override for dynamic case enumeration, (2) `templates/claude-code/.mcp.json` byte-matched to the existing `run_docker.sh` ready-block, (3) `templates/mastra/` runnable starter pinned to `@mastra/mcp@1.3.x` per D-08, (4) a `tests/e2e/` Python pytest suite that uses `httpx` against a running container, mirroring the existing bash smoke-script JSON-RPC envelopes. The `--print-config` flag is a 30-line refactor that extracts the existing `run_docker.sh` heredoc (lines 297-345) into a shell function reused by both `--remote` and a new `--print-config` branch.

**Primary recommendation:** Implement Resources via a hybrid pattern — register one **template** (`mare://cases/{case}/{artifact}`) for URI discovery + override `mcp._mcp_server` low-level `list_resources` handler for dynamic per-request case enumeration. This avoids the `_resource_manager` static-cache trap and preserves the "resources reflect current filesystem" invariant.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**MCP Resources (CLI-04)**
- **D-01:** URI scheme is `mare://cases/<case>/<artifact>` — custom `mare://` scheme, hierarchical, namespaced. Example: `mare://cases/000-mfc42ul.dll/sample-profile.json`. The `/cases/` segment leaves room for future top-level namespaces (`mare://uploads/...`).
- **D-02:** `resources/list` enumerates **all cases** under `/agent/status/` (mirrors `list_cases()`), not just the active case. Active case state does NOT gate resource listing.
- **D-03:** Expose **all 13 pipeline artifacts** as resources (per `artifact-spec.md`). Read-only; lazy-read on `resources/read`.
- **D-04:** **MIME types inferred from extension** at read time:
  - `.json` → `application/json`
  - `.txt` / `.log` → `text/plain`
  - `.md` → `text/markdown`
  - Anything else → `application/octet-stream`
- **D-05:** **Uploads are NOT exposed as resources.** Remain accessible via `list_uploads()` / `get_sample_info()` tools only.

**Mastra.ai template (CLI-02, CLI-03)**
- **D-06:** Ship a **full runnable starter project** at `templates/mastra/` containing `package.json` + `tsconfig.json` + `.env.example` + `src/index.ts` + `README.md`.
- **D-07:** Starter demonstrates the **full triage happy path**: connect → upload sample → call `run_triage` → fetch the resulting report.
- **D-08:** **Pin `@mastra/mcp` to `1.3.x`** and `@mastra/core` to latest.
- **D-09:** Starter README ALSO carries a **5-10 line drop-in MCPClient snippet** for users with an existing mastra project.

**Claude Code template (CLI-01, CLI-03)**
- **D-10:** Ship `templates/claude-code/.mcp.json` — bare working snippet with placeholder values. The file is the **reference**; `run_docker.sh --remote` print block remains the **canonical onboarding UX**.
- **D-11:** Add **`./run_docker.sh --print-config`** flag. Reads `workspace/.mcp-gateway-token` and re-renders the same ready-block. Pure print, no compose action. Fail loudly if no token file.

**End-to-end verification**
- **D-12:** CLI-01 verification = (a) automated raw-MCP smoke test using Python `httpx` exercising `initialize` → `tools/list` → `tools/call`, AND (b) documented manual UAT checklist.
- **D-13:** CLI-02 verification = `templates/mastra/` starter doubles as the test. Pytest case runs `npm install && npm start` against running gateway in temp dir.
- **D-14:** CLI-04 verification = automated test issuing `resources/list` then `resources/read`. Asserts URI scheme, MIME types, non-empty content.
- **D-15:** New e2e tests live at `mcp-gateway/tests/e2e/` — co-located. Reuses existing `pyproject.toml` pytest config.

**Documentation**
- **D-16:** **Full top-level `README.md` rewrite is in scope** — covers install, local mode, remote mode, Claude Code config, mastra.ai config, resource browsing. Phase 3's deferred README rewrite is ABSORBED here.

### Claude's Discretion

- Exact placeholder syntax inside `templates/claude-code/.mcp.json` (e.g., `TOKEN-HERE` vs `<paste-token>` vs `${MCP_GATEWAY_TOKEN}`).
- Node version pin and `engines` field in `templates/mastra/package.json` (likely `>=18` or `>=20`).
- Whether `templates/mastra/src/index.ts` uses a hardcoded sample path / sha256 or accepts a CLI arg.
- Whether `--print-config` reuses an extracted bash function (`print_ready_block()`) or duplicates the heredoc. Refactor only if low-cost.
- Resource content size cap inside `resources/read` — default to "read whole file" unless this proves problematic.
- Whether to also touch `mcp-gateway/README.md` in addition to top-level README rewrite.
- Logging/error shape for `resources/read` when an artifact file is missing (case exists but pipeline didn't run that step yet).
- Test fixture choice for the e2e harness — reuse `examples/mfc42u.dll` or generate tiny synthetic binary.

### Deferred Ideas (OUT OF SCOPE)

- Resource update notifications (`notifications/resources/list_changed`, `resources/subscribe`) → v2 (GW-V2-02 / GW-V2-03)
- MCP Prompts exposing orchestrator workflows → v2 (GW-V2-01)
- Multi-session / concurrent independent analyses → v2 (GW-V2-03). Phase 4 keeps single-process active-case state.
- Truncation/streaming of very large artifacts in `resources/read`
- Per-tool / per-resource scopes / fine-grained auth → bearer-only
- OAuth 2.1 client flow → out of scope
- Uploads as MCP Resources → explicitly rejected (D-05)
- Codex on-host config template → not in CLI-01..CLI-04 scope
- mcp-gateway/README.md thorough rewrite → follow-up
- CI wiring for the e2e tests
- Backend comparison / unified disasm normalization → v2

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **CLI-01** | Claude Code connects to container via `.mcp.json` with `type: "http"` and bearer token header | Confirmed schema in [Claude Code MCP docs](https://code.claude.com/docs/en/mcp): `type:"http"`, `url`, `headers.Authorization`, `${VAR}` env-var expansion. Templated `.mcp.json` matches existing `run_docker.sh` heredoc byte-for-byte (lines 314-324). |
| **CLI-02** | Mastra.ai connects to container via `MCPClient` with same Streamable HTTP endpoint | Confirmed `MCPClient` import path (`@mastra/mcp`), constructor shape (`servers: { name: { url, requestInit: { headers } } }`), auto-detection of Streamable HTTP per [mastra docs](https://mastra.ai/reference/tools/mcp-client). |
| **CLI-03** | Pre-built config templates provided for Claude Code (`.mcp.json` snippet) and mastra.ai | Two deliverables: `templates/claude-code/.mcp.json` (D-10) + `templates/mastra/` runnable starter (D-06). Both work with bearer-token substitution only. |
| **CLI-04** | MCP Resources expose case artifacts as browsable resources | Verified `FastMCP.resource()` accepts custom `mare://` scheme (tested in mcp 1.27.x venv); template + low-level `list_resources` override pattern documented below. |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

The following directives from `CLAUDE.md` (project root) are mandatory:

- **`@mastra/mcp` pinned to `1.3.x`** — CONTEXT D-08 + CLAUDE.md Version Compatibility Matrix. Despite latest npm being `1.5.2`, the project's tested combination is `1.3.x`. **Do not pin to caret-range** (`^1.3.0`) — use exact `~1.3.1` or pin to `1.3.x` literal range.
- **`@mastra/core` to latest** — CLAUDE.md says "latest"; CONTEXT D-08 reaffirms.
- **Streamable HTTP transport (2025-03-26)** — already wired in Phase 2; clients must use HTTP, not SSE. Both Claude Code and mastra.ai auto-fallback to SSE if needed but should connect Streamable HTTP first.
- **Bearer token = sole auth** — Phase 2 D-12, D-18; Phase 4 must NOT introduce a second auth surface (no per-client tokens, no scopes, no OAuth). Templates and tests reference `Authorization: Bearer <token>` exclusively.
- **Do NOT use `mcp-remote` (npm)** — CVE-2025-6514 (CVSS 9.6 command injection). Templates must not reference it.
- **Do NOT use SSE legacy transport in templates** — deprecated June 2025. URLs end in `/mcp`, not `/sse`.
- **Do NOT use `MastraMCPClient` (legacy)** — use `MCPClient` from `@mastra/mcp`.
- **Use GSD workflow for repo edits** (workspace/CLAUDE.md): all repo changes routed through `/gsd:execute-phase` per the workflow enforcement directive.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mcp` (Python SDK) | `>=1.27,<1.28` | FastMCP server, Resources API, low-level `Server` access | Already pinned in `mcp-gateway/pyproject.toml`. Resources API stable since 1.20. `[VERIFIED: pyproject.toml + venv smoke test]` |
| `@mastra/mcp` | `1.3.1` (within `1.3.x`) | Mastra MCPClient for the starter project | CLAUDE.md + CONTEXT D-08 lock. Latest 1.3.x is `1.3.2` (published 2026-03-30). Recommend `~1.3.1` (allows 1.3.x patch updates). `[VERIFIED: npm registry, latest 1.5.2 published 2026-04-24]` |
| `@mastra/core` | `^1.28.0` | Mastra framework runtime | Latest 1.28.0 published 2026-04-24. CLAUDE.md says "latest"; safe to take latest minor. `[VERIFIED: npm registry]` |
| `httpx` | `>=0.27` | Python e2e HTTP client (raw MCP smoke test) | Already a gateway dependency (`pyproject.toml`). Async + sync both supported; tests can use sync for simplicity. `[VERIFIED: pyproject.toml]` |
| `pytest` + `pytest-asyncio` | `>=8` / `>=0.23` | Test framework (e2e suite) | Already in `[project.optional-dependencies] dev`; `asyncio_mode = "auto"` configured. `[VERIFIED: pyproject.toml]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `typescript` | `^5.4` | TypeScript compiler for mastra starter | mastra projects are TS-first. Use the same major as mastra docs. `[ASSUMED — verify against mastra 1.3.x peer deps]` |
| `tsx` | `^4.7` | TS execution for `npm start` | Lighter than ts-node; mastra examples use it. `[ASSUMED]` |
| `zod` | `^3.25.0 \|\| ^4.0.0` | Schema validation (peer dep of @mastra/mcp 1.3.x) | Required peer; install explicitly to avoid resolution surprises. `[VERIFIED: npm registry @mastra/mcp@1.3.1 peerDependencies]` |
| `dotenv` | `^16` | Load `.env` in mastra starter | Standard pattern for token + URL env loading in Node. `[ASSUMED]` |
| Python `mimetypes` (stdlib) | n/a | MIME type inference for resources | Built-in. Verified `.md → text/markdown` works on Linux but `.log → (None, None)`. **Use a hand-rolled override map** (D-04 list) and fall back to `application/octet-stream`. `[VERIFIED: Python 3.12 stdlib smoke test]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python `httpx` for e2e tests | `requests` (sync only) | `httpx` is already a dependency; `requests` would be added cost. Use `httpx`. |
| Pytest e2e harness | Bash scripts (existing `smoke.sh`, `test_upload_then_analyze.sh`) | Existing bash scripts work but don't integrate with `pytest` runner. New tests should be Python-native (D-15) for unified `pytest mcp-gateway/tests/` invocation. The existing bash scripts can be retained as-is for ad-hoc CLI smoke. |
| Override `_resource_manager.list_resources` (private attr) | Override low-level `mcp._mcp_server.list_resources` decorator (public-ish API) | Private-attr access breaks on SDK upgrade. Use the low-level `Server.list_resources()` decorator path — same pattern Phase 2 used to keep tools-list public-API-clean (`test_tool_list.py`). |
| `npx -y` install in mastra starter | Explicit `npm install` step | `npm install` is what users do; explicit is clearer. CONTEXT D-13 says "npm install && npm start". |
| Custom port for tests | Reuse `MCP_GATEWAY_HOST_PORT=8080` from running container | Tests assume an already-running container per D-15. |

**Installation:**
```bash
# Python (already done — gateway pyproject.toml)
# No changes required; resources module just imports from mcp.server.fastmcp.

# Node (templates/mastra/package.json — exact version pinning per D-08)
npm install --save \
  @mastra/mcp@~1.3.1 \
  @mastra/core@latest \
  zod@^3.25.0 \
  dotenv@^16
npm install --save-dev \
  typescript@^5.4 \
  tsx@^4.7 \
  @types/node@^20
```

**Version verification (run before locking templates/mastra/package.json):**
```bash
npm view @mastra/mcp version            # confirm latest 1.3.x
npm view @mastra/mcp@~1.3.1 version     # what ~1.3.1 resolves to
npm view @mastra/core version           # confirm latest
npm view @mastra/mcp@1.3.1 peerDependencies  # confirm zod range
```

Verified at research time (2026-04-27): `@mastra/mcp@1.3.2` (published 2026-03-30, latest 1.3.x), `@mastra/core@1.28.0` (published 2026-04-24), peer `zod@^3.25.0 || ^4.0.0`. `[VERIFIED: npm registry HTTP query]`

## Architecture Patterns

### Recommended Project Structure
```
.
├── README.md                       # REWRITE (D-16): two-mode framing
├── run_docker.sh                   # MODIFY: add --print-config flag (D-11)
├── templates/                      # NEW directory (D-06, D-10)
│   ├── claude-code/
│   │   └── .mcp.json               # NEW: CC config template (D-10)
│   └── mastra/
│       ├── package.json            # NEW: pinned @mastra/mcp@~1.3.1 (D-08)
│       ├── tsconfig.json
│       ├── .env.example
│       ├── README.md               # carries the 5-10 line drop-in snippet (D-09)
│       └── src/
│           └── index.ts            # full triage happy path (D-07)
└── mcp-gateway/
    ├── src/mcp_gateway/
    │   ├── tools/
    │   │   ├── __init__.py         # MODIFY: add `from . import resources; resources.register(mcp)`
    │   │   ├── cases.py            # unchanged (Resources reuses STATUS_ROOT + CASE_NAME_RE)
    │   │   ├── samples.py          # unchanged (Resources imports STATUS_ROOT)
    │   │   └── resources.py        # NEW (D-01..D-05)
    │   └── app.py                  # unchanged (register_all_tools already wires the new module)
    └── tests/e2e/
        ├── __init__.py             # NEW (empty, makes the dir a package)
        ├── conftest.py             # NEW: gateway_url + bearer_token fixtures (env-driven)
        ├── test_claude_code_smoke.py   # NEW (D-12): initialize → tools/list → tools/call
        ├── test_resources.py           # NEW (D-14): resources/list + resources/read
        └── test_mastra_starter.py      # NEW (D-13): subprocess npm install && npm start
```

### Pattern 1: FastMCP Resource Registration with Custom URI Scheme

**What:** Register one **template** for URI discovery + override low-level `list_resources` for dynamic per-request enumeration.

**When to use:** When list contents change at runtime (cases come and go) AND clients need a stable URI shape to construct reads.

**Why hybrid:** `FastMCP.list_resources()` reads from `_resource_manager`'s static cache. Mutating the cache on every request is fragile. Registering a **template** alone shows up only in `resources/templates/list` (NOT in `resources/list`) — most clients only call `resources/list`. We need both.

**Example:**
```python
# Source: VERIFIED via mcp 1.27.x venv smoke test (2026-04-27)
# File: mcp-gateway/src/mcp_gateway/tools/resources.py
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Iterable

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.resources import FunctionResource
import mcp.types as mcp_types
from pydantic import AnyUrl

from .cases import CASE_NAME_RE
from .samples import STATUS_ROOT

log = logging.getLogger("mcp_gateway.resources")

# D-03: 13 required artifacts per workspace/.claude/skills/.../artifact-spec.md
ARTIFACTS = (
    "00_sample_profile.md",
    "01_strings_raw.txt",
    "02_strings_interesting.md",
    "03_imports_raw.txt",
    "04_imports_interesting.md",
    "05_behavior_hypotheses.md",
    "06_component_inventory.md",
    "07_interaction_model.md",
    "08_deep_analysis_plan.md",
    "09_priority_queue.md",
    "10_reporting_draft.md",
    "INDEX.md",
    "CURRENT_STATE.json",
)

# D-04: hand-rolled extension → MIME map (stdlib mimetypes returns None for .log)
_MIME_MAP = {
    ".json": "application/json",
    ".txt":  "text/plain",
    ".log":  "text/plain",
    ".md":   "text/markdown",
}

def _mime_for(path: Path) -> str:
    return _MIME_MAP.get(path.suffix.lower(), "application/octet-stream")


def _list_cases() -> list[str]:
    """Reuse the same enumeration as tools/cases.py:list_cases. Returns case dir names."""
    if not STATUS_ROOT.exists():
        return []
    return sorted(
        p.name for p in STATUS_ROOT.iterdir()
        if p.is_dir() and CASE_NAME_RE.match(p.name)
    )


def _build_resource_list() -> list[mcp_types.Resource]:
    """D-02: enumerate all 13 artifacts × all cases. List is dynamic per-request."""
    out: list[mcp_types.Resource] = []
    for case in _list_cases():
        for artifact in ARTIFACTS:
            uri = f"mare://cases/{case}/{artifact}"
            artifact_path = STATUS_ROOT / case / artifact
            out.append(mcp_types.Resource(
                uri=AnyUrl(uri),
                name=f"{case}/{artifact}",
                description=f"Pipeline artifact for case {case}",
                mimeType=_mime_for(artifact_path),
            ))
    return out


def register(mcp: FastMCP) -> None:
    """Register Resources (D-01..D-05).

    Two-pronged:
      1. A template `mare://cases/{case}/{artifact}` so clients can discover the URI
         shape via `resources/templates/list` and read by-URI even for cases that
         appear after their last list_resources call.
      2. A custom `resources/list` handler on the underlying low-level Server that
         enumerates the live filesystem at request time (D-02 dynamism).
    """

    # (1) Template — registers the URI shape for `resources/templates/list`.
    @mcp.resource("mare://cases/{case}/{artifact}")
    def read_case_artifact(case: str, artifact: str) -> str | bytes:
        """Read a single pipeline artifact. Custom URI scheme: mare:// (D-01)."""
        # T-02-PATHTRAVERSAL: validate case name + artifact name against allowlists.
        if not CASE_NAME_RE.match(case):
            raise ValueError(f"invalid case name: {case!r}")
        if artifact not in ARTIFACTS:
            raise ValueError(f"unknown artifact name: {artifact!r}")
        path = STATUS_ROOT / case / artifact
        # Defense in depth: ensure resolved path stays under STATUS_ROOT.
        real = path.resolve()
        if not str(real).startswith(str(STATUS_ROOT.resolve()) + os.sep):
            raise ValueError(f"path traversal rejected: {path}")
        if not real.exists():
            # Structured MCP error: case exists but artifact missing (pipeline in progress).
            raise FileNotFoundError(f"artifact {artifact} not present for case {case}")
        # Text formats: return str. Binary: return bytes.
        mime = _mime_for(real)
        if mime.startswith("text/") or mime == "application/json":
            return real.read_text(encoding="utf-8", errors="replace")
        return real.read_bytes()

    # (2) Override the low-level Server's `resources/list` handler for dynamic listing.
    # This is the public-API-stable path (FastMCP exposes `_mcp_server` as the
    # underlying `mcp.server.lowlevel.server.Server`).
    @mcp._mcp_server.list_resources()
    async def list_all_case_artifacts() -> list[mcp_types.Resource]:
        return _build_resource_list()
```

**Wire it up:** `mcp-gateway/src/mcp_gateway/tools/__init__.py`:
```python
from . import cases, artifacts, workflows, disasm, resources  # add `resources`
cases.register(mcp)
artifacts.register(mcp)
workflows.register(mcp)
disasm.register(mcp)
resources.register(mcp)  # new line
```

### Pattern 2: Claude Code `.mcp.json` Template

**What:** Project-scope `.mcp.json` with `type: "http"`, `url`, and bearer header. Use `${VAR}` env-var expansion for the token (Claude Code documented behavior).

**When to use:** Phase 4 ships this verbatim at `templates/claude-code/.mcp.json`.

**Example:**
```json
// Source: code.claude.com/docs/en/mcp, Phase 3 ready-block heredoc
{
  "mcpServers": {
    "mare-toolbox": {
      "type": "http",
      "url": "${MARE_GATEWAY_URL:-http://localhost:8080/mcp}",
      "headers": {
        "Authorization": "Bearer ${MARE_GATEWAY_TOKEN}"
      }
    }
  }
}
```

**Why env-var expansion (over hardcoded `TOKEN-HERE` placeholder):** Claude Code supports `${VAR}` and `${VAR:-default}` natively. Users export `MARE_GATEWAY_TOKEN=$(cat workspace/.mcp-gateway-token)` and the same `.mcp.json` works across machines. The boot-time print block (`run_docker.sh`) emits a hardcoded form for first-time copy-paste; the checked-in template uses env vars for portability. **Both forms are valid; pick env-var expansion for the checked-in template** since that's what Claude Code's docs recommend for shared-team configs.

### Pattern 3: Mastra MCPClient with Bearer Auth

**What:** `MCPClient` from `@mastra/mcp` with a `requestInit` block carrying the Authorization header.

**When to use:** `templates/mastra/src/index.ts` and the README drop-in snippet (D-09).

**Example:**
```typescript
// Source: VERIFIED via mastra.ai/reference/tools/mcp-client (2026-04-27)
// File: templates/mastra/src/index.ts (the canonical happy-path script)
import { MCPClient } from "@mastra/mcp";
import "dotenv/config";

const TOKEN = process.env.MARE_TOKEN;
const URL_  = process.env.MARE_URL ?? "http://localhost:8080/mcp";
if (!TOKEN) throw new Error("MARE_TOKEN env var required");

const mcp = new MCPClient({
  servers: {
    mare: {
      url: new URL(URL_),
      requestInit: {
        headers: { Authorization: `Bearer ${TOKEN}` },
      },
    },
  },
});

// (1) discover tools
const tools = await mcp.getTools();          // returns flat record keyed by `mare_<tool>`
console.log("Tools available:", Object.keys(tools).length);

// (2) upload a sample (separate /upload endpoint per Phase 2 D-11)
const samplePath = process.argv[2] ?? "./sample.bin";
const fs = await import("node:fs/promises");
const sampleBytes = await fs.readFile(samplePath);
const uploadResp = await fetch(URL_.replace(/\/mcp$/, "/upload"), {
  method: "POST",
  headers: { Authorization: `Bearer ${TOKEN}`, "X-Filename": samplePath.split("/").pop()! },
  body: sampleBytes,
});
const { sample_id } = await uploadResp.json() as { sample_id: string };
console.log("Uploaded:", sample_id);

// (3) run triage with the sha256
const triageTool = tools["mare_run_triage"];   // mastra namespaces tools as `<server>_<tool>`
const triageResult = await triageTool.execute({ context: { sample: sample_id } });
console.log("Triage result:", triageResult);

// (4) fetch report artifact via tools (Phase 2 get_artifact)
const artifactTool = tools["mare_get_artifact"];
const report = await artifactTool.execute({
  context: { case_id: `${sample_id}`, artifact_name: "10_reporting_draft.md" },
});
console.log("Report excerpt:", String(report).slice(0, 200));

await mcp.disconnect();
```

**Drop-in snippet for D-09 README** (5-10 lines, paste-ready):
```typescript
import { MCPClient } from "@mastra/mcp";

const mcp = new MCPClient({
  servers: {
    mare: {
      url: new URL(process.env.MARE_URL ?? "http://localhost:8080/mcp"),
      requestInit: { headers: { Authorization: `Bearer ${process.env.MARE_TOKEN}` } },
    },
  },
});
const tools = await mcp.getTools();
```

**API NOTE:** `MCPClient.getTools()` (returns flat namespace-prefixed record) is the canonical 1.3.x path; some older docs reference `listTools()` (returns the raw MCP tool list). Both exist in 1.3.x but `getTools()` is the integration-ready form for `Agent` consumption. `[CITED: mastra.ai/reference/tools/mcp-client]`

### Pattern 4: Python httpx-based Raw-MCP Smoke Test

**What:** Sync `httpx.Client` issuing JSON-RPC envelopes against the `/mcp` endpoint with bearer auth. Mirrors the existing `mcp-gateway/tests/e2e/smoke.sh` pattern but in Python so it integrates with `pytest`.

**When to use:** `tests/e2e/test_claude_code_smoke.py`, `tests/e2e/test_resources.py`.

**Streamable HTTP wire details (verified):**
- `Content-Type: application/json` on requests
- `Accept: application/json, text/event-stream` (gateway returns JSON when `json_response=True` is set in `app.py:38`)
- `Authorization: Bearer <token>` required on every `/mcp` POST
- JSON-RPC method names: `initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read`, `resources/templates/list`
- The gateway runs `stateless_http=True` (`app.py:39`), so no session-id management needed for these tests.

**Example:**
```python
# Source: derived from mcp-gateway/tests/e2e/smoke.sh + mcp 1.27 wire format
# File: mcp-gateway/tests/e2e/conftest.py
import os
from pathlib import Path
import pytest
import httpx

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def gateway_url() -> str:
    """Default to the host-published gateway port; override with GATEWAY_URL env."""
    return os.environ.get("GATEWAY_URL", "http://127.0.0.1:8080")


@pytest.fixture(scope="session")
def bearer_token() -> str:
    """Read token from env var or workspace/.mcp-gateway-token (host-side)."""
    tok = os.environ.get("MARE_TOKEN") or os.environ.get("MCP_GATEWAY_TOKEN")
    if tok:
        return tok.strip()
    candidates = [
        REPO_ROOT / "workspace" / ".mcp-gateway-token",
        Path("/agent/.mcp-gateway-token"),
    ]
    for c in candidates:
        if c.exists() and c.stat().st_size > 0:
            return c.read_text().strip()
    pytest.skip(
        "no gateway token found — start the container with `./run_docker.sh --remote`"
    )


@pytest.fixture(scope="session")
def mcp_client(gateway_url, bearer_token):
    """Sync httpx client preconfigured with auth + Streamable HTTP headers."""
    with httpx.Client(
        base_url=gateway_url,
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        # MCP requires `initialize` once per session before any tools/resources call.
        init = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "phase4-pytest", "version": "1"},
            },
        })
        init.raise_for_status()
        yield client
```

```python
# File: mcp-gateway/tests/e2e/test_resources.py (CLI-04 verification, D-14)
def test_resources_list_includes_mare_uri(mcp_client):
    resp = mcp_client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {},
    })
    resp.raise_for_status()
    body = resp.json()
    resources = body["result"]["resources"]
    assert any(r["uri"].startswith("mare://cases/") for r in resources), (
        "no mare://cases/... resources surfaced (D-01 URI scheme not wired?)"
    )


def test_resource_mime_types(mcp_client):
    resp = mcp_client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {},
    })
    resources = resp.json()["result"]["resources"]
    by_ext = {
        ".json": "application/json",
        ".md":   "text/markdown",
        ".txt":  "text/plain",
    }
    for r in resources:
        for ext, expected in by_ext.items():
            if r["uri"].endswith(ext):
                assert r["mimeType"] == expected, f"{r['uri']} → {r['mimeType']} (expected {expected})"


def test_resources_read_returns_content(mcp_client):
    # Seed expectation: at least one case must exist; if none, skip.
    listed = mcp_client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 4, "method": "resources/list", "params": {},
    }).json()["result"]["resources"]
    if not listed:
        import pytest
        pytest.skip("no cases under /agent/status/ — run a triage first")
    target = listed[0]
    read = mcp_client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 5, "method": "resources/read",
        "params": {"uri": target["uri"]},
    })
    read.raise_for_status()
    contents = read.json()["result"]["contents"]
    assert contents, "resources/read returned no contents block"
    # Either text or blob is present.
    assert "text" in contents[0] or "blob" in contents[0]
```

### Pattern 5: pytest Subprocess Test for Mastra Starter

**What:** Pytest test that copies `templates/mastra/` to `tmp_path`, runs `npm install` then `npm start`, captures stdout, asserts on expected markers.

**When to use:** `tests/e2e/test_mastra_starter.py` (D-13).

**Example:**
```python
# File: mcp-gateway/tests/e2e/test_mastra_starter.py
import os
import shutil
import subprocess
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MASTRA_TEMPLATE = REPO_ROOT / "templates" / "mastra"


@pytest.mark.skipif(
    shutil.which("npm") is None,
    reason="npm not on PATH — install Node.js to run mastra starter test",
)
def test_mastra_starter_runs_against_gateway(tmp_path, gateway_url, bearer_token):
    # 1. Copy template to a fresh dir so node_modules/ stays out of the repo.
    work = tmp_path / "mastra"
    shutil.copytree(MASTRA_TEMPLATE, work)

    env = {
        **os.environ,
        "MARE_URL":   gateway_url + "/mcp",
        "MARE_TOKEN": bearer_token,
        # CI hint: keep npm quiet
        "npm_config_loglevel": "error",
    }

    # 2. npm install (allow up to 120s for first install).
    install = subprocess.run(
        ["npm", "install", "--no-audit", "--no-fund"],
        cwd=work, env=env, capture_output=True, text=True, timeout=180,
    )
    assert install.returncode == 0, f"npm install failed: {install.stderr[-1000:]}"

    # 3. npm start (sample baked into examples/ inside the container; for the
    #    host-side test we point the script at the workspace example).
    sample = REPO_ROOT / "workspace" / "examples" / "samples" / "mfc42ul.dll"
    run = subprocess.run(
        ["npm", "start", "--silent", "--", str(sample)],
        cwd=work, env=env, capture_output=True, text=True, timeout=120,
    )
    assert run.returncode == 0, f"npm start failed: {run.stderr[-1000:]}"
    # Expected stdout markers (script prints these — see Pattern 3 example):
    assert "Tools available:" in run.stdout
    assert "Uploaded:" in run.stdout
    assert "Triage result:" in run.stdout
```

**Note on subprocess hygiene:**
- Use `capture_output=True, text=True` for clean assertions; avoid streaming.
- `timeout=` on every `subprocess.run` — npm-install can stall on a flaky registry.
- Slice `stderr[-1000:]` in failure messages — full npm output is multi-MB.
- Use `tmp_path` (pytest builtin) so node_modules/ never escapes into the repo tree.

### Pattern 6: `run_docker.sh --print-config` Refactor

**What:** Extract the existing ready-block heredoc (lines 297-345) into a shell function. Both `--remote` (post-up) and the new `--print-config` branch call the function.

**When to use:** D-11 implementation. Per Claude's discretion in CONTEXT, refactor only if low-cost — and it IS low-cost (~25 lines extracted into a function).

**Example sketch:**
```bash
# Add near the top of run_docker.sh (after flag parsing, before mode switches).
print_ready_block() {
  local token="$1"
  local host_bind="$2"
  local host_port="$3"
  local display_host="$host_bind"
  if [[ "$host_bind" == "0.0.0.0" ]]; then display_host="localhost"; fi
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
     Tip: shell scrollback may retain the bearer token; clear it before
          sharing your screen.

WARN
  fi
}

# New branch in flag parser (parallel to --remote):
#   --print-config) MODE="print-config"; shift ;;

# Handle MODE="print-config" before the build/compose chain:
if [[ "$MODE" == "print-config" ]]; then
  TOKEN_FILE="$HOST_PWD/.mcp-gateway-token"
  if [[ ! -s "$TOKEN_FILE" ]]; then
    echo "[error] no token file at $TOKEN_FILE" >&2
    echo "[error] start the container first: ./run_docker.sh --remote" >&2
    exit 1
  fi
  TOKEN=$(< "$TOKEN_FILE"); TOKEN="${TOKEN%$'\n'}"
  print_ready_block "$TOKEN" \
    "${MCP_GATEWAY_HOST_BIND:-0.0.0.0}" \
    "${MCP_GATEWAY_HOST_PORT:-8080}"
  exit 0
fi
```

### Anti-Patterns to Avoid

- **Mutating `mcp._resource_manager._resources` directly to "refresh" the list.** This is private API; the SDK is pinned `<1.28` partly to insulate against this, but the public-API path (`@mcp._mcp_server.list_resources()` decorator) is stable and cleaner.
- **Hardcoding the token into `templates/claude-code/.mcp.json`.** Use `${MARE_GATEWAY_TOKEN}` expansion. Hardcoded tokens leak via git.
- **Using `npx -y` to run mastra starter.** Users expect a normal `npm install && npm start` (CONTEXT D-13 wording).
- **Returning `bytes` from a `mare://...md` resource.** Markdown is text — return `str`. The MCP spec packages text resources as `{ uri, mimeType, text }` and binary as `{ uri, mimeType, blob }` (base64). Mixing them confuses clients.
- **Calling `resources/list` over and over without `initialize` first.** MCP spec mandates `initialize` once per session. Pytest fixture handles this once at session scope; per-test calls reuse the same `httpx.Client`.
- **Path traversal in `read_case_artifact(case, artifact)`.** Phase 2 already validates via `_resolve_allowed`; the new resources code MUST do the same (CASE_NAME_RE + ARTIFACTS allowlist + resolved-path-under-STATUS_ROOT check).
- **Spawning a fresh gateway in `tests/e2e/conftest.py`.** Per CONTEXT specifics: "E2E tests MUST be runnable against a running container, not require restarting it." Read the token + URL from env / token file; `pytest.skip()` if not running.
- **Pinning `@mastra/mcp@^1.3.0`.** Caret allows 1.4.x and 1.5.x — D-08 says strictly 1.3.x. Use `~1.3.1` or `>=1.3.0,<1.4.0` literal.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP protocol envelopes | Custom JSON-RPC builder | `httpx` POST to `/mcp` with `{jsonrpc, id, method, params}` literal | Three-method test surface (`initialize`/`tools/list`/`tools/call`/`resources/*`); no need for `mcp.ClientSession` overhead in e2e tests. The bash smoke uses raw POST and works fine. |
| Resource enumeration on every read | Custom in-memory cache | Hit the filesystem each `resources/list` call | `/agent/status/` listing is cheap (handful of dirs, dozens of files); no cache invalidation logic needed. Phase 4 is single-session (active-case state stays process-global per Phase 2 D-04). |
| URI scheme validation | Custom regex check on `case` and `artifact` | Reuse `CASE_NAME_RE` from `tools/cases.py` + `ARTIFACTS` tuple allowlist | Single source of truth; cases.py already validates. |
| MIME type detection | Custom magic-byte sniffer | Hand-rolled extension map (per D-04) with `application/octet-stream` fallback | Spec calls for 4 cases; magic-byte detection is over-engineering. Stdlib `mimetypes` would work for `.json`/`.md`/`.txt` but returns `None` for `.log` on stock Linux — the hand-rolled map is more deterministic. |
| Token discovery in tests | Polling for the file with custom retry | Read once at fixture session-scope, `pytest.skip()` if absent | Tests assume container is already running (CONTEXT specifics). If not, skip cleanly — don't try to start one. |
| Mastra MCP transport selection | Forcing SSE in `MCPClient` | Pass a `url` (no transport flag) — auto-detects Streamable HTTP, falls back to SSE | Default behavior is correct for our gateway (Streamable HTTP per Phase 2). |
| `npm start` script | Custom Node executable | `tsx src/index.ts` via `npm start` | Standard mastra/Node pattern; tsx is mastra's recommended TS runner. |
| Subprocess test orchestration | Manual `Popen + communicate` | `subprocess.run(..., capture_output=True, text=True, timeout=...)` | Built-in pattern handles all edge cases for "run, wait, capture, fail-on-nonzero". |

**Key insight:** Phase 4 is plumbing, not invention. Every component (MCP Resources, Streamable HTTP, mastra MCPClient, .mcp.json) is documented and tested upstream. Build *thin wrappers* that hand off to upstream APIs. The most likely failure mode is over-engineering — adding caches, custom URI parsers, or custom transports where the SDK already handles it.

## Runtime State Inventory

> Phase 4 is **mostly additive** (new files in `templates/`, new module in `tools/resources.py`, new `tests/e2e/` test files, new `--print-config` branch). One small refactor (extracting `print_ready_block()` from `run_docker.sh`).

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | None — Resources are read-only views over `/agent/status/<case>/*`; no new persistence. | None. |
| **Live service config** | None — gateway env vars (`MCP_GATEWAY_*`) unchanged from Phase 3. No new compose vars needed for Phase 4. | None. |
| **OS-registered state** | None — no new daemons, no new ports, no new systemd/launchd entries. Gateway already runs from Phase 2/3. | None. |
| **Secrets/env vars** | `MCP_GATEWAY_TOKEN` continues to be the bearer token. Templates introduce **client-side env var names** (`MARE_TOKEN`, `MARE_URL`) for the mastra starter's `.env.example` — these are NEW user-facing names. Claude Code `.mcp.json` template uses `MARE_GATEWAY_TOKEN` and `MARE_GATEWAY_URL`. | Document the env var names in template READMEs. Confirm name choices in plan (`MARE_TOKEN` vs `MARE_GATEWAY_TOKEN` — currently inconsistent across two templates; pick ONE in the plan). |
| **Build artifacts / installed packages** | `templates/mastra/node_modules/` (gitignored, generated by `npm install` at e2e test time AND by users). No installed-package staleness — the mastra starter is a fresh project. | Add `templates/mastra/node_modules/` and `templates/mastra/dist/` to `.gitignore`. Existing `.gitignore` should already cover this if `node_modules/` is global; verify in plan. |

**Inconsistency to resolve in planning:** `MARE_TOKEN` (mastra starter convention from Pattern 3 above) vs `MARE_GATEWAY_TOKEN` (Claude Code template convention from Pattern 2). Recommend **`MARE_GATEWAY_TOKEN` and `MARE_GATEWAY_URL`** uniformly across both templates (clearer intent, avoids name collision with hypothetical other "mare" env vars). Plan must lock one choice.

## Common Pitfalls

### Pitfall 1: FastMCP `list_resources` returns the static cache
**What goes wrong:** New cases created after gateway startup don't appear in `resources/list` results.
**Why it happens:** `FastMCP.list_resources()` returns whatever is in `_resource_manager._resources` (a dict populated at registration time).
**How to avoid:** Override the underlying low-level handler — `@mcp._mcp_server.list_resources()` decorator. This handler runs per-request and can re-enumerate the filesystem.
**Warning signs:** Tests pass on a fresh case but fail when a second case is added without restart.

### Pitfall 2: Resource templates do NOT show up in `resources/list`
**What goes wrong:** A `@mcp.resource("mare://cases/{case}/{artifact}")` decorator alone makes the URI shape discoverable via `resources/templates/list`, but `resources/list` returns empty.
**Why it happens:** MCP spec separates concrete resources (`resources/list`) from templates (`resources/templates/list`). Most clients (Claude Code, mastra) call `resources/list` only.
**How to avoid:** Register BOTH — a template (for URI structure discovery) AND a concrete-list handler (for current-state enumeration).
**Warning signs:** Manual `httpx` test sees the resources, but Claude Code's `/mcp` panel shows nothing.

### Pitfall 3: `.log` files get `application/octet-stream` from stdlib `mimetypes`
**What goes wrong:** `mimetypes.guess_type("foo.log")` returns `(None, None)` on stock Python 3.12 Linux.
**Why it happens:** `.log` isn't registered by default; some distros add it via `/etc/mime.types`, but not all.
**How to avoid:** Use the hand-rolled map in Pattern 1. **Don't trust `mimetypes` for `.log`.**
**Warning signs:** Test asserts `mimeType == "text/plain"` for `01_strings_raw.txt` works but fails for any `.log` artifact.

### Pitfall 4: `Authorization` header dropped on redirect
**What goes wrong:** `httpx` (and curl) strip `Authorization` headers when following cross-origin redirects.
**Why it happens:** Security default — prevents credential leakage to a redirect target.
**How to avoid:** Hit `/mcp` (no trailing slash); the gateway handles both. The existing bash smoke uses `/mcp/` directly to avoid the redirect — pytest tests should follow the same convention OR pin `follow_redirects=True` only when the redirect target is the same origin (default httpx behavior keeps Authorization on same-origin redirects, only drops on cross-origin).
**Warning signs:** A test gets 401 even though it sets the bearer header correctly. Look at `httpx` history for a 307 redirect.

### Pitfall 5: Mastra `@mastra/mcp@1.3.x` peer-dep mismatch with `@mastra/core@1.28`
**What goes wrong:** `npm install` warns about peer-dep mismatch because `@mastra/mcp@1.3.1` was published 2026-03-20 against `@mastra/core@1.x` and `@mastra/core@1.28.0` is the latest stable.
**Why it happens:** mastra ships fast; older packages list peer deps with broad ranges (`@mastra/core: >=1.0.0-0 <2.0.0-0` per registry data) but newer cores can introduce subtle breakages.
**How to avoid:** Test the install locally before locking versions. If `@mastra/core@1.28.0` breaks `@mastra/mcp@1.3.x`, downgrade core to `^1.20` or upgrade mcp (which violates D-08 — escalate to user).
**Warning signs:** `npm install` succeeds but `npm start` fails with `Cannot find module` or runtime API errors. **Action:** Plan should include a one-shot manual install verification before publishing the template.

### Pitfall 6: `subprocess.run("npm install")` finds different Node versions across machines
**What goes wrong:** Test passes on dev's Node 20 but fails in CI on Node 18.
**Why it happens:** mastra requires Node 18+; some features need Node 20.
**How to avoid:** Pin `engines.node = ">=20"` in `templates/mastra/package.json`. The pytest test should `subprocess.run(["node", "--version"])` and skip if too old.
**Warning signs:** Mysterious `npm install` errors mentioning ESM / `import.meta` / `crypto.subtle`.

### Pitfall 7: `templates/mastra/node_modules/` accidentally committed
**What goes wrong:** First contributor runs the e2e test, generates `node_modules/`, commits the change.
**Why it happens:** Top-level `.gitignore` may not cover `templates/mastra/node_modules/`.
**How to avoid:** Add `templates/**/node_modules/` and `templates/**/dist/` to root `.gitignore` as part of Phase 4. Also add `templates/mastra/.gitignore` for belt-and-suspenders.
**Warning signs:** PR diff shows thousands of `node_modules/` files.

### Pitfall 8: Two different env var names across templates (MARE_TOKEN vs MARE_GATEWAY_TOKEN)
**What goes wrong:** User reads the Claude Code template (uses `MARE_GATEWAY_TOKEN`), then the mastra starter (uses `MARE_TOKEN`), gets confused.
**Why it happens:** Researcher (this doc) used different conventions in two patterns above.
**How to avoid:** Lock ONE name in plan. Recommendation: **`MARE_GATEWAY_TOKEN`** and **`MARE_GATEWAY_URL`** uniformly. The README rewrite (D-16) should set the convention once, in a "Configure your client" section, and both templates inherit it.
**Warning signs:** Two README sections disagree on what env var to set.

### Pitfall 9: `--print-config` runs before container is up and finds a stale token
**What goes wrong:** User runs `./run_docker.sh --remote` (background container starts), then `./run_docker.sh --remote` AGAIN (a second invocation), then `--print-config`. The token may have been re-generated, but `--print-config` reads the file and prints what's there — which is fine. But if the user manually rotates the token without restarting, `--print-config` is now lying.
**Why it happens:** `--print-config` reads the file at invocation time; it doesn't probe the running gateway.
**How to avoid:** Document the failure mode in the print-block message ("Token reflects the most recent gateway start"). For Phase 4, accept this as a known limitation; a stronger version (probe gateway, ask for token via API) is out of scope.
**Warning signs:** User pastes a token from `--print-config` into Claude Code, gets 401, restart fixes it.

## Code Examples

### Resource list JSON-RPC envelope (wire format)
```json
// Request
{ "jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {} }

// Response shape (per MCP 2025-03-26 spec)
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "resources": [
      {
        "uri": "mare://cases/000-mfc42ul.dll/00_sample_profile.md",
        "name": "000-mfc42ul.dll/00_sample_profile.md",
        "description": "Pipeline artifact for case 000-mfc42ul.dll",
        "mimeType": "text/markdown"
      }
    ]
  }
}
```

### Resource read JSON-RPC envelope
```json
// Request
{
  "jsonrpc": "2.0", "id": 5, "method": "resources/read",
  "params": { "uri": "mare://cases/000-mfc42ul.dll/CURRENT_STATE.json" }
}

// Response shape
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "contents": [{
      "uri": "mare://cases/000-mfc42ul.dll/CURRENT_STATE.json",
      "mimeType": "application/json",
      "text": "{\"sample_path\": ...}"
    }]
  }
}
```

### Mastra starter `package.json` (D-06, D-08)
```json
{
  "name": "mare-mastra-starter",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "engines": { "node": ">=20" },
  "scripts": {
    "start": "tsx src/index.ts",
    "build": "tsc"
  },
  "dependencies": {
    "@mastra/core": "^1.28.0",
    "@mastra/mcp": "~1.3.1",
    "dotenv": "^16.4.5",
    "zod": "^3.25.0"
  },
  "devDependencies": {
    "@types/node": "^20.11.0",
    "tsx": "^4.7.0",
    "typescript": "^5.4.0"
  }
}
```

### Mastra starter `tsconfig.json`
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "esModuleInterop": true,
    "strict": true,
    "skipLibCheck": true,
    "outDir": "dist"
  },
  "include": ["src/**/*"]
}
```

### `.env.example` (D-06)
```env
# Bearer token from `./run_docker.sh --remote` ready-block (or `cat workspace/.mcp-gateway-token`)
MARE_GATEWAY_TOKEN=

# Container gateway endpoint
MARE_GATEWAY_URL=http://localhost:8080/mcp
```

### Claude Code `.mcp.json` template (D-10)
```json
{
  "mcpServers": {
    "mare-toolbox": {
      "type": "http",
      "url": "${MARE_GATEWAY_URL:-http://localhost:8080/mcp}",
      "headers": {
        "Authorization": "Bearer ${MARE_GATEWAY_TOKEN}"
      }
    }
  }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `MastraMCPClient` (legacy class) | `MCPClient` from `@mastra/mcp` | 2025 (mastra deprecation cycle) | Don't use the legacy name (CLAUDE.md "Do NOT Use"). |
| `mcp-remote` npm bridge | Native `type: "http"` in Claude Code `.mcp.json` | June 2025 (after CVE-2025-6514) | Bridge no longer needed; native HTTP transport is built into Claude Code. |
| SSE transport | Streamable HTTP (2025-03-26 spec) | June 2025 | URLs end in `/mcp` not `/sse`. Both Claude Code and mastra try Streamable HTTP first, fall back to SSE only if needed. |
| MCP `resources/subscribe` for live updates | (deferred to Phase v2) | n/a | CONTEXT defers; Phase 4 is read-only point-in-time. |
| `claude mcp add --transport http ... --header ...` (CLI) | `.mcp.json` checked in to repo (project scope) | early 2025 (project scope GA) | Project-scoped `.mcp.json` is now the canonical team-share pattern; `claude mcp add` is dev-machine convenience. Phase 4 ships the project-scope file. |

**Deprecated/outdated:**
- **`mcp-remote` (npm)**: CVE-2025-6514 — do not reference in any template. `[CITED: stackoverflow.blog/2026/01/21/...]`
- **`MastraMCPClient`**: replaced by `MCPClient`. `[CITED: CLAUDE.md "Do NOT Use" list]`
- **MCP SSE-only transport**: deprecated June 2025 per MCP spec. `[CITED: modelcontextprotocol.io/specification/2025-03-26/...]`

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `tsx` and `typescript` are the right TS toolchain for mastra 1.3.x starter | Standard Stack / Supporting | Low — these are mainstream Node TS tools. If mastra docs prescribe a different runner (e.g., `node --import=tsx`), adjust the `npm start` script. |
| A2 | `dotenv` for env loading in the starter | Standard Stack / Supporting | Low — universal Node pattern. |
| A3 | Node 20 minimum is correct for `@mastra/core@1.28` | Standard Stack / `engines.node` | Low — all recent mastra docs target Node 20. Plan should run `node --version` check during e2e test setup. |
| A4 | `MCPClient.getTools()` (vs `listTools()`) is the canonical 1.3.x integration entry | Pattern 3 | Medium — if `getTools()` was added later than 1.3.0, the starter could fail on 1.3.0 specifically. Mitigation: pin `~1.3.1` (skip 1.3.0). |
| A5 | The mastra `MCPClient` correctly auto-detects Streamable HTTP vs SSE based on URL | Pattern 3 | Low — confirmed via WebSearch + mastra docs. |
| A6 | `templates/mastra/node_modules/` should be gitignored (not committed) | Runtime State Inventory | None — universal Node convention. |
| A7 | Claude Code's `${VAR}` env-var expansion is preserved through `claude mcp add`/edit operations on the file | Pattern 2 | Medium — there's a known bug (Issue #18692) where `claude mcp add` resolves env vars to literals on rewrite. Mitigation: document in template README that users should NOT use `claude mcp add` to modify the checked-in template. |
| A8 | `@mastra/core@1.28.0` is peer-compatible with `@mastra/mcp@1.3.1` | Common Pitfalls / Pitfall 5 | Medium — npm registry confirms peer range allows it (`>=1.0.0-0 <2.0.0-0`), but breaking changes in core minors are possible. Mitigation: smoke-install during plan execution; downgrade core to `^1.20` if issues surface. |
| A9 | Recommendation to use `MARE_GATEWAY_TOKEN` / `MARE_GATEWAY_URL` env var names uniformly | Runtime State Inventory + Pitfall 8 | Low — naming convention only; no functional impact. Plan locks the choice. |
| A10 | The 13 artifacts list is the complete D-03 set per `artifact-spec.md` | Pattern 1 / `ARTIFACTS` constant | LOW — verified directly from `workspace/.claude/skills/.../artifact-spec.md`. |
| A11 | `mcp._mcp_server.list_resources()` decorator is stable across mcp 1.27.x | Pattern 1 | LOW — verified in venv. The pyproject.toml pin `<1.28` insulates against future SDK changes. |

**Confirmed (no longer assumed):** `mare://` custom URI scheme accepted by FastMCP (verified in venv); `httpx` already a dependency (verified in `pyproject.toml`); 13-artifact list (verified in `artifact-spec.md`); FastMCP `_mcp_server` low-level handler API (verified in venv via `inspect.getsource`).

## Open Questions (RESOLVED)

1. **Single sample fixture for the mastra starter test**
   - What we know: `workspace/examples/samples/mfc42ul.dll` exists.
   - What's unclear: Does the starter's `npm start` need to mount/copy this sample into the container, or can it reference it via URL/sha after upload?
   - RESOLVED: Starter accepts a CLI arg with a host-side path, reads bytes locally, POSTs to `/upload`, gets sha256 back. The test passes `workspace/examples/samples/mfc42ul.dll` as that arg. Plan should confirm.

2. **README structure for two-mode framing (D-16)**
   - What we know: D-16 requires a full rewrite covering local + remote modes, both client configs, resource browsing.
   - What's unclear: Order of sections — "what is this" first, or "install" first?
   - RESOLVED: Outline below; planner adapts. Section beats: (a) one-line value prop, (b) "Two ways to use this" mode comparison table, (c) Quick start: local mode, (d) Quick start: remote mode (with `--remote` ready-block screenshot/quote), (e) Connect Claude Code (link to `templates/claude-code/.mcp.json`), (f) Connect mastra.ai (link to `templates/mastra/`), (g) Browse case artifacts (mention MCP Resources + sample URIs), (h) Troubleshooting (`--print-config`, token rotation, port conflicts).

3. **Resource truncation policy**
   - What we know: CONTEXT D-04 says "default to read whole file unless this proves problematic."
   - What's unclear: What's "problematic"? `01_strings_raw.txt` for a large binary could be 10+ MB.
   - RESOLVED: No truncation in Phase 4. If a real artifact exceeds 50 MB, the user will hit it and we revisit. Document the no-cap policy in `tools/resources.py` docstring.

4. **Mastra `@mastra/core` peer compat (A8 follow-through)**
   - What we know: `@mastra/mcp@1.3.x` peer range allows `@mastra/core` up to `<2.0.0-0`.
   - What's unclear: Does `1.28.0` actually work with `1.3.1`?
   - RESOLVED: Plan must include a manual `npm install && npm run build` smoke during execution. If it fails, downgrade core to `^1.20` (closest to 1.3.x's release window). User confirmation required only if the downgrade breaks API surface used in `src/index.ts`.

5. **Should `mcp-gateway/README.md` be updated alongside the top-level rewrite?**
   - What we know: D-16 says "may receive a small client-integration update."
   - What's unclear: Is "small update" worth the planning bandwidth, or skip?
   - RESOLVED: Add a single new section ("Client integration: see top-level README") with a link. Five-line addition, low cost, prevents the gateway README from being a dead end.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | Gateway, e2e tests, resources module | ✓ | 3.12 (host); 3.12+ in container | — |
| `mcp` Python SDK 1.27.x | Resources registration | ✓ | 1.27.0 (verified via venv install) | — |
| `httpx` | E2e tests | ✓ | already a gateway dep | — |
| `pytest` + `pytest-asyncio` | E2e tests | ✓ | already in dev deps | — |
| Node.js 20+ | Mastra starter test (D-13) | Likely ✓ on dev machines | (host-dependent) | Skip test with `pytest.skip("npm not on PATH")` if absent — D-13 is verification, not blocking |
| `npm` | Mastra starter test | Likely ✓ if Node installed | bundled with Node | Same as above |
| `@mastra/mcp@~1.3.1` | Mastra starter | ✗ (resolved at `npm install`) | network-fetched | none — npm registry must be reachable |
| `@mastra/core@^1.28` | Mastra starter | ✗ (resolved at `npm install`) | network-fetched | downgrade to `^1.20` if peer-dep break (see A8) |
| Running gateway on `127.0.0.1:8080` | E2e tests | depends on whether `--remote` is up | n/a | `pytest.skip()` if no token file or connection refused |
| `workspace/.mcp-gateway-token` | E2e tests + `--print-config` | depends on whether `--remote` was run | n/a | `--print-config` exits non-zero with hint; tests skip |

**Missing dependencies with no fallback:**
- None — every component degrades gracefully to a skip or a clear error message.

**Missing dependencies with fallback:**
- `npm` / Node — pytest test skips cleanly. Documented in pytest test file via `@pytest.mark.skipif(shutil.which("npm") is None, ...)`.
- Running gateway — pytest fixture skips cleanly. Documented in `conftest.py:bearer_token` fixture via `pytest.skip(...)`.

## Validation Architecture

> `.planning/config.json` was not consulted (file may not exist). Treating `nyquist_validation` as enabled per default.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest>=8` + `pytest-asyncio>=0.23` |
| Config file | `mcp-gateway/pyproject.toml` (`[tool.pytest.ini_options]`) — `asyncio_mode = "auto"`, `addopts = "-ra"` |
| Quick run command | `cd mcp-gateway && pytest tests/ -x` (unit tests, fast) |
| Full suite command | `cd mcp-gateway && pytest tests/ -ra` (includes `tests/e2e/` if container is up) |
| E2e-only command | `cd mcp-gateway && pytest tests/e2e/ -ra` |
| Manual smoke (legacy) | `bash mcp-gateway/tests/e2e/smoke.sh` (still works, retained alongside Python tests) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| **CLI-01** | Claude Code can `initialize` → `tools/list` → `tools/call` against `/mcp` with bearer | e2e (raw httpx) | `pytest tests/e2e/test_claude_code_smoke.py -x` | ❌ Wave 0 |
| **CLI-01** | Manual UAT — real Claude Code session against container | manual | (documented checklist in plan) | ❌ Wave 0 (checklist file) |
| **CLI-02** | Mastra `MCPClient` connects via Streamable HTTP, lists tools, calls `run_triage` | e2e (subprocess npm) | `pytest tests/e2e/test_mastra_starter.py -x` | ❌ Wave 0 |
| **CLI-03 (CC)** | Template `.mcp.json` parses + matches the `run_docker.sh` ready-block shape | unit (json+text compare) | `pytest tests/test_templates.py::test_claude_code_mcp_json_valid -x` | ❌ Wave 0 |
| **CLI-03 (mastra)** | Template `package.json` lints + has `~1.3.1` pin per D-08 | unit (jq/python json) | `pytest tests/test_templates.py::test_mastra_pinning -x` | ❌ Wave 0 |
| **CLI-04** | `resources/list` returns `mare://cases/...` URIs, MIME types per D-04, content non-empty | e2e (raw httpx) | `pytest tests/e2e/test_resources.py -x` | ❌ Wave 0 |
| **CLI-04** | Internal: `tools/resources.py` enumerates 13 artifacts × N cases, validates URIs | unit (in-memory FastMCP) | `pytest tests/test_resources_unit.py -x` | ❌ Wave 0 |
| **D-11** | `./run_docker.sh --print-config` exits 0 with token, exits non-zero without | shell test | `bash mcp-gateway/tests/e2e/test_print_config.sh` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x --ignore=tests/e2e/` (unit tests only, < 5s, no container needed)
- **Per wave merge:** Full suite WITHOUT e2e if no `--remote` running; `pytest tests/e2e/ -ra` if `--remote` is running
- **Phase gate:** Full suite green AND manual UAT checklist completed before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `mcp-gateway/tests/test_resources_unit.py` — unit-level coverage of `tools/resources.py` (URI scheme, MIME map, allowlist, dynamic listing) using in-memory FastMCP
- [ ] `mcp-gateway/tests/test_templates.py` — validates `templates/claude-code/.mcp.json` JSON parses + `templates/mastra/package.json` pins `~1.3.1`
- [ ] `mcp-gateway/tests/e2e/__init__.py` — empty file marking the dir a package
- [ ] `mcp-gateway/tests/e2e/conftest.py` — gateway URL + token fixtures (env-driven, skip if absent)
- [ ] `mcp-gateway/tests/e2e/test_claude_code_smoke.py` — CLI-01 raw httpx flow
- [ ] `mcp-gateway/tests/e2e/test_resources.py` — CLI-04 resources flow
- [ ] `mcp-gateway/tests/e2e/test_mastra_starter.py` — CLI-02 subprocess npm test
- [ ] `mcp-gateway/tests/e2e/test_print_config.sh` — D-11 CLI behavior (or fold into a Python test)
- [ ] Manual UAT checklist file (place in plan or `docs/` — not gateway code) — D-12 manual signoff

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (inherited) | Bearer token from Phase 2; Phase 4 must NOT introduce a second auth surface |
| V3 Session Management | partial | Gateway is `stateless_http=True`; no session lifecycle to protect |
| V4 Access Control | yes | Bearer token gates all `/mcp` and `/upload` requests; Resources are exposed under same auth (Phase 2 BearerAuthMiddleware applies to entire `/mcp` mount) |
| V5 Input Validation | yes | URI parameters (`case`, `artifact`) validated against allowlists (CASE_NAME_RE + ARTIFACTS tuple); resolved-path containment check under STATUS_ROOT |
| V6 Cryptography | no (inherited) | TLS termination is user/ops concern (LAN-only by default) |
| V12 Files & Resources | yes | Path traversal prevention on `mare://cases/{case}/{artifact}` reads — same pattern as Phase 2 `_resolve_allowed` |

### Known Threat Patterns for {gateway + Resources}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via `case` or `artifact` URI param | Tampering / Information Disclosure | CASE_NAME_RE allowlist (`^\d{3}-.+`) + ARTIFACTS tuple allowlist + `path.resolve()` containment under `STATUS_ROOT` (Pattern 1 code) |
| Token leak in `templates/claude-code/.mcp.json` | Information Disclosure | Use `${MARE_GATEWAY_TOKEN}` expansion (never hardcoded). README warns against committing local-resolved values. |
| Token leak in `templates/mastra/.env` | Information Disclosure | `.env.example` (no real value); `.env` is gitignored by mastra default + add to `.gitignore` |
| Cross-origin redirect strips `Authorization` (test false-401) | Spoofing-adjacent | Tests hit `/mcp` directly (no trailing slash); `httpx` defaults to dropping Authorization on cross-origin redirect |
| `npm install` from untrusted registry | Tampering / Supply chain | Pin exact versions (`~1.3.1`, not `^1.3.0`); future improvement: lockfile committed (`package-lock.json`) — currently out of scope per CONTEXT but worth noting |
| Reading large binary as text in `resources/read` | DoS / OOM | Phase 4 default: read whole file. If artifact > 50 MB, revisit. ARTIFACTS list is bounded to 13 small files; tool-logs/disassembly subdirs are NOT in the resource list. |
| Resource exposure of stale data (case from previous user, no auth scoping) | Information Disclosure | Single-user / trusted-team deployment model (Phase 2 D-18). Bearer token = full surface. Acceptable for v1. |

## Sources

### Primary (HIGH confidence)
- `mcp-gateway/src/mcp_gateway/app.py` — Gateway architecture, FastMCP construction parameters
- `mcp-gateway/src/mcp_gateway/tools/cases.py` — `CASE_NAME_RE`, `list_cases()` enumeration pattern
- `mcp-gateway/src/mcp_gateway/tools/samples.py` — `STATUS_ROOT`, `UPLOADS_ROOT`, `_resolve_allowed`
- `mcp-gateway/tests/e2e/smoke.sh` — Existing JSON-RPC envelope shapes for `initialize` / `tools/list` / `tools/call`
- `mcp-gateway/tests/e2e/test_upload_then_analyze.sh` — Upload + tool call pattern
- `mcp-gateway/tests/test_tool_list.py` — Public-API-stable test pattern using `create_connected_server_and_client_session`
- `mcp-gateway/pyproject.toml` — Pinned versions, pytest config
- `run_docker.sh` (lines 297-345) — Ready-block heredoc structure to extract for `--print-config`
- `workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md` — Authoritative 13-artifact list
- `.planning/phases/04-external-client-integration/04-CONTEXT.md` — All locked decisions (D-01..D-16)
- `.planning/phases/02-mcp-gateway/02-CONTEXT.md` — Pass-through model (D-07), single-session active-case (D-04), upload mechanism (D-11..D-15), bearer-only auth (D-12, D-18)
- `.planning/phases/03-container-integration/03-CONTEXT.md` — `--remote` flow, token discovery, ready-block format
- Local venv smoke test (mcp 1.27.x) — Verified `mare://` custom URI scheme, FastMCP template + low-level handler patterns, MIME stdlib behavior
- npm registry HTTP query (2026-04-27) — `@mastra/mcp@1.3.2` (latest 1.3.x), `@mastra/core@1.28.0`, peer deps

### Secondary (MEDIUM confidence)
- [Claude Code MCP docs](https://code.claude.com/docs/en/mcp) — `.mcp.json` `type:"http"` schema, `${VAR}` expansion, project-scope file (verified via WebFetch)
- [Mastra MCPClient docs](https://mastra.ai/reference/tools/mcp-client) — Constructor signature with `requestInit.headers` (verified via WebFetch)
- [MCP Transports spec (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — Streamable HTTP wire format
- [MCP Resources spec (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/server/resources) — `resources/list`, `resources/read`, content shape (`text` vs `blob`)

### Tertiary (LOW confidence — flag for validation)
- A4 (`MCPClient.getTools()` vs `listTools()` canonical entry) — observed across multiple WebSearch results; both exist but `getTools()` is integration-ready. **Validate by running the starter once.**
- A8 (`@mastra/core@1.28.0` × `@mastra/mcp@1.3.1` compatibility) — peer-range claims compatible, but no direct test executed. **Validate by `npm install` smoke during plan execution.**
- A7 (`claude mcp add` env-var literal-rewrite bug) — referenced GitHub issue #18692; bug may be patched. **Document anyway in template README; users should hand-edit.**

## Metadata

**Confidence breakdown:**
- Resources implementation (Pattern 1): HIGH — verified in venv with mcp 1.27.x; URI scheme + dynamic listing both work
- Claude Code template (Pattern 2): HIGH — schema verified against official docs + existing `run_docker.sh` heredoc
- Mastra starter (Pattern 3): MEDIUM — `MCPClient` constructor verified, but exact API shape (`getTools()` vs `listTools()`) needs one smoke run; `core@1.28 × mcp@1.3.1` compat unverified
- httpx e2e harness (Pattern 4): HIGH — mirrors existing bash smoke; wire format verified via mcp-types inspection
- Mastra subprocess test (Pattern 5): MEDIUM — pattern is straightforward, but Node version availability + npm install behavior is host-dependent
- `--print-config` extraction (Pattern 6): HIGH — pure refactor of existing heredoc; trivial
- Common pitfalls: HIGH — derived from venv smoke + spec reading + lessons from Phase 2 e2e
- Security: HIGH — inherits Phase 2 controls; no new auth/state surface

**Research date:** 2026-04-27
**Valid until:** 2026-05-27 (30 days — mastra ships fast minors; recheck `@mastra/mcp` 1.3.x compatibility before locking package.json if more than ~6 weeks elapse)
