---
phase: 02-mcp-gateway
plan: 03
type: execute
wave: 3
depends_on:
  - 02-01
  - 02-02
files_modified:
  - mcp-gateway/src/mcp_gateway/backend/client.py
  - mcp-gateway/src/mcp_gateway/backend/passthrough.py
  - mcp-gateway/src/mcp_gateway/backend/__init__.py
  - mcp-gateway/src/mcp_gateway/app.py
  - mcp-gateway/tests/test_backend_client.py
  - mcp-gateway/tests/test_passthrough_registration.py
autonomous: true
requirements:
  - GW-03
tags:
  - mcp
  - backend
  - passthrough
  - python

must_haves:
  truths:
    - "`PinnedBackend(backend_name)` as async context manager establishes a ClientSession to the correct backend"
    - "For backend='ida': client connects to `http://127.0.0.1:8745/mcp` via streamablehttp_client (literal 127.0.0.1, never 'localhost' — Pitfall 3)"
    - "For backend='bn': client spawns `python3 /agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py` via stdio_client"
    - "For backend='ghidra': client spawns `python3 /agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py` via stdio_client with GHIDRA_INSTALL_DIR env"
    - "`PinnedBackend.__aenter__` calls `session.initialize()` and caches `tools/list` response as `self.backend_tools`"
    - "`PinnedBackend.call_tool(name, args)` forwards verbatim to `session.call_tool(name, args)` — no name rewriting, no arg translation"
    - "`PinnedBackend.call_tool` serializes concurrent calls via `asyncio.Lock` (RESEARCH Open Q2)"
    - "Backend subprocess/transport crash at __aenter__ raises clear error (D-10 fail loud, not silent fallback)"
    - "`register_backend_passthrough(mcp, pinned)` iterates `pinned.backend_tools` and registers ONE forwarding handler per backend tool on the gateway FastMCP — under the tool's NATIVE name with its NATIVE input schema"
    - "Registered pass-through tools do NOT collide with gateway-native tool names; collisions raise `ValueError` (fail loud — better than silent shadowing)"
    - "Gateway's `tools/list` (through in-memory client) after passthrough registration includes both native + backend tool names"
    - "`get_active_backend()` returns `{'backend': <name>}` matching the pinned backend once Plan 03's lifespan runs"
    - "Gateway startup log emits `[gateway] backend: <name>` → `[gateway] backend tools registered: <count>` → `[gateway] ready`"
  artifacts:
    - path: "mcp-gateway/src/mcp_gateway/backend/client.py"
      provides: "PinnedBackend (AsyncExitStack-based; IDA/BN/Ghidra support; call_tool + backend_tools cache)"
      exports: ["PinnedBackend"]
    - path: "mcp-gateway/src/mcp_gateway/backend/passthrough.py"
      provides: "register_backend_passthrough(mcp, pinned) — re-exposes backend tools with native names"
      exports: ["register_backend_passthrough"]
    - path: "mcp-gateway/src/mcp_gateway/backend/__init__.py"
      provides: "Re-exports detect_backend + PinnedBackend + register_backend_passthrough"
      exports: ["detect_backend", "PinnedBackend", "register_backend_passthrough"]
  key_links:
    - from: "mcp-gateway/src/mcp_gateway/backend/client.py::PinnedBackend.__aenter__"
      to: "streamablehttp_client OR stdio_client → ClientSession.initialize → session.list_tools"
      via: "AsyncExitStack + ClientSession"
      pattern: "AsyncExitStack.*ClientSession.*list_tools"
    - from: "mcp-gateway/src/mcp_gateway/backend/passthrough.py::register_backend_passthrough"
      to: "FastMCP tool registration with explicit input_schema from backend tools/list"
      via: "per-tool closure capturing (name, pinned) → pinned.call_tool(name, args)"
      pattern: "call_tool.*name"
    - from: "mcp-gateway/src/mcp_gateway/app.py::lifespan"
      to: "PinnedBackend context manager + register_backend_passthrough"
      via: "nested async with inside Starlette lifespan, BEFORE mcp.session_manager.run()"
      pattern: "async with PinnedBackend.*register_backend_passthrough"
---

<objective>
Implement the backend pass-through layer per revised D-07: `PinnedBackend` holds a long-lived `ClientSession` to the pinned disassembler backend (IDA via Streamable HTTP; BN/Ghidra via stdio subprocess) and exposes a generic `call_tool(name, args)` that forwards verbatim to the backend. `register_backend_passthrough(mcp, pinned)` enumerates the backend's `tools/list` and re-registers each backend tool on the gateway's FastMCP instance under its NATIVE name and NATIVE input schema. The lifespan wires this sequence BEFORE `session_manager.run()` so the first client `tools/list` sees both the 19 gateway-native tools (from Plan 02) and the backend's native tools.

Purpose: Fulfills GW-03 — client has one authenticated HTTP endpoint but gets access to the full backend tool surface. Under D-07 pass-through there is no translation layer — the gateway does not rename tools, does not rewrite args, does not manage backend session IDs. The orchestrator skill and other clients call `get_active_backend()` first, then drive the native backend tools directly.

Output: With Ghidra pinned, a client sees `program.open`, `function.list`, `decomp.function`, `reference.to`, etc. in `tools/list` alongside the 19 gateway-native tools. With IDA pinned, a client sees `decompile`, `list_funcs`, `xrefs_to`, etc. Backend session/program lifecycle is the client's concern.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/02-mcp-gateway/02-CONTEXT.md
@.planning/phases/02-mcp-gateway/02-RESEARCH.md
@.planning/phases/02-mcp-gateway/02-VALIDATION.md
@.planning/phases/02-mcp-gateway/02-DISCUSSION-LOG.md
@.planning/phases/02-mcp-gateway/02-01-package-scaffold-and-auth-PLAN.md
@.planning/phases/02-mcp-gateway/02-02-fastmcp-server-and-tool-surface-PLAN.md
@.planning/phases/01-ida-pro-backend/01-CONTEXT.md

<interfaces>
<!-- From Plan 01 -->
```python
from mcp_gateway.backend.detect import detect_backend   # "ida"|"bn"|"ghidra"
from mcp_gateway import session_state                   # PINNED_BACKEND = None at module scope
```

<!-- From Plan 02 -->
```python
from mcp_gateway.app import build_app, get_mcp           # lifespan hook is where PinnedBackend + passthrough get entered
from mcp_gateway.tools import register_all_tools         # already registers 19 gateway-native tools (incl. get_active_backend)
```

<!-- From MCP Python SDK -->
```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client   # for IDA
from mcp.client.stdio import stdio_client, StdioServerParameters   # for BN/Ghidra
from contextlib import AsyncExitStack
```

<!-- Phase 1 fact: idalib-mcp already runs as a daemon on 127.0.0.1:8745/mcp, started by agent-entrypoint.sh lines 269-292 -->

<!-- D-07 pass-through model — gateway does NOT rename or rewrite args. Client calls
     backend-native tools directly. For Ghidra this means client calls `program.open(path)`
     first, threads `session_id` into subsequent calls (`function.list(session_id, ...)`,
     `decomp.function(session_id, function_start)`, etc.). For IDA, idalib-mcp is pre-bound
     to one program at daemon startup, so there is no `program.open` — client calls
     `decompile(function=...)` directly on whatever binary idalib-mcp is serving. -->
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: PinnedBackend connection class (IDA http, BN/Ghidra stdio) + unit tests</name>
  <files>
    mcp-gateway/src/mcp_gateway/backend/client.py,
    mcp-gateway/src/mcp_gateway/backend/__init__.py,
    mcp-gateway/tests/test_backend_client.py
  </files>
  <read_first>
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Pattern 2 Backend-as-Client; § Pitfall 3 localhost IPv6; § Pitfall 4 stdio deadlock; § Pitfall 5 Accept header; § Open Questions #2 asyncio.Lock serialization)
    - .planning/phases/02-mcp-gateway/02-CONTEXT.md (D-06 MCP client not re-implementing; D-07 pass-through NOT translation; D-09 pinned; D-10 fail loud)
    - .planning/phases/02-mcp-gateway/02-01-package-scaffold-and-auth-PLAN.md (backend/__init__.py currently re-exports detect_backend only)
  </read_first>
  <behavior>
    - `PinnedBackend("ida")` as `async with` establishes ClientSession via `streamablehttp_client("http://127.0.0.1:8745/mcp")` (literal `127.0.0.1`, NOT `localhost` — Pitfall 3)
    - `PinnedBackend("bn")` spawns `StdioServerParameters(command="python3", args=["/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py"])` and wraps in `ClientSession`
    - `PinnedBackend("ghidra")` spawns `StdioServerParameters(command="python3", args=["/agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py"], env={..., "GHIDRA_INSTALL_DIR": ...})`
    - `PinnedBackend.__aenter__` calls `session.initialize()`, then `session.list_tools()`, and caches the `Tool` records as `self.backend_tools: list[Tool]`
    - `PinnedBackend.call_tool(name, args)` delegates to `self.session.call_tool(name, args)` under an `asyncio.Lock` — no translation, no rewriting
    - `PinnedBackend.__aexit__` closes the AsyncExitStack cleanly
    - `PinnedBackend("bogus")` raises `ValueError` (fail loud)
    - Backend init failure (transport error) surfaces as the underlying exception (no silent fallback — D-10)
    - Integration test: in-memory FastMCP backend → `PinnedBackend`-style wrapper connects via memory transport → `call_tool("native_name", {...})` returns backend's result
  </behavior>
  <action>
Create `mcp-gateway/src/mcp_gateway/backend/client.py`:

```python
"""PinnedBackend: holds a persistent MCP ClientSession to the selected backend.

D-06: gateway acts as an MCP client; no re-implementing disassembler logic.
D-07: pass-through — gateway forwards calls verbatim, never renames or translates args.
D-09: selected backend is pinned for the gateway's lifetime.
D-10: crashes fail loud (no silent fallback to next-priority backend).

Transport per backend:
  ida    — Streamable HTTP to http://127.0.0.1:8745/mcp (idalib-mcp daemon from Phase 1).
           Use 127.0.0.1 LITERAL, not 'localhost' (Pitfall 3 IPv6 hang).
  bn     — stdio subprocess: python3 /agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py
  ghidra — stdio subprocess: python3 /agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py
           with GHIDRA_INSTALL_DIR env (default /usr/share/ghidra, matches configure-agent-mcp.sh line 106).
"""
from __future__ import annotations
import asyncio
import logging
import os
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import Tool

log = logging.getLogger("mcp_gateway.backend")

IDA_URL = "http://127.0.0.1:8745/mcp"
BN_SCRIPT = "/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py"
GHIDRA_SCRIPT = "/agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py"

SUPPORTED_BACKENDS = ("ida", "bn", "ghidra")


class PinnedBackend:
    """Async context manager wrapping a long-lived ClientSession to a disassembler backend.

    After __aenter__ completes, `self.session` is ready and `self.backend_tools` holds
    the result of tools/list — consumed by `passthrough.register_backend_passthrough`.
    """

    def __init__(self, backend: str):
        if backend not in SUPPORTED_BACKENDS:
            raise ValueError(
                f"unsupported backend: {backend!r} (expected one of {SUPPORTED_BACKENDS})"
            )
        self.backend = backend
        self._stack = AsyncExitStack()
        self._call_lock = asyncio.Lock()
        self.session: ClientSession | None = None
        self.backend_tools: list[Tool] = []

    async def __aenter__(self) -> "PinnedBackend":
        try:
            if self.backend == "ida":
                transport = await self._stack.enter_async_context(
                    streamablehttp_client(IDA_URL)
                )
                read, write, _get_session_id = transport
            else:
                script = BN_SCRIPT if self.backend == "bn" else GHIDRA_SCRIPT
                env = None
                if self.backend == "ghidra":
                    ghidra_dir = os.environ.get("GHIDRA_INSTALL_DIR") or (
                        "/usr/share/ghidra" if os.path.isdir("/usr/share/ghidra") else None
                    )
                    if ghidra_dir:
                        env = {**os.environ, "GHIDRA_INSTALL_DIR": ghidra_dir}
                params = StdioServerParameters(command="python3", args=[script], env=env)
                transport = await self._stack.enter_async_context(stdio_client(params))
                read, write = transport

            self.session = await self._stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
            tools_resp = await self.session.list_tools()
            self.backend_tools = list(tools_resp.tools)
            log.info(
                "[gateway] backend session initialized: %s (%d tools)",
                self.backend,
                len(self.backend_tools),
            )
            return self
        except Exception:
            # Fail loud (D-10) — close partial state and re-raise.
            await self._stack.aclose()
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._stack.aclose()
        self.session = None
        self.backend_tools = []

    async def call_tool(self, name: str, args: dict[str, Any] | None = None):
        """Forward a tool call verbatim to the backend. D-07: no translation."""
        if self.session is None:
            raise RuntimeError("PinnedBackend not initialized — use as async context manager")
        async with self._call_lock:
            return await self.session.call_tool(name, args or {})
```

Update `mcp-gateway/src/mcp_gateway/backend/__init__.py`:

```python
from .detect import detect_backend
from .client import PinnedBackend
from .passthrough import register_backend_passthrough

__all__ = ["detect_backend", "PinnedBackend", "register_backend_passthrough"]
```

Create `mcp-gateway/tests/test_backend_client.py`:

```python
"""Tests for PinnedBackend connection wrapper (no translation layer — D-07 pass-through)."""
from __future__ import annotations
import asyncio

import pytest
from mcp.server.fastmcp import FastMCP

from mcp_gateway.backend import client as client_mod


class _FakePinnedBackend:
    """In-memory PinnedBackend using the SDK's memory transport — avoids network/stdio."""

    def __init__(self, backend: str, fake_mcp: FastMCP):
        self.backend = backend
        self._fake = fake_mcp
        self.session = None
        self._call_lock = asyncio.Lock()
        self.backend_tools = []
        self._cm = None

    async def __aenter__(self):
        from mcp.shared.memory import create_connected_server_and_client_session
        self._cm = create_connected_server_and_client_session(self._fake._mcp_server)
        self.session = await self._cm.__aenter__()
        tools_resp = await self.session.list_tools()
        self.backend_tools = list(tools_resp.tools)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._cm.__aexit__(exc_type, exc_val, exc_tb)
        self.session = None
        self.backend_tools = []

    async def call_tool(self, name, args=None):
        async with self._call_lock:
            return await self.session.call_tool(name, args or {})


@pytest.fixture
def ghidra_like_backend_mcp() -> FastMCP:
    """In-memory MCP server mimicking Ghidra's native tool surface (with session_id)."""
    m = FastMCP("fake-ghidra", stateless_http=True)

    @m.tool(name="program.open")
    def program_open(path: str) -> dict:
        return {"session_id": "sess-123", "program": path}

    @m.tool(name="function.list")
    def function_list(session_id: str, offset: int = 0, limit: int = 100) -> dict:
        # Real Ghidra signature. No gateway translation — client passes session_id itself.
        return {"session_id": session_id, "items": [{"name": "main"}, {"name": "entry"}]}

    @m.tool(name="decomp.function")
    def decomp_function(session_id: str, function_start: str) -> dict:
        return {"session_id": session_id, "function_start": function_start, "text": "void f() {}"}

    return m


@pytest.fixture
def ida_like_backend_mcp() -> FastMCP:
    """In-memory MCP server mimicking IDA's native tool surface (pre-bound program)."""
    m = FastMCP("fake-ida", stateless_http=True)

    @m.tool()
    def decompile(function: str) -> str:
        return f"int {function}() {{ return 0; }}"

    @m.tool()
    def list_funcs() -> list[str]:
        return ["main", "init"]

    @m.tool()
    def xrefs_to(function: str) -> list[str]:
        return [f"ref_to_{function}"]

    return m


# -------- Constants / input validation --------

def test_pinned_backend_rejects_unknown():
    with pytest.raises(ValueError, match="unsupported backend"):
        client_mod.PinnedBackend("qemu")


def test_ida_url_uses_127_0_0_1_literal():
    assert client_mod.IDA_URL == "http://127.0.0.1:8745/mcp"
    assert "localhost" not in client_mod.IDA_URL


def test_bn_script_path():
    assert client_mod.BN_SCRIPT == "/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py"


def test_ghidra_script_path():
    assert client_mod.GHIDRA_SCRIPT == "/agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py"


def test_supported_backends_matches_detect():
    from mcp_gateway.backend.detect import BACKENDS
    assert client_mod.SUPPORTED_BACKENDS == BACKENDS


# -------- __aenter__ / call_tool against fake backends --------

@pytest.mark.asyncio
async def test_aenter_caches_backend_tools(ghidra_like_backend_mcp):
    async with _FakePinnedBackend("ghidra", ghidra_like_backend_mcp) as pinned:
        names = {t.name for t in pinned.backend_tools}
        assert names == {"program.open", "function.list", "decomp.function"}


@pytest.mark.asyncio
async def test_call_tool_forwards_verbatim_ghidra_session_flow(ghidra_like_backend_mcp):
    """D-07: gateway does NOT manage session_id — client threads it through call_tool."""
    async with _FakePinnedBackend("ghidra", ghidra_like_backend_mcp) as pinned:
        # Client opens program and grabs session_id
        open_result = await pinned.call_tool("program.open", {"path": "/agent/uploads/foo"})
        text_block = next(b for b in open_result.content if getattr(b, "text", None))
        import json
        opened = json.loads(text_block.text)
        session_id = opened["session_id"]

        # Client threads session_id into subsequent call
        list_result = await pinned.call_tool(
            "function.list", {"session_id": session_id, "offset": 0, "limit": 100}
        )
        text_block = next(b for b in list_result.content if getattr(b, "text", None))
        listed = json.loads(text_block.text)
        assert listed["session_id"] == session_id
        assert len(listed["items"]) == 2


@pytest.mark.asyncio
async def test_call_tool_forwards_verbatim_ida_no_session(ida_like_backend_mcp):
    """IDA has no session concept — idalib-mcp is pre-bound to one program."""
    async with _FakePinnedBackend("ida", ida_like_backend_mcp) as pinned:
        r = await pinned.call_tool("decompile", {"function": "main"})
        text_block = next(b for b in r.content if getattr(b, "text", None))
        assert "int main()" in text_block.text


@pytest.mark.asyncio
async def test_call_tool_serializes_concurrent_calls(ida_like_backend_mcp):
    """asyncio.Lock serializes concurrent call_tool invocations (Open Q2)."""
    async with _FakePinnedBackend("ida", ida_like_backend_mcp) as pinned:
        results = await asyncio.gather(
            pinned.call_tool("decompile", {"function": "a"}),
            pinned.call_tool("decompile", {"function": "b"}),
            pinned.call_tool("decompile", {"function": "c"}),
        )
        assert len(results) == 3
        assert all(not r.isError for r in results)
```
  </action>
  <verify>
    <automated>pytest mcp-gateway/tests/test_backend_client.py -x --no-header -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest mcp-gateway/tests/test_backend_client.py -x --no-header -q` exits 0
    - `grep -q 'IDA_URL = "http://127.0.0.1:8745/mcp"' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -q 'streamablehttp_client' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -q 'stdio_client' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -q 'asyncio.Lock' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -q 'GHIDRA_INSTALL_DIR' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -q 'AsyncExitStack' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -q 'self.backend_tools' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -q 'session.list_tools' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -c 'localhost' mcp-gateway/src/mcp_gateway/backend/client.py` == 0
    - `grep -c 'tool_map\|call_unified\|translate' mcp-gateway/src/mcp_gateway/backend/client.py` == 0 (no translation layer — D-07)
    - `python -c "from mcp_gateway.backend import PinnedBackend, detect_backend; print(PinnedBackend.__name__)"` exits 0
  </acceptance_criteria>
  <done>PinnedBackend class holds ClientSession + caches tools/list; `call_tool(name, args)` forwards verbatim under asyncio.Lock; 127.0.0.1 literal for IDA; all three transports exercised in tests.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: register_backend_passthrough — dynamic re-registration with native names + schemas</name>
  <files>
    mcp-gateway/src/mcp_gateway/backend/passthrough.py,
    mcp-gateway/tests/test_passthrough_registration.py
  </files>
  <read_first>
    - mcp-gateway/src/mcp_gateway/backend/client.py (Task 1 — PinnedBackend.backend_tools + call_tool)
    - .planning/phases/02-mcp-gateway/02-CONTEXT.md (D-07 pass-through model)
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Open Question: FastMCP dynamic tool add with explicit schema)
    - Existing FastMCP tool registration — grep the installed mcp package:
      `python -c "import mcp.server.fastmcp; import inspect; print(inspect.getsourcefile(mcp.server.fastmcp.FastMCP))"`
      Then inspect `_tool_manager` / `add_tool` / `Tool` to find the right API for passing an explicit JSON Schema.
  </read_first>
  <behavior>
    - `register_backend_passthrough(mcp, pinned)` iterates `pinned.backend_tools` and adds ONE forwarding handler per backend tool to `mcp` under the tool's native `name`, carrying the backend's `inputSchema` and `description`
    - Each registered handler, when called with args dict, awaits `pinned.call_tool(name, args)` and returns the result unchanged
    - If a backend tool name collides with an already-registered gateway-native tool, raise `ValueError("backend tool name collides with native tool: <name>")` — DO NOT silently shadow
    - Returns the count of tools registered (useful for the `[gateway] backend tools registered: N` log line)
    - After registration, `await session.list_tools()` (via `create_connected_server_and_client_session`) includes the backend's native names alongside the 19 native ones
    - Calling a pass-through tool via in-memory client → reaches `pinned.call_tool` with the exact name + args — verified by capturing via a stub `PinnedBackend`
  </behavior>
  <action>
**Step 1 — Inspect FastMCP's dynamic add-tool API.**

Before coding, run inside the executor environment:

```bash
python -c "
import mcp.server.fastmcp as f
from mcp.server.fastmcp.tools import Tool as FastTool
print('FastMCP methods:', [m for m in dir(f.FastMCP) if 'tool' in m.lower()])
print('Tool class:', FastTool)
"
python -c "
from mcp.server.fastmcp.tools import Tool as FastTool
import inspect
print(inspect.signature(FastTool.from_function))
print([m for m in dir(FastTool) if not m.startswith('_')])
"
```

The relevant FastMCP internals in `mcp>=1.27,<1.28` (pinned in pyproject.toml):
- `FastMCP._tool_manager.add_tool(tool: Tool)` — registers a `Tool` instance directly.
- `mcp.server.fastmcp.tools.Tool` accepts `fn`, `name`, `description`, `parameters` (JSON schema dict), `fn_metadata` (pydantic `FuncMetadata`), `is_async`, `context_kwarg`.
- To supply an explicit JSON Schema (from backend's `tools/list` `inputSchema`), construct `FuncMetadata` with an `ArgModelBase` subclass that skips pydantic validation, OR wrap the handler so it accepts `**kwargs` and set `parameters=schema` directly. The latter is simpler: FastMCP serializes `parameters` as the tool's inputSchema; handler receives kwargs unpacked from client args.

If the executor's inspection of the installed SDK disagrees with the above (SDK drift), deviate to the actual API — record the deviation in SUMMARY.md. The PRINCIPLE (register with backend's native name + inputSchema + forwarding handler) is fixed; the exact call is the implementation detail.

**Step 2 — Create `mcp-gateway/src/mcp_gateway/backend/passthrough.py`:**

```python
"""Backend tool pass-through registration (D-07).

Given a live PinnedBackend, iterate its cached `backend_tools` (from tools/list)
and register a forwarding handler on the gateway's FastMCP instance for each,
under the tool's NATIVE name and NATIVE inputSchema.

No translation. No renaming. The gateway is a transparent multiplexer.
"""
from __future__ import annotations
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.tools import Tool as FastTool

from .client import PinnedBackend

log = logging.getLogger("mcp_gateway.backend.passthrough")


def _make_forwarder(pinned: PinnedBackend, tool_name: str):
    """Construct an async handler that forwards (name, kwargs) to pinned.call_tool."""

    async def handler(**kwargs: Any):
        result = await pinned.call_tool(tool_name, kwargs)
        # MCP CallToolResult → MCP tool handler return.
        # FastMCP wraps return values into content blocks; we already have a CallToolResult.
        # Extract content blocks and surface them verbatim. If result.isError, raise so
        # FastMCP emits a tool-error response (D-10 fail loud).
        if getattr(result, "isError", False):
            texts = [
                getattr(b, "text", "") for b in getattr(result, "content", []) or []
            ]
            raise RuntimeError(f"backend tool {tool_name!r} error: {' | '.join(texts)[:512]}")
        # Return raw content blocks (list of TextContent/ImageContent/etc.) — FastMCP
        # passes list[ContentBlock] through as-is in its response.
        return list(getattr(result, "content", []) or [])

    handler.__name__ = f"passthrough__{tool_name.replace('.', '__')}"
    return handler


def register_backend_passthrough(mcp: FastMCP, pinned: PinnedBackend) -> int:
    """Register one forwarding handler per backend tool. Returns the count registered.

    Collisions with gateway-native tool names raise ValueError (D-10 — no silent shadowing).
    """
    # FastMCP internal: list of currently-registered names. If upgraded past 1.27, rewrite
    # using the public API once FastMCP exposes a dynamic-registration / list endpoint.
    existing_names = set(mcp._tool_manager._tools.keys())  # type: ignore[attr-defined]

    registered = 0
    for tool in pinned.backend_tools:
        if tool.name in existing_names:
            raise ValueError(
                f"backend tool name collides with gateway-native tool: {tool.name!r}"
            )
        handler = _make_forwarder(pinned, tool.name)
        # Build a FastTool directly so we can supply an explicit inputSchema (parameters).
        # FastMCP normally infers parameters from the function signature; for pass-through
        # we want the backend's exact schema, not one derived from `**kwargs`.
        fast_tool = FastTool(
            fn=handler,
            name=tool.name,
            description=(tool.description or f"[passthrough to {pinned.backend}] {tool.name}"),
            parameters=dict(tool.inputSchema or {"type": "object", "properties": {}}),
            fn_metadata=None,  # skip pydantic validation — schema is authoritative
            is_async=True,
            context_kwarg=None,
        )
        mcp._tool_manager._tools[tool.name] = fast_tool  # type: ignore[attr-defined]
        registered += 1

    log.info(
        "[gateway] backend tools registered: %d (backend=%s)", registered, pinned.backend
    )
    return registered
```

**IMPORTANT — SDK-drift escape hatch:** If `FastTool(fn_metadata=None)` fails at runtime (some 1.27.x builds require a `FuncMetadata`), fall back to:

```python
from mcp.server.fastmcp.utilities.func_metadata import func_metadata
...
fn_metadata=func_metadata(handler, skip_names=[])
```

and let FastMCP infer from `**kwargs`. The tool's `parameters=` still overrides inputSchema in the tools/list response. Record this deviation in SUMMARY.md if needed.

**Step 3 — Create `mcp-gateway/tests/test_passthrough_registration.py`:**

```python
"""Tests for backend tool pass-through registration (D-07)."""
from __future__ import annotations
import asyncio

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import Tool

from mcp_gateway.backend.passthrough import register_backend_passthrough
from mcp_gateway.tools import register_all_tools


class _StubPinned:
    """Just enough of PinnedBackend to satisfy passthrough.register_backend_passthrough."""

    def __init__(self, backend: str, backend_tools: list[Tool]):
        self.backend = backend
        self.backend_tools = backend_tools
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        # Return something that looks enough like a CallToolResult for the forwarder.
        from mcp.types import CallToolResult, TextContent
        return CallToolResult(
            content=[TextContent(type="text", text=f"ok:{name}:{sorted(args.items())}")],
            isError=False,
        )


def _tool_rec(name: str, schema: dict, description: str = "") -> Tool:
    return Tool(name=name, description=description, inputSchema=schema)


@pytest.fixture
def gateway_mcp_with_natives() -> FastMCP:
    """Gateway FastMCP pre-loaded with the 19 Plan 02 native tools."""
    m = FastMCP("mare-gateway-test", stateless_http=True)
    register_all_tools(m)
    return m


# -------- happy path: Ghidra-style tools with session_id in schema --------

def test_register_registers_all_backend_tools(gateway_mcp_with_natives):
    backend_tools = [
        _tool_rec(
            "program.open",
            {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        ),
        _tool_rec(
            "function.list",
            {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "offset": {"type": "integer", "default": 0},
                    "limit": {"type": "integer", "default": 100},
                },
                "required": ["session_id"],
            },
        ),
        _tool_rec(
            "decomp.function",
            {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "function_start": {"type": "string"},
                },
                "required": ["session_id", "function_start"],
            },
        ),
    ]
    pinned = _StubPinned("ghidra", backend_tools)
    n = register_backend_passthrough(gateway_mcp_with_natives, pinned)
    assert n == 3


@pytest.mark.asyncio
async def test_tools_list_shows_native_plus_backend(gateway_mcp_with_natives):
    backend_tools = [
        _tool_rec("program.open", {"type": "object", "properties": {"path": {"type": "string"}}}),
        _tool_rec("function.list", {"type": "object", "properties": {"session_id": {"type": "string"}}}),
    ]
    pinned = _StubPinned("ghidra", backend_tools)
    register_backend_passthrough(gateway_mcp_with_natives, pinned)

    async with create_connected_server_and_client_session(gateway_mcp_with_natives._mcp_server) as session:
        resp = await session.list_tools()
        names = {t.name for t in resp.tools}
    assert "program.open" in names      # native backend name (dotted, unchanged)
    assert "function.list" in names     # native backend name
    assert "get_active_backend" in names  # gateway-native (Plan 02)
    assert "run_triage" in names          # gateway-native (Plan 02)
    # No translated names (D-07 — verify we did NOT introduce `decompile` / `list_functions`)
    assert "decompile" not in names
    assert "list_functions" not in names


@pytest.mark.asyncio
async def test_calling_passthrough_tool_forwards_to_backend(gateway_mcp_with_natives):
    backend_tools = [
        _tool_rec(
            "function.list",
            {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        ),
    ]
    pinned = _StubPinned("ghidra", backend_tools)
    register_backend_passthrough(gateway_mcp_with_natives, pinned)

    async with create_connected_server_and_client_session(gateway_mcp_with_natives._mcp_server) as session:
        result = await session.call_tool("function.list", {"session_id": "sess-xyz"})
    assert not result.isError
    # The stub captured the call verbatim — no translation, no arg rewriting.
    assert pinned.calls == [("function.list", {"session_id": "sess-xyz"})]


def test_inputSchema_is_backend_schema_not_inferred(gateway_mcp_with_natives):
    backend_schema = {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "from program.open"},
            "function_start": {"type": "string"},
        },
        "required": ["session_id", "function_start"],
    }
    backend_tools = [_tool_rec("decomp.function", backend_schema)]
    pinned = _StubPinned("ghidra", backend_tools)
    register_backend_passthrough(gateway_mcp_with_natives, pinned)

    # FastMCP internal — if upgraded past 1.27, rewrite using create_connected_server_and_client_session
    # and inspect `tools/list` response for inputSchema.
    fast_tool = gateway_mcp_with_natives._tool_manager._tools["decomp.function"]
    assert fast_tool.parameters["required"] == ["session_id", "function_start"]


# -------- collision with native tool --------

def test_collision_with_native_tool_raises(gateway_mcp_with_natives):
    # `get_active_backend` is registered by Plan 02 as a native tool.
    bad_tools = [_tool_rec("get_active_backend", {"type": "object"})]
    pinned = _StubPinned("ida", bad_tools)
    with pytest.raises(ValueError, match="collides with gateway-native"):
        register_backend_passthrough(gateway_mcp_with_natives, pinned)


# -------- error forwarding --------

class _ErrorPinned(_StubPinned):
    async def call_tool(self, name, args):
        from mcp.types import CallToolResult, TextContent
        return CallToolResult(
            content=[TextContent(type="text", text=f"boom {name}")],
            isError=True,
        )


@pytest.mark.asyncio
async def test_backend_error_surfaces_as_tool_error(gateway_mcp_with_natives):
    pinned = _ErrorPinned("ida", [_tool_rec("decompile", {"type": "object"})])
    register_backend_passthrough(gateway_mcp_with_natives, pinned)

    async with create_connected_server_and_client_session(gateway_mcp_with_natives._mcp_server) as session:
        result = await session.call_tool("decompile", {"function": "main"})
    assert result.isError is True
```
  </action>
  <verify>
    <automated>pytest mcp-gateway/tests/test_passthrough_registration.py -x --no-header -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest mcp-gateway/tests/test_passthrough_registration.py -x --no-header -q` exits 0
    - `grep -q 'def register_backend_passthrough' mcp-gateway/src/mcp_gateway/backend/passthrough.py`
    - `grep -q 'pinned.backend_tools' mcp-gateway/src/mcp_gateway/backend/passthrough.py`
    - `grep -q 'collides with gateway-native' mcp-gateway/src/mcp_gateway/backend/passthrough.py`
    - `grep -c 'tool_map\|translate\|call_unified' mcp-gateway/src/mcp_gateway/backend/passthrough.py` == 0 (D-07 — no translation)
    - `python -c "from mcp_gateway.backend import register_backend_passthrough; print('ok')"` exits 0
  </acceptance_criteria>
  <done>Backend tools re-registered on gateway FastMCP under their native names + native inputSchemas; collisions fail loud; 6 tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Wire PinnedBackend + passthrough into app.py lifespan; verify tools/list end-to-end</name>
  <files>
    mcp-gateway/src/mcp_gateway/app.py,
    mcp-gateway/tests/test_passthrough_registration.py
  </files>
  <read_first>
    - mcp-gateway/src/mcp_gateway/app.py (Plan 02 left lifespan entering only session_manager.run; backend detected but no PinnedBackend entered)
    - mcp-gateway/src/mcp_gateway/backend/client.py (Task 1 — PinnedBackend)
    - mcp-gateway/src/mcp_gateway/backend/passthrough.py (Task 2 — register_backend_passthrough)
    - mcp-gateway/src/mcp_gateway/session_state.py (Plan 01 — PINNED_BACKEND module attribute)
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Code Example 1 full app.py skeleton shows the lifespan pattern)
  </read_first>
  <behavior>
    - `build_app()` lifespan enters `PinnedBackend(backend_name)` BEFORE `mcp.session_manager.run()` and BEFORE yielding
    - Inside the PinnedBackend context, `session_state.PINNED_BACKEND = pinned`, then `register_backend_passthrough(mcp, pinned)` is called
    - On lifespan exit, `session_state.PINNED_BACKEND` is reset to None
    - When `MCP_GATEWAY_SKIP_BACKEND=1`, NO PinnedBackend entered (test mode) — `session_state.PINNED_BACKEND` stays None and passthrough registration is skipped
    - Startup log order: `[gateway] backend: <name>` → `[gateway] backend session initialized: <name> (N tools)` → `[gateway] backend tools registered: N` → `[gateway] ready on ...`
    - Existing tests from Plan 01+02 remain green (regression)
    - Integration test at HTTP layer: with a stub PinnedBackend injected, a Streamable HTTP client sees `tools/list` including backend tools, and calling one reaches the stub
  </behavior>
  <action>
**Step 1 — Update `mcp-gateway/src/mcp_gateway/app.py`** to enter PinnedBackend + register passthrough inside the lifespan. Replace the existing `build_app()` function with:

```python
"""Starlette application factory + FastMCP integration + middleware wiring + backend lifespan.

GW-01 (FastMCP Streamable HTTP) + GW-03 (backend pass-through via PinnedBackend).
"""
from __future__ import annotations
import contextlib
import logging
import os

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from mcp.server.fastmcp import FastMCP

from .auth import BearerAuthMiddleware, OriginMiddleware, load_or_generate_token
from .backend.detect import detect_backend
from .backend.client import PinnedBackend
from .backend.passthrough import register_backend_passthrough
from .tools import register_all_tools
from . import session_state

log = logging.getLogger("mcp_gateway")

_MCP_INSTANCE: FastMCP | None = None


def get_mcp() -> FastMCP:
    """Access the module-level FastMCP instance."""
    global _MCP_INSTANCE
    if _MCP_INSTANCE is None:
        _MCP_INSTANCE = FastMCP("mare-gateway", stateless_http=True, json_response=True)
    return _MCP_INSTANCE


async def _healthz(request):
    return JSONResponse({"ok": True})


async def _upload_placeholder(request):
    """Placeholder — replaced by Plan 04's streaming handler."""
    return JSONResponse(
        {"error": "upload handler not yet installed", "plan": "Plan 04"},
        status_code=501,
    )


def build_app() -> Starlette:
    token = load_or_generate_token()

    skip_backend = os.environ.get("MCP_GATEWAY_SKIP_BACKEND") == "1"
    if skip_backend:
        log.warning("[gateway] MCP_GATEWAY_SKIP_BACKEND=1 — backend detection bypassed (test mode)")
        backend_name: str | None = None
    else:
        backend_name = detect_backend()
        log.info("[gateway] backend: %s", backend_name)

    mcp = get_mcp()
    register_all_tools(mcp)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        if backend_name is None:
            # Test/escape-hatch path — no backend, no passthrough.
            try:
                async with mcp.session_manager.run():
                    log.info(
                        "[gateway] ready on %s:%s (no backend)",
                        os.environ.get("MCP_GATEWAY_HOST", "127.0.0.1"),
                        os.environ.get("MCP_GATEWAY_PORT", "8080"),
                    )
                    yield
            finally:
                session_state.PINNED_BACKEND = None
            return

        # Real backend path (D-09: pinned for lifetime, D-10: fail loud on crash, D-07: passthrough)
        async with PinnedBackend(backend_name) as pinned:
            session_state.PINNED_BACKEND = pinned
            count = register_backend_passthrough(mcp, pinned)
            try:
                async with mcp.session_manager.run():
                    log.info(
                        "[gateway] ready on %s:%s",
                        os.environ.get("MCP_GATEWAY_HOST", "127.0.0.1"),
                        os.environ.get("MCP_GATEWAY_PORT", "8080"),
                    )
                    log.info(
                        "[gateway] token file: %s",
                        os.environ.get("MCP_GATEWAY_TOKEN_FILE", "/agent/.mcp-gateway-token"),
                    )
                    log.info("[gateway] backend tools registered: %d", count)
                    yield
            finally:
                session_state.PINNED_BACKEND = None

    app = Starlette(
        routes=[
            Route("/healthz", _healthz, methods=["GET"]),
            Route("/upload", _upload_placeholder, methods=["POST"]),
            Mount("/mcp", app=mcp.streamable_http_app()),
        ],
        lifespan=lifespan,
    )
    # Starlette runs middleware last-added first. Add Bearer last (innermost → runs first),
    # then Origin (outermost → runs first on DNS-rebind check).
    app.add_middleware(BearerAuthMiddleware, token=token)
    app.add_middleware(OriginMiddleware)
    return app
```

**Step 2 — Append integration tests to `mcp-gateway/tests/test_passthrough_registration.py`:**

```python
# ---------- lifespan integration: get_active_backend reflects PINNED_BACKEND ----------

@pytest.mark.asyncio
async def test_get_active_backend_reflects_pinned_backend(monkeypatch, gateway_mcp_with_natives):
    """When session_state.PINNED_BACKEND is set, get_active_backend returns its name."""
    from mcp_gateway import session_state

    pinned = _StubPinned("ghidra", [])
    monkeypatch.setattr(session_state, "PINNED_BACKEND", pinned)

    async with create_connected_server_and_client_session(gateway_mcp_with_natives._mcp_server) as session:
        result = await session.call_tool("get_active_backend", {})
    assert not result.isError
    # Surface as text content; parse and check backend name
    import json
    text = next(b.text for b in result.content if getattr(b, "text", None))
    payload = json.loads(text)
    assert payload["backend"] == "ghidra"


@pytest.mark.asyncio
async def test_get_active_backend_reports_none_when_unset(monkeypatch, gateway_mcp_with_natives):
    from mcp_gateway import session_state
    monkeypatch.setattr(session_state, "PINNED_BACKEND", None)

    async with create_connected_server_and_client_session(gateway_mcp_with_natives._mcp_server) as session:
        result = await session.call_tool("get_active_backend", {})
    import json
    text = next(b.text for b in result.content if getattr(b, "text", None))
    payload = json.loads(text)
    assert payload["backend"] == "none"


def test_build_app_with_skip_backend_works(monkeypatch, tmp_path):
    """Smoke: with MCP_GATEWAY_SKIP_BACKEND=1 build_app() returns a Starlette app."""
    monkeypatch.setenv("MCP_GATEWAY_SKIP_BACKEND", "1")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "t")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / "tok"))
    # Reset module singleton so register_all_tools does not double-register on reuse.
    from mcp_gateway import app as app_mod
    monkeypatch.setattr(app_mod, "_MCP_INSTANCE", None)
    application = app_mod.build_app()
    assert application is not None
```
  </action>
  <verify>
    <automated>pytest mcp-gateway/tests/ -x --no-header -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest mcp-gateway/tests/ -x --no-header -q` exits 0 (full suite green, no regression of Plan 01/02 tests)
    - `grep -q 'async with PinnedBackend' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'register_backend_passthrough(mcp, pinned)' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'session_state.PINNED_BACKEND = pinned' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'session_state.PINNED_BACKEND = None' mcp-gateway/src/mcp_gateway/app.py` (reset on exit)
    - `grep -q 'MCP_GATEWAY_SKIP_BACKEND' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'from .backend.client import PinnedBackend' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'from .backend.passthrough import register_backend_passthrough' mcp-gateway/src/mcp_gateway/app.py`
    - `python -c "import os; os.environ['MCP_GATEWAY_SKIP_BACKEND']='1'; os.environ['MCP_GATEWAY_TOKEN']='t'; os.environ['MCP_GATEWAY_TOKEN_FILE']='/tmp/.tok'; from mcp_gateway.app import build_app; build_app()"` exits 0
  </acceptance_criteria>
  <done>PinnedBackend entered inside the Starlette lifespan; `session_state.PINNED_BACKEND` set for the gateway's lifetime; `register_backend_passthrough` re-exposes backend tools under native names; `get_active_backend` reflects the pinned backend; full test suite green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| gateway process → idalib-mcp daemon | Trusted (local loopback, Phase 1 already validates) but use 127.0.0.1 literal (Pitfall 3) |
| gateway process → BN/Ghidra stdio subprocess | Trusted script path (hardcoded in client.py); argv is fixed, not user-controlled |
| Pass-through tool args (client → gateway → backend) | Untrusted at the gateway edge (bearer-validated already); forwarded verbatim to backend — the backend's own input validation is the inner trust boundary |
| Backend result → MCP tool response | Passed through; backend is trusted not to emit hostile payloads |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-02-SUBPROC | Tampering / RCE | stdio subprocess spawn (BN, Ghidra) | HIGH | mitigate | Task 1: `StdioServerParameters(command="python3", args=[LITERAL_SCRIPT_PATH])`. Script paths are hardcoded constants, NOT derived from user input. No shell interpolation. |
| T-02-AUTH | Spoofing | Backend ClientSession | LOW | accept | Backends run on localhost loopback or as direct subprocess; no network exposure. Gateway process owns both sides. |
| T-02-NET | Info Disclosure (IPv6 hang via `localhost`) | IDA Streamable HTTP client | LOW | mitigate | Task 1 constant `IDA_URL = "http://127.0.0.1:8745/mcp"` literal (Pitfall 3 in RESEARCH.md). Acceptance criteria greps absence of `localhost`. |
| T-02-PASSTHROUGH-ARG | Tampering | Backend tools receiving arbitrary args | MEDIUM | accept | Under D-07 pass-through, gateway does NOT validate backend-tool args. The backend owns its own input schema and runs its own validation. This matches the declared trust boundary (bearer auth at the gateway edge; backend handles inner validation). Gateway-native tools (Plan 02) still do their own path-traversal etc. checks (T-02-PATHTRAVERSAL). |
| T-02-SILENT-FALLBACK | Availability/Integrity | backend crash | HIGH | mitigate | Task 1: `PinnedBackend.__aenter__` re-raises on init failure (D-10). The `lifespan` does NOT try the next-priority backend. Errors surface as MCP error to the client. Backend-reported errors in `call_tool` are re-raised by the passthrough forwarder so FastMCP emits a tool-error response. |
| T-02-SUBPROC-DEADLOCK | DoS (backend hang) | stdio subprocess stderr | MEDIUM | mitigate | Task 1: uses SDK's `stdio_client` which reads stdout in background task and discards stderr (Pitfall 4 in RESEARCH). Do NOT wrap with extra I/O. |
| T-02-TOOL-COLLISION | Integrity | gateway-native vs backend tool name clash | MEDIUM | mitigate | Task 2: `register_backend_passthrough` raises `ValueError` on collision — no silent shadowing. Currently no collisions anticipated (backend tools mostly dotted names; native tools are single verbs), but the guard is in place. |
| T-02-TOKENLEAK | Info Disclosure | — | — | — | Not applicable (Plan 01 handles) |
| T-02-UPLOAD | DoS | — | — | transfer | Plan 04 |
</threat_model>

<verification>
After all 3 tasks:
1. Full test suite: `pytest mcp-gateway/tests/ -x --no-header -q` — exits 0 (Plan 01 + 02 + 03 combined, ~45+ tests)
2. `ruff check mcp-gateway/src/ mcp-gateway/tests/` clean
3. Import graph: `python -c "from mcp_gateway.app import build_app; from mcp_gateway.backend import PinnedBackend, detect_backend, register_backend_passthrough; print('imports ok')"` exits 0
4. Key security/correctness greps:
   - `grep -c 'localhost' mcp-gateway/src/mcp_gateway/backend/client.py` == 0
   - `grep -c 'shell=True' mcp-gateway/src/mcp_gateway/backend/client.py` == 0
   - `grep -c '127.0.0.1' mcp-gateway/src/mcp_gateway/backend/client.py` >= 1
   - `grep -rnc 'tool_map\|call_unified\|translate' mcp-gateway/src/mcp_gateway/backend/ | awk -F: '$2>0{exit 1}'` — no translation-layer artifacts anywhere (D-07)
   - `test ! -f mcp-gateway/src/mcp_gateway/tools/disasm.py` — disasm module does not exist (D-07)
   - `test ! -f mcp-gateway/src/mcp_gateway/backend/tool_map.py` — tool_map module does not exist (D-07)
5. End-to-end: with `MCP_GATEWAY_SKIP_BACKEND=1` + a stub PinnedBackend injected via monkeypatch, `tools/list` over in-memory transport shows both native (19) and backend (N) tools.
</verification>

<success_criteria>
- GW-03 met: client has one endpoint; tools/list includes gateway-native + backend-native tools; calling backend tools reaches the backend via PinnedBackend.call_tool
- PinnedBackend enters inside Starlette lifespan; `session_state.PINNED_BACKEND` is set for the gateway lifetime
- `register_backend_passthrough` enumerates backend's tools/list and registers each on the gateway FastMCP under the native name + native inputSchema
- asyncio.Lock serializes concurrent call_tool invocations (Open Q2 resolved)
- D-06 (gateway as MCP client): `ClientSession` wraps real backend transport; no logic re-implementation
- D-07 (pass-through, not translation): no tool renaming, no arg rewriting, no session management — the backend's own tool surface is exposed
- D-09 (pinned): backend chosen ONCE at lifespan enter; no mid-session switching
- D-10 (fail loud): PinnedBackend.__aenter__ re-raises on init failure; registration collisions raise; backend tool errors surface as MCP tool errors
- 127.0.0.1 literal used for IDA (Pitfall 3 avoided)
- `get_active_backend` reflects the pinned backend, letting clients/skills branch on backend
- No regression: all Plan 01 and Plan 02 tests still green
</success_criteria>

<output>
After completion, create `.planning/phases/02-mcp-gateway/02-03-SUMMARY.md`.
Include:
- Transport matrix: ida → Streamable HTTP 127.0.0.1:8745; bn → stdio subprocess; ghidra → stdio subprocess with GHIDRA_INSTALL_DIR
- Pass-through counts observed for each backend (from `[gateway] backend tools registered: N` log line during smoke)
- Any FastMCP SDK-drift deviations encountered in Task 2 (Tool/FuncMetadata API)
- Test counts: test_backend_client.py (~10), test_passthrough_registration.py (~9), full suite running green
- Threat mitigations: T-02-SUBPROC (argv-only), T-02-SILENT-FALLBACK (D-10 fail-loud), T-02-NET (127.0.0.1 literal), T-02-TOOL-COLLISION (ValueError on native-vs-backend name clash)
- Handoff to Plan 04: app.py still has `/upload` placeholder returning 501 — Plan 04 replaces it
- Handoff to Plan 05: backend subprocess paths (BN, Ghidra) expected at `/agent/mcp/...` — Plan 05's Dockerfile must ensure these are present; smoke test should verify `tools/list` against the real chosen backend includes a known native tool name (e.g., `program.open` for Ghidra, `decompile` for IDA)
</output>
