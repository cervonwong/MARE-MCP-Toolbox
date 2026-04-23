---
phase: 02-mcp-gateway
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - mcp-gateway/pyproject.toml
  - mcp-gateway/README.md
  - mcp-gateway/src/mcp_gateway/__init__.py
  - mcp-gateway/src/mcp_gateway/__main__.py
  - mcp-gateway/src/mcp_gateway/_version.py
  - mcp-gateway/src/mcp_gateway/cli.py
  - mcp-gateway/src/mcp_gateway/auth.py
  - mcp-gateway/src/mcp_gateway/session_state.py
  - mcp-gateway/src/mcp_gateway/backend/__init__.py
  - mcp-gateway/src/mcp_gateway/backend/detect.py
  - mcp-gateway/tests/__init__.py
  - mcp-gateway/tests/conftest.py
  - mcp-gateway/tests/test_auth.py
  - mcp-gateway/tests/test_cli.py
  - mcp-gateway/tests/test_detect.py
  - mcp-gateway/tests/e2e/smoke.sh
  - mcp-gateway/tests/e2e/test_upload_then_analyze.sh
autonomous: true
requirements:
  - GW-04
  - GW-05
tags:
  - mcp
  - auth
  - scaffold
  - python

must_haves:
  truths:
    - "Package `mcp_gateway` is importable via `python -c 'import mcp_gateway'` after `pip install -e mcp-gateway/`"
    - "`load_or_generate_token()` returns env var verbatim when `MCP_GATEWAY_TOKEN` is set"
    - "`load_or_generate_token()` generates a secrets.token_urlsafe(32) token when env var is unset"
    - "Token file at path in `MCP_GATEWAY_TOKEN_FILE` (default `/agent/.mcp-gateway-token`) is created with 0600 permissions"
    - "`BearerAuthMiddleware` returns 401 for missing/invalid bearer on `/mcp*` and `/upload`"
    - "`BearerAuthMiddleware` allows `/healthz` without a bearer"
    - "`OriginMiddleware` allows Origin `http://127.0.0.1:*`, `http://localhost:*`, and missing Origin; rejects others with 403"
    - "`detect_backend()` returns 'ida' when `/opt/ida-pro` is populated AND `idalib-mcp` is on PATH"
    - "`detect_backend()` returns 'bn' when IDA missing AND `/opt/binaryninja/scripts/install_api.py` + BN MCP file exist"
    - "`detect_backend()` returns 'ghidra' when IDA and BN missing AND Ghidra MCP file exists"
    - "`detect_backend()` raises RuntimeError when no backend is installed"
    - "Default CLI host is `127.0.0.1` when `MCP_GATEWAY_HOST` is unset"
    - "Default CLI port is `8080` when `MCP_GATEWAY_PORT` is unset"
    - "`MCP_GATEWAY_QUIET=1` suppresses the `[gateway] Bearer token:` log line but token file is still written"
  artifacts:
    - path: "mcp-gateway/pyproject.toml"
      provides: "Package metadata, pytest-asyncio config, entry point"
      contains: "mcp>=1.27,<1.28"
    - path: "mcp-gateway/src/mcp_gateway/auth.py"
      provides: "load_or_generate_token, BearerAuthMiddleware, OriginMiddleware"
      exports: ["load_or_generate_token", "BearerAuthMiddleware", "OriginMiddleware"]
    - path: "mcp-gateway/src/mcp_gateway/backend/detect.py"
      provides: "detect_backend() returning 'ida'|'bn'|'ghidra' or raising"
      exports: ["detect_backend"]
    - path: "mcp-gateway/src/mcp_gateway/cli.py"
      provides: "main() argparse entry; defaults host=127.0.0.1, port=8080"
      exports: ["main"]
    - path: "mcp-gateway/tests/conftest.py"
      provides: "bearer_token, tmp_upload_dir, tmp_status_dir, fake_backend_mcp fixtures"
    - path: "mcp-gateway/tests/test_auth.py"
      provides: "4 auth test cases (missing/invalid/valid bearer + open /healthz)"
  key_links:
    - from: "mcp-gateway/src/mcp_gateway/auth.py::load_or_generate_token"
      to: "os.environ['MCP_GATEWAY_TOKEN'] / secrets.token_urlsafe"
      via: "env-var-wins fallback pattern"
      pattern: "MCP_GATEWAY_TOKEN.*secrets\\.token_urlsafe"
    - from: "mcp-gateway/src/mcp_gateway/auth.py::BearerAuthMiddleware.dispatch"
      to: "hmac.compare_digest"
      via: "constant-time comparison"
      pattern: "hmac\\.compare_digest"
    - from: "mcp-gateway/src/mcp_gateway/backend/detect.py"
      to: "docker-bin/configure-agent-mcp.sh"
      via: "mirrors IDA > BN > Ghidra chain at lines 67-119"
      pattern: "/opt/ida-pro.*idalib-mcp"
---

<objective>
Bootstrap the `mcp-gateway/` Python package with pyproject.toml + pytest config, Wave 0 test fixtures, bearer-token auth middleware, Origin validation middleware, backend detection module, and CLI entry point.

Purpose: This is the foundation wave. Every downstream plan (02, 03, 04, 05) depends on this scaffold. Auth + detect must be verifiable in isolation so later plans can focus on FastMCP integration, backend routing, and uploads without re-doing plumbing.

Output: A fully-tested `mcp_gateway` package that can be pip-installed, with green pytest suite for auth, CLI defaults, and backend detection. The Starlette app itself is not yet assembled — that happens in Plan 02.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/phases/02-mcp-gateway/02-CONTEXT.md
@.planning/phases/02-mcp-gateway/02-RESEARCH.md
@.planning/phases/02-mcp-gateway/02-VALIDATION.md
@docker-bin/configure-agent-mcp.sh
@CLAUDE.md

<interfaces>
<!-- Key contracts downstream plans will import from this plan. -->

From mcp-gateway/src/mcp_gateway/auth.py (this plan creates):
```python
def load_or_generate_token() -> str: ...
class BearerAuthMiddleware(BaseHTTPMiddleware):
    PROTECTED_PREFIXES = ("/mcp", "/upload")
    def __init__(self, app, token: str): ...
class OriginMiddleware(BaseHTTPMiddleware):
    ALLOWED_PREFIXES = ("http://127.0.0.1", "http://localhost", "null")
```

From mcp-gateway/src/mcp_gateway/backend/detect.py (this plan creates):
```python
def detect_backend() -> str:  # returns "ida" | "bn" | "ghidra" or raises RuntimeError
    """Priority: IDA > BN > Ghidra. Mirrors docker-bin/configure-agent-mcp.sh lines 67-119."""
```

From mcp-gateway/src/mcp_gateway/session_state.py (this plan creates):
```python
PINNED_BACKEND = None      # set by Plan 03's lifespan; type: Optional[PinnedBackend]
ACTIVE_CASE: str | None = None  # per-session active case (Plan 02's case tools mutate)
```

Reuse pattern (mirror of docker-bin/configure-agent-mcp.sh lines 67-119):
```bash
if [ -d "/opt/ida-pro" ] && [ "$(ls -A /opt/ida-pro 2>/dev/null)" ] && command -v idalib-mcp >/dev/null 2>&1; then
  # IDA
elif [ -f /opt/binaryninja/scripts/install_api.py ] && [ -f "${BINJA_ROOT}/binary_ninja_headless_mcp.py" ]; then
  # BN
elif [ -f "${GHIDRA_ROOT}/ghidra_headless_mcp.py" ]; then
  # Ghidra
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Package scaffold + Wave 0 fixtures + pyproject</name>
  <files>
    mcp-gateway/pyproject.toml,
    mcp-gateway/README.md,
    mcp-gateway/src/mcp_gateway/__init__.py,
    mcp-gateway/src/mcp_gateway/__main__.py,
    mcp-gateway/src/mcp_gateway/_version.py,
    mcp-gateway/src/mcp_gateway/session_state.py,
    mcp-gateway/src/mcp_gateway/backend/__init__.py,
    mcp-gateway/tests/__init__.py,
    mcp-gateway/tests/conftest.py,
    mcp-gateway/tests/e2e/smoke.sh,
    mcp-gateway/tests/e2e/test_upload_then_analyze.sh
  </files>
  <read_first>
    - mcp-gateway/ (verify directory is empty/doesn't exist)
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Recommended Project Structure, § Validation Architecture, § Example 5)
    - .planning/phases/02-mcp-gateway/02-VALIDATION.md (§ Wave 0 Requirements)
    - mcp/ghidra-headless-mcp/pyproject.toml (for pyproject.toml style reference)
    - mcp/ghidra-headless-mcp/ghidra_headless_mcp/_version.py (for _version.py pattern)
  </read_first>
  <behavior>
    - Package `mcp_gateway` importable after `pip install -e mcp-gateway/`
    - `python -m mcp_gateway --help` exits 0 once cli.py lands in Task 2
    - `pytest mcp-gateway/tests/ --collect-only` exits 0 without errors
    - `conftest.py` exports fixtures: `bearer_token`, `tmp_upload_dir`, `tmp_status_dir`, `fake_backend_mcp`
    - `session_state.py` exposes module-level `PINNED_BACKEND = None`, `ACTIVE_CASE: str | None = None`
    - e2e shell stubs exist and are executable but the body is placeholder (filled in Plan 05)
  </behavior>
  <action>
Create `mcp-gateway/pyproject.toml` with EXACTLY this content (verbatim, including dependencies, build system, scripts entry, and pytest config):

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "mcp-gateway"
version = "0.1.0"
description = "MARE-MCP-Toolbox gateway: curated MCP tool surface over Streamable HTTP"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.27,<1.28",
    "starlette>=0.37",
    "uvicorn>=0.27",
    "python-multipart>=0.0.9",
    "httpx>=0.27",
    "anyio>=4.5",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "ruff>=0.5"]

[project.scripts]
mcp-gateway = "mcp_gateway.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra"
```

Create `mcp-gateway/src/mcp_gateway/__init__.py` with:
```python
"""MARE-MCP-Toolbox gateway."""
from ._version import __version__

__all__ = ["__version__"]
```

Create `mcp-gateway/src/mcp_gateway/_version.py` with:
```python
__version__ = "0.1.0"
```

Create `mcp-gateway/src/mcp_gateway/__main__.py` with:
```python
from .cli import main

if __name__ == "__main__":
    main()
```

Create `mcp-gateway/src/mcp_gateway/session_state.py` with:
```python
"""Module-level gateway state (Phase 2 single-session model).

v2 (GW-V2-03) will replace this with per-client-session state keyed off Mcp-Session-Id.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .backend.client import PinnedBackend  # created in Plan 03

PINNED_BACKEND: Optional["PinnedBackend"] = None
ACTIVE_CASE: Optional[str] = None
```

Create `mcp-gateway/src/mcp_gateway/backend/__init__.py` with:
```python
from .detect import detect_backend

__all__ = ["detect_backend"]
```

Create `mcp-gateway/tests/__init__.py` as empty file.

Create `mcp-gateway/tests/conftest.py` with:
```python
"""Shared test fixtures for mcp-gateway."""
from __future__ import annotations
import os
import secrets
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP


@pytest.fixture
def bearer_token() -> str:
    """Deterministic-per-test bearer token used by auth fixtures."""
    return secrets.token_urlsafe(16)


@pytest.fixture
def tmp_upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setenv("MCP_GATEWAY_UPLOAD_DIR", str(d))
    return d


@pytest.fixture
def tmp_status_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "status"
    d.mkdir()
    monkeypatch.setenv("MCP_GATEWAY_STATUS_DIR", str(d))
    return d


@pytest.fixture
def fake_backend_mcp() -> FastMCP:
    """In-memory MCP server standing in for a real BN/Ghidra/IDA backend."""
    fake = FastMCP("fake-backend", stateless_http=True)

    @fake.tool()
    def list_funcs() -> list[str]:
        return ["main", "init", "doWork"]

    @fake.tool()
    def decompile(function: str) -> str:
        return f"int {function}() {{ return 0; }}"

    @fake.tool()
    def xrefs_to(function: str) -> list[str]:
        return [f"ref_to_{function}_1", f"ref_to_{function}_2"]

    return fake
```

Create `mcp-gateway/tests/e2e/smoke.sh` as an executable placeholder (body filled in Plan 05):
```bash
#!/usr/bin/env bash
# E2E smoke test — full container integration.
# Body is filled in Plan 05 (Task: container integration + smoke test).
set -euo pipefail
echo "[smoke] placeholder — implement in Plan 05" >&2
exit 0
```

Create `mcp-gateway/tests/e2e/test_upload_then_analyze.sh` as an executable placeholder:
```bash
#!/usr/bin/env bash
# Upload-then-analyze e2e — POST /upload then call collect_strings(sample=<sha256>).
# Body is filled in Plan 04 / Plan 05.
set -euo pipefail
echo "[upload-then-analyze] placeholder — implement in Plan 04/05" >&2
exit 0
```

Create `mcp-gateway/README.md` with a brief operator quick-reference (6-12 lines) describing: purpose, `pip install -e mcp-gateway/`, `mcp-gateway --host 127.0.0.1 --port 8080`, env vars (`MCP_GATEWAY_TOKEN`, `MCP_GATEWAY_HOST`, `MCP_GATEWAY_PORT`, `MCP_GATEWAY_MAX_UPLOAD_MB`, `MCP_GATEWAY_QUIET`), and auth header format.

chmod 0755 both e2e shell scripts.
  </action>
  <verify>
    <automated>pip install -e mcp-gateway/ && python -c "import mcp_gateway; print(mcp_gateway.__version__)" && pytest mcp-gateway/tests/ --collect-only -q</automated>
  </verify>
  <acceptance_criteria>
    - File `mcp-gateway/pyproject.toml` exists and contains string `mcp>=1.27,<1.28` (tight pin per checker: keeps reliance on `_tool_manager` stable until we migrate to public client API)
    - File `mcp-gateway/pyproject.toml` contains string `asyncio_mode = "auto"`
    - File `mcp-gateway/pyproject.toml` contains `mcp-gateway = "mcp_gateway.cli:main"`
    - `pip install -e mcp-gateway/` exits 0
    - `python -c "import mcp_gateway; assert mcp_gateway.__version__ == '0.1.0'"` exits 0
    - `pytest mcp-gateway/tests/ --collect-only -q` exits 0 (no collection errors)
    - `test -x mcp-gateway/tests/e2e/smoke.sh` succeeds (0755)
    - `test -x mcp-gateway/tests/e2e/test_upload_then_analyze.sh` succeeds
    - `grep -c 'bearer_token\|tmp_upload_dir\|tmp_status_dir\|fake_backend_mcp' mcp-gateway/tests/conftest.py` is >= 4
    - `python -c "from mcp_gateway.session_state import PINNED_BACKEND, ACTIVE_CASE; assert PINNED_BACKEND is None and ACTIVE_CASE is None"` exits 0
  </acceptance_criteria>
  <done>Package installable, all Wave 0 stubs present, test collection green, session state module initialized.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Auth module (token lifecycle + BearerAuthMiddleware + OriginMiddleware) and CLI</name>
  <files>
    mcp-gateway/src/mcp_gateway/auth.py,
    mcp-gateway/src/mcp_gateway/cli.py,
    mcp-gateway/tests/test_auth.py,
    mcp-gateway/tests/test_cli.py
  </files>
  <read_first>
    - mcp-gateway/src/mcp_gateway/auth.py (confirm absent before write — Task 1 did not create it)
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Pattern 3 Bearer Auth Middleware, § Example 3 auth.py, § Pitfall 7 token leak, § Pitfall 8 Origin bypass)
    - .planning/phases/02-mcp-gateway/02-CONTEXT.md (D-16 env-var-wins, D-17 token file + log line + MCP_GATEWAY_QUIET, D-19 127.0.0.1 default, D-20 port 8080)
    - .planning/phases/02-mcp-gateway/02-VALIDATION.md (rows for GW-04 and GW-05)
  </read_first>
  <behavior>
    - `load_or_generate_token()` with `MCP_GATEWAY_TOKEN=abc` → returns `"abc"`
    - `load_or_generate_token()` with unset env → returns 43-char URL-safe string (secrets.token_urlsafe(32))
    - Token file has mode 0o600 after `load_or_generate_token()` call (T-02-TOKENLEAK mitigation)
    - `MCP_GATEWAY_QUIET=1` → no `[gateway] Bearer token:` log line emitted; file still written
    - `BearerAuthMiddleware` — GET `/healthz` without Authorization → 200 (T-02-AUTH open endpoint)
    - `BearerAuthMiddleware` — POST `/mcp` without Authorization → 401 with body `{"error": "missing bearer token"}` (T-02-AUTH mitigation)
    - `BearerAuthMiddleware` — POST `/upload` without Authorization → 401 (T-02-AUTH mitigation for upload path)
    - `BearerAuthMiddleware` — POST `/mcp` with wrong bearer → 401
    - `BearerAuthMiddleware` — POST `/mcp` with correct bearer → 200 (forwarded to inner app)
    - `BearerAuthMiddleware.dispatch` uses `hmac.compare_digest` (constant-time)
    - `OriginMiddleware` — Origin `http://127.0.0.1:3000` → 200
    - `OriginMiddleware` — Origin `http://localhost:8080` → 200
    - `OriginMiddleware` — Origin `null` → 200
    - `OriginMiddleware` — no Origin header → 200
    - `OriginMiddleware` — Origin `http://evil.com` → 403 (T-02-AUTH DNS rebind protection)
    - `cli.main(argv=[])` sets host=127.0.0.1, port=8080 when env unset (T-02-NET localhost default)
    - `cli.main(argv=[])` sets host=0.0.0.0 when `MCP_GATEWAY_HOST=0.0.0.0`
    - `cli.main(argv=[])` sets port=9090 when `MCP_GATEWAY_PORT=9090`
  </behavior>
  <action>
Create `mcp-gateway/src/mcp_gateway/auth.py` with EXACTLY this structure (based on RESEARCH Example 3, verbatim adaptation):

```python
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

    Allow Origin starting with http://127.0.0.1 or http://localhost, or literal "null",
    or missing Origin (non-browser client). Reject everything else with 403.
    T-02-NET mitigation.
    """

    ALLOWED_PREFIXES = ("http://127.0.0.1", "http://localhost")

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        if origin is None or origin == "null":
            return await call_next(request)
        if any(origin.startswith(p) for p in self.ALLOWED_PREFIXES):
            return await call_next(request)
        return JSONResponse({"error": "forbidden origin"}, status_code=403)
```

Create `mcp-gateway/src/mcp_gateway/cli.py`:

```python
"""Gateway CLI entry point. Invoked as `mcp-gateway` or `python -m mcp_gateway`."""
from __future__ import annotations
import argparse
import logging
import os
from typing import Sequence

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mcp-gateway", description="MARE MCP gateway daemon")
    p.add_argument(
        "--host",
        default=os.environ.get("MCP_GATEWAY_HOST", DEFAULT_HOST),
        help=f"Bind host (default: env MCP_GATEWAY_HOST or {DEFAULT_HOST})",
    )
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MCP_GATEWAY_PORT", str(DEFAULT_PORT))),
        help=f"Bind port (default: env MCP_GATEWAY_PORT or {DEFAULT_PORT})",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s: %(message)s")

    # Lazy import so `--help` works without pulling the whole Starlette app chain.
    from .app import build_app  # noqa: F401  — Plan 02 creates build_app
    import uvicorn

    app = build_app()
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `mcp-gateway/tests/test_auth.py`:

```python
"""Tests for load_or_generate_token + BearerAuthMiddleware + OriginMiddleware.

Maps to: .planning/phases/02-mcp-gateway/02-VALIDATION.md rows GW-04 (all).
"""
from __future__ import annotations
import os
import stat
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mcp_gateway.auth import (
    BearerAuthMiddleware,
    OriginMiddleware,
    load_or_generate_token,
)


def _build_test_app(token: str) -> Starlette:
    async def mcp_ok(request):
        return JSONResponse({"ok": True})

    async def upload_ok(request):
        return JSONResponse({"ok": True})

    async def health_ok(request):
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[
            Route("/mcp", mcp_ok, methods=["POST"]),
            Route("/upload", upload_ok, methods=["POST"]),
            Route("/healthz", health_ok, methods=["GET"]),
        ]
    )
    app.add_middleware(BearerAuthMiddleware, token=token)
    return app


# -------- load_or_generate_token --------

def test_env_var_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "supersecret-from-env")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / "tok"))
    assert load_or_generate_token() == "supersecret-from-env"


def test_generated_token_when_env_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("MCP_GATEWAY_TOKEN", raising=False)
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / "tok"))
    tok = load_or_generate_token()
    assert len(tok) >= 32
    # token_urlsafe(32) is 43 characters URL-safe base64 without padding.
    assert isinstance(tok, str)


def test_token_file_is_0600(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "t")
    tok_path = tmp_path / "tok"
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tok_path))
    load_or_generate_token()
    assert tok_path.exists()
    mode = stat.S_IMODE(tok_path.stat().st_mode)
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


def test_quiet_suppresses_log(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "t")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / "tok"))
    monkeypatch.setenv("MCP_GATEWAY_QUIET", "1")
    caplog.set_level("INFO", logger="mcp_gateway.auth")
    load_or_generate_token()
    assert not any("Bearer token:" in r.getMessage() for r in caplog.records)


# -------- BearerAuthMiddleware --------

def test_health_open(bearer_token):
    with TestClient(_build_test_app(bearer_token)) as client:
        r = client.get("/healthz")
        assert r.status_code == 200


def test_mcp_requires_bearer(bearer_token):
    with TestClient(_build_test_app(bearer_token)) as client:
        r = client.post("/mcp", json={})
        assert r.status_code == 401
        assert "missing bearer token" in r.text


def test_upload_requires_bearer(bearer_token):
    with TestClient(_build_test_app(bearer_token)) as client:
        r = client.post("/upload", content=b"x")
        assert r.status_code == 401


def test_valid_bearer_ok(bearer_token):
    with TestClient(_build_test_app(bearer_token)) as client:
        r = client.post("/mcp", json={}, headers={"Authorization": f"Bearer {bearer_token}"})
        assert r.status_code == 200


def test_invalid_bearer_rejected(bearer_token):
    with TestClient(_build_test_app(bearer_token)) as client:
        r = client.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401
        assert "invalid bearer token" in r.text


# -------- OriginMiddleware --------

def _app_with_origin_only() -> Starlette:
    async def ok(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", ok, methods=["POST"])])
    app.add_middleware(OriginMiddleware)
    return app


def test_origin_localhost_allowed():
    with TestClient(_app_with_origin_only()) as client:
        r = client.post("/mcp", json={}, headers={"Origin": "http://127.0.0.1:3000"})
        assert r.status_code == 200


def test_origin_null_allowed():
    with TestClient(_app_with_origin_only()) as client:
        r = client.post("/mcp", json={}, headers={"Origin": "null"})
        assert r.status_code == 200


def test_origin_missing_allowed():
    with TestClient(_app_with_origin_only()) as client:
        r = client.post("/mcp", json={})
        assert r.status_code == 200


def test_origin_evil_rejected():
    with TestClient(_app_with_origin_only()) as client:
        r = client.post("/mcp", json={}, headers={"Origin": "http://evil.com"})
        assert r.status_code == 403
```

Create `mcp-gateway/tests/test_cli.py`:

```python
"""Tests for CLI defaults (host, port). Maps to GW-05 rows in VALIDATION.md."""
from __future__ import annotations

from mcp_gateway.cli import build_parser, DEFAULT_HOST, DEFAULT_PORT


def test_default_bind_is_localhost(monkeypatch):
    monkeypatch.delenv("MCP_GATEWAY_HOST", raising=False)
    monkeypatch.delenv("MCP_GATEWAY_PORT", raising=False)
    args = build_parser().parse_args([])
    assert args.host == DEFAULT_HOST == "127.0.0.1"
    assert args.port == DEFAULT_PORT == 8080


def test_env_overrides_bind(monkeypatch):
    monkeypatch.setenv("MCP_GATEWAY_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_GATEWAY_PORT", "9090")
    args = build_parser().parse_args([])
    assert args.host == "0.0.0.0"
    assert args.port == 9090


def test_cli_flags_override_env(monkeypatch):
    monkeypatch.setenv("MCP_GATEWAY_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_GATEWAY_PORT", "9090")
    args = build_parser().parse_args(["--host", "127.0.0.1", "--port", "8080"])
    assert args.host == "127.0.0.1"
    assert args.port == 8080
```
  </action>
  <verify>
    <automated>pytest mcp-gateway/tests/test_auth.py mcp-gateway/tests/test_cli.py -x --no-header -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest mcp-gateway/tests/test_auth.py -x --no-header -q` exits 0
    - `pytest mcp-gateway/tests/test_cli.py -x --no-header -q` exits 0
    - `grep -c "hmac.compare_digest" mcp-gateway/src/mcp_gateway/auth.py` == 1
    - `grep -c "secrets.token_urlsafe(32)" mcp-gateway/src/mcp_gateway/auth.py` == 1
    - `grep -c "0o600" mcp-gateway/src/mcp_gateway/auth.py` >= 1
    - `grep -q 'PROTECTED_PREFIXES = ("/mcp", "/upload")' mcp-gateway/src/mcp_gateway/auth.py`
    - `grep -q '"127.0.0.1"' mcp-gateway/src/mcp_gateway/cli.py`
    - `grep -q 'DEFAULT_PORT = 8080' mcp-gateway/src/mcp_gateway/cli.py`
    - `grep -q "MCP_GATEWAY_QUIET" mcp-gateway/src/mcp_gateway/auth.py`
  </acceptance_criteria>
  <done>Auth module + CLI scaffold in place; all 14 unit tests green; token never logged when quiet; file is 0600.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Backend detection module + tests</name>
  <files>
    mcp-gateway/src/mcp_gateway/backend/detect.py,
    mcp-gateway/tests/test_detect.py
  </files>
  <read_first>
    - docker-bin/configure-agent-mcp.sh (lines 67-119 — authoritative priority chain to mirror)
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Code Example 4 — detect.py skeleton)
    - .planning/phases/02-mcp-gateway/02-CONTEXT.md (D-09 pinned backend, canonical_refs — configure-agent-mcp.sh authoritative)
    - .planning/phases/01-ida-pro-backend/01-CONTEXT.md (Phase 1 D-06 no silent fallback policy)
  </read_first>
  <behavior>
    - `detect_backend()` returns `"ida"` when `/opt/ida-pro` is a non-empty dir AND `shutil.which("idalib-mcp")` is truthy
    - `detect_backend()` returns `"bn"` when IDA path fails AND `/opt/binaryninja/scripts/install_api.py` exists AND `/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py` exists
    - `detect_backend()` returns `"ghidra"` when above fail AND `/agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py` exists
    - `detect_backend()` raises `RuntimeError("No disassembler backend available (checked IDA, BN, Ghidra)")` when all fail
    - Priority is IDA > BN > Ghidra (matches configure-agent-mcp.sh lines 67-119, NOT the stale REQUIREMENTS.md GW-03 wording)
  </behavior>
  <action>
Create `mcp-gateway/src/mcp_gateway/backend/detect.py` with EXACTLY this content (mirrors docker-bin/configure-agent-mcp.sh lines 67-119):

```python
"""Disassembler backend detection — IDA > BN > Ghidra (D-09).

Authoritative priority: mirrors docker-bin/configure-agent-mcp.sh lines 67-119.
NOTE: REQUIREMENTS.md GW-03 text says "BN > IDA > Ghidra" — that is stale; the actual
policy per CONTEXT.md D-09, Phase 1 D-06, and the existing bash detection is IDA > BN > Ghidra.
See .planning/phases/02-mcp-gateway/02-RESEARCH.md § Critical priority clarification.
"""
from __future__ import annotations
import shutil
from pathlib import Path

IDA_DIR = Path("/opt/ida-pro")
BN_INSTALL_API = Path("/opt/binaryninja/scripts/install_api.py")
BN_MCP_SCRIPT = Path("/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py")
GHIDRA_MCP_SCRIPT = Path("/agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py")

BACKENDS = ("ida", "bn", "ghidra")


def _ida_available() -> bool:
    if not IDA_DIR.is_dir():
        return False
    # Treat empty dir as "not installed" (matches bash `[ "$(ls -A /opt/ida-pro 2>/dev/null)" ]`).
    try:
        if not any(IDA_DIR.iterdir()):
            return False
    except PermissionError:
        return False
    return shutil.which("idalib-mcp") is not None


def _bn_available() -> bool:
    return BN_INSTALL_API.exists() and BN_MCP_SCRIPT.exists()


def _ghidra_available() -> bool:
    return GHIDRA_MCP_SCRIPT.exists()


def detect_backend() -> str:
    """Return `"ida" | "bn" | "ghidra"` per priority; raise if none installed.

    This function is pure and stateless — the result of a call is pinned by Plan 03's
    lifespan for the gateway's lifetime (D-09: no dynamic switching mid-session).
    """
    if _ida_available():
        return "ida"
    if _bn_available():
        return "bn"
    if _ghidra_available():
        return "ghidra"
    raise RuntimeError("No disassembler backend available (checked IDA, BN, Ghidra)")
```

Create `mcp-gateway/tests/test_detect.py`:

```python
"""Tests for detect_backend() priority chain.

Maps to: .planning/phases/02-mcp-gateway/02-VALIDATION.md GW-03 unit row.
Uses monkeypatching of module-level Path constants + shutil.which to avoid touching
the real filesystem (tests must run on developer laptops without IDA/BN installed).
"""
from __future__ import annotations
from pathlib import Path

import pytest

from mcp_gateway.backend import detect as detect_mod


class FakePath:
    def __init__(self, *, is_dir=False, exists=False, iter_items=()):
        self._is_dir = is_dir
        self._exists = exists
        self._iter = list(iter_items)

    def is_dir(self):
        return self._is_dir

    def exists(self):
        return self._exists

    def iterdir(self):
        return iter(self._iter)


def _patch_state(monkeypatch, *, ida=False, bn=False, ghidra=False, ida_cmd=True):
    monkeypatch.setattr(
        detect_mod, "IDA_DIR",
        FakePath(is_dir=ida, iter_items=(["x"] if ida else [])),
    )
    monkeypatch.setattr(detect_mod, "BN_INSTALL_API", FakePath(exists=bn))
    monkeypatch.setattr(detect_mod, "BN_MCP_SCRIPT", FakePath(exists=bn))
    monkeypatch.setattr(detect_mod, "GHIDRA_MCP_SCRIPT", FakePath(exists=ghidra))
    monkeypatch.setattr(
        detect_mod.shutil, "which",
        lambda name: "/usr/local/bin/idalib-mcp" if (name == "idalib-mcp" and ida_cmd) else None,
    )


def test_priority_ida_wins_when_all_installed(monkeypatch):
    _patch_state(monkeypatch, ida=True, bn=True, ghidra=True)
    assert detect_mod.detect_backend() == "ida"


def test_bn_selected_when_ida_dir_empty(monkeypatch):
    _patch_state(monkeypatch, ida=False, bn=True, ghidra=True)
    assert detect_mod.detect_backend() == "bn"


def test_bn_selected_when_idalib_mcp_command_missing(monkeypatch):
    _patch_state(monkeypatch, ida=True, ida_cmd=False, bn=True, ghidra=True)
    assert detect_mod.detect_backend() == "bn"


def test_ghidra_selected_when_ida_and_bn_absent(monkeypatch):
    _patch_state(monkeypatch, ida=False, bn=False, ghidra=True)
    assert detect_mod.detect_backend() == "ghidra"


def test_raises_when_no_backend(monkeypatch):
    _patch_state(monkeypatch, ida=False, bn=False, ghidra=False)
    with pytest.raises(RuntimeError, match="No disassembler backend available"):
        detect_mod.detect_backend()


def test_priority_matches_bash_script():
    """Smoke test: ensure BACKENDS tuple order mirrors configure-agent-mcp.sh lines 67-119."""
    assert detect_mod.BACKENDS == ("ida", "bn", "ghidra")
```
  </action>
  <verify>
    <automated>pytest mcp-gateway/tests/test_detect.py -x --no-header -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest mcp-gateway/tests/test_detect.py -x --no-header -q` exits 0
    - `grep -q 'IDA_DIR = Path("/opt/ida-pro")' mcp-gateway/src/mcp_gateway/backend/detect.py`
    - `grep -q 'BN_MCP_SCRIPT = Path("/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py")' mcp-gateway/src/mcp_gateway/backend/detect.py`
    - `grep -q 'GHIDRA_MCP_SCRIPT = Path("/agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py")' mcp-gateway/src/mcp_gateway/backend/detect.py`
    - `grep -q 'idalib-mcp' mcp-gateway/src/mcp_gateway/backend/detect.py`
    - `grep -q 'BACKENDS = ("ida", "bn", "ghidra")' mcp-gateway/src/mcp_gateway/backend/detect.py`
    - `python -c "from mcp_gateway.backend.detect import detect_backend, BACKENDS; assert BACKENDS == ('ida','bn','ghidra')"` exits 0
  </acceptance_criteria>
  <done>detect_backend() returns correct backend per priority chain; raises cleanly on empty install; 6 tests green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| host-env → gateway process | `MCP_GATEWAY_TOKEN` env var and token-file path are trusted (operator-controlled) |
| external client → HTTP endpoints (/mcp, /upload) | Untrusted: MUST have valid bearer and allowed Origin |
| `/healthz` GET | Intentionally open — reveals nothing beyond `{"ok": true}` |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-02-AUTH | Spoofing / EoP | `BearerAuthMiddleware` on /mcp and /upload | HIGH | mitigate | Task 2: `hmac.compare_digest` constant-time compare; 401 on missing/invalid; applies to both `/mcp*` and `/upload`; `/healthz` is the only open endpoint. |
| T-02-NET | Spoofing (DNS rebind) / EoP | default bind | MEDIUM | mitigate | Task 2: `OriginMiddleware` allowlists `http://127.0.0.1`, `http://localhost`, `null`, missing. CLI defaults host=`127.0.0.1` (D-19); `MCP_GATEWAY_HOST=0.0.0.0` is explicit opt-in. |
| T-02-TOKENLEAK | Information Disclosure | token file / logs | MEDIUM | mitigate | Task 2: `os.open(..., 0o600)` + `os.chmod(0o600)` on token file (D-17); `MCP_GATEWAY_QUIET=1` suppresses log line; uvicorn `access_log=False` in `cli.main` (Task 2); `Authorization` never logged. |
| T-02-SUBPROC | Tampering / RCE | (deferred to Plan 02) | HIGH | transfer | Plan 02 will enforce `asyncio.create_subprocess_exec(*argv)` — no shell, no string interpolation. Not applicable to this plan (no subprocess code). |
| T-02-PATHTRAVERSAL | Tampering / EoP | (deferred to Plan 02/04) | HIGH | transfer | Plan 02 (`resolve_sample`) + Plan 04 (upload filename) will canonicalize paths and reject `..`. Not applicable to this plan. |
| T-02-UPLOAD | DoS | (deferred to Plan 04) | HIGH | transfer | Plan 04 will enforce `MCP_GATEWAY_MAX_UPLOAD_MB` cap via streaming. Not applicable to this plan. |
</threat_model>

<verification>
After all 3 tasks:
1. `pytest mcp-gateway/tests/ -v --no-header` — ALL tests green (Tasks 1, 2, 3 combined ~20 test cases)
2. `ruff check mcp-gateway/src/ mcp-gateway/tests/` — no errors
3. `pip install -e mcp-gateway/ && python -m mcp_gateway --help` — prints argparse help and exits 0 (build_app import will fail here; catch: cli.py imports build_app lazily inside main(), --help should still work since argparse runs before main's body)
4. Token file permissions: `test -f /tmp/pytest-of-*/tok && stat -c %a /tmp/pytest-of-*/tok` should print `600`
5. `grep -c "hmac.compare_digest" mcp-gateway/src/mcp_gateway/auth.py` == 1
</verification>

<success_criteria>
- Package `mcp_gateway` installed in editable mode; `import mcp_gateway` and `from mcp_gateway.auth import load_or_generate_token, BearerAuthMiddleware, OriginMiddleware` both succeed
- `from mcp_gateway.backend.detect import detect_backend` succeeds and function follows IDA > BN > Ghidra priority (T-02-NET fidelity to bash)
- All auth tests pass, including: `/mcp` unauth → 401, `/upload` unauth → 401, `/healthz` open, valid bearer passes, invalid bearer → 401, Origin DNS-rebind protection works
- Token file is mode 0600 on disk; no bearer token in logs when `MCP_GATEWAY_QUIET=1`
- CLI defaults: host=127.0.0.1, port=8080 (D-19, D-20)
- Wave 0 test infra ready: conftest.py has `bearer_token`, `tmp_upload_dir`, `tmp_status_dir`, `fake_backend_mcp` fixtures; e2e shell stubs exist
- `pytest mcp-gateway/tests/ --collect-only` shows 20+ tests
</success_criteria>

<output>
After completion, create `.planning/phases/02-mcp-gateway/02-01-SUMMARY.md` per `$HOME/.claude/get-shit-done/templates/summary.md`.
Include:
- Files created: every file in frontmatter `files_modified`
- Tests added (with counts): test_auth.py (14), test_cli.py (3), test_detect.py (6)
- Decision fidelity: D-16/D-17/D-18/D-19/D-20 all implemented; D-09 priority chain mirrored in detect.py
- Threat mitigations: T-02-AUTH (auth.py), T-02-NET (OriginMiddleware + CLI default), T-02-TOKENLEAK (0600 + QUIET)
- Handoff: Plans 02/03/04 can `from mcp_gateway.auth import BearerAuthMiddleware, OriginMiddleware, load_or_generate_token` and `from mcp_gateway.backend.detect import detect_backend`
</output>
