"""Sample resolver: sha256-id or container-local path -> absolute path.

T-02-PATHTRAVERSAL mitigation: canonicalize then allowlist-check against known prefixes.
"""
from __future__ import annotations
import os
import re
from pathlib import Path

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

UPLOADS_ROOT = Path(os.environ.get("MCP_GATEWAY_UPLOAD_DIR", "/agent/uploads"))
EXAMPLES_ROOT = Path(os.environ.get("MCP_GATEWAY_EXAMPLES_DIR", "/agent/examples"))
STATUS_ROOT = Path(os.environ.get("MCP_GATEWAY_STATUS_DIR", "/agent/status"))

ALLOWED_PREFIXES = (UPLOADS_ROOT, EXAMPLES_ROOT, STATUS_ROOT)


def _resolve_allowed(path: Path) -> str:
    """Canonicalize + verify the resolved path is under one of ALLOWED_PREFIXES."""
    real = Path(os.path.realpath(path))
    for prefix in ALLOWED_PREFIXES:
        prefix_real = Path(os.path.realpath(prefix))
        try:
            real.relative_to(prefix_real)
            return str(real)
        except ValueError:
            continue
    raise ValueError(
        f"path {path!r} not under allowed prefixes {[str(p) for p in ALLOWED_PREFIXES]}"
    )


def resolve_sample(sample: str) -> str:
    """Resolve a sample identifier (sha256 OR container path) to an absolute filesystem path.

    D-15: "sample" may be a sha256 hex string (previous upload) or an already-absolute
    container path. In both cases the final resolved path must live under one of
    ALLOWED_PREFIXES (uploads, examples, status) — path traversal is rejected (T-02-PATHTRAVERSAL).
    """
    if not isinstance(sample, str) or not sample:
        raise ValueError("sample must be a non-empty string")

    if SHA256_RE.match(sample):
        sample_dir = UPLOADS_ROOT / sample
        if not sample_dir.is_dir():
            raise FileNotFoundError(f"no upload for sha256 {sample}")
        # Pick the first non-hidden file (Phase 2: one file per hash per D-13).
        candidates = sorted(p for p in sample_dir.iterdir() if p.is_file() and not p.name.startswith("."))
        if not candidates:
            raise FileNotFoundError(f"upload dir {sample_dir} is empty")
        return _resolve_allowed(candidates[0])

    # Treat as path. Reject obvious traversal before canonicalizing (defense in depth).
    if ".." in Path(sample).parts:
        raise ValueError(f"path traversal rejected: {sample!r}")
    return _resolve_allowed(Path(sample))
