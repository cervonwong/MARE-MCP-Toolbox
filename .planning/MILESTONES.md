# Milestones — MARE-MCP-Toolbox v2

Historical record of shipped milestones. For current work, see `.planning/ROADMAP.md`.

---

## v1.1 — Remote RE Tool Expansion

**Shipped:** 2026-05-21
**Phases:** 5-14 (10 phases, 48 plans, 70 tasks)
**Timeline:** 2026-05-12 → 2026-05-21 (~9 days, 247 commits)
**Archive:** [v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md) · [v1.1-REQUIREMENTS.md](milestones/v1.1-REQUIREMENTS.md) · [v1.1-MILESTONE-AUDIT.md](milestones/v1.1-MILESTONE-AUDIT.md)

**Delivered:** Remote agents (Claude Code on host, mastra.ai) reach feature-parity with a human analyst at a Kali prompt — a constrained `run_shell`, 11 typed static wrappers, session-scoped r2/gdb, a background job system, an extraction tier, and an env-gated dynamic mode, all through MCP with logging, timeouts, output caps, artifact capture, and case-dir confinement. Tool surface grows 22 → 54 (baseline) / 61 (dynamic mode).

**Key accomplishments:**

1. **F-1 image-hash fix (Phase 5)** — `run_docker.sh` content-hash now covers `mcp-gateway/`, made locale-stable via `LC_ALL=C sort`, extracted to `scripts/compute_image_hash.sh` with hermetic pytest regression (`mcp-gateway/tests/test_image_hash.py`). Closes the 2026-05-11 UAT trap where gateway edits never reached the running container.
2. **`ReToolRunner` chokepoint + `artifacts_io` LEAF (Phase 6)** — Single argv-only subprocess execution path: `start_new_session=True`, hard timeout with process-group `SIGKILL`, `CancelledError` propagation, head-truncated stdout/stderr with full auto-capture to `case_dir/tool-logs/<timestamp>-<slug>.txt`, 100 MB urandom OOM-bounded; canonical `confine_to` helper rejects NUL-byte + traversal + symlink-escape.
3. **`run_shell` + 11 typed static wrappers + `re_artifacts` (Phase 7)** — Constrained bash one-liner via dedicated `mare-shell` UID with env-var whitelist (excludes `MCP_GATEWAY_TOKEN` and credentials); `run_file`/`run_die`/`run_xxd`/`run_readelf`/`run_objdump`/`run_nm`/`run_rabin2`/`run_capstone_disasm`/`run_ropper`/`run_jq`/`run_yq` with typed JSON; `write_artifact`/`append_artifact`/`list_artifacts`/`get_artifact_tree`/`get_tool_log`; MCP Resources at `mare://cases/<case>/tool-logs/<file>`; tool-name collision hard-fail at startup.
4. **Session-scoped r2 (Phase 8)** — `SessionRegistry` primitive (cap 4, idle reaper 600 s, `_DANGEROUS_R2_CMD_RE` denylist, lifespan teardown via `os.killpg`); 4 MCP tools (`open_r2_session`, `r2_cmd`, `close_r2_session`, `list_r2_sessions`) with SESS-05 disclaimer spliced into every docstring.
5. **Background job system (Phase 9)** — `BackgroundJobRegistry` (FIFO eviction, `MARE_JOB_KILLED_LOG_CAP` marker, `killpg(SIGKILL)` cancellation grace, 25-key snapshot) + 4 MCP tools (`start_tool_job`/`get_tool_job`/`cancel_tool_job`/`list_tool_jobs`) with D-15 four-shape error contract — tools never raise across the MCP boundary, even on missing/invalid kwargs.
6. **Extraction tier (Phase 10)** — `extraction.py` primitive (extraction-dir minting `extracted/<engine>-<UTC>Z-<rand4>/`, `_mare_meta.json` sidecar, recursive symlink quarantine with `.symlink-target.txt` sentinel, atomic re-upload with sha256, archive-bomb monitor + `MAX_EXTRACT_MB=4096` cap) + 7 MCP tools (`run_binwalk` signatures/entropy/extract on binwalk3, `run_unblob`, `run_upx_test`/`list`/`unpack`, `list_extracted_files`, `promote_extracted_sample`). Dockerfile migrated to binwalk3 (v2 EOL 2025-12-12).
7. **Dynamic Lab Mode env-gated (Phase 11)** — `sessions/` package refactor (BaseSession + kind-aware SessionRegistry); `dynamic.py` LEAF with capability probes (ptrace_scope/binfmt_misc/qemu arches/netns), per-call `unshare --net --ipc --uts` wrapping, argv profiles for strace/ltrace/qemu_user, follow-fork stray reaper via `/proc/<pid>/task/*/children`; `sessions/gdb.py` gdb-MI3 driver (49-prefix allowlist + 15-vector deny regex blocking `python`/`pi`/`source`/`shell`/`!`); 7 `@mcp.tool()` handlers registered iff `MCP_GATEWAY_DYNAMIC_TOOLS=1` (tool count 54 off / 61 on); `./run_docker.sh --dynamic` operator entry point.
8. **Orchestrator skill v1.1 update (Phase 12)** — `malware-analysis-orchestrator` SKILL.md rewritten for IDA-first backend priority (correcting v1.0 BN-first drift), 7 workflow files at `references/workflows/W-1..W-7-*.md` mapping findings → tools; dual-mode operation preserved (gateway vs scripts); `update_state.py --probe-dynamic` flag + `populate_dynamic_caps` mode-aware probe; 52-test regression suite GREEN with SKILL.md sha256 baseline.
9. **Hardening: atomic caps + r2 sandbox (Phase 13)** — `asyncio.BoundedSemaphore` replaces TOCTOU `count >= max` on both `SessionRegistry` (r2 + gdb combined cap) and `BackgroundJobRegistry` (single release sink in `_mark_terminal` across 7 terminal-state paths); r2 sessions latch `e cfg.sandbox=true` via post-spawn stdin batch (hot-fix `d696a72` after Plan 13-03 argv approach was found to set sandbox AFTER binary autoload); `_DANGEROUS_R2_CMD_RE` reframed as defence-in-depth marker — security boundary lives on `cfg.sandbox`; env-gated `open_r2_session_unsafe` opt-in (`MCP_GATEWAY_R2_UNSAFE_ALLOWED=1`) with WARN-level audit logging.
10. **Phase 14 milestone gap closure** — Surgical fixes for test-order regressions (`r2_sessions` module-attribute catch, `sessions/__init__` package re-bind, ACL test container-only skipif); REQUIREMENTS.md sync (14 checkbox flips + 14 traceability-row updates); ROADMAP progress table + STATE.md body + 4 VALIDATION.md `nyquist_compliant: true` flips; 15 live UAT items captured in rebuilt container `kali-re-tools:0ac0f3e3ebbf` across phases 7/8/10/11/13; `/gsd-audit-milestone v1.1` re-run returned `status: passed`.

### Tech Debt Carried to v1.2

Logged in `.planning/phases/14-close-v1.1-gaps/deferred-items.md`:

- 47 REQUIREMENTS.md traceability rows still show `TBD | Pending` in the `Plan | Verified` columns despite body checkbox + VERIFICATION.md being correct (pure bookkeeping)
- 4 phase VERIFICATION.md frontmatters still labelled `human_needed` (07/08/10/11) — closure evidence is in-document under `## Live UAT Results (Phase 14 closure)`
- `test_r2_sessions.py` conftest monkey-patch bypass (12 collection errors in-container; production code unaffected)
- `test_skill_md_dual_mode.py` `StopIteration` in-container (host-only by intent)
- MCP `r2_cmd` 30 s session-pipe timeout on freshly-opened sessions (direct r2 invocation works; not a security-boundary issue)
- `tests/e2e/test_mastra_starter.py` `ERR_MODULE_NOT_FOUND` on tsx 4.21.0 + Node.js v25 wrapper-script resolution skew (pin tsx ≥4.22 or pin Node 20)

### Stats

- Phases: 10 (Plans: 48, all SUMMARY.md complete)
- Commits: 247
- Diff: +87,625 / -20,413 lines across 402 files (planning artifacts inclusive)
- Tool surface: 22 (v1.0) → 54 baseline / 61 with dynamic mode
- Requirements: 61/61 satisfied across FOUND/SHELL/STATIC/ARTIF/SESS/JOBS/EXTR/DYN/SKILL/HARDEN/SESS-CAP/JOBS-CAP families
- Audit: `/gsd-audit-milestone v1.1` → `status: passed`, `gaps: []`

---

## v1.0 — Remote MCP Foundation

**Shipped:** 2026-04-27
**Phases:** 1-4 (16 plans)
**Timeline:** 2026-03-18 → 2026-04-27 (~40 days, 151 commits)
**Archive:** [v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md) · [v1.0-REQUIREMENTS.md](milestones/v1.0-REQUIREMENTS.md)

**Delivered:** IDA Pro as a third disassembler backend plus a remote MCP gateway that exposes the container's analysis tools to Claude Code and mastra.ai over Streamable HTTP — without changing the existing in-container agent workflow.

**Key accomplishments:**
1. IDA Pro headless backend with multi-stage Docker build (license never in image layers), `idalib-mcp` SSE transport, and `configure-agent-mcp.sh` IDA > BN > Ghidra fallback chain
2. Custom FastMCP gateway: 22 curated tools over Streamable HTTP at `/mcp`, bearer-token auth + Origin DNS-rebind middleware, path-traversal and argv-only subprocess mitigations
3. `PinnedBackend` async ClientSession routing disassembler tools to IDA (HTTP) or BN/Ghidra (stdio subprocess), with `asyncio.Lock` serialization and native-name pass-through (`get_active_backend()` for discovery)
4. Streaming `POST /upload` with sha256 content-addressing, 1 GB cap, and rejected path-traversal/multipart content (10 unit + 4 integration tests)
5. Dual-mode container: `./run_docker.sh` (v1-identical local) vs `./run_docker.sh --remote` (detached gateway) from one image; `MCP_GATEWAY_ENABLED` Dockerfile guard makes local-mode byte-identical
6. External client templates: Claude Code `.mcp.json` with `${MARE_GATEWAY_TOKEN}` expansion, mastra.ai starter at `templates/mastra/` using `@mastra/mcp ~1.3.1`, and MCP Resources at `mare://cases/<case>/<artifact>` covering all 13 artifact types

### UAT

**CLI-01 manual UAT: PASSED 2026-05-11** (signed administrator@leongs-house.dev). All 8 sections of `.planning/phases/04-external-client-integration/04-UAT.md` checked, driven via `claude --mcp-config --strict-mcp-config` against the running container — config discovery, env-var expansion, `mcp list` health check, `list_uploads` + `get_active_backend` tool calls, `resources/list` (13 URIs), `resources/read` of CURRENT_STATE.json, wrong-token negative test, cleanup.

### Findings Carried to v1.1

- **F-1 — Image content-hash misses `mcp-gateway/` changes.** `run_docker.sh:209-222` does not include `mcp-gateway/src/` in the `DOCKERFILE_SHA` checksum, so gateway-package edits never trigger an image rebuild. Caught during 2026-05-11 UAT: Plan 04-03's `tools/resources.py` was in repo + tests but not in the 04-27 image, so `resources/list` returned empty until the image was force-rebuilt. Fix: extend the hash to include `mcp-gateway/`. (Resolved in v1.1 Phase 5.)

### Stats

- Phases: 4 (Plans: 16, all SUMMARY.md complete)
- Commits: 151
- LOC delta: +49,754 / -2,712 (across all repo files)
- Verification: Phase 1 ✓, Phase 2 ✓, Phase 3 ✓, Phase 4 ✓ automated + ✓ human UAT (2026-05-11)
