"""MCP Resources for case artifacts (CLI-04, D-01..D-05).

URI scheme: mare://cases/<case>/<artifact>  (D-01)
Listing: dynamic — re-enumerates STATUS_ROOT on every resources/list call (D-02).
Coverage: 13 pipeline artifacts per artifact-spec.md (D-03).
MIME: extension-inferred map + octet-stream fallback (D-04).
Uploads: NOT exposed (D-05).
"""
from __future__ import annotations
import logging
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
import mcp.types as mcp_types
from pydantic import AnyUrl

from .cases import CASE_NAME_RE
from .samples import STATUS_ROOT
from ..artifacts_io import EXPANDED_CASE_SUBDIRS

log = logging.getLogger("mcp_gateway.resources")

# D-03: the 13 required artifacts per
# workspace/.claude/skills/malware-analysis-orchestrator/references/artifact-spec.md
ARTIFACTS: tuple[str, ...] = (
    "00_sample_profile.md",
    "01_strings_raw.txt",
    "02_strings_interesting.md",
    "03_imports_raw.txt",
    "04_imports_interesting.md",
    "05_behavior_hypotheses.md",
    "06_component_inventory.md",
    "07_interaction_model.md",
    "08_deep_analysis_plan.md",
    "09_priority_queue.md",
    "10_reporting_draft.md",
    "INDEX.md",
    "CURRENT_STATE.json",
)

# D-04: extension → MIME. Stdlib mimetypes returns None for .log on stock Linux,
# so we hand-roll the map. Lookup is case-insensitive.
_MIME_MAP = {
    ".json": "application/json",
    ".txt":  "text/plain",
    ".log":  "text/plain",
    ".md":   "text/markdown",
}


def _env_int(name: str, default: int) -> int:
    """Read non-negative int env var; raise RuntimeError on invalid value (matches Phase 6 D-08 pattern)."""
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


def _mime_for(path: Path) -> str:
    """Return the MIME type for a path based on its (case-insensitive) suffix."""
    return _MIME_MAP.get(path.suffix.lower(), "application/octet-stream")


def _status_root() -> Path:
    """Resolve STATUS_ROOT dynamically per call so monkeypatch / env var changes
    are honored at runtime (matches the module docstring's "dynamic — re-enumerates
    STATUS_ROOT on every resources/list call" promise). Falls back to the
    module-level STATUS_ROOT for backward compatibility when env var is unset.
    """
    raw = os.environ.get("MCP_GATEWAY_STATUS_DIR")
    if raw is None:
        return STATUS_ROOT
    return Path(raw)


def _list_cases() -> list[str]:
    """Enumerate case directories under STATUS_ROOT (mirrors tools/cases.py:list_cases).

    Returns sorted list of case dir names matching CASE_NAME_RE. Empty if
    STATUS_ROOT does not exist.
    """
    root = _status_root()
    if not root.exists():
        return []
    return sorted(
        p.name for p in root.iterdir()
        if p.is_dir() and CASE_NAME_RE.match(p.name)
    )


def _build_resource_list() -> list[mcp_types.Resource]:
    """D-02 (v1.0): enumerate (all cases) × (13 artifacts) at depth 1.
    D-26 (Phase 7): additionally walk EXPANDED_CASE_SUBDIRS at depth <= 2 per case.

    Caps (Phase 7 D-26 + D-27):
      - MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES (default 1024): hard cap on total resources
        returned across all cases (prevents resources/list from blowing the MCP wire).
      - MCP_GATEWAY_RESOURCE_TREE_MAX_DEPTH (default 2): caps the case subdir walk
        depth; default 2 means `<subdir>/<file>` is exposed but `<subdir>/<sub>/<file>`
        (depth 3) is NOT (extracted/<sub>/* deferred to Phase 10).

    Hidden files (dot-prefixed) are skipped consistent with the v1.0
    `tools/artifacts.py:_is_invalid_filename` convention.
    """
    cap = _env_int("MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES", 1024)
    max_depth = _env_int("MCP_GATEWAY_RESOURCE_TREE_MAX_DEPTH", 2)
    status_root = _status_root()
    out: list[mcp_types.Resource] = []
    for case in _list_cases():
        case_root = status_root / case
        # --- v1.0 depth-1 flat ARTIFACTS enumeration (unchanged) ---
        for artifact in ARTIFACTS:
            if len(out) >= cap:
                return out
            uri = f"mare://cases/{case}/{artifact}"
            artifact_path = case_root / artifact
            out.append(mcp_types.Resource(
                uri=AnyUrl(uri),
                name=f"{case}/{artifact}",
                description=f"Pipeline artifact for case {case}",
                mimeType=_mime_for(artifact_path),
            ))
        # --- Phase 7 D-26: depth-2 walk over EXPANDED_CASE_SUBDIRS ---
        # max_depth=2 -> expose <subdir>/<file>; max_depth<2 -> skip the walk entirely.
        if max_depth < 2:
            continue
        for sub in EXPANDED_CASE_SUBDIRS:
            sub_root = case_root / sub
            if not sub_root.is_dir():
                continue
            try:
                children = sorted(sub_root.iterdir())
            except OSError:
                continue
            for child in children:
                if len(out) >= cap:
                    return out
                # Skip non-files (directories at depth 2 imply depth 3+ -- NOT exposed in Phase 7).
                if not child.is_file():
                    continue
                # Skip hidden files (consistent with uploads._is_invalid_filename).
                if child.name.startswith("."):
                    continue
                uri = f"mare://cases/{case}/{sub}/{child.name}"
                out.append(mcp_types.Resource(
                    uri=AnyUrl(uri),
                    name=f"{case}/{sub}/{child.name}",
                    description=f"Captured {sub} artifact for case {case}",
                    mimeType=_mime_for(child),
                ))
    return out


def _safe_artifact_path(case: str, artifact: str) -> Path:
    """Validate (case, artifact) and return the resolved path under STATUS_ROOT.

    Raises ValueError on traversal / unknown artifact / invalid case name (T-04-01).
    """
    if not CASE_NAME_RE.match(case):
        raise ValueError(f"invalid case name: {case!r}")
    if artifact not in ARTIFACTS:
        raise ValueError(f"unknown artifact name: {artifact!r}")
    path = STATUS_ROOT / case / artifact
    real = Path(os.path.realpath(path))
    status_real = Path(os.path.realpath(STATUS_ROOT))
    try:
        real.relative_to(status_real)
    except ValueError:
        raise ValueError(f"path traversal rejected: {path}")
    return real


def register(mcp: FastMCP) -> None:
    """Register MCP Resources on the FastMCP instance.

    Two-pronged registration (RESEARCH Pitfalls 1 & 2):
      (1) URI template for resources/templates/list discovery.
      (2) Low-level list_resources handler for dynamic resources/list enumeration.
    """

    # (1) Template — registers the URI shape for resources/templates/list.
    @mcp.resource("mare://cases/{case}/{artifact}")
    def read_case_artifact(case: str, artifact: str) -> str | bytes:
        """Read a single pipeline artifact (D-01). Raises FileNotFoundError if absent."""
        real = _safe_artifact_path(case, artifact)
        if not real.exists():
            raise FileNotFoundError(
                f"artifact {artifact} not present for case {case} "
                "(pipeline may not have run that step yet)"
            )
        mime = _mime_for(real)
        if mime.startswith("text/") or mime == "application/json":
            return real.read_text(encoding="utf-8", errors="replace")
        return real.read_bytes()

    # (2) Low-level list_resources handler — runs per-request, sees current FS.
    @mcp._mcp_server.list_resources()
    async def list_all_case_artifacts() -> list[mcp_types.Resource]:
        return _build_resource_list()

    log.info(
        "[resources] registered mare://cases/<case>/<artifact> "
        "(%d depth-1 artifact slots × dynamic case set; "
        "Phase 7 D-26: + depth-2 walk over %d EXPANDED_CASE_SUBDIRS, "
        "capped at MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES=%d, depth=%d)",
        len(ARTIFACTS),
        len(EXPANDED_CASE_SUBDIRS),
        _env_int("MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES", 1024),
        _env_int("MCP_GATEWAY_RESOURCE_TREE_MAX_DEPTH", 2),
    )
