"""Phase 13 HARDEN-02 + JOBS-CAP-01: concurrency-atomicity tests for BackgroundJobRegistry.

Tests the BoundedSemaphore cap-enforcement primitive (Phase 13 D-01) under
concurrent contention. Uses _sleep_probe spec so tests run without external
tool dependencies (Pitfall 10 layer 1).

Test matrix (D-02): cap-atomic, all-reachable-terminals release-exactly-once,
pre-spawn-failure releases.

The 5 terminal-state transition paths in _spawn_and_drive:
  - succeeded / failed / cancelled / killed_timeout / killed_log_cap
killed_log_cap is exercised by tests/jobs/test_log_cap.py -- this file covers
the other 4 plus the pre-spawn-failure release-on-except branch.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mcp_gateway import jobs, session_state
from mcp_gateway.jobs import JobCapReached, JobToolSpec


@pytest.fixture
async def attached_registry(registry_factory):
    """Construct a BackgroundJobRegistry(max_inflight=3) and bind it to session_state.

    Mirrors the test_errors.py attached_registry pattern but with cap=3 so the
    HARDEN-02 N+1 contention test (4 concurrent submits) has exactly 1
    over-cap rejection.
    """
    async with registry_factory(max_inflight=3) as reg:
        prev = session_state.JOB_REGISTRY
        session_state.JOB_REGISTRY = reg
        try:
            yield reg
        finally:
            session_state.JOB_REGISTRY = prev


@pytest.mark.asyncio
async def test_n_concurrent_submits_exactly_one_rejected(attached_registry, case_dir_fixture):
    """HARDEN-02 / JOBS-CAP-01 central proof: cap=3, submit 4 concurrently.

    The atomic probe-and-acquire under self._lock (Pitfall 3 fix) guarantees
    that EXACTLY one of the 4 concurrent submits hits the cap, not zero or two.
    Pre-Phase-13 had a TOCTOU race where N+M concurrent submits could all
    observe count<cap and proceed.
    """
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]

    async def _submit_one():
        return await attached_registry.submit(
            spec=spec,
            kwargs={"seconds": 5},
            case_dir_resolved=str(case_dir_fixture),
            effective_timeout_s=30.0,
        )

    results = await asyncio.gather(
        *[_submit_one() for _ in range(4)], return_exceptions=True
    )
    successes = [r for r in results if isinstance(r, jobs.Job)]
    failures = [r for r in results if isinstance(r, JobCapReached)]
    assert len(successes) == 3, f"expected 3 successes, got {len(successes)}: {results}"
    assert len(failures) == 1, f"expected 1 cap-reject, got {len(failures)}: {results}"

    # The cap-reject error payload must read from self._inflight (D-04: dict-is-truth).
    payload = failures[0].to_dict()
    assert payload["error"] == "job cap reached"
    assert payload["inflight"] == 3
    assert payload["cap"] == 3

    # Cleanup: cancel the live ones + await their drive tasks so the registry
    # context exits cleanly.
    for j in successes:
        await attached_registry.cancel(j, reason="test-cleanup")
    await asyncio.gather(
        *[j._drive_task for j in successes if j._drive_task is not None],
        return_exceptions=True,
    )


@pytest.mark.asyncio
async def test_terminal_transitions_release_exactly_once(registry_factory, case_dir_fixture):
    """HARDEN-02: 4 reachable terminal statuses each release the slot exactly once.

    Covers:
      - succeeded   (kwargs={"seconds": 0}, returncode=0)
      - failed      (custom spec running ["false"], returncode=1)
      - cancelled   (kwargs={"seconds": 30}, registry.cancel() before completion)
      - killed_timeout (kwargs={"seconds": 30}, effective_timeout_s=0.2)

    killed_log_cap is covered in tests/jobs/test_log_cap.py -- this test
    exercises the other 4 paths and asserts `_slot_released is True` after each.

    After every terminal transition, the registry's BoundedSemaphore must be
    fully unlocked (no slot leak across cycles).
    """
    # Custom spec for the 'failed' terminal branch (returncode != 0).
    def _build_false_argv(case_dir: Path, kw: dict) -> list[str]:
        return ["false"]

    failed_spec = JobToolSpec(
        name="_test_false",
        slug="test_false",
        build_argv=_build_false_argv,
        default_timeout_s=10.0,
        progress_parser=None,
        kwargs_schema=None,
        description="test-only: spec that always fails (exits 1).",
    )
    sleep_spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]

    async with registry_factory(max_inflight=2) as reg:
        # Case A: succeeded
        j = await reg.submit(
            spec=sleep_spec, kwargs={"seconds": 0},
            case_dir_resolved=str(case_dir_fixture),
            effective_timeout_s=10.0,
        )
        await j._drive_task
        assert j.status == "succeeded", f"expected succeeded, got {j.status}"
        assert j._slot_released is True
        assert not reg._sem.locked(), "slot leaked after succeeded"

        # Case B: failed
        j = await reg.submit(
            spec=failed_spec, kwargs={},
            case_dir_resolved=str(case_dir_fixture),
            effective_timeout_s=10.0,
        )
        await j._drive_task
        assert j.status == "failed", f"expected failed, got {j.status}"
        assert j._slot_released is True
        assert not reg._sem.locked(), "slot leaked after failed"

        # Case C: cancelled
        j = await reg.submit(
            spec=sleep_spec, kwargs={"seconds": 30},
            case_dir_resolved=str(case_dir_fixture),
            effective_timeout_s=300.0,
        )
        # Give the drive task a moment to spawn the subprocess so cancel hits a
        # real process (not the pre-spawn pgid==None early-return branch).
        await asyncio.sleep(0.1)
        await reg.cancel(j, reason="user")
        await j._drive_task
        assert j.status == "cancelled", f"expected cancelled, got {j.status}"
        assert j._slot_released is True
        assert not reg._sem.locked(), "slot leaked after cancelled"

        # Case D: killed_timeout
        j = await reg.submit(
            spec=sleep_spec, kwargs={"seconds": 30},
            case_dir_resolved=str(case_dir_fixture),
            effective_timeout_s=0.2,
        )
        await j._drive_task
        assert j.status == "killed_timeout", f"expected killed_timeout, got {j.status}"
        assert j._slot_released is True
        assert not reg._sem.locked(), "slot leaked after killed_timeout"


@pytest.mark.asyncio
async def test_cancel_pre_spawn_releases(registry_factory, case_dir_fixture, monkeypatch):
    """HARDEN-02: pre-spawn failure (ensure_subdir raises) releases the slot.

    Submit a job; monkeypatched ensure_subdir raises PermissionError BEFORE the
    drive task is created. The submit()'s `except BaseException: self._sem.release()`
    branch must release the slot so a subsequent submit can re-acquire.
    """
    sleep_spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    async with registry_factory(max_inflight=2) as reg:
        original_ensure = jobs.ensure_subdir
        calls = [0]

        def boom(case_dir, sub):
            calls[0] += 1
            if calls[0] == 1:
                raise PermissionError("test injection: pre-spawn failure")
            return original_ensure(case_dir, sub)

        monkeypatch.setattr(jobs, "ensure_subdir", boom)

        with pytest.raises(PermissionError):
            await reg.submit(
                spec=sleep_spec, kwargs={"seconds": 0},
                case_dir_resolved=str(case_dir_fixture),
                effective_timeout_s=10.0,
            )

        assert not reg._sem.locked(), \
            "pre-spawn failure must release the slot (submit-except branch)"

        # Subsequent submit succeeds -- slot was returned to the semaphore.
        j = await reg.submit(
            spec=sleep_spec, kwargs={"seconds": 0},
            case_dir_resolved=str(case_dir_fixture),
            effective_timeout_s=10.0,
        )
        await j._drive_task
        assert j.status == "succeeded"
        assert j._slot_released is True
