"""Module-level gateway state (Phase 2 single-session model).

v2 (GW-V2-03) will replace this with per-client-session state keyed off Mcp-Session-Id.

Phase 8 SESS-05 consequence: SESSION_REGISTRY (the r2-session registry) is also
module-level -- r2 sessions are shared across every MCP client connected with the
same bearer token. The shared-across-bearer-token-clients caveat is documented in
the tools/r2_sessions.py docstrings per Phase 8 D-23.

Phase 9 D-07 consequence: JOB_REGISTRY (the background-job registry) is ALSO
module-level -- jobs are shared across every MCP client with the same bearer
token. Any client can see, cancel, and inspect any job_id. The shared-across-
bearer-token-clients caveat is documented in the tools/jobs.py docstrings via
the D-26 disclaimer.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .backend.client import PinnedBackend  # created in Plan 03
    from .sessions import SessionRegistry      # Phase 8 D-07
    from .jobs import BackgroundJobRegistry    # Phase 9 D-07

PINNED_BACKEND: Optional["PinnedBackend"] = None
ACTIVE_CASE: Optional[str] = None
SESSION_REGISTRY: Optional["SessionRegistry"] = None         # Phase 8 D-07
JOB_REGISTRY: Optional["BackgroundJobRegistry"] = None       # Phase 9 D-07
