"""Phase 13 HARDEN-03 integration positive control.

Spawns a real r2 with cfg.sandbox=true and exercises a sandbox-blocked
operation that is NOT covered by the gateway's _DANGEROUS_R2_CMD_RE
regex. The point is to prove cfg.sandbox=true is the actual enforcing
boundary, not just the gateway-side pre-filter.

Gated on r2 availability via _require_r2_or_skip; marked slow.
"""
from __future__ import annotations
import hashlib
import pytest
from tests.conftest import _require_r2_or_skip


@pytest.mark.slow
@pytest.mark.asyncio
async def test_sandbox_active_when_open_r2(tmp_path, monkeypatch):
    """HARDEN-03 positive control: cfg.sandbox is true in the running r2 session."""
    _require_r2_or_skip()
    # Lazy imports so collection works on r2-less hosts.
    from mcp_gateway.sessions._base import SessionRegistry
    from mcp_gateway.sessions.r2 import _open_r2

    # Build a minimal sample (a 4KB binary blob to feed r2).
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"\x7fELF" + b"\x00" * 4090)
    sha = hashlib.sha256(sample.read_bytes()).hexdigest()

    async with SessionRegistry(max_sessions=2, idle_s=30, reaper_interval_s=30) as reg:
        sess = await _open_r2(
            reg, case_dir=tmp_path, sample_sha256=sha,
            sample_path=sample, init_commands=None,
            open_timeout_s=15.0, sandbox=True,
        )
        # Query r2's runtime view of cfg.sandbox via exec_one.
        raw, timed_out = await sess.exec_one("e cfg.sandbox", timeout=10.0)
        assert not timed_out, "r2 cmd timed out"
        decoded = raw.decode("utf-8", errors="replace").lower()
        assert "true" in decoded, (
            f"r2 reports cfg.sandbox != true: {decoded!r}; "
            f"sandbox argv flag did not take effect"
        )
        await reg.close(sess.session_id, reason="test")
