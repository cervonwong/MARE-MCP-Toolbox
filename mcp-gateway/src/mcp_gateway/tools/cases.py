"""Case management + upload browsing tools (5 tools: list_cases, set_active_case,
get_active_case, list_uploads, get_sample_info).
"""
from __future__ import annotations
import hashlib
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .. import session_state
from .samples import UPLOADS_ROOT, STATUS_ROOT, resolve_sample

CASE_NAME_RE = re.compile(r"^\d{3}-.+")


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_cases() -> list[dict]:
        """Enumerate analysis cases under /agent/status/. Each case dir name is NNN-<filename>."""
        if not STATUS_ROOT.exists():
            return []
        items: list[dict] = []
        for p in sorted(STATUS_ROOT.iterdir()):
            if p.is_dir() and CASE_NAME_RE.match(p.name):
                items.append({
                    "name": p.name,
                    "path": str(p),
                    "mtime": p.stat().st_mtime,
                })
        return items

    @mcp.tool()
    def set_active_case(case: str) -> dict:
        """Set the per-session active case (directory name like '001-foo.bin' or absolute path)."""
        session_state.ACTIVE_CASE = case
        return {"active_case": case}

    @mcp.tool()
    def get_active_case() -> dict:
        """Return the currently-active case for this session (or null)."""
        return {"active_case": session_state.ACTIVE_CASE}

    @mcp.tool()
    def list_uploads() -> list[dict]:
        """Enumerate /agent/uploads/<sha256>/*.bin entries."""
        if not UPLOADS_ROOT.exists():
            return []
        items: list[dict] = []
        for sha_dir in sorted(UPLOADS_ROOT.iterdir()):
            if sha_dir.is_dir() and len(sha_dir.name) == 64:
                for f in sha_dir.iterdir():
                    if f.is_file() and not f.name.startswith("."):
                        items.append({
                            "sha256": sha_dir.name,
                            "filename": f.name,
                            "path": str(f),
                            "size": f.stat().st_size,
                        })
        return items

    @mcp.tool()
    def get_sample_info(sample: str) -> dict:
        """Return {sha256, size, path} for a sample (sha256 id or container path)."""
        path = resolve_sample(sample)
        p = Path(path)
        sha = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return {
            "sha256": sha.hexdigest(),
            "size": p.stat().st_size,
            "path": str(p),
        }

    @mcp.tool()
    def get_active_backend() -> dict:
        """Return the disassembler backend currently pinned for this gateway lifetime.

        D-07 pass-through model: backend tools (e.g., 'decompile', 'program.open',
        'list_funcs') are registered under their NATIVE names. Clients call this
        tool to learn which backend is active so they can drive the right surface.

        Returns:
            {"backend": "ida" | "bn" | "ghidra" | "none"}
        """
        pinned = session_state.PINNED_BACKEND
        if pinned is None:
            return {"backend": "none"}
        # PinnedBackend exposes both `.backend` (canonical, set in __init__) and
        # `.name` (public alias). Prefer `.backend`; fall back to `.name` defensively.
        name = getattr(pinned, "backend", None) or getattr(pinned, "name", None) or "unknown"
        return {"backend": str(name)}
