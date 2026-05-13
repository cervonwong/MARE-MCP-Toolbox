"""Phase 7 ARTIF-01..04: artifact-control MCP tools.

Five gateway-native MCP tools layered over Phase 6 chokepoints (artifacts_io.confine_to,
ensure_subdir, ensure_mare_shell_access, tool_log_path) and v1.0 case_dirs.resolve_case_dir.

Tools:
  - write_artifact   (D-21): create/replace a file in case_dir; text or base64 binary
  - append_artifact  (D-22): append-only; creates if missing
  - list_artifacts   (D-23): flat one-dir listing (top-level or one EXPANDED_CASE_SUBDIRS entry)
  - get_artifact_tree (D-24): recursive walk with file-count and depth caps
  - get_tool_log     (D-25): bytes-by-offset paginated read of large captured logs

All path-accepting tools compose `confine_to(resolve_case_dir(case_dir), ...)` per
Phase 6 D-14 to reject traversal uniformly. Writers (write_artifact, append_artifact)
also invoke `artifacts_io.ensure_mare_shell_access(case_dir)` so a subsequent
run_shell call (Phase 7 D-21 explicit) can read what was written.

The five tools are defined at module level so unit tests (test_re_artifacts.py) can
import and await them directly without going through the FastMCP tool-manager. The
`register(mcp)` function decorates them with `@mcp.tool()` at gateway startup. This
mirrors the import-then-register pattern expected by every Phase 7 Wave 2 test module
(test_re_static.py, test_run_shell.py).
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP

from ..artifacts_io import (
    EXPANDED_CASE_SUBDIRS,
    confine_to,
    ensure_mare_shell_access,
)
from ..runner import STDOUT_HEAD_KB, _truncate_to_utf8_boundary
from .case_dirs import resolve_case_dir

# D-23: subdir allowlist for list_artifacts. Empty string means "top-level".
_LIST_ARTIFACTS_ALLOWED_SUBDIRS: frozenset[str] = frozenset(EXPANDED_CASE_SUBDIRS) | {""}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        v = int(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from e
    if v < 0:
        raise RuntimeError(f"{name} must be >= 0, got {v}")
    return v


def _is_hidden(name: str) -> bool:
    """Hidden = dot-prefixed (consistent with tools/artifacts.py and uploads._is_invalid_filename)."""
    return name.startswith(".")


def _file_sha256(path: Path) -> str:
    """Stream the file to a SHA-256 digest (helps clients verify chunked-read reassembly)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---- D-21 ----
async def write_artifact(
    case_dir: str,
    relpath: str,
    content: str,
    *,
    mode: Literal["text", "binary"] = "text",
    overwrite: bool = False,
) -> dict:
    """Write a file inside `case_dir/<relpath>` (ARTIF-02 / D-21).

    `mode="text"` (default): `content` is treated as a UTF-8 string and written as bytes.
    `mode="binary"`: `content` is a base64-encoded string; decoded server-side to bytes.
    `overwrite=False` (default): raises `FileExistsError` if the target file already exists.
    `overwrite=True`: replaces. `confine_to` rejects path-traversal escapes.
    `artifacts_io.ensure_mare_shell_access(case_dir)` is invoked BEFORE the write so a
    subsequent `run_shell` UID 700 can read the file.
    """
    resolved_case = Path(resolve_case_dir(case_dir))
    target = confine_to(resolved_case, relpath)
    if mode == "binary":
        try:
            data = base64.b64decode(content, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError(f"binary content is not valid base64: {exc}") from exc
    elif mode == "text":
        data = content.encode("utf-8")
    else:
        raise ValueError(f"mode must be 'text' or 'binary', got {mode!r}")
    overwrote = False
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"artifact already exists (use overwrite=True): {relpath}")
        overwrote = True
    # Lazy-create any missing parent directories under case_dir.
    target.parent.mkdir(parents=True, exist_ok=True)
    # D-05 / D-21: backfill mare-shell ACLs on the case_dir before the write.
    ensure_mare_shell_access(resolved_case)
    target.write_bytes(data)
    return {
        "case_dir": str(resolved_case),
        "relpath": relpath,
        "bytes_written": len(data),
        "mode": mode,
        "overwrote": overwrote,
    }


# ---- D-22 ----
async def append_artifact(
    case_dir: str,
    relpath: str,
    content: str,
    *,
    mode: Literal["text", "binary"] = "text",
) -> dict:
    """Append to `case_dir/<relpath>` (ARTIF-02 / D-22). Creates if missing.

    Append-only -- no `overwrite` flag (append is always additive). `mode` semantics
    identical to write_artifact. Same `confine_to` + `ensure_mare_shell_access` chokepoints.
    """
    resolved_case = Path(resolve_case_dir(case_dir))
    target = confine_to(resolved_case, relpath)
    if mode == "binary":
        try:
            data = base64.b64decode(content, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError(f"binary content is not valid base64: {exc}") from exc
    elif mode == "text":
        data = content.encode("utf-8")
    else:
        raise ValueError(f"mode must be 'text' or 'binary', got {mode!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    ensure_mare_shell_access(resolved_case)
    with open(target, "ab") as f:
        f.write(data)
    return {
        "case_dir": str(resolved_case),
        "relpath": relpath,
        "bytes_appended": len(data),
        "mode": mode,
    }


# ---- D-23 ----
async def list_artifacts(
    case_dir: str,
    subdir: Optional[str] = None,
) -> dict:
    """Flat one-directory listing of case_dir (or one EXPANDED_CASE_SUBDIRS entry) (ARTIF-03 / D-23).

    `subdir=None` lists top-level files of case_dir.
    `subdir="tool-logs"` (or any other in `EXPANDED_CASE_SUBDIRS`) lists that subdir only.
    Anything else -> `ValueError`. Does NOT recurse (use `get_artifact_tree`).
    Hidden files (`.dotfile`) are skipped.
    """
    sub_key = subdir if subdir is not None else ""
    if sub_key not in _LIST_ARTIFACTS_ALLOWED_SUBDIRS:
        raise ValueError(
            f"subdir must be None or one of {sorted(_LIST_ARTIFACTS_ALLOWED_SUBDIRS - {''})}, got {subdir!r}"
        )
    resolved_case = Path(resolve_case_dir(case_dir))
    # sub_key is from a closed set (_LIST_ARTIFACTS_ALLOWED_SUBDIRS); confine_to
    # is defense-in-depth.  Single-line form: empty sub_key -> case root itself.
    target_dir = confine_to(resolved_case, sub_key) if sub_key else resolved_case
    files: list[dict] = []
    if target_dir.is_dir():
        for entry in sorted(target_dir.iterdir()):
            if not entry.is_file() or _is_hidden(entry.name):
                continue
            stat = entry.stat()
            files.append({
                "name": entry.name,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })
    return {
        "case_dir": str(resolved_case),
        "subdir": subdir,
        "files": files,
    }


# ---- D-24 ----
async def get_artifact_tree(case_dir: str) -> dict:
    """Recursive case-dir tree with file-count and depth caps (ARTIF-03 / D-24).

    Caps:
      - MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES (default 1024) -- stops walking
        once this many files visited; sets truncation_reason="max_files".
      - MCP_GATEWAY_ARTIFACT_TREE_MAX_DEPTH (default 8) -- refuses to recurse
        past this depth; sets truncation_reason="max_depth" if hit.

    Hidden files (dot-prefixed) skipped at every level.
    """
    # Read caps fresh per call so test monkeypatches take effect.
    max_files = _env_int("MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES", 1024)
    max_depth = _env_int("MCP_GATEWAY_ARTIFACT_TREE_MAX_DEPTH", 8)
    resolved_case = Path(resolve_case_dir(case_dir))
    state = {"file_count": 0, "truncated": False, "truncation_reason": None}

    def _walk(path: Path, depth: int) -> dict:
        node: dict = {"name": path.name, "type": "dir", "children": []}
        if depth >= max_depth:
            state["truncated"] = True
            state["truncation_reason"] = state["truncation_reason"] or "max_depth"
            return node
        try:
            entries = sorted(path.iterdir())
        except OSError:
            return node
        for entry in entries:
            if _is_hidden(entry.name):
                continue
            if state["file_count"] >= max_files:
                state["truncated"] = True
                state["truncation_reason"] = state["truncation_reason"] or "max_files"
                return node
            if entry.is_dir() and not entry.is_symlink():
                node["children"].append(_walk(entry, depth + 1))
            elif entry.is_file():
                state["file_count"] += 1
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = -1
                node["children"].append({
                    "name": entry.name,
                    "type": "file",
                    "size": size,
                })
        return node

    tree = _walk(resolved_case, 0)
    return {
        "case_dir": str(resolved_case),
        "tree": tree,
        "truncated": state["truncated"],
        "truncation_reason": state["truncation_reason"],
        "file_count": state["file_count"],
    }


# ---- D-25 ----
async def get_tool_log(
    case_dir: str,
    log_name: str,
    *,
    offset: int = 0,
    length: int = 65536,
) -> dict:
    """Bytes-by-offset paginated read of a captured tool log (ARTIF-04 / D-25).

    Path resolution: `confine_to(case_dir / "tool-logs", log_name)`.
    `length` clamp: `MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB * 4` bytes (default 1 MB).
    `offset >= total_size` -> `eof=True, length_returned=0`.

    Returns a dict with `content` UTF-8-safely truncated, `next_offset` for pagination,
    `eof` flag, full-file `sha256` so clients can verify reassembly of chunked reads.
    """
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")
    if length < 0:
        raise ValueError(f"length must be >= 0, got {length}")
    resolved_case = Path(resolve_case_dir(case_dir))
    tool_logs_dir = resolved_case / "tool-logs"
    # Confine to tool-logs/<log_name>. confine_to enforces traversal rejection.
    target = confine_to(tool_logs_dir, log_name) if tool_logs_dir.is_dir() else None
    if target is None or not target.is_file():
        raise FileNotFoundError(f"tool-log not found: {log_name}")
    # D-25 length cap: head_kb * 4 bytes per call.
    per_call_cap = STDOUT_HEAD_KB * 4 * 1024
    length_clamped = min(length, per_call_cap)
    total_size = target.stat().st_size
    if offset >= total_size:
        return {
            "case_dir": str(resolved_case),
            "log_name": log_name,
            "offset": offset,
            "length_requested": length,
            "length_returned": 0,
            "total_size": total_size,
            "content": "",
            "eof": True,
            "next_offset": offset,
            "sha256": _file_sha256(target),
        }
    with open(target, "rb") as f:
        f.seek(offset)
        raw = f.read(length_clamped)
    # UTF-8-safe truncation reuses runner's helper.
    safe = _truncate_to_utf8_boundary(raw, len(raw))
    content = safe.decode("utf-8", errors="replace")
    length_returned = len(safe)
    next_offset = offset + length_returned
    eof = next_offset >= total_size
    return {
        "case_dir": str(resolved_case),
        "log_name": log_name,
        "offset": offset,
        "length_requested": length,
        "length_returned": length_returned,
        "total_size": total_size,
        "content": content,
        "eof": eof,
        "next_offset": next_offset,
        "sha256": _file_sha256(target),
    }


def register(mcp: FastMCP) -> None:
    """Register the five artifact-control tools on the FastMCP instance.

    Tools are defined at module level (for direct test import) and re-registered
    here as `@mcp.tool()` so the gateway surfaces them to MCP clients. The decorator
    is a no-op pass-through on the underlying coroutine -- production semantics are
    identical to direct function calls.
    """
    mcp.tool()(write_artifact)
    mcp.tool()(append_artifact)
    mcp.tool()(list_artifacts)
    mcp.tool()(get_artifact_tree)
    mcp.tool()(get_tool_log)
