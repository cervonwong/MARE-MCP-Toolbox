"""Phase 11 gdb-MI3 session driver (D-04..D-10, D-DYN-NET-01, D-DYN-IMPORT-01).

Public surface:
- GdbSession dataclass (BaseSession subclass with gdb-specific fields)
- _open_gdb(registry, *, case_dir, sample_sha256, sample_path, init_commands, open_timeout_s) -> GdbSession
- validate_mi_command(cmd) -> None (raises ValueError on deny)
- build_sentinel_emit / build_sentinel_terminator / build_lockdown_init_batch helpers
- GDB_OPEN_TIMEOUT_S / GDB_CMD_TIMEOUT_S env-var constants
- _ALLOWED_MI_PREFIXES tuple, _DANGEROUS_GDB_RE compiled pattern

Constraints:
- NO `-iex`/`-ex`/`-x` flags in the gdb argv (Pitfall #10 -- they bypass MI allowlist)
- Sentinel framing AFTER user cmd, NOT `(gdb)\n` prompt (Pitfall #1 -- async records interleave)
- Allowlist FIRST, deny regex SECOND, both raise ValueError (D-07)
- Imports forbidden: mcp.server.fastmcp; tools/* at top-level (tools.samples is LOCAL-only inside _open_gdb)
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
from mcp_gateway.dynamic import wrap_netns

from ._base import (
    BaseSession,
    SessionCapReached,
    _env_float,
    make_sentinel,
)

log = logging.getLogger("mcp_gateway.sessions.gdb")


# ---------------------------------------------------------------------------
# D-09 / D-10 (Phase 11): env-var module constants. Validated at import (D-DYN-ENV-01).
# ---------------------------------------------------------------------------
GDB_OPEN_TIMEOUT_S: float = _env_float("MCP_GATEWAY_GDB_OPEN_TIMEOUT_S", 30.0)
GDB_CMD_TIMEOUT_S: float = _env_float("MCP_GATEWAY_GDB_CMD_TIMEOUT_S", 60.0)


# ---------------------------------------------------------------------------
# D-07: MI prefix allowlist. Strict positive list -- every MI command MUST
# begin with one of these prefixes (after stripping leading whitespace).
# ---------------------------------------------------------------------------
_ALLOWED_MI_PREFIXES: tuple[str, ...] = (
    # State inspection
    "-info-",
    "-data-evaluate-expression",
    "-data-list-register-names",
    "-data-list-register-values",
    "-data-read-memory",
    "-data-disassemble",
    # Stack
    "-stack-list-frames",
    "-stack-list-arguments",
    "-stack-list-locals",
    "-stack-list-variables",
    "-stack-info-depth",
    "-stack-info-frame",
    "-stack-select-frame",
    # Execution control
    "-exec-run",
    "-exec-continue",
    "-exec-next",
    "-exec-step",
    "-exec-finish",
    "-exec-until",
    "-exec-interrupt",
    "-exec-return",
    # Breakpoints
    "-break-insert",
    "-break-delete",
    "-break-list",
    "-break-disable",
    "-break-enable",
    "-break-info",
    "-break-condition",
    # Threads
    "-thread-list-ids",
    "-thread-info",
    "-thread-select",
    # Symbols / files (read-only)
    "-symbol-info-functions",
    "-symbol-info-variables",
    "-symbol-info-types",
    "-symbol-info-modules",
    "-file-list-exec-source-files",
    "-file-list-exec-source-file",
    # Variable objects
    "-var-create",
    "-var-delete",
    "-var-evaluate-expression",
    "-var-list-children",
    "-var-info-",
    "-var-update",
    # Gateway-side framing
    "-gdb-version",
)


# ---------------------------------------------------------------------------
# D-07: deny regex (belt-and-braces after allowlist passes). Anchored on
# start-of-string, `;`, newline, or whitespace -- the only positions a
# "fresh command" can begin in a composite expression.
# ---------------------------------------------------------------------------
_DANGEROUS_GDB_RE: re.Pattern[str] = re.compile(
    r"(?:^|;|\n|\s)\s*("
    r"-interpreter-exec\s+console"           # the Python/CLI escape
    r"|python(?:\s|$)"                        # raw CLI python
    r"|pi(?:\s|$)"                            # CLI python alias
    r"|source(?:\s|$)"                        # arbitrary file sourcing
    r"|shell(?:\s|$)"                         # CLI shell
    r"|!"                                     # ! shellout
    r"|-gdb-set\s+logging\s+(?:on|file)"      # arbitrary file write
    r"|-target-(?:select|attach)"             # remote/pid attach
    r"|attach(?:\s|$)"                        # CLI attach
    r"|add-symbol-file"                       # filesystem load
    r"|generate-core-file"                    # core dump anywhere
    r"|dump\s"                                # dump <addr> to file
    r"|set\s+inferior-tty"                    # tty hijack
    r"|jit-reader-load"                       # JIT-reader-load shared object
    r"|define\s"                              # define user gdb command (could compose denied calls)
    r")"
)


def is_allowed_mi(cmd: str) -> bool:
    """Return True iff cmd begins with a prefix in _ALLOWED_MI_PREFIXES.

    Whitespace at the start is stripped before matching. Empty / non-prefix-matching
    commands return False. The check is PREFIX-based -- full command (cmd args) is
    allowed as long as the leading MI keyword matches.
    """
    stripped = cmd.lstrip()
    return any(stripped.startswith(p) for p in _ALLOWED_MI_PREFIXES)


def validate_mi_command(cmd: str) -> None:
    """Allowlist FIRST, deny regex SECOND. Both raise ValueError naming the violation.

    Composite commands (containing ';' / newline) are scanned by the deny regex even
    if the leading prefix is allowlisted -- this catches "-info-functions ;
    -interpreter-exec console ..." patterns where someone tries to chain a denied
    call after an allowed prefix.
    """
    if not isinstance(cmd, str):
        raise ValueError(f"gdb command must be str, got {type(cmd).__name__}")
    if not is_allowed_mi(cmd):
        raise ValueError(
            f"gdb-MI command refused: not in allowlist: {cmd!r}; "
            f"allowed prefixes are listed in sessions.gdb._ALLOWED_MI_PREFIXES"
        )
    if _DANGEROUS_GDB_RE.search(cmd):
        raise ValueError(
            f"gdb-MI command refused: matches deny regex: {cmd!r} "
            f"(blocked: python/source/shell/!/interpreter-exec/target-*/attach/"
            f"add-symbol-file/dump/generate-core-file/set inferior-tty/define/jit-reader-load)"
        )


# ---------------------------------------------------------------------------
# D-06: sentinel framing. The string passed to -data-evaluate-expression is a
# gdb string literal -- quote it with escaped inner double-quotes so gdb echoes
# the literal back in its ^done record.
# ---------------------------------------------------------------------------
def build_sentinel_emit(sentinel: str) -> bytes:
    """Bytes to write to gdb stdin to emit our framing terminator."""
    return f'-data-evaluate-expression "\\"{sentinel}\\""\n'.encode("ascii")


def build_sentinel_terminator(sentinel: str) -> bytes:
    """Substring readuntil must find in gdb's stdout to know the previous cmd completed.

    gdb emits: `^done,value="\\"<sentinel>\\""` -- note the inner quotes are escaped
    in the wire output (gdb's MI3 string format).
    """
    return f'^done,value="\\"{sentinel}\\""'.encode("ascii")


# ---------------------------------------------------------------------------
# D-05: mandatory lockdown init batch -- 10 `-gdb-set` lines + 1 `-gdb-version`,
# followed by a single sentinel-emit terminator. Sent as ONE write to gdb stdin.
# ---------------------------------------------------------------------------
_LOCKDOWN_LINES: tuple[bytes, ...] = (
    b"-gdb-set confirm off\n",
    b"-gdb-set pagination off\n",
    b"-gdb-set print pretty off\n",
    b"-gdb-set verbose off\n",
    b"-gdb-set debuginfod enabled off\n",
    b"-gdb-set auto-solib-add off\n",
    b"-gdb-set logging file /dev/null\n",
    b"-gdb-set follow-fork-mode parent\n",
    b"-gdb-set detach-on-fork on\n",
    b"-gdb-set startup-with-shell off\n",
    b"-gdb-version\n",
)


def build_lockdown_init_batch(sentinel: str) -> bytes:
    """Concatenate the mandatory init batch + a single sentinel-emit terminator.

    Sent as ONE write to gdb's stdin; the readuntil pattern matches only AFTER all
    replies have come back (the sentinel-emit comes last in the batch).
    """
    return b"".join(_LOCKDOWN_LINES) + build_sentinel_emit(sentinel)


# ---------------------------------------------------------------------------
# D-04: gdb argv builder. EXACTLY 11 elements under wrap_netns. Pitfall #10:
# NEVER include -iex / -ex / -x (they bypass the MI allowlist).
# ---------------------------------------------------------------------------
def _build_gdb_argv(sample_path: Path) -> list[str]:
    """Build the EXACT 11-element argv for gdb under per-call netns isolation."""
    inner = [
        "gdb",
        "--interpreter=mi3",
        "--quiet",
        "--nx",
        "--nh",
        str(sample_path),
    ]
    return wrap_netns(inner)


# ---------------------------------------------------------------------------
# D-03: GdbSession dataclass (subclass of BaseSession).
# Dataclass inheritance rule: all subclass-added fields MUST have defaults
# because BaseSession's tail fields (command_count, closed, close_reason, kind)
# carry defaults. Callers always pass the gdb-specific fields via keyword in
# _open_gdb.
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class GdbSession(BaseSession):
    sample_sha256: str = ""
    sample_path: Path = dataclasses.field(default_factory=Path)
    gdb_version: str = ""
    mi_version: str = "mi3"
    follow_fork_mode: str = "parent"
    netns_wrapped: bool = True
    kind: str = "gdb"  # override BaseSession default

    async def exec_one(self, cmd: str, *, timeout: float) -> tuple[bytes, bool]:
        """Validate cmd, write to gdb stdin, read until sentinel; return (raw_bytes, timed_out).

        Caller MUST hold self.lock (Phase 8 D-20 convention). Validation raises
        ValueError BEFORE any bytes hit gdb's stdin (D-07).
        """
        validate_mi_command(cmd)
        self.proc.stdin.write(cmd.encode("utf-8") + b"\n")
        self.proc.stdin.write(build_sentinel_emit(self.sentinel))
        await self.proc.stdin.drain()

        terminator = build_sentinel_terminator(self.sentinel)
        buf = bytearray()
        try:
            while True:
                line = await asyncio.wait_for(
                    self.proc.stdout.readuntil(b"\n"),
                    timeout=timeout,
                )
                if terminator in line:
                    return bytes(buf), False
                buf.extend(line)
        except asyncio.TimeoutError:
            return bytes(buf), True


# ---------------------------------------------------------------------------
# _open_gdb driver -- mirrors sessions/r2.py::_open_r2 structure.
# ---------------------------------------------------------------------------
async def _open_gdb(
    registry,
    *,
    case_dir: Path,
    sample_sha256: str,
    sample_path: Path,
    init_commands: Optional[list[str]],
    open_timeout_s: float,
    follow_fork_mode: str = "parent",
) -> GdbSession:
    """Spawn gdb under wrap_netns, run lockdown init batch, then user init_commands.

    Validates init_commands BEFORE spawn (Pitfall: validate user input early).
    On any failure during init, killpg the gdb pgroup and raise RuntimeError.
    """
    # Validate user init_commands BEFORE spawn
    for ic in (init_commands or []):
        validate_mi_command(ic)

    # Phase 13 D-01/D-03: atomic cap check + slot reservation. Same pattern as
    # sessions/r2.py::_open_r2 -- the registry._lock bridges locked()-probe and
    # acquire() into a single atomic gate (Pitfall 3). D-04: cap-reject payload
    # reads from registry.count_open() / list() (dict-is-truth invariant).
    async with registry._lock:
        if registry._sem.locked():
            raise SessionCapReached(registry._max, registry.count_open(), registry.list())
        await registry._sem.acquire()
        session_id = secrets.token_urlsafe(12)

    sess: Optional[GdbSession] = None
    try:
        # Lazy dynamic/ subdir + transcript path
        ensure_subdir(case_dir, "dynamic")
        transcript_path = confine_to(case_dir, f"dynamic/{session_id}-gdb-transcript.log")

        sentinel = make_sentinel()
        argv = _build_gdb_argv(sample_path)

        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(case_dir),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            # Process exited before we could read pgid; treat as init failure.
            await asyncio.shield(proc.wait())
            raise RuntimeError("gdb process exited before getpgid")

        # Lockdown init batch -- write + read-until-sentinel (D-05)
        gdb_version_line = ""
        try:
            batch = build_lockdown_init_batch(sentinel)
            proc.stdin.write(batch)
            await proc.stdin.drain()
            terminator = build_sentinel_terminator(sentinel)
            init_buf = bytearray()
            deadline = time.monotonic() + open_timeout_s
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError("gdb init batch timed out")
                line = await asyncio.wait_for(
                    proc.stdout.readuntil(b"\n"),
                    timeout=remaining,
                )
                init_buf.extend(line)
                if terminator in line:
                    break
            # Best-effort: pull gdb_version from the init buffer. gdb emits the
            # version reply as: `~"GNU gdb (...)\n"` (a console-stream record).
            for ln in init_buf.split(b"\n"):
                if ln.startswith(b'~"GNU gdb'):
                    gdb_version_line = ln.decode("utf-8", errors="replace").strip()
                    break
        except Exception as e:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                await asyncio.shield(proc.wait())
            except Exception:
                pass
            raise RuntimeError(f"gdb init failed: {type(e).__name__}: {e}") from e

        # Transcript header (matches Phase 8 D-13 r2 format, gdb_session marker).
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        try:
            with open(transcript_path, "ab") as f:
                f.write(
                    f"=== MARE gdb_session {session_id} opened {now_iso} "
                    f"sample={sample_sha256[:8]} ===\n".encode()
                )
        except OSError:
            log.exception("[sessions/gdb] failed to write transcript header for %s", session_id)

        now_mono = time.monotonic()
        sess = GdbSession(
            session_id=session_id,
            case_dir=case_dir,
            pgid=pgid,
            lock=asyncio.Lock(),
            sentinel=sentinel,
            transcript_path=transcript_path,
            opened_at=now_mono,
            opened_iso=now_iso,
            last_used_at=now_mono,
            proc=proc,
            sample_sha256=sample_sha256,
            sample_path=sample_path,
            gdb_version=gdb_version_line,
            follow_fork_mode=follow_fork_mode,
        )

        # Run user init_commands inside session lock
        async with sess.lock:
            for ic in (init_commands or []):
                raw, timed_out = await sess.exec_one(ic, timeout=open_timeout_s)
                if timed_out:
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
                    try:
                        await asyncio.shield(proc.wait())
                    except Exception:
                        pass
                    raise RuntimeError(
                        f"gdb init_command timed out on {ic!r} after {open_timeout_s}s"
                    )
                sess.command_count += 1
                sess.last_used_at = time.monotonic()

        # Register under registry lock
        async with registry._lock:
            registry._sessions[session_id] = sess
        log.info(
            "[sessions/gdb] opened %s (pid=%d sample=%s)",
            session_id, proc.pid, sample_sha256[:8],
        )
        return sess
    except BaseException:
        # Phase 13 D-02: release the reserved slot on ANY spawn-or-init failure
        # (catches CancelledError + Exception). Mark session as having released
        # its slot so subsequent close() is a no-op on the semaphore (Pitfall 4).
        if sess is not None:
            sess._slot_released = True
        registry._sem.release()
        raise
