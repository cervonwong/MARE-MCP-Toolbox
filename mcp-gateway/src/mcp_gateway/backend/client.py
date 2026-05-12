"""PinnedBackend: holds a persistent MCP ClientSession to the selected backend.

D-06: gateway acts as an MCP client; no re-implementing disassembler logic.
D-09: selected backend is pinned for the gateway's lifetime.
D-10: crashes fail loud (no silent fallback to next-priority backend).

Transport per backend:
  ida    -- Streamable HTTP to http://127.0.0.1:8745/mcp (idalib-mcp daemon from Phase 1).
            Use 127.0.0.1 LITERAL (avoid DNS hostnames: Pitfall 3 IPv6 hang).
  bn     -- stdio subprocess: python3 /agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py
  ghidra -- stdio subprocess: python3 /agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py
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
            raise ValueError(
                f"unsupported backend: {backend!r} (expected one of {SUPPORTED_BACKENDS})"
            )
        self.backend = backend
        self.name = backend  # public alias (see tools/cases.get_active_backend)
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
            # Fail loud (D-10) -- close partial state and re-raise.
            await self._stack.aclose()
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._stack.aclose()
        self.session = None

    async def call(self, backend_tool: str, args: dict):
        """Raw call by backend-tool-name."""
        if self.session is None:
            raise RuntimeError("PinnedBackend not initialized -- use as async context manager")
        async with self._call_lock:
            return await self.session.call_tool(backend_tool, args)

    async def list_tools(self):
        """Return native MCP tool definitions exposed by the pinned backend."""
        if self.session is None:
            raise RuntimeError("PinnedBackend not initialized -- use as async context manager")
        async with self._call_lock:
            response = await self.session.list_tools()
        return list(response.tools)

    async def call_unified(self, unified_name: str, args: dict | None = None) -> dict:
        """Resolve unified -> backend tool name via tool_map, then call().

        Returns a dict shape {content, raw_result} for MCP tool handler consumption.
        """
        backend_tool, translated_args = tool_map.translate(
            unified_name, self.backend, args or {}
        )
        result = await self.call(backend_tool, translated_args)
        # Normalize MCP CallToolResult -> dict. The SDK's result has `.content`
        # (list of TextContent/etc).
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
