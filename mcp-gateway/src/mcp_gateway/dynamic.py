"""Phase 11 dynamic-mode primitive layer (env-gated; D-DYN-IMPORT-01).

Public surface (consumed by tools/dynamic.py and sessions/gdb.py and app.py::lifespan):
- DYNAMIC_TOOLS_ENABLED: bool
- DynamicCapabilities dataclass + CAPABILITIES module slot + probe_all()
- STRACE_PROFILES / LTRACE_PROFILES / QEMU_USER_PROFILES frozen mappings
- EXTRA_ARGS_ALLOWLIST_RE / _DENIED_EXTRA_ARG_FLAGS / _validate_argv_list
- wrap_netns(argv)
- build_strace_argv / build_ltrace_argv / build_qemu_user_argv (pure)
- reap_followfork_strays(runner_pid, original_pgid) -> int
- STRACE_SPEC / LTRACE_SPEC / QEMU_USER_SPEC (JobToolSpec entries, registered at module import)

Design contract (locked per CONTEXT.md D-DYN-* and RESEARCH.md):
- All probes NEVER raise (best-effort dataclass fields + warnings)
- All argv builders are PURE (only ensure_subdir side effect -- matches Phase 10 D-15)
- extra_args / run_argv validated inside build_argv (Pitfall #8 -- _validate_kwargs has no array branch)
- wrap_netns prefix is exactly ["unshare", "--net", "--ipc", "--uts", "--"] (D-DYN-NET-01)
- reap_followfork_strays bounded recursion depth MCP_GATEWAY_DYN_REAP_DEPTH (default 8)
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
import os
import re
import secrets
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any, Mapping, Optional

from mcp_gateway.artifacts_io import ensure_subdir
from mcp_gateway.jobs import JobToolSpec, register_job_tool

log = logging.getLogger("mcp_gateway.dynamic")


# ---------------------------------------------------------------------------
# 3a. Env-var module constants (D-DYN-ENV-01)
# ---------------------------------------------------------------------------
def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        v = int(raw)
    except ValueError as e:
        raise RuntimeError(f"{name}={raw!r} not int: {e}") from e
    if v < 0:
        raise RuntimeError(f"{name}={v} must be >= 0")
    return v


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        v = float(raw)
    except ValueError as e:
        raise RuntimeError(f"{name}={raw!r} not float: {e}") from e
    if v <= 0:
        raise RuntimeError(f"{name}={v} must be > 0")
    return v


DYNAMIC_TOOLS_ENABLED: bool = os.environ.get("MCP_GATEWAY_DYNAMIC_TOOLS") == "1"
REAP_DEPTH: int = _env_int("MCP_GATEWAY_DYN_REAP_DEPTH", 8)
PROBE_TIMEOUT_S: float = _env_float("MCP_GATEWAY_DYN_PROBE_TIMEOUT_S", 3.0)


# ---------------------------------------------------------------------------
# 3b. Profile dictionaries (D-DYN-PROF-01)
# ---------------------------------------------------------------------------
STRACE_PROFILES: Mapping[str, tuple[str, ...]] = {
    "file_io":              ("-f", "-e", "trace=file,desc"),
    "network":              ("-f", "-e", "trace=network"),
    "process":              ("-f", "-e", "trace=process"),
    "signals":              ("-f", "-e", "trace=signal"),
    "file_network_process": ("-f", "-e", "trace=file,desc,network,process"),
    "all":                  ("-f", "-e", "trace=all"),
    "summary":              ("-f", "-c"),
}

LTRACE_PROFILES: Mapping[str, tuple[str, ...]] = {
    "library_calls":         ("-f",),
    "system_only":           ("-f", "-S"),
    "library_and_system":    ("-f", "-S", "-l", "*"),
    "library_count_summary": ("-f", "-c"),
}

QEMU_USER_PROFILES: Mapping[str, tuple[str, ...]] = {
    "simple":         (),
    "syscall_strace": ("-strace",),
    "singlestep_asm": ("-singlestep", "-d", "in_asm,exec"),
    "page_faults":    ("-d", "page"),
    "all_trace":      ("-d", "in_asm,exec,page,cpu,fpu"),
}

_QEMU_ALLOWED_ARCHES: frozenset[str] = frozenset({
    "arm", "aarch64", "mips", "mipsel", "ppc", "ppc64",
    "i386", "x86_64", "riscv64", "sparc",
})


# ---------------------------------------------------------------------------
# 3c. extra_args allowlist regex + denylist (D-DYN-PROF-02; Pitfall #9)
# ---------------------------------------------------------------------------
EXTRA_ARGS_ALLOWLIST_RE = re.compile(
    r"^("
    r"-[a-zA-Z][a-zA-Z0-9_-]{0,31}"          # short flag like -f, -ff, --help
    r"|--[a-zA-Z][a-zA-Z0-9_-]{0,63}"        # long flag like --signal=KILL
    r"|--[a-zA-Z][a-zA-Z0-9_-]{0,63}=[a-zA-Z0-9_,/.:+=-]{1,256}"  # long flag with value
    r"|[a-zA-Z0-9_,/.:+=-]{1,256}"            # bare value (e.g., 'trace=open,read')
    r")$"
)

_DENIED_EXTRA_ARG_FLAGS: frozenset[str] = frozenset({
    "-o",                  # output redirect -- gateway-controlled
    "-D", "--daemonize",
    "--detach",
    "-p", "--attach",      # attach to existing PID -- not in v1.1 sample-exec model
    "--output-separately",
    # Pitfall #9: actual strace dangerous flags (NOT "--exec" which is not a real flag)
    "-b", "--detach-on",   # --detach-on=execve causes strace to detach at execve
})


def _validate_argv_list(items: list[str], *, field: str) -> None:
    """Per-item validation against EXTRA_ARGS_ALLOWLIST_RE + _DENIED_EXTRA_ARG_FLAGS.

    Raises ValueError on first violation with a descriptive message.
    Empty list is valid (no items to check).
    """
    if not isinstance(items, list):
        raise ValueError(f"{field}: expected list, got {type(items).__name__}")
    for i, item in enumerate(items):
        if not isinstance(item, str):
            raise ValueError(f"{field}[{i}]: not a string: {type(item).__name__}")
        if not EXTRA_ARGS_ALLOWLIST_RE.match(item):
            raise ValueError(f"{field}[{i}]: rejected by allowlist regex: {item!r}")
        # Denylist: split on '=' first so --detach-on=execve matches --detach-on
        flag_name = item.split("=", 1)[0]
        if flag_name in _DENIED_EXTRA_ARG_FLAGS:
            raise ValueError(
                f"{field}[{i}]: flag {flag_name!r} is denied "
                f"(output-path / detach / attach are gateway-controlled)"
            )


# ---------------------------------------------------------------------------
# 3d. wrap_netns (D-DYN-NET-01)
# ---------------------------------------------------------------------------
def wrap_netns(argv: list[str]) -> list[str]:
    """Prepend per-call netns isolation (D-DYN-NET-01). Defense-in-depth.

    Returns: ["unshare", "--net", "--ipc", "--uts", "--", *argv]
    Even for empty argv, preserves the "--" delimiter so the caller cannot
    accidentally interpret a sample path as an unshare flag.
    """
    return ["unshare", "--net", "--ipc", "--uts", "--", *argv]


# ---------------------------------------------------------------------------
# Per-subdir log-path helper (local; artifacts_io.tool_log_path is tool-logs/-only).
# Mirrors artifacts_io._SLUG_RE / tool_log_path bookkeeping but parameterises subdir + ext.
# ---------------------------------------------------------------------------
_DYN_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def _dyn_tool_log_path(case_dir: Path, slug: str, ext: str, *, subdir: str) -> Path:
    """Build case_dir/<subdir>/<ts>-<slug>-<rand4><ext>.

    Per CONTEXT.md D-DYN-JOB-02, dynamic mode writes under dynamic/ or qemu/,
    not the artifacts_io tool-logs/ default. ext must include leading dot.
    """
    lowered = slug.lower()
    if not _DYN_SLUG_RE.match(lowered):
        raise ValueError(f"invalid slug: {slug!r}")
    if not ext.startswith("."):
        raise ValueError(f"ext must start with '.': {ext!r}")
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rand4 = secrets.token_hex(2)
    return Path(case_dir) / subdir / f"{ts}-{lowered}-{rand4}{ext}"


# ---------------------------------------------------------------------------
# 3e. build_*_argv builders (D-DYN-JOB-02)
# ---------------------------------------------------------------------------
def _resolve_sample_local(sample_ref: str) -> str:
    # LOCAL import -- dynamic.py is a LEAF; tools.samples lives in the tools/ tier.
    from mcp_gateway.tools import samples
    return samples.resolve_sample(sample_ref)


def build_strace_argv(case_dir: Path, kwargs: dict) -> list[str]:
    sample_ref  = kwargs["sample"]
    profile     = kwargs["profile"]
    extra_args  = kwargs.get("extra_args") or []
    run_argv    = kwargs.get("run_argv") or []

    _validate_argv_list(extra_args, field="extra_args")
    _validate_argv_list(run_argv,   field="run_argv")

    if profile not in STRACE_PROFILES:
        raise ValueError(
            f"unknown strace profile: {profile!r}; allowed: {sorted(STRACE_PROFILES)}"
        )

    sample_path = _resolve_sample_local(sample_ref)
    # ensure 'dynamic/' subdir, mint a per-call output path
    ensure_subdir(case_dir, "dynamic")
    out_path = _dyn_tool_log_path(case_dir, "strace", ".txt", subdir="dynamic")

    inner = [
        "strace",
        *STRACE_PROFILES[profile],
        "-o", str(out_path),
        *extra_args,
        "--",
        str(sample_path),
        *run_argv,
    ]
    return wrap_netns(inner)


def build_ltrace_argv(case_dir: Path, kwargs: dict) -> list[str]:
    sample_ref  = kwargs["sample"]
    profile     = kwargs["profile"]
    extra_args  = kwargs.get("extra_args") or []
    run_argv    = kwargs.get("run_argv") or []

    _validate_argv_list(extra_args, field="extra_args")
    _validate_argv_list(run_argv,   field="run_argv")

    if profile not in LTRACE_PROFILES:
        raise ValueError(
            f"unknown ltrace profile: {profile!r}; allowed: {sorted(LTRACE_PROFILES)}"
        )

    sample_path = _resolve_sample_local(sample_ref)
    ensure_subdir(case_dir, "dynamic")
    out_path = _dyn_tool_log_path(case_dir, "ltrace", ".txt", subdir="dynamic")

    inner = [
        "ltrace",
        *LTRACE_PROFILES[profile],
        "-o", str(out_path),
        *extra_args,
        "--",
        str(sample_path),
        *run_argv,
    ]
    return wrap_netns(inner)


def build_qemu_user_argv(case_dir: Path, kwargs: dict) -> list[str]:
    sample_ref  = kwargs["sample"]
    arch        = kwargs["arch"]
    profile     = kwargs["profile"]
    extra_args  = kwargs.get("extra_args") or []
    run_argv    = kwargs.get("run_argv") or []

    if arch not in _QEMU_ALLOWED_ARCHES:
        raise ValueError(
            f"unknown qemu arch: {arch!r}; allowed: {sorted(_QEMU_ALLOWED_ARCHES)}"
        )
    _validate_argv_list(extra_args, field="extra_args")
    _validate_argv_list(run_argv,   field="run_argv")
    if profile not in QEMU_USER_PROFILES:
        raise ValueError(
            f"unknown qemu_user profile: {profile!r}; allowed: {sorted(QEMU_USER_PROFILES)}"
        )

    sample_path = _resolve_sample_local(sample_ref)
    ensure_subdir(case_dir, "qemu")
    out_path = _dyn_tool_log_path(case_dir, "qemu_user", ".txt", subdir="qemu")
    qemu_bin = f"qemu-{arch}-static"

    # qemu doesn't accept -o; instead we redirect its stderr/stdout via the JOBS log-file capture.
    # Per CONTEXT.md D-DYN-JOB-02, the JOB infrastructure already writes everything to log_path_abs,
    # but qemu's -d <items> writes to stderr by default -- that's captured. The out_path is reserved
    # but not appended to qemu's argv to keep the surface minimal (qemu's -D <file> would do this but
    # D-DYN-PROF-02 denies -D).
    _ = out_path  # reserved; JOBS log capture is the primary output sink for qemu_user

    inner = [
        qemu_bin,
        *QEMU_USER_PROFILES[profile],
        *extra_args,
        "--",
        str(sample_path),
        *run_argv,
    ]
    return wrap_netns(inner)


# ---------------------------------------------------------------------------
# 3f. DynamicCapabilities + probe_all (D-DYN-CAP-PROBE-01)
# ---------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class DynamicCapabilities:
    probed_at: str
    dynamic_mode_enabled: bool
    ptrace_scope: Optional[int]
    ptrace_traceme_works: bool
    binfmt_misc_mounted: bool
    qemu_architectures: tuple[str, ...]
    qemu_static_binaries: tuple[str, ...]
    netns_feasible: bool
    unshare_path: Optional[str]
    gdb_path: Optional[str]
    gdb_version: Optional[str]
    strace_path: Optional[str]
    ltrace_path: Optional[str]
    warnings: tuple[str, ...]


# Module-level slot populated ONCE at lifespan startup (D-DYN-CAP-INIT, wired by Plan 06).
CAPABILITIES: Optional[DynamicCapabilities] = None


def _probe_ptrace_traceme() -> bool:
    """Spawn a child that calls PTRACE_TRACEME; return True if rc == 0. Never raises."""
    # Use a small inline Python script via -c so we don't depend on a fixture binary.
    code = (
        "import ctypes, os, sys\n"
        "libc = ctypes.CDLL('libc.so.6', use_errno=True)\n"
        "PTRACE_TRACEME = 0\n"
        "rc = libc.ptrace(PTRACE_TRACEME, 0, 0, 0)\n"
        "sys.exit(0 if rc == 0 else 1)\n"
    )
    try:
        r = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, timeout=PROBE_TIMEOUT_S,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


_BINFMT_DIR = Path("/proc/sys/fs/binfmt_misc")


def _probe_qemu(binfmt_mounted: bool) -> tuple[list[str], list[str]]:
    """Cross-check binfmt registrations (qemu-<arch>) with installed qemu-<arch>-static binaries."""
    arches: list[str] = []
    bins: list[str] = []
    if binfmt_mounted:
        try:
            for entry in _BINFMT_DIR.iterdir():
                if not entry.name.startswith("qemu-"):
                    continue
                arch = entry.name[len("qemu-"):]
                try:
                    content = entry.read_text()
                except (OSError, PermissionError):
                    continue
                if "enabled" not in content:
                    continue
                # Pitfall #6: require F flag for in-container exec
                is_F = False
                for line in content.splitlines():
                    if line.startswith("flags:") and "F" in line.split(":", 1)[1]:
                        is_F = True
                        break
                bin_path = shutil.which(f"qemu-{arch}-static")
                if bin_path:
                    bins.append(bin_path)
                if is_F and bin_path:
                    arches.append(arch)
        except (OSError, PermissionError):
            pass
    # Also enumerate qemu-*-static binaries even when binfmt is not mounted (informational signal)
    for arch in sorted(_QEMU_ALLOWED_ARCHES):
        p = shutil.which(f"qemu-{arch}-static")
        if p and p not in bins:
            bins.append(p)
    return arches, bins


def probe_all() -> DynamicCapabilities:
    """Probe every dynamic-mode capability. NEVER raises (D-DYN-CAP-PROBE-02)."""
    warnings: list[str] = []
    probed_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    dynamic_mode = os.environ.get("MCP_GATEWAY_DYNAMIC_TOOLS") == "1"

    # 1) ptrace_scope (host-controlled per Pitfall #7)
    ptrace_scope: Optional[int] = None
    try:
        ptrace_scope = int(Path("/proc/sys/kernel/yama/ptrace_scope").read_text().strip())
        if ptrace_scope >= 2:
            warnings.append(
                f"ptrace_scope={ptrace_scope} -- strace/ltrace/gdb will fail. "
                f"Host operator: sudo sysctl -w kernel.yama.ptrace_scope=0"
            )
    except (OSError, ValueError):
        warnings.append("ptrace_scope: /proc/sys/kernel/yama/ptrace_scope not readable")

    # 2) PTRACE_TRACEME smoke test
    ptrace_works = _probe_ptrace_traceme()
    if not ptrace_works:
        warnings.append("ptrace TRACEME smoke test failed -- check container CAP_SYS_PTRACE")

    # 3) binfmt_misc
    binfmt_mounted = _BINFMT_DIR.is_dir() and (_BINFMT_DIR / "register").exists()
    if not binfmt_mounted:
        warnings.append(
            "binfmt_misc not mounted -- run_qemu_user still works via explicit qemu-<arch>-static argv"
        )

    # 4) qemu architectures (binfmt + binary cross-check)
    qemu_arches, qemu_bins = _probe_qemu(binfmt_mounted)

    # 5) netns feasibility (LOAD-BEARING -- Pitfall #2)
    netns_ok = False
    unshare_path = shutil.which("unshare")
    if unshare_path is None:
        warnings.append("unshare not found in PATH -- no network isolation possible")
    else:
        try:
            r = subprocess.run(
                [unshare_path, "--net", "true"],
                capture_output=True, timeout=PROBE_TIMEOUT_S,
            )
            netns_ok = (r.returncode == 0)
            if not netns_ok:
                warnings.append(
                    "unshare --net failed -- check container --security-opt seccomp=unconfined "
                    "or --cap-add=SYS_ADMIN"
                )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            warnings.append(f"unshare probe error: {type(e).__name__}")

    # 6) Tool paths + gdb version
    gdb_path = shutil.which("gdb")
    strace_path = shutil.which("strace")
    ltrace_path = shutil.which("ltrace")

    gdb_version: Optional[str] = None
    if gdb_path:
        try:
            r = subprocess.run(
                [gdb_path, "--version"],
                capture_output=True, timeout=PROBE_TIMEOUT_S,
            )
            gdb_version = (
                r.stdout.decode("utf-8", errors="replace").splitlines()[0]
                if r.stdout else None
            )
        except (subprocess.TimeoutExpired, OSError):
            pass
    else:
        warnings.append("gdb not found in PATH -- open_gdb_session will fail")
    if strace_path is None:
        warnings.append("strace not found in PATH -- run_strace will fail")
    if ltrace_path is None:
        warnings.append("ltrace not found in PATH -- run_ltrace will fail")

    return DynamicCapabilities(
        probed_at=probed_at,
        dynamic_mode_enabled=dynamic_mode,
        ptrace_scope=ptrace_scope,
        ptrace_traceme_works=ptrace_works,
        binfmt_misc_mounted=binfmt_mounted,
        qemu_architectures=tuple(qemu_arches),
        qemu_static_binaries=tuple(qemu_bins),
        netns_feasible=netns_ok,
        unshare_path=unshare_path,
        gdb_path=gdb_path,
        gdb_version=gdb_version,
        strace_path=strace_path,
        ltrace_path=ltrace_path,
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# 3g. reap_followfork_strays (D-DYN-JOB-03)
# ---------------------------------------------------------------------------
def reap_followfork_strays(runner_pid: int, original_pgid: int) -> int:
    """Walk /proc/<pid>/task/*/children up to REAP_DEPTH; SIGKILL setsid escapees.

    Returns count of strays reaped. NEVER raises. Logged at INFO if count > 0.
    D-DYN-JOB-03: invoked from JobToolSpec.post_terminal_hook after killpg has fired.
    Race safety: os.getpgid(cpid) may raise ProcessLookupError if the child exits
    mid-walk -- caught and skipped (the child is already gone, no reap needed).
    """
    killed = 0
    visited: set[int] = set()

    def _walk(pid: int, depth: int) -> None:
        nonlocal killed
        if depth >= REAP_DEPTH or pid in visited:
            return
        visited.add(pid)
        task_dir = Path(f"/proc/{pid}/task")
        if not task_dir.is_dir():
            return
        try:
            tdirs = list(task_dir.iterdir())
        except (OSError, PermissionError):
            return
        for tdir in tdirs:
            try:
                children_str = (tdir / "children").read_text().strip()
            except (OSError, PermissionError):
                continue
            for c in children_str.split():
                try:
                    cpid = int(c)
                except ValueError:
                    continue
                _walk(cpid, depth + 1)
                try:
                    cpgid = os.getpgid(cpid)
                except (ProcessLookupError, PermissionError, OSError):
                    # Child exited mid-walk (race), or we cannot read its pgid -- skip
                    continue
                if cpgid != original_pgid:
                    try:
                        os.kill(cpid, signal.SIGKILL)
                        killed += 1
                    except (ProcessLookupError, PermissionError, OSError):
                        pass

    _walk(runner_pid, depth=0)
    if killed > 0:
        log.info(
            "[dynamic] reaped %d follow-fork stray(s) (runner_pid=%d pgid=%d)",
            killed, runner_pid, original_pgid,
        )
    return killed


async def _reaper_hook(job: "Any") -> None:
    """JobToolSpec.post_terminal_hook adapter. Reads job.pgid + job.proc.pid; calls reap."""
    try:
        pgid = job.pgid
        runner_pid = job.proc.pid if job.proc is not None else None
    except AttributeError:
        return
    if pgid is None or runner_pid is None:
        return
    try:
        reap_followfork_strays(runner_pid, pgid)
    except Exception:
        log.exception("[dynamic] reap_followfork_strays failed (swallowed)")


# ---------------------------------------------------------------------------
# 3h. JobToolSpec registrations (D-DYN-JOB-01)
# ---------------------------------------------------------------------------
STRACE_SPEC = JobToolSpec(
    name="strace",
    slug="strace",
    build_argv=build_strace_argv,
    default_timeout_s=900.0,
    progress_parser=None,
    kwargs_schema={
        "sample":     {"type": "string", "required": True, "max_length": 256},
        "profile":    {"type": "string", "required": True, "enum": list(STRACE_PROFILES)},
        # array schemas validated inside build_argv (Pitfall #8)
    },
    description=(
        "Linux strace under per-call netns (no-net). Profile-driven argv. "
        "Output: case_dir/dynamic/<ts>-strace-<rand4>.txt. Long-running (15-min default)."
    ),
    post_terminal_hook=_reaper_hook,
)

LTRACE_SPEC = JobToolSpec(
    name="ltrace",
    slug="ltrace",
    build_argv=build_ltrace_argv,
    default_timeout_s=900.0,
    progress_parser=None,
    kwargs_schema={
        "sample":     {"type": "string", "required": True, "max_length": 256},
        "profile":    {"type": "string", "required": True, "enum": list(LTRACE_PROFILES)},
    },
    description=(
        "Linux ltrace under per-call netns. Profile-driven. "
        "Output: case_dir/dynamic/<ts>-ltrace-<rand4>.txt. "
        "NOTE: ltrace 0.7.3 is unmaintained -- prefer run_strace for modern binaries."
    ),
    post_terminal_hook=_reaper_hook,
)

QEMU_USER_SPEC = JobToolSpec(
    name="qemu_user",
    slug="qemu_user",
    build_argv=build_qemu_user_argv,
    default_timeout_s=1800.0,
    progress_parser=None,
    kwargs_schema={
        "sample":     {"type": "string", "required": True, "max_length": 256},
        "arch":       {"type": "string", "required": True,
                       "enum": sorted(_QEMU_ALLOWED_ARCHES)},
        "profile":    {"type": "string", "required": True, "enum": list(QEMU_USER_PROFILES)},
    },
    description=(
        "qemu-<arch>-static cross-arch user-mode emulation under per-call netns. "
        "Output captured to case_dir/qemu/. NOTE: multi-threaded samples are unreliable "
        "under qemu-user (known limitation)."
    ),
    post_terminal_hook=_reaper_hook,
)

register_job_tool(STRACE_SPEC)
register_job_tool(LTRACE_SPEC)
register_job_tool(QEMU_USER_SPEC)
