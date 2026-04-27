"""CLI-04, D-04: extension → MIME map for case-artifact resources."""
from __future__ import annotations
from pathlib import Path

import pytest

# Import is intentionally inside the test (the module may not exist yet at TDD-RED).
def _mime_for(name: str) -> str:
    from mcp_gateway.tools.resources import _mime_for as fn
    return fn(Path(name))


@pytest.mark.parametrize("filename,expected", [
    ("CURRENT_STATE.json",        "application/json"),
    ("01_strings_raw.txt",        "text/plain"),
    ("agent.log",                 "text/plain"),
    ("00_sample_profile.md",      "text/markdown"),
    ("INDEX.md",                  "text/markdown"),
    ("blob.bin",                  "application/octet-stream"),
    ("noext",                     "application/octet-stream"),
    ("FOO.JSON",                  "application/json"),  # case-insensitive
    ("UPPER.MD",                  "text/markdown"),
])
def test_mime_map_d04(filename, expected):
    assert _mime_for(filename) == expected
