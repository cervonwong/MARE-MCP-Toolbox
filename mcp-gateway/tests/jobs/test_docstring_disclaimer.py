"""Test D-26 disclaimer regression -- both verbatim phrases in every tool docstring."""
from __future__ import annotations

import pytest

from mcp_gateway.tools import jobs as tjobs


PHRASE_IN_MEMORY = "In-memory registry"
PHRASE_SHARED = "shared across all bearer-token clients"
TOOLS = ("start_tool_job", "get_tool_job", "cancel_tool_job", "list_tool_jobs")


@pytest.mark.parametrize("tool", TOOLS)
def test_d26_in_memory_phrase_present(tool):
    """In-memory registry phrase present in every tool docstring."""
    doc = getattr(tjobs, tool).__doc__ or ""
    assert PHRASE_IN_MEMORY in doc, f"{tool} __doc__ missing {PHRASE_IN_MEMORY!r}"


@pytest.mark.parametrize("tool", TOOLS)
def test_d26_shared_phrase_present(tool):
    """`shared across all bearer-token clients` phrase present in every tool docstring."""
    doc = getattr(tjobs, tool).__doc__ or ""
    assert PHRASE_SHARED in doc, f"{tool} __doc__ missing {PHRASE_SHARED!r}"


@pytest.mark.parametrize("tool", TOOLS)
def test_no_leftover_placeholder(tool):
    """{_JOBS_DISCLAIMER} splice token must NOT survive in the post-splice docstring."""
    doc = getattr(tjobs, tool).__doc__ or ""
    assert "{_JOBS_DISCLAIMER}" not in doc, f"{tool} __doc__ has unspliced placeholder"
