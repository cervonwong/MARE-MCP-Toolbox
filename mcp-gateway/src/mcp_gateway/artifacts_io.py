"""Pure path helpers for v1.1 RE tools (Phase 6 / FOUND-04).

This module is a LEAF -- it imports stdlib only, never from `mcp_gateway.*` (D-07).
Phase 7+ tools call `confine_to(resolve_case_dir(case_dir), user_path)` to compose
the STATUS_ROOT guard (`tools/case_dirs.resolve_case_dir`) with the realpath
containment check here.

Public API:
- `EXPANDED_CASE_SUBDIRS`: tuple of nine canonical case-dir subdir names (D-16)
- `confine_to(case_dir, path)`: realpath + `is_relative_to` containment (D-11..D-14)
- `ensure_subdir(case_dir, name)`: lazy mkdir with slug-validated name (D-15)
- `tool_log_path(case_dir, slug)`: case_dir/tool-logs/<ts>-<slug>-<rand4>.txt (D-09)
- `ensure_mare_shell_access(case_dir)`: idempotent POSIX ACL grant for mare-shell (D-05, D-06)

References:
- CONTEXT.md D-09, D-11..D-16
- Phase 7 CONTEXT.md D-03, D-05, D-06 (mare-shell ACL semantics)
- RESEARCH.md Pattern 8 (confine_to), Code Examples sec.6-8
- v1.0 ancestor: `tools/artifacts.py:115-139` (NOT modified by this phase)
"""
from __future__ import annotations

import datetime
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

# D-16: catalog of the nine expanded case-dir subdirs.
# Order matters for catalog iteration; tuple guarantees immutability.
EXPANDED_CASE_SUBDIRS: tuple[str, ...] = (
    "tool-logs",
    "extracted",
    "hex",
    "rop",
    "dynamic",
    "qemu",
    "disassembly",
    "decompilation",
    "xrefs",
)

# D-09 + D-15: shared slug regex. ^[a-z0-9][a-z0-9_-]{0,39}$ after lowercase.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def _validate_slug(slug: str) -> str:
    """Auto-lowercase then validate; return canonical lowercased form (D-09)."""
    lowered = slug.lower()
    if not _SLUG_RE.fullmatch(lowered):
        raise ValueError(
            f"slug must match {_SLUG_RE.pattern!r} (after lowercase), got {slug!r}"
        )
    return lowered


def confine_to(case_dir: str | os.PathLike, path: str | os.PathLike) -> Path:
    """Reject path-traversal escapes; return canonical resolved Path under case_dir.

    Semantics (D-11..D-14):
    1. NUL byte in either argument -> ValueError (D-13)
    2. case_dir is resolved with strict=True (must exist, must be directory) (D-11 step 1)
    3. Relative `path` joined onto resolved case_dir; absolute used as-is (D-11 step 2)
    4. Target resolved with strict=False -- non-existing leaf is OK (D-11 step 3, D-13)
    5. Containment via `target.is_relative_to(case_dir)` or `target == case_dir` (D-11 step 4)
    6. Returns the canonical resolved Path (D-11 step 5)

    Does NOT enforce STATUS_ROOT (D-14) -- that is `tools/case_dirs.resolve_case_dir`'s job.
    Symlinks inside case_dir whose target also lies inside case_dir are allowed (D-12);
    Path.resolve() follows the link before containment is checked.
    """
    # D-13: NUL byte rejection must precede any Path operation.
    case_str = os.fspath(case_dir)
    path_str = os.fspath(path)
    if "\x00" in case_str or "\x00" in path_str:
        raise ValueError("path contains NUL byte")

    # D-11 step 1: case_dir must exist and be a directory.
    try:
        resolved_case = Path(case_str).resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise ValueError(f"case_dir does not exist: {case_str!r}") from exc
    if not resolved_case.is_dir():
        raise ValueError(f"case_dir is not a directory: {case_str!r}")

    # D-11 step 2: relative paths join onto resolved case_dir; absolute as-is.
    candidate = Path(path_str)
    if not candidate.is_absolute():
        candidate = resolved_case / candidate

    # D-11 step 3: strict=False -- non-existing leaf is the legitimate write case (D-13).
    resolved_target = candidate.resolve(strict=False)

    # D-11 step 4: containment via is_relative_to (Python 3.9+; container is 3.11+).
    # Allow target == case_dir as well as proper descendants.
    if not (resolved_target == resolved_case or resolved_target.is_relative_to(resolved_case)):
        raise ValueError(f"path escapes case_dir: {path_str!r}")

    return resolved_target


def ensure_subdir(case_dir: str | Path, name: str) -> Path:
    """Lazily create `case_dir/<name>` with parents=False, exist_ok=True (D-15).

    Idempotent and concurrency-safe -- two coroutines calling for the same subdir
    race the mkdir cleanly because exist_ok=True swallows FileExistsError.

    Validates `name` against the slug regex `^[a-z0-9][a-z0-9_-]{0,39}$` (auto-
    lowercased before validation). Returns the resolved Path.

    Does NOT validate that case_dir is under STATUS_ROOT (callers compose with
    `resolve_case_dir` upstream -- see CONTEXT.md Claude's-Discretion).
    """
    lowered = _validate_slug(name)
    target = Path(case_dir) / lowered
    target.mkdir(parents=False, exist_ok=True)
    return target.resolve(strict=True)


def tool_log_path(case_dir: str | Path, slug: str) -> Path:
    """Return the canonical log file path for one runner invocation (D-09).

    Format: `case_dir/tool-logs/<%Y%m%dT%H%M%SZ>-<slug>-<rand4>.txt`
    - timestamp: UTC, compact ISO-basic (no colons), lexicographically sortable
    - slug: caller-supplied; auto-lowercased; must match `^[a-z0-9][a-z0-9_-]{0,39}$`
    - rand4: `secrets.token_hex(2)` -- 4 lowercase hex chars, 16 bits of entropy
      against same-second collisions

    NOTE: This function constructs the path string only. The caller is
    responsible for `ensure_subdir(case_dir, "tool-logs")` before writing.
    """
    lowered = _validate_slug(slug)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rand4 = secrets.token_hex(2)  # 4 lowercase hex chars
    return Path(case_dir) / "tool-logs" / f"{ts}-{lowered}-{rand4}.txt"


# D-03 (Phase 7): canonical ACL applied to every case-dir so the mare-shell UID
# (created by Dockerfile useradd -r -u 700 mare-shell) can rwx the case-dir
# without joining the agent group. Default ACL means children inherit the grant.
_MARE_SHELL_ACL_SPEC = "u:agent:rwx,g:mare-shell:rwx,o::---"


def ensure_mare_shell_access(case_dir: str | os.PathLike) -> None:
    """Idempotent POSIX ACL grant for mare-shell on case_dir (D-05, D-06).

    Applies the canonical ACL `u:agent:rwx,g:mare-shell:rwx,o::---` as BOTH:
      * Access ACL (`setfacl -m`) -- grants the existing case_dir directory
      * Default ACL (`setfacl -d -m`) -- children created later inherit the grant

    Both calls are idempotent at the OS level: setfacl is a no-op when the ACL
    already matches. Phase 7's run_shell / write_artifact / append_artifact
    invoke this helper before any spawn/write, amortising the cost to the
    first call per case_dir (D-05 lazy backfill semantics).

    Raises:
      RuntimeError -- `setfacl` not on PATH (Phase 7 D-06 fail-loud: requires
        apt 'acl' package per Dockerfile D-04); OR either setfacl invocation
        exits non-zero (Phase 7 ships with ACLs REQUIRED, not optional).

    NOTE: This function is intentionally NOT called from `ensure_subdir`.
    Read-only artifact creators (the runner writing tool-logs as `agent`)
    don't need mare-shell ACLs (D-05 rationale).
    """
    if shutil.which("setfacl") is None:
        raise RuntimeError(
            "setfacl not on PATH; Phase 7 (D-04) requires apt 'acl' package "
            "to be installed in the container image"
        )
    case_str = str(case_dir)
    base = ["setfacl", "-m", _MARE_SHELL_ACL_SPEC, case_str]
    default = ["setfacl", "-d", "-m", _MARE_SHELL_ACL_SPEC, case_str]
    for cmd in (base, default):
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(
                f"setfacl failed ({' '.join(cmd)!r}): "
                f"exit={res.returncode} stderr={res.stderr.strip()!r}"
            )
