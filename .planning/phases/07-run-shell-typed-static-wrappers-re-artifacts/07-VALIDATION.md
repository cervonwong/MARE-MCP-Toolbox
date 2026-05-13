---
phase: 7
slug: run-shell-typed-static-wrappers-re-artifacts
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-13
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `07-RESEARCH.md` §"Validation Architecture". Planner fills in the per-task map; executor maintains status column.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (existing — `mcp-gateway/pyproject.toml`) |
| **Config file** | `mcp-gateway/pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd mcp-gateway && uv run pytest -x -q --ignore=tests/test_runner_slow.py -m "not slow"` |
| **Full suite command** | `cd mcp-gateway && uv run pytest -q` |
| **Estimated runtime** | quick ~30s, full ~5–10 min (with D-35 slow test) |

---

## Sampling Rate

- **After every task commit:** Run quick command (≤30s)
- **After every plan wave:** Run full suite (slow included)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds (quick); 10 minutes (full)

---

## Per-Task Verification Map

Planner populates this table from PLAN.md tasks. Each row maps a task → requirement → test command. The executor updates Status as tasks land.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _TBD by planner_ | | | | | | | | | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Per RESEARCH §Validation Architecture, Wave 0 MUST create RED-stub test files and fixtures BEFORE any implementation lands:

- [ ] `mcp-gateway/tests/fixtures/` directory + 3 small public-domain binaries (D-34): tiny ELF, tiny PE, stripped object — total <200 KB; regeneration source committed alongside
- [ ] `mcp-gateway/tests/test_acl_available.py` — RED stub for `shutil.which("setfacl") is not None`
- [ ] `mcp-gateway/tests/test_run_shell.py` — RED stubs for env scrub (D-09/D-10), UID assertion (D-08), token inaccessibility (D-08), cwd confinement, NUL/empty/oversize cmd rejection (D-29), ANSI strip parity, timeout/output-cap parity (D-35 marked `slow`)
- [ ] `mcp-gateway/tests/test_re_static.py` — RED stubs for each of the 11 wrappers (D-18 happy paths + allowlist-violation tests for readelf/objdump/nm/rabin2)
- [ ] `mcp-gateway/tests/test_re_artifacts.py` — RED stubs for `write_artifact` text/binary/overwrite=False, `append_artifact`, `list_artifacts`, `get_artifact_tree` cap behavior, `get_tool_log` paged-read with `next_offset` (D-21..D-25)
- [ ] `mcp-gateway/tests/test_collision_check.py` — RED stubs for empty backend, single-collision, multi-collision deterministic ordering, stub-backend monkeypatch (D-15)
- [ ] `mcp-gateway/tests/test_resources.py` — RED stubs (or extension to existing) for depth-2 walk over `EXPANDED_CASE_SUBDIRS`, cap enforcement, hidden-file skip, depth-3 NOT exposed (D-26/D-27)
- [ ] Pin pytest markers (`slow`) in `pyproject.toml` if not already present

After Wave 0: every test fails for the right reason ("module not found" / "attribute missing"), not for a missing fixture or syntax error.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dockerfile rebuild produces `mare-shell` UID=700 and ACL revocations survive | SHELL-01, SHELL-02 | Requires `docker build` + `docker run` round-trip; not unit-testable inside pytest | `docker compose build && docker compose run --rm gateway-agent id mare-shell` (expect uid=700); `docker compose run --rm gateway-agent stat -c '%a' /agent/.mcp-gateway-token` (expect 400) |
| MCP Resources actually visible to a remote client | ARTIF-04 | Requires live MCP client roundtrip (Claude Code or mastra) | After phase ships: connect Claude Code via `.mcp.json`, issue `resources/list`, confirm `mare://cases/<case>/tool-logs/<f>` URIs appear |
| Gateway exits with code 78 on simulated collision | — (SC-6 supporting) | exit-code propagation through Starlette is environment-sensitive | `MCP_GATEWAY_FAKE_BACKEND_COLLISIONS=run_xxd uv run python -m mcp_gateway.app; echo $?` (expect 78) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s for quick; <10 min for full
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
