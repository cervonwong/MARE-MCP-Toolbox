"""Test Q3 hand-rolled kwargs validator (no jsonschema dep)."""
from __future__ import annotations

import pytest

from mcp_gateway import jobs


def test_none_schema_is_noop():
    spec = jobs.JOB_TOOL_REGISTRY["_log_burst_probe"]  # kwargs_schema=None
    assert spec.kwargs_schema is None
    # should not raise
    assert jobs._validate_kwargs(spec, {}) is None
    assert jobs._validate_kwargs(spec, {"anything": "goes"}) is None


def test_sleep_probe_boundary_min():
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    assert jobs._validate_kwargs(spec, {"seconds": 0}) is None


def test_sleep_probe_boundary_max():
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    assert jobs._validate_kwargs(spec, {"seconds": 600}) is None


def test_sleep_probe_negative_rejected():
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    with pytest.raises(jobs.InvalidKwargs) as ei:
        jobs._validate_kwargs(spec, {"seconds": -1})
    assert ei.value.field == "seconds"
    assert ei.value.expected == ">= 0"
    assert ei.value.got == "-1"


def test_sleep_probe_over_max_rejected():
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    with pytest.raises(jobs.InvalidKwargs) as ei:
        jobs._validate_kwargs(spec, {"seconds": 601})
    assert ei.value.field == "seconds"
    assert ei.value.expected == "<= 600"
    assert ei.value.got == "601"


def test_sleep_probe_bool_is_not_integer():
    """Q3 walker: bool is NOT integer (despite Python's bool<->int inheritance)."""
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    with pytest.raises(jobs.InvalidKwargs) as ei:
        jobs._validate_kwargs(spec, {"seconds": True})
    assert ei.value.field == "seconds"
    assert ei.value.expected == "integer"
    assert ei.value.got == "bool"


def test_sleep_probe_string_rejected():
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    with pytest.raises(jobs.InvalidKwargs) as ei:
        jobs._validate_kwargs(spec, {"seconds": "5"})
    assert ei.value.field == "seconds"
    assert ei.value.expected == "integer"
    assert ei.value.got == "str"


def test_capa_sample_max_length():
    spec = jobs.JOB_TOOL_REGISTRY["capa"]
    with pytest.raises(jobs.InvalidKwargs) as ei:
        jobs._validate_kwargs(spec, {"sample": "x" * 257})
    assert ei.value.field == "sample"
    assert ei.value.expected == "length <= 256"
    assert ei.value.got == "length 257"


def test_unknown_field_ignored():
    """Q3 forward-compat: extra fields not in schema are silently accepted."""
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    assert jobs._validate_kwargs(spec, {"seconds": 1, "future_field": 42}) is None


def test_no_jsonschema_import_in_jobs_module():
    """Q3 invariant: jobs.py does NOT import jsonschema (hand-rolled walker)."""
    import inspect

    src = inspect.getsource(jobs)
    assert "import jsonschema" not in src
    assert "from jsonschema" not in src
