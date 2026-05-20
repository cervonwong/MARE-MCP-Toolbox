"""Public re-exports of every Phase 8 + Phase 11 session symbol.

Phase 8 callers (`from mcp_gateway.sessions import X`) continue to work
via this re-export -- see CONTEXT.md D-01 and RESEARCH.md Pitfall #11.

DO NOT use `from .X import *` -- Pitfall #11 specifies explicit names
for deterministic reload semantics (and grep-friendly auditing).
"""
from __future__ import annotations

import importlib
import sys

# Force-reload submodules when this package is reloaded so env-var
# validation in _base.py re-runs. Python's `from X import Y` only fetches
# already-loaded modules from sys.modules; without this explicit reload,
# `importlib.reload(mcp_gateway.sessions)` would NOT re-read env vars and
# the Phase 8 D-14 test `test_env_var_bad_value_raises` would silently pass.
# This preserves the exact Phase 8 reload semantics that the monolithic
# sessions.py provided.
for _submod in ("mcp_gateway.sessions._base", "mcp_gateway.sessions.r2"):
    _m = sys.modules.get(_submod)
    if _m is not None:
        importlib.reload(_m)

from ._base import (
    SessionRegistry,
    BaseSession,
    SessionCapReached,
    SESSION_IDLE_S,
    MAX_SESSIONS,
    R2_CMD_TIMEOUT_S,
    REAPER_INTERVAL_S,
    SESSION_OPEN_TIMEOUT_S,
    _env_int,
    _env_float,
    _ANSI_ESCAPE_TEXT,
    strip_ansi,
    truncate_for_response,
    make_sentinel,
)
from .r2 import (
    R2Session,
    _DANGEROUS_R2_CMD_RE,
    check_dangerous_cmd,
)
# Plan 03 will add `from .gdb import GdbSession, GDB_CMD_TIMEOUT_S, GDB_OPEN_TIMEOUT_S`.
# Until Plan 03 lands, gdb path is unreachable and `kind="gdb"` raises a
# deferred ImportError inside SessionRegistry.open's gdb branch.

__all__ = [
    # _base
    "SessionRegistry", "BaseSession", "SessionCapReached",
    "SESSION_IDLE_S", "MAX_SESSIONS", "R2_CMD_TIMEOUT_S",
    "REAPER_INTERVAL_S", "SESSION_OPEN_TIMEOUT_S",
    "_env_int", "_env_float", "_ANSI_ESCAPE_TEXT",
    "strip_ansi", "truncate_for_response", "make_sentinel",
    # r2
    "R2Session", "_DANGEROUS_R2_CMD_RE", "check_dangerous_cmd",
]
