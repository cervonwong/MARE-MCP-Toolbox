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
for _submod in (
    "mcp_gateway.sessions._base",
    "mcp_gateway.sessions.r2",
    "mcp_gateway.sessions.gdb",
):
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
# Phase 11 Plan 03 addition: gdb-MI3 session driver.
from .gdb import (
    GdbSession,
    GDB_OPEN_TIMEOUT_S,
    GDB_CMD_TIMEOUT_S,
    validate_mi_command,
)

__all__ = [
    # _base
    "SessionRegistry", "BaseSession", "SessionCapReached",
    "SESSION_IDLE_S", "MAX_SESSIONS", "R2_CMD_TIMEOUT_S",
    "REAPER_INTERVAL_S", "SESSION_OPEN_TIMEOUT_S",
    "_env_int", "_env_float", "_ANSI_ESCAPE_TEXT",
    "strip_ansi", "truncate_for_response", "make_sentinel",
    # r2
    "R2Session", "_DANGEROUS_R2_CMD_RE", "check_dangerous_cmd",
    # gdb (Phase 11 Plan 03)
    "GdbSession", "GDB_OPEN_TIMEOUT_S", "GDB_CMD_TIMEOUT_S",
    "validate_mi_command",
]

# Phase 14 D-02: ensure `mcp_gateway.sessions.r2` and `mcp_gateway.sessions.gdb`
# remain accessible as PACKAGE ATTRIBUTES (e.g. `mcp_gateway.sessions.r2`)
# after the reload sweep above runs. The explicit `from .r2 import ...` /
# `from .gdb import ...` statements bind symbols from those submodules but do
# not guarantee the submodule itself stays bound as a package attribute when
# `importlib.reload(mcp_gateway.sessions._base)` is invoked from tests
# (test_gdb_env_validates_bad_values pops `mcp_gateway.sessions` from
# sys.modules in its cleanup, then re-imports; the re-import path triggers
# this __init__ which previously did NOT re-establish r2/gdb attrs).
#
# `monkeypatch.setattr("mcp_gateway.sessions.r2._open_r2", ...)` in
# tests/test_sessions_concurrency.py relies on this attribute being
# present. The two assignments below restore Phase 8 behaviour explicitly.
import sys as _sys

if "mcp_gateway.sessions.r2" in _sys.modules:
    _sys.modules[__name__].r2 = _sys.modules["mcp_gateway.sessions.r2"]
if "mcp_gateway.sessions.gdb" in _sys.modules:
    _sys.modules[__name__].gdb = _sys.modules["mcp_gateway.sessions.gdb"]
