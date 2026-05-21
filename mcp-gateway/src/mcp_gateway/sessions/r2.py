"""r2-specific session driver. R2Session dataclass + _open_r2 driver + _DANGEROUS_R2_CMD_RE.

This module is a leaf of the sessions/ package: it imports from
`sessions._base` (BaseSession + helpers) and from `mcp_gateway.artifacts_io`,
nothing else (D-DYN-IMPORT-01).

Public surface (re-exported by `sessions/__init__.py`):
- `R2Session`: dataclass subclass of `BaseSession` with r2-specific
  `sample_sha256` + `sample_path` fields and the `exec_one` method.
- `_DANGEROUS_R2_CMD_RE`: module-level compiled regex (Phase 8 D-08).
- `check_dangerous_cmd(cmd)`: raises ValueError with the D-09 message on match.
- `_open_r2(registry, ...)`: the spawn driver (extracted from Phase 8
  `SessionRegistry.open` body). Accepts the registry as `self`-equivalent so
  it can use `registry._lock`, `registry._sessions`, `registry._max` etc.
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
import os
import re
import secrets
import signal
import time
from pathlib import Path
from typing import Optional

from mcp_gateway.artifacts_io import confine_to, ensure_subdir

from ._base import BaseSession, SessionCapReached, make_sentinel

log = logging.getLogger("mcp_gateway.sessions.r2")


# ----------------------------------------------------------------------------
# D-08 / D-09 (Phase 8 → reframed Phase 13): dangerous-command regex.
#
# PHASE 13 SECURITY BOUNDARY DELINEATION (D-09):
#   THE SECURITY BOUNDARY IS r2's NATIVE cfg.sandbox=true (Phase 13 D-07).
#   This regex is a UX LAYER that gives operators a clearer error than r2's
#   sandbox-refused output for the common `!` / `R!` / `#!` shell-escape
#   prefixes. It runs in the gateway BEFORE bytes hit r2's stdin.
#
#   DO NOT EXTEND THIS REGEX. Adding new patterns re-enters the parser
#   arms race that motivated Phase 13. If a new r2-syntax bypass surfaces,
#   it will be caught by cfg.sandbox=true's in-process guards
#   (r_sandbox_system, upper-dir-open blocks); add a positive-control test
#   for it in tests/test_r2_sandbox_integration.py instead of growing this regex.
#
#   Phase 13 Pitfall 8 note: cfg.sandbox is a ONE-WAY LATCH. An init-batch
#   line `e cfg.sandbox=false` is silently rejected by r_sandbox_disable.
#   To get an unsandboxed r2 session, callers must spawn a NEW process via
#   open_r2_session_unsafe (Plan 04 / D-10/D-12).
#
#   See Phase 13 CONTEXT.md D-09 + RESEARCH.md Pitfall 1 + 8.
#
# PHASE 8 ORIGINAL DESIGN (preserved):
#   Full-string scan, not literal-first-char. Anchored at start/`;`/`|`/newline;
#   matches optional whitespace before the prefix. Per-command refusal raises
#   ValueError naming the prefix specifically so operators see actionable errors.
# ----------------------------------------------------------------------------
_DANGEROUS_R2_CMD_RE: re.Pattern[str] = re.compile(
    r"(?:^|;|\||\n)\s*(?:#!|R!|!)"
)


def check_dangerous_cmd(cmd: str) -> None:
    """Raise ValueError if cmd contains a refused shell-escape prefix.

    UX layer (Phase 13 D-09): r2's native cfg.sandbox=true is the security
    boundary; this regex catches obvious mistakes with an actionable error
    BEFORE bytes hit r2. Per-command refusal is preserved from Phase 8 D-08
    (one bad command does not invalidate the session).

    DO NOT extend the regex pattern -- see the module-level Phase 13 framing
    comment for rationale.
    """
    if _DANGEROUS_R2_CMD_RE.search(cmd):
        raise ValueError(
            "dangerous r2 command refused: shell-escape prefix "
            "'!' / '#!' / 'R!' is blocked by the gateway wrapper"
        )


# ----------------------------------------------------------------------------
# Phase 8 D-15: R2Session dataclass -- now subclasses BaseSession (Phase 11 D-02).
#
# Dataclass inheritance gotcha: BaseSession has fields with defaults at the
# end (command_count, closed, close_reason, kind). The subclass-added fields
# therefore MUST also have defaults (Python 3.11 dataclass rule -- a field
# with a default cannot be followed by a field without one). We give
# `sample_sha256` an empty-string default and `sample_path` a Path() default
# via default_factory; callers ALWAYS pass both via keyword in _open_r2.
# The `kind` field is re-declared to default to the literal "r2" (overriding
# BaseSession's `"r2"` default; explicit for self-documentation).
# ----------------------------------------------------------------------------
@dataclasses.dataclass
class R2Session(BaseSession):
    sample_sha256: str = ""
    sample_path: Path = dataclasses.field(default_factory=Path)
    kind: str = "r2"  # override BaseSession default; freeze to literal "r2"

    async def exec_one(self, cmd: str, *, timeout: float) -> tuple[bytes, bool]:
        """Send one command + sentinel, read stdout until sentinel line.

        Returns (raw_bytes_before_sentinel, timed_out_bool).
        On timeout the caller must close() the session (Phase 8 D-20 step d).
        Does NOT acquire self.lock -- caller is responsible (Phase 8 D-20).
        """
        sentinel_line = (self.sentinel + "\n").encode()
        self.proc.stdin.write(cmd.encode("utf-8") + b"\n")
        self.proc.stdin.write(f"?e {self.sentinel}\n".encode())
        await self.proc.stdin.drain()
        buf = bytearray()
        try:
            while True:
                line = await asyncio.wait_for(
                    self.proc.stdout.readuntil(b"\n"),
                    timeout=timeout,
                )
                if line == sentinel_line:
                    return bytes(buf), False
                buf.extend(line)
        except asyncio.TimeoutError:
            return bytes(buf), True


# ----------------------------------------------------------------------------
# _open_r2: extracted verbatim from Phase 8 sessions.py::SessionRegistry.open
# body (lines 250-357). Operates on the registry as a first argument so its
# uses of `self._lock`, `self._sessions`, `self._max`, `self.count_open()`,
# `self.list()` remain valid as `registry._lock` etc.
# ----------------------------------------------------------------------------
async def _open_r2(
    registry,
    *,
    case_dir: Path,
    sample_sha256: str,
    sample_path: Path,
    init_commands: Optional[list[str]],
    open_timeout_s: float,
    sandbox: bool = True,
) -> R2Session:
    """Spawn r2, run lockdown init (Phase 8 D-03), then user init_commands.

    Phase 13 D-07 (HOT-FIX 2026-05-21): when sandbox=True (default),
    `e cfg.sandbox=true` is written as the FIRST line of the post-spawn stdin
    init batch, BEFORE the sentinel emit and BEFORE any user-controlled
    command. argv-time latching was rejected because r2 6.0.5's cfg.sandbox
    engages at argv-evaluation time and refuses `r_core_file_open` on the
    binary itself (in-container log.level=4 probe:
    "ERROR: Cannot open '/bin/ls'"). Post-spawn latching lets the binary
    open unsandboxed, then sandbox engages before any analyst-driven command
    runs. When sandbox=False (called only from open_r2_session_unsafe per
    Plan 04), no cfg.sandbox token appears in argv OR in the init batch.

    The remaining argv `-e` flags (`scr.*`, `cfg.user=mare`) STAY in argv
    because they are non-security configuration whose pre-open application
    is harmless and convenient.

    The body is the verbatim Phase 8 SessionRegistry.open logic, extracted so
    the kind-dispatch in `_base.SessionRegistry.open` can defer to it (and to
    a future `_open_gdb`) without case-by-case branching at every step.
    """
    # Phase 8 D-19 step 3: validate init_commands BEFORE spawn (Pitfall 4).
    for ic in (init_commands or []):
        check_dangerous_cmd(ic)

    # Phase 13 D-01/D-03: atomic cap check + slot reservation. The registry._lock
    # bridges the locked()-probe and acquire() into a single atomic gate
    # (Pitfall 3 fix -- without the lock, two coroutines could both see locked()=False
    # and both await acquire(), with one blocking instead of raising). The lock is
    # held only across acquire() itself, which is instantaneous when locked() was False.
    # D-04: cap-reject error payload still reads from registry.count_open() / list()
    # (the dict is the truth; the semaphore is the gate).
    async with registry._lock:
        if registry._sem.locked():
            raise SessionCapReached(registry._max, registry.count_open(), registry.list())
        await registry._sem.acquire()
        session_id = secrets.token_urlsafe(12)

    sess: Optional[R2Session] = None
    try:
        # Phase 8 D-13: lazy r2-sessions/ subdir + transcript path under confine_to.
        ensure_subdir(case_dir, "r2-sessions")
        transcript_path = confine_to(case_dir, f"r2-sessions/{session_id}-transcript.log")

        # Phase 8 D-04: per-session randomized sentinel.
        sentinel = make_sentinel()

        # Phase 8 D-02: argv-only spawn with start_new_session=True for killpg cleanup.
        # Phase 13 D-07 (HOT-FIX 2026-05-21): cfg.sandbox is NOT latched via argv —
        # see D-21 in 13-CONTEXT.md. r2 6.0.5 engages cfg.sandbox at argv-eval time
        # AND its file-open guard refuses to open the binary itself when latched
        # in argv. The sandbox latch lives in the post-spawn init_batch below.
        # The argv `-e` flags here carry ONLY non-security configuration (scr.*,
        # cfg.user=mare) — these are safe to apply pre-open.
        argv: list[str] = [
            "r2", "-2", "-q0",
            "-e", "scr.interactive=false",
            "-e", "scr.color=0",
            "-e", "scr.html=0",
            "-e", "cfg.user=mare",
        ]
        argv.append(str(sample_path))
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(case_dir),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        pgid = os.getpgid(proc.pid)

        # Phase 8 D-03 / Phase 13 D-07 (HOT-FIX 2026-05-21):
        # When sandbox=True, the FIRST line of the post-spawn stdin init batch
        # MUST be `e cfg.sandbox=true`. This is the Phase 13 security boundary:
        # the sandbox latches BEFORE the sentinel emit and BEFORE any
        # user-controlled command. argv-time latching was rejected because
        # r2 6.0.5 refuses `r_core_file_open` on the sample itself when
        # cfg.sandbox is in argv (in-container log.level=4 probe: "ERROR:
        # Cannot open '/bin/ls'"); see 13-CONTEXT.md D-21.
        #
        # Pitfall 8: cfg.sandbox is a ONE-WAY LATCH — once on, `e cfg.sandbox=false`
        # is silently rejected by r_sandbox_disable. Callers wanting an unsandboxed
        # session must call open_r2_session_unsafe (Plan 04 / D-10).
        #
        # init_commands are validated against _DANGEROUS_R2_CMD_RE BEFORE this
        # point (line 162-163) AND executed AFTER the sandbox latches inside
        # `async with sess.lock:` (line 264-277) — the security boundary is
        # preserved end-to-end: no analyst-driven r2 input ever runs unsandboxed.
        if sandbox:
            init_batch = f"e cfg.sandbox=true\n?e {sentinel}\n"
        else:
            init_batch = f"?e {sentinel}\n"
        try:
            proc.stdin.write(init_batch.encode())
            await proc.stdin.drain()
            await asyncio.wait_for(
                proc.stdout.readuntil((sentinel + "\n").encode()),
                timeout=open_timeout_s,
            )
        except (asyncio.TimeoutError, Exception):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            await asyncio.shield(proc.wait())
            raise RuntimeError(
                "r2 init failed: lockdown commands did not complete within timeout"
            )

        # Phase 8 D-13: transcript header.
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        with open(transcript_path, "ab") as f:
            f.write(
                f"=== MARE r2_session {session_id} opened {now_iso} "
                f"sample={sample_sha256[:8]} ===\n".encode()
            )

        now_mono = time.monotonic()
        sess = R2Session(
            session_id=session_id,
            case_dir=case_dir,
            proc=proc,
            pgid=pgid,
            lock=asyncio.Lock(),
            sentinel=sentinel,
            transcript_path=transcript_path,
            opened_at=now_mono,
            opened_iso=now_iso,
            last_used_at=now_mono,
            sample_sha256=sample_sha256,
            sample_path=sample_path,
        )

        # Phase 8 D-19 step 4: run user init_commands inside the session lock
        # (single-threaded r2).
        async with sess.lock:
            for ic in (init_commands or []):
                raw, timed_out = await sess.exec_one(ic, timeout=open_timeout_s)
                if timed_out:
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
                    await asyncio.shield(proc.wait())
                    raise RuntimeError(
                        f"r2 init_commands timed out on {ic!r} after {open_timeout_s}s"
                    )
                sess.command_count += 1
                sess.last_used_at = time.monotonic()

        # Register under lock.
        async with registry._lock:
            registry._sessions[session_id] = sess
        log.info("[sessions] opened %s (pid=%d sample=%s)",
                 session_id, proc.pid, sample_sha256[:8])
        return sess
    except BaseException:
        # Phase 13 D-02: release the reserved slot on ANY spawn-or-init failure
        # (catches CancelledError + Exception; CancelledError is NOT an Exception
        # subclass since 3.8). Mark the session as having released its slot so
        # any subsequent close() call is a no-op on the semaphore (Pitfall 4).
        if sess is not None:
            sess._slot_released = True
        registry._sem.release()
        raise
