# Phase 2: MCP Gateway - Research

**Researched:** 2026-04-23
**Domain:** MCP server development (Python FastMCP, Streamable HTTP, multi-backend aggregation, bearer auth, multipart upload)
**Confidence:** HIGH (all core decisions cross-verified against MCP spec 2025-03-26, mcp SDK 1.27, Starlette docs, and existing repo code)

## Summary

Phase 2 builds a **custom FastMCP gateway** (Python, using `mcp.server.fastmcp.FastMCP` from the official SDK `mcp>=1.27.0`) that:

1. Exposes a Streamable HTTP MCP endpoint at `/mcp` on 127.0.0.1:8080 with bearer-token auth.
2. Aggregates a curated 18-22 tool surface — composite workflow tools (`run_triage`, `run_deep_analysis`, `generate_report`), 13 atomic orchestrator tools (one per case-directory artifact), 3-6 unified disassembler tools (`decompile`, `list_functions`, `get_xrefs`), and case-management tools (`list_cases`, `set_active_case`, `get_artifact`).
3. Acts as an **MCP client** to the installed disassembler backend — Streamable HTTP client against `http://127.0.0.1:8745/mcp` for IDA, stdio subprocess client for BN/Ghidra — and forwards tool calls under unified verb-first names (D-06, D-07).
4. Serves a separate `POST /upload` endpoint on the same port (mounted via Starlette) protected by the same bearer token (D-11, D-12).
5. Reuses the existing orchestrator skill's shell scripts at `workspace/.claude/skills/malware-analysis-orchestrator/scripts/` as the implementation of the atomic pipeline tools (D-08), shelling out via `asyncio.create_subprocess_exec`.

**Primary recommendation:** Build a new `mcp-gateway/` Python package at the repo root. Use the official `mcp` SDK's FastMCP, mount it on a Starlette ASGI app alongside `/upload` and `/healthz` routes, add a `BaseHTTPMiddleware` for bearer-token auth, manage the backend `ClientSession` via `AsyncExitStack` inside a Starlette `lifespan`, and run under uvicorn as a daemon started from `agent-entrypoint.sh` alongside the existing idalib-mcp daemon. Resolve the critical CLAUDE.md vs CONTEXT.md divergence in favor of CONTEXT.md (custom FastMCP, not mcp-proxy) and add a CLAUDE.md update task to the plan.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Tool surface strategy**
- **D-01:** Layered tool surface — ships BOTH composite workflow tools (e.g. `run_triage`, `run_deep_analysis`, `generate_report`) AND atomic pipeline tools. Clients choose granularity.
- **D-02:** Atomic tier = one tool per 13-artifact file. ~13 atomic tools + a handful of workflow/case tools + disassembler-routed tools ≈ 18-22 total (fits GW-02's 15-25 target).
- **D-03:** Tool naming uses **verb-first** style — `run_triage`, `decompile`, `collect_strings`, `scan_yara`, `list_functions`, `fetch_strings`, `get_xrefs`, `rank_signals`, `build_hypothesis`, `list_cases`, `get_artifact`, `set_active_case`. Avoid dotted namespaces; avoid underscored-by-domain (e.g. `case_list_artifacts`).
- **D-04:** Case/session state is exposed as tools: `list_cases`, `get_artifact(case_id, artifact_name)`, `set_active_case`, and related helpers. The gateway tracks the active case per MCP session. In Phase 4 these artifacts are additionally promoted to MCP Resources (CLI-04).
- **D-05:** No raw CLI passthrough (already ruled out in REQUIREMENTS.md Out of Scope). Every tool is a curated wrapper with a documented JSON schema.

**Gateway ↔ backend architecture**
- **D-06:** Gateway acts as an **MCP client** to each disassembler backend's existing MCP server — it does NOT re-implement disassembler logic.
  - IDA: `http://127.0.0.1:8745/mcp` (idalib-mcp, already running from Phase 1).
  - BN: spawn `python3 /agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py` as a persistent stdio subprocess at gateway start.
  - Ghidra: spawn `python3 /agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py` as a persistent stdio subprocess at gateway start.
- **D-07:** Gateway aggregates the backend's tools and re-exposes them under the unified verb-first names (D-03). Client never sees backend-specific tool names. Backend-specific tools that don't have a unified equivalent are hidden (not exposed) in Phase 2 — only the GW-02 curated set is visible.
- **D-08:** Non-disassembler pipeline tools (`collect_strings`, `collect_imports`, `scan_yara`, `scan_capa`, `rank_signals`, `build_hypothesis`, etc.) **reuse the existing orchestrator skill's scripts** at `workspace/.claude/skills/malware-analysis-orchestrator/scripts/*`.
- **D-09:** Gateway is started by `agent-entrypoint.sh` at container boot as a long-lived service alongside idalib-mcp. Backend detection reuses the logic from `docker-bin/configure-agent-mcp.sh`. Detected backend is **pinned for the gateway's lifetime**.
- **D-10:** Gateway crashes/failures in the backend MCP subprocess fail loudly (structured MCP error); does NOT silently fall back.

**File upload mechanism**
- **D-11:** Uploads use a **separate HTTP POST endpoint** on the same port as the MCP server. `POST /upload`. Returns `{ "sample_id": "<sha256>", "path": "/agent/uploads/<sha256>/<name>", "size": <bytes> }`.
- **D-12:** Upload endpoint protected by the **same bearer token** as the MCP endpoint.
- **D-13:** Samples stored at `/agent/uploads/<sha256>/<original_name>` (content-hashed dir).
- **D-14:** Default upload size cap: **1 GB**. Configurable via `MCP_GATEWAY_MAX_UPLOAD_MB`. Exceeding → 413 for /upload, MCP error for tool paths.
- **D-15:** All sample-accepting tools resolve the `sample` parameter in two ways: (a) sha256 / `sample_id` from a previous upload, or (b) container-local path. Single interface for remote clients and inner-container agents.

**Auth token lifecycle**
- **D-16:** Env var wins, else auto-generate. `MCP_GATEWAY_TOKEN` if set, otherwise cryptographically-random token at startup.
- **D-17:** Exposed via BOTH: (a) `/agent/.mcp-gateway-token` (chmod 0600, owned by `agent`), AND (b) one-line log `[gateway] Bearer token: <token>`. Log line suppressed with `MCP_GATEWAY_QUIET=1`. File path is always written.
- **D-18:** Single token for the whole gateway — no per-tool scopes, no multi-user claims. OAuth 2.1 explicitly out of scope.
- **D-19:** Network binding: `127.0.0.1` by default. Set `MCP_GATEWAY_HOST=0.0.0.0` to expose on all interfaces.
- **D-20:** Port `8080` by default. Configurable via `MCP_GATEWAY_PORT`.

### Claude's Discretion

- Concurrency / session-isolation model for multiple simultaneous remote clients (v2 work — Phase 2 can assume single-session or simple serialization).
- Error serialization format — follow MCP 2025-03-26 spec defaults.
- Logging level/format — something that plays nicely with `docker compose logs`.
- FastMCP composition details (tool handler registration, middleware order, auth placement).
- Backend subprocess restart policy (crash: restart N times then fail, or fail-fast).
- Inter-process transport detail between gateway and BN/Ghidra stdio MCP servers (raw stdio vs an in-process `ClientSession`).
- Exact schema/argument names for each of the ~20 tools.

### Deferred Ideas (OUT OF SCOPE)

- MCP Resources for case artifacts (sample profile, strings, hypotheses, reports) → **Phase 4** (CLI-04).
- MCP Prompts exposing orchestrator workflows as prompt templates → **v2** (GW-V2-01).
- Dynamic notifications for analysis progress → **v2** (GW-V2-02).
- Multi-session / concurrent remote clients with independent analyses → **v2** (GW-V2-03).
- Session lifecycle management, idle timeouts, case cleanup → **v2** (GW-V2-04).
- Unified disassembler abstraction layer (normalize tool args across BN/IDA/Ghidra beyond just names) → **v2** (DIS-V2-01).
- Backend comparison mode → **v2** (DIS-V2-02).
- Claude Code / mastra.ai client config templates → **Phase 4** (CLI-01, CLI-02, CLI-03).
- Host-side port publishing in `compose.yaml` → **Phase 3** (INF-02).
- Dual-mode entrypoint tuning → **Phase 3** (INF-01, INF-05).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **GW-01** | Python FastMCP server exposes curated tool surface over Streamable HTTP transport (spec 2025-03-26) | Standard Stack → `mcp>=1.27.0` with `FastMCP(..., stateless_http=True, json_response=True).streamable_http_app()`; Architecture Pattern 1; Code Example §§1-2. Streamable HTTP endpoint at `/mcp` is the MCP spec 2025-03-26 standard [CITED: modelcontextprotocol.io/specification/2025-03-26/basic/transports]. |
| **GW-02** | Gateway exposes ~15-25 orchestrator-level tools mapping to the existing 13-artifact pipeline | Tool Inventory (§ Tool Surface Design) lists 21 concrete tool names mapped to orchestrator scripts and backend MCP calls. |
| **GW-03** | Disassembler tools route to whichever backend is installed (BN > IDA > Ghidra), presenting a unified interface | Architecture Pattern 2 (Backend-as-Client) + Tool Inventory § Disassembler tools. Matches Phase 1 D-06 "no silent fallback" policy. Note: CONTEXT.md D-09 says priority is IDA > BN > Ghidra; existing `configure-agent-mcp.sh` also uses IDA > BN > Ghidra; REQUIREMENTS.md GW-03 text says "BN > IDA > Ghidra" — **treat REQUIREMENTS.md text as stale, actual priority is IDA > BN > Ghidra** (explicitly stated in Phase 1 D-06 and CONTEXT.md D-09). |
| **GW-04** | Bearer token authentication required on all remote MCP endpoints | Architecture Pattern 3 (BearerAuthMiddleware); Code Example §3; Don't-Hand-Roll § "token generation"; CLAUDE.md flags mcp-remote CVE-2025-6514 (we do not use mcp-remote). |
| **GW-05** | Gateway binds to localhost only by default; explicit opt-in for network exposure | Default `MCP_GATEWAY_HOST=127.0.0.1`; MCP spec mandates this [CITED: MCP 2025-03-26 Transports § Security Warning]. Code Example §5. |
| **GW-06** | File upload mechanism allows remote clients to submit samples to the container for analysis | Architecture Pattern 4 (Mount custom Starlette `/upload` route alongside FastMCP). Code Example §4 with streaming body to disk. Common Pitfall: memory-blow-up; use `request.stream()`, not `await request.body()`. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

> CRITICAL: CLAUDE.md's "Recommended Stack" table recommends **mcp-proxy (sparfenyuk)** for stdio-to-HTTP bridging. CONTEXT.md explicitly **chose a custom FastMCP gateway instead** (D-01 through D-20 lock this in). The user's locked decisions in CONTEXT.md take precedence. The plan MUST include a documentation task to update CLAUDE.md's "Recommended Stack" table to reflect the custom FastMCP choice (move mcp-proxy row to "Alternatives Considered" with the rationale that aggregation + auth + /upload + unified tool surface in a single process can't be done by mcp-proxy alone).

Directives that remain binding:

- **Transport:** Streamable HTTP (Protocol 2025-03-26) is the active transport. Do NOT use SSE legacy; do NOT use mcp-remote (CVE-2025-6514).
- **Auth:** Bearer token only; OAuth 2.1 is explicitly out of scope.
- **Python:** 3.11+ (Kali rolling has 3.12 — see Environment Availability).
- **License constraints:** No license artifacts in image (not applicable to gateway itself, it has no licensed deps).
- **Backward compatibility:** Existing "agent inside container" mode (INF-05) must continue working unchanged. The gateway is additive, launched as a separate daemon.
- **GSD workflow enforcement:** All file edits during execution must go through a GSD command (`/gsd:execute-phase`).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mcp` (Python SDK) | `>=1.27.0` | MCP protocol + `FastMCP` server + `ClientSession` + transports | [VERIFIED: pypi.org/project/mcp 1.27.0 released 2026-04-02]. Official SDK from modelcontextprotocol org. Provides both server (`FastMCP`) and client (`stdio_client`, `streamablehttp_client`, `ClientSession`) APIs. Required by existing `configure-agent-mcp.sh` expectations and the idalib-mcp backend. |
| `starlette` | `>=0.37` | ASGI framework used by FastMCP's `streamable_http_app()`; used for mounting custom routes and middleware | [CITED: python-sdk README "Mounting to an Existing ASGI Server"]. `mcp` already depends on starlette transitively. |
| `uvicorn` | `>=0.27` | ASGI server | Standard runtime for Starlette/FastMCP apps. `mcp[cli]` extras include uvicorn; explicit install is safer. |
| `python-multipart` | `>=0.0.9` | Required by Starlette `request.form()` parser for multipart uploads | [CITED: starlette.io/requests]. Starlette raises AssertionError without it when `form()` is called. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | `>=0.27` | HTTP client used internally by `streamablehttp_client` | Transitive via `mcp`. Needed for `streamablehttp_client` to talk to idalib-mcp. |
| `anyio` | `>=4.5` | Async primitives (`AsyncExitStack`-friendly) | Transitive via `mcp` and starlette. |
| `pydantic` | `>=2.7` | Tool input schema generation (FastMCP uses type hints + pydantic to auto-generate JSON schemas) | Transitive via `mcp`. Our tool handlers can use `BaseModel` for complex inputs or rely on FastMCP's inference from type hints. |
| `pytest`, `pytest-asyncio` | latest | Unit + async test runner | Already in Dockerfile (`pytest`, `ruff`). Add `pytest-asyncio` for async test coverage. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Official `mcp` SDK FastMCP | `fastmcp` (jlowin/PrefectHQ v2) | The standalone `fastmcp` package has a nicer `@custom_route` decorator, but it's a separate ecosystem (v2) and has had regressions with that decorator [CITED: github.com/jlowin/fastmcp issues #556, #1311]. The official SDK's `streamable_http_app()` + manual Starlette `Mount` is the stable path and matches what's already in the repo (ghidra-headless-mcp uses the official SDK). Rejected. |
| Custom FastMCP gateway | `mcp-proxy` (sparfenyuk) | [CITED: CLAUDE.md "Recommended Stack"] mcp-proxy is a 1:1 stdio→HTTP bridge. It cannot: (a) aggregate multiple backends, (b) rename tools, (c) host a /upload endpoint, (d) serve orchestrator scripts as atomic tools. User explicitly chose custom FastMCP (D-01..D-20). Rejected per user decision. |
| Starlette `Mount()` | FastAPI | FastAPI adds an unnecessary layer and schema generator on top of Starlette. FastMCP already emits MCP JSON schema from type hints; we only need raw HTTP for `/upload`. Starlette is lighter. Rejected. |

**Installation:**
```bash
pip install --no-cache-dir --break-system-packages \
    "mcp>=1.27.0" \
    "uvicorn>=0.27" \
    "starlette>=0.37" \
    "python-multipart>=0.0.9" \
    "httpx>=0.27"
```

**Version verification:**
- `mcp` 1.27.0 confirmed on pypi 2026-04-02 [VERIFIED: pypi.org/project/mcp/].
- Rest are stable, transitively included. The explicit install makes the dependency intent auditable.
- Add `pip show mcp starlette uvicorn` to a container smoke test to confirm versions at runtime.

## Architecture Patterns

### Recommended Project Structure
```
mcp-gateway/
├── pyproject.toml                  # Package metadata, entry-point: `mcp-gateway`
├── README.md                       # Quick reference for operators
├── src/
│   └── mcp_gateway/
│       ├── __init__.py
│       ├── __main__.py              # `python -m mcp_gateway` entry
│       ├── cli.py                   # argparse + main()
│       ├── app.py                   # Starlette ASGI factory (FastMCP + routes + middleware)
│       ├── auth.py                  # BearerAuthMiddleware, token lifecycle
│       ├── backend/
│       │   ├── __init__.py
│       │   ├── detect.py            # Backend detection (IDA > BN > Ghidra), mirrors configure-agent-mcp.sh
│       │   ├── client.py            # PinnedBackend wrapper: holds a persistent ClientSession
│       │   ├── stdio_backend.py     # Spawn BN/Ghidra stdio subprocess + ClientSession
│       │   ├── http_backend.py      # Connect ClientSession to idalib-mcp http://127.0.0.1:8745/mcp
│       │   └── tool_map.py          # Unified-name → backend-tool-name mapping per backend
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── cases.py             # list_cases, get_artifact, set_active_case
│       │   ├── workflows.py         # run_triage, run_deep_analysis, generate_report
│       │   ├── artifacts.py         # init_case, collect_strings, collect_imports, scan_yara, scan_capa, rank_signals, build_hypothesis, update_state
│       │   ├── disasm.py            # decompile, list_functions, get_xrefs (delegate to backend)
│       │   └── samples.py           # resolve_sample helper (sha256 or path)
│       ├── uploads.py               # POST /upload handler with streaming body
│       ├── session_state.py         # Module-level active-case (Phase 2 single-session model)
│       └── subprocess_runner.py     # asyncio helper for shelling out to orchestrator scripts
└── tests/
    ├── conftest.py                   # FakeBackend fixture (in-process MCP server)
    ├── test_auth.py                  # BearerAuthMiddleware 401/200 cases
    ├── test_uploads.py               # /upload streaming, size cap, sha256 dedupe
    ├── test_sample_resolution.py     # resolve_sample: hash vs path, traversal
    ├── test_tool_routing.py          # disasm tools route to fake backend
    ├── test_artifact_tools.py        # orchestrator shell-outs with tmp case dir
    ├── test_workflow_tools.py        # run_triage composite ordering
    └── test_detect.py                # backend detection priority chain
```

Container install path: `/opt/mcp-gateway/` (copied during Docker build), installed with `pip install -e /opt/mcp-gateway`. Entry script on PATH: `mcp-gateway` (via `[project.scripts]` in pyproject.toml) or `python3 -m mcp_gateway`.

### Pattern 1: FastMCP Streamable HTTP Server (Official SDK)

**What:** The server-side skeleton. FastMCP provides an ASGI app we mount under `/mcp` on a Starlette root app.

**When to use:** Always — this is the only blessed way to expose Streamable HTTP in the official SDK.

**Example:**
```python
# Source: https://github.com/modelcontextprotocol/python-sdk/blob/main/README.md
# [CITED: python-sdk README "Mounting to an Existing ASGI Server"]
import contextlib
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "mare-gateway",
    stateless_http=True,       # simple per-request model; multi-session deferred to v2
    json_response=True,        # return JSON instead of forcing SSE upgrade when possible
)

@mcp.tool()
def health() -> dict:
    """Gateway health check."""
    return {"status": "ok"}

# Lifespan runs the FastMCP session manager (required for streamable_http_app)
@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        # also: enter persistent backend ClientSession here (Pattern 2)
        yield

app = Starlette(
    routes=[
        Mount("/mcp", app=mcp.streamable_http_app()),
        Route("/upload", upload_handler, methods=["POST"]),
        Route("/healthz", health_http, methods=["GET"]),
    ],
    lifespan=lifespan,
)
```

**Key constraints from MCP spec 2025-03-26** [CITED: modelcontextprotocol.io/specification/2025-03-26/basic/transports]:
- Server MUST validate `Origin` header (DNS-rebind protection). Add to middleware.
- Server MUST bind to 127.0.0.1 by default for local deployments.
- Server MUST respond at a single MCP endpoint path (we pick `/mcp`) supporting both POST and GET.
- Server MAY issue an `Mcp-Session-Id` header; for Phase 2 use `stateless_http=True` so this is handled automatically.
- Client's POST MUST carry `Accept: application/json, text/event-stream`.

### Pattern 2: Backend-as-Client (MCP Client inside a Server)

**What:** The gateway holds a persistent `ClientSession` to the pinned backend. Tool handlers delegate by calling `backend_session.call_tool(remapped_name, args)`.

**When to use:** For every disassembler tool (`decompile`, `list_functions`, `get_xrefs`, and a few others).

**Example (IDA — Streamable HTTP client):**
```python
# Source: MCP Python SDK README; [CITED: python-sdk README "Writing MCP Clients"]
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client   # note: streamablehttp, no underscore
from mcp.client.stdio import stdio_client, StdioServerParameters

class PinnedBackend:
    """Holds a long-lived ClientSession to the selected disassembler backend."""
    def __init__(self, backend: str):
        self.backend = backend              # "ida" | "bn" | "ghidra"
        self._stack = AsyncExitStack()
        self.session: ClientSession | None = None

    async def __aenter__(self):
        if self.backend == "ida":
            # idalib-mcp already runs as a daemon on 127.0.0.1:8745 (Phase 1)
            transport = await self._stack.enter_async_context(
                streamablehttp_client("http://127.0.0.1:8745/mcp")
            )
            read, write, _get_session_id = transport
        else:
            script = {
                "bn": "/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py",
                "ghidra": "/agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py",
            }[self.backend]
            env = {"GHIDRA_INSTALL_DIR": "/usr/share/ghidra"} if self.backend == "ghidra" else None
            params = StdioServerParameters(command="python3", args=[script], env=env)
            transport = await self._stack.enter_async_context(stdio_client(params))
            read, write = transport

        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()
        self.session = None

    async def call(self, backend_tool: str, args: dict):
        if self.session is None:
            raise RuntimeError("backend not initialized")
        result = await self.session.call_tool(backend_tool, args)
        return result
```

Then in `lifespan`:
```python
@contextlib.asynccontextmanager
async def lifespan(app):
    backend = detect_backend()                       # "ida" | "bn" | "ghidra"
    async with PinnedBackend(backend) as pinned:
        app.state.pinned = pinned
        async with mcp.session_manager.run():
            yield
```

Tool handler delegates:
```python
@mcp.tool()
async def decompile(function: str, sample: str | None = None, ctx: Context) -> str:
    """Decompile a function in the active sample via the pinned disassembler backend."""
    sample_path = resolve_sample(sample or active_sample())
    backend_name = app.state.pinned.backend
    backend_tool, backend_args = tool_map.translate(
        unified="decompile",
        backend=backend_name,
        args={"function": function, "sample_path": sample_path},
    )
    result = await app.state.pinned.call(backend_tool, backend_args)
    return mcp_text(result)
```

### Pattern 3: Bearer Auth Middleware

**What:** A `BaseHTTPMiddleware` that rejects requests without `Authorization: Bearer <TOKEN>` on both `/mcp*` and `/upload`.

**Example:**
```python
# [CITED: starlette.io/middleware and starlette.io/authentication]
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import hmac

class BearerAuthMiddleware(BaseHTTPMiddleware):
    PROTECTED_PREFIXES = ("/mcp", "/upload")

    def __init__(self, app, token: str):
        super().__init__(app)
        self._token = token.encode()

    async def dispatch(self, request, call_next):
        # allow /healthz unauthenticated
        if not any(request.url.path.startswith(p) for p in self.PROTECTED_PREFIXES):
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"error": "missing bearer token"}, status_code=401)

        presented = auth.split(" ", 1)[1].strip().encode()
        if not hmac.compare_digest(presented, self._token):
            return JSONResponse({"error": "invalid bearer token"}, status_code=401)

        return await call_next(request)
```

Wire into the app:
```python
app.add_middleware(BearerAuthMiddleware, token=load_or_generate_token())
```

**Key points:**
- Use `hmac.compare_digest` (constant-time), not `==`, to avoid timing attacks.
- Case-insensitive header lookup (HTTP header casing is not preserved).
- Apply to both `/mcp*` and `/upload`; leave `/healthz` open.
- Also validate `Origin` header per MCP spec § Security Warning to prevent DNS rebinding — add a second small middleware or combine in one.

### Pattern 4: Streaming File Upload with Size Cap

**What:** `/upload` accepts a binary body, streams to a temp file, computes sha256 on the fly, then moves to `/agent/uploads/<sha256>/<name>`.

**Example (raw body streaming — preferred for 1 GB cap):**
```python
# [CITED: starlette.io/requests "Stream"]
import hashlib, os, tempfile, shutil
from starlette.requests import Request
from starlette.responses import JSONResponse

UPLOAD_DIR = "/agent/uploads"
MAX_BYTES = int(os.environ.get("MCP_GATEWAY_MAX_UPLOAD_MB", "1024")) * 1024 * 1024

async def upload_handler(request: Request) -> JSONResponse:
    filename = request.headers.get("x-filename", "sample.bin")
    if "/" in filename or ".." in filename:
        return JSONResponse({"error": "invalid filename"}, status_code=400)

    total = 0
    sha = hashlib.sha256()
    # Stream to a temp file first; rename to content-hashed path at the end.
    with tempfile.NamedTemporaryFile(
        dir=UPLOAD_DIR, delete=False, prefix=".incoming-", suffix=".bin"
    ) as tmp:
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_BYTES:
                tmp.close()
                os.unlink(tmp.name)
                return JSONResponse(
                    {"error": f"upload exceeds {MAX_BYTES} bytes"},
                    status_code=413,
                )
            sha.update(chunk)
            tmp.write(chunk)
        tmp_path = tmp.name

    digest = sha.hexdigest()
    target_dir = os.path.join(UPLOAD_DIR, digest)
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, filename)
    if os.path.exists(target):
        os.unlink(tmp_path)   # dedupe
    else:
        shutil.move(tmp_path, target)
    os.chmod(target, 0o644)
    return JSONResponse({"sample_id": digest, "path": target, "size": total})
```

**Client usage:**
```bash
curl -X POST http://127.0.0.1:8080/upload \
    -H "Authorization: Bearer $TOKEN" \
    -H "X-Filename: suspect.exe" \
    --data-binary @/path/to/local/suspect.exe
```

**Note on multipart vs raw:** Multipart is nicer for curl but Starlette's `request.form()` buffers to a temp spool (using `python-multipart`'s `max_part_size`). Raw body + `X-Filename` header is simpler, streams without multipart parsing overhead, and matches mastra.ai/Claude Code's usage patterns. Use raw body as default; accept multipart as a secondary branch if `Content-Type: multipart/*`.

### Pattern 5: Async Subprocess for Orchestrator Scripts

**What:** Atomic tools (`collect_strings`, `scan_yara`, `run_triage` composite, etc.) shell out to existing skill scripts via `asyncio.create_subprocess_exec`. Capture stdout/stderr/exit code and return a structured result.

**Example:**
```python
# [ASSUMED: idiomatic asyncio pattern — verified by python docs; not specific to MCP]
import asyncio, shlex
from pathlib import Path

SCRIPTS = Path("/agent/workspace/.claude/skills/malware-analysis-orchestrator/scripts")

async def run_script(argv: list[str], *, cwd: str, timeout: float = 600.0) -> dict:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise

    return {
        "exit_code": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }

@mcp.tool()
async def collect_strings(sample: str, case_dir: str | None = None) -> dict:
    """Collect raw strings from the sample; writes <case_dir>/01_strings_raw.txt."""
    sample_path = resolve_sample(sample)
    argv = [str(SCRIPTS / "collect_strings.sh"), sample_path]
    if case_dir:
        argv.append(case_dir)
    result = await run_script(argv, cwd="/agent")   # scripts write under status/ relative to cwd
    if result["exit_code"] != 0:
        raise McpError(f"collect_strings failed: {result['stderr'][:500]}")
    return result
```

Key points:
- Use `create_subprocess_exec`, never `subprocess.run` (blocks the event loop).
- Always provide a timeout — long-running triage should have minutes-scale timeout (e.g., 600s); fast tools (update_state) under 30s.
- cwd MUST be `/agent` because `init_status_tree.sh` uses relative path `status/` — see `init_status_tree.sh` line 33 (`STATUS_ROOT="status"`).
- Do NOT pipe sample data through stdin (files only — matches script signature `<sample_path>`).

### Anti-Patterns to Avoid

- **Don't use `subprocess.run` in a tool handler.** It blocks the ASGI event loop and stalls all concurrent tool calls.
- **Don't use `await request.body()` for uploads.** It buffers the entire body in memory — 1 GB uploads will OOM the container. Use `request.stream()` instead.
- **Don't spawn a stdio subprocess per tool call.** The backend `ClientSession` is expensive to initialize (BN/Ghidra load the program); pin it for the gateway lifetime (D-09).
- **Don't share one `ClientSession` across unrelated sample analyses in BN/Ghidra.** BN/Ghidra stdio MCPs open and hold a program; the active program is per-session. Phase 2's single-session model assumes one active sample at a time; closing/reopening the program happens through the backend's own tools (e.g., `program.open`). Document this as a known limitation.
- **Don't re-implement the 13-artifact pipeline.** Call existing scripts (D-08). Single-sourced logic is the whole point of reusing the orchestrator skill.
- **Don't expose raw CLI passthrough as a tool.** Explicitly ruled out (REQUIREMENTS.md Out of Scope, CONTEXT.md D-05).
- **Don't rely on `localhost`.** idalib-mcp's server is IPv4-only and `localhost` resolves to `::1` on some clients (see `configure-agent-mcp.sh` comment lines 80-83). Always use `127.0.0.1` literal.
- **Don't generate the bearer token with `random.random()`.** Use `secrets.token_urlsafe(32)` — cryptographically secure.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP JSON-RPC server | Raw JSON-RPC over HTTP | `mcp.server.fastmcp.FastMCP` | Protocol spec is 100+ pages (initialization, notifications, session management, Mcp-Session-Id, SSE fallback). FastMCP handles all of it. |
| Tool JSON schema generation | Hand-written JSON schemas | Python type hints + `pydantic` (FastMCP infers schemas from type hints) | Drift between signature and schema is a common bug class. |
| MCP client connection | Raw JSON-RPC reader | `mcp.ClientSession` + `streamablehttp_client` / `stdio_client` | Handles initialization handshake, capability negotiation, and keeps Mcp-Session-Id in sync. |
| Bearer token generation | Hand-rolled PRNG | `secrets.token_urlsafe(32)` | Cryptographically secure; 256 bits of entropy. |
| Constant-time token comparison | `==` | `hmac.compare_digest` | Defends against timing-based token disclosure. |
| Streaming upload to disk | `await request.body()` then write | `async for chunk in request.stream()` | Avoids buffering a 1 GB body in memory. |
| Subprocess exec from async | `subprocess.run` / `Popen` | `asyncio.create_subprocess_exec` | Won't block the event loop; integrates with timeouts. |
| sha256 computation | Reading file twice | Hash as you stream (`hashlib.sha256().update(chunk)`) | One pass; no extra disk read. |
| ASGI app composition | Custom ASGI dispatcher | `starlette.routing.Mount` + `starlette.routing.Route` | Battle-tested; supports lifespan, middleware, websockets. |
| ASGI auth middleware | Manual header parsing in every route | `starlette.middleware.base.BaseHTTPMiddleware` | One definition, applies to all routes uniformly. |
| Backend detection | Re-implement in Python from scratch | Either shell out to a shared `/usr/local/bin/detect-disasm-backend.sh` OR translate the 50 lines into a tiny `detect.py` module that both `configure-agent-mcp.sh` (via CLI) and the gateway can call | Keeps "one truth" for priority chain; duplication leads to drift (e.g., Phase 1 D-06 vs REQUIREMENTS.md GW-03 already shows this risk). |

**Key insight:** Every item above has a mature, well-tested library / stdlib primitive. Hand-rolling any of them adds a security or correctness footgun without a single upside.

## Tool Surface Design

**Target count (GW-02):** 15-25. Design proposal: **21 tools**.

### Composite workflow tools (3)
| Name | Purpose | Implementation |
|------|---------|----------------|
| `run_triage` | Full triage pipeline: init case, collect strings, collect imports, scan yara, scan capa, rank signals, build hypothesis, mark `triage_complete` | Calls the atomic tools in sequence (matches SKILL.md "Quick Start"). |
| `run_deep_analysis` | Placeholder for deep-analysis phase: references `deep-analysis-checklist.md`, marks `planning_complete` | Phase 2: minimal stub that updates state; full deep-analysis in v2. |
| `generate_report` | Emit executive + technical summary from `10_reporting_draft.md` | Reads artifact, returns formatted content (Phase 2 scope: return-only, no extra writing). |

### Atomic pipeline tools (10, mapped to scripts)
| Name | Script / Logic | Artifacts produced |
|------|----------------|--------------------|
| `init_case` | `scripts/init_status_tree.sh <sample> [--new]` | Creates `status/<NNN>-<filename>/` + all 13 empty artifact files |
| `collect_strings` | `scripts/collect_strings.sh <sample> [case_dir]` | `00_sample_profile.md`, `01_strings_raw.txt` |
| `collect_imports` | `scripts/collect_imports.sh <sample> [case_dir]` | `03_imports_raw.txt` |
| `scan_yara` | `scripts/scan_yara.sh <sample> [case_dir]` | appends YARA matches to `00_sample_profile.md` |
| `scan_capa` | `scripts/scan_capa.sh <sample> [case_dir]` | appends capa tables to `00_sample_profile.md`, `tool-logs/capa.json` |
| `rank_signals` | `python3 scripts/rank_signals.py --status-dir <case_dir>` | `02_strings_interesting.md`, `04_imports_interesting.md` |
| `build_hypothesis` | `python3 scripts/build_hypothesis.py --status-dir <case_dir>` | `05_behavior_hypotheses.md` |
| `update_state` | `python3 scripts/update_state.py --status-dir <case_dir> --phase <x>` | `INDEX.md`, `CURRENT_STATE.json` |
| `resolve_case` | `scripts/resolve_case.sh <sample>` (returns latest case dir) | —  (pure query) |
| `get_artifact` | Reads `<case_dir>/<artifact_name>` content and returns it | — (pure query) |

### Disassembler tools (unified, route to backend) (3)
Phase 2 minimum:
| Unified name | IDA tool name | BN tool name | Ghidra tool name |
|--------------|---------------|--------------|------------------|
| `decompile` | `decompile` | `decompile` (or similar — planner verifies at spawn time) | `decomp.function` |
| `list_functions` | `list_funcs` | `list_functions` (or similar) | `function.list` |
| `get_xrefs` | `xrefs_to` | (backend-specific) | `reference.to` |

Future disassembler tools for v2: `get_function_at`, `get_strings_defined`, `get_imports`, etc. Phase 2 ships only these 3 to stay under the 25 cap; the planner can add 1-2 more if the tool count budget allows.

### Case management tools (5)
| Name | Purpose |
|------|---------|
| `list_cases` | Enumerate `status/[0-9][0-9][0-9]-*/` directories, return metadata |
| `set_active_case` | Set module-level `ACTIVE_CASE` var (Phase 2 single-session model) |
| `get_active_case` | Query current active case |
| `list_uploads` | Enumerate `/agent/uploads/<sha256>/*` (helpful for clients that uploaded via `/upload`) |
| `get_sample_info` | Return `{sha256, size, format, path}` for a sample (sha256 or path) |

**Total: 3 + 10 + 3 + 5 = 21 tools.** Fits GW-02's 15-25 range.

### Critical priority clarification

CONTEXT.md D-09 and Phase 1 D-06 both say priority is **IDA > BN > Ghidra**. REQUIREMENTS.md GW-03 text says "BN > IDA > Ghidra". `docker-bin/configure-agent-mcp.sh` lines 67-68 say IDA > BN > Ghidra. The **authoritative priority is IDA > BN > Ghidra** — this is also what the existing code enforces. The plan MUST include an update to REQUIREMENTS.md GW-03 to correct the stale "BN > IDA > Ghidra" wording, and the gateway's `detect.py` MUST match the existing bash priority chain.

## Common Pitfalls

### Pitfall 1: FastMCP namespace confusion
**What goes wrong:** Developer imports `from fastmcp import FastMCP` (jlowin package) instead of `from mcp.server.fastmcp import FastMCP` (official SDK).
**Why:** Two packages exist; the standalone `fastmcp` has a more ergonomic API (e.g., `@custom_route`). CLAUDE.md and CONTEXT.md implicitly reference the official SDK.
**How to avoid:** Pin `mcp>=1.27.0` in `pyproject.toml`; do NOT add a `fastmcp` dep. Import from `mcp.server.fastmcp`. Add a single `import` line in `tests/test_imports.py` that imports the correct symbols.
**Warning signs:** `ModuleNotFoundError: No module named 'fastmcp'` in CI (wrong package) OR `AttributeError: 'FastMCP' object has no attribute 'custom_route'` (wrong FastMCP).

### Pitfall 2: Missing `session_manager.run()` lifespan
**What goes wrong:** Streamable HTTP returns 503 or hangs on first `initialize` request.
**Why:** `streamable_http_app()` requires the session manager to be running for session management.
**How to avoid:** Wrap the entire app in a `lifespan` async context that does `async with mcp.session_manager.run(): yield`.
**Warning signs:** Error message `session_manager is not running` on first POST to `/mcp`.

### Pitfall 3: `localhost` vs `127.0.0.1` hang
**What goes wrong:** Gateway tries to connect to `http://localhost:8745/mcp` and hangs for 30 seconds before timing out.
**Why:** idalib-mcp's zeromcp TCPServer is IPv4-only (documented in `configure-agent-mcp.sh` lines 80-83). Modern `httpx`/`fetch` resolves `localhost` to `::1` (IPv6) first.
**How to avoid:** Always use `127.0.0.1` literal in URLs pointing to idalib-mcp. Add a linter/test that rejects `localhost` in the backend config.
**Warning signs:** First tool call takes 30+ seconds; timeout error.

### Pitfall 4: Stdio subprocess deadlock
**What goes wrong:** BN/Ghidra subprocess hangs; gateway's tool calls never return.
**Why:** `stdio_client` writes to stdin and reads from stdout. If the subprocess writes to stderr without a reader (or writes more than the pipe buffer), it can deadlock.
**How to avoid:** The SDK's `stdio_client` handles this correctly (reads stdout into a background task; discards stderr by default). BUT: custom tooling that wraps `stdio_client` with extra I/O can break this. Follow the SDK pattern exactly. Log subprocess stderr separately (e.g., redirect to `/tmp/bn-mcp-stderr.log` via StdioServerParameters `errlog=`).
**Warning signs:** Gateway logs show `RuntimeError: Server process is not running` or silent hangs.

### Pitfall 5: Streamable HTTP `Accept` header
**What goes wrong:** Gateway's ClientSession to idalib-mcp gets 406 Not Acceptable.
**Why:** MCP 2025-03-26 spec mandates `Accept: application/json, text/event-stream` on every POST.
**How to avoid:** The SDK's `streamablehttp_client` sets this automatically. Don't override the `Accept` header manually.

### Pitfall 6: 1 GB upload OOM
**What goes wrong:** Large sample upload crashes the gateway with OOM or python hangs.
**Why:** Calling `await request.body()` or `await request.form()` in Starlette loads the entire body into memory (or a temp spool file without streaming).
**How to avoid:** Use `async for chunk in request.stream()` — streams raw bytes. Enforce the byte cap inline during streaming (see Pattern 4). For multipart, `max_part_size` only caps individual parts, not total; enforce total via streaming accounting.
**Warning signs:** Container memory usage spikes during upload; uvicorn logs "worker killed".

### Pitfall 7: Token leak via logs
**What goes wrong:** Auto-generated bearer token gets logged at INFO level in places other than the intentional one-line startup log, or the `/agent/.mcp-gateway-token` file has wrong permissions.
**Why:** Middleware that logs request headers can print `Authorization`. Debug logging can print env vars.
**How to avoid:**
  - Write the token file as `open(path, "w", opener=lambda p, f: os.open(p, f, 0o600))`, then `os.chown(path, agent_uid, agent_gid)`.
  - Add a log filter that redacts `Authorization` headers from access logs.
  - Set `uvicorn --access-log` off OR configure a formatter that drops the header.
**Warning signs:** Token appears in `docker compose logs` more than once.

### Pitfall 8: Origin header bypass
**What goes wrong:** Browser at malicious.com performs DNS rebind and calls the gateway despite 127.0.0.1 binding.
**Why:** Without `Origin` validation, any local browser page can POST to `http://127.0.0.1:8080/mcp` via DNS rebinding [CITED: MCP 2025-03-26 § Security Warning].
**How to avoid:** Add an OriginMiddleware: allowlist `null`, `http://127.0.0.1:*`, `http://localhost:*`. Reject everything else with 403.
**Warning signs:** N/A at development time; only manifests as a real attack.

### Pitfall 9: Orchestrator script cwd assumption
**What goes wrong:** `init_status_tree.sh` creates `status/` in the gateway's cwd (e.g., `/`) instead of `/agent`, breaking case discovery.
**Why:** Scripts use relative path `STATUS_ROOT="status"`.
**How to avoid:** Set `cwd="/agent"` in every `asyncio.create_subprocess_exec` call. Add an integration test that runs `init_case` and verifies `/agent/status/` was written.
**Warning signs:** `list_cases` returns empty list even after `init_case` succeeds.

### Pitfall 10: Phase 1 dependency — idalib-mcp EULA not accepted
**What goes wrong:** On a host without the IDA batch-mode EULA accepted, `idalib_open()` fails with "License not yet accepted, cannot run in batch mode". Gateway's disassembler tools return errors even though detection succeeded.
**Why:** Documented in `Dockerfile` lines 283-291 and `/usr/local/bin/ida-accept-eula`.
**How to avoid:** Not a gateway bug, but Phase 2 startup logs should surface the Phase 1 hint ("if IDA tools fail, run `ida-accept-eula`"). Don't silently hide backend errors — GW-D10.

## Code Examples

### Example 1: Full `mcp-gateway/src/mcp_gateway/app.py` skeleton
```python
# [Synthesized from MCP SDK patterns; all primitives cited above]
import contextlib, os, logging
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from mcp.server.fastmcp import FastMCP

from .auth import BearerAuthMiddleware, OriginMiddleware, load_or_generate_token
from .backend import detect_backend, PinnedBackend
from .uploads import upload_handler
from .tools import register_all_tools
from . import session_state

log = logging.getLogger("mcp_gateway")

def build_app() -> Starlette:
    token = load_or_generate_token()
    backend_name = detect_backend()        # "ida" | "bn" | "ghidra"; raises if none
    log.info("[gateway] backend: %s", backend_name)

    mcp = FastMCP("mare-gateway", stateless_http=True, json_response=True)
    register_all_tools(mcp)                # registers all 21 tools

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with PinnedBackend(backend_name) as pinned:
            session_state.PINNED_BACKEND = pinned
            log.info("[gateway] ready on %s:%s",
                     os.environ.get("MCP_GATEWAY_HOST", "127.0.0.1"),
                     os.environ.get("MCP_GATEWAY_PORT", "8080"))
            async with mcp.session_manager.run():
                yield

    app = Starlette(
        routes=[
            Route("/healthz", lambda r: _json({"ok": True}), methods=["GET"]),
            Route("/upload", upload_handler, methods=["POST"]),
            Mount("/mcp", app=mcp.streamable_http_app()),
        ],
        lifespan=lifespan,
    )
    app.add_middleware(OriginMiddleware)
    app.add_middleware(BearerAuthMiddleware, token=token)
    return app
```

### Example 2: `cli.py` — daemon entry
```python
import argparse, os, logging, uvicorn
from .app import build_app

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("MCP_GATEWAY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_GATEWAY_PORT", "8080")))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
    app = build_app()
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)
```

### Example 3: `auth.py` — token lifecycle + middleware
```python
import os, secrets, logging, hmac
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

log = logging.getLogger("mcp_gateway.auth")
TOKEN_FILE = Path(os.environ.get("MCP_GATEWAY_TOKEN_FILE", "/agent/.mcp-gateway-token"))

def load_or_generate_token() -> str:
    tok = os.environ.get("MCP_GATEWAY_TOKEN")
    if not tok:
        tok = secrets.token_urlsafe(32)
        log.info("[gateway] generated new bearer token")
    # Write token file with 0600 permissions
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(tok + "\n")
    if not os.environ.get("MCP_GATEWAY_QUIET"):
        log.info("[gateway] Bearer token: %s", tok)
    log.info("[gateway] token file: %s", TOKEN_FILE)
    return tok

class BearerAuthMiddleware(BaseHTTPMiddleware):
    PROTECTED_PREFIXES = ("/mcp", "/upload")
    def __init__(self, app, token: str):
        super().__init__(app)
        self._token = token.encode()
    async def dispatch(self, request, call_next):
        if not any(request.url.path.startswith(p) for p in self.PROTECTED_PREFIXES):
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"error": "missing bearer token"}, status_code=401)
        if not hmac.compare_digest(auth.split(" ", 1)[1].strip().encode(), self._token):
            return JSONResponse({"error": "invalid bearer token"}, status_code=401)
        return await call_next(request)

class OriginMiddleware(BaseHTTPMiddleware):
    ALLOWED_PREFIXES = ("http://127.0.0.1", "http://localhost", "null")
    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin")
        if origin is None or any(origin.startswith(p) for p in self.ALLOWED_PREFIXES):
            return await call_next(request)
        return JSONResponse({"error": "forbidden origin"}, status_code=403)
```

### Example 4: `backend/detect.py` — priority chain (mirrors bash)
```python
import os, shutil
from pathlib import Path

BINJA_MCP = Path("/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py")
GHIDRA_MCP = Path("/agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py")

def detect_backend() -> str:
    """Priority: IDA > BN > Ghidra. Mirrors docker-bin/configure-agent-mcp.sh lines 67-119."""
    ida_dir = Path("/opt/ida-pro")
    if ida_dir.is_dir() and any(ida_dir.iterdir()) and shutil.which("idalib-mcp"):
        return "ida"
    if Path("/opt/binaryninja/scripts/install_api.py").exists() and BINJA_MCP.exists():
        return "bn"
    if GHIDRA_MCP.exists():
        return "ghidra"
    raise RuntimeError("No disassembler backend available (checked IDA, BN, Ghidra)")
```

### Example 5: Test skeleton — `tests/conftest.py`
```python
import pytest, asyncio
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

@pytest.fixture
def fake_backend_mcp():
    """In-memory MCP server that stands in for a real BN/Ghidra backend."""
    fake = FastMCP("fake-backend", stateless_http=True)

    @fake.tool()
    def list_funcs() -> list[str]:
        return ["main", "init", "doWork"]

    @fake.tool()
    def decompile(function: str) -> str:
        return f"int {function}() {{ return 0; }}"

    return fake

@pytest.fixture
async def fake_client(fake_backend_mcp):
    async with create_connected_server_and_client_session(fake_backend_mcp) as session:
        yield session
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SSE transport (HTTP+SSE, protocol 2024-11-05) | Streamable HTTP (protocol 2025-03-26) | MCP spec update, June 2025 | SSE is deprecated; new servers should default to Streamable HTTP with SSE fallback. idalib-mcp already serves both on same port. |
| `sse_client` / `sse_server` helpers | `streamablehttp_client` / `streamable_http_app()` | mcp SDK 1.8.0, May 2025 | SSE helpers still exist for backcompat. |
| FastMCP 1.x standalone | Folded into `mcp.server.fastmcp` | 2024 | Use `mcp.server.fastmcp.FastMCP` in the official SDK; the standalone `fastmcp` is now a separate v2 project (jlowin/PrefectHQ). |
| Per-tool JSON schema hand-writing | Type hints + pydantic auto-derive | FastMCP 1.0 | Type hints on tool handlers are authoritative. |
| `mcp-remote` npm client for stdio→HTTP | mcp SDK native, or `mcp-proxy` | 2025 | `mcp-remote` had CVE-2025-6514 (CVSS 9.6 command injection). Avoid. |

**Deprecated / Outdated (do not use):**
- `@mcp.custom_route` — does not exist in the official SDK. Only in standalone `fastmcp` v2 (and has regressions). Use `starlette.routing.Route` directly.
- HTTP+SSE transport (protocol 2024-11-05) as the primary transport. Use Streamable HTTP; keep SSE fallback only if a client demands it.
- `mcp-remote` — use `streamablehttp_client` or `mcp-proxy` (though we don't need mcp-proxy per D-01).
- `MastraMCPClient` (mastra.ai) — use `MCPClient` in Phase 4.

## Runtime State Inventory

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None — gateway does not maintain its own DB. Uses `status/` directory tree (already managed by orchestrator scripts) and `/agent/uploads/<sha256>/` (created by this phase). | None — content-hashed upload dir is inherently idempotent. |
| Live service config | idalib-mcp daemon already listens on 127.0.0.1:8745 (Phase 1 — `agent-entrypoint.sh` lines 269-292). Gateway connects TO it, does not modify it. `configure-agent-mcp.sh` writes `.mcp.json` / `config.toml` for inner agents pointing at the disassembler backend — gateway does not affect this. | None — Phase 2 is additive. Phase 4 will add host-side client configs. |
| OS-registered state | None. Gateway is a user-space daemon started by `agent-entrypoint.sh` via `nohup`. No systemd / pm2 / cron. | None. |
| Secrets / env vars | New env vars introduced by this phase: `MCP_GATEWAY_TOKEN`, `MCP_GATEWAY_HOST`, `MCP_GATEWAY_PORT`, `MCP_GATEWAY_MAX_UPLOAD_MB`, `MCP_GATEWAY_QUIET`. Token persisted to `/agent/.mcp-gateway-token` (0600, owned by `agent`). | Phase 3 wires these through `compose.yaml`. Phase 4 surfaces the token to host-side clients. |
| Build artifacts / installed packages | `mcp-gateway/` will be `pip install -e`'d in the image; creates `mcp_gateway.egg-info/` under `/opt/mcp-gateway/`. The `mcp-gateway` console script gets installed to `/usr/local/bin/mcp-gateway`. | None — standard pip install. Dockerfile RUN block handles it. |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3.11+ | mcp SDK 1.27 | ✓ (Kali rolling ships 3.12+) | 3.12.3 local; container verifies `>=3.12` at build time | — |
| pip (with `--break-system-packages`) | System-wide install pattern | ✓ | Uses existing Dockerfile pattern | — |
| uvicorn | ASGI runtime | Need to install | `>=0.27` from PyPI | — |
| starlette | ASGI framework | Transitive via mcp | `>=0.37` | — |
| python-multipart | multipart form parsing (optional, only if we accept multipart uploads) | Need to install | `>=0.0.9` | Skip; use raw body streaming only |
| idalib-mcp daemon | IDA backend MCP server on 127.0.0.1:8745 | Conditional (only when INSTALL_IDA_PRO=1) | Phase 1 already wires this | If missing, priority chain falls to BN/Ghidra |
| `/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py` | BN backend MCP | Conditional (auto-cloned per workspace/CLAUDE.md) | — | Detection chain falls to Ghidra |
| `/agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py` | Ghidra backend MCP | Conditional (auto-cloned) + Ghidra installed when no commercial disassembler | — | If none present: gateway MUST fail loud at startup (D-10); no backend, no disassembler tools |
| Orchestrator skill scripts | Atomic pipeline tools | ✓ `workspace/.claude/skills/malware-analysis-orchestrator/scripts/` | Bind-mounted via `/agent` | If missing: `run_triage` fails with a clear error message |

**Missing dependencies with no fallback:**
- None at planning time. All runtime dependencies are addressed by either Phase 1 (disassemblers) or this phase's Dockerfile/pip install block.

**Missing dependencies with fallback:**
- When all three disassembler backends are absent, the gateway's atomic (non-disassembler) tools still work (`collect_strings`, `scan_yara`, etc.). Plan a "degraded mode" startup path: if `detect_backend()` raises, either (a) start anyway with a null backend and make disassembler tools return a clear "no backend available" error, or (b) fail loud at startup. Decision for Phase 2: **fail loud** (matches D-10 and Phase 1 D-06 "no silent fallback" policy).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` + `pytest-asyncio` (the existing project pattern — `ghidra_headless_mcp` uses pytest; Dockerfile installs `pytest` and `ruff`). Python 3.12. |
| Config file | `mcp-gateway/pyproject.toml` `[tool.pytest.ini_options]` section (asyncio_mode = "auto"). To be created in Wave 0. |
| Quick run command | `pytest mcp-gateway/tests/ -x --no-header -q` (from `/agent` in-container, or repo root on host) |
| Full suite command | `pytest mcp-gateway/tests/ -v --cov=mcp_gateway` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GW-01 | FastMCP server exposes Streamable HTTP endpoint responding to `initialize` | integration | `pytest mcp-gateway/tests/test_server_init.py -x` | Wave 0 |
| GW-01 | `tools/list` returns the curated 21-tool set | integration | `pytest mcp-gateway/tests/test_tool_list.py -x` | Wave 0 |
| GW-02 | Count of exposed tools is within 15-25 | unit | `pytest mcp-gateway/tests/test_tool_list.py::test_tool_count_in_range -x` | Wave 0 |
| GW-02 | Each orchestrator script has a matching atomic tool (named per D-03) | unit | `pytest mcp-gateway/tests/test_tool_list.py::test_atomic_tools_map_to_scripts -x` | Wave 0 |
| GW-03 | `decompile` tool routes to pinned backend; fake backend returns stub; gateway forwards | integration | `pytest mcp-gateway/tests/test_tool_routing.py -x` | Wave 0 |
| GW-03 | Unified name `list_functions` calls correct backend tool name per backend | unit | `pytest mcp-gateway/tests/test_tool_map.py -x` | Wave 0 |
| GW-04 | Request to `/mcp` without Authorization → 401 | integration | `pytest mcp-gateway/tests/test_auth.py::test_mcp_requires_bearer -x` | Wave 0 |
| GW-04 | Request to `/upload` without Authorization → 401 | integration | `pytest mcp-gateway/tests/test_auth.py::test_upload_requires_bearer -x` | Wave 0 |
| GW-04 | Valid bearer token passes through to `initialize` | integration | `pytest mcp-gateway/tests/test_auth.py::test_valid_bearer_ok -x` | Wave 0 |
| GW-04 | `/healthz` works without bearer | unit | `pytest mcp-gateway/tests/test_auth.py::test_health_open -x` | Wave 0 |
| GW-05 | Default bind is 127.0.0.1 | unit | `pytest mcp-gateway/tests/test_cli.py::test_default_bind_is_localhost -x` | Wave 0 |
| GW-05 | `MCP_GATEWAY_HOST=0.0.0.0` overrides | unit | `pytest mcp-gateway/tests/test_cli.py::test_env_overrides_bind -x` | Wave 0 |
| GW-06 | POST /upload with bytes creates `/agent/uploads/<sha256>/<name>` | integration | `pytest mcp-gateway/tests/test_uploads.py::test_upload_roundtrip -x` | Wave 0 |
| GW-06 | Upload > MAX_BYTES → 413 | integration | `pytest mcp-gateway/tests/test_uploads.py::test_upload_over_cap -x` | Wave 0 |
| GW-06 | Duplicate upload dedupes on sha256 | integration | `pytest mcp-gateway/tests/test_uploads.py::test_upload_dedupe -x` | Wave 0 |
| GW-06 | Uploaded sample usable via `collect_strings(sample=<sha256>)` | e2e (container) | `bash mcp-gateway/tests/e2e/test_upload_then_analyze.sh` | Wave 0 |
| (Phase gate) | Full docker-compose-up smoke: gateway reachable, tools/list, one triage run | e2e (container, manual-automated) | `bash mcp-gateway/tests/e2e/smoke.sh` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest mcp-gateway/tests/ -x --no-header -q` (< 30s)
- **Per wave merge:** Full suite `pytest mcp-gateway/tests/ -v --cov=mcp_gateway` + ruff lint
- **Phase gate:** Full suite green + container smoke test (`bash mcp-gateway/tests/e2e/smoke.sh`) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `mcp-gateway/pyproject.toml` — package metadata, pytest-asyncio config, `[project.scripts]` entry for `mcp-gateway`
- [ ] `mcp-gateway/tests/conftest.py` — shared fixtures: `fake_backend_mcp`, `gateway_test_client` (ASGI test client), `tmp_upload_dir`, `tmp_status_dir`, `bearer_token`
- [ ] `mcp-gateway/tests/e2e/smoke.sh` — docker-compose up + curl smoke test (to be authored in the last wave, but placeholder stubbed early)
- [ ] `mcp-gateway/tests/e2e/test_upload_then_analyze.sh` — upload-then-run integration
- [ ] Install `pytest-asyncio` in the Dockerfile gateway-install block
- [ ] `mcp-gateway/Makefile` or similar with `make test` shortcut (optional but nice)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Static bearer token (per D-16..D-18). OAuth 2.1 explicitly out of scope. |
| V3 Session Management | partial | Phase 2 uses `stateless_http=True` (no server-side session state). MCP `Mcp-Session-Id` is handled by the SDK. Multi-session isolation is deferred to v2 (GW-V2-03). |
| V4 Access Control | yes | Single token = single role = full access (`/mcp/*` and `/upload`). No per-tool scopes (D-18). `/healthz` is the only unauthenticated endpoint. |
| V5 Input Validation | yes | pydantic schemas via FastMCP type hints; `resolve_sample()` validates sha256 format and rejects path traversal; filename header on `/upload` is rejected if contains `/` or `..`. |
| V6 Cryptography | yes | `secrets.token_urlsafe(32)` for token generation; `hashlib.sha256` for sample IDs; `hmac.compare_digest` for token comparison. No hand-rolled crypto. |
| V9 Communication | yes | TLS is NOT terminated at the gateway (local deployment). Phase 3/4 discussion: if exposed beyond Docker network, TLS must be added at a reverse proxy (caddy/traefik). For now, localhost-only binding (D-19) + Docker network isolation. |
| V11 API | yes | Single well-defined endpoint: `/mcp` (POST/GET), `/upload` (POST), `/healthz` (GET). No undocumented routes. |
| V13 Configuration | yes | Environment-driven config; secrets file `/agent/.mcp-gateway-token` 0600 permissions. |

### Known Threat Patterns for Python ASGI + MCP stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Token disclosure via logs | Information Disclosure | Suppress `Authorization` in uvicorn access logs; `MCP_GATEWAY_QUIET=1` option for token log line (D-17); token file 0600. |
| Timing attack on token compare | Information Disclosure | `hmac.compare_digest` (constant time). |
| DNS rebinding attack | Spoofing / EoP | Origin header allowlist (MCP spec 2025-03-26 § Security Warning); bind 127.0.0.1. |
| Path traversal via upload filename | Tampering / EoP | Reject `/` and `..` in `X-Filename`; content-hashed directory layout means filename is only a hint, not a path. |
| Path traversal via sample parameter | Tampering / EoP | `resolve_sample()` canonicalizes path (`os.path.realpath`) and verifies it starts with `/agent/uploads/` OR `/agent/`; rejects others. |
| Large upload DoS (disk exhaustion) | DoS | Size cap `MCP_GATEWAY_MAX_UPLOAD_MB` enforced during streaming (D-14). |
| Large upload DoS (memory) | DoS | Stream with `request.stream()`, hash & write as chunks arrive. |
| Stdio subprocess exploits via passed args | Tampering / RCE | Never pass MCP tool input directly to shell; use `create_subprocess_exec` with argv list; orchestrator scripts explicitly accept `<sample_path>` and `<case_dir>`, both of which are filesystem paths we canonicalize first. |
| Command injection in `run_script` | RCE | `create_subprocess_exec(*argv)` — no shell, no string interpolation; argv entries are either literal script paths or values from `resolve_sample()`. |
| Cross-client session bleed (future) | Authorization | Phase 2 single-session model accepts this risk for now (GW-V2-03 is v2). Document clearly that concurrent remote clients share the active-case state. |
| Backend subprocess hijack | Tampering | Launch BN/Ghidra subprocess as `agent` user (not root); don't accept arbitrary args from MCP calls. |
| Unauthenticated health ping reveals backend | Information Disclosure | `/healthz` returns only `{"ok": true}`; does NOT reveal backend name or version. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ida-pro-mcp` exposes a `decompile` tool with argument `function` accepting a name or address | Tool Surface Design → Disassembler tools | LOW — tested easily at gateway startup by calling `tools/list` on the IDA backend ClientSession; planner can add a startup probe that logs backend's actual tool surface. |
| A2 | BN MCP server's tool name for "list all functions" is roughly `list_functions` | Tool Surface Design | LOW — same mitigation as A1; the `binary-ninja-headless-mcp` repo is vendored and the plan should grep its handler registry to confirm exact names. |
| A3 | Orchestrator scripts run successfully against samples under `/agent/uploads/<sha256>/<name>` (not just `/agent/examples/...`) | Architecture Pattern 5 + Tool Surface | LOW — the scripts take a path argument, they do not care about the parent directory. `init_status_tree.sh` uses `basename "$SAMPLE"` (line 32). But case-directory collisions (two uploads with the same original filename) will reuse the same case — document this as a known quirk. |
| A4 | `/agent/uploads/` persists across `docker compose up` cycles because `/agent` is bind-mounted | Pattern 4 + CONTEXT D-13 | LOW — verified by reading compose.yaml line 11: `"${HOST_PWD:-.}:/agent"`. As long as users do not set `HOST_PWD=/tmp/foo`, uploads persist on the host under the project directory. |
| A5 | The existing BN/Ghidra MCP servers reliably handle being spawned as a long-lived subprocess with a program loaded early vs. per-request | Pattern 2 + D-09 | MEDIUM — Ghidra's server does have `program.open`/`program.close` tools (verified in `ghidra_headless_mcp/server.py`), so we can manage state explicitly. Binary Ninja's MCP wrapper has not been inspected yet in this research pass; plan should add a Wave 0 task to grep `mcp/binary-ninja-headless-mcp/` for the equivalent. |
| A6 | `mcp.server.fastmcp.FastMCP` in `mcp>=1.27.0` still exposes `streamable_http_app()` and `session_manager` as documented | Architecture Pattern 1 | LOW — verified against the python-sdk README (2026). Pin `mcp==1.27.0` to lock. |
| A7 | `host` and `port` kwargs on `FastMCP()` are ignored when we use `streamable_http_app()` + uvicorn directly (binding is done by uvicorn) | Pattern 1 + Example 2 | LOW — we pass host/port to uvicorn.run(), not FastMCP. Test coverage: `test_cli.py::test_env_overrides_bind`. |
| A8 | REQUIREMENTS.md GW-03 "BN > IDA > Ghidra" wording is stale; actual priority is IDA > BN > Ghidra per configure-agent-mcp.sh and Phase 1 D-06 | Phase Requirements table + Critical priority clarification | HIGH if wrong — would mean the gateway enforces the wrong priority. BUT: verified by reading `configure-agent-mcp.sh` lines 67-119 and Phase 1 CONTEXT.md D-06 + Phase 2 CONTEXT.md D-09 — all three sources agree on IDA > BN > Ghidra. Flagged as REQ correction task. |
| A9 | FastMCP `tools/list` can produce ≥15 visible tools when we register 21 handlers with `@mcp.tool()` decorators; FastMCP does not silently hide any based on type hints | Tool Surface Design | LOW — the Ghidra MCP server registers ~100 tools without issue. |
| A10 | `uvicorn` default body size does not block 1 GB uploads when we use `request.stream()` | Pattern 4 + Pitfall 6 | MEDIUM — `uvicorn` does not impose a default body size limit on streamed requests; limits apply to individual buffered items only. If a client sets `Content-Length: 2_000_000_000`, uvicorn forwards it; our middleware caps it during streaming. If we see 413s at uvicorn level before our middleware runs, plan adds an `--limit-max-requests` check. |

## Open Questions

1. **Exact backend tool names for BN MCP server** (A5)
   - What we know: Ghidra's server.py has a comprehensive `_BACKEND_TOOL_NAME_MAP` we can mirror.
   - What's unclear: BN's MCP tool names are not documented in this research pass.
   - Recommendation: Add a Wave 0 task in the plan: "Grep `/agent/mcp/binary-ninja-headless-mcp/*.py` for `@tool` / `register_tool` decorators; produce `backend/tool_map.py` table".

2. **Concurrency model for 21 tools sharing one backend ClientSession**
   - What we know: Phase 2 is single-session; `PinnedBackend` has one `ClientSession`.
   - What's unclear: If two `/mcp` requests arrive concurrently and both call `decompile`, does the shared session serialize them safely?
   - Recommendation: Add an `asyncio.Lock` around `PinnedBackend.call()` in Phase 2 (simple, correct, matches the "serialization" mention in Claude's Discretion). Document that v2 will lift this for multi-session.

3. **Composite `run_triage` error semantics**
   - What we know: Composite should call atomic tools in sequence.
   - What's unclear: If `scan_capa` fails mid-pipeline, do we abort or continue?
   - Recommendation: Continue-on-script-error (capa may not support the format, yara might have no matches) but return a structured `{step, exit_code, stderr}` list so the client sees what succeeded. Matches orchestrator skill's tolerance for missing tools.

4. **Token rotation**
   - What we know: Token is generated once at gateway start and persisted.
   - What's unclear: What if the user wants to rotate? Do we restart the gateway?
   - Recommendation: Phase 2 scope: yes, gateway restart is the rotation mechanism. Document in README. v2 may add a `rotate-token` admin tool.

5. **Reconcile CLAUDE.md with CONTEXT.md**
   - What we know: CLAUDE.md recommends mcp-proxy; CONTEXT.md chose custom FastMCP.
   - What's unclear: When does CLAUDE.md get updated?
   - Recommendation: Add a task to Wave N (docs) that updates `CLAUDE.md` "Recommended Stack" to reflect the custom FastMCP path and move `mcp-proxy` to "Alternatives Considered" with rationale "cannot aggregate multiple backends + expose /upload + apply auth in a single process".

6. **Versioning the gateway**
   - What we know: `mcp-gateway` is a new package.
   - What's unclear: Version strategy?
   - Recommendation: Start at `0.1.0`; tie future versions to the project milestone (v2.0 aligns with project v2). Add `__version__` to `mcp_gateway/_version.py` mirroring `ghidra_headless_mcp/_version.py`.

## Sources

### Primary (HIGH confidence)
- [MCP 2025-03-26 Transports spec](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — Streamable HTTP endpoint semantics, Mcp-Session-Id, security warning (Origin validation, localhost binding).
- [mcp python SDK on PyPI (1.27.0, 2026-04-02)](https://pypi.org/project/mcp/) — version, Python requirement.
- [mcp python SDK README (GitHub)](https://github.com/modelcontextprotocol/python-sdk) — `FastMCP`, `streamable_http_app()`, `session_manager`, `stdio_client`, `streamablehttp_client`, `ClientSession` patterns.
- `docker-bin/configure-agent-mcp.sh` (this repo) — backend detection priority chain (IDA > BN > Ghidra), IPv4-only note about localhost, idalib-mcp URL layout (`/mcp` + `/sse` on 8745).
- `Dockerfile` lines 115-147, 269-291 — existing idalib-mcp install and daemon start pattern; EULA handling.
- `compose.yaml` — env var and volume mount patterns.
- `mcp/ghidra-headless-mcp/ghidra_headless_mcp/server.py` — reference MCP server structure, tool-name style, backend-method mapping example.
- `workspace/.claude/skills/malware-analysis-orchestrator/scripts/` — exact script signatures, cwd assumption, case-directory conventions.
- `workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md` — 13-artifact canonical list.

### Secondary (MEDIUM confidence)
- [Starlette docs: Requests](https://www.starlette.io/requests/) — streaming request body, multipart `max_part_size`.
- [Starlette docs: Middleware](https://www.starlette.io/middleware/) — `BaseHTTPMiddleware` pattern.
- [Starlette docs: Authentication](https://www.starlette.io/authentication/) — bearer scheme handling.
- [Cloudflare blog — streamable HTTP MCP](https://blog.cloudflare.com/streamable-http-mcp-servers-python/) — persistent backend session pattern with `AsyncExitStack`.
- [CVE-2025-6514 (mcp-remote)](https://stackoverflow.blog/2026/01/21/is-that-allowed-authentication-and-authorization-in-model-context-protocol/) — CVSS 9.6 command injection in mcp-remote npm; confirms CLAUDE.md "Do NOT Use" list.
- [MCP authorization guide](https://modelcontextprotocol.io/docs/tutorials/security/authorization) — OAuth vs bearer tradeoffs.

### Tertiary (LOW confidence, flagged for validation)
- [ida-pro-mcp README (mrexodia)](https://github.com/mrexodia/ida-pro-mcp) — Exact tool names listing (used for the Tool Surface Design A1/A2 assumption rows). Validated against Phase 1 CONTEXT.md but not executed end-to-end.
- [FastMCP v2 (jlowin/PrefectHQ) issues](https://github.com/jlowin/fastmcp) — regressions on `@custom_route` (issues #556, #1311) — used only as evidence AGAINST using that package; does not affect our chosen path.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — `mcp` SDK version and API surface verified against pypi + README (2026).
- Architecture patterns: HIGH — Pattern 1/3/4 are canonical Starlette + mcp; Pattern 2 is synthesized but every primitive is from the SDK README; Pattern 5 is stdlib-only.
- Tool surface: MEDIUM — 21-tool count and naming are concrete; exact backend tool names for BN not yet grepped (A5).
- Pitfalls: HIGH — most are from spec text or this repo's own comments.
- Security: HIGH for listed controls; MEDIUM for threat model (not a full STRIDE session).
- Nyquist validation: HIGH — test-per-requirement mapping is concrete.

**Research date:** 2026-04-23
**Valid until:** 2026-05-23 (30 days — mcp SDK and Starlette are stable; re-check if mcp SDK ships a 1.28.x that changes `streamable_http_app` API)
