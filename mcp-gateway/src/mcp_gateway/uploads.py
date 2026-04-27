"""POST /upload: streaming file upload with sha256-based content addressing.

D-11: separate POST endpoint on the same port as MCP.
D-13: samples stored at `<UPLOAD_DIR>/<sha256>/<original_name>` (dedup by hash).
D-14: default 1 GB cap, overridable via MCP_GATEWAY_MAX_UPLOAD_MB.
D-15: returned sample_id is usable by tools/resolve_sample.

Threat mitigations:
  T-02-UPLOAD       - stream via request.stream(), enforce cap during streaming, 413 on overflow.
  T-02-PATHTRAVERSAL - reject filenames containing '/', '..', or starting with '.'.
  T-02-TOKENLEAK    - (not applicable here; auth is upstream)
"""
from __future__ import annotations
import hashlib
import logging
import os
import shutil
import tempfile
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger("mcp_gateway.uploads")

DEFAULT_UPLOAD_DIR = "/agent/uploads"
DEFAULT_MAX_UPLOAD_MB = 1024  # 1 GB
DEFAULT_FILENAME = "sample.bin"


def _upload_dir() -> Path:
    return Path(os.environ.get("MCP_GATEWAY_UPLOAD_DIR", DEFAULT_UPLOAD_DIR))


def _max_bytes() -> int:
    raw = os.environ.get("MCP_GATEWAY_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))
    try:
        mb = int(raw)
    except ValueError as e:
        raise RuntimeError(
            f"MCP_GATEWAY_MAX_UPLOAD_MB must be an integer, got {raw!r}"
        ) from e
    if mb < 0:
        raise RuntimeError(f"MCP_GATEWAY_MAX_UPLOAD_MB must be >= 0, got {mb}")
    return mb * 1024 * 1024


# Re-exported at module level for test visibility - tests check `uploads.MAX_BYTES` etc.
# These are callables in code; expose the evaluated defaults for introspection too.
MAX_BYTES = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
UPLOAD_DIR = Path(DEFAULT_UPLOAD_DIR)


def _is_invalid_filename(name: str) -> bool:
    if not name:
        return True
    if "/" in name or "\\" in name:
        return True
    if ".." in name:
        return True
    if name.startswith("."):
        return True
    # Control characters / NUL
    if any(ord(c) < 32 for c in name):
        return True
    return False


async def upload_handler(request: Request) -> JSONResponse:
    """Handle POST /upload: stream body to disk, hash, dedupe by sha256, return sample_id.

    MUST use `async for chunk in request.stream()` - never `request.body()` (OOM on 1 GB).
    """
    # Reject multipart in Phase 2 (raw body + X-Filename only).
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/"):
        return JSONResponse(
            {"error": "multipart not supported in Phase 2 - use raw body with X-Filename"},
            status_code=415,
        )

    filename = request.headers.get("x-filename", DEFAULT_FILENAME)
    if _is_invalid_filename(filename):
        return JSONResponse({"error": "invalid filename"}, status_code=400)

    max_bytes = _max_bytes()

    # Fast-fail on Content-Length > max (client cooperating). Streaming check still applies.
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > max_bytes:
                return JSONResponse(
                    {"error": f"upload exceeds {max_bytes} bytes (content-length declared)"},
                    status_code=413,
                )
        except ValueError:
            pass  # malformed header; continue and rely on streaming cap

    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    sha = hashlib.sha256()

    # Stream to a temporary file INSIDE upload_dir so the final atomic move is on the same FS.
    tmp = tempfile.NamedTemporaryFile(
        dir=str(upload_dir), delete=False, prefix=".incoming-", suffix=".bin"
    )
    try:
        try:
            async for chunk in request.stream():
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    tmp.close()
                    try:
                        os.unlink(tmp.name)
                    except FileNotFoundError:
                        pass
                    return JSONResponse(
                        {"error": f"upload exceeds {max_bytes} bytes"},
                        status_code=413,
                    )
                sha.update(chunk)
                tmp.write(chunk)
        finally:
            tmp.close()
    except Exception:
        # Best-effort cleanup on any streaming exception (client disconnect, etc.)
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass
        raise

    if total == 0:
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass
        return JSONResponse({"error": "empty upload"}, status_code=400)

    digest = sha.hexdigest()
    target_dir = upload_dir / digest
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename

    if target.exists():
        # Dedupe: content-hashed path already exists. Drop tmp.
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass
        log.info("[upload] dedupe hit sha256=%s filename=%s size=%d", digest, filename, total)
    else:
        shutil.move(tmp.name, str(target))
        os.chmod(target, 0o644)
        log.info("[upload] stored sha256=%s filename=%s size=%d", digest, filename, total)

    return JSONResponse(
        {"sample_id": digest, "path": str(target), "size": total},
        status_code=200,
    )
