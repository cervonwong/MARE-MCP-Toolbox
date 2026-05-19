---
phase: 11
slug: dynamic-lab-mode-env-gated
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-19
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source of truth: `11-RESEARCH.md` §"Validation Architecture" (lines 480–533).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (already in `mcp-gateway/pyproject.toml` test deps) |
| **Config file** | `mcp-gateway/pyproject.toml` (default pytest discovery) |
| **Quick run command** | `pytest mcp-gateway/tests/test_dynamic_*.py mcp-gateway/tests/test_sessions_package.py mcp-gateway/tests/test_gdb_session.py -x -m "not slow"` |
| **Full suite command** | `pytest mcp-gateway/tests/ -x` (slow tests gated via `_require_*_or_skip`) |
| **Estimated runtime** | ~10 s quick · ~30 s wave · full suite varies with apt-installed tools |

---

## Sampling Rate

- **After every task commit:** Run the quick command above (~10 s)
- **After every plan wave:** Run `pytest mcp-gateway/tests/ -x -m "not slow"` (~30 s)
- **Before `/gsd-verify-work`:** Full suite must be green including slow tests (require gdb / strace / ltrace / qemu-user-static / netns posture)
- **Max feedback latency:** 30 s per wave; ~60 s per phase gate

---

## Per-Task Verification Map

> Initial mapping derived from RESEARCH.md §"Phase Requirements → Test Map". Plan authors must add `task_id` columns once plans are drafted. Status starts ⬜ pending; will be ✅ after Wave 0 stubs land.

| Req ID | Behavior | Test Type | Automated Command | File Exists | Status |
|--------|----------|-----------|-------------------|-------------|--------|
| DYN-01 | Tools registered iff env var set | unit | `pytest mcp-gateway/tests/test_dynamic_gate.py -x` | ❌ W0 | ⬜ pending |
| DYN-01 | EXPECTED_TOOLS = 54 (off) / 61 (on) | unit | `pytest mcp-gateway/tests/test_tool_list.py -x -k "expected_tools"` | ✅ edit existing | ⬜ pending |
| DYN-02 | `--dynamic` exports env var, requires `--remote` | shell | `bats run_docker.sh --dynamic` (or pytest-shell-wrap matching Phase 3) | ❌ W0 | ⬜ pending |
| DYN-03 | strace runs with profile, netns active, output in `case_dir/dynamic/` | integration | `pytest mcp-gateway/tests/test_dynamic_tools.py::test_run_strace_roundtrip -x -m slow` | ❌ W0 | ⬜ pending |
| DYN-03 | argv allowlist rejects shell-metachar in `extra_args` | unit | `pytest mcp-gateway/tests/test_dynamic_primitive.py::test_extra_args_rejects_metachar -x` | ❌ W0 | ⬜ pending |
| DYN-03 | netns prevents network: `getaddrinfo` returns `ENETUNREACH` | integration | `pytest mcp-gateway/tests/test_dynamic_tools.py::test_netns_blocks_dns -x -m slow` | ❌ W0 | ⬜ pending |
| DYN-04 | `run_qemu_user` with `arch=arm` runs on a known-good ELF | integration | `pytest mcp-gateway/tests/test_dynamic_tools.py::test_run_qemu_user_arm -x -m slow` | ❌ W0 | ⬜ pending |
| DYN-04 | `probe_qemu_architectures` returns non-empty when binaries exist | unit | `pytest mcp-gateway/tests/test_dynamic_primitive.py::test_probe_qemu_architectures -x` | ❌ W0 | ⬜ pending |
| DYN-05 | Open gdb session → exec → close roundtrip with MI3 framing | integration | `pytest mcp-gateway/tests/test_gdb_session.py::test_gdb_session_roundtrip -x -m slow` | ❌ W0 | ⬜ pending |
| DYN-05 | MI allowlist accepts known prefixes | unit | `pytest mcp-gateway/tests/test_gdb_session.py::test_mi_allowlist_positive -x` | ❌ W0 | ⬜ pending |
| DYN-05 | MI allowlist rejects `python` / `interpreter-exec console` / `source` / `!` / `pi` / `attach` / `-target-select` / `-gdb-set logging on` / `add-symbol-file` / `dump` / `set inferior-tty` | unit | `pytest mcp-gateway/tests/test_gdb_session.py::test_mi_allowlist_negative_matrix -x` | ❌ W0 | ⬜ pending |
| DYN-06 | Capability probe returns expected fields, never raises | unit | `pytest mcp-gateway/tests/test_dynamic_primitive.py::test_probe_all -x` | ❌ W0 | ⬜ pending |
| DYN-06 | Probe with monkeypatched missing tools surfaces warnings | unit | `pytest mcp-gateway/tests/test_dynamic_primitive.py::test_probe_warnings_on_missing -x` | ❌ W0 | ⬜ pending |
| DYN-07 | Trace tools dispatch via `start_tool_job` | integration | `pytest mcp-gateway/tests/test_dynamic_jobs.py::test_strace_via_jobs -x -m slow` | ❌ W0 | ⬜ pending |
| DYN-07 | `reap_followfork_strays` kills `setsid` grandchildren | integration | `pytest mcp-gateway/tests/test_dynamic_primitive.py::test_reap_followfork_strays -x -m slow` | ❌ W0 | ⬜ pending |
| DYN-07 | Sample resolved by sha256 from `uploads/` and existing `case_dir` | unit | `pytest mcp-gateway/tests/test_dynamic_tools.py::test_sample_resolution -x` | ❌ W0 | ⬜ pending |
| Refactor | `sessions/` package re-exports preserve every Phase 8 symbol | unit | `pytest mcp-gateway/tests/test_sessions_package.py -x` | ❌ W0 | ⬜ pending |
| Refactor | Phase 8 existing tests continue to pass | regression | `pytest mcp-gateway/tests/test_sessions.py mcp-gateway/tests/test_r2_sessions.py -x` | ✅ existing | ⬜ pending |
| All | Disclaimer string in all 7 dynamic-tool docstrings | unit | `pytest mcp-gateway/tests/test_dynamic_tools.py::test_disclaimer_in_all_docstrings -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Per RESEARCH.md §"Wave 0 Gaps":

- [ ] `mcp-gateway/tests/test_dynamic_primitive.py` — DYN-03 / DYN-04 / DYN-06 / DYN-07 builder + probe + reap logic
- [ ] `mcp-gateway/tests/test_dynamic_tools.py` — MCP surface tests for all 7 tools (DYN-03 / DYN-04 / DYN-05 / DYN-06)
- [ ] `mcp-gateway/tests/test_gdb_session.py` — gdb-MI3 driver, sentinel framing, allowlist matrix (DYN-05)
- [ ] `mcp-gateway/tests/test_sessions_package.py` — Phase 8 → Phase 11 refactor regression
- [ ] `mcp-gateway/tests/test_dynamic_jobs.py` — `JobToolSpec` integration for 3 dynamic specs (DYN-07)
- [ ] `mcp-gateway/tests/test_dynamic_gate.py` — env-gate behavior (DYN-01)
- [ ] `mcp-gateway/tests/conftest.py` — add `_require_gdb_or_skip`, `_require_strace_or_skip`, `_require_ltrace_or_skip`, `_require_qemu_user_or_skip`, `_require_netns_or_skip`
- [ ] `mcp-gateway/tests/fixtures/dns_lookup.c` — `getaddrinfo("example.com", ...)` to verify `ENETUNREACH` under netns
- [ ] `mcp-gateway/tests/fixtures/setsid_escape.c` — fork + child `setsid()` + `sleep(60)` to verify reap
- [ ] `mcp-gateway/tests/fixtures/hello_<arch>.bin` — pre-built foreign-arch ELF for qemu round-trip
- [ ] `scripts/probe_dynamic_tools.sh` (optional) — operator helper analogous to Phase 10's `probe_extraction_tools.sh`

**Framework install:** None — pytest-asyncio already in `mcp-gateway/pyproject.toml`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Container shape unchanged when `MCP_GATEWAY_DYNAMIC_TOOLS` is unset | DYN-01 | Requires running the gateway image to confirm `tools/list` advertises exactly 54 tools and standard pytest suite passes byte-identically | 1) Build image without `--dynamic`. 2) `mcp-cli list-tools --url $URL` → assert count == 54. 3) `docker exec gateway pytest mcp-gateway/tests/ -x` |
| Operator end-to-end on the rebuilt image | DYN-02 | Validates compose / run_docker.sh / lifespan / probe wiring under real Docker (slow CI / dev-only) | 1) `./run_docker.sh --remote --dynamic`. 2) `curl -H "Authorization: Bearer $TOKEN" $URL/mcp/tools/list` → assert 61 tools. 3) Call `get_dynamic_capabilities` → assert non-null probe result. |
| qemu-user multi-thread behavior on real foreign binaries | DYN-04 | qemu-user has known multi-thread issues that escape unit testing | Manually run `run_qemu_user(arch="arm", sample_sha256=...)` on a non-trivial threaded sample; verify graceful failure or correct trace. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30 s per wave
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
