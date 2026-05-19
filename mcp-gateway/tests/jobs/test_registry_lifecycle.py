"""Test BackgroundJobRegistry async-context-manager lifecycle (D-14 + JOBS-04)."""
from __future__ import annotations

import pytest

from mcp_gateway import jobs


@pytest.mark.asyncio
async def test_enter_exit_clean():
    reg = jobs.BackgroundJobRegistry(max_inflight=4, cancel_grace_s=1.0, max_completed=10)
    async with reg as entered:
        assert entered is reg


@pytest.mark.asyncio
async def test_empty_registry_lists_are_empty():
    async with jobs.BackgroundJobRegistry(
        max_inflight=4, cancel_grace_s=1.0, max_completed=10
    ) as reg:
        assert reg.list_inflight() == []
        assert reg.list_completed() == []


@pytest.mark.asyncio
async def test_exit_on_empty_returns_cleanly():
    """__aexit__ on empty registry must not raise."""
    reg = jobs.BackgroundJobRegistry(max_inflight=4, cancel_grace_s=1.0, max_completed=10)
    async with reg:
        pass
    # No exception means clean exit.


@pytest.mark.asyncio
async def test_in_memory_invariant_jobs04():
    """JOBS-04: registry holds in-memory dicts; no disk/db persistence."""
    reg = jobs.BackgroundJobRegistry(max_inflight=4, cancel_grace_s=1.0, max_completed=10)
    assert hasattr(reg, "_inflight")
    assert hasattr(reg, "_completed")
    assert isinstance(reg._inflight, dict)
    # _completed is OrderedDict (FIFO eviction support); just check dict-like
    assert hasattr(reg._completed, "popitem")


@pytest.mark.asyncio
async def test_re_enter_after_exit_supported():
    """Document current re-entry behavior: registry instance is re-enterable
    (state survives because __aexit__ does not destroy _inflight/_completed)."""
    reg = jobs.BackgroundJobRegistry(max_inflight=4, cancel_grace_s=1.0, max_completed=10)
    async with reg:
        pass
    # Re-enter — should not raise
    async with reg:
        assert reg.list_inflight() == []
