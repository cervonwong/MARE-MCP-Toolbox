"""Integration tests for PinnedBackend routing via a fake in-memory MCP backend.

Uses mcp.shared.memory.create_connected_server_and_client_session to sidestep
network/stdio and directly test the translate -> call path.

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
        self._cm = None

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
    with pytest.raises(ValueError, match="unsupported backend"):
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


# ---------- End-to-end: disasm tool handler -> PINNED_BACKEND.call_unified ----------

@pytest.mark.asyncio
async def test_disasm_tool_handler_delegates_to_pinned(ida_like_backend_mcp, monkeypatch):
    """disasm.py::decompile must call session_state.PINNED_BACKEND.call_unified with args."""
    from mcp_gateway import session_state
    from mcp_gateway.tools import disasm as disasm_mod

    # Set up a fake PinnedBackend that captures the call
    captured = {}

    class _Capture:
        backend = "ida"

        async def call_unified(self, unified_name, args):
            captured.update({"unified_name": unified_name, "args": args})
            return {
                "unified_tool": unified_name,
                "content": [{"type": "text", "text": "captured"}],
            }

    monkeypatch.setattr(session_state, "PINNED_BACKEND", _Capture())
    m = FastMCP("t", stateless_http=True)
    disasm_mod.register(m)
    # FastMCP internal -- if upgraded past 1.27, rewrite using
    # create_connected_server_and_client_session.call_tool(name, args)
    decompile_fn = m._tool_manager._tools["decompile"].fn

    r = await decompile_fn(function="main")
    assert captured["unified_name"] == "decompile"
    assert captured["args"]["function"] == "main"
    assert r["content"][0]["text"] == "captured"


@pytest.mark.asyncio
async def test_disasm_returns_stub_when_no_backend(monkeypatch):
    """With PINNED_BACKEND=None, disasm tools return a structured stub error."""
    from mcp_gateway import session_state
    from mcp_gateway.tools import disasm as disasm_mod

    monkeypatch.setattr(session_state, "PINNED_BACKEND", None)
    m = FastMCP("t", stateless_http=True)
    disasm_mod.register(m)

    decompile_fn = m._tool_manager._tools["decompile"].fn
    r = await decompile_fn(function="main")
    assert "error" in r and r["error"] == "backend not yet wired"


# ---------- build_app() lifespan PinnedBackend wiring ----------

def test_build_app_skips_backend_when_env_flag_set(monkeypatch, tmp_path):
    """MCP_GATEWAY_SKIP_BACKEND=1 must not try to enter a PinnedBackend."""
    import os
    from mcp_gateway.app import build_app

    monkeypatch.setenv("MCP_GATEWAY_SKIP_BACKEND", "1")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "test-token")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / ".tok"))
    app = build_app()
    assert app is not None


def test_build_app_imports_pinnedbackend_from_client():
    """Regression: app.py must import PinnedBackend from backend.client (not stubbed)."""
    import mcp_gateway.app as app_mod
    from mcp_gateway.backend.client import PinnedBackend
    assert app_mod.PinnedBackend is PinnedBackend


@pytest.mark.asyncio
async def test_lifespan_enters_and_exits_pinned_backend(monkeypatch, tmp_path):
    """Lifespan must enter a PinnedBackend when a real backend is detected,
    set session_state.PINNED_BACKEND, and reset it to None on exit (D-09 + D-10).
    """
    from mcp_gateway import session_state
    from mcp_gateway import app as app_mod

    calls = {"entered": 0, "exited": 0, "during_lifespan_pinned": None}

    class _FakePinned:
        def __init__(self, backend):
            self.backend = backend

        async def __aenter__(self):
            calls["entered"] += 1
            return self

        async def __aexit__(self, *a):
            calls["exited"] += 1

    def _fake_detect():
        return "ida"

    monkeypatch.setattr(app_mod, "detect_backend", _fake_detect)
    monkeypatch.setattr(app_mod, "PinnedBackend", _FakePinned)
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "test-token")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / ".tok"))
    monkeypatch.delenv("MCP_GATEWAY_SKIP_BACKEND", raising=False)

    # Ensure the test starts with None so we can confirm reset on exit.
    monkeypatch.setattr(session_state, "PINNED_BACKEND", None)

    app = app_mod.build_app()
    # Drive the lifespan manually
    async with app.router.lifespan_context(app):
        calls["during_lifespan_pinned"] = session_state.PINNED_BACKEND

    assert calls["entered"] == 1, "PinnedBackend was never entered by lifespan"
    assert calls["exited"] == 1, "PinnedBackend was never exited by lifespan"
    assert isinstance(calls["during_lifespan_pinned"], _FakePinned), (
        "session_state.PINNED_BACKEND was not set inside the lifespan"
    )
    assert session_state.PINNED_BACKEND is None, (
        "session_state.PINNED_BACKEND was not reset after lifespan exit"
    )
