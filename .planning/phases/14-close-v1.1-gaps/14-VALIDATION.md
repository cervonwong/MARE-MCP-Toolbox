---
phase: 14
slug: close-v1-1-gaps
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-21
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (mcp-gateway/pyproject.toml) |
| **Config file** | `mcp-gateway/pyproject.toml` (pytest config); existing `mcp-gateway/tests/` |
| **Quick run command** | `cd mcp-gateway && uv run pytest tests/test_r2_sessions.py tests/test_sessions_concurrency.py tests/test_acl_available.py -q` |
| **Full suite command** | `cd mcp-gateway && uv run pytest -m 'not slow'` |
| **Estimated runtime** | ~90 seconds (full non-slow), ~5 seconds (targeted) |

---

## Sampling Rate

- **After every task commit:** Run quick command on the affected test file(s)
- **After every plan wave:** Run `cd mcp-gateway && uv run pytest -m 'not slow'`
- **Before `/gsd-verify-work`:** Full suite must show 0 failed; `/gsd-audit-milestone v1.1` must return `status: passed`
- **Max feedback latency:** ~5 seconds (targeted) / ~90 seconds (full suite)

---

## Per-Task Verification Map

Populated after planner produces PLAN.md files. Skeleton (planner fills exact task IDs):

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 14-01-NN | 01 | 1 | (closure) | — | `SessionCapReached` survives `importlib.reload`; reproducer chain green | unit (regression) | `cd mcp-gateway && uv run pytest tests/test_gdb_session.py::test_gdb_env_validates_bad_values tests/test_r2_sessions.py::test_unsafe_shares_combined_cap -q` | ✅ | ⬜ pending |
| 14-01-NN | 01 | 1 | (closure) | — | `r2`/`gdb` survive reload re-import as package attributes | unit (regression) | `cd mcp-gateway && uv run pytest tests/test_gdb_session.py::test_gdb_env_validates_bad_values tests/test_sessions_concurrency.py -q` | ✅ | ⬜ pending |
| 14-01-NN | 01 | 1 | (closure) | — | `test_setfacl_on_path` cleanly skips on bare host; runs in container | unit (skip contract) | `cd mcp-gateway && uv run pytest tests/test_acl_available.py -q` (host: skipped; container: passed) | ✅ | ⬜ pending |
| 14-NN-NN | 02 | 1 | (closure) | — | Final gate: full non-slow suite green in one run | integration | `cd mcp-gateway && uv run pytest -m 'not slow'` | ✅ | ⬜ pending |
| 14-NN-NN | 03 | 1 | HARDEN-01..07, SESS-CAP-01, JOBS-CAP-01, SHELL-03, ARTIF-01..04 | — | REQUIREMENTS.md checkboxes + traceability `Verified` flips align with VERIFICATION evidence | doc verify | `grep -c "\\[x\\] HARDEN-" .planning/REQUIREMENTS.md` ≥ 7; `grep "61/61" .planning/REQUIREMENTS.md` | ✅ | ⬜ pending |
| 14-NN-NN | 04 | 1 | (closure) | — | ROADMAP.md progress table reflects phases 5-9 complete with real verification dates | doc verify | `grep -E "Phase 5.*Complete.*2026-05-12" .planning/ROADMAP.md` and similar for 6-9 | ✅ | ⬜ pending |
| 14-NN-NN | 04 | 1 | (closure) | — | STATE.md body matches frontmatter (no stale "in progress" / "next phase" disagreement) | doc verify | `! grep -E "in_progress|next phase" .planning/STATE.md` (or planner-specified exact grep) | ✅ | ⬜ pending |
| 14-NN-NN | 04 | 1 | (closure) | — | VALIDATION.md frontmatter `nyquist_compliant: true` for phases 5, 6, 12, 13 | doc verify | `grep "nyquist_compliant: true" .planning/phases/{05,06,12,13}-*/*-VALIDATION.md` (4 hits) | ✅ | ⬜ pending |
| 14-NN-NN | 05 | 2 | (closure) | — | 15 live UAT items recorded in respective VERIFICATION.md with timestamps + transcripts | manual recording | `grep -l "Live UAT Results (Phase 14 closure)" .planning/phases/{07,08,10,11,13}-*/*-VERIFICATION.md` (5 files) | ✅ | ⬜ pending |
| 14-NN-NN | 05 | 2 | (closure) | — | Audit re-run returns `status: passed` with no gaps | integration (audit re-run) | `/gsd-audit-milestone v1.1` → `status: passed`, `gaps: []` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements. No new test files or fixtures needed.*

- Test framework, conftest, and existing reproducer suites are all in place at `mcp-gateway/tests/`.
- The 8 failing tests are existing tests; D-01/D-02 fixes turn them green without authoring new tests.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Phase 7: mare-shell UID + ACL revocations | (closure UAT) | Requires container shell with mare-shell user + filesystem ACLs | `./run_docker.sh --remote`; exec into container; verify `id mare-shell` UID + `getfacl` on protected paths; record transcript |
| Phase 7: 100 MB run_shell /dev/urandom slow test | (closure UAT) | Slow test marked slow; needs container with run_shell wrapper | `./run_docker.sh --remote`; from remote MCP client trigger `run_shell` against `/dev/urandom` with 100 MB cap; record transcript |
| Phase 7: MCP Resources visible to a remote MCP client | (closure UAT) | Requires remote MCP client roundtrip | `./run_docker.sh --remote`; connect Claude Code or similar remote MCP client; verify Resources panel; record transcript |
| Phase 8: container r2-gated test suite | (closure UAT) | Requires r2 binary present (container only) | `./run_docker.sh --remote`; `pytest -m r2_required` inside container; record transcript |
| Phase 8: gateway shutdown leaves no zombie r2 processes | (closure UAT) | Process lifecycle observation outside test harness | Start gateway in container; spawn r2 sessions; SIGTERM gateway; `ps -ef \| grep -c r2` == 0; record transcript |
| Phase 10: remote-client recursive triage | (closure UAT) | run_binwalk extract → list_extracted_files → promote_extracted_sample chain via remote MCP | `./run_docker.sh --remote`; from remote client: trigger the chain on a known archive; record transcript |
| Phase 10: archive-bomb cap aborts mid-extraction | (closure UAT) | Requires crafted bomb input and real extractor | Inside container: feed crafted archive bomb to `run_binwalk extract`; verify cap aborts; record transcript |
| Phase 10: `scripts/probe_extraction_tools.sh` READY verdict | (closure UAT) | Verifies container build provisioned binwalk3/unblob/upx | Inside container: `bash scripts/probe_extraction_tools.sh`; expect `READY`; record transcript |
| Phase 10: three slow extraction integration tests | (closure UAT) | Marked slow; container-only | Inside container: `uv run pytest -m slow tests/test_extraction_*.py`; record transcript |
| Phase 11: tools/list returns 61 under --remote --dynamic | (closure UAT) | Requires live dynamic mode | `./run_docker.sh --remote --dynamic`; query `tools/list`; expect count 61; record transcript |
| Phase 11: get_dynamic_capabilities + run_strace end-to-end | (closure UAT) | Requires live container with strace | `./run_docker.sh --remote --dynamic`; trigger pair from remote client; record transcript |
| Phase 11: strace/ltrace/qemu slow JOBS integration tests | (closure UAT) | Slow + container-only | Inside container: `uv run pytest -m slow tests/test_dynamic_jobs.py` (or planner-located path); record transcript |
| Phase 11: gdb MI allowlist runtime enforcement | (closure UAT) | Live gdb session needed | Container: open gdb MI session; attempt non-allowlisted command; expect rejection; record transcript |
| Phase 11: `scripts/probe_dynamic_tools.sh` READY verdict | (closure UAT) | Verifies dynamic toolchain present in container | Inside container: `bash scripts/probe_dynamic_tools.sh`; expect `READY`; record transcript |
| Phase 13: Live r2 session reports cfg.sandbox=true (HARDEN-03) | HARDEN-03 (closure live arm) | Live r2 process needed; closes HARDEN-03 live verification | Inside container: open r2 session; `e cfg.sandbox`; expect `true`; record transcript |

*Why these are manual:* each requires a freshly rebuilt container (post D-01/D-02 fixes), often plus a remote MCP client — automatable in CI but explicitly designated by the audit as live human-verification items. Recording format per D-13 in CONTEXT.md.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (none required — see "Wave 0 Requirements")
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s (full non-slow suite)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
