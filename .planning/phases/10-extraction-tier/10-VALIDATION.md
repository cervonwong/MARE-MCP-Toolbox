---
phase: 10
slug: extraction-tier
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| **Quick run command** | `cd mcp-gateway && pytest tests/test_extraction.py tests/test_tools_extract.py -x -q` |
| **Full suite command** | `cd mcp-gateway && pytest -q` |
| **Estimated runtime** | ~60 seconds quick / ~180 seconds full |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

> Populated by gsd-planner from tasks defined in 10-*-PLAN.md. Each task must
> reference at least one EXTR-XX requirement and be covered by an automated
> test command OR an explicit Wave 0 stub.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| pending | — | — | EXTR-01..06 | — | see CONTEXT D-22/D-23 | unit/integration | populated by planner | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_extraction.py` — RED stubs for EXTR-01 (binwalk), EXTR-02 (unblob), EXTR-03 (UPX trio)
- [ ] `tests/test_tools_extract.py` — RED stubs for EXTR-04 (`list_extracted_files`), EXTR-05 (`promote_extracted_sample`), EXTR-06 (symlink quarantine + bomb cap + atomic promotion)
- [ ] `tests/conftest.py` — fixtures: `tmp_case_dir`, `synthetic_zip_sample`, `synthetic_upx_sample`, `symlink_payload_sample`
- [ ] Docker probe (in container): confirm `binwalk3`, `unblob`, `upx` are on PATH and report expected `--version`

*Phase 9 conftest fixtures are reused where possible; new fixtures only for synthetic extractable samples and symlink payloads.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| End-to-end recursive triage via Claude Code MCP client | EXTR-05 | Requires live gateway + remote client; demonstrates that promoted child case is independently analysable | After Wave 3 GREEN: upload firmware fixture → call `run_binwalk(..., mode="extract")` → call `list_extracted_files` → call `promote_extracted_sample` with a carved child → run `run_strings` on the new case to confirm it functions as a first-class case |
| Archive-bomb cap aborts mid-extraction | EXTR-06 | Cannot ship a 4 GB+ bomb fixture; manual test with a hand-crafted zip-bomb in dev | Set `MCP_GATEWAY_MAX_EXTRACT_MB=64` env, run extraction on a zip-bomb sample, confirm process is killed and meta sidecar shows `aborted: bomb-cap-exceeded` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (binwalk3, unblob, upx, symlink quarantine, bomb cap, promotion)
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter after planner populates the per-task map

**Approval:** pending
