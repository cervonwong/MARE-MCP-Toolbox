"""Phase 10 MCP surface: seven extraction-tier tools (D-01..D-23 from 10-CONTEXT).

Tools (D-01):
  - run_binwalk       (sync for signatures/entropy; async-via-job for extract)
  - run_unblob        (always async; Phase 9 job dispatch)
  - run_upx_test      (sync; parsed)
  - run_upx_list      (sync; parsed)
  - run_upx_unpack    (sync; parsed)
  - list_extracted_files
  - promote_extracted_sample

Result-dict layering (D-10):
  Sync wrappers          -> Phase 6 D-03 12-key dict + Phase 10 extension keys
  Async (job) wrappers   -> Phase 9 D-19 25-key snapshot + Phase 10 extension keys

Phase 10 extension keys (D-10):
  engine, mode, extraction_dir, symlinks_quarantined, meta_path

Error contract (D-22): six locked error-dict shapes; tools NEVER raise out of MCP.

Disclaimer splice (D-23): _EXTRACTION_DISCLAIMER_LONG (4 long-form tools)
                       /  _EXTRACTION_DISCLAIMER_SHORT (3 UPX tools).

Pitfall 5: init_case is a closure inside tools/artifacts.py::register(mcp); we
canNOT import it. promote_extracted_sample shells out to
scripts/init_status_tree.sh via subprocess_runner.run_script and identifies
the new case dir via STATUS_ROOT iterdir-diff (pre vs post).
"""
from __future__ import annotations

import asyncio  # noqa: F401  -- kept for future use; _spawn_monitor is the only spawn site
import datetime
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal, Optional

from mcp.server.fastmcp import Context, FastMCP

from mcp_gateway import extraction
from mcp_gateway.artifacts_io import confine_to
from mcp_gateway.runner import run_tool
from mcp_gateway.subprocess_runner import SCRIPTS, run_script
from mcp_gateway.tools import jobs as tools_jobs
from mcp_gateway.tools.case_dirs import resolve_case_dir
from mcp_gateway.tools.cases import CASE_NAME_RE
from mcp_gateway.tools.samples import (
    SHA256_RE,  # noqa: F401  re-export for callers
    STATUS_ROOT,
    UPLOADS_ROOT,  # noqa: F401  re-export for callers
    resolve_sample,
)
from mcp_gateway.uploads import _is_invalid_filename

log = logging.getLogger("mcp_gateway.tools.extract")


# ----------------------------------------------------------------------------
# D-23 disclaimer text (verbatim). Spliced into tool __doc__ via .replace()
# because Python's parser only attaches docstrings when the function body's
# first expression is a pure string literal.
# ----------------------------------------------------------------------------
_EXTRACTION_DISCLAIMER_LONG = """
    Extraction state lives in case_dir/extracted/<engine>-<ts>-<rand4>/
    with a `_mare_meta.json` provenance sidecar. The in-memory job
    registry for unblob/binwalk_extract is volatile (gateway restart
    cancels in-flight jobs and forgets terminal jobs), but the on-disk
    extraction tree + sidecar are preserved.

    Promotion lineage lives in <new_case_dir>/_lineage.json. Promotion
    is idempotent by sha256 (re-promoting the same child returns the
    existing case dir); pass force_new=True to bypass.

    Extraction tools are shared across all bearer-token clients
    (no per-Mcp-Session-Id keying). Any client with the bearer token
    can see and cancel any extraction job. (Per-session keying deferred
    to v1.2.)
"""

_EXTRACTION_DISCLAIMER_SHORT = """
    Extraction state lives in case_dir/extracted/upx-<ts>-<rand4>/
    with a `_mare_meta.json` provenance sidecar.

    UPX tools are shared across all bearer-token clients
    (no per-Mcp-Session-Id keying). (Per-session keying deferred to v1.2.)
"""


# ----------------------------------------------------------------------------
# Parser regexes (D-09: robust defaults — never crash; emit raw line on miss)
# ----------------------------------------------------------------------------

# binwalk3 signatures text fallback: "<dec_offset>  0x<hex_offset>  <description>"
_BINWALK_SIG_RE = re.compile(
    r"^\s*(?P<offset_dec>\d+)\s+0x(?P<offset_hex>[0-9A-Fa-f]+)\s+(?P<description>.+?)\s*$"
)

# binwalk3 entropy table fallback: rows like "<block_start>  <entropy>  <falling/rising>" or
# "<block_start>-<block_end>  <entropy>"
_BINWALK_ENTROPY_RE = re.compile(
    r"^\s*(?P<block_start>0?x?[0-9A-Fa-f]+)\s*[-\s]+\s*(?P<block_end>0?x?[0-9A-Fa-f]+)?\s+(?P<entropy>[0-9.]+)"
)

# UPX -l columns: "file_size  ratio  format  name" or
# "compressed   uncompressed   ratio   format   name"
_UPX_LIST_RE = re.compile(
    r"^\s*(?P<compressed_size>\d+)\s+(?P<uncompressed_size>\d+)\s+(?P<ratio>[0-9.%]+)\s+"
    r"(?P<format>\S+)\s+(?P<name>.+?)\s*$"
)


# ----------------------------------------------------------------------------
# Private helpers
# ----------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _err_invalid_case_dir(case_dir: str, exc: Exception) -> dict:
    return {
        "error": "invalid case_dir",
        "case_dir": str(case_dir),
        "hint": (
            f"case_dir must be a directory under STATUS_ROOT ({STATUS_ROOT}); "
            f"resolve_case_dir said: {exc}"
        ),
    }


def _err_invalid_sample(sample: str, exc: Exception) -> dict:
    return {
        "error": "invalid sample",
        "sample": str(sample),
        "hint": (
            "sample must be a sha256 hex string of a previous upload OR an "
            f"absolute path under one of the allowed prefixes; resolve_sample said: {exc}"
        ),
    }


def _err_internal(exc: Exception) -> dict:
    return {"error": "internal", "hint": f"{type(exc).__name__}: {exc}"}


def _err_extraction_cap_exceeded(
    cap_bytes: int, observed_bytes: int, extraction_dir: str
) -> dict:
    """D-22 shape 6: returned by extraction tools when the monitor flipped meta
    to status=cap_exceeded. Re-synthesised here from the meta sidecar so callers
    see a consistent error envelope without re-reading the JSON themselves.
    """
    return {
        "error": "extraction cap exceeded",
        "cap_bytes": int(cap_bytes),
        "observed_bytes": int(observed_bytes),
        "extraction_dir": str(extraction_dir),
        "hint": (
            "The sibling monitor observed extracted_bytes > MCP_GATEWAY_MAX_EXTRACT_MB "
            "and cancelled the underlying job. Inspect the extracted/ tree for partial "
            "output and either raise the cap (env var) or carve a smaller subset."
        ),
    }


def _existing_case_for_sha256(sha: str) -> Optional[Path]:
    """D-14 lineage scan: find an existing case-dir whose `_lineage.json`
    records this sha256.  Co-located here (NOT in extraction.py) to keep
    the primitive layer free of tools/* imports.
    """
    if not STATUS_ROOT.is_dir():
        return None
    for entry in sorted(STATUS_ROOT.iterdir()):
        try:
            if not entry.is_dir():
                continue
            if not CASE_NAME_RE.match(entry.name):
                continue
            lineage = entry / "_lineage.json"
            if not lineage.is_file():
                continue
            try:
                data = json.loads(lineage.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("promoted_sha256") == sha:
                return entry
        except OSError:
            continue
    return None


def _parse_binwalk_signatures(report_json_path: Path, stdout: str) -> Optional[list[dict]]:
    """D-09 robust default. Try JSON report first; fall back to stdout regex.
    Returns None ONLY on unrecoverable parser confusion (used for D-22 shape 3).
    Empty list is the legitimate "no signatures found" answer.
    """
    # Preferred: JSON report from `binwalk -l`.
    try:
        if report_json_path.is_file():
            raw = report_json_path.read_text(encoding="utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, list):
                rows: list[dict] = []
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    rows.append({
                        "offset_dec": item.get("offset") if isinstance(item.get("offset"), int) else None,
                        "offset_hex": (
                            hex(item["offset"]) if isinstance(item.get("offset"), int) else None
                        ),
                        "description": item.get("description") or item.get("name") or "",
                        "raw": None,
                    })
                return rows
            if isinstance(data, dict) and isinstance(data.get("signatures"), list):
                rows = []
                for item in data["signatures"]:
                    if not isinstance(item, dict):
                        continue
                    off = item.get("offset")
                    rows.append({
                        "offset_dec": off if isinstance(off, int) else None,
                        "offset_hex": hex(off) if isinstance(off, int) else None,
                        "description": item.get("description") or item.get("name") or "",
                        "raw": None,
                    })
                return rows
    except OSError:
        pass

    # Fallback: parse stdout text. Return [] on empty stdout (legitimate no-signatures).
    if not stdout:
        return []
    rows = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        m = _BINWALK_SIG_RE.match(line)
        if m:
            try:
                rows.append({
                    "offset_dec": int(m.group("offset_dec")),
                    "offset_hex": "0x" + m.group("offset_hex").lower(),
                    "description": m.group("description"),
                    "raw": None,
                })
            except (TypeError, ValueError):
                rows.append({
                    "offset_dec": None,
                    "offset_hex": None,
                    "description": None,
                    "raw": line,
                })
        else:
            rows.append({
                "offset_dec": None,
                "offset_hex": None,
                "description": None,
                "raw": line,
            })
    return rows


def _parse_binwalk_entropy(extraction_path: Path, stdout: str) -> list[dict]:
    """D-09 robust default. Best-effort entropy-row parse; never crashes."""
    rows: list[dict] = []
    if stdout:
        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _BINWALK_ENTROPY_RE.match(line)
            if m:
                try:
                    rows.append({
                        "block_start": m.group("block_start"),
                        "block_end": m.group("block_end"),
                        "entropy": float(m.group("entropy")),
                        "raw": None,
                    })
                except (TypeError, ValueError):
                    rows.append({
                        "block_start": None,
                        "block_end": None,
                        "entropy": None,
                        "raw": line,
                    })
            else:
                rows.append({
                    "block_start": None,
                    "block_end": None,
                    "entropy": None,
                    "raw": line,
                })
    return rows


def _find_entropy_plot(extraction_path: Path) -> Optional[str]:
    """Return a case-rel-style basename for the first .png in extraction_path, or None."""
    try:
        for p in sorted(extraction_path.iterdir()):
            if p.is_file() and p.suffix.lower() == ".png":
                return p.name
    except OSError:
        return None
    return None


def _parse_upx_test_stderr(stderr: str, exit_code: int) -> tuple[bool, str]:
    """Return (is_upx_packed, test_result)."""
    s = stderr or ""
    if "Not packed by UPX" in s or "not packed" in s.lower():
        return False, "not_packed"
    if exit_code == 0 and ("[OK]" in s or "tested OK" in s.lower() or "tested ok" in s.lower()):
        return True, "ok"
    if exit_code != 0 and ("[ERROR]" in s or "corrupt" in s.lower()):
        return True, "corrupt"
    return False, "error"


def _parse_upx_list_stderr(stderr: str) -> list[dict]:
    """D-09 robust default. Best-effort upx -l row parse; never crashes."""
    rows: list[dict] = []
    if not stderr:
        return rows
    for line in stderr.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        # Skip headers/banners
        low = line.lower()
        if (
            "ultimate packer" in low
            or "copyright" in low
            or "markus" in low
            or "file size" in low
            or line.strip().startswith("-")
        ):
            continue
        m = _UPX_LIST_RE.match(line)
        if m:
            try:
                rows.append({
                    "file": m.group("name"),
                    "compressed_size": int(m.group("compressed_size")),
                    "uncompressed_size": int(m.group("uncompressed_size")),
                    "ratio": m.group("ratio"),
                    "format": m.group("format"),
                    "name": m.group("name"),
                    "raw": None,
                })
            except (TypeError, ValueError):
                rows.append({
                    "file": None,
                    "compressed_size": None,
                    "uncompressed_size": None,
                    "ratio": None,
                    "format": None,
                    "name": None,
                    "raw": line,
                })
        else:
            rows.append({
                "file": None,
                "compressed_size": None,
                "uncompressed_size": None,
                "ratio": None,
                "format": None,
                "name": None,
                "raw": line,
            })
    return rows


# ----------------------------------------------------------------------------
# D-01 tools
# ----------------------------------------------------------------------------

async def run_binwalk(
    case_dir: str,
    sample: str,
    *,
    mode: Literal["signatures", "entropy", "extract"] = "signatures",
    ctx: Optional[Context] = None,
) -> dict:
    """Run binwalk3 on a sample.

    Modes (D-02):
      - "signatures": fast scan, returns parsed signatures list (sync)
      - "entropy":    entropy block table + optional PNG plot (sync)
      - "extract":    recursive carve via Phase 9 job dispatch (async)

    Returns:
      Sync modes -> Phase 6 D-03 12-key dict + Phase 10 extension keys
                    (engine, mode, extraction_dir, symlinks_quarantined,
                    meta_path) + per-mode extras (signatures, entropy,
                    entropy_plot, job_id=None).
      Extract    -> Phase 9 D-19 25-key snapshot + same extension keys.

    {_EXTRACTION_DISCLAIMER}
    """
    try:
        # --- input validation ---
        try:
            case_dir_resolved = resolve_case_dir(case_dir)
        except (ValueError, TypeError) as e:
            return _err_invalid_case_dir(case_dir, e)
        case_path = Path(case_dir_resolved)

        try:
            sample_abs = resolve_sample(sample)
        except (ValueError, TypeError, FileNotFoundError) as e:
            return _err_invalid_sample(sample, e)

        if mode not in ("signatures", "entropy", "extract"):
            return {
                "error": "invalid sample",
                "sample": str(sample),
                "hint": (
                    "mode must be one of signatures|entropy|extract; "
                    f"got {mode!r}"
                ),
            }

        # --- mode: extract (Phase 9 job dispatch) ---
        if mode == "extract":
            extraction_path = extraction.extraction_dir(case_path, "binwalk")
            try:
                sample_sha = extraction._hash_file_streaming(sample_abs)
            except OSError:
                sample_sha = ""
            initial_meta = {
                "engine": "binwalk",
                "mode": "extract",
                "sample": sample_abs,
                "sample_sha256": sample_sha,
                "case_dir": str(case_path),
                "extraction_dir": str(extraction_path),
                "started_at": _utc_now_iso(),
                "completed_at": None,
                "exit_code": None,
                "status": "running",
                "job_id": None,
                "argv": [],
                "log_path": "",
                "symlinks_quarantined": 0,
                "cap_exceeded": False,
                "extract_bytes_total": 0,
                "monitor_polls": 0,
            }
            try:
                extraction.write_meta(extraction_path, initial_meta)
            except OSError as e:
                log.warning("[run_binwalk] write_meta initial failed: %s", e)

            kwargs = {
                "case_dir": str(case_path),
                "sample": sample_abs,
                "extraction_dir": str(extraction_path),
                "matryoshka": True,
            }
            snapshot = await tools_jobs.start_tool_job(
                tool="binwalk_extract",
                kwargs=kwargs,
                case_dir=str(case_path),
                ctx=ctx,
            )

            # Pitfall 4: start_tool_job returned error (cap, invalid kwargs, etc.)
            if isinstance(snapshot, dict) and "error" in snapshot:
                try:
                    extraction.update_meta(extraction_path, {
                        "status": "failed",
                        "completed_at": _utc_now_iso(),
                        "argv": [],
                        "log_path": "",
                    })
                except OSError as e:
                    log.warning("[run_binwalk] update_meta(failed) failed: %s", e)
                return {
                    **snapshot,
                    "engine": "binwalk",
                    "mode": "extract",
                    "extraction_dir": str(extraction_path.relative_to(case_path)),
                    "meta_path": str((extraction_path / "_mare_meta.json").relative_to(case_path)),
                    "symlinks_quarantined": 0,
                }

            # Spawn monitor (Plan 03 GC-safe centralized spawn site)
            try:
                extraction._spawn_monitor(snapshot["job_id"], extraction_path)
            except Exception as e:  # noqa: BLE001
                log.warning("[run_binwalk] _spawn_monitor failed: %s", e)

            try:
                extraction.update_meta(extraction_path, {
                    "job_id": snapshot.get("job_id"),
                    "argv": list(snapshot.get("argv", []) or []),
                    "log_path": snapshot.get("log_path", "") or "",
                })
            except OSError as e:
                log.warning("[run_binwalk] update_meta(post-spawn) failed: %s", e)

            return {
                **snapshot,
                "engine": "binwalk",
                "mode": "extract",
                "extraction_dir": str(extraction_path.relative_to(case_path)),
                "meta_path": str((extraction_path / "_mare_meta.json").relative_to(case_path)),
                "symlinks_quarantined": 0,
            }

        # --- sync modes: signatures / entropy ---
        extraction_path = extraction.extraction_dir(case_path, "binwalk")
        try:
            sample_sha = extraction._hash_file_streaming(sample_abs)
        except OSError:
            sample_sha = ""

        if mode == "signatures":
            report_path = extraction_path / "binwalk-report.json"
            argv = [
                "binwalk",
                "-l", str(report_path),
                "-q",
                "--",
                sample_abs,
            ]
            slug = "binwalk_signatures"
        else:  # entropy
            argv = [
                "binwalk",
                "-E",
                "-C", str(extraction_path),
                "-q",
                "--",
                sample_abs,
            ]
            slug = "binwalk_entropy"

        try:
            res = await run_tool(str(case_path), argv, slug=slug, timeout=300.0)
        except Exception as e:  # noqa: BLE001
            log.exception("[run_binwalk] run_tool raised")
            return _err_internal(e)

        # Quarantine symlinks defensively (D-15)
        try:
            quarantine_count, _qpaths = extraction.quarantine_symlinks(extraction_path)
        except OSError as e:
            log.warning("[run_binwalk] quarantine_symlinks failed: %s", e)
            quarantine_count = 0

        # Parse per-mode result
        signatures: Optional[list[dict]] = None
        entropy_rows: Optional[list[dict]] = None
        entropy_plot: Optional[str] = None

        if mode == "signatures":
            signatures = _parse_binwalk_signatures(report_path, res.get("stdout_head", ""))
            # D-22 shape 3: unable to parse at all
            if signatures is None:
                stderr_head = res.get("stderr_head", "") or ""
                return {
                    "error": "unsupported binwalk version",
                    "stderr_head": stderr_head[:512],
                    "hint": (
                        "binwalk output could not be parsed against either the JSON "
                        "report schema or the text signatures regex. Probe binwalk3 "
                        "with `binwalk --version` and run scripts/probe_extraction_tools.sh."
                    ),
                }
        else:
            entropy_rows = _parse_binwalk_entropy(extraction_path, res.get("stdout_head", ""))
            entropy_plot = _find_entropy_plot(extraction_path)

        # Finalize meta sidecar (status=succeeded|failed by exit_code)
        status = "succeeded" if res.get("exit_code") == 0 else "failed"
        try:
            extraction.write_meta(extraction_path, {
                "engine": "binwalk",
                "mode": mode,
                "sample": sample_abs,
                "sample_sha256": sample_sha,
                "case_dir": str(case_path),
                "extraction_dir": str(extraction_path),
                "started_at": _utc_now_iso(),
                "completed_at": _utc_now_iso(),
                "exit_code": res.get("exit_code"),
                "status": status,
                "job_id": None,
                "argv": list(res.get("argv", []) or argv),
                "log_path": res.get("log_path", "") or "",
                "symlinks_quarantined": quarantine_count,
                "cap_exceeded": False,
                "extract_bytes_total": 0,
                "monitor_polls": 0,
            })
        except OSError as e:
            log.warning("[run_binwalk] write_meta(final) failed: %s", e)

        meta_rel = str((extraction_path / "_mare_meta.json").relative_to(case_path))

        return {
            **res,
            "engine": "binwalk",
            "mode": mode,
            "extraction_dir": str(extraction_path.relative_to(case_path)),
            "symlinks_quarantined": quarantine_count,
            "meta_path": meta_rel,
            "signatures": signatures,
            "entropy": entropy_rows,
            "entropy_plot": entropy_plot,
            "job_id": None,
        }
    except Exception as e:  # noqa: BLE001
        log.exception("[run_binwalk] unhandled")
        return _err_internal(e)


async def run_unblob(
    case_dir: str,
    sample: str,
    *,
    depth: int = 8,
    ctx: Optional[Context] = None,
) -> dict:
    """Recursive carve via unblob. Always dispatches a Phase 9 background job.

    Returns the Phase 9 D-19 25-key snapshot dict layered with Phase 10
    extension keys (engine="unblob", mode="extract", extraction_dir, meta_path,
    symlinks_quarantined).

    {_EXTRACTION_DISCLAIMER}
    """
    try:
        try:
            case_dir_resolved = resolve_case_dir(case_dir)
        except (ValueError, TypeError) as e:
            return _err_invalid_case_dir(case_dir, e)
        case_path = Path(case_dir_resolved)

        try:
            sample_abs = resolve_sample(sample)
        except (ValueError, TypeError, FileNotFoundError) as e:
            return _err_invalid_sample(sample, e)

        extraction_path = extraction.extraction_dir(case_path, "unblob")
        try:
            sample_sha = extraction._hash_file_streaming(sample_abs)
        except OSError:
            sample_sha = ""
        initial_meta = {
            "engine": "unblob",
            "mode": "extract",
            "sample": sample_abs,
            "sample_sha256": sample_sha,
            "case_dir": str(case_path),
            "extraction_dir": str(extraction_path),
            "started_at": _utc_now_iso(),
            "completed_at": None,
            "exit_code": None,
            "status": "running",
            "job_id": None,
            "argv": [],
            "log_path": "",
            "symlinks_quarantined": 0,
            "cap_exceeded": False,
            "extract_bytes_total": 0,
            "monitor_polls": 0,
        }
        try:
            extraction.write_meta(extraction_path, initial_meta)
        except OSError as e:
            log.warning("[run_unblob] write_meta initial failed: %s", e)

        kwargs = {
            "case_dir": str(case_path),
            "sample": sample_abs,
            "extraction_dir": str(extraction_path),
            "depth": int(depth) if isinstance(depth, (int, float)) and not isinstance(depth, bool) else depth,
        }
        snapshot = await tools_jobs.start_tool_job(
            tool="unblob",
            kwargs=kwargs,
            case_dir=str(case_path),
            ctx=ctx,
        )

        if isinstance(snapshot, dict) and "error" in snapshot:
            # Pitfall 4: convert orphan running meta to failed
            try:
                extraction.update_meta(extraction_path, {
                    "status": "failed",
                    "completed_at": _utc_now_iso(),
                    "argv": [],
                    "log_path": "",
                })
            except OSError as e:
                log.warning("[run_unblob] update_meta(failed) failed: %s", e)
            return {
                **snapshot,
                "engine": "unblob",
                "mode": "extract",
                "extraction_dir": str(extraction_path.relative_to(case_path)),
                "meta_path": str((extraction_path / "_mare_meta.json").relative_to(case_path)),
                "symlinks_quarantined": 0,
            }

        try:
            extraction._spawn_monitor(snapshot["job_id"], extraction_path)
        except Exception as e:  # noqa: BLE001
            log.warning("[run_unblob] _spawn_monitor failed: %s", e)

        try:
            extraction.update_meta(extraction_path, {
                "job_id": snapshot.get("job_id"),
                "argv": list(snapshot.get("argv", []) or []),
                "log_path": snapshot.get("log_path", "") or "",
            })
        except OSError as e:
            log.warning("[run_unblob] update_meta(post-spawn) failed: %s", e)

        return {
            **snapshot,
            "engine": "unblob",
            "mode": "extract",
            "extraction_dir": str(extraction_path.relative_to(case_path)),
            "meta_path": str((extraction_path / "_mare_meta.json").relative_to(case_path)),
            "symlinks_quarantined": 0,
        }
    except Exception as e:  # noqa: BLE001
        log.exception("[run_unblob] unhandled")
        return _err_internal(e)


async def run_upx_test(case_dir: str, sample: str) -> dict:
    """Run `upx -t` to test integrity of a (possibly UPX-packed) sample.

    Parsed: is_upx_packed (bool), test_result ("ok"|"not_packed"|"corrupt"|"error").

    {_EXTRACTION_DISCLAIMER}
    """
    try:
        try:
            case_dir_resolved = resolve_case_dir(case_dir)
        except (ValueError, TypeError) as e:
            return _err_invalid_case_dir(case_dir, e)
        case_path = Path(case_dir_resolved)

        try:
            sample_abs = resolve_sample(sample)
        except (ValueError, TypeError, FileNotFoundError) as e:
            return _err_invalid_sample(sample, e)

        argv = ["upx", "-t", "--", sample_abs]
        try:
            res = await run_tool(str(case_path), argv, slug="upx_test", timeout=120.0)
        except Exception as e:  # noqa: BLE001
            log.exception("[run_upx_test] run_tool raised")
            return _err_internal(e)

        is_packed, test_result = _parse_upx_test_stderr(
            res.get("stderr_head", "") or "", int(res.get("exit_code", -1))
        )

        return {
            **res,
            "engine": "upx",
            "mode": "test",
            "extraction_dir": None,
            "symlinks_quarantined": 0,
            "meta_path": None,
            "is_upx_packed": is_packed,
            "test_result": test_result,
        }
    except Exception as e:  # noqa: BLE001
        log.exception("[run_upx_test] unhandled")
        return _err_internal(e)


async def run_upx_list(case_dir: str, sample: str) -> dict:
    """Run `upx -l` to list compressed-section metadata for a packed binary.

    Parsed: rows: list[{file, compressed_size, uncompressed_size, ratio, format, name, raw}].

    {_EXTRACTION_DISCLAIMER}
    """
    try:
        try:
            case_dir_resolved = resolve_case_dir(case_dir)
        except (ValueError, TypeError) as e:
            return _err_invalid_case_dir(case_dir, e)
        case_path = Path(case_dir_resolved)

        try:
            sample_abs = resolve_sample(sample)
        except (ValueError, TypeError, FileNotFoundError) as e:
            return _err_invalid_sample(sample, e)

        argv = ["upx", "-l", "--", sample_abs]
        try:
            res = await run_tool(str(case_path), argv, slug="upx_list", timeout=120.0)
        except Exception as e:  # noqa: BLE001
            log.exception("[run_upx_list] run_tool raised")
            return _err_internal(e)

        rows = _parse_upx_list_stderr(res.get("stderr_head", "") or res.get("stdout_head", "") or "")

        return {
            **res,
            "engine": "upx",
            "mode": "list",
            "extraction_dir": None,
            "symlinks_quarantined": 0,
            "meta_path": None,
            "rows": rows,
        }
    except Exception as e:  # noqa: BLE001
        log.exception("[run_upx_list] unhandled")
        return _err_internal(e)


async def run_upx_unpack(case_dir: str, sample: str) -> dict:
    """Run `upx -d` to unpack a UPX-compressed binary.

    Writes the unpacked file under
    case_dir/extracted/upx-<ts>-<rand4>/<basename>.unpacked. Auto-quarantines
    any symlinks under the extraction dir (paranoid; rare for UPX).

    {_EXTRACTION_DISCLAIMER}
    """
    try:
        try:
            case_dir_resolved = resolve_case_dir(case_dir)
        except (ValueError, TypeError) as e:
            return _err_invalid_case_dir(case_dir, e)
        case_path = Path(case_dir_resolved)

        try:
            sample_abs = resolve_sample(sample)
        except (ValueError, TypeError, FileNotFoundError) as e:
            return _err_invalid_sample(sample, e)

        extraction_path = extraction.extraction_dir(case_path, "upx")
        basename = Path(sample_abs).name
        unpacked = extraction_path / f"{basename}.unpacked"
        argv = ["upx", "-d", "-o", str(unpacked), "--", sample_abs]

        try:
            res = await run_tool(str(case_path), argv, slug="upx_unpack", timeout=300.0)
        except Exception as e:  # noqa: BLE001
            log.exception("[run_upx_unpack] run_tool raised")
            return _err_internal(e)

        try:
            qcount, _qpaths = extraction.quarantine_symlinks(extraction_path)
        except OSError as e:
            log.warning("[run_upx_unpack] quarantine_symlinks failed: %s", e)
            qcount = 0

        try:
            sample_sha = extraction._hash_file_streaming(sample_abs)
        except OSError:
            sample_sha = ""

        unpacked_size = 0
        if unpacked.is_file():
            try:
                unpacked_size = unpacked.stat().st_size
            except OSError:
                unpacked_size = 0

        status = "succeeded" if res.get("exit_code") == 0 and unpacked.is_file() else "failed"
        try:
            extraction.write_meta(extraction_path, {
                "engine": "upx",
                "mode": "unpack",
                "sample": sample_abs,
                "sample_sha256": sample_sha,
                "case_dir": str(case_path),
                "extraction_dir": str(extraction_path),
                "started_at": _utc_now_iso(),
                "completed_at": _utc_now_iso(),
                "exit_code": res.get("exit_code"),
                "status": status,
                "job_id": None,
                "argv": list(res.get("argv", []) or argv),
                "log_path": res.get("log_path", "") or "",
                "symlinks_quarantined": qcount,
                "cap_exceeded": False,
                "extract_bytes_total": unpacked_size,
                "monitor_polls": 0,
            })
        except OSError as e:
            log.warning("[run_upx_unpack] write_meta failed: %s", e)

        try:
            unpacked_rel = str(unpacked.relative_to(case_path)) if unpacked.exists() else None
        except ValueError:
            unpacked_rel = None

        meta_rel = str((extraction_path / "_mare_meta.json").relative_to(case_path))

        return {
            **res,
            "engine": "upx",
            "mode": "unpack",
            "extraction_dir": str(extraction_path.relative_to(case_path)),
            "symlinks_quarantined": qcount,
            "meta_path": meta_rel,
            "unpacked_path": unpacked_rel,
            "unpacked_size": unpacked_size,
        }
    except Exception as e:  # noqa: BLE001
        log.exception("[run_upx_unpack] unhandled")
        return _err_internal(e)


async def list_extracted_files(
    case_dir: str,
    *,
    engine: Optional[Literal["binwalk", "unblob", "upx"]] = None,
    limit: int = 500,
    include_quarantined: bool = True,
) -> dict:
    """Enumerate files under case_dir/extracted/*, optionally filtered by engine.

    Per-extraction file cap = extraction.MAX_FILES_PER_EXTRACTION (env-driven, default 5000).
    Cross-extraction overall cap = `limit` (silently clamped to <= 10000).

    Returns a D-05 shape dict:
      {
        case_dir: absolute path,
        extractions: [
          {
            engine, extraction_dir, started_at, completed_at, exit_code,
            status, job_id, symlinks_quarantined, cap_exceeded,
            files: [{path, size, is_symlink_quarantine}, ...],
            files_truncated: bool,
          },
          ...
        ],
        total_extractions, total_files_listed, truncated
      }

    {_EXTRACTION_DISCLAIMER}
    """
    try:
        try:
            case_dir_resolved = resolve_case_dir(case_dir)
        except (ValueError, TypeError) as e:
            return _err_invalid_case_dir(case_dir, e)
        case_path = Path(case_dir_resolved)

        # Clamp limit (D-05): silently <= 10000
        try:
            limit_i = int(limit)
        except (TypeError, ValueError):
            limit_i = 500
        if limit_i < 0:
            limit_i = 0
        if limit_i > 10000:
            limit_i = 10000

        per_cap = int(extraction.MAX_FILES_PER_EXTRACTION)

        all_extractions = extraction.enumerate_extractions(case_path)
        # Engine filter (engine is locked to the dir-name prefix in enumerate_extractions)
        if engine:
            all_extractions = [e for e in all_extractions if e.get("engine") == engine]

        total_listed = 0
        truncated_overall = False
        out_extractions: list[dict] = []

        for ext in all_extractions:
            # Drop internal keys before exposing
            dir_abs: Path = ext.get("_dir_abs")  # type: ignore[assignment]
            files: list[dict] = []
            files_truncated = False
            if dir_abs is not None and dir_abs.is_dir():
                try:
                    for root, _dirs, filenames in os.walk(str(dir_abs), followlinks=False):
                        for name in filenames:
                            if len(files) >= per_cap:
                                files_truncated = True
                                break
                            fpath = Path(root) / name
                            try:
                                if fpath.is_symlink():
                                    # Skip raw symlinks (sentinel files are real files).
                                    continue
                                size = fpath.stat().st_size
                            except OSError:
                                continue
                            is_q = name.endswith(".symlink-target.txt")
                            if not include_quarantined and is_q:
                                continue
                            try:
                                rel = str(fpath.relative_to(case_path))
                            except ValueError:
                                rel = str(fpath)
                            files.append({
                                "path": rel,
                                "size": size,
                                "is_symlink_quarantine": is_q,
                            })
                        if files_truncated:
                            break
                except OSError as e:
                    log.warning("[list_extracted_files] walk failed: %s", e)

            entry = {k: v for k, v in ext.items() if not k.startswith("_")}
            entry["files"] = files
            entry["files_truncated"] = files_truncated
            out_extractions.append(entry)

            total_listed += len(files)
            if total_listed >= limit_i:
                truncated_overall = total_listed > limit_i or truncated_overall
                # Trim last extraction's files to fit the global cap
                overflow = total_listed - limit_i
                if overflow > 0:
                    entry["files"] = entry["files"][: max(0, len(entry["files"]) - overflow)]
                    total_listed = limit_i
                    truncated_overall = True
                break

        return {
            "case_dir": str(case_path),
            "extractions": out_extractions,
            "total_extractions": len(out_extractions),
            "total_files_listed": total_listed,
            "truncated": truncated_overall,
        }
    except Exception as e:  # noqa: BLE001
        log.exception("[list_extracted_files] unhandled")
        return _err_internal(e)


async def promote_extracted_sample(
    parent_case_dir: str,
    child_path: str,
    *,
    force_new: bool = False,
) -> dict:
    """Promote a carved child file out of an extraction tree into a new case.

    Steps (D-06):
      1. Validate parent_case_dir + child_path (rejects traversal + .symlink-target.txt
         sentinels with D-22 shapes 4 + 5).
      2. Hash the child (sha256).
      3. Unless force_new=True: if any existing case-dir's _lineage.json records
         this sha256, return idempotent_reuse=True with the existing case-dir.
      4. extraction.write_upload(child_path, basename) -> (sha256, target_path).
      5. Shell out to scripts/init_status_tree.sh --new to mint a new case dir
         (Pitfall 5: init_case is a closure inside tools/artifacts.py).
      6. Write <new_case_dir>/_lineage.json (D-14 shape).
      7. Return the D-06 10-key shape.

    {_EXTRACTION_DISCLAIMER}
    """
    try:
        # --- 1. validate parent_case_dir ---
        try:
            parent_resolved = resolve_case_dir(parent_case_dir)
        except (ValueError, TypeError) as e:
            return _err_invalid_case_dir(parent_case_dir, e)
        parent_path = Path(parent_resolved)

        # --- validate child_path under parent_case_dir/extracted/ ---
        try:
            child_abs = confine_to(parent_path, child_path)
        except (ValueError, TypeError) as e:
            return {
                "error": "child_path must live under parent case's extracted/",
                "parent_case_dir": str(parent_path),
                "child_path": str(child_path),
                "hint": f"confine_to said: {e}",
            }

        extracted_root = parent_path / "extracted"
        try:
            if not child_abs.is_relative_to(extracted_root):
                return {
                    "error": "child_path must live under parent case's extracted/",
                    "parent_case_dir": str(parent_path),
                    "child_path": str(child_path),
                }
        except AttributeError:
            # Python <3.9 fallback (we're 3.11 but defensive)
            try:
                child_abs.relative_to(extracted_root)
            except ValueError:
                return {
                    "error": "child_path must live under parent case's extracted/",
                    "parent_case_dir": str(parent_path),
                    "child_path": str(child_path),
                }

        if not child_abs.is_file():
            return {
                "error": "invalid sample",
                "sample": str(child_path),
                "hint": f"child_path does not point to a regular file: {child_abs}",
            }

        basename = child_abs.name

        # --- symlink-quarantine-sentinel rejection (D-22 shape 5) ---
        if basename.endswith(".symlink-target.txt"):
            return {
                "error": (
                    "child is a symlink quarantine sentinel "
                    "(.symlink-target.txt) — read it for the original target, "
                    "do not promote it"
                ),
                "child_path": str(child_abs),
            }

        # --- basename safety (Phase 2 predicate) ---
        if _is_invalid_filename(basename):
            return {
                "error": "invalid sample",
                "sample": basename,
                "hint": (
                    "child basename contains forbidden chars "
                    "(`/`, `\\`, `..`, control bytes, or leading dot)"
                ),
            }

        # --- 2. hash ---
        try:
            sha = extraction._hash_file_streaming(child_abs)
        except OSError as e:
            return _err_internal(e)

        # --- 3. idempotency by sha256 (unless force_new) ---
        if not force_new:
            existing = _existing_case_for_sha256(sha)
            if existing is not None:
                try:
                    lineage_data = json.loads((existing / "_lineage.json").read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    lineage_data = {}
                return {
                    "new_case_dir": str(existing),
                    "new_case_name": existing.name,
                    "sha256": sha,
                    "dedup": True,
                    "idempotent_reuse": True,
                    "parent_case_dir": str(parent_path),
                    "parent_extraction_dir": lineage_data.get("parent_extraction_dir"),
                    "child_path": str(child_abs),
                    "promoted_at": lineage_data.get("promoted_at", _utc_now_iso()),
                    "lineage_path": str((existing / "_lineage.json")),
                }

        # --- 4. atomic re-upload via extraction.write_upload ---
        try:
            digest, target_path = extraction.write_upload(child_abs, basename)
        except ValueError as e:
            return {
                "error": "invalid sample",
                "sample": basename,
                "hint": f"write_upload rejected: {e}",
            }
        except OSError as e:
            return _err_internal(e)

        # Sanity: digests should match (write_upload re-streams + rehashes)
        if digest != sha:
            log.warning(
                "[promote_extracted_sample] digest mismatch: %s vs write_upload %s",
                sha, digest,
            )
            sha = digest  # write_upload is authoritative

        # --- 5. shell out to init_status_tree.sh --new (Pitfall 5) ---
        pre_names: set[str]
        try:
            pre_names = {p.name for p in STATUS_ROOT.iterdir() if p.is_dir()}
        except OSError as e:
            return _err_internal(e)

        init_argv = ["bash", str(SCRIPTS / "init_status_tree.sh"), str(target_path), "--new"]
        try:
            init_res = await run_script(init_argv, cwd="/agent", timeout=60.0)
        except asyncio.TimeoutError:
            return {
                "error": "internal",
                "hint": "init_status_tree.sh timed out after 60s",
            }
        except Exception as e:  # noqa: BLE001
            log.exception("[promote_extracted_sample] run_script raised")
            return _err_internal(e)

        if init_res.get("exit_code") != 0:
            return {
                "error": "internal",
                "hint": (
                    f"init_status_tree.sh failed exit={init_res.get('exit_code')}: "
                    f"{(init_res.get('stderr') or '')[:512]}"
                ),
            }

        try:
            post_names = {p.name for p in STATUS_ROOT.iterdir() if p.is_dir()}
        except OSError as e:
            return _err_internal(e)

        new_names = sorted(post_names - pre_names)
        if not new_names:
            return {
                "error": "internal",
                "hint": (
                    "init_status_tree.sh did not create a new case dir under "
                    f"{STATUS_ROOT} (stderr_head: {(init_res.get('stderr') or '')[:256]})"
                ),
            }
        new_case_dir = STATUS_ROOT / new_names[-1]

        # --- 6. write _lineage.json (D-14) ---
        promoted_at = _utc_now_iso()
        try:
            parent_extraction_dir_rel = str(
                child_abs.parent.relative_to(parent_path)
            )
        except ValueError:
            parent_extraction_dir_rel = str(child_abs.parent)
        lineage_payload = {
            "version": 1,
            "promoted_sha256": sha,
            "parent_case_dir": str(parent_path),
            "parent_extraction_dir": parent_extraction_dir_rel,
            "child_path": str(child_abs),
            "promoted_at": promoted_at,
            "promoted_by": "promote_extracted_sample",
        }
        lineage_path = new_case_dir / "_lineage.json"
        try:
            lineage_path.write_text(
                json.dumps(lineage_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError as e:
            log.warning("[promote_extracted_sample] lineage write failed: %s", e)

        # --- 7. D-06 10-key return ---
        return {
            "new_case_dir": str(new_case_dir),
            "new_case_name": new_case_dir.name,
            "sha256": sha,
            "dedup": target_path.exists(),
            "idempotent_reuse": False,
            "parent_case_dir": str(parent_path),
            "parent_extraction_dir": parent_extraction_dir_rel,
            "child_path": str(child_abs),
            "promoted_at": promoted_at,
            "lineage_path": str(lineage_path),
        }
    except Exception as e:  # noqa: BLE001
        log.exception("[promote_extracted_sample] unhandled")
        return _err_internal(e)


# ----------------------------------------------------------------------------
# D-23 disclaimer splice (post-definition; Python parser attaches docstrings
# only to pure string literals).
# ----------------------------------------------------------------------------
run_binwalk.__doc__ = (run_binwalk.__doc__ or "").replace(
    "{_EXTRACTION_DISCLAIMER}", _EXTRACTION_DISCLAIMER_LONG
)
run_unblob.__doc__ = (run_unblob.__doc__ or "").replace(
    "{_EXTRACTION_DISCLAIMER}", _EXTRACTION_DISCLAIMER_LONG
)
list_extracted_files.__doc__ = (list_extracted_files.__doc__ or "").replace(
    "{_EXTRACTION_DISCLAIMER}", _EXTRACTION_DISCLAIMER_LONG
)
promote_extracted_sample.__doc__ = (promote_extracted_sample.__doc__ or "").replace(
    "{_EXTRACTION_DISCLAIMER}", _EXTRACTION_DISCLAIMER_LONG
)
run_upx_test.__doc__ = (run_upx_test.__doc__ or "").replace(
    "{_EXTRACTION_DISCLAIMER}", _EXTRACTION_DISCLAIMER_SHORT
)
run_upx_list.__doc__ = (run_upx_list.__doc__ or "").replace(
    "{_EXTRACTION_DISCLAIMER}", _EXTRACTION_DISCLAIMER_SHORT
)
run_upx_unpack.__doc__ = (run_upx_unpack.__doc__ or "").replace(
    "{_EXTRACTION_DISCLAIMER}", _EXTRACTION_DISCLAIMER_SHORT
)


# ----------------------------------------------------------------------------
# register(mcp): wrap each coroutine with mcp.tool() at registration time
# (NOT @decorator). Matches Phase 8/9 r2_sessions/jobs pattern; allows tests
# to import + call the coroutines directly without a FastMCP instance.
# ----------------------------------------------------------------------------
def register(mcp: FastMCP) -> None:
    """Register all 7 Phase 10 extraction tools on the given FastMCP."""
    mcp.tool()(run_binwalk)
    mcp.tool()(run_unblob)
    mcp.tool()(run_upx_test)
    mcp.tool()(run_upx_list)
    mcp.tool()(run_upx_unpack)
    mcp.tool()(list_extracted_files)
    mcp.tool()(promote_extracted_sample)
