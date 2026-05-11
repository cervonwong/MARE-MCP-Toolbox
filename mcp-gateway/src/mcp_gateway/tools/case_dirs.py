"""Case directory resolver for gateway tools."""
from __future__ import annotations

import os
from pathlib import Path

from . import samples


def resolve_case_dir(case_dir: str) -> str:
    """Return a canonical case directory path constrained to STATUS_ROOT."""
    if not isinstance(case_dir, str) or not case_dir:
        raise ValueError("case_dir must be a non-empty string")

    real_case = Path(os.path.realpath(case_dir))
    real_status = Path(os.path.realpath(samples.STATUS_ROOT))
    try:
        real_case.relative_to(real_status)
    except ValueError as exc:
        raise ValueError(f"case_dir must be under {real_status}") from exc
    if real_case == real_status:
        raise ValueError(f"case_dir must be a case directory under {real_status}")
    return str(real_case)
