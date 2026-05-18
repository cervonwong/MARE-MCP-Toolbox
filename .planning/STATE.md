---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Remote RE Tool Expansion
status: verifying
stopped_at: Phase 8 context gathered
last_updated: "2026-05-18T03:13:47.101Z"
last_activity: 2026-05-13
progress:
  total_phases: 8
  completed_phases: 3
  total_plans: 14
  completed_plans: 14
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-12 — v1.1 Remote RE Tool Expansion scoped)

**Core value:** Automated malware triage and deep analysis via AI agents with full access to professional RE tooling — accessible both from inside the container and from external MCP clients.
**Current focus:** Phase 07 — run-shell-typed-static-wrappers-re-artifacts

## Current Position

Milestone: v1.1 Remote RE Tool Expansion
Phase: 07 (run-shell-typed-static-wrappers-re-artifacts) — EXECUTING
Plan: 8 of 8
Status: Phase complete — ready for verification
Last activity: 2026-05-13

Progress: [          ] 0% (0/8 phases complete)

## Performance Metrics

**Velocity:**

- Total plans completed (v1.0): 16
- v1.1 plans completed: 0

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

**v1.1 design decisions (newly added):**

- Expose a constrained `run_shell` over MCP — safety from cwd-confinement + timeout + output cap + auto-capture, not argv allowlisting
- Typed wrappers exist for discoverability and structured output (capstone JSON, ropper bounds, r2/gdb sessions), not as the exclusive surface
- Session-scoped r2 and gdb — iterative analyst workflow needs shared analysis state
- Dynamic mode env-gated default-off (`MCP_GATEWAY_DYNAMIC_TOOLS=1`, surfaced via `./run_docker.sh --dynamic`)
- Composite `investigate_*` MCP tools dropped — orchestrator skill is the composer

**v1.1 roadmap decisions (2026-05-12):**

- Adopted research-consensus 8-phase structure (Phases 5-12) verbatim — all 4 research streams converged on this ordering
- Phase 5 (F-1) lands first to unblock every subsequent gateway edit (UAT failure mode 2026-05-11)
- `ReToolRunner` (Phase 6) precedes all consumers; chokepoint primitive validated under wrappers (Phase 7) before sessions/jobs build on it
- Sessions (Phase 8) before Jobs (Phase 9) — same lifespan-registry pattern, r2 validates plumbing at lower complexity than gdb
- Extraction (Phase 10) depends on Jobs (unblob on multi-GB firmware exceeds 60 s MCP cap)
- Dynamic Mode (Phase 11) last among code phases — reuses session plumbing for gdb and job system for long traces
- Orchestrator Skill Update (Phase 12) very last — references all primitives

**Carryover from v1.0:**

- F-1: `run_docker.sh:209-222` `DOCKERFILE_SHA` does not include `mcp-gateway/src/` — gateway-package edits never trigger image rebuild. Now scoped as Phase 5 (FOUND-01).
- [Phase 05-f-1-image-hash-fix]: Inline LC_ALL=C prefix per sort invocation in run_docker.sh image-hash subshell (vs. global export) — keeps locale intent visible at call site
- [Phase 05-f-1-image-hash-fix]: Extracted run_docker.sh:212-229 inline image-hash subshell to scripts/compute_image_hash.sh; refactor preserves byte-identical output and keeps DOCKERFILE_SHA/SHORT_SHA/HASH_IMAGE in run_docker.sh scope (D-01/D-06).
- [Phase 05-f-1-image-hash-fix]: Locked FOUND-01 invariant with hermetic 11-node pytest at mcp-gateway/tests/test_image_hash.py — single-fixture-per-test pattern; explicit env={PATH,HOME} dict to subprocess (no env=os.environ); test skeleton copied verbatim from 05-RESEARCH.md to preserve VALIDATION.md's row-by-row contract.
- [Phase 06-retoolrunner-artifacts-io-foundation]: Wave-0 RED-state test scaffolding pattern -- name failing test functions referencing not-yet-existing modules; Wave 1/2 turn them GREEN. Enforces Nyquist: every <verify> in downstream plans references an existing test.
- [Phase 06-retoolrunner-artifacts-io-foundation]: Threat-register-as-tests -- every <threat_model> row with disposition=mitigate (T-6-01/02/03/06/07) has at least one named test function rather than being prose-only mitigations.
- [Phase 06-retoolrunner-artifacts-io-foundation]: Leaf-module discipline (D-07) enforced for artifacts_io.py -- stdlib-only imports keep the module safe to import from any Phase 7+ tool wrapper without cycles
- [Phase 06-retoolrunner-artifacts-io-foundation]: Paste-ready code from 06-02-PLAN.md <action> block used verbatim -- TDD GREEN-phase executed with zero deviation; all 16 RED tests flipped GREEN on first run
- [Phase 06-retoolrunner-artifacts-io-foundation]: ReToolRunner spawned via asyncio.create_subprocess_exec with start_new_session=True; on TimeoutError swallows + returns {timed_out=True, exit_code=-9}; on CancelledError runs killpg+shielded wait then re-raises (D-04, D-17, Pitfall 18)
- [Phase 06-retoolrunner-artifacts-io-foundation]: Stdout/stderr drained concurrently via asyncio.gather of two _drain coros with head_cap_bytes + raw file sink; on timeout, drain results become zero placeholders but on-disk log preserves what flushed (FOUND-02 SC-4, Pitfall 1)
- [Phase 06-retoolrunner-artifacts-io-foundation]: D-03 12-key return shape locked: exit_code, timed_out, duration_s, stdout_head, stdout_truncated, stdout_bytes_total, stderr_head, stderr_truncated, stderr_bytes_total, log_path, argv, slug -- exact order, never renamed by Phase 7+ consumers
- [Phase 06-retoolrunner-artifacts-io-foundation]: Grep-the-source chokepoint tests catch BOTH code AND prose violations; future plans must phrase 'never shell-invocation kwarg' (not 'never shell=True') in docstrings to avoid spurious test failures from copy-pasted action blocks
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Wave 0 fixture binaries built via documented fallback paths (gcc inline asm for ELF; hand-crafted 408-byte PE stub; gcc -c for stripped.o) because executor host lacked nasm/mingw-w64/setfacl; all pass magic-byte + size acceptance; README documents both canonical and fallback build paths.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Wave 0 RED-stub discipline locked in for Phase 7: 52 tests collected cleanly, each imports the not-yet-existing Phase 7 module at function top so collection passes but execution ImportErrors -- pytest.skip is forbidden; failure-to-import IS the RED state Wave 1/2 will flip to GREEN.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Dockerfile permission/ACL revocations split into build-time best-effort + entrypoint re-apply (overlayfs xattr-drop mitigation per Pitfall 3 / moby#40553); token-file chmod 0400 placed AFTER the MCP_GATEWAY_ENABLED block with a 0.2s x 5 retry loop since the bearer token is generated only when the gateway starts.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-02: ensure_mare_shell_access LEAF extension landed via zero-deviation TDD (RED commit + GREEN commit, 80s total); shutil+subprocess added to artifacts_io.py stdlib-only import block (LEAF discipline preserved, grep 'from mcp_gateway' = 0); fail-loud RuntimeError on missing setfacl OR nonzero exit; mock-based unit tests cover contract on hosts without setfacl (executor host case).
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-03: collision_check.py module (~67 LoC) delivered with verbatim plan code; Wave 0 RED-stub test fixtures retargeted from Phase 7 Wave 2 names (run_xxd/run_file/run_die, not yet registered) to v1.0 gateway-native names (init_case/get_artifact/decompile) so tests are self-contained against Wave 1 surface — collision-detection mechanism unchanged, more faithful to D-12 scope.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-04: tools/resources.py depth-2 walk delivered with paste-ready plan code + one deviation: added _status_root() helper that reads MCP_GATEWAY_STATUS_DIR dynamically per call (the module-level STATUS_ROOT import is preserved as no-env fallback). This honours the existing 'dynamic' listing docstring promise and unblocks test_resources_no_depth_3 + test_resources_skip_hidden which would otherwise see stale STATUS_ROOT when test_resources_unit.py is collected first.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-05: re_artifacts.py (335 LoC) delivered with 3 Rule-3 deviations: (a) module-level coroutines over nested-in-register so tests can import directly; (b) skip-on-no-setfacl helper for 6 ACL-exercising tests (host lacks setfacl); (c) autouse samples.STATUS_ROOT monkeypatch fixture (binding-at-import issue). 9 pass + 6 skip on host; container will flip all 6 to PASS.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-06: tools/re_static.py (491 LoC) delivered with 3 Rule-3 deviations: (a) module-level coroutines + register-wrapper pattern (matches Plan 07-05) so tests import wrappers directly; (b) autouse _sync_samples_roots fixture monkeypatches samples.STATUS_ROOT + EXAMPLES_ROOT + ALLOWED_PREFIXES per test; (c) _require_tool_or_skip guards for die/rabin2/jq/yq (host-missing). 10 pass + 4 skip on host; container will flip all 4 to PASS.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-07: tools/shell.py (211 LoC) delivered with 6 Rule-3 deviations: (a) module-level run_shell + register-wraps pattern (matches 07-05/07-06); (b) autouse samples.STATUS_ROOT monkeypatch fixture; (c) 8 spawning tests gated by _require_setfacl_or_skip; (d) test_mare_shell_user_exists fail->skip (host lacks user, Dockerfile creates it); (e) @mcp.tool() decorator -> mcp.tool()(run_shell) call; (f) assert -> RuntimeError in _build_shell_env drift check. 5 pass + 9 skip + 1 slow-deselect on host.
- [Phase 07-run-shell-typed-static-wrappers-re-artifacts]: Plan 07-08: Wave 3 integration — register_all_tools learns shell/re_static/re_artifacts (D-16); collision_check imported but not registered; assert_no_collisions called on BOTH lifespan paths AFTER backend connect AND BEFORE serving (D-11 ordering, Pitfall 7); backend_passthrough docstring rewritten to reflect D-14 (hard-fail REVERSES v1.0 backend-wins); GW-02 tool-count invariant bumped 15-25 -> 35-50 in test_tool_list.py with explicit D-16 rationale (Rule 1 deviation); final surface = 39 tools (22 v1.0 + 17 Phase 7).

### Pending Todos

- Plan Phase 5 (F-1 Image-Hash Fix) via `/gsd-plan-phase 5`
- Resolve open decisions flagged in research/SUMMARY.md during phase planning:
  - Phase 7: `run_shell` env whitelist contents, `mare-shell` UID primary group ACL on existing case-dirs
  - Phase 8: session resource caps (default 30 min idle, cap 8 sessions per consensus)
  - Phase 9: job log retention/rotation policy
  - Phase 11: per-call netns mechanism, ptrace probe error UX, gdb MI3 command allowlist, binfmt detection helper
- Research flag: `/gsd-research-phase 11` recommended before planning Dynamic Lab Mode (6 distinct pitfalls cluster in that phase)

### Blockers/Concerns

- F-1 (Phase 5) must land before substantive gateway edits, otherwise every subsequent phase hits the "edited gateway, container still has old code" trap that burned 2026-05-11 UAT
- Security boundary needs explicit documentation in v1.1 README: shell is real but cwd-confined to case_dir, no network unless dynamic mode + opt-in, every invocation captured
- Dynamic mode UX surface (`./run_docker.sh --dynamic` ergonomics, env var documentation, mode visibility in `CURRENT_STATE.json`) needs design during Phase 11 planning, not just implementation
- Mount-namespace isolation for `run_shell` deferred to v1.2 (would require CAP_SYS_ADMIN); v1.1 posture-only confinement documented as known limitation

### Quick Tasks Completed (v1.0 era)

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260414-el8 | Refactor: create workspace/ directory, move skills to native .claude/.codex locations, update mount config and README | 2026-04-14 | dfa6cdb | [260414-el8-refactor-create-workspace-directory-move](./quick/260414-el8-refactor-create-workspace-directory-move/) |
| 260414-fsg | Replace docker-bin wrappers with native config files for Claude and Codex | 2026-04-14 | 3b3c981 | [260414-fsg-replace-docker-bin-wrappers-with-native-](./quick/260414-fsg-replace-docker-bin-wrappers-with-native-/) |
| 260414-iee | Move Claude/Codex config from workspace project-level to user-level via configure-agent-mcp.sh | 2026-04-14 | a89af30 | [260414-iee-move-claude-codex-config-from-workspace-](./quick/260414-iee-move-claude-codex-config-from-workspace-/) |
| 260423-f3k | Fix inner agent statusline paths (/workspace -> /agent) | 2026-04-23 | bdae5ea | [260423-f3k-fix-inner-agent-statusline-paths-workspa](./quick/260423-f3k-fix-inner-agent-statusline-paths-workspa/) |
| 260511-cwf | Fix remote MCP security defaults: localhost host bind, exact Origin validation, and case_dir confinement | 2026-05-11 | f556fda | [260511-cwf-fix-remote-mcp-security-defaults-localho](./quick/260511-cwf-fix-remote-mcp-security-defaults-localho/) |
| 260511-evu | Make the Mastra starter provide a browser GUI in addition to the existing CLI, and verify by opening the GUI | 2026-05-11 | uncommitted | [260511-evu-make-the-mastra-starter-provide-a-browse](./quick/260511-evu-make-the-mastra-starter-provide-a-browse/) |
| 260511-fam | Switch the Mastra starter GUI to the default Mastra Studio dashboard with a registered MARE agent and tools | 2026-05-11 | uncommitted | [260511-fam-switch-the-mastra-starter-gui-to-the-def](./quick/260511-fam-switch-the-mastra-starter-gui-to-the-def/) |
| Phase 05-f-1-image-hash-fix P01 | 2min | 1 tasks | 1 files |
| Phase 05-f-1-image-hash-fix P02 | 100s | 2 tasks | 2 files |
| Phase 05-f-1-image-hash-fix P03 | 87s | 1 tasks | 1 files |
| Phase 06-retoolrunner-artifacts-io-foundation P01 | 3min | 3 tasks | 3 files |
| Phase 06-retoolrunner-artifacts-io-foundation P02 | 4min | 1 tasks | 1 files |
| Phase 06-retoolrunner-artifacts-io-foundation P03 | 3min | 1 tasks | 1 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P01 | 5min | 3 tasks | 15 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P02 | 80s | 1 tasks | 2 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P03 | 12min | 1 tasks | 2 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P04 | 3min | 1 tasks | 1 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P05 | 4min | 1 tasks | 2 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P06 | 4min | 1 tasks | 2 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P07 | 3min | 1 tasks | 2 files |
| Phase 07-run-shell-typed-static-wrappers-re-artifacts P08 | 4min | 2 tasks | 6 files |

## Session Continuity

Last session: 2026-05-18T03:13:47.097Z
Stopped at: Phase 8 context gathered
Resume file: .planning/phases/08-session-scoped-r2/08-CONTEXT.md
