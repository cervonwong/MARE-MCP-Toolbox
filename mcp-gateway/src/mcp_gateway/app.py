"""Starlette application factory + FastMCP integration + middleware wiring.

Fulfills GW-01 (FastMCP Streamable HTTP), wires Plan 01 auth, registers 21 tools
from Plan 02 Task 2. The /upload route is a placeholder here returning 501;
Plan 04 replaces it with a real streaming handler.
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
from .tools import register_all_tools

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


async def _upload_placeholder(request):
    """Placeholder -- replaced by Plan 04's real streaming handler."""
    return JSONResponse(
        {"error": "upload handler not yet installed", "plan": "Plan 04"},
        status_code=501,
    )


def build_app() -> Starlette:
    """Assemble the gateway ASGI app.

    Order of operations:
      1) Generate/load bearer token (D-16, D-17, T-02-TOKENLEAK).
      2) Detect backend (D-09). Raise if none installed (D-10 fail-loud) unless
         MCP_GATEWAY_SKIP_BACKEND=1 (test-only escape hatch).
      3) Create FastMCP instance and register all 21 tools (GW-02).
      4) Build Starlette app with /healthz, /upload placeholder, /mcp mount.
      5) Add OriginMiddleware (outer, DNS rebind T-02-NET) + BearerAuthMiddleware (inner, T-02-AUTH).
    """
    token = load_or_generate_token()

    skip_backend = os.environ.get("MCP_GATEWAY_SKIP_BACKEND") == "1"
    if skip_backend:
        log.warning("[gateway] MCP_GATEWAY_SKIP_BACKEND=1 -- backend detection bypassed (test mode)")
        backend_name = "none"
    else:
        backend_name = detect_backend()
        log.info("[gateway] backend: %s", backend_name)

    mcp = get_mcp()
    register_all_tools(mcp)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        # Plan 03 extends this lifespan to enter a PinnedBackend context.
        log.info(
            "[gateway] ready on %s:%s",
            os.environ.get("MCP_GATEWAY_HOST", "127.0.0.1"),
            os.environ.get("MCP_GATEWAY_PORT", "8080"),
        )
        log.info("[gateway] token file: %s", os.environ.get("MCP_GATEWAY_TOKEN_FILE", "/agent/.mcp-gateway-token"))
        async with mcp.session_manager.run():
            yield

    app = Starlette(
        routes=[
            Route("/healthz", _healthz, methods=["GET"]),
            Route("/upload", _upload_placeholder, methods=["POST"]),
            Mount("/mcp", app=mcp.streamable_http_app()),
        ],
        lifespan=lifespan,
    )
    # Order matters: Starlette runs middleware in REVERSE add order for requests,
    # so add Bearer last (innermost) to run first; add Origin before Bearer (outermost).
    app.add_middleware(BearerAuthMiddleware, token=token)
    app.add_middleware(OriginMiddleware)
    return app
