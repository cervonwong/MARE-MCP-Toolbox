---
phase: 5
slug: f-1-image-hash-fix
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-12
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 8 (asyncio_mode = "auto", not used here) |
| **Config file** | `mcp-gateway/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `pytest mcp-gateway/tests/test_image_hash.py -x` |
| **Full suite command** | `pytest mcp-gateway/tests/ -x` |
| **Estimated runtime** | <2s for quick run (D-11); ~10-15s for full mcp-gateway suite |

---

## Sampling Rate

- **After every task commit:** Run `pytest mcp-gateway/tests/test_image_hash.py -x`
- **After every plan wave:** Run `pytest mcp-gateway/tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green PLUS smoke `./run_docker.sh --help` exits 0
- **Max feedback latency:** 2 seconds (per D-11)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 5-01-01 | 01 | 1 | FOUND-01 / D-02 | — | N/A (no security surface; build-time hash) | structural (grep) | `grep -nE "LC_ALL=C sort" run_docker.sh \| wc -l` returns >= 2 | ❌ W0 | ⬜ pending |
| 5-02-01 | 02 | 2 | FOUND-01 / D-05, D-06 | — | N/A | structural | `test -x scripts/compute_image_hash.sh` exits 0 | ❌ W0 | ⬜ pending |
| 5-02-02 | 02 | 2 | FOUND-01 / D-06 | — | N/A | unit (subprocess) | `pytest mcp-gateway/tests/test_image_hash.py::test_helper_exists_and_executable -x` | ❌ W0 | ⬜ pending |
| 5-02-03 | 02 | 2 | FOUND-01 / D-06 | — | byte-identical refactor; preserve `DOCKERFILE_SHA`/`SHORT_SHA`/`HASH_IMAGE` names | structural (grep) | `grep -nE "^DOCKERFILE_SHA=|^SHORT_SHA=|^HASH_IMAGE=" run_docker.sh \| wc -l` returns >= 3 | ❌ W0 | ⬜ pending |
| 5-03-01 | 03 | 3 | FOUND-01 / SC-1 + SC-4 | — | N/A | unit (subprocess) | `pytest mcp-gateway/tests/test_image_hash.py::test_sc1_src_edit_changes_hash -x` | ❌ W0 | ⬜ pending |
| 5-03-02 | 03 | 3 | FOUND-01 / SC-2 | — | N/A | unit (subprocess) | `pytest mcp-gateway/tests/test_image_hash.py::test_sc2_pyproject_edit_changes_hash -x` | ❌ W0 | ⬜ pending |
| 5-03-03 | 03 | 3 | FOUND-01 / SC-3a-d | — | N/A | unit (subprocess, parametrize) | `pytest mcp-gateway/tests/test_image_hash.py::test_sc3_pruned_writes_do_not_change_hash -x` | ❌ W0 | ⬜ pending |
| 5-03-04 | 03 | 3 | FOUND-01 / D-10 | — | N/A | unit (subprocess + env) | `pytest mcp-gateway/tests/test_image_hash.py::test_binja_toggle_changes_hash -x` | ❌ W0 | ⬜ pending |
| 5-03-05 | 03 | 3 | FOUND-01 / stability | — | N/A | unit (subprocess) | `pytest mcp-gateway/tests/test_image_hash.py::test_baseline_hash_stable -x` | ❌ W0 | ⬜ pending |
| 5-03-06 | 03 | 3 | FOUND-01 / D-05 contract | — | clear stderr on missing inputs | unit (subprocess) | `pytest mcp-gateway/tests/test_image_hash.py::test_missing_dockerfile_exits_nonzero -x` | ❌ W0 | ⬜ pending |
| 5-03-07 | 03 | 3 | FOUND-01 / D-10 | — | N/A | unit (subprocess, clean env) | `pytest mcp-gateway/tests/test_image_hash.py::test_helper_clean_env_no_binja_inputs -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Task IDs are placeholders — the planner will finalize task identifiers in PLAN.md files; the requirement mapping above is the contract.*

---

## Wave 0 Requirements

- [ ] `scripts/` — new directory at repo root (does not yet exist)
- [ ] `scripts/compute_image_hash.sh` — new helper extracted from `run_docker.sh:212-229` (FOUND-01 / D-05)
- [ ] `mcp-gateway/tests/test_image_hash.py` — 11 test cases per the Validation Architecture in 05-RESEARCH.md (FOUND-01)
- [ ] `run_docker.sh:212-229` — modify in place: replace inline subshell with helper call, preserve `DOCKERFILE_SHA`/`SHORT_SHA`/`HASH_IMAGE` scope and names (FOUND-01 / D-06)

No framework install needed — pytest >= 8 is already in `mcp-gateway/pyproject.toml` `[project.optional-dependencies] dev`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `./run_docker.sh --help` still exits 0 after refactor | FOUND-01 / D-06 | The pytest does not invoke `run_docker.sh` — it tests the extracted helper. A smoke check of the script itself catches accidental syntax breakage during the inline → helper-call edit. | From repo root: `./run_docker.sh --help`; expect exit 0 and unchanged usage output. |
| First post-fix `./run_docker.sh` may trigger a one-time rebuild | FOUND-01 / A3 | Acceptable per CONTEXT.md and RESEARCH §Runtime State Inventory. Confirms the fix is taking effect. | Run `./run_docker.sh` once after the phase merges; observe `[build] building ...` (not `[build] up to date`). Subsequent runs without edits should print `[build] up to date`. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (helper script, scripts/ dir, new test file, run_docker.sh patch)
- [ ] No watch-mode flags
- [ ] Feedback latency < 2s (per D-11)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
