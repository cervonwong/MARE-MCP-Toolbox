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


def _mime_for(path: Path) -> str:
    """Return the MIME type for a path based on its (case-insensitive) suffix."""
    return _MIME_MAP.get(path.suffix.lower(), "application/octet-stream")


def _list_cases() -> list[str]:
    """Enumerate case directories under STATUS_ROOT (mirrors tools/cases.py:list_cases).

    Returns sorted list of case dir names matching CASE_NAME_RE. Empty if
    STATUS_ROOT does not exist.
    """
    if not STATUS_ROOT.exists():
        return []
    return sorted(
        p.name for p in STATUS_ROOT.iterdir()
        if p.is_dir() and CASE_NAME_RE.match(p.name)
    )


def _build_resource_list() -> list[mcp_types.Resource]:
    """D-02: enumerate (all cases) × (13 artifacts). Filesystem-fresh per call."""
    out: list[mcp_types.Resource] = []
    for case in _list_cases():
        for artifact in ARTIFACTS:
            uri = f"mare://cases/{case}/{artifact}"
            artifact_path = STATUS_ROOT / case / artifact
            out.append(mcp_types.Resource(
                uri=AnyUrl(uri),
                name=f"{case}/{artifact}",
                description=f"Pipeline artifact for case {case}",
                mimeType=_mime_for(artifact_path),
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
        "(%d artifact slots × dynamic case set)",
        len(ARTIFACTS),
    )
