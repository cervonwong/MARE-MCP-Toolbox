"""BackgroundJobRegistry primitive: asyncio-detached subprocess execution (Phase 9).

Public API (consumed by tools/jobs.py and app.py::lifespan):
- `BackgroundJobRegistry` -- async-context-manager (D-14). __aenter__ readies state;
  __aexit__ cancels every in-flight job (SIGTERM-grace-SIGKILL ladder) in parallel.
- `Job`, `JobToolSpec` dataclasses; `JobStatus` Literal vocabulary (D-06).
- `JOB_TOOL_REGISTRY: dict[str, JobToolSpec]` + `register_job_tool(spec)` (D-02, D-03).
- `JobCapReached`, `UnknownJobTool`, `JobNotFound`, `InvalidKwargs` error types (D-15).
- 10 module constants read once from env (D-13).

Design contract (locked per D-01..D-26 + RESEARCH Q1-Q5):
- argv-only spawn via asyncio.create_subprocess_exec (JOBS-01) -- same safety properties as ReToolRunner
- `proc_callback` (Q4) is the runner.py extension; Phase 9 spawn inlines for ring-buffer/progress
- Chunked-read drain (Phase 6 precedent), per-byte counter cap (Q2 override D-09 readline pseudocode)
- In-memory ring buffers for head AND tail of stdout/stderr (Q1 override file re-parsing)
- Hand-rolled kwargs validator (Q3 -- no schema-validation dep)
- capa progress_parser=None (Q1: capa uses rich Console.status spinner, no parseable progress)
- asyncio.shield ONLY in cancel() SIGTERM-grace path (D-23)
- Tools never raise -- error dict shapes (D-15)
- Disclaimer text owned by tools/jobs.py (D-26)

This module is the layer BELOW MCP -- it does NOT import the FastMCP surface.
Plan 02 (tools/jobs.py) is the MCP surface.
"""
from __future__ import annotations

import asyncio
import collections
import dataclasses
import datetime
import json
import logging
import os
import re
import secrets
import signal
import time
from pathlib import Path
from typing import Callable, Literal, Optional

from mcp_gateway.artifacts_io import ensure_subdir, tool_log_path

log = logging.getLogger("mcp_gateway.jobs")


# ----------------------------------------------------------------------------
# Env helpers (inlined per Q4 -- avoid runner.py / sessions.py cross-import)
# ----------------------------------------------------------------------------
def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        v = int(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from e
    if v < 0:
        raise RuntimeError(f"{name} must be >= 0, got {v}")
    return v


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        v = float(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} must be a float, got {raw!r}") from e
    if v < 0:
        raise RuntimeError(f"{name} must be >= 0, got {v}")
    return v


# ----------------------------------------------------------------------------
# D-13: 10 env-read module constants. Read once at import; RuntimeError on bad.
# ----------------------------------------------------------------------------
JOB_TIMEOUT_S:      float = _env_float("MCP_GATEWAY_JOB_TIMEOUT_S",      3600.0)
JOB_MAX_TIMEOUT_S:  float = _env_float("MCP_GATEWAY_JOB_MAX_TIMEOUT_S",  86400.0)
JOB_CANCEL_GRACE_S: float = _env_float("MCP_GATEWAY_JOB_CANCEL_GRACE_S", 10.0)
MAX_JOB_LOG_MB:     int   = _env_int(  "MCP_GATEWAY_MAX_JOB_LOG_MB",     256)
MAX_JOBS_INFLIGHT:  int   = _env_int(  "MCP_GATEWAY_MAX_JOBS_INFLIGHT",  4)
MAX_COMPLETED_JOBS: int   = _env_int(  "MCP_GATEWAY_MAX_COMPLETED_JOBS", 200)
JOB_STDOUT_HEAD_KB: int   = _env_int(  "MCP_GATEWAY_JOB_STDOUT_HEAD_KB", 32)
JOB_STDOUT_TAIL_KB: int   = _env_int(  "MCP_GATEWAY_JOB_STDOUT_TAIL_KB", 32)
JOB_STDERR_HEAD_KB: int   = _env_int(  "MCP_GATEWAY_JOB_STDERR_HEAD_KB", 32)
JOB_STDERR_TAIL_KB: int   = _env_int(  "MCP_GATEWAY_JOB_STDERR_TAIL_KB", 32)

# Derived constant -- recomputed once at import; used in drain per-byte cap.
MAX_JOB_LOG_BYTES: int = MAX_JOB_LOG_MB * 1024 * 1024


# ----------------------------------------------------------------------------
# ANSI/UTF-8 helpers (inlined per Q4)
# ----------------------------------------------------------------------------
_ANSI_ESCAPE_TEXT = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_TEXT.sub("", text)


def _truncate_for_response(text: str, head_kb: int) -> str:
    max_bytes = head_kb * 1024
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    cut = encoded[:max_bytes]
    while cut and (cut[-1] & 0xC0) == 0x80:
        cut = cut[:-1]
    return cut.decode("utf-8", errors="replace")


# ----------------------------------------------------------------------------
# D-06 status vocabulary -- EXACT 7 strings, EXACT order
# ----------------------------------------------------------------------------
JobStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "killed_timeout",
    "killed_log_cap",
]

_TERMINAL_STATUSES: frozenset[str] = frozenset({
    "succeeded", "failed", "cancelled", "killed_timeout", "killed_log_cap",
})


# ----------------------------------------------------------------------------
# D-02 JobToolSpec -- EXACT 7 fields, EXACT order
# ----------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class JobToolSpec:
    name: str
    slug: str
    build_argv: Callable[[Path, dict], list[str]]
    default_timeout_s: float
    progress_parser: Optional[Callable[[bytes], Optional[tuple[int, int, str]]]]
    kwargs_schema: Optional[dict]
    description: str


# ----------------------------------------------------------------------------
# Job dataclass -- per-job mutable state
# ----------------------------------------------------------------------------
@dataclasses.dataclass
class Job:
    job_id: str
    tool: str
    spec: JobToolSpec
    kwargs: dict
    case_dir: str  # case-rel resolved string (resolve_case_dir output)
    argv: list[str]
    effective_timeout_s: float
    log_path_abs: Path
    log_path_rel: str  # case-relative for D-19 snapshot
    status: str = "pending"
    started_at_mono: Optional[float] = None
    ended_at_mono: Optional[float] = None
    started_at_iso: Optional[str] = None
    ended_at_iso: Optional[str] = None
    # Live process refs (captured at spawn-time inside _spawn_and_drive)
    proc: Optional["asyncio.subprocess.Process"] = None
    pgid: Optional[int] = None
    # Drain ring buffers (Q1: per-role, in-memory; tail uses deque(maxlen=N))
    stdout_head_buf: bytearray = dataclasses.field(default_factory=bytearray)
    stderr_head_buf: bytearray = dataclasses.field(default_factory=bytearray)
    stdout_tail_buf: "collections.deque[int]" = dataclasses.field(
        default_factory=lambda: collections.deque(maxlen=JOB_STDOUT_TAIL_KB * 1024)
    )
    stderr_tail_buf: "collections.deque[int]" = dataclasses.field(
        default_factory=lambda: collections.deque(maxlen=JOB_STDERR_TAIL_KB * 1024)
    )
    stdout_head_truncated: bool = False
    stderr_head_truncated: bool = False
    stdout_bytes_total: int = 0
    stderr_bytes_total: int = 0
    log_bytes_written: int = 0
    # Cancellation / cap flags
    _cancel_requested: bool = False
    _log_cap_exceeded: bool = False
    # Progress (D-16 + D-18)
    progress: Optional[int] = None
    progress_total: Optional[int] = None
    progress_message: Optional[str] = None
    # D-16: dedup keyed by ctx.session_id for poll-side push
    _last_reported_to: dict = dataclasses.field(default_factory=dict)
    # Optional terminal-result capture (unused when spawn is inlined; kept for symmetry)
    _terminal_result: Optional[dict] = None
    # Pitfall 2: retain drive task reference so GC does not drop it
    _drive_task: Optional[asyncio.Task] = None


# ----------------------------------------------------------------------------
# D-15 error types (Phase 8 to_dict pattern) -- four shapes
# ----------------------------------------------------------------------------
class JobCapReached(Exception):
    def __init__(self, inflight: int, cap: int):
        self.inflight, self.cap = inflight, cap
        super().__init__(f"job cap reached: inflight={inflight} cap={cap}")

    def to_dict(self) -> dict:
        return {
            "error": "job cap reached",
            "inflight": self.inflight,
            "cap": self.cap,
            "hint": "wait for an inflight job to complete or cancel one via cancel_tool_job(job_id)",
        }


class UnknownJobTool(Exception):
    def __init__(self, tool: str, known: list[str]):
        self.tool, self.known = tool, known
        super().__init__(f"unknown job tool: {tool!r}")

    def to_dict(self) -> dict:
        return {
            "error": "unknown job tool",
            "tool": self.tool,
            "known": sorted(self.known),
            "hint": "call list_tool_jobs(state='_specs') for the spec catalog",
        }


class JobNotFound(Exception):
    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__(f"job not found: {job_id!r}")

    def to_dict(self) -> dict:
        return {
            "error": "job not found (evicted from in-memory registry; gateway restart also evicts)",
            "job_id": self.job_id,
            "hint": "browse tool-logs/<ts>-<slug>-<rand4>.json via Resources for the final snapshot",
        }


class InvalidKwargs(Exception):
    def __init__(self, field: str, expected: str, got: str):
        self.field, self.expected, self.got = field, expected, got
        super().__init__(f"invalid kwargs: field={field!r} expected={expected!r} got={got!r}")

    def to_dict(self) -> dict:
        return {
            "error": "invalid kwargs",
            "field": self.field,
            "expected": self.expected,
            "got": self.got,
        }


# ----------------------------------------------------------------------------
# Hand-rolled kwargs validator (Q3 -- no schema-validation dep)
# ----------------------------------------------------------------------------
def _validate_kwargs(spec: JobToolSpec, kwargs: dict) -> None:
    """Raise InvalidKwargs(field, expected, got) on first miss; return None on success.

    Supported schema shapes (sufficient for _sleep_probe + capa + foreseeable Phase 10/11):
      {field: {"type": "integer", "min": int, "max": int}}
      {field: {"type": "string", "max_length": int}}
      {field: {"type": "string", "enum": [str, ...]}}
      {field: {"type": "boolean"}}
    Unknown fields in kwargs are ignored (forward-compatible).
    """
    if spec.kwargs_schema is None:
        return
    for field, rule in spec.kwargs_schema.items():
        if field not in kwargs:
            continue
        val = kwargs[field]
        expected = rule.get("type")
        if expected == "integer":
            if isinstance(val, bool) or not isinstance(val, int):
                raise InvalidKwargs(field, "integer", type(val).__name__)
            if "min" in rule and val < rule["min"]:
                raise InvalidKwargs(field, f">= {rule['min']}", str(val))
            if "max" in rule and val > rule["max"]:
                raise InvalidKwargs(field, f"<= {rule['max']}", str(val))
        elif expected == "string":
            if not isinstance(val, str):
                raise InvalidKwargs(field, "string", type(val).__name__)
            if "max_length" in rule and len(val) > rule["max_length"]:
                raise InvalidKwargs(field, f"length <= {rule['max_length']}", f"length {len(val)}")
            if "enum" in rule and val not in rule["enum"]:
                raise InvalidKwargs(field, f"one of {rule['enum']}", val)
        elif expected == "boolean":
            if not isinstance(val, bool):
                raise InvalidKwargs(field, "boolean", type(val).__name__)


# ----------------------------------------------------------------------------
# JOB_TOOL_REGISTRY mapping + register_job_tool (D-02)
# ----------------------------------------------------------------------------
JOB_TOOL_REGISTRY: dict[str, JobToolSpec] = {}


def register_job_tool(spec: JobToolSpec) -> None:
    """Register a JobToolSpec at module-import time.

    Idempotent: re-registering the same name with the same spec object is a no-op.
    Re-registering the same name with a different spec raises RuntimeError.
    """
    existing = JOB_TOOL_REGISTRY.get(spec.name)
    if existing is None:
        JOB_TOOL_REGISTRY[spec.name] = spec
        return
    if existing is spec:
        return
    raise RuntimeError(
        f"job tool {spec.name!r} already registered with a different spec -- "
        f"check that register_job_tool is called only once per spec"
    )


# ----------------------------------------------------------------------------
# Ship-with-Phase-9 specs (D-03 + RESEARCH Claude-Discretion-2 + D-04 + Q1 capa correction)
# ----------------------------------------------------------------------------

# ----- _sleep_probe (D-03 + RESEARCH Claude-Discretion-2; SC-4 disconnect test fixture) -----
def _build_sleep_argv(case_dir: Path, kw: dict) -> list[str]:
    return ["sleep", str(int(kw.get("seconds", 1)))]


_SLEEP_PROBE_SPEC = JobToolSpec(
    name="_sleep_probe",
    slug="sleep_probe",
    build_argv=_build_sleep_argv,
    default_timeout_s=300.0,
    progress_parser=None,
    kwargs_schema={"seconds": {"type": "integer", "min": 0, "max": 600}},
    description="Internal probe -- sleeps N seconds. Used for plumbing tests.",
)
register_job_tool(_SLEEP_PROBE_SPEC)


# ----- _log_burst_probe (RESEARCH Claude-Discretion-2; SC-3 log-cap test fixture) -----
def _build_log_burst_argv(case_dir: Path, kw: dict) -> list[str]:
    return ["sh", "-c", "while true; do head -c 1048576 /dev/urandom | base64; done"]


_LOG_BURST_PROBE_SPEC = JobToolSpec(
    name="_log_burst_probe",
    slug="log_burst_probe",
    build_argv=_build_log_burst_argv,
    default_timeout_s=120.0,
    progress_parser=None,
    kwargs_schema=None,
    description="Internal probe -- bursts /dev/urandom base64 until log cap hits. Used for SC-3 tests.",
)
register_job_tool(_LOG_BURST_PROBE_SPEC)


# ----- capa (D-04; Q1 correction: progress_parser=None, capa uses rich spinner) -----
def _build_capa_argv(case_dir: Path, kw: dict) -> list[str]:
    """Build argv for capa. kwargs: {sample: case-rel-path-or-sha256}.

    Local import of tools.samples avoids the circular cycle that would result from
    a top-level import (jobs.py is imported by tools/jobs.py which sits in the same
    package as tools/samples.py).
    """
    from mcp_gateway.tools import samples
    sample_ref = kw["sample"]
    sample_path = samples.resolve_sample(sample_ref)
    return ["capa", "--quiet", "--json", str(sample_path)]


_CAPA_SPEC = JobToolSpec(
    name="capa",
    slug="capa",
    build_argv=_build_capa_argv,
    default_timeout_s=900.0,
    progress_parser=None,  # Q1 VERIFIED: capa uses rich Console.status('dots') -- no parseable progress
    kwargs_schema={"sample": {"type": "string", "max_length": 256}},
    description=(
        "Run Mandiant's capa to identify capabilities of a binary sample. "
        "JSON output. Long-running for real samples (1-5 min typical, up to 15 min cap). "
        "No progress signals -- poll get_tool_job for status."
    ),
)
register_job_tool(_CAPA_SPEC)
