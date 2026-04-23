"""Module-level gateway state (Phase 2 single-session model).

v2 (GW-V2-03) will replace this with per-client-session state keyed off Mcp-Session-Id.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .backend.client import PinnedBackend  # created in Plan 03

PINNED_BACKEND: Optional["PinnedBackend"] = None
ACTIVE_CASE: Optional[str] = None
