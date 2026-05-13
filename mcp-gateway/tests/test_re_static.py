"""Phase 7 STATIC-01..09 + D-18, D-19, D-32.

Wave-0 RED stubs. Imports mcp_gateway.tools.re_static which does NOT yet exist;
ImportError on execution. Wave-2 implementation flips RED -> GREEN.

Fixtures under mcp-gateway/tests/fixtures/ are committed by Wave-0 Task 2.
"""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _ensure_status_case(tmp_status_dir, name: str) -> Path:
    case = tmp_status_dir / name
    case.mkdir()
    return case


# ---- STATIC-01: run_file returns magic ----
async def test_run_file_elf(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_file
    case = _ensure_status_case(tmp_status_dir, "100-runfile")
    result = await run_file(str(case), str(FIXTURES / "hello_elf"))
    assert result["exit_code"] == 0
    assert "ELF" in result.get("magic", "")


# ---- STATIC-02: run_die returns detections list ----
async def test_run_die_pe(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_die
    case = _ensure_status_case(tmp_status_dir, "101-rundie")
    result = await run_die(str(case), str(FIXTURES / "hello_pe.exe"))
    # die may exit non-zero on minimal hand-crafted PE; structural assertion is the 'detections' key.
    assert "detections" in result
    assert isinstance(result["detections"], list)


# ---- STATIC-03: run_xxd bounded, hex_path under hex/ ----
async def test_run_xxd_bounded(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_xxd
    case = _ensure_status_case(tmp_status_dir, "102-runxxd")
    result = await run_xxd(str(case), str(FIXTURES / "hello_elf"), offset=0, length=64)
    assert result["exit_code"] == 0
    assert "hex_dump" in result
    assert len(result["hex_dump"]) <= 64 * 1024  # 64 KB cap
    hex_path = case / result["hex_path"]
    assert hex_path.parent.name == "hex"
    assert hex_path.is_file()


# ---- STATIC-04 (allowlist): run_readelf rejects disallowed flag ----
async def test_run_readelf_rejects_disallowed_flag(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_readelf
    case = _ensure_status_case(tmp_status_dir, "103-readelf-bad")
    with pytest.raises(ValueError):
        await run_readelf(str(case), str(FIXTURES / "hello_elf"), sections=["-Z"])


# ---- STATIC-04: run_readelf header happy ----
async def test_run_readelf_header(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_readelf
    case = _ensure_status_case(tmp_status_dir, "104-readelf-header")
    result = await run_readelf(str(case), str(FIXTURES / "hello_elf"), sections=["-h"])
    assert result["exit_code"] == 0
    assert "ELF Header" in result.get("output", "") or "ELF Header" in result["stdout_head"]


# ---- STATIC-05 (objdump headers) ----
async def test_run_objdump_headers(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_objdump
    case = _ensure_status_case(tmp_status_dir, "105-objdump")
    result = await run_objdump(str(case), str(FIXTURES / "hello_elf"), mode="headers")
    assert result["exit_code"] == 0
    assert "section" in result.get("output", "").lower() or "section" in result["stdout_head"].lower()


# ---- STATIC-05 (objdump mode allowlist) ----
async def test_run_objdump_rejects_invalid_mode(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_objdump
    case = _ensure_status_case(tmp_status_dir, "106-objdump-bad")
    with pytest.raises(ValueError):
        await run_objdump(str(case), str(FIXTURES / "hello_elf"), mode="nonsense")


# ---- STATIC-05 (nm all mode) ----
async def test_run_nm_all(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_nm
    case = _ensure_status_case(tmp_status_dir, "107-nm")
    result = await run_nm(str(case), str(FIXTURES / "hello_elf"), mode="all")
    assert result["exit_code"] == 0
    # mode="all" -> raw output, no symbol parsing
    assert "output" in result or "stdout_head" in result


# ---- STATIC-06 (rabin2 allowlist) ----
async def test_run_rabin2_rejects_invalid_command(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_rabin2
    case = _ensure_status_case(tmp_status_dir, "108-rabin2-bad")
    with pytest.raises(ValueError):
        await run_rabin2(str(case), str(FIXTURES / "hello_elf"), command="zzz")


# ---- STATIC-06 (rabin2 info happy) ----
async def test_run_rabin2_info(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_rabin2
    case = _ensure_status_case(tmp_status_dir, "109-rabin2-info")
    result = await run_rabin2(str(case), str(FIXTURES / "hello_elf"), command="i")
    # rabin2 may print warnings on stderr but exit 0
    assert "json_output" in result or "stdout_head" in result


# ---- STATIC-07 (capstone in-process disasm) ----
async def test_run_capstone_disasm_x86_64(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_capstone_disasm
    # In-process; no subprocess; case_dir optional.
    result = await run_capstone_disasm(arch="x86", mode="64", bytes_hex="90c3", base_addr=0x1000)
    assert result["exit_code"] == 0
    assert result["timed_out"] is False
    insns = result["instructions"]
    assert len(insns) == 2
    assert insns[0]["mnemonic"] == "nop"
    assert insns[1]["mnemonic"] == "ret"
    # 12-key shape preserved
    for k in (
        "exit_code", "timed_out", "duration_s",
        "stdout_head", "stdout_truncated", "stdout_bytes_total",
        "stderr_head", "stderr_truncated", "stderr_bytes_total",
        "log_path", "argv", "slug",
    ):
        assert k in result, f"D-19 12-key shape missing {k!r}"


# ---- STATIC-08 (ropper in-process gadgets) ----
async def test_run_ropper_x86_64(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_ropper
    case = _ensure_status_case(tmp_status_dir, "110-ropper")
    result = await run_ropper(str(case), str(FIXTURES / "hello_elf"), arch="x86_64", max_gadgets=10)
    assert result["exit_code"] == 0
    assert "gadgets" in result
    assert isinstance(result["gadgets"], list)
    assert len(result["gadgets"]) <= 10


# ---- STATIC-09 (jq) ----
async def test_run_jq_artifact(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_jq
    case = _ensure_status_case(tmp_status_dir, "111-runjq")
    # Drop a JSON file in the case dir
    (case / "test.json").write_text('{"hello":"mare"}\n', encoding="utf-8")
    result = await run_jq(str(case), "test.json", ".hello")
    assert result["exit_code"] == 0
    assert "mare" in result.get("result", result["stdout_head"])


# ---- STATIC-09 (yq) ----
async def test_run_yq_artifact(tmp_status_dir) -> None:
    from mcp_gateway.tools.re_static import run_yq
    case = _ensure_status_case(tmp_status_dir, "112-runyq")
    (case / "test.yaml").write_text("hello: mare\n", encoding="utf-8")
    result = await run_yq(str(case), "test.yaml", ".hello")
    assert result["exit_code"] == 0
    assert "mare" in result.get("result", result["stdout_head"])
