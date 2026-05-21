"""Phase 7 D-04 + Phase 14 D-04: setfacl must be on PATH inside the container.

Host/container contract (Phase 14 D-04, Option A):
- Inside the Kali Linux container (the reference run environment): the apt
  package `acl` is installed by the Dockerfile, providing `setfacl`. This
  test MUST run and pass there.
- On a bare developer host (no `acl` package): `shutil.which('setfacl')`
  returns None and this test SKIPS cleanly. The host is not the reference
  run environment for ACL behaviour; container builds already install the
  `acl` package, and `Dockerfile` re-applies ACLs at container start.

The skipif keeps `pytest -m 'not slow'` green on bare hosts while still
enforcing the contract inside the container. See `.planning/v1.1-MILESTONE-AUDIT.md`
section "Current Test Gaps" for the audit trail.
"""
from __future__ import annotations

import shutil

import pytest


@pytest.mark.skipif(
    shutil.which("setfacl") is None,
    reason="setfacl host-binary missing; container-only contract (Phase 14 D-04)",
)
def test_setfacl_on_path() -> None:
    """D-04: `shutil.which('setfacl')` is not None inside the container."""
    assert shutil.which("setfacl") is not None, (
        "Phase 7 D-04 requires apt package 'acl' (provides setfacl). "
        "Container builds install this via Dockerfile; on bare hosts the test "
        "skips via the skipif decorator above."
    )
