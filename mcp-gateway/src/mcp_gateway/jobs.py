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


# ----------------------------------------------------------------------------
# Drain function (Q2 chunked-read; D-09 counter cap; D-16 Tier-1 progress dispatch)
# ----------------------------------------------------------------------------
async def _drain(
    stream: "asyncio.StreamReader",
    role: str,                     # "stdout" or "stderr"
    job: "Job",
    file_sink,                     # open binary file handle, append mode, unbuffered
    spec: JobToolSpec,
) -> None:
    """Per-pipe drain.

    - Chunked read (Phase 6 precedent), NOT readline (Q2 overrides CONTEXT.md D-09 pseudocode)
    - Per-byte combined counter cap (D-09)
    - Per-line `\\n`-boundary dispatch to spec.progress_parser (D-16 Tier-1, stderr only)
    - In-memory ring buffers populated for head AND tail (Q1)
    - Writes raw bytes to file_sink (Phase 6 D-09 same shape)
    - On cap-exceed: write marker, immediate SIGKILL (no grace per D-09), return
    """
    CHUNK = 64 * 1024
    head_cap_bytes = (
        JOB_STDOUT_HEAD_KB if role == "stdout" else JOB_STDERR_HEAD_KB
    ) * 1024
    line_buf = bytearray()  # for progress-parser \n-boundary dispatch
    while True:
        chunk = await stream.read(CHUNK)
        if not chunk:
            return

        n = len(chunk)

        # Combined stdout+stderr counter cap (D-09)
        if job.log_bytes_written + n > MAX_JOB_LOG_BYTES:
            job._log_cap_exceeded = True
            allowed = max(0, MAX_JOB_LOG_BYTES - job.log_bytes_written)
            if allowed > 0:
                file_sink.write(chunk[:allowed])
                job.log_bytes_written += allowed
            file_sink.write(b"\n=== MARE_JOB_KILLED_LOG_CAP ===\n")
            # Immediate SIGKILL -- no grace per D-09 ("pathologically loud tool")
            if job.pgid is not None:
                try:
                    os.killpg(job.pgid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
            return

        file_sink.write(chunk)
        job.log_bytes_written += n

        # Per-role byte counters + head/tail ring buffers (Q1)
        if role == "stdout":
            job.stdout_bytes_total += n
            head = job.stdout_head_buf
            if len(head) < head_cap_bytes:
                remaining = head_cap_bytes - len(head)
                head.extend(chunk[:remaining])
                if n > remaining:
                    job.stdout_head_truncated = True
            else:
                job.stdout_head_truncated = True
            job.stdout_tail_buf.extend(chunk)
        else:
            job.stderr_bytes_total += n
            head = job.stderr_head_buf
            if len(head) < head_cap_bytes:
                remaining = head_cap_bytes - len(head)
                head.extend(chunk[:remaining])
                if n > remaining:
                    job.stderr_head_truncated = True
            else:
                job.stderr_head_truncated = True
            job.stderr_tail_buf.extend(chunk)

        # Progress dispatch (D-16 Tier-1) -- only stderr is parsed per D-16
        if role == "stderr" and spec.progress_parser is not None:
            line_buf.extend(chunk)
            while b"\n" in line_buf:
                line, _, rest = line_buf.partition(b"\n")
                line_buf = bytearray(rest)
                try:
                    result = spec.progress_parser(bytes(line))
                except Exception:
                    log.exception("[jobs] progress_parser raised -- ignoring")
                    result = None
                if result is not None:
                    cur, total, msg = result
                    job.progress = int(cur)
                    job.progress_total = int(total)
                    # D-18: message truncated to 200 chars
                    job.progress_message = str(msg)[:200]


# ----------------------------------------------------------------------------
# BackgroundJobRegistry (D-14)
# ----------------------------------------------------------------------------
class BackgroundJobRegistry:
    """Async-context-managed in-memory job registry (D-14, JOBS-04).

    Lifespan contract:
      __aenter__: ready state, return self.
      __aexit__:  parallel cancel of every in-flight job (D-07 ladder),
                  then await drive tasks; in-memory state lost (JOBS-04 explicit).

    Internal state guarded by `_lock`:
      _inflight:  dict[job_id -> Job]   (pending|running)
      _completed: OrderedDict[job_id -> Job]  (FIFO by ended_at -- D-10)
    The lock is NEVER held during subprocess I/O (avoids cross-job head-of-line blocking).

    Design note (JOBS-01): _spawn_and_drive INLINES spawn+drain matching runner.py
    because Phase 9 layers two extras on Phase 6's drain (per-role tail ring buffers
    per Q1, per-line progress_parser dispatch per D-16) that runner.py's drain does
    not provide. JOBS-01 "same safety properties" is upheld at the spec level:
    argv-only, start_new_session=True, cwd-confine via Path.resolve(strict=True),
    log-write to tool_log_path, head-cap, byte-counter cap.
    """

    def __init__(
        self,
        *,
        max_inflight: int,
        cancel_grace_s: float,
        max_completed: int,
    ):
        self._max_inflight = max_inflight
        self._cancel_grace_s = cancel_grace_s
        self._max_completed = max_completed
        self._inflight: dict[str, Job] = {}
        self._completed: "collections.OrderedDict[str, Job]" = collections.OrderedDict()
        self._lock: asyncio.Lock = asyncio.Lock()

    async def __aenter__(self) -> "BackgroundJobRegistry":
        log.info(
            "[jobs] registry entered (max_inflight=%d cancel_grace=%.1fs max_completed=%d)",
            self._max_inflight, self._cancel_grace_s, self._max_completed,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        async with self._lock:
            inflight_jobs = list(self._inflight.values())
        if inflight_jobs:
            log.info("[jobs] shutdown: cancelling %d in-flight job(s)", len(inflight_jobs))
            await asyncio.gather(
                *[self.cancel(j, reason="shutdown") for j in inflight_jobs],
                return_exceptions=True,
            )
        drive_tasks = [j._drive_task for j in inflight_jobs if j._drive_task is not None]
        if drive_tasks:
            await asyncio.gather(*drive_tasks, return_exceptions=True)

    async def submit(
        self,
        *,
        spec: JobToolSpec,
        kwargs: dict,
        case_dir_resolved: str,
        effective_timeout_s: float,
    ) -> Job:
        """Register a new Job + start its drive task. Raises JobCapReached when cap hit."""
        async with self._lock:
            if len(self._inflight) >= self._max_inflight:
                raise JobCapReached(inflight=len(self._inflight), cap=self._max_inflight)
            # D-05 step 6: 16-hex job_id
            job_id = secrets.token_hex(8)
            while job_id in self._inflight or job_id in self._completed:
                job_id = secrets.token_hex(8)

        case_dir_path = Path(case_dir_resolved)
        ensure_subdir(case_dir_path, "tool-logs")
        argv = spec.build_argv(case_dir_path, kwargs)
        log_abs = tool_log_path(case_dir_path, spec.slug)
        log_rel = str(log_abs.relative_to(case_dir_path))

        job = Job(
            job_id=job_id,
            tool=spec.name,
            spec=spec,
            kwargs=dict(kwargs),
            case_dir=case_dir_resolved,
            argv=list(argv),
            effective_timeout_s=effective_timeout_s,
            log_path_abs=log_abs,
            log_path_rel=log_rel,
        )

        async with self._lock:
            self._inflight[job_id] = job

        # Pitfall 2: retain task on the Job so GC does not drop it
        job._drive_task = asyncio.create_task(
            self._spawn_and_drive(job),
            name=f"job-drive-{job_id}",
        )
        return job

    def get(self, job_id: str) -> Job:
        if job_id in self._inflight:
            return self._inflight[job_id]
        if job_id in self._completed:
            return self._completed[job_id]
        raise JobNotFound(job_id)

    def list_inflight(self) -> list[Job]:
        return list(self._inflight.values())

    def list_completed(self) -> list[Job]:
        return list(self._completed.values())

    async def cancel(self, job: Job, *, reason: str = "user") -> None:
        """SIGTERM-grace-SIGKILL. Idempotent on terminal jobs (D-07)."""
        if job.status in _TERMINAL_STATUSES:
            return
        job._cancel_requested = True
        if job.pgid is None or job.proc is None:
            # Spawn hasn't reached create_subprocess_exec yet; drive task observes flag in finally.
            return
        try:
            os.killpg(job.pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
        try:
            # D-23: asyncio.shield ONLY here, around the grace-period wait.
            await asyncio.wait_for(
                asyncio.shield(job.proc.wait()),
                timeout=self._cancel_grace_s,
            )
        except asyncio.TimeoutError:
            try:
                os.killpg(job.pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            await asyncio.shield(job.proc.wait())

    async def _spawn_and_drive(self, job: Job) -> None:
        """Spawn subprocess, drive per-role drain, transition to terminal status (D-22)."""
        spec = job.spec
        try:
            case_dir_path = Path(job.case_dir).resolve(strict=True)
            env = os.environ.copy()

            job.status = "running"
            job.started_at_mono = time.monotonic()
            job.started_at_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

            with open(job.log_path_abs, "ab", buffering=0) as sink:
                proc = await asyncio.create_subprocess_exec(
                    *job.argv,
                    cwd=str(case_dir_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    start_new_session=True,
                )
                job.proc = proc
                job.pgid = os.getpgid(proc.pid)

                try:
                    await asyncio.wait_for(
                        asyncio.gather(
                            _drain(proc.stdout, "stdout", job, sink, spec),
                            _drain(proc.stderr, "stderr", job, sink, spec),
                            proc.wait(),
                        ),
                        timeout=job.effective_timeout_s,
                    )
                except asyncio.TimeoutError:
                    # D-08: SIGTERM-grace-SIGKILL ladder, then status=killed_timeout
                    await self.cancel(job, reason="timeout")
                    job.status = "killed_timeout"
                    return
                except asyncio.CancelledError:
                    # SC-4 path: drive task externally cancelled
                    try:
                        os.killpg(job.pgid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
                    await asyncio.shield(proc.wait())
                    job.status = "cancelled"
                    raise

            # Drain completed naturally -- decide terminal status (D-06 priority order)
            if job._cancel_requested:
                job.status = "cancelled"
            elif job._log_cap_exceeded:
                job.status = "killed_log_cap"
            elif proc.returncode == 0:
                job.status = "succeeded"
            else:
                job.status = "failed"

        except Exception:
            # Unexpected error -- mark failed, log, never propagate (D-15 "tools never raise")
            log.exception("[jobs] _spawn_and_drive crashed for job %s", job.job_id)
            job.status = "failed"
        finally:
            job.ended_at_mono = time.monotonic()
            job.ended_at_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            await self._mark_terminal(job)

    async def _mark_terminal(self, job: Job) -> None:
        """Move from _inflight to _completed; write .json snapshot (D-21); FIFO-evict (D-10).

        On-disk log file is PRESERVED across eviction (D-10 invariant).
        """
        snapshot = self._build_snapshot(job)
        json_path = job.log_path_abs.with_suffix(".json")
        try:
            json_path.write_text(json.dumps(snapshot, default=str, indent=2))
        except OSError:
            log.exception("[jobs] failed to write .json snapshot for %s", job.job_id)

        async with self._lock:
            self._inflight.pop(job.job_id, None)
            self._completed[job.job_id] = job
            while len(self._completed) > self._max_completed:
                evicted_id, _ = self._completed.popitem(last=False)
                log.info(
                    "[jobs] FIFO-evicted completed job %s (cap=%d; log file preserved on disk)",
                    evicted_id, self._max_completed,
                )

    def _build_snapshot(self, job: Job) -> dict:
        """Build the D-19 25-key snapshot (12 Phase 6 base + 13 Phase 9 extensions).

        Cheap to call repeatedly: head/tail come from in-memory ring buffers (Q1),
        no file I/O on the read path.
        """
        duration_s = 0.0
        if job.started_at_mono is not None:
            end = job.ended_at_mono if job.ended_at_mono is not None else time.monotonic()
            duration_s = end - job.started_at_mono

        exit_code = -1
        if job.proc is not None and job.proc.returncode is not None:
            exit_code = job.proc.returncode

        stdout_head_text = _strip_ansi(bytes(job.stdout_head_buf).decode("utf-8", errors="replace"))
        stderr_head_text = _strip_ansi(bytes(job.stderr_head_buf).decode("utf-8", errors="replace"))
        stdout_tail_text = _strip_ansi(bytes(job.stdout_tail_buf).decode("utf-8", errors="replace"))
        stderr_tail_text = _strip_ansi(bytes(job.stderr_tail_buf).decode("utf-8", errors="replace"))

        return {
            # Phase 6 D-03 12-key base
            "exit_code": exit_code,
            "timed_out": job.status == "killed_timeout",
            "duration_s": duration_s,
            "stdout_head": _truncate_for_response(stdout_head_text, JOB_STDOUT_HEAD_KB),
            "stdout_truncated": job.stdout_head_truncated,
            "stdout_bytes_total": job.stdout_bytes_total,
            "stderr_head": _truncate_for_response(stderr_head_text, JOB_STDERR_HEAD_KB),
            "stderr_truncated": job.stderr_head_truncated,
            "stderr_bytes_total": job.stderr_bytes_total,
            "log_path": job.log_path_rel,
            "argv": list(job.argv),
            "slug": job.spec.slug,
            # Phase 9 D-19 extensions (13)
            "job_id": job.job_id,
            "tool": job.tool,
            "status": job.status,
            "started_at": job.started_at_iso,
            "ended_at": job.ended_at_iso,
            "stdout_tail": _truncate_for_response(stdout_tail_text, JOB_STDOUT_TAIL_KB),
            "stderr_tail": _truncate_for_response(stderr_tail_text, JOB_STDERR_TAIL_KB),
            "progress": job.progress,
            "progress_total": job.progress_total,
            "progress_message": job.progress_message,
            "kwargs": dict(job.kwargs),
            "case_dir": job.case_dir,
            "effective_timeout_s": job.effective_timeout_s,
        }
