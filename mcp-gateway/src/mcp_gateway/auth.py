"""Auth: token lifecycle + BearerAuthMiddleware + OriginMiddleware.

Threat mitigations (see .planning/phases/02-mcp-gateway/02-PLAN.md threat_model):
  - T-02-AUTH: constant-time compare, 401 on /mcp and /upload without valid bearer.
  - T-02-TOKENLEAK: token file 0o600, MCP_GATEWAY_QUIET suppresses log line.
"""
from __future__ import annotations
import hmac
import logging
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger("mcp_gateway.auth")

DEFAULT_TOKEN_FILE = "/agent/.mcp-gateway-token"


def _token_file_path() -> Path:
    return Path(os.environ.get("MCP_GATEWAY_TOKEN_FILE", DEFAULT_TOKEN_FILE))


def load_or_generate_token() -> str:
    """Return bearer token. D-16: env var wins, else generate. D-17: write 0600 file, log once."""
    tok = os.environ.get("MCP_GATEWAY_TOKEN")
    if not tok:
        tok = secrets.token_urlsafe(32)
        log.info("[gateway] generated new bearer token")
    token_file = _token_file_path()
    token_file.parent.mkdir(parents=True, exist_ok=True)
    # Open with O_CREAT|O_TRUNC|O_WRONLY and mode 0o600 atomically (T-02-TOKENLEAK).
    fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(tok + "\n")
    finally:
        # fdopen closes fd on exit; nothing else to do.
        pass
    # Enforce mode even if umask interfered (belt-and-suspenders).
    os.chmod(token_file, 0o600)
    if not os.environ.get("MCP_GATEWAY_QUIET"):
        log.info("[gateway] Bearer token: %s", tok)
    log.info("[gateway] token file: %s", token_file)
    return tok


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests to /mcp* and /upload without valid Authorization: Bearer <token>.

    /healthz is intentionally open (D-17 monitoring). T-02-AUTH mitigation.
    """

    PROTECTED_PREFIXES = ("/mcp", "/upload")

    def __init__(self, app, token: str):
        super().__init__(app)
        self._token = token.encode()

    async def dispatch(self, request: Request, call_next):
        if not any(request.url.path.startswith(p) for p in self.PROTECTED_PREFIXES):
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"error": "missing bearer token"}, status_code=401)
        presented = auth.split(" ", 1)[1].strip().encode()
        if not hmac.compare_digest(presented, self._token):
            return JSONResponse({"error": "invalid bearer token"}, status_code=401)
        return await call_next(request)


class OriginMiddleware(BaseHTTPMiddleware):
    """DNS-rebind protection per MCP spec 2025-03-26 § Security Warning.

    Allow exact loopback hosts, literal "null", or missing Origin (non-browser client).
    Reject everything else with 403.
    T-02-NET mitigation.
    """

    ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        if origin is None or origin == "null":
            return await call_next(request)
        try:
            parsed = urlsplit(origin)
        except ValueError:
            return JSONResponse({"error": "forbidden origin"}, status_code=403)
        if parsed.scheme in {"http", "https"} and parsed.hostname in self.ALLOWED_HOSTS:
            return await call_next(request)
        return JSONResponse({"error": "forbidden origin"}, status_code=403)
