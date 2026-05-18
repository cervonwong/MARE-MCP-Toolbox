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
from mcp.server.transport_security import TransportSecuritySettings

from .auth import BearerAuthMiddleware, OriginMiddleware, load_or_generate_token
from .backend.detect import detect_backend
from .backend.client import PinnedBackend
from .tools import register_all_tools
from .tools.collision_check import assert_no_collisions
from .sessions import (
    SessionRegistry,
    MAX_SESSIONS,
    SESSION_IDLE_S,
    REAPER_INTERVAL_S,
)
from .uploads import upload_handler
from . import session_state

log = logging.getLogger("mcp_gateway")

_MCP_INSTANCE: FastMCP | None = None


def get_mcp() -> FastMCP:
    """Access the module-level FastMCP instance (used by Plan 03 to register backend-fed tools).

    NOTE: streamable_http_path="/" so that when mounted at "/mcp" the full path is
    "/mcp" (not "/mcp/mcp"). FastMCP's built-in transport_security is disabled
    because we wrap the outer Starlette app with OriginMiddleware (T-02-NET).
    """
    global _MCP_INSTANCE
    if _MCP_INSTANCE is None:
        _MCP_INSTANCE = FastMCP(
            "mare-gateway",
            stateless_http=True,
            json_response=True,
            streamable_http_path="/",
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=False,
            ),
        )
    return _MCP_INSTANCE


async def _healthz(request):
    return JSONResponse({"ok": True})


def build_app() -> Starlette:
    """Assemble the gateway ASGI app.

    Order of operations:
      1) Generate/load bearer token (D-16, D-17, T-02-TOKENLEAK).
      2) Detect backend (D-09). Raise if none installed (D-10 fail-loud) unless
         MCP_GATEWAY_SKIP_BACKEND=1 (test-only escape hatch).
      3) Create FastMCP instance and register all 21 tools (GW-02).
      4) Build Starlette app with /healthz, /upload (streaming handler, Plan 04), /mcp mount.
      5) Lifespan enters a PinnedBackend (Plan 03) that holds a ClientSession
         to the active disassembler MCP for the gateway's lifetime (D-09).
         When MCP_GATEWAY_SKIP_BACKEND=1, no PinnedBackend is entered and
         disasm tools return their Plan 02 stub.
      6) Add OriginMiddleware (outer, DNS rebind T-02-NET) + BearerAuthMiddleware (inner, T-02-AUTH).
    """
    token = load_or_generate_token()

    skip_backend = os.environ.get("MCP_GATEWAY_SKIP_BACKEND") == "1"
    if skip_backend:
        log.warning(
            "[gateway] MCP_GATEWAY_SKIP_BACKEND=1 -- backend detection bypassed (test mode)"
        )
        backend_name: str | None = None
    else:
        backend_name = detect_backend()
        log.info("[gateway] backend: %s", backend_name)

    mcp = get_mcp()
    register_all_tools(mcp)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        # D-14 + D-24: SessionRegistry parameters come from the sessions module
        # constants which were read ONCE at sessions.py import with RuntimeError
        # sanity-check on bad env values. We do NOT re-read os.environ here —
        # that would bypass D-14's validation and create two sources of truth.
        def _build_registry() -> SessionRegistry:
            return SessionRegistry(
                max_sessions=MAX_SESSIONS,
                idle_s=SESSION_IDLE_S,
                reaper_interval_s=REAPER_INTERVAL_S,
            )

        if backend_name is None:
            # Test/escape-hatch path -- no backend, disasm tools return stub.
            # Phase 7 D-11: collision check runs even on the no-backend path; it
            # sees an empty tool_cache (or PINNED_BACKEND is None), exits cleanly,
            # and validates the gateway-native surface stands alone correctly.
            try:
                await assert_no_collisions(mcp)
                # Phase 8 D-24: SessionRegistry also active on no-backend path
                # (r2 is standalone; no disassembler dependency).
                async with _build_registry() as registry:
                    session_state.SESSION_REGISTRY = registry
                    try:
                        async with mcp.session_manager.run():
                            log.info(
                                "[gateway] ready on %s:%s (no backend)",
                                os.environ.get("MCP_GATEWAY_HOST", "127.0.0.1"),
                                os.environ.get("MCP_GATEWAY_PORT", "8080"),
                            )
                            yield
                    finally:
                        session_state.SESSION_REGISTRY = None
            finally:
                session_state.PINNED_BACKEND = None
            return

        # Real backend path (D-09: pinned for lifetime, D-10: fail loud on crash).
        async with PinnedBackend(backend_name) as pinned:
            session_state.PINNED_BACKEND = pinned
            try:
                # Phase 7 D-11: hard-fail at lifespan if backend tools shadow ours.
                # MUST be AFTER `session_state.PINNED_BACKEND = pinned` so that
                # PinnedBackend.__aenter__ has populated tool_cache; MUST be
                # BEFORE serving so a collision exits the process cleanly with
                # EX_CONFIG (78) rather than a half-started server.
                await assert_no_collisions(mcp)
                # Phase 8 D-24: SessionRegistry block lives INSIDE the
                # PinnedBackend block AND AFTER assert_no_collisions. On
                # shutdown the registry's __aexit__ kills every open r2 session
                # BEFORE PinnedBackend's __aexit__ fires (LIFO unwind), so no
                # zombie r2 processes survive container teardown.
                async with _build_registry() as registry:
                    session_state.SESSION_REGISTRY = registry
                    try:
                        async with mcp.session_manager.run():
                            log.info(
                                "[gateway] ready on %s:%s",
                                os.environ.get("MCP_GATEWAY_HOST", "127.0.0.1"),
                                os.environ.get("MCP_GATEWAY_PORT", "8080"),
                            )
                            log.info(
                                "[gateway] token file: %s",
                                os.environ.get(
                                    "MCP_GATEWAY_TOKEN_FILE", "/agent/.mcp-gateway-token"
                                ),
                            )
                            yield
                    finally:
                        session_state.SESSION_REGISTRY = None
            finally:
                session_state.PINNED_BACKEND = None

    app = Starlette(
        routes=[
            Route("/healthz", _healthz, methods=["GET"]),
            Route("/upload", upload_handler, methods=["POST"]),
            Mount("/mcp", app=mcp.streamable_http_app()),
        ],
        lifespan=lifespan,
    )
    # Starlette wraps middlewares in add-order: the LAST one added becomes the
    # OUTERMOST (runs first on a request). Add Bearer first (inner: runs second),
    # then Origin (outer: runs first -> DNS-rebind check before auth).
    app.add_middleware(BearerAuthMiddleware, token=token)
    app.add_middleware(OriginMiddleware)
    return app
