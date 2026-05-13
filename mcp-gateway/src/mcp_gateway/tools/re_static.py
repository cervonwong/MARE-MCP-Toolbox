"""Phase 7 STATIC-01..09 / D-18, D-19, D-30..D-32: typed static-RE tool wrappers.

Eleven MCP tools layered over Phase 6's `run_tool` chokepoint (`runner.py`) plus
two in-process wrappers (`run_capstone_disasm`, `run_ropper`) that produce the
same 12-key result shape via `_inproc_result` (D-19) so MCP clients see uniform
output.

Tools registered (D-16, D-18):
  Subprocess (9):
    - run_file       (STATIC-01)
    - run_die        (STATIC-02)
    - run_xxd        (STATIC-03)
    - run_readelf    (STATIC-04)
    - run_objdump    (STATIC-05)
    - run_nm         (STATIC-05)
    - run_rabin2     (STATIC-06)
    - run_jq         (STATIC-09)
    - run_yq         (STATIC-09)
  In-process (2):
    - run_capstone_disasm  (STATIC-07; via `capstone` python bindings)
    - run_ropper           (STATIC-08; via `ropper` python bindings)

All wrappers (D-30..D-32):
  - Take `case_dir` as the first positional argument (when applicable);
  - Compose `resolve_case_dir(case_dir)` + `resolve_sample(sample)` + (for path
    args) `confine_to(resolved_case, artifact_path)` for input validation;
  - Validate allowlisted enums (run_readelf sections / run_objdump mode /
    run_nm mode / run_rabin2 command) BEFORE any subprocess spawn;
  - Raise `ValueError` on validation failure;
  - Forward optional `timeout: float | None = None` to `run_tool`;
  - Use slug = public tool name (regex `^[a-z0-9][a-z0-9_-]{0,39}$`).

The eleven tools are defined at module level so unit tests (test_re_static.py) can
import and await them directly without going through the FastMCP tool-manager. The
`register(mcp)` function decorates them with `@mcp.tool()` at gateway startup. This
mirrors the import-then-register pattern used by tools/re_artifacts.py (Plan 07-05).
"""
from __future__ import annotations

import datetime
import json
import secrets
import time
from pathlib import Path
from typing import Any, Literal, Optional

from mcp.server.fastmcp import FastMCP

from ..artifacts_io import confine_to, ensure_subdir
from ..runner import STDOUT_HEAD_KB, run_tool
from .case_dirs import resolve_case_dir
from .samples import resolve_sample

# D-19: in-proc helper produces the same 12-key shape as Phase 6's runner result.
_STDOUT_HEAD_BYTES = STDOUT_HEAD_KB * 1024


def _rand4() -> str:
    """4-char lowercase hex; matches Phase 6 D-09 tool-log-filename convention."""
    return secrets.token_hex(2)


def _utc_ts() -> str:
    """Compact UTC ISO-basic timestamp (matches Phase 6 D-09)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _inproc_result(
    case_dir: Optional[str],
    slug: str,
    output_text: str,
    log_relpath: str,
    started_at: float,
) -> dict:
    """ReToolRunner-compatible 12-key shape for in-process tools (D-19)."""
    return {
        "exit_code": 0,
        "timed_out": False,
        "duration_s": time.monotonic() - started_at,
        "stdout_head": output_text[:_STDOUT_HEAD_BYTES],
        "stdout_truncated": len(output_text) > _STDOUT_HEAD_BYTES,
        "stdout_bytes_total": len(output_text),
        "stderr_head": "",
        "stderr_truncated": False,
        "stderr_bytes_total": 0,
        "log_path": log_relpath,
        "argv": [slug, "(in-process)"],
        "slug": slug,
    }


# ---- Allowlists (D-18, D-32) ----
# run_readelf sections (D-18 row 4 + Claude's-Discretion: + -n notes, -V version)
_READELF_ALLOWED: frozenset[str] = frozenset({
    "-h", "-l", "-d", "-S", "-s", "-r", "-a", "-W", "-n", "-V",
})

# run_objdump mode -> objdump flag (D-18 row 5)
_OBJDUMP_MODE_FLAGS: dict[str, list[str]] = {
    "headers": ["-h"],
    "disasm":  ["-d"],
    "syms":    ["-t"],
    "relocs":  ["-r"],
    "all":     ["-x"],
}

# run_nm mode -> nm flag(s) (D-18 row 6)
_NM_MODE_FLAGS: dict[str, list[str]] = {
    "all":       [],
    "dynamic":   ["-D"],
    "undefined": ["-u"],
    "defined":   ["--defined-only"],
}

# run_rabin2 command allowlist (D-18 row 7)
_RABIN2_ALLOWED: frozenset[str] = frozenset({
    "i", "is", "iI", "ii", "iE", "iz", "zz", "iL",
})

# run_xxd hex_dump cap (D-18 row 3 -- 64 KB)
_XXD_HEX_DUMP_CAP = 64 * 1024


# ---------- STATIC-01: run_file ----------
async def run_file(case_dir: str, sample: str, timeout: Optional[float] = None) -> dict:
    """Identify a sample via libmagic (STATIC-01 / D-18 row 1)."""
    resolved_case = resolve_case_dir(case_dir)
    resolved_sample = resolve_sample(sample)
    argv = ["file", "-b", resolved_sample]
    result = await run_tool(resolved_case, argv, slug="run_file", timeout=timeout)
    first_line = (result["stdout_head"] or "").strip().splitlines()
    result["magic"] = first_line[0] if first_line else ""
    return result


# ---------- STATIC-02: run_die ----------
async def run_die(case_dir: str, sample: str, timeout: Optional[float] = None) -> dict:
    """Detect packers/protectors with DIE; parse `-j` JSON (STATIC-02 / D-18 row 2)."""
    resolved_case = resolve_case_dir(case_dir)
    resolved_sample = resolve_sample(sample)
    argv = ["die", "-j", resolved_sample]
    result = await run_tool(resolved_case, argv, slug="run_die", timeout=timeout)
    detections: list[dict] = []
    if result["stdout_head"]:
        try:
            parsed = json.loads(result["stdout_head"])
            # DIE JSON shape: {"detects":[{"type":"...", "values":[...]}]}
            if isinstance(parsed, dict) and "detects" in parsed:
                detections = parsed["detects"] or []
            elif isinstance(parsed, list):
                detections = parsed
        except json.JSONDecodeError as exc:
            result["json_parse_error"] = str(exc)
    result["detections"] = detections
    return result


# ---------- STATIC-03: run_xxd ----------
async def run_xxd(
    case_dir: str,
    sample: str,
    offset: int = 0,
    length: int = 1024,
    timeout: Optional[float] = None,
) -> dict:
    """Bounded hex window over a sample; full slice saved to hex/ (STATIC-03 / D-18 row 3)."""
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")
    if length <= 0:
        raise ValueError(f"length must be > 0, got {length}")
    resolved_case = resolve_case_dir(case_dir)
    resolved_sample = resolve_sample(sample)
    argv = ["xxd", "-s", str(offset), "-l", str(length), resolved_sample]
    result = await run_tool(resolved_case, argv, slug="run_xxd", timeout=timeout)
    # Cap returned hex_dump at 64 KB (D-18 row 3).
    hex_dump = (result["stdout_head"] or "")[:_XXD_HEX_DUMP_CAP]
    # Write full slice to hex/xxd-<ts>-<rand4>.txt for client retrieval.
    hex_dir = ensure_subdir(resolved_case, "hex")
    hex_file = hex_dir / f"xxd-{_utc_ts()}-{_rand4()}.txt"
    hex_file.write_text(result["stdout_head"] or "", encoding="utf-8", errors="replace")
    result["hex_dump"] = hex_dump
    result["hex_path"] = str(hex_file.relative_to(Path(resolved_case)))
    return result


# ---------- STATIC-04: run_readelf ----------
async def run_readelf(
    case_dir: str,
    sample: str,
    sections: list[str],
    timeout: Optional[float] = None,
) -> dict:
    """Inspect ELF metadata; sections is an allowlisted list of flags (STATIC-04 / D-18 row 4)."""
    if not isinstance(sections, list) or not sections:
        raise ValueError("sections must be a non-empty list of allowlisted flags")
    bad = [s for s in sections if s not in _READELF_ALLOWED]
    if bad:
        raise ValueError(
            f"sections must be a subset of {sorted(_READELF_ALLOWED)}, "
            f"got disallowed {bad}"
        )
    resolved_case = resolve_case_dir(case_dir)
    resolved_sample = resolve_sample(sample)
    argv = ["readelf", *sections, resolved_sample]
    result = await run_tool(resolved_case, argv, slug="run_readelf", timeout=timeout)
    result["output"] = result["stdout_head"]
    return result


# ---------- STATIC-05: run_objdump ----------
async def run_objdump(
    case_dir: str,
    sample: str,
    mode: Literal["headers", "disasm", "syms", "relocs", "all"],
    timeout: Optional[float] = None,
) -> dict:
    """objdump in one of five mapped modes (STATIC-05 / D-18 row 5)."""
    if mode not in _OBJDUMP_MODE_FLAGS:
        raise ValueError(
            f"mode must be one of {sorted(_OBJDUMP_MODE_FLAGS.keys())}, got {mode!r}"
        )
    resolved_case = resolve_case_dir(case_dir)
    resolved_sample = resolve_sample(sample)
    argv = ["objdump", *_OBJDUMP_MODE_FLAGS[mode], resolved_sample]
    result = await run_tool(resolved_case, argv, slug="run_objdump", timeout=timeout)
    result["output"] = result["stdout_head"]
    return result


# ---------- STATIC-05 (nm): run_nm ----------
async def run_nm(
    case_dir: str,
    sample: str,
    mode: Literal["all", "dynamic", "undefined", "defined"],
    timeout: Optional[float] = None,
) -> dict:
    """nm in one of four modes; parses symbol list when mode != 'all' (STATIC-05 / D-18 row 6)."""
    if mode not in _NM_MODE_FLAGS:
        raise ValueError(f"mode must be one of {sorted(_NM_MODE_FLAGS.keys())}, got {mode!r}")
    resolved_case = resolve_case_dir(case_dir)
    resolved_sample = resolve_sample(sample)
    argv = ["nm", *_NM_MODE_FLAGS[mode], resolved_sample]
    result = await run_tool(resolved_case, argv, slug="run_nm", timeout=timeout)
    if mode == "all":
        result["output"] = result["stdout_head"]
    else:
        # Each nm line: <address?>  <type>  <name>
        symbols: list[dict] = []
        for line in (result["stdout_head"] or "").splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) == 3:
                addr, sym_type, name = parts
                symbols.append({"address": addr, "type": sym_type, "name": name})
            elif len(parts) == 2:
                sym_type, name = parts
                symbols.append({"address": None, "type": sym_type, "name": name})
        result["symbols"] = symbols
    return result


# ---------- STATIC-06: run_rabin2 ----------
async def run_rabin2(
    case_dir: str,
    sample: str,
    command: Literal["i", "is", "iI", "ii", "iE", "iz", "zz", "iL"],
    timeout: Optional[float] = None,
) -> dict:
    """rabin2 -j <command> <sample>; parses JSON when exit==0 (STATIC-06 / D-18 row 7)."""
    if command not in _RABIN2_ALLOWED:
        raise ValueError(
            f"command must be one of {sorted(_RABIN2_ALLOWED)}, got {command!r}"
        )
    resolved_case = resolve_case_dir(case_dir)
    resolved_sample = resolve_sample(sample)
    argv = ["rabin2", "-j", command, resolved_sample]
    result = await run_tool(resolved_case, argv, slug="run_rabin2", timeout=timeout)
    if result["exit_code"] == 0 and result["stdout_head"]:
        try:
            result["json_output"] = json.loads(result["stdout_head"])
        except json.JSONDecodeError as exc:
            result["json_output"] = None
            result["json_parse_error"] = str(exc)
    else:
        result["json_output"] = None
    return result


# ---------- STATIC-07: run_capstone_disasm (in-process) ----------
async def run_capstone_disasm(
    arch: str,
    mode: str,
    bytes_hex: str,
    base_addr: int = 0,
    case_dir: Optional[str] = None,
    timeout: Optional[float] = None,  # accepted for uniformity (D-30); ignored in-proc
) -> dict:
    """Disassemble a byte range with capstone (STATIC-07 / D-18 row 8, D-19 in-proc shape)."""
    try:
        import capstone  # type: ignore
    except ImportError as exc:  # pragma: no cover - dep pinned in pyproject.toml
        raise RuntimeError(
            f"capstone import failed: {exc}. Phase 7 D-20 pins capstone>=5.0.0 "
            "in pyproject.toml; check that pip install succeeded in the image."
        ) from exc

    # Map agent strings to capstone constants. Raise ValueError on unknown values.
    arch_map: dict[str, int] = {
        "x86": capstone.CS_ARCH_X86,
        "arm": capstone.CS_ARCH_ARM,
        "arm64": capstone.CS_ARCH_ARM64,
        "aarch64": capstone.CS_ARCH_ARM64,
        "mips": capstone.CS_ARCH_MIPS,
        "ppc": capstone.CS_ARCH_PPC,
        "sparc": capstone.CS_ARCH_SPARC,
    }
    mode_map: dict[str, int] = {
        "16": capstone.CS_MODE_16,
        "32": capstone.CS_MODE_32,
        "64": capstone.CS_MODE_64,
        "arm": capstone.CS_MODE_ARM,
        "thumb": capstone.CS_MODE_THUMB,
        "mips32": capstone.CS_MODE_MIPS32,
        "mips64": capstone.CS_MODE_MIPS64,
        "big": capstone.CS_MODE_BIG_ENDIAN,
        "little": capstone.CS_MODE_LITTLE_ENDIAN,
    }
    if arch not in arch_map:
        raise ValueError(f"arch must be one of {sorted(arch_map.keys())}, got {arch!r}")
    if mode not in mode_map:
        raise ValueError(f"mode must be one of {sorted(mode_map.keys())}, got {mode!r}")
    try:
        data = bytes.fromhex(bytes_hex.replace(" ", ""))
    except ValueError as exc:
        raise ValueError(f"bytes_hex must be valid hex: {exc}") from exc

    started_at = time.monotonic()
    md = capstone.Cs(arch_map[arch], mode_map[mode])
    instructions: list[dict] = []
    text_lines: list[str] = []
    for insn in md.disasm(data, base_addr):
        entry = {
            "address": insn.address,
            "mnemonic": insn.mnemonic,
            "op_str": insn.op_str,
            "bytes": insn.bytes.hex(),
        }
        instructions.append(entry)
        text_lines.append(f"0x{insn.address:x}\t{insn.mnemonic}\t{insn.op_str}")

    output_text = "\n".join(text_lines)
    # Optional artifact dump per D-19: only when case_dir provided.
    log_relpath = "(in-process; no case_dir)"
    if case_dir is not None:
        resolved_case = resolve_case_dir(case_dir)
        disasm_dir = ensure_subdir(resolved_case, "disassembly")
        log_file = disasm_dir / f"capstone-{_utc_ts()}-{_rand4()}.json"
        log_file.write_text(json.dumps(instructions, indent=2), encoding="utf-8")
        log_relpath = str(log_file.relative_to(Path(resolved_case)))

    result = _inproc_result(case_dir, "run_capstone_disasm", output_text, log_relpath, started_at)
    result["instructions"] = instructions
    return result


# ---------- STATIC-08: run_ropper (in-process) ----------
async def run_ropper(
    case_dir: str,
    sample: str,
    arch: str,
    filter: Optional[str] = None,
    badbytes: Optional[str] = None,
    max_gadgets: int = 1024,
    timeout: Optional[float] = None,  # accepted for uniformity (D-30); ignored in-proc
) -> dict:
    """Search ROP gadgets via ropper Python API (STATIC-08 / D-18 row 9, D-19 in-proc shape)."""
    if max_gadgets <= 0:
        raise ValueError(f"max_gadgets must be > 0, got {max_gadgets}")
    try:
        from ropper import RopperService  # type: ignore
    except ImportError as exc:  # pragma: no cover - dep pinned in pyproject.toml
        raise RuntimeError(
            f"ropper import failed: {exc}. Phase 7 D-20 pins ropper>=1.13.10 in pyproject.toml."
        ) from exc

    resolved_case = resolve_case_dir(case_dir)
    resolved_sample = resolve_sample(sample)
    started_at = time.monotonic()

    options = {"detailed": False, "color": False, "all": False, "inst_count": 6}
    if badbytes:
        options["badbytes"] = badbytes
    svc = RopperService(options=options)
    svc.addFile(resolved_sample)
    svc.loadGadgetsFor(name=resolved_sample)
    if filter:
        try:
            svc.applyFilter(name=resolved_sample, filter=filter)
        except Exception:  # ropper filter compile errors are AttributeError/ValueError
            pass
    file_obj = svc.getFileFor(name=resolved_sample)
    all_gadgets = (file_obj.gadgets if file_obj is not None else None) or []

    def _gadget_to_dict(g: Any) -> dict:
        try:
            instr_text = " ; ".join(
                line[2] if isinstance(line, tuple) and len(line) >= 3 else str(line)
                for line in getattr(g, "lines", []) or []
            )
        except Exception:
            instr_text = str(g)
        raw_bytes = getattr(g, "bytes", b"")
        return {
            "address": getattr(g, "address", None),
            "instructions": instr_text,
            "bytes": raw_bytes.hex() if isinstance(raw_bytes, (bytes, bytearray)) else "",
        }

    truncated_gadgets = [_gadget_to_dict(g) for g in all_gadgets[:max_gadgets]]

    # Always write full gadget list to rop/ (D-19 rationale: "Full gadget list JSON-dumped").
    rop_dir = ensure_subdir(resolved_case, "rop")
    rop_file = rop_dir / f"ropper-{_utc_ts()}-{_rand4()}.json"
    full_dump = [_gadget_to_dict(g) for g in all_gadgets]
    rop_file.write_text(json.dumps(full_dump, indent=2, default=str), encoding="utf-8")
    log_relpath = str(rop_file.relative_to(Path(resolved_case)))

    output_text = (
        f"ropper(arch={arch}) found {len(all_gadgets)} gadgets; "
        f"returning {len(truncated_gadgets)}"
    )
    result = _inproc_result(case_dir, "run_ropper", output_text, log_relpath, started_at)
    result["gadgets"] = truncated_gadgets
    result["gadget_count_total"] = len(all_gadgets)
    return result


# ---------- STATIC-09: run_jq ----------
async def run_jq(
    case_dir: str,
    artifact_path: str,
    expr: str,
    timeout: Optional[float] = None,
) -> dict:
    """Run jq over a case artifact (STATIC-09 / D-18 row 10)."""
    if not isinstance(expr, str) or not expr:
        raise ValueError("expr must be a non-empty string")
    resolved_case = Path(resolve_case_dir(case_dir))
    target = confine_to(resolved_case, artifact_path)
    argv = ["jq", expr, str(target)]
    result = await run_tool(str(resolved_case), argv, slug="run_jq", timeout=timeout)
    result["result"] = result["stdout_head"]
    return result


# ---------- STATIC-09 (yq): run_yq ----------
async def run_yq(
    case_dir: str,
    artifact_path: str,
    expr: str,
    timeout: Optional[float] = None,
) -> dict:
    """Run yq over a case artifact (STATIC-09 / D-18 row 11)."""
    if not isinstance(expr, str) or not expr:
        raise ValueError("expr must be a non-empty string")
    resolved_case = Path(resolve_case_dir(case_dir))
    target = confine_to(resolved_case, artifact_path)
    argv = ["yq", expr, str(target)]
    result = await run_tool(str(resolved_case), argv, slug="run_yq", timeout=timeout)
    result["result"] = result["stdout_head"]
    return result


def register(mcp: FastMCP) -> None:
    """Register the 11 typed static-RE wrappers on the FastMCP instance.

    Tools are defined at module level (for direct test import) and re-registered
    here as `@mcp.tool()` so the gateway surfaces them to MCP clients. The decorator
    is a no-op pass-through on the underlying coroutine -- production semantics are
    identical to direct function calls.
    """
    mcp.tool()(run_file)
    mcp.tool()(run_die)
    mcp.tool()(run_xxd)
    mcp.tool()(run_readelf)
    mcp.tool()(run_objdump)
    mcp.tool()(run_nm)
    mcp.tool()(run_rabin2)
    mcp.tool()(run_capstone_disasm)
    mcp.tool()(run_ropper)
    mcp.tool()(run_jq)
    mcp.tool()(run_yq)
