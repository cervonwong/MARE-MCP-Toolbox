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
