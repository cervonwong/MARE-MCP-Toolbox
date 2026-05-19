"""Phase 10 extraction primitive -- extraction-dir minting, _mare_meta.json sidecar I/O,
symlink quarantine, atomic re-upload, two JobToolSpec argv builders.

Architectural tier: leaf primitive (same tier as runner.py / sessions.py / jobs.py).
Imports allowed: artifacts_io, runner, jobs, uploads, tools.samples (LOCAL inside argv builders only).
Imports FORBIDDEN: mcp.server.fastmcp; tools.* except tools.samples (local-import only).

Decisions implemented:
  D-07 (extraction-dir naming), D-08 (sidecar shape), D-11 (JobToolSpec registration),
  D-12 (pure argv builders), D-15/D-16 (quarantine), D-18 (env-var constants), D-19 (imports).
  `start_extract_monitor` lives in Plan 03 -- NOT in this file.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from mcp_gateway.artifacts_io import confine_to, ensure_subdir  # noqa: F401
from mcp_gateway.jobs import JobToolSpec, register_job_tool

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# D-18: env-var module constants (validated at import; RuntimeError on bad)
# ---------------------------------------------------------------------------
def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        v = int(raw)
    except ValueError as e:
        raise RuntimeError(f"{name}={raw!r} is not a valid int: {e}") from e
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
        raise RuntimeError(f"{name}={raw!r} is not a valid float: {e}") from e
    if v <= 0:
        raise RuntimeError(f"{name}={v} must be > 0")
    return v


MAX_EXTRACT_MB: int                = _env_int("MCP_GATEWAY_MAX_EXTRACT_MB", 4096)
EXTRACT_MONITOR_INTERVAL_S: float  = _env_float("MCP_GATEWAY_EXTRACT_MONITOR_INTERVAL_S", 5.0)
MAX_FILES_PER_EXTRACTION: int      = _env_int("MCP_GATEWAY_LIST_EXTRACT_FILES_PER_EXTRACTION", 5000)
MAX_EXTRACT_BYTES: int             = MAX_EXTRACT_MB * 1024 * 1024


# Dir-name regex: <engine>-<UTC YYYYmmddTHHMMSSZ>-<rand4 hex>
_DIRNAME_RE = re.compile(r"^(binwalk|unblob|upx)-(\d{8}T\d{6}Z)-([0-9a-f]{4})$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_now_slug() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _hash_file_streaming(path: str | Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


# ---------------------------------------------------------------------------
# D-07: extraction_dir
# ---------------------------------------------------------------------------
def extraction_dir(case_dir: str | Path, engine: Literal["binwalk", "unblob", "upx"]) -> Path:
    """Mint extracted/<engine>-<UTC>Z-<rand4>/ subdir under case_dir.

    Returns absolute resolved Path. Caller owns lifetime of the directory.
    """
    if engine not in ("binwalk", "unblob", "upx"):
        raise ValueError(f"engine must be one of binwalk|unblob|upx, got {engine!r}")
    ensure_subdir(case_dir, "extracted")
    ts = _utc_now_slug()
    rand4 = secrets.token_hex(2)
    target = Path(case_dir) / "extracted" / f"{engine}-{ts}-{rand4}"
    # Pitfall 8: mkdir(exist_ok=False) raises FileExistsError on any pre-existing
    # entry (including symlink); rand4 + 1-sec UTC granularity makes collision ~0.
    target.mkdir(parents=False, exist_ok=False)
    return target.resolve(strict=True)  # Pitfall 8: resolve AFTER mkdir confirms no race


# ---------------------------------------------------------------------------
# D-08: _mare_meta.json sidecar I/O (atomic writes -- Pitfall 6)
# ---------------------------------------------------------------------------
def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=str(path.parent),
        prefix=".meta-", suffix=".json", delete=False,
    )
    try:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.rename(tmp.name, str(path))  # POSIX atomic rename on same FS


def write_meta(extraction_dir: Path, payload: dict) -> Path:
    """Write initial _mare_meta.json. Returns the meta path."""
    meta_path = Path(extraction_dir) / "_mare_meta.json"
    _atomic_write_json(meta_path, dict(payload))
    return meta_path


def update_meta(extraction_dir: Path, patch: dict) -> dict:
    """Shallow-merge patch into _mare_meta.json. Returns the merged dict.

    Pitfall 6: atomic rename prevents readers from seeing partial JSON.
    Single-writer guarantee: only the sibling monitor task writes after the wrapper
    returns; D-17 enforces this.
    """
    meta_path = Path(extraction_dir) / "_mare_meta.json"
    try:
        current = json.loads(meta_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        current = {}
    merged = {**current, **patch}
    _atomic_write_json(meta_path, merged)
    return merged


def read_meta(extraction_dir: Path) -> dict:
    """Read and json.loads _mare_meta.json; raises FileNotFoundError if absent."""
    return json.loads((Path(extraction_dir) / "_mare_meta.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# D-15/D-16: quarantine_symlinks (per RESEARCH Example 2 verbatim)
# ---------------------------------------------------------------------------
def quarantine_symlinks(extraction_dir: Path) -> tuple[int, list[str]]:
    """Recursively replace symlinks with .symlink-target.txt sentinels.

    Walks via os.walk(followlinks=False). Idempotent.
    Returns (count, list_of_quarantined_paths_relative_to_extraction_dir).
    """
    count = 0
    paths: list[str] = []
    iso = _utc_now_iso()
    extraction_dir = Path(extraction_dir)
    for root, dirs, files in os.walk(str(extraction_dir), followlinks=False):
        # os.walk(followlinks=False) is the default; explicit for clarity.
        # Find symlinks in `files` AND `dirs` (a symlinked dir shows up in dirs).
        for name in list(files) + list(dirs):
            full = Path(root) / name
            if not full.is_symlink():
                continue
            try:
                as_written = os.readlink(str(full))
                resolved = os.path.realpath(str(full))
            except OSError as exc:
                log.warning("[extraction] readlink failed for %s: %s", full, exc)
                continue
            rel = str(full.relative_to(extraction_dir))
            body = (
                "SYMLINK QUARANTINE\n"
                f"Original symlink (relative within extraction): {rel}\n"
                f"Target (as-written by extractor):              {as_written}\n"
                f"Resolved target (canonical absolute):          {resolved}\n"
                f"Quarantined: {iso}\n"
                "Reason: Symlinks outside an extraction can read host files via the MCP Resources walker; "
                "quarantining preserves the original link metadata as plain text without enabling traversal.\n"
            )
            sentinel = full.parent / f"{full.name}.symlink-target.txt"
            sentinel.write_text(body, encoding="utf-8")
            full.unlink()
            count += 1
            paths.append(rel)
    return count, paths


# ---------------------------------------------------------------------------
# enumerate_extractions (for Plan 04's list_extracted_files)
# ---------------------------------------------------------------------------
def enumerate_extractions(case_dir: str | Path) -> list[dict]:
    """Walk <case_dir>/extracted/*; return per-extraction provenance dicts.

    Engine derived from dir-name regex; falls back to dir-name parse if
    _mare_meta.json missing. Plan 04 layers caps + filters on top.
    """
    results: list[dict] = []
    case_dir = Path(case_dir)
    root = case_dir / "extracted"
    if not root.is_dir():
        return results
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        m = _DIRNAME_RE.match(d.name)
        if not m:
            continue
        engine, ts, _rand4 = m.group(1), m.group(2), m.group(3)
        try:
            meta = read_meta(d)
        except (FileNotFoundError, json.JSONDecodeError):
            meta = {"engine": engine, "status": "unknown", "started_at": ts}
        results.append({
            "engine": engine,
            "extraction_dir": str(d.relative_to(case_dir)),
            "started_at": meta.get("started_at"),
            "completed_at": meta.get("completed_at"),
            "exit_code": meta.get("exit_code"),
            "status": meta.get("status", "unknown"),
            "job_id": meta.get("job_id"),
            "symlinks_quarantined": int(meta.get("symlinks_quarantined", 0)),
            "cap_exceeded": bool(meta.get("cap_exceeded", False)),
            "_dir_abs": d,   # internal, stripped by Plan 04's caller
            "_meta": meta,   # internal, stripped by Plan 04's caller
        })
    return results


# ---------------------------------------------------------------------------
# D-06 step 4: write_upload (atomic re-upload -- per RESEARCH Example 3 verbatim)
# ---------------------------------------------------------------------------
def write_upload(child_path: Path, target_basename: str) -> tuple[str, Path]:
    """Stream child_path into <UPLOADS_ROOT>/<sha256>/<basename> atomically.

    Returns (sha256_hex, final_absolute_path).
    Idempotent: if <UPLOADS_ROOT>/<sha256>/<basename> already exists, returns it
    without rewriting.

    Raises ValueError on invalid target_basename (per uploads._is_invalid_filename)
    or on child_path exceeding MAX_BYTES.
    """
    from mcp_gateway.tools.samples import UPLOADS_ROOT
    from mcp_gateway.uploads import _is_invalid_filename, MAX_BYTES

    if _is_invalid_filename(target_basename):
        raise ValueError(f"invalid target_basename: {target_basename!r}")

    sha = hashlib.sha256()
    size = 0
    UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        dir=str(UPLOADS_ROOT), delete=False, prefix=".incoming-", suffix=".bin"
    )
    try:
        try:
            with open(child_path, "rb") as src:
                while True:
                    chunk = src.read(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError(f"child exceeds {MAX_BYTES} bytes")
                    sha.update(chunk)
                    tmp.write(chunk)
        finally:
            tmp.close()
    except Exception:
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass
        raise

    digest = sha.hexdigest()
    target_dir = UPLOADS_ROOT / digest
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / target_basename
    if target.exists():
        # Dedup: same content already present.
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass
    else:
        shutil.move(tmp.name, str(target))
        os.chmod(target, 0o644)
    return digest, target


# ---------------------------------------------------------------------------
# D-12: pure argv builders
# ---------------------------------------------------------------------------
def _build_unblob_argv(case_dir: Path, kwargs: dict) -> list[str]:
    """Build argv for unblob v26+. Pure function (no side effects).

    argv shape: ["unblob", "--report", "<extraction_dir>/report.json",
                 "-e", "<extraction_dir>", "-d", "<depth>", "--", "<sample>"]
    """
    from mcp_gateway.tools import samples  # LOCAL import -- same pattern as jobs.py:363
    sample = samples.resolve_sample(kwargs["sample"])
    extraction_path = Path(kwargs["extraction_dir"])
    if not extraction_path.is_relative_to(Path(case_dir)):
        raise ValueError(f"extraction_dir not under case_dir: {extraction_path}")
    depth = int(kwargs.get("depth", 8))
    if depth < 1 or depth > 16:
        raise ValueError(f"depth must be 1..16, got {depth}")
    return [
        "unblob",
        "--report", str(extraction_path / "report.json"),
        "-e", str(extraction_path),
        "-d", str(depth),
        "--",          # defense in depth (Open Question #5 = YES)
        sample,
    ]


def _build_binwalk_extract_argv(case_dir: Path, kwargs: dict) -> list[str]:
    """Build argv for binwalk3 v3.1+. Pure function (no side effects).

    NOTE: binwalk3 has NO -d/--depth flag (Assumption A2). The `depth` kwarg is
    retained in the schema for forward compatibility but is IGNORED here.
    Recursion is controlled solely by -M (matryoshka).

    argv shape (matryoshka=True):
      ["binwalk", "-e", "-M", "-C", "<extraction_dir>",
       "-l", "<extraction_dir>/binwalk-report.json", "-q", "--", "<sample>"]
    """
    from mcp_gateway.tools import samples  # LOCAL import
    sample = samples.resolve_sample(kwargs["sample"])
    extraction_path = Path(kwargs["extraction_dir"])
    if not extraction_path.is_relative_to(Path(case_dir)):
        raise ValueError(f"extraction_dir not under case_dir: {extraction_path}")
    matryoshka = bool(kwargs.get("matryoshka", True))
    argv = [
        "binwalk",
        "-e",
        "-C", str(extraction_path),
        "-l", str(extraction_path / "binwalk-report.json"),
        "-q",
        "--",
        sample,
    ]
    if matryoshka:
        argv.insert(2, "-M")  # after -e, before -C
    return argv


# ---------------------------------------------------------------------------
# D-11: JobToolSpec registrations
# ---------------------------------------------------------------------------
_UNBLOB_SPEC = JobToolSpec(
    name="unblob",
    slug="unblob",
    build_argv=_build_unblob_argv,
    default_timeout_s=3600.0,
    progress_parser=None,  # Pitfall 3: unblob Rich Progress -> not line-parseable
    kwargs_schema={
        "case_dir":       {"type": "string", "required": True},
        "sample":         {"type": "string", "required": True},
        "extraction_dir": {"type": "string", "required": True},
        "depth":          {"type": "integer", "min": 1, "max": 16},
    },
    description=(
        "Carve embedded files from a sample via unblob. Writes JSON report at "
        "<extraction_dir>/report.json. Auto-quarantines symlinks post-extract. "
        "Enforces MCP_GATEWAY_MAX_EXTRACT_MB cap via sibling monitor. "
        "No progress signals -- poll get_tool_job for status."
    ),
)
register_job_tool(_UNBLOB_SPEC)


_BINWALK_EXTRACT_SPEC = JobToolSpec(
    name="binwalk_extract",
    slug="binwalk_extract",
    build_argv=_build_binwalk_extract_argv,
    default_timeout_s=1800.0,
    progress_parser=None,  # binwalk3 -q mode is silent on stderr
    kwargs_schema={
        "case_dir":       {"type": "string", "required": True},
        "sample":         {"type": "string", "required": True},
        "extraction_dir": {"type": "string", "required": True},
        "depth":          {"type": "integer", "min": 1, "max": 8},
        "matryoshka":     {"type": "boolean"},
    },
    description=(
        "Recursive extraction via binwalk3 -e -M. Writes carved children under "
        "<extraction_dir>. NOTE: binwalk3 has no --depth flag; the `depth` kwarg "
        "is reserved for forward compatibility and currently ignored. "
        "Auto-quarantines symlinks. Cap via MCP_GATEWAY_MAX_EXTRACT_MB."
    ),
)
register_job_tool(_BINWALK_EXTRACT_SPEC)
