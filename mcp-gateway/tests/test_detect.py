"""Tests for detect_backend() priority chain.

Maps to: .planning/phases/02-mcp-gateway/02-VALIDATION.md GW-03 unit row.
Uses monkeypatching of module-level Path constants + shutil.which to avoid touching
the real filesystem (tests must run on developer laptops without IDA/BN installed).
"""
from __future__ import annotations
from pathlib import Path

import pytest

from mcp_gateway.backend import detect as detect_mod


class FakePath:
    def __init__(self, *, is_dir=False, exists=False, iter_items=()):
        self._is_dir = is_dir
        self._exists = exists
        self._iter = list(iter_items)

    def is_dir(self):
        return self._is_dir

    def exists(self):
        return self._exists

    def iterdir(self):
        return iter(self._iter)


def _patch_state(monkeypatch, *, ida=False, bn=False, ghidra=False, ida_cmd=True):
    monkeypatch.setattr(
        detect_mod, "IDA_DIR",
        FakePath(is_dir=ida, iter_items=(["x"] if ida else [])),
    )
    monkeypatch.setattr(detect_mod, "BN_INSTALL_API", FakePath(exists=bn))
    monkeypatch.setattr(detect_mod, "BN_MCP_SCRIPT", FakePath(exists=bn))
    monkeypatch.setattr(detect_mod, "GHIDRA_MCP_SCRIPT", FakePath(exists=ghidra))
    monkeypatch.setattr(
        detect_mod.shutil, "which",
        lambda name: "/usr/local/bin/idalib-mcp" if (name == "idalib-mcp" and ida_cmd) else None,
    )


def test_priority_ida_wins_when_all_installed(monkeypatch):
    _patch_state(monkeypatch, ida=True, bn=True, ghidra=True)
    assert detect_mod.detect_backend() == "ida"


def test_bn_selected_when_ida_dir_empty(monkeypatch):
    _patch_state(monkeypatch, ida=False, bn=True, ghidra=True)
    assert detect_mod.detect_backend() == "bn"


def test_bn_selected_when_idalib_mcp_command_missing(monkeypatch):
    _patch_state(monkeypatch, ida=True, ida_cmd=False, bn=True, ghidra=True)
    assert detect_mod.detect_backend() == "bn"


def test_ghidra_selected_when_ida_and_bn_absent(monkeypatch):
    _patch_state(monkeypatch, ida=False, bn=False, ghidra=True)
    assert detect_mod.detect_backend() == "ghidra"


def test_raises_when_no_backend(monkeypatch):
    _patch_state(monkeypatch, ida=False, bn=False, ghidra=False)
    with pytest.raises(RuntimeError, match="No disassembler backend available"):
        detect_mod.detect_backend()


def test_priority_matches_bash_script():
    """Smoke test: ensure BACKENDS tuple order mirrors configure-agent-mcp.sh lines 67-119."""
    assert detect_mod.BACKENDS == ("ida", "bn", "ghidra")
