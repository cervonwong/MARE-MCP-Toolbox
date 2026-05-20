"""Phase 11 Plan 02 Wave-0 tests for the dynamic primitive layer.

These tests start as RED (ImportError on collection because dynamic.py does
not yet exist) and flip GREEN when Plan 02 Task 2 lands the dynamic.py
module + the JobToolSpec.post_terminal_hook extension.

Pattern reference: Phase 8 Plan 01 (test_sessions.py), Phase 9 Plan 04
(jobs test suite), Phase 10 Plan 01 (test_extraction.py).
"""
from __future__ import annotations

import dataclasses
import importlib
import inspect
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Profiles + allowlist (DYN-03)
# ---------------------------------------------------------------------------
def test_strace_profiles_keys():
    from mcp_gateway.dynamic import STRACE_PROFILES
    assert set(STRACE_PROFILES.keys()) == {
        "file_io", "network", "process", "signals",
        "file_network_process", "all", "summary",
    }


def test_strace_profile_file_io_argv():
    from mcp_gateway.dynamic import STRACE_PROFILES
    assert STRACE_PROFILES["file_io"] == ("-f", "-e", "trace=file,desc")


def test_strace_profile_file_network_process_argv():
    from mcp_gateway.dynamic import STRACE_PROFILES
    assert STRACE_PROFILES["file_network_process"] == (
        "-f", "-e", "trace=file,desc,network,process",
    )


def test_ltrace_profiles_keys():
    from mcp_gateway.dynamic import LTRACE_PROFILES
    assert set(LTRACE_PROFILES.keys()) == {
        "library_calls", "system_only", "library_and_system",
        "library_count_summary",
    }


def test_qemu_user_profiles_keys():
    from mcp_gateway.dynamic import QEMU_USER_PROFILES
    assert set(QEMU_USER_PROFILES.keys()) == {
        "simple", "syscall_strace", "singlestep_asm",
        "page_faults", "all_trace",
    }


def test_extra_args_allowlist_accepts_normal_flags():
    from mcp_gateway.dynamic import EXTRA_ARGS_ALLOWLIST_RE
    accepted = [
        "-f", "-ff", "--help",
        "--signal=KILL", "trace=open,read",
        "--output-format=text",
    ]
    for s in accepted:
        assert EXTRA_ARGS_ALLOWLIST_RE.match(s), f"should accept: {s!r}"


def test_extra_args_rejects_metachar():
    from mcp_gateway.dynamic import _validate_argv_list
    rejected = [
        "; rm", "foo|bar", "$HOME", "`whoami`",
        ">/tmp/x", "<input", "a\nb", "a\tb",
        "a\\b", "a\x00b",
    ]
    for s in rejected:
        with pytest.raises(ValueError):
            _validate_argv_list([s], field="extra_args")


def test_extra_args_denylist_blocks_dangerous_flags():
    from mcp_gateway.dynamic import _validate_argv_list
    for bad in [
        "-o", "-D", "--daemonize", "--detach", "-p",
        "--attach", "--output-separately", "-b", "--detach-on",
    ]:
        with pytest.raises(ValueError):
            _validate_argv_list([bad], field="extra_args")


def test_extra_args_denylist_handles_equals_form():
    from mcp_gateway.dynamic import _validate_argv_list
    with pytest.raises(ValueError):
        _validate_argv_list(["--detach-on=execve"], field="extra_args")


# ---------------------------------------------------------------------------
# wrap_netns (DYN-03 net-isolation)
# ---------------------------------------------------------------------------
def test_wrap_netns_prefix():
    from mcp_gateway.dynamic import wrap_netns
    assert wrap_netns(["strace", "-f", "/bin/ls"]) == [
        "unshare", "--net", "--ipc", "--uts", "--",
        "strace", "-f", "/bin/ls",
    ]


def test_wrap_netns_idempotent_for_non_wrapped():
    from mcp_gateway.dynamic import wrap_netns
    assert wrap_netns([]) == ["unshare", "--net", "--ipc", "--uts", "--"]


# ---------------------------------------------------------------------------
# build_*_argv (DYN-03 / DYN-04)
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_case_dir(tmp_path, monkeypatch):
    """Create a case_dir with dynamic/ + qemu/ subdirs and stub resolve_sample."""
    case_dir = tmp_path / "999-fakecase"
    case_dir.mkdir()
    (case_dir / "dynamic").mkdir()
    (case_dir / "qemu").mkdir()

    # Stub resolve_sample so builders don't need a real upload.
    from mcp_gateway.tools import samples

    def _fake_resolve(sample):
        return "/tmp/fakesample"

    monkeypatch.setattr(samples, "resolve_sample", _fake_resolve)
    return case_dir


def test_build_strace_argv_shape(fake_case_dir):
    from mcp_gateway.dynamic import build_strace_argv
    argv = build_strace_argv(fake_case_dir, {
        "sample": "deadbeef" * 8,
        "profile": "file_io",
        "extra_args": ["-y"],
        "run_argv": ["arg1"],
    })
    assert argv[0:5] == ["unshare", "--net", "--ipc", "--uts", "--"]
    assert argv[5] == "strace"
    assert "-f" in argv and "-e" in argv and "trace=file,desc" in argv
    assert "-o" in argv
    # find the -o output path
    o_idx = argv.index("-o")
    out_path = argv[o_idx + 1]
    assert "/dynamic/" in out_path and out_path.endswith(".txt")
    # "--" separator appears at least once in builder's own argv (excluding wrap prefix)
    assert "--" in argv[5:]
    assert "/tmp/fakesample" in argv
    assert "arg1" in argv


def test_build_strace_argv_rejects_bad_profile(fake_case_dir):
    from mcp_gateway.dynamic import build_strace_argv
    with pytest.raises(ValueError, match="nonexistent_profile"):
        build_strace_argv(fake_case_dir, {
            "sample": "x",
            "profile": "nonexistent_profile",
        })


def test_build_strace_argv_rejects_metachar_extra_args(fake_case_dir):
    from mcp_gateway.dynamic import build_strace_argv
    with pytest.raises(ValueError):
        build_strace_argv(fake_case_dir, {
            "sample": "x" * 16,
            "profile": "file_io",
            "extra_args": ["; rm -rf /"],
        })


def test_build_ltrace_argv_shape(fake_case_dir):
    from mcp_gateway.dynamic import build_ltrace_argv
    argv = build_ltrace_argv(fake_case_dir, {
        "sample": "deadbeef" * 8,
        "profile": "library_calls",
    })
    assert argv[0:5] == ["unshare", "--net", "--ipc", "--uts", "--"]
    assert argv[5] == "ltrace"
    assert "-f" in argv
    assert "-o" in argv
    o_idx = argv.index("-o")
    out_path = argv[o_idx + 1]
    assert "/dynamic/" in out_path
    assert "ltrace" in out_path
    assert out_path.endswith(".txt")


def test_build_qemu_user_argv_shape(fake_case_dir):
    from mcp_gateway.dynamic import build_qemu_user_argv
    argv = build_qemu_user_argv(fake_case_dir, {
        "sample": "deadbeef" * 8,
        "arch": "arm",
        "profile": "simple",
    })
    assert argv[0:5] == ["unshare", "--net", "--ipc", "--uts", "--"]
    assert argv[5] == "qemu-arm-static"
    # qemu output sink — qemu/ is reserved (used by JOBS log capture),
    # so we just confirm /tmp/fakesample landed in argv.
    assert "/tmp/fakesample" in argv


def test_build_qemu_user_argv_rejects_bad_arch(fake_case_dir):
    from mcp_gateway.dynamic import build_qemu_user_argv
    with pytest.raises(ValueError, match="not_an_arch"):
        build_qemu_user_argv(fake_case_dir, {
            "sample": "x" * 16,
            "arch": "not_an_arch",
            "profile": "simple",
        })


# ---------------------------------------------------------------------------
# DynamicCapabilities + probe_all (DYN-06)
# ---------------------------------------------------------------------------
def test_dynamic_capabilities_dataclass_fields():
    from mcp_gateway.dynamic import DynamicCapabilities
    names = [f.name for f in dataclasses.fields(DynamicCapabilities)]
    expected = [
        "probed_at",
        "dynamic_mode_enabled",
        "ptrace_scope",
        "ptrace_traceme_works",
        "binfmt_misc_mounted",
        "qemu_architectures",
        "qemu_static_binaries",
        "netns_feasible",
        "unshare_path",
        "gdb_path",
        "gdb_version",
        "strace_path",
        "ltrace_path",
        "warnings",
    ]
    assert names == expected, f"got: {names}"


def test_probe_all_returns_capabilities_never_raises():
    from mcp_gateway.dynamic import DynamicCapabilities, probe_all
    caps = probe_all()
    assert isinstance(caps, DynamicCapabilities)
    assert caps.probed_at  # non-empty ISO string


def test_probe_warnings_on_missing_unshare(monkeypatch):
    import shutil as _shutil
    import subprocess as _subprocess
    from mcp_gateway import dynamic as dyn_mod

    real_which = _shutil.which

    def _which(name):
        if name == "unshare":
            return None
        return real_which(name)

    def _fake_run(*args, **kwargs):
        raise FileNotFoundError("unshare not found")

    monkeypatch.setattr(dyn_mod.shutil, "which", _which)
    monkeypatch.setattr(dyn_mod.subprocess, "run", _fake_run)
    caps = dyn_mod.probe_all()
    assert caps.netns_feasible is False
    assert any("unshare" in w for w in caps.warnings)


def test_probe_qemu_architectures(tmp_path, monkeypatch):
    from mcp_gateway import dynamic as dyn_mod

    fake_binfmt = tmp_path / "binfmt_misc"
    fake_binfmt.mkdir()
    (fake_binfmt / "register").write_text("")  # marker
    (fake_binfmt / "qemu-arm").write_text(
        "enabled\ninterpreter /usr/bin/qemu-arm-static\nflags: F\n"
    )

    real_which = dyn_mod.shutil.which

    def _which(name):
        if name == "qemu-arm-static":
            return "/usr/bin/qemu-arm-static"
        return real_which(name)

    monkeypatch.setattr(dyn_mod, "_BINFMT_DIR", fake_binfmt)
    monkeypatch.setattr(dyn_mod.shutil, "which", _which)
    arches, bins = dyn_mod._probe_qemu(binfmt_mounted=True)
    assert "arm" in arches


# ---------------------------------------------------------------------------
# reap_followfork_strays (DYN-07)
# ---------------------------------------------------------------------------
def test_reap_followfork_strays_returns_zero_when_no_strays():
    from mcp_gateway.dynamic import reap_followfork_strays
    n = reap_followfork_strays(os.getpid(), os.getpgrp())
    assert n == 0


def test_reap_followfork_strays_signature():
    from mcp_gateway.dynamic import reap_followfork_strays
    sig = inspect.signature(reap_followfork_strays)
    names = list(sig.parameters)
    assert names == ["runner_pid", "original_pgid"]


# ---------------------------------------------------------------------------
# JobToolSpec backward-compat (Open Question #3)
# ---------------------------------------------------------------------------
def test_jobtoolspec_has_post_terminal_hook_field():
    from mcp_gateway.jobs import JobToolSpec
    field_names = {f.name for f in dataclasses.fields(JobToolSpec)}
    assert "post_terminal_hook" in field_names


def test_jobtoolspec_post_terminal_hook_defaults_none():
    from mcp_gateway.jobs import JobToolSpec
    f = next(
        f for f in dataclasses.fields(JobToolSpec)
        if f.name == "post_terminal_hook"
    )
    assert f.default is None


def test_phase9_specs_still_construct_without_hook():
    # Ensure Phase 9 specs are registered AND have None post_terminal_hook
    from mcp_gateway.jobs import JOB_TOOL_REGISTRY
    for name in ["_sleep_probe", "_log_burst_probe", "capa"]:
        assert name in JOB_TOOL_REGISTRY, f"missing Phase 9 spec: {name}"
        assert JOB_TOOL_REGISTRY[name].post_terminal_hook is None


def test_phase10_specs_still_construct_without_hook():
    # Importing extraction registers Phase 10 specs.
    import mcp_gateway.extraction  # noqa: F401
    from mcp_gateway.jobs import JOB_TOOL_REGISTRY
    for name in ["unblob", "binwalk_extract"]:
        assert name in JOB_TOOL_REGISTRY, f"missing Phase 10 spec: {name}"
        assert JOB_TOOL_REGISTRY[name].post_terminal_hook is None


# ---------------------------------------------------------------------------
# JobToolSpec registrations from dynamic.py
# ---------------------------------------------------------------------------
def test_dynamic_specs_registered_at_import():
    import mcp_gateway.dynamic  # noqa: F401
    from mcp_gateway.jobs import JOB_TOOL_REGISTRY
    for name in ("strace", "ltrace", "qemu_user"):
        assert name in JOB_TOOL_REGISTRY, f"missing dynamic spec: {name}"
        hook = JOB_TOOL_REGISTRY[name].post_terminal_hook
        assert hook is not None, f"hook not bound for: {name}"
        assert callable(hook)
