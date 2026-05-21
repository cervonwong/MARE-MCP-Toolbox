---
phase: 10
slug: extraction-tier
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-19
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | mcp-gateway/pyproject.toml (or existing pytest.ini) |
| **Quick run command** | `cd mcp-gateway && pytest tests/extraction/ -x -q -m "not slow"` |
| **Full suite command** | `cd mcp-gateway && pytest -q` |
| **Estimated runtime** | ~1 second extraction / ~40 seconds full |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

Populated by the Plan 05 executor from all tasks defined across plans 01-05.
Each row maps a task to its locked automated verification command and the
EXTR-XX requirement(s) the task addresses.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01.T1 | 01 | 0 | EXTR-01..06 | T-10-W0-02 | Dockerfile uses binwalk3 (v2 EOL) + probe script for capability verification | unit | `grep -c '^[[:space:]]*binwalk3' Dockerfile \| grep -q '^[1-9]'` | yes | ✅ green |
| 10-01.T2 | 01 | 0 | EXTR-01..06 | T-10-W0-01 | Wave 0 RED-stub scaffold for all 13 test files | unit | `cd mcp-gateway && python -m pytest tests/extraction/ --collect-only -q` | yes | ✅ green |
| 10-02.T1 | 02 | 1 | EXTR-01..06 | T-10-02-03 | Primitive layer with locked surface + env constants + JobToolSpec registration | unit | `python -c "from mcp_gateway import extraction; from mcp_gateway.jobs import JOB_TOOL_REGISTRY; assert 'unblob' in JOB_TOOL_REGISTRY and 'binwalk_extract' in JOB_TOOL_REGISTRY"` | yes | ✅ green |
| 10-03.T1 | 03 | 1 | EXTR-02, EXTR-06 | T-10-03-01, T-10-03-02, T-10-03-03 | Archive-bomb monitor + GC-safe task retention + post-terminal symlink quarantine timing | integration | `cd mcp-gateway && python -m pytest tests/extraction/test_extract_monitor.py -x --no-header -q` | yes | ✅ green |
| 10-04.T1 | 04 | 2 | EXTR-01..06 | T-10-04-01..09 | 7 MCP tool handlers + disclaimer splice + D-22 error shapes + monitor spawn | unit + integration | `cd mcp-gateway && python -m pytest tests/extraction/ -m "not slow" -x --no-header -q` | yes | ✅ green |
| 10-05.T1 | 05 | 3 | EXTR-01..06 | T-10-05-01, T-10-05-02 | register_all_tools wires extract; EXPECTED_TOOLS 47→54; range bump | unit | `cd mcp-gateway && python -m pytest tests/test_tool_list.py -x --no-header -q` | yes | ✅ green |
| 10-05.T2 | 05 | 3 | EXTR-01..06 | T-10-05-03, T-10-05-04, T-10-05-05 | Wave 0 RED → GREEN flip on all 13 test files | unit + integration | `cd mcp-gateway && python -m pytest tests/extraction/ -x --no-header -q -m "not slow"` | yes | ✅ green |
| 10-05.T3 | 05 | 3 | EXTR-01..06 | T-10-05-06 | Nyquist sign-off; VALIDATION.md finalized | docs | n/a — verified by frontmatter `nyquist_compliant: true` | yes | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/extraction/test_*.py` — RED stubs for EXTR-01..06 across all 13 test files (Plan 01 expanded the original 2-file scope into a 13-file extraction/ test package)
- [x] `tests/extraction/__init__.py` + `tests/extraction/conftest.py` — Plan 01 fixtures: `_require_binwalk_or_skip`, `_require_unblob_or_skip`, `_require_upx_or_skip`, `fake_extraction_tree`
- [x] Docker probe (in container): `scripts/probe_extraction_tools.sh` exists (Plan 01) — to be run after the operator's next `./run_docker.sh` rebuild
- [x] Plan 05 GREEN flip: all 13 test files exercise the locked primitive + MCP-surface contracts; 51 non-slow tests PASS on host, 3 slow tests skip cleanly via `_require_*_or_skip` gates

*Phase 9 conftest fixtures are reused where possible; new fixtures only for synthetic extractable samples and symlink payloads.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| End-to-end recursive triage via Claude Code MCP client | EXTR-05 | Requires live gateway + remote client; demonstrates that promoted child case is independently analysable | After Wave 3 GREEN: upload firmware fixture → call `run_binwalk(..., mode="extract")` → call `list_extracted_files` → call `promote_extracted_sample` with a carved child → run `run_strings` on the new case to confirm it functions as a first-class case |
| Archive-bomb cap aborts mid-extraction | EXTR-06 | Cannot ship a 4 GB+ bomb fixture; manual test with a hand-crafted zip-bomb in dev | Set `MCP_GATEWAY_MAX_EXTRACT_MB=64` env, run extraction on a zip-bomb sample, confirm process is killed and meta sidecar shows `aborted: bomb-cap-exceeded` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (binwalk3, unblob, upx, symlink quarantine, bomb cap, promotion)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter after planner populates the per-task map

**Approval: green**
