"""Unified-name -> backend-tool-name mapping for the 3 disassembler unified tools.

Research: .planning/phases/02-mcp-gateway/02-RESEARCH.md Tool Surface Design -> Disassembler tools.
D-07: client only ever sees unified verb-first names; backend-specific names are hidden.

NOTE: BN tool names should be verified by grepping the vendored submodule at
`/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py` inside the
container. Placeholder values below use the unified name as a fallback -- the
installer (Plan 05) verifies by running `tools/list` against the BN backend at
container startup and logs a warning if any unified tool maps to a missing backend tool.
"""
from __future__ import annotations
from typing import Callable

# Mapping layout: { unified_name: { backend: (backend_tool_name, args_transform) } }
# args_transform is a callable that maps unified args dict -> backend args dict.
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
