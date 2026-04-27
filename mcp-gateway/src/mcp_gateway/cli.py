"""Gateway CLI entry point. Invoked as `mcp-gateway` or `python -m mcp_gateway`."""
from __future__ import annotations
import argparse
import logging
import os
from typing import Sequence

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


def _default_port() -> int:
    raw = os.environ.get("MCP_GATEWAY_PORT", str(DEFAULT_PORT))
    try:
        port = int(raw)
    except ValueError as e:
        raise RuntimeError(
            f"MCP_GATEWAY_PORT must be an integer, got {raw!r}"
        ) from e
    if not (0 <= port <= 65535):
        raise RuntimeError(f"MCP_GATEWAY_PORT must be in 0..65535, got {port}")
    return port


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
        default=_default_port(),
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
