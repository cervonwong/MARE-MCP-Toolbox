"""Phase 12 (D-11..D-14): SKILL.md + W-N dual-mode regression tests.

Wave 0 RED-stub: all tests except test_skill_md_frontmatter_intact and
test_no_abbreviated_prefix should FAIL until Plans 02 (W-N files),
03 (scripts + artifact-spec), and 04 (SKILL.md rewrite) land.

Refresh the SKILL.md sha256 baseline with:
    UPDATE_SKILL_SNAPSHOT=1 pytest mcp-gateway/tests/test_skill_md_dual_mode.py::test_skill_md_snapshot
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

try:
    import yaml  # PyYAML may be present on host; venv lacks it -- fallback path below
except ImportError:  # pragma: no cover
    yaml = None

# Pitfall 4 mitigation: locate REPO_ROOT by .planning marker, not parents[2].
# Container guard: when no parent contains `.planning` (e.g. inside the Docker
# image at /opt/mcp-gateway), skip this whole module — the tests validate the
# orchestrator skill markdown under .planning/ + workspace/skills/ which the
# container does not ship. Resolves deferred-items.md "test_skill_md_dual_mode.py
# StopIteration in-container" entry.
_repo_root_candidates = [p for p in Path(__file__).resolve().parents if (p / ".planning").is_dir()]
if not _repo_root_candidates:
    import pytest as _pytest
    _pytest.skip("no parent dir contains .planning (host-only test; container does not ship workspace/skills)", allow_module_level=True)
REPO_ROOT = _repo_root_candidates[0]
SKILL_DIR = REPO_ROOT / "workspace/.claude/skills/malware-analysis-orchestrator"
CODEX_SKILL_DIR = REPO_ROOT / "workspace/.codex/skills/malware-analysis-orchestrator"
SKILL_MD = SKILL_DIR / "SKILL.md"
WORKFLOWS_DIR = SKILL_DIR / "references/workflows"
WORKFLOW_FILES = sorted(WORKFLOWS_DIR.glob("W-*.md")) if WORKFLOWS_DIR.is_dir() else []
REF_FILES = [
    SKILL_DIR / "references/workflow.md",
    SKILL_DIR / "references/deep-re-workflows.md",
]
ALL_SKILL_FILES = [SKILL_MD, *WORKFLOW_FILES, *[p for p in REF_FILES if p.is_file()]]
SNAPSHOT_FILE = REPO_ROOT / "mcp-gateway/tests/snapshots/SKILL.md.sha256"

GATEWAY_TOOL_RE = re.compile(r"mcp__mare[-_]\w+__\w+")
FALLBACK_RE = re.compile(r"scripts/|\bfallback\b|\belse\b", re.IGNORECASE)
ABBREVIATED_RE = re.compile(r"mcp__mare__(?!toolbox)")  # Pitfall 3

# Per-W-N v1.1 wrapper allow-list (D-05 mapping)
WN_WRAPPER_PATTERNS = {
    "W-1": r"run_die|run_upx_test|run_upx_unpack",
    "W-2": r"run_rabin2|run_readelf|run_nm|open_r2_session",
    "W-3": r"run_rabin2|run_xxd|run_capstone_disasm",
    "W-4": r"run_rabin2|run_ropper",
    "W-5": r"start_tool_job|run_strace|run_ltrace",
    "W-6": r"run_binwalk|run_unblob|list_extracted_files|promote_extracted_sample",
    "W-7": r"run_rabin2|run_qemu_user",
}

CODEX_V1_1_RELATIVE_PATHS = [
    "references/deep-re-workflows.md",
    "references/workflows/W-1-packed-binary-triage.md",
    "references/workflows/W-2-elf-deep-dive.md",
    "references/workflows/W-3-pe-deep-dive.md",
    "references/workflows/W-4-rop-gadget-hunt.md",
    "references/workflows/W-5-dynamic-api-trace.md",
    "references/workflows/W-6-firmware-unpack.md",
    "references/workflows/W-7-cross-arch-iot.md",
    "scripts/probe_dynamic_tools.sh",
]


def check_dual_mode(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_no, snippet) for gateway-tool refs without fallback."""
    if not path.is_file():
        return [(0, f"<file missing: {path}>")]
    lines = path.read_text(encoding="utf-8").splitlines()
    offenses: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if not GATEWAY_TOOL_RE.search(line):
            continue
        lo = max(0, i - 3)
        hi = min(len(lines), i + 4)
        window = "\n".join(lines[lo:hi])
        if not FALLBACK_RE.search(window):
            offenses.append((i + 1, line.strip()))
    return offenses


# ---- SKILL-01: backend priority ---------------------------------------


def test_skill_md_frontmatter_intact():
    """Validate top-doc YAML frontmatter has correct `name` + non-empty `description`.

    Parse path: prefer `yaml.safe_load_all` when PyYAML is importable. When it
    is NOT (e.g., the mcp-gateway venv on this executor host does not pin
    PyYAML as a dep, and CONTEXT.md `<domain>` puts adding it out of scope for
    this phase), fall back to a regex-based frontmatter extraction with
    line-grep on the `name:` and `description:` keys. Both parse paths assert
    the same T-12 frontmatter invariant.
    """
    assert SKILL_MD.is_file(), f"missing SKILL.md at {SKILL_MD}"
    text = SKILL_MD.read_text(encoding="utf-8")
    if yaml is not None:
        with SKILL_MD.open("r", encoding="utf-8") as fh:
            docs = list(yaml.safe_load_all(fh))
        assert docs and isinstance(docs[0], dict), "no YAML frontmatter parsed"
        assert docs[0].get("name") == "malware-analysis-orchestrator"
        assert docs[0].get("description"), "description must be non-empty"
        return
    # Manual fallback: extract leading `---\n...\n---` block, line-grep keys.
    m = re.match(r"---\n(.*?)\n---", text, re.DOTALL)
    assert m, "no YAML frontmatter block (---...---) found at file head"
    block = m.group(1)
    name_m = re.search(r"^name:\s*(\S.*)$", block, re.MULTILINE)
    desc_m = re.search(r"^description:\s*(\S.*)$", block, re.MULTILINE)
    assert name_m, "no `name:` line in frontmatter"
    assert name_m.group(1).strip().strip("\"'") == "malware-analysis-orchestrator"
    assert desc_m and desc_m.group(1).strip(), "description must be non-empty"


def test_backend_priority_correct():
    text = SKILL_MD.read_text(encoding="utf-8")
    # Substring with whitespace tolerance: IDA appears before BN, BN before Ghidra
    m = re.search(r"IDA[^\n]*?Binary Ninja[^\n]*?Ghidra", text, re.IGNORECASE)
    assert m, "expected `IDA ... Binary Ninja ... Ghidra` ordering in SKILL.md"


def test_no_legacy_bn_first_priority():
    """Assert the legacy `Binary Ninja MCP server ... primary tool` phrasing is gone.

    NOTE: the SKILL.md v1.0 line uses markdown bold (`**Binary Ninja MCP server**
    -- primary tool ...`), so the literal substring from the plan's <behavior>
    block (`Binary Ninja MCP server -- primary tool`) does NOT match. Use a
    regex tolerant of optional `**` (markdown emphasis) between the server name
    and the `-- primary tool` phrase. This matches the v1.0 line at SKILL.md:141
    so the test is RED on the baseline, and turns GREEN once Plan 04 rewrites
    the backend-priority section to put IDA first.
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    pattern = re.compile(r"Binary Ninja MCP server\*{0,2}\s*--\s*primary tool")
    m = pattern.search(text)
    assert m is None, (
        f"legacy BN-first phrasing still present in SKILL.md "
        f"(matched: {m.group(0)!r} at offset {m.start()})"
    )


# ---- Codex copy synchronization ---------------------------------------


@pytest.mark.parametrize("relpath", CODEX_V1_1_RELATIVE_PATHS)
def test_codex_skill_has_v1_1_artifacts(relpath: str):
    """Project instruction: shared Claude/Codex skill copies stay synchronized."""
    assert (CODEX_SKILL_DIR / relpath).is_file(), f"Codex skill missing {relpath}"


def test_codex_skill_backend_priority_matches_v1_1():
    """Codex SKILL.md must not keep stale BN-first v1.0 backend guidance."""
    text = (CODEX_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "IDA Pro MCP > Binary Ninja MCP > Ghidra MCP > r2" in text
    assert "Binary Ninja MCP server** -- primary" not in text


def test_codex_artifact_spec_has_dynamic_schema():
    """Codex artifact spec must include Phase 12 dynamic-mode state fields."""
    text = (CODEX_SKILL_DIR / "references/artifact-spec.md").read_text(encoding="utf-8")
    for token in (
        '"mode"',
        "dynamic_mode_enabled",
        "dynamic_capabilities",
        "Accept: application/json, text/event-stream",
    ):
        assert token in text


def test_codex_dynamic_scripts_match_phase12_surface():
    """Codex scripts must carry the dynamic capability probe/update surface."""
    init_text = (CODEX_SKILL_DIR / "scripts/init_status_tree.sh").read_text(encoding="utf-8")
    state_text = (CODEX_SKILL_DIR / "scripts/update_state.py").read_text(encoding="utf-8")
    assert "populate_dynamic_caps" in init_text
    assert "Accept: application/json, text/event-stream" in init_text
    assert "--probe-dynamic" in state_text
    assert "dynamic_capabilities" in state_text


# ---- SKILL-02: W-N files + index --------------------------------------


def test_workflow_count_locked():
    files = sorted(WORKFLOWS_DIR.glob("W-*.md")) if WORKFLOWS_DIR.is_dir() else []
    assert len(files) == 7, (
        f"expected 7 W-N workflow files (W-1..W-7), found {len(files)}: "
        f"{[p.name for p in files]}"
    )


def test_workflow_index_present():
    idx = SKILL_DIR / "references/deep-re-workflows.md"
    assert idx.is_file(), f"missing index at {idx}"
    text = idx.read_text(encoding="utf-8")
    for n in range(1, 8):
        assert re.search(rf"W-{n}\b", text), f"index does not reference W-{n}"


@pytest.mark.parametrize(
    "wn_path",
    WORKFLOW_FILES or [None],
    ids=lambda p: p.name if p is not None and hasattr(p, "name") else "missing",
)
def test_wn_files_reference_v1_1_wrappers(wn_path):
    if not WORKFLOW_FILES or wn_path is None:
        pytest.fail("no W-N files exist yet (Wave 0 RED state)")
    m = re.match(r"W-(\d+)", wn_path.name)
    assert m, f"unexpected W-N filename: {wn_path.name}"
    key = f"W-{m.group(1)}"
    pattern = WN_WRAPPER_PATTERNS.get(key)
    assert pattern, f"no wrapper pattern for {key}"
    text = wn_path.read_text(encoding="utf-8")
    assert re.search(pattern, text), (
        f"{wn_path.name}: no v1.1 wrapper from /{pattern}/ found"
    )


# ---- SKILL-03: dual-mode invariant ------------------------------------


@pytest.mark.parametrize("doc", ALL_SKILL_FILES or [SKILL_MD], ids=lambda p: p.name)
def test_dual_mode_invariant(doc: Path):
    offenses = check_dual_mode(doc)
    assert not offenses, (
        f"\nDual-mode regression in {doc}:\n"
        + "\n".join(f"  L{ln}: {snip}" for ln, snip in offenses)
    )


@pytest.mark.parametrize("doc", ALL_SKILL_FILES or [SKILL_MD], ids=lambda p: p.name)
def test_no_abbreviated_prefix(doc: Path):
    if not doc.is_file():
        pytest.fail(f"missing file: {doc}")
    text = doc.read_text(encoding="utf-8")
    matches = ABBREVIATED_RE.findall(text)
    assert not matches, (
        f"abbreviated prefix `mcp__mare__` (without `-toolbox`) found in "
        f"{doc.name}: {matches}. Canonical prefix is `mcp__mare-toolbox__`."
    )


def test_skill_md_snapshot():
    actual = hashlib.sha256(SKILL_MD.read_bytes()).hexdigest()
    if os.environ.get("UPDATE_SKILL_SNAPSHOT") == "1":
        SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_FILE.write_text(actual + "\n")
        return
    if not SNAPSHOT_FILE.is_file():
        warnings.warn(
            f"SKILL.md snapshot missing at {SNAPSHOT_FILE.relative_to(REPO_ROOT)}. "
            f"Create with: UPDATE_SKILL_SNAPSHOT=1 pytest "
            f"mcp-gateway/tests/test_skill_md_dual_mode.py::test_skill_md_snapshot",
            UserWarning,
        )
        return
    expected = SNAPSHOT_FILE.read_text().strip()
    if actual != expected:
        warnings.warn(
            f"SKILL.md sha256 drift.\n  actual:   {actual}\n  expected: {expected}\n"
            f"  refresh:  UPDATE_SKILL_SNAPSHOT=1 pytest "
            f"mcp-gateway/tests/test_skill_md_dual_mode.py::test_skill_md_snapshot",
            UserWarning,
        )


# ---- SKILL-04: dynamic-mode plumbing ----------------------------------


def test_update_state_writes_dynamic_fields(tmp_path: Path):
    update_state = SKILL_DIR / "scripts/update_state.py"
    assert update_state.is_file(), f"missing {update_state}"
    result = subprocess.run(
        [
            sys.executable,
            str(update_state),
            "--status-dir",
            str(tmp_path),
            "--phase",
            "test",
            "--probe-dynamic",
            "--mode",
            "scripts",
            "--dynamic-enabled",
            "false",
            "--dynamic-caps",
            "{}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"update_state.py exited {result.returncode}\nstderr={result.stderr}"
    )
    state = json.loads((tmp_path / "CURRENT_STATE.json").read_text())
    assert "mode" in state and state["mode"] == "scripts"
    assert "dynamic_mode_enabled" in state and state["dynamic_mode_enabled"] is False
    assert "dynamic_capabilities" in state and isinstance(state["dynamic_capabilities"], dict)


def test_artifact_spec_documents_dynamic_fields():
    spec = SKILL_DIR / "references/artifact-spec.md"
    assert spec.is_file(), f"missing {spec}"
    text = spec.read_text(encoding="utf-8")
    for token in ("dynamic_mode_enabled", "dynamic_capabilities", '"mode"'):
        assert token in text, f"artifact-spec.md missing token {token!r}"


def test_skill_documents_dynamic_skip_behavior():
    # SKILL.md or any W-5/W-6/W-7 file (which is where dynamic skip lives)
    haystack_files = [SKILL_MD] + [
        p for p in WORKFLOW_FILES if re.match(r"W-[567]-", p.name)
    ]
    haystack = "\n".join(
        p.read_text(encoding="utf-8") for p in haystack_files if p.is_file()
    )
    assert re.search(r"dynamic/[\w\-.<>]+-skipped\.md", haystack), (
        "no `<case_dir>/dynamic/<step>-skipped.md` placeholder pattern documented"
    )
    assert re.search(r"skipped[ \-_]steps", haystack, re.IGNORECASE), (
        "no 'skipped steps' INDEX.md subsection documented (D-18)"
    )


# ---- Frontmatter contract (Anthropic API enforces description limits) -------


def _extract_frontmatter(path: Path) -> dict[str, str]:
    """Return frontmatter as {key: raw_value} string map. Empty dict if no block."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
        if km:
            out[km.group(1)] = km.group(2).strip().strip("\"'")
    return out


def test_frontmatter_description_within_anthropic_limit():
    """Anthropic Agent Skills enforce description <= 1024 chars."""
    fm = _extract_frontmatter(SKILL_MD)
    desc = fm.get("description", "")
    assert desc, "frontmatter missing `description` key"
    assert len(desc) <= 1024, (
        f"frontmatter description is {len(desc)} chars; Anthropic limit is 1024. "
        f"Trim before publishing."
    )


def test_frontmatter_description_ends_with_period():
    """Sentence hygiene: description is a complete sentence."""
    fm = _extract_frontmatter(SKILL_MD)
    desc = fm.get("description", "")
    assert desc.endswith("."), (
        f"frontmatter description should end with `.`; got: ...{desc[-40:]!r}"
    )


# ---- Structural protection: required H2 sections + Decision Tree routes -----

REQUIRED_H2 = (
    # (heading regex tolerant of v1.1 wording, friendly-name for error msg)
    (r"^##\s+.*Backend Priorit", "Backend Priority"),
    (r"^##\s+.*Operating Modes?", "Operating Modes"),
    (r"^##\s+.*Workflow Decision Tree", "Workflow Decision Tree"),
    (r"^##\s+.*Dynamic.*Mode", "Dynamic Mode"),
)


def test_skill_md_has_required_h2_sections():
    """SKILL.md must keep its load-bearing H2 sections after any rewrite (RED until 12-04)."""
    text = SKILL_MD.read_text(encoding="utf-8")
    missing = [
        friendly
        for pattern, friendly in REQUIRED_H2
        if not re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
    ]
    assert not missing, (
        f"SKILL.md missing required H2 sections: {missing}. "
        f"These protect against accidental deletion during edits."
    )


def test_decision_tree_routes_to_all_wn():
    """The Workflow Decision Tree must link to W-1..W-7 (RED until 12-04 lands routing)."""
    text = SKILL_MD.read_text(encoding="utf-8")
    # Slice from the Decision Tree H2 to the next H2 (or EOF).
    start = re.search(r"^##\s+.*Workflow Decision Tree.*$", text, re.MULTILINE | re.IGNORECASE)
    if not start:
        pytest.fail("no `## Workflow Decision Tree` heading found in SKILL.md")
    tail = text[start.end():]
    end = re.search(r"^##\s+", tail, re.MULTILINE)
    section = tail[: end.start()] if end else tail
    missing = [f"W-{n}" for n in range(1, 8) if not re.search(rf"W-{n}\b", section)]
    assert not missing, (
        f"Decision Tree section does not route to: {missing}. "
        f"Every W-N file must be reachable from the routing logic."
    )


# ---- Cross-reference integrity ---------------------------------------------


def _enumerate_gateway_tools() -> set[str]:
    """Scan mcp-gateway source for every registered tool name.

    Covers both registration patterns used in the codebase:
      1. `@mcp.tool()` decorator immediately above a `def`
      2. Explicit `mcp.tool()(<name>)` registration inside `register(mcp)`
    """
    tools: set[str] = set()
    src_root = REPO_ROOT / "mcp-gateway/src/mcp_gateway"
    if not src_root.is_dir():
        return tools
    for path in src_root.rglob("*.py"):
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if "@mcp.tool()" in line:
                for j in range(i + 1, min(i + 5, len(lines))):
                    m = re.match(r"\s*(?:async\s+)?def\s+(\w+)\s*\(", lines[j])
                    if m:
                        tools.add(m.group(1))
                        break
        for m in re.finditer(r"mcp\.tool\(\)\((\w+)\)", src):
            tools.add(m.group(1))
    return tools


TOOL_TOKEN_RE = re.compile(r"mcp__mare[-_]toolbox__([a-z0-9_]+)")


def test_tool_tokens_exist_in_gateway_registry():
    """Every `mcp__mare-toolbox__<name>` in skill docs must resolve to a real registered tool."""
    registry = _enumerate_gateway_tools()
    if not registry:
        pytest.skip("could not enumerate gateway tool registry (mcp-gateway src not found)")
    used: set[str] = set()
    for path in ALL_SKILL_FILES:
        if not path.is_file():
            continue
        for m in TOOL_TOKEN_RE.finditer(path.read_text(encoding="utf-8")):
            used.add(m.group(1))
    unknown = sorted(used - registry)
    assert not unknown, (
        f"Skill docs reference tool tokens that do not exist in the gateway registry:\n  "
        f"{unknown}\nKnown tools (sample): {sorted(registry)[:5]}..."
    )


SCRIPT_REF_RE = re.compile(r"scripts/([\w\-]+\.(?:sh|py))")


def test_scripts_references_resolve():
    """Every `scripts/<foo>.{sh,py}` referenced in skill docs must exist on disk."""
    scripts_dir = SKILL_DIR / "scripts"
    if not scripts_dir.is_dir():
        pytest.skip(f"scripts dir missing: {scripts_dir}")
    available = {p.name for p in scripts_dir.iterdir() if p.is_file()}
    missing: list[tuple[str, str]] = []
    for path in ALL_SKILL_FILES:
        if not path.is_file():
            continue
        for m in SCRIPT_REF_RE.finditer(path.read_text(encoding="utf-8")):
            name = m.group(1)
            if name not in available:
                missing.append((path.name, name))
    assert not missing, (
        f"Skill docs reference scripts that do not exist:\n  "
        + "\n  ".join(f"{doc}: scripts/{name}" for doc, name in missing)
    )


# ---- Stub-marker hygiene ----------------------------------------------------

STUB_MARKER_RE = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b")


@pytest.mark.parametrize("doc", ALL_SKILL_FILES or [SKILL_MD], ids=lambda p: p.name)
def test_no_stub_markers_in_published_surface(doc: Path):
    """Published skill surface must not contain TODO/TBD/FIXME/XXX markers."""
    if not doc.is_file():
        pytest.skip(f"file not present: {doc}")
    offenses: list[tuple[int, str]] = []
    for i, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), start=1):
        if STUB_MARKER_RE.search(line):
            offenses.append((i, line.strip()))
    assert not offenses, (
        f"\nStub markers in {doc.name}:\n"
        + "\n".join(f"  L{ln}: {snip}" for ln, snip in offenses)
    )
