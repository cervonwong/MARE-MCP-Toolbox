"""Phase 7 ARTIF-02..04 + D-21..D-25.

Wave-0 RED stubs. Imports mcp_gateway.tools.re_artifacts which does NOT yet exist;
ImportError on execution. Wave-2 implementation flips RED -> GREEN.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest


# ---- ARTIF-02 (write text) ----
async def test_write_artifact_text(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_artifacts import write_artifact
    case = tmp_status_dir / "200-write-text"
    case.mkdir()
    result = await write_artifact(str(case), "hello.txt", "Hello, MARE!")
    assert result["bytes_written"] == len("Hello, MARE!".encode("utf-8"))
    assert (case / "hello.txt").read_text(encoding="utf-8") == "Hello, MARE!"


# ---- ARTIF-02 (write binary base64) ----
async def test_write_artifact_binary(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_artifacts import write_artifact
    case = tmp_status_dir / "201-write-bin"
    case.mkdir()
    payload = base64.b64encode(b"\x00\xffMARE").decode("ascii")
    result = await write_artifact(str(case), "blob.bin", payload, mode="binary")
    assert result["bytes_written"] == 6
    assert (case / "blob.bin").read_bytes() == b"\x00\xffMARE"


# ---- ARTIF-02 (overwrite=False raises) ----
async def test_write_artifact_overwrite_false(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_artifacts import write_artifact
    case = tmp_status_dir / "202-overwrite"
    case.mkdir()
    await write_artifact(str(case), "a.txt", "v1")
    with pytest.raises(FileExistsError):
        await write_artifact(str(case), "a.txt", "v2")


# ---- ARTIF-02 (overwrite=True replaces) ----
async def test_write_artifact_overwrite_true(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_artifacts import write_artifact
    case = tmp_status_dir / "203-overwrite-yes"
    case.mkdir()
    await write_artifact(str(case), "a.txt", "v1")
    result = await write_artifact(str(case), "a.txt", "v2", overwrite=True)
    assert result["overwrote"] is True
    assert (case / "a.txt").read_text(encoding="utf-8") == "v2"


# ---- ARTIF-02 (confine_to traversal rejection) ----
async def test_write_artifact_rejects_traversal(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_artifacts import write_artifact
    case = tmp_status_dir / "204-traversal"
    case.mkdir()
    with pytest.raises(ValueError):
        await write_artifact(str(case), "../escape.txt", "x")


# ---- ARTIF-02 (append) ----
async def test_append_artifact(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_artifacts import append_artifact
    case = tmp_status_dir / "205-append"
    case.mkdir()
    await append_artifact(str(case), "log.txt", "line1\n")
    await append_artifact(str(case), "log.txt", "line2\n")
    assert (case / "log.txt").read_text(encoding="utf-8") == "line1\nline2\n"


# ---- ARTIF-02 (ACL backfill via write) ----
async def test_write_artifact_grants_mare_shell(tmp_status_dir) -> None:
    """D-21 mandates write_artifact -> ensure_mare_shell_access. Verify ACL applied."""
    from mcp_gateway.tools.re_artifacts import write_artifact
    case = tmp_status_dir / "206-acl-backfill"
    case.mkdir()
    await write_artifact(str(case), "a.txt", "x")
    # The ACL set by ensure_mare_shell_access must be visible to getfacl
    import subprocess
    res = subprocess.run(["getfacl", "-c", str(case)], capture_output=True, text=True)
    assert res.returncode == 0
    assert "user:agent:rwx" in res.stdout or "user:" in res.stdout
    assert "group:mare-shell:rwx" in res.stdout


# ---- ARTIF-03 (list_artifacts flat) ----
async def test_list_artifacts_flat(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_artifacts import list_artifacts
    case = tmp_status_dir / "210-listflat"
    case.mkdir()
    (case / "a.txt").write_text("a")
    (case / "b.txt").write_text("bb")
    result = await list_artifacts(str(case))
    names = {f["name"] for f in result["files"]}
    assert {"a.txt", "b.txt"} <= names


# ---- ARTIF-03 (list_artifacts subdir) ----
async def test_list_artifacts_subdir(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_artifacts import list_artifacts
    case = tmp_status_dir / "211-listsub"
    case.mkdir()
    (case / "tool-logs").mkdir()
    (case / "tool-logs" / "log1.txt").write_text("log")
    result = await list_artifacts(str(case), subdir="tool-logs")
    assert {"log1.txt"} <= {f["name"] for f in result["files"]}


# ---- ARTIF-03 (subdir allowlist) ----
async def test_list_artifacts_rejects_bad_subdir(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_artifacts import list_artifacts
    case = tmp_status_dir / "212-badsub"
    case.mkdir()
    with pytest.raises(ValueError):
        await list_artifacts(str(case), subdir="../etc")
    with pytest.raises(ValueError):
        await list_artifacts(str(case), subdir="not-in-expanded-subdirs")


# ---- ARTIF-03 (tree happy) ----
async def test_get_artifact_tree(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_artifacts import get_artifact_tree
    case = tmp_status_dir / "220-tree"
    case.mkdir()
    (case / "a.txt").write_text("a")
    (case / "sub").mkdir()
    (case / "sub" / "b.txt").write_text("b")
    result = await get_artifact_tree(str(case))
    assert "tree" in result
    assert result["tree"]["type"] == "dir"
    assert "children" in result["tree"]
    assert result["file_count"] >= 2


# ---- ARTIF-03 (tree max_files cap) ----
async def test_get_artifact_tree_max_files(tmp_status_dir, monkeypatch) -> None:
    from mcp_gateway.tools.re_artifacts import get_artifact_tree
    case = tmp_status_dir / "221-treecap"
    case.mkdir()
    monkeypatch.setenv("MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES", "3")
    for i in range(10):
        (case / f"f{i}.txt").write_text("x")
    # Need to reimport to pick up env change OR module reads per-call (D-24 default behaviour).
    result = await get_artifact_tree(str(case))
    assert result["truncated"] is True
    assert result["truncation_reason"] == "max_files"


# ---- ARTIF-04 (paged read) ----
async def test_get_tool_log_paged(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_artifacts import get_tool_log
    case = tmp_status_dir / "230-paged"
    case.mkdir()
    (case / "tool-logs").mkdir()
    log = case / "tool-logs" / "demo.txt"
    log.write_bytes(b"A" * 1024)
    res1 = await get_tool_log(str(case), "demo.txt", offset=0, length=256)
    assert res1["length_returned"] == 256
    assert res1["next_offset"] == 256
    assert res1["eof"] is False
    res2 = await get_tool_log(str(case), "demo.txt", offset=res1["next_offset"], length=2048)
    assert res2["eof"] is True


# ---- ARTIF-04 (eof on read past end) ----
async def test_get_tool_log_eof(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_artifacts import get_tool_log
    case = tmp_status_dir / "231-eof"
    case.mkdir()
    (case / "tool-logs").mkdir()
    (case / "tool-logs" / "tiny.txt").write_bytes(b"abc")
    result = await get_tool_log(str(case), "tiny.txt", offset=100, length=10)
    assert result["eof"] is True
    assert result["length_returned"] == 0


# ---- ARTIF-04 (length clamp) ----
async def test_get_tool_log_length_cap(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_artifacts import get_tool_log
    case = tmp_status_dir / "232-cap"
    case.mkdir()
    (case / "tool-logs").mkdir()
    (case / "tool-logs" / "big.txt").write_bytes(b"A" * (10 * 1024 * 1024))
    # Request 10 MB; D-25 clamps at MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB * 4 = 256*4 = 1024 KB = 1 MB default
    result = await get_tool_log(str(case), "big.txt", offset=0, length=10 * 1024 * 1024)
    assert result["length_returned"] <= 1024 * 1024 + 4  # allow a few-byte UTF-8 boundary slop
