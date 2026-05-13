"""Phase 7 D-04: setfacl must be on PATH inside the container.

The Dockerfile apt install line adds 'acl' to the package list. This unit test
fails loudly if the apt package was forgotten across a rebuild (e.g., on a host
where the image was rebuilt without Phase 7's Dockerfile edits).
"""
from __future__ import annotations

import shutil


def test_setfacl_on_path() -> None:
    """D-04: `shutil.which('setfacl')` is not None."""
    assert shutil.which("setfacl") is not None, (
        "Phase 7 D-04 requires apt package 'acl' (provides setfacl). "
        "Dockerfile apt install list must include 'acl'."
    )
