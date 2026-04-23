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
  - mcp-gateway/src/mcp_gateway/backend/tool_map.py
  - mcp-gateway/src/mcp_gateway/backend/__init__.py
  - mcp-gateway/src/mcp_gateway/app.py
  - mcp-gateway/src/mcp_gateway/tools/disasm.py
  - mcp-gateway/tests/test_tool_map.py
  - mcp-gateway/tests/test_tool_routing.py
autonomous: true
requirements:
  - GW-03
tags:
  - mcp
  - backend
  - routing
  - python

must_haves:
  truths:
    - "`PinnedBackend(backend_name)` as async context manager establishes a ClientSession to the correct backend"
    - "For backend='ida': client connects to `http://127.0.0.1:8745/mcp` via streamablehttp_client"
    - "For backend='bn': client spawns `python3 /agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py` via stdio_client"
    - "For backend='ghidra': client spawns `python3 /agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py` via stdio_client with GHIDRA_INSTALL_DIR env"
    - "`tool_map.translate(unified='decompile', backend='ida')` returns backend tool name + arg shape for IDA"
    - "`tool_map.translate(unified='list_functions', backend='ghidra')` returns Ghidra's `function.list` equivalent"
    - "`PinnedBackend.call_unified(unified_name, args)` serializes calls via `asyncio.Lock` (RESEARCH Open Q2)"
    - "Disassembler tool `decompile` successfully forwards to fake backend in TestClient with `PINNED_BACKEND` set"
    - "Gateway startup log emits `[gateway] backend: <name>` line before `[gateway] ready`"
    - "Backend subprocess crash raises clear MCP error (D-10 fail loud, not silent fallback)"
  artifacts:
    - path: "mcp-gateway/src/mcp_gateway/backend/client.py"
      provides: "PinnedBackend (AsyncExitStack-based; IDA/BN/Ghidra support; call_unified method)"
      exports: ["PinnedBackend"]
    - path: "mcp-gateway/src/mcp_gateway/backend/tool_map.py"
      provides: "Unified-name → backend-tool-name mapping per backend"
      exports: ["translate", "TOOL_MAP"]
    - path: "mcp-gateway/src/mcp_gateway/backend/__init__.py"
      provides: "Re-exports detect_backend + PinnedBackend"
      exports: ["detect_backend", "PinnedBackend"]
  key_links:
    - from: "mcp-gateway/src/mcp_gateway/backend/client.py::PinnedBackend.__aenter__"
      to: "streamablehttp_client OR stdio_client"
      via: "AsyncExitStack + ClientSession"
      pattern: "AsyncExitStack.*ClientSession"
    - from: "mcp-gateway/src/mcp_gateway/app.py::lifespan"
      to: "PinnedBackend context manager"
      via: "nested async with inside Starlette lifespan"
      pattern: "async with PinnedBackend"
    - from: "mcp-gateway/src/mcp_gateway/tools/disasm.py"
      to: "session_state.PINNED_BACKEND.call_unified"
      via: "unified → backend tool name via tool_map.translate"
      pattern: "call_unified"
---

<objective>
Implement the backend-as-MCP-client layer: `PinnedBackend` class that holds a long-lived `ClientSession` to the selected disassembler (IDA via Streamable HTTP, BN/Ghidra via stdio subprocess), plus a `tool_map` translation layer that converts unified verb-first names (`decompile`, `list_functions`, `get_xrefs`) into backend-specific tool names and argument shapes. Wire `PinnedBackend` into `app.py`'s lifespan so the gateway's disassembler tools transparently delegate to the active backend.

Purpose: Fulfills GW-03 — a single unified interface to clients regardless of which of the three backends is active. Plan 02 left `session_state.PINNED_BACKEND` as `None` and the disasm tools returning a stub; this plan completes the connection.

Output: `decompile`, `list_functions`, `get_xrefs` MCP tool calls reach the backend's equivalent tool and return its result under the unified name. IDA backend uses Streamable HTTP client (no re-spawning — idalib-mcp already runs from Phase 1). BN and Ghidra backends get a persistent stdio subprocess spawned inside the gateway's lifespan.
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
from mcp_gateway.tools.disasm import ...  # Plan 02 left disasm tools returning stub when PINNED_BACKEND is None
from mcp_gateway.app import build_app, get_mcp  # lifespan is where PinnedBackend gets entered
```

<!-- From MCP Python SDK -->
```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client   # for IDA
from mcp.client.stdio import stdio_client, StdioServerParameters   # for BN/Ghidra
from contextlib import AsyncExitStack
```

<!-- Phase 1 fact: idalib-mcp already runs as a daemon on 127.0.0.1:8745/mcp, started by agent-entrypoint.sh lines 269-292 -->

<!-- Tool-name mapping (from RESEARCH.md § Tool Surface Design → Disassembler tools table) -->
| Unified      | IDA             | BN (verify at spawn)  | Ghidra            |
| ------------ | --------------- | --------------------- | ----------------- |
| decompile    | decompile       | decompile             | decomp.function   |
| list_functions | list_funcs    | list_functions        | function.list     |
| get_xrefs    | xrefs_to        | get_xrefs             | reference.to      |
<!-- NOTE: exact BN tool names should be verified by grepping /agent/mcp/binary-ninja-headless-mcp/ during execution (RESEARCH A5). See Task 1 instructions. -->
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: tool_map module + unit tests for the unified→backend translation</name>
  <files>
    mcp-gateway/src/mcp_gateway/backend/tool_map.py,
    mcp-gateway/tests/test_tool_map.py
  </files>
  <read_first>
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Tool Surface Design → Disassembler tools table; § Assumptions Log A1, A2, A5)
    - mcp/ghidra-headless-mcp/ghidra_headless_mcp/server.py (grep for `@tool\|register_tool\|tool_name` — find the actual tool names Ghidra exposes)
    - mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py (if present — grep for tool registrations; record actual names)
    - .planning/phases/02-mcp-gateway/02-CONTEXT.md (D-03 verb-first naming; D-07 unified re-exposure)
  </read_first>
  <behavior>
    - `translate(unified="decompile", backend="ida")` returns `("decompile", args_passthrough)` — IDA's tool is already named `decompile`
    - `translate(unified="decompile", backend="ghidra")` returns `("decomp.function", args_passthrough)`
    - `translate(unified="list_functions", backend="ida")` returns `("list_funcs", args_passthrough)`
    - `translate(unified="list_functions", backend="ghidra")` returns `("function.list", args_passthrough)`
    - `translate(unified="get_xrefs", backend="ida")` returns `("xrefs_to", args_passthrough)`
    - `translate(unified="get_xrefs", backend="ghidra")` returns `("reference.to", args_passthrough)`
    - `translate(unified="decompile", backend="unknown")` raises `KeyError`
    - `translate(unified="bogus", backend="ida")` raises `KeyError`
    - For BN backend: verify exact names by grepping `/agent/mcp/binary-ninja-headless-mcp/` during execution; record findings as comments in tool_map.py. If file not present locally, use placeholder names matching the unified names (BN is a vendored submodule likely missing from devlaptop)
  </behavior>
  <action>
**Step 1 — Verify backend tool names by grep:**

Before writing tool_map.py, run (manually if needed, inline in the task):
```bash
grep -rn '@mcp\.tool\|\.tool_name\|tool_name=\|register_tool' mcp/ghidra-headless-mcp/ 2>/dev/null | head -30
grep -rn '@mcp\.tool\|\.tool_name\|tool_name=\|register_tool' mcp/binary-ninja-headless-mcp/ 2>/dev/null | head -30
```

Record the actual tool name strings found. If BN submodule is missing from the repo locally, leave the BN column with the unified names as fallback — the executor running this plan inside the container has the submodule and MUST re-run the grep and update the mapping. Add a `# TODO(Plan 03 container-side validation):` comment next to the BN row.

**Step 2 — Create `mcp-gateway/src/mcp_gateway/backend/tool_map.py`:**

```python
"""Unified-name → backend-tool-name mapping for the 3 disassembler unified tools.

Research: .planning/phases/02-mcp-gateway/02-RESEARCH.md § Tool Surface Design → Disassembler tools.
D-07: client only ever sees unified verb-first names; backend-specific names are hidden.

NOTE: BN tool names should be verified by grepping the vendored submodule at
`/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py` inside the
container. Placeholder values below use the unified name as a fallback — the
installer (Plan 05) verifies by running `tools/list` against the BN backend at
container startup and logs a warning if any unified tool maps to a missing backend tool.
"""
from __future__ import annotations
from typing import Callable

# Mapping layout: { unified_name: { backend: (backend_tool_name, args_transform) } }
# args_transform is a callable that maps unified args dict → backend args dict.
# In Phase 2 all three unified tools have the same arg keys as their backend
# equivalents, so args_transform is identity. v2 (DIS-V2-01) will add real shape
# normalization.

_identity: Callable[[dict], dict] = lambda args: dict(args)

TOOL_MAP: dict[str, dict[str, tuple[str, Callable[[dict], dict]]]] = {
    "decompile": {
        "ida":    ("decompile",       _identity),
        # TODO(Plan 03 container-side validation): verify BN tool name by grepping
        # /agent/mcp/binary-ninja-headless-mcp/ inside the container.
        "bn":     ("decompile",       _identity),
        "ghidra": ("decomp.function", _identity),
    },
    "list_functions": {
        "ida":    ("list_funcs",      _identity),
        # TODO(Plan 03 container-side validation): verify BN tool name
        "bn":     ("list_functions",  _identity),
        "ghidra": ("function.list",   _identity),
    },
    "get_xrefs": {
        "ida":    ("xrefs_to",        _identity),
        # TODO(Plan 03 container-side validation): verify BN tool name
        "bn":     ("get_xrefs",       _identity),
        "ghidra": ("reference.to",    _identity),
    },
}


def translate(unified: str, backend: str, args: dict | None = None) -> tuple[str, dict]:
    """Convert a unified tool invocation to the backend's (tool_name, args) tuple.

    Raises KeyError if the unified name is unknown or the backend has no mapping.
    """
    if unified not in TOOL_MAP:
        raise KeyError(f"unknown unified tool: {unified!r}")
    per_backend = TOOL_MAP[unified]
    if backend not in per_backend:
        raise KeyError(f"backend {backend!r} not supported for unified tool {unified!r}")
    backend_tool, xform = per_backend[backend]
    return backend_tool, xform(args or {})


def supported_unified_tools() -> list[str]:
    """Return the list of unified disassembler tool names currently exposed."""
    return sorted(TOOL_MAP.keys())


def validate_backend_support(backend: str) -> list[str]:
    """Return unified tools that have a mapping for the given backend."""
    return sorted(name for name, per in TOOL_MAP.items() if backend in per)
```

**Step 3 — Create `mcp-gateway/tests/test_tool_map.py`:**

```python
"""Tests for backend/tool_map.py translation layer. Maps to VALIDATION.md GW-03 unit row."""
from __future__ import annotations

import pytest

from mcp_gateway.backend.tool_map import (
    TOOL_MAP,
    supported_unified_tools,
    translate,
    validate_backend_support,
)


# --------- translate() ---------

@pytest.mark.parametrize(
    "unified,backend,expected_tool",
    [
        ("decompile",      "ida",    "decompile"),
        ("decompile",      "ghidra", "decomp.function"),
        ("list_functions", "ida",    "list_funcs"),
        ("list_functions", "ghidra", "function.list"),
        ("get_xrefs",      "ida",    "xrefs_to"),
        ("get_xrefs",      "ghidra", "reference.to"),
    ],
)
def test_translate_returns_backend_tool(unified, backend, expected_tool):
    tool, args = translate(unified, backend, {"foo": "bar"})
    assert tool == expected_tool
    assert args == {"foo": "bar"}  # identity transform in Phase 2


def test_translate_unknown_unified_raises():
    with pytest.raises(KeyError, match="unknown unified tool"):
        translate("not_a_tool", "ida")


def test_translate_unknown_backend_raises():
    with pytest.raises(KeyError, match="backend 'not_a_backend'"):
        translate("decompile", "not_a_backend")


def test_translate_empty_args_default():
    tool, args = translate("decompile", "ida")
    assert args == {}


# --------- supported_unified_tools + validate_backend_support ---------

def test_supported_unified_tools_are_the_3_disasm_tools():
    assert set(supported_unified_tools()) == {"decompile", "list_functions", "get_xrefs"}


def test_all_three_backends_supported_for_every_unified_tool():
    for unified in supported_unified_tools():
        backends = set(TOOL_MAP[unified].keys())
        assert backends == {"ida", "bn", "ghidra"}, f"{unified} missing a backend"


def test_validate_backend_support_ida():
    assert validate_backend_support("ida") == ["decompile", "get_xrefs", "list_functions"]


def test_validate_backend_support_missing_backend():
    assert validate_backend_support("qemu") == []
```
  </action>
  <verify>
    <automated>pytest mcp-gateway/tests/test_tool_map.py -x --no-header -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest mcp-gateway/tests/test_tool_map.py -x --no-header -q` exits 0
    - `grep -q 'TOOL_MAP' mcp-gateway/src/mcp_gateway/backend/tool_map.py`
    - `grep -q '"decompile".*"decomp.function"' mcp-gateway/src/mcp_gateway/backend/tool_map.py || grep -qE '"ghidra":.*"decomp\.function"' mcp-gateway/src/mcp_gateway/backend/tool_map.py`
    - `grep -q '"list_funcs"' mcp-gateway/src/mcp_gateway/backend/tool_map.py`
    - `grep -q '"reference.to"' mcp-gateway/src/mcp_gateway/backend/tool_map.py`
    - `grep -q 'def translate' mcp-gateway/src/mcp_gateway/backend/tool_map.py`
    - `grep -q 'TODO(Plan 03 container-side validation)' mcp-gateway/src/mcp_gateway/backend/tool_map.py` (BN verification flag)
    - `python -c "from mcp_gateway.backend.tool_map import translate; t,a = translate('decompile', 'ghidra'); assert t == 'decomp.function'"` exits 0
  </acceptance_criteria>
  <done>tool_map.py exports translate() + TOOL_MAP; 9 tests green; BN names flagged as TODO for container-side validation.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: PinnedBackend client (IDA http, BN/Ghidra stdio) + test_tool_routing with fake backend</name>
  <files>
    mcp-gateway/src/mcp_gateway/backend/client.py,
    mcp-gateway/src/mcp_gateway/backend/__init__.py,
    mcp-gateway/tests/test_tool_routing.py
  </files>
  <read_first>
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Pattern 2 Backend-as-Client; § Pitfall 3 localhost IPv6; § Pitfall 4 stdio deadlock; § Pitfall 5 Accept header; § Open Questions #2 asyncio.Lock serialization)
    - .planning/phases/02-mcp-gateway/02-CONTEXT.md (D-06 MCP client not re-implementing; D-07 unified re-exposure; D-09 pinned; D-10 fail loud)
    - .planning/phases/02-mcp-gateway/02-01-package-scaffold-and-auth-PLAN.md (backend/__init__.py currently re-exports detect_backend only)
    - mcp-gateway/src/mcp_gateway/backend/tool_map.py (Task 1 — translate())
  </read_first>
  <behavior>
    - `PinnedBackend("ida")` as `async with` establishes ClientSession via `streamablehttp_client("http://127.0.0.1:8745/mcp")` (literal `127.0.0.1`, NOT `localhost` — Pitfall 3)
    - `PinnedBackend("bn")` spawns `StdioServerParameters(command="python3", args=["/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py"])` and wraps in `ClientSession`
    - `PinnedBackend("ghidra")` spawns `StdioServerParameters(command="python3", args=["/agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py"], env={"GHIDRA_INSTALL_DIR": ...})`
    - `PinnedBackend.__aenter__` calls `session.initialize()`
    - `PinnedBackend.call(backend_tool_name, args)` delegates to `self.session.call_tool(backend_tool_name, args)`
    - `PinnedBackend.call_unified(unified_name, args)` uses `tool_map.translate(unified_name, self.backend, args)` then `.call()`
    - `PinnedBackend.call_unified` uses `asyncio.Lock` to serialize concurrent calls (Open Q2)
    - `PinnedBackend.__aexit__` closes the AsyncExitStack cleanly
    - `PinnedBackend("bogus")` raises ValueError
    - Backend subprocess error surfaces as MCP error (no silent fallback per D-10)
    - Integration test: fake in-memory MCP server acting as backend + `PinnedBackend.call_unified("list_functions")` returns backend's result
  </behavior>
  <action>
Create `mcp-gateway/src/mcp_gateway/backend/client.py`:

```python
"""PinnedBackend: holds a persistent MCP ClientSession to the selected backend.

D-06: gateway acts as an MCP client; no re-implementing disassembler logic.
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

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.streamable_http import streamablehttp_client

from . import tool_map

log = logging.getLogger("mcp_gateway.backend")

IDA_URL = "http://127.0.0.1:8745/mcp"
BN_SCRIPT = "/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py"
GHIDRA_SCRIPT = "/agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py"

SUPPORTED_BACKENDS = ("ida", "bn", "ghidra")


class PinnedBackend:
    """Async context manager wrapping a long-lived ClientSession to a disassembler backend."""

    def __init__(self, backend: str):
        if backend not in SUPPORTED_BACKENDS:
            raise ValueError(f"unsupported backend: {backend!r} (expected one of {SUPPORTED_BACKENDS})")
        self.backend = backend
        self._stack = AsyncExitStack()
        self._call_lock = asyncio.Lock()
        self.session: ClientSession | None = None

    async def __aenter__(self) -> "PinnedBackend":
        try:
            if self.backend == "ida":
                # Phase 1 already runs idalib-mcp on 127.0.0.1:8745 as a daemon.
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
            log.info("[gateway] backend session initialized: %s", self.backend)
            return self
        except Exception:
            # Fail loud (D-10) — close partial state and re-raise.
            await self._stack.aclose()
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._stack.aclose()
        self.session = None

    async def call(self, backend_tool: str, args: dict):
        """Raw call by backend-tool-name."""
        if self.session is None:
            raise RuntimeError("PinnedBackend not initialized — use as async context manager")
        async with self._call_lock:
            return await self.session.call_tool(backend_tool, args)

    async def call_unified(self, unified_name: str, args: dict | None = None) -> dict:
        """Resolve unified → backend tool name via tool_map, then call().

        Returns a dict shape {content, raw_result} for MCP tool handler consumption.
        """
        backend_tool, translated_args = tool_map.translate(unified_name, self.backend, args or {})
        result = await self.call(backend_tool, translated_args)
        # Normalize MCP CallToolResult → dict. The SDK's result has `.content` (list of TextContent/etc).
        content_blocks = []
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text is not None:
                content_blocks.append({"type": "text", "text": text})
            else:
                content_blocks.append({"type": type(block).__name__})
        return {
            "unified_tool": unified_name,
            "backend": self.backend,
            "backend_tool": backend_tool,
            "content": content_blocks,
            "is_error": bool(getattr(result, "isError", False)),
        }
```

Update `mcp-gateway/src/mcp_gateway/backend/__init__.py` to re-export `PinnedBackend`:

```python
from .detect import detect_backend
from .client import PinnedBackend

__all__ = ["detect_backend", "PinnedBackend"]
```

Create `mcp-gateway/tests/test_tool_routing.py`:

```python
"""Integration tests for PinnedBackend routing via a fake in-memory MCP backend.

Uses mcp.shared.memory.create_connected_server_and_client_session to sidestep
network/stdio and directly test the translate → call path.

Maps to VALIDATION.md rows:
  - GW-03 test_tool_routing (integration)
"""
from __future__ import annotations
import asyncio

import pytest
from mcp.server.fastmcp import FastMCP

from mcp_gateway.backend import client as client_mod
from mcp_gateway.backend import tool_map


class _FakePinnedBackend:
    """Drop-in PinnedBackend that talks to an in-memory FastMCP via the SDK's memory transport."""

    def __init__(self, backend: str, fake_mcp: FastMCP):
        self.backend = backend
        self._fake = fake_mcp
        self.session = None
        self._call_lock = asyncio.Lock()
        self._stack = None

    async def __aenter__(self):
        from mcp.shared.memory import create_connected_server_and_client_session
        self._cm = create_connected_server_and_client_session(self._fake._mcp_server)
        self.session = await self._cm.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._cm.__aexit__(exc_type, exc_val, exc_tb)
        self.session = None

    async def call(self, backend_tool, args):
        async with self._call_lock:
            return await self.session.call_tool(backend_tool, args)

    async def call_unified(self, unified_name, args=None):
        backend_tool, translated_args = tool_map.translate(unified_name, self.backend, args or {})
        result = await self.call(backend_tool, translated_args)
        content_blocks = []
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text is not None:
                content_blocks.append({"type": "text", "text": text})
        return {
            "unified_tool": unified_name,
            "backend": self.backend,
            "backend_tool": backend_tool,
            "content": content_blocks,
            "is_error": bool(getattr(result, "isError", False)),
        }


@pytest.fixture
def ida_like_backend_mcp() -> FastMCP:
    """In-memory MCP server using IDA-style tool names (matches tool_map['*']['ida'])."""
    m = FastMCP("fake-ida", stateless_http=True)

    @m.tool()
    def decompile(function: str) -> str:
        return f"int {function}() {{ return 0; }}  // fake-ida"

    @m.tool()
    def list_funcs() -> list[str]:
        return ["main", "init", "doWork"]

    @m.tool()
    def xrefs_to(function: str) -> list[str]:
        return [f"ref_1_to_{function}", f"ref_2_to_{function}"]

    return m


@pytest.fixture
def ghidra_like_backend_mcp() -> FastMCP:
    """In-memory MCP server using Ghidra-style names."""
    m = FastMCP("fake-ghidra", stateless_http=True)

    @m.tool(name="decomp.function")
    def decomp_function(function: str) -> str:
        return f"void {function}() {{}}  // fake-ghidra"

    @m.tool(name="function.list")
    def function_list() -> list[str]:
        return ["entry", "start"]

    @m.tool(name="reference.to")
    def reference_to(function: str) -> list[str]:
        return [f"ghidra_ref_{function}"]

    return m


# ---------- Real PinnedBackend class smoke tests ----------

def test_pinned_backend_rejects_unknown():
    import pytest as _pytest
    with _pytest.raises(ValueError, match="unsupported backend"):
        client_mod.PinnedBackend("qemu")


def test_ida_uses_127_0_0_1_literal():
    # Pitfall 3: IDA URL must use 127.0.0.1, never 'localhost'.
    assert client_mod.IDA_URL == "http://127.0.0.1:8745/mcp"


def test_bn_script_path():
    assert client_mod.BN_SCRIPT == "/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py"


def test_ghidra_script_path():
    assert client_mod.GHIDRA_SCRIPT == "/agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py"


def test_supported_backends_match_detect():
    from mcp_gateway.backend.detect import BACKENDS
    assert client_mod.SUPPORTED_BACKENDS == BACKENDS


# ---------- call_unified against fake backends ----------

@pytest.mark.asyncio
async def test_call_unified_decompile_ida_like(ida_like_backend_mcp):
    async with _FakePinnedBackend("ida", ida_like_backend_mcp) as pinned:
        r = await pinned.call_unified("decompile", {"function": "main"})
        assert r["unified_tool"] == "decompile"
        assert r["backend"] == "ida"
        assert r["backend_tool"] == "decompile"
        assert any("fake-ida" in b["text"] for b in r["content"])
        assert r["is_error"] is False


@pytest.mark.asyncio
async def test_call_unified_list_functions_ghidra_like(ghidra_like_backend_mcp):
    async with _FakePinnedBackend("ghidra", ghidra_like_backend_mcp) as pinned:
        r = await pinned.call_unified("list_functions")
        assert r["backend_tool"] == "function.list"
        assert any("entry" in b["text"] for b in r["content"])


@pytest.mark.asyncio
async def test_call_unified_get_xrefs_routes_by_backend(
    ida_like_backend_mcp, ghidra_like_backend_mcp
):
    async with _FakePinnedBackend("ida", ida_like_backend_mcp) as ida:
        r1 = await ida.call_unified("get_xrefs", {"function": "main"})
        assert r1["backend_tool"] == "xrefs_to"
    async with _FakePinnedBackend("ghidra", ghidra_like_backend_mcp) as ghidra:
        r2 = await ghidra.call_unified("get_xrefs", {"function": "main"})
        assert r2["backend_tool"] == "reference.to"


@pytest.mark.asyncio
async def test_call_unified_serializes_concurrent_calls(ida_like_backend_mcp):
    """Multiple concurrent call_unified calls must serialize via the lock (Open Q2)."""
    async with _FakePinnedBackend("ida", ida_like_backend_mcp) as pinned:
        results = await asyncio.gather(
            pinned.call_unified("decompile", {"function": "a"}),
            pinned.call_unified("decompile", {"function": "b"}),
            pinned.call_unified("decompile", {"function": "c"}),
        )
        assert all(r["unified_tool"] == "decompile" for r in results)


@pytest.mark.asyncio
async def test_call_unified_unknown_raises(ida_like_backend_mcp):
    async with _FakePinnedBackend("ida", ida_like_backend_mcp) as pinned:
        with pytest.raises(KeyError):
            await pinned.call_unified("not_a_tool")
```
  </action>
  <verify>
    <automated>pytest mcp-gateway/tests/test_tool_routing.py -x --no-header -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest mcp-gateway/tests/test_tool_routing.py -x --no-header -q` exits 0
    - `grep -q 'IDA_URL = "http://127.0.0.1:8745/mcp"' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -q 'streamablehttp_client' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -q 'stdio_client' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -q 'asyncio.Lock' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -q 'GHIDRA_INSTALL_DIR' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -q 'AsyncExitStack' mcp-gateway/src/mcp_gateway/backend/client.py`
    - `grep -q 'PinnedBackend' mcp-gateway/src/mcp_gateway/backend/__init__.py`
    - `python -c "from mcp_gateway.backend import PinnedBackend, detect_backend; print(PinnedBackend.__name__)"` exits 0
    - No use of `localhost` in client.py: `grep -c 'localhost' mcp-gateway/src/mcp_gateway/backend/client.py` == 0
  </acceptance_criteria>
  <done>PinnedBackend class complete with all three transport paths; 127.0.0.1 literal used for IDA; asyncio.Lock serializes calls; 10+ routing tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Wire PinnedBackend into app.py lifespan + update disasm tools to use call_unified</name>
  <files>
    mcp-gateway/src/mcp_gateway/app.py,
    mcp-gateway/src/mcp_gateway/tools/disasm.py
  </files>
  <read_first>
    - mcp-gateway/src/mcp_gateway/app.py (Plan 02 Task 3 left lifespan entering only session_manager.run; backend_name captured but no PinnedBackend entered)
    - mcp-gateway/src/mcp_gateway/tools/disasm.py (Plan 02 Task 2 — delegates to session_state.PINNED_BACKEND.call_unified which now exists on PinnedBackend)
    - mcp-gateway/src/mcp_gateway/backend/client.py (Task 2 — PinnedBackend class)
    - mcp-gateway/src/mcp_gateway/session_state.py (Plan 01 — PINNED_BACKEND module attribute)
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Code Example 1 full app.py skeleton shows the lifespan pattern)
  </read_first>
  <behavior>
    - `build_app()` lifespan enters `PinnedBackend(backend_name)` and sets `session_state.PINNED_BACKEND = pinned` BEFORE `mcp.session_manager.run()`
    - On lifespan exit, `session_state.PINNED_BACKEND` is reset to None
    - When `MCP_GATEWAY_SKIP_BACKEND=1`, NO PinnedBackend entered (test mode) — `session_state.PINNED_BACKEND` stays None
    - Startup log order: `[gateway] backend: <name>` → `[gateway] backend session initialized: <name>` → `[gateway] ready on ...`
    - disasm.py handlers unchanged structurally (Plan 02 stubs already call `session_state.PINNED_BACKEND.call_unified(...)`) but verify no further changes needed; add inline doc comment pointing at Plan 03 as the plan that wired it
    - Existing tests from Plan 01+02 remain green (regression)
    - New integration test: with `MCP_GATEWAY_SKIP_BACKEND=1` + monkeypatched `session_state.PINNED_BACKEND = fake_pinned`, calling `decompile` via Streamable HTTP tool handler returns the fake's response
  </behavior>
  <action>
**Step 1 — Update `mcp-gateway/src/mcp_gateway/app.py`** to enter PinnedBackend inside the lifespan. Replace the existing `build_app()` function with:

```python
"""Starlette application factory + FastMCP integration + middleware wiring + backend lifespan.

GW-01 (FastMCP Streamable HTTP) + GW-03 (unified backend routing via PinnedBackend).
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
            # Test/escape-hatch path — no backend, disasm tools will return stub.
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

        # Real backend path (D-09: pinned for lifetime, D-10: fail loud on crash)
        async with PinnedBackend(backend_name) as pinned:
            session_state.PINNED_BACKEND = pinned
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

**Step 2 — Verify `mcp-gateway/src/mcp_gateway/tools/disasm.py`** from Plan 02 Task 2 already calls `session_state.PINNED_BACKEND.call_unified(...)`. Add a brief header comment acknowledging Plan 03 wired the backend side:

```python
"""Unified disassembler tools (3): decompile, list_functions, get_xrefs.

Delegates to session_state.PINNED_BACKEND (set by Plan 03's lifespan).
If PINNED_BACKEND is None (test mode or no backend), returns structured stub.
Plan 03 wired PinnedBackend.call_unified — the `.call_unified` method maps the
unified name to the backend's tool via tool_map.translate.
"""
```

(The rest of disasm.py from Plan 02 Task 2 stays identical. If the Plan 02 file has drifted, re-apply the handlers verbatim from Plan 02's action.)

**Step 3 — Append an integration test to `mcp-gateway/tests/test_tool_routing.py`** (or put it in test_server_init.py if the executor prefers):

```python
# ---------- End-to-end: disasm tool handler → PINNED_BACKEND.call_unified ----------

@pytest.mark.asyncio
async def test_disasm_tool_handler_delegates_to_pinned(ida_like_backend_mcp, monkeypatch):
    """disasm.py::decompile must call session_state.PINNED_BACKEND.call_unified with args."""
    from mcp_gateway import session_state
    from mcp_gateway.tools import disasm as disasm_mod
    from mcp.server.fastmcp import FastMCP

    # Set up a fake PinnedBackend that captures the call
    captured = {}

    class _Capture:
        backend = "ida"

        async def call_unified(self, unified_name, args):
            captured.update({"unified_name": unified_name, "args": args})
            return {"unified_tool": unified_name, "content": [{"type": "text", "text": "captured"}]}

    monkeypatch.setattr(session_state, "PINNED_BACKEND", _Capture())
    m = FastMCP("t", stateless_http=True)
    disasm_mod.register(m)
    decompile_fn = m._tool_manager._tools["decompile"].fn

    r = await decompile_fn(function="main")
    assert captured["unified_name"] == "decompile"
    assert captured["args"]["function"] == "main"
    assert r["content"][0]["text"] == "captured"


def test_disasm_returns_stub_when_no_backend(monkeypatch):
    """With PINNED_BACKEND=None, disasm tools return a structured stub error."""
    from mcp_gateway import session_state
    from mcp_gateway.tools import disasm as disasm_mod
    from mcp.server.fastmcp import FastMCP

    monkeypatch.setattr(session_state, "PINNED_BACKEND", None)
    m = FastMCP("t", stateless_http=True)
    disasm_mod.register(m)

    # Note: decompile is async; we need to run it.
    import asyncio
    decompile_fn = m._tool_manager._tools["decompile"].fn
    r = asyncio.get_event_loop().run_until_complete(decompile_fn(function="main"))
    assert "error" in r and r["error"] == "backend not yet wired"
```
  </action>
  <verify>
    <automated>pytest mcp-gateway/tests/ -x --no-header -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest mcp-gateway/tests/ -x --no-header -q` exits 0 (full suite green, no regression of Plan 01/02 tests)
    - `grep -q 'async with PinnedBackend' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'session_state.PINNED_BACKEND = pinned' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'session_state.PINNED_BACKEND = None' mcp-gateway/src/mcp_gateway/app.py` (reset on exit)
    - `grep -q 'MCP_GATEWAY_SKIP_BACKEND' mcp-gateway/src/mcp_gateway/app.py` (test bypass)
    - `grep -q 'from .backend.client import PinnedBackend' mcp-gateway/src/mcp_gateway/app.py`
    - `python -c "from mcp_gateway.app import build_app; import os; os.environ['MCP_GATEWAY_SKIP_BACKEND']='1'; os.environ['MCP_GATEWAY_TOKEN']='t'; os.environ['MCP_GATEWAY_TOKEN_FILE']='/tmp/.tok'; build_app()"` exits 0
  </acceptance_criteria>
  <done>PinnedBackend is entered inside the Starlette lifespan; session_state.PINNED_BACKEND is set for the gateway's lifetime; disasm tool handlers transparently delegate to the active backend; full test suite green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| gateway process → idalib-mcp daemon | Trusted (local loopback, Phase 1 already validates) but use 127.0.0.1 literal (Pitfall 3) |
| gateway process → BN/Ghidra stdio subprocess | Trusted script path (hardcoded in client.py); argv is fixed, not user-controlled |
| disasm tool input (function name, sample) | Untrusted; validated/canonicalized via `resolve_sample` (Plan 02) before reaching backend |
| Backend result → MCP tool response | Passed through; backend is trusted not to emit hostile payloads |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-02-SUBPROC | Tampering / RCE | stdio subprocess spawn (BN, Ghidra) | HIGH | mitigate | Task 2: `StdioServerParameters(command="python3", args=[LITERAL_SCRIPT_PATH])`. Script paths are hardcoded constants, NOT derived from user input. No shell interpolation. |
| T-02-AUTH | Spoofing | Backend ClientSession | LOW | accept | Backends run on localhost loopback or as direct subprocess; no network exposure. Gateway process owns both sides. |
| T-02-NET | Info Disclosure (IPv6 hang via `localhost`) | IDA Streamable HTTP client | LOW | mitigate | Task 2 constant `IDA_URL = "http://127.0.0.1:8745/mcp"` literal (Pitfall 3 in RESEARCH.md). Acceptance criteria greps absence of `localhost`. |
| T-02-PATHTRAVERSAL | Tampering | disasm tool `sample` arg | HIGH | mitigate | disasm.py (Plan 02) calls `resolve_sample()` which already rejects traversal. Plan 03 does not weaken this. |
| T-02-SILENT-FALLBACK | Availability/Integrity | backend crash | HIGH | mitigate | Task 2: `PinnedBackend.__aenter__` re-raises on init failure (D-10). The `lifespan` does NOT try the next-priority backend. Errors surface as MCP error to the client. |
| T-02-SUBPROC-DEADLOCK | DoS (backend hang) | stdio subprocess stderr | MEDIUM | mitigate | Task 2: uses SDK's `stdio_client` which reads stdout in background task and discards stderr (Pitfall 4 in RESEARCH). Do NOT wrap with extra I/O. |
| T-02-TOKENLEAK | Info Disclosure | — | — | — | Not applicable (Plan 01 handles) |
| T-02-UPLOAD | DoS | — | — | transfer | Plan 04 |
</threat_model>

<verification>
After all 3 tasks:
1. Full test suite: `pytest mcp-gateway/tests/ -x --no-header -q` — exits 0 (Plan 01 + 02 + 03 combined, ~45+ tests)
2. `ruff check mcp-gateway/src/ mcp-gateway/tests/` clean
3. Import graph: `python -c "from mcp_gateway.app import build_app; from mcp_gateway.backend import PinnedBackend, detect_backend; from mcp_gateway.backend.tool_map import translate; print('imports ok')"` exits 0
4. Key security greps:
   - `grep -c 'localhost' mcp-gateway/src/mcp_gateway/backend/client.py` == 0
   - `grep -c 'shell=True' mcp-gateway/src/mcp_gateway/backend/client.py` == 0
   - `grep -c '127.0.0.1' mcp-gateway/src/mcp_gateway/backend/client.py` >= 1
5. Disasm tools respond correctly:
   - With PINNED_BACKEND set → delegates and returns content
   - With PINNED_BACKEND=None → returns structured stub (no crash)
</verification>

<success_criteria>
- GW-03 met: client calling `decompile(function="main")` gets routed to `decompile` (IDA), `decomp.function` (Ghidra), or BN equivalent transparently
- PinnedBackend enters inside Starlette lifespan; `session_state.PINNED_BACKEND` is set for the gateway lifetime
- asyncio.Lock serializes concurrent call_unified invocations (Open Q2 resolved)
- D-06 (gateway as MCP client): `ClientSession` wraps real backend transport; no logic re-implementation
- D-07 (unified surface): clients see only `decompile`, `list_functions`, `get_xrefs` — never `decomp.function` or `list_funcs`
- D-09 (pinned): backend chosen ONCE at lifespan enter; no mid-session switching
- D-10 (fail loud): PinnedBackend.__aenter__ re-raises on init failure; no silent fallback
- 127.0.0.1 literal used for IDA (Pitfall 3 avoided)
- BN tool name TODO flagged for container-side validation (RESEARCH A5)
- No regression: all Plan 01 and Plan 02 tests still green
</success_criteria>

<output>
After completion, create `.planning/phases/02-mcp-gateway/02-03-SUMMARY.md`.
Include:
- Transport matrix: ida → Streamable HTTP 127.0.0.1:8745; bn → stdio subprocess; ghidra → stdio subprocess with GHIDRA_INSTALL_DIR
- tool_map table (current mappings + BN TODO items)
- Test counts: test_tool_map.py (9), test_tool_routing.py (12+), full suite running green
- Threat mitigations: T-02-SUBPROC (argv-only), T-02-SILENT-FALLBACK (D-10 fail-loud), T-02-NET (127.0.0.1 literal)
- Handoff to Plan 04: app.py still has `/upload` placeholder returning 501 — Plan 04 replaces it
- Handoff to Plan 05: backend subprocess paths (BN, Ghidra) expected at `/agent/mcp/...` — Plan 05's Dockerfile must ensure these are present; smoke test should verify `tools/list` against the real chosen backend
</output>
