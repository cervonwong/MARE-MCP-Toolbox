"""Phase 11 Plan 01 Wave-0 regression tests for the sessions/ package refactor.

These tests verify that splitting the monolithic `sessions.py` into a
`sessions/` package (per CONTEXT.md D-01..D-03 and RESEARCH.md Pitfall #11)
preserves the EXACT Phase 8 public surface:
- Every Phase 8 symbol still importable from `mcp_gateway.sessions`.
- `R2Session` / `SessionRegistry` / `_DANGEROUS_R2_CMD_RE` are the SAME
  object whether imported from the package root or the submodule.
- A new `BaseSession` dataclass exists in `sessions._base` and `R2Session`
  subclasses it.
- `SessionRegistry.open` gains a `kind: Literal['r2','gdb']` kwarg with
  default `"r2"` for backward compatibility.
- The legacy `sessions.py` is DELETED (replaced by the package directory).
- `importlib.reload(mcp_gateway.sessions)` does not raise.

These tests are RED before Task 2 lands (sessions.py still exists,
sessions._base does not exist, etc.) and flip GREEN after Task 2.
"""
from __future__ import annotations

import dataclasses
import importlib
import inspect
from pathlib import Path

import mcp_gateway


def test_reexports_phase8_symbols():
    """Every Phase 8 public symbol is importable from `mcp_gateway.sessions`."""
    import mcp_gateway.sessions as s

    expected_names = [
        "SessionRegistry",
        "R2Session",
        "_DANGEROUS_R2_CMD_RE",
        "check_dangerous_cmd",
        "SessionCapReached",
        "strip_ansi",
        "truncate_for_response",
        "MAX_SESSIONS",
        "SESSION_IDLE_S",
        "REAPER_INTERVAL_S",
        "R2_CMD_TIMEOUT_S",
        "SESSION_OPEN_TIMEOUT_S",
        "_env_int",
        "_env_float",
        "_ANSI_ESCAPE_TEXT",
    ]
    for name in expected_names:
        assert hasattr(s, name), f"mcp_gateway.sessions missing symbol: {name}"


def test_r2session_identity():
    """R2Session is the SAME object via package root and submodule."""
    from mcp_gateway.sessions import R2Session as A
    from mcp_gateway.sessions.r2 import R2Session as B
    assert A is B, "R2Session must be re-exported (same object), not duplicated"


def test_session_registry_identity():
    """SessionRegistry is the SAME object via package root and _base submodule."""
    from mcp_gateway.sessions import SessionRegistry as A
    from mcp_gateway.sessions._base import SessionRegistry as B
    assert A is B, "SessionRegistry must be re-exported (same object), not duplicated"


def test_dangerous_regex_identity():
    """_DANGEROUS_R2_CMD_RE is the SAME object via package root and r2 submodule."""
    from mcp_gateway.sessions import _DANGEROUS_R2_CMD_RE as A
    from mcp_gateway.sessions.r2 import _DANGEROUS_R2_CMD_RE as B
    assert A is B, "_DANGEROUS_R2_CMD_RE must be re-exported, not re-compiled"


def test_basesession_dataclass_exists():
    """BaseSession dataclass exists in sessions._base with the locked field set."""
    from mcp_gateway.sessions._base import BaseSession
    assert dataclasses.is_dataclass(BaseSession), "BaseSession must be a dataclass"
    names = {f.name for f in dataclasses.fields(BaseSession)}
    required = {
        "session_id", "case_dir", "pgid", "lock", "opened_at", "opened_iso",
        "last_used_at", "command_count", "closed", "close_reason",
        "transcript_path", "proc", "sentinel", "kind",
    }
    missing = required - names
    assert not missing, f"BaseSession missing required fields: {missing}"


def test_r2session_subclasses_basesession():
    """R2Session is a subclass of BaseSession (kind-agnostic ancestor)."""
    from mcp_gateway.sessions._base import BaseSession
    from mcp_gateway.sessions.r2 import R2Session
    assert issubclass(R2Session, BaseSession), \
        "R2Session must subclass BaseSession for kind-agnostic registry storage"


def test_reload_succeeds():
    """importlib.reload(mcp_gateway.sessions) does not raise."""
    import mcp_gateway.sessions as s
    # Reload should not raise. After reload, the re-exported SessionRegistry
    # must still be identical to the one defined in _base.
    importlib.reload(s)
    import mcp_gateway.sessions._base as base
    importlib.reload(base)
    # After reloading both, the package-root re-import again to refresh binding.
    importlib.reload(s)
    assert s.SessionRegistry is base.SessionRegistry, \
        "after reload, sessions.SessionRegistry must match sessions._base.SessionRegistry"


def test_phase8_callers_still_work():
    """The exact app.py:22-27 import statement continues to work post-refactor."""
    from mcp_gateway.sessions import (
        SessionRegistry,
        MAX_SESSIONS,
        SESSION_IDLE_S,
        REAPER_INTERVAL_S,
    )
    assert callable(SessionRegistry), "SessionRegistry must be a class/callable"
    assert isinstance(MAX_SESSIONS, int), f"MAX_SESSIONS must be int, got {type(MAX_SESSIONS)}"
    assert isinstance(SESSION_IDLE_S, float), \
        f"SESSION_IDLE_S must be float, got {type(SESSION_IDLE_S)}"
    assert isinstance(REAPER_INTERVAL_S, float), \
        f"REAPER_INTERVAL_S must be float, got {type(REAPER_INTERVAL_S)}"


def test_no_legacy_sessions_py():
    """The legacy sessions.py file MUST be deleted post-refactor (replaced by sessions/)."""
    legacy = Path(mcp_gateway.__file__).parent / "sessions.py"
    assert not legacy.exists(), \
        f"legacy sessions.py still exists at {legacy}; refactor must delete it"


def test_registry_open_accepts_kind_kwarg():
    """SessionRegistry.open accepts kind: Literal['r2','gdb'] with default 'r2'."""
    from mcp_gateway.sessions import SessionRegistry
    sig = inspect.signature(SessionRegistry.open)
    assert "kind" in sig.parameters, \
        f"SessionRegistry.open missing 'kind' param; params={list(sig.parameters)!r}"
    param = sig.parameters["kind"]
    assert param.default == "r2", \
        f"SessionRegistry.open 'kind' default must be 'r2' for backward compat; got {param.default!r}"
