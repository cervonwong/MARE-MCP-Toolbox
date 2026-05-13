# Requirements — Milestone v1.1 Remote RE Tool Expansion

**Goal:** Give remote agents (Claude Code on host, mastra.ai) feature parity with what a human analyst does at a Kali prompt — through MCP, with logging, timeouts, output caps, artifact capture, and case-dir confinement.

**Scope note:** v1.0 (Remote MCP Foundation) is shipped and validated. v1.1 is purely additive: a new chokepoint runner, a constrained shell, typed RE-tool wrappers, session-scoped r2/gdb, an extraction tier, an env-gated dynamic mode, a background job system, and an orchestrator-skill rewrite. v1.0 requirements (GW-*, DIS-*, CLI-*) are not re-validated.

---

## v1.1 Requirements

### Foundation (FOUND)

- [x] **FOUND-01**: Agent edits to `mcp-gateway/src/` trigger a Docker image rebuild on the next `./run_docker.sh` invocation (F-1 carryover fix — content-hash includes gateway source)
- [x] **FOUND-02**: Every new v1.1 subprocess invocation goes through a single `ReToolRunner` that enforces argv-only execution, cwd-confinement to `case_dir`, hard timeout, process-group SIGKILL on timeout/cancel, and a structured JSON result shape with `exit_code`, `stdout_head`, `stderr_head`, `log_path`, `timed_out`, and byte/truncation counts
- [x] **FOUND-03**: Runner-driven tools auto-capture full stdout/stderr to `case_dir/tool-logs/<timestamp>-<slug>.txt` while returning only a head-truncated preview in the MCP response (mitigates 25k-token MCP response cap)
- [x] **FOUND-04**: A canonical `confine_to(case_dir, path)` helper exists and is used by every path-accepting tool in v1.1 to reject path traversal

### Constrained Shell (SHELL)

- [ ] **SHELL-01**: Agent can execute a bash one-liner via `run_shell(case_dir, cmd)` with cwd pinned to the case directory, output auto-captured, output cap enforced, hard timeout enforced
- [ ] **SHELL-02**: `run_shell` executes as a dedicated non-root `mare-shell` UID with an env-var whitelist that excludes `MCP_GATEWAY_TOKEN`, API keys, and AWS-style credentials
- [ ] **SHELL-03**: `run_shell` docstring explicitly documents that confinement is structural posture (cwd + UID + timeout + capture), not OS-level isolation, so agents and operators know what `run_shell` is and is not

### Typed Static Wrappers (STATIC)

- [ ] **STATIC-01**: Agent can identify a sample with `run_file(case_dir, sample)` returning libmagic output
- [ ] **STATIC-02**: Agent can detect packers/protectors with `run_die(case_dir, sample)` returning DIE JSON
- [ ] **STATIC-03**: Agent can read a bounded hex window with `run_xxd(case_dir, sample, offset, length)` returning the slice (capped) and full output saved to `case_dir/hex/`
- [ ] **STATIC-04**: Agent can inspect ELF metadata with `run_readelf(case_dir, sample, sections)` (allowlisted section flags)
- [ ] **STATIC-05**: Agent can disassemble or list symbols with `run_objdump(case_dir, sample, mode)` and `run_nm(case_dir, sample, mode)` returning structured output
- [ ] **STATIC-06**: Agent can run bounded rabin2 queries with `run_rabin2(case_dir, sample, command)` (JSON-first via `-j`)
- [ ] **STATIC-07**: Agent can disassemble byte ranges with `run_capstone_disasm(arch, mode, bytes_hex, base_addr)` returning typed `CsInsn`-shaped JSON
- [ ] **STATIC-08**: Agent can search for ROP gadgets with `run_ropper(case_dir, sample, arch, filter, badbytes)` returning typed `Gadget` JSON; full gadget list written to `case_dir/rop/`
- [ ] **STATIC-09**: Agent can run jq/yq over case artifacts via `run_jq(case_dir, artifact_path, expr)` and `run_yq(case_dir, artifact_path, expr)`
- [ ] **STATIC-10**: All STATIC wrappers reject tool-name collisions with backend-pass-through tools at startup (hard-fail rather than silent override)

### Artifact Tree & Control Helpers (ARTIF)

- [ ] **ARTIF-01**: Each case directory supports lazily-created subdirs: `tool-logs/`, `extracted/`, `hex/`, `rop/`, `dynamic/`, `qemu/`, `disassembly/`, `decompilation/`, `xrefs/`
- [ ] **ARTIF-02**: Agent can write/append artifacts via `write_artifact(case_dir, relpath, content)` and `append_artifact(case_dir, relpath, content)`, with `confine_to` enforced
- [ ] **ARTIF-03**: Agent can enumerate artifacts via `list_artifacts(case_dir, subdir)` and `get_artifact_tree(case_dir)`
- [ ] **ARTIF-04**: Agent can range-read large tool logs via `get_tool_log(case_dir, log_name, offset, length)` so multi-megabyte logs don't blow the MCP response cap
- [x] **ARTIF-05**: MCP Resources expose `mare://cases/<case>/tool-logs/<file>` for every captured log (consistent with v1.0 Resource scheme)

### Session-Scoped r2 (SESS)

- [ ] **SESS-01**: Agent can open a persistent r2 analysis session via `open_r2_session(case_dir, sample, init_commands)`, receive an opaque session_id, and reuse r2's analysis state (e.g., results of `aaa`) across subsequent calls
- [ ] **SESS-02**: Agent can execute arbitrary r2 commands in an open session via `r2_cmd(session_id, cmd, format)` with output head-truncated + full output captured
- [ ] **SESS-03**: Agent can close a session via `close_r2_session(session_id)` and enumerate active sessions via `list_sessions()`
- [ ] **SESS-04**: r2 sessions are auto-reaped after configurable idle (default 30 min) and a session cap (default 8) is enforced; sessions surviving gateway shutdown are killed (no zombies)
- [ ] **SESS-05**: Sessions are shared across all MCP clients with the same bearer token (single-tenant by design); this limitation is documented in tool docstrings (per-`Mcp-Session-Id` keying deferred to v1.2)
- [ ] **SESS-06**: r2 sessions refuse dangerous shell-escape commands (`#!`, `R!`, `!`) at the wrapper layer; r2 init runs with `scr.interactive=false; scr.color=0`

### Extraction Tier (EXTR)

- [ ] **EXTR-01**: Agent can run binwalk for signatures and entropy via `run_binwalk(case_dir, sample, mode)` where mode covers signatures-only, entropy, and extract; extraction output confined to `case_dir/extracted/binwalk-<ts>/`
- [ ] **EXTR-02**: Agent can run unblob with structured `--report` JSON via `run_unblob(case_dir, sample)`; output confined to `case_dir/extracted/unblob-<ts>/`
- [ ] **EXTR-03**: Agent can test/list/unpack UPX-packed samples via `run_upx_test`, `run_upx_list`, `run_upx_unpack`; unpacked output confined to `case_dir/extracted/upx-<ts>/`
- [ ] **EXTR-04**: Agent can enumerate previously-extracted files via `list_extracted_files(case_dir)` (engine-agnostic)
- [ ] **EXTR-05**: Agent can promote an extracted child file to a first-class new case via `promote_extracted_sample(parent_case_dir, child_path)`, which re-uploads with sha256 content-addressing, initializes a new case directory, and returns the new case_dir
- [ ] **EXTR-06**: Extraction tools enforce: symlink quarantine (symlinks become `.symlink-target.txt` files), archive-bomb cap (`MCP_GATEWAY_MAX_EXTRACT_MB` default 4 GB), and atomic promotion (sha256 recomputed)

### Background Job System (JOBS)

- [ ] **JOBS-01**: Agent can start a long-running tool as a background job via `start_tool_job(tool, args)` and receive an opaque job_id; the job runs through `ReToolRunner` with the same safety properties
- [ ] **JOBS-02**: Agent can poll job status via `get_tool_job(job_id)` returning `status`, head-tail of stdout/stderr, exit code if done, and the log artifact path
- [ ] **JOBS-03**: Agent can cancel a job via `cancel_tool_job(job_id)` which SIGTERMs the process group and (after a grace period) SIGKILLs
- [ ] **JOBS-04**: Agent can enumerate active and recently-completed jobs via `list_tool_jobs(state)`; the registry is in-memory only, gateway restart cancels in-flight jobs (documented behavior)
- [ ] **JOBS-05**: Each job's log artifact is capped at `MCP_GATEWAY_MAX_JOB_LOG_MB` (default 256 MB); over-cap jobs are killed and marked `status=killed_log_cap`. Completed jobs are LRU-cleaned to bound memory
- [ ] **JOBS-06**: Jobs survive request cancellation correctly — `CancelledError` propagates to `killpg(SIGKILL)` via `asyncio.shield(proc.wait())`; client disconnect → subprocess dead within 200 ms (test asserts this)
- [ ] **JOBS-07**: Jobs that long-run tools support MCP progress notifications via `Context.report_progress(progress, total, message)` where the tool can produce progress signals (e.g., unblob percent-complete)

### Dynamic Lab Mode (DYN, env-gated default-off)

- [ ] **DYN-01**: Dynamic tools (`run_strace`, `run_ltrace`, `run_qemu_user`, `open_gdb_session`, `gdb_exec`, `close_gdb_session`, `get_dynamic_capabilities`) are registered if and only if `MCP_GATEWAY_DYNAMIC_TOOLS=1` is set at gateway startup. Default-off; `tools/list` does not advertise these tools when off
- [ ] **DYN-02**: Operator can enable dynamic mode end-to-end via `./run_docker.sh --dynamic` which sets the env var, surfaces the mode in `CURRENT_STATE.json`, and applies dynamic-mode defaults (no-net, dedicated cwd under `dynamic/`)
- [ ] **DYN-03**: Agent can run `run_strace(case_dir, sample, profile)` and `run_ltrace(case_dir, sample, profile)` with allowlisted argv profiles (e.g., `file_network_process`, `library_calls`); output to `case_dir/dynamic/`; default no-net via per-call `unshare --net`
- [ ] **DYN-04**: Agent can run `run_qemu_user(case_dir, sample, arch, argv, profile)` for cross-arch user-mode emulation; binfmt drift is detected at startup via `get_dynamic_capabilities()`; output to `case_dir/qemu/`
- [ ] **DYN-05**: Agent can drive an interactive gdb session via `open_gdb_session(case_dir, sample)` → `gdb_exec(session_id, cmd)` → `close_gdb_session(session_id)`, using `gdb --interpreter=mi3`; commands are restricted to an allowlist of MI prefixes (e.g., `info`, `print`, `x`, `disas`, `bt`, `continue`, `break`) to prevent `python <code>` sandbox escape
- [ ] **DYN-06**: `get_dynamic_capabilities()` probes and reports at gateway startup: `ptrace_scope`, `binfmt_misc` registration status, available qemu architectures, netns feasibility; agents and operators can detect missing capabilities and act before sample execution
- [ ] **DYN-07**: Dynamic tools enforce: long-running tools use the JOBS system, output is captured to `case_dir/dynamic/` or `case_dir/qemu/`, sample must be resolved via sha256 from `uploads/` or already inside an existing `case_dir`, follow-fork process groups are reaped (scan `/proc/<runner_pid>/task/*/children` for stragglers)

### Orchestrator Skill Update (SKILL)

- [ ] **SKILL-01**: Updated `workspace/.claude/skills/malware-analysis-orchestrator/` reflects backend priority `IDA > BN > Ghidra` (correcting v1.0 documentation drift)
- [ ] **SKILL-02**: Skill encodes the deep RE checklist mapping findings → tools (W-1 packed-binary triage, W-2 ELF deep-dive, W-3 PE deep-dive, W-4 ROP hunt, W-5 dynamic API trace, W-6 firmware unpack, W-7 cross-arch IoT triage); each maps to v1.1 typed wrappers and `run_shell` fallbacks
- [ ] **SKILL-03**: Skill preserves dual-mode operation: every step has an MCP path (gateway tools) and a local-script path (`scripts/...`), with a decision rule based on `tools/list` content; a regression test snapshots SKILL.md and fails CI on unconditional `mcp__mare__*` references with no fallback
- [ ] **SKILL-04**: Skill marks dynamic mode status in `CURRENT_STATE.json` so subsequent analysis steps know whether dynamic tools are available; dynamic-mode-only steps are skipped (with a noted reason) when the mode is off

---

## Out of Scope (v1.1)

Explicit exclusions, with reasoning. These items were considered and deferred.

- **Mount-namespace isolation for `run_shell`** — would require `CAP_SYS_ADMIN`, broadens the container capability surface. Posture-only confinement (UID + env scrub + cwd + ACL) is the v1.1 boundary; reconsider for v1.2 only if the capability cost becomes acceptable.
- **Per-`Mcp-Session-Id` keying of sessions and jobs** — v1.1 keeps single-session state matching v1.0's `session_state.py` (`GW-V2-03` ticket). Sessions and jobs are shared across all MCP clients with the same bearer token; documented as a known limitation.
- **Background job persistence across gateway restart** — in-memory registry only; restart cancels in-flight jobs by design. Reconsider only if "come back tomorrow" UX becomes important.
- **Per-call `tool-logs/<ts>-<slug>.txt` log rotation** — v1.1 caps per-job logs (mitigates Pitfall 8) but does not rotate per-call captures. Acceptable to let `tool-logs/` grow within the case-dir lifecycle; revisit if cases routinely live >30 days.
- **Composite `investigate_*` MCP tools** (`investigate_packer`, `run_static_deep_dive`, `generate_detection_leads`, etc.) — these are agent prompts dressed as tools; the orchestrator skill is the composer. The gateway exposes primitives only.
- **Argv allowlist for the long tail of Kali utilities** — `run_shell` covers ad-hoc invocations; wrapping every tool would explode the surface without closing the gaps. Wrappers exist only for tools where parsing/validation pays off.
- **Always-on dynamic mode** — widens attack surface; env-gated default-off is the explicit decision.
- **Batch-only gdb** — every interactive analysis becomes a script-generation problem. Session-scoped gdb is the v1.1 model.
- **`run_strings` as a typed v1.1 wrapper** — v1.0's `collect_strings` already covers this; use `run_shell` for ad-hoc strings invocations.
- **Sandboxed-network dynamic** (INetSim/FakeDNS/honeynet integration) — v1.1 ships no-net by default; opt-in `allow_network=true` is v1.2+.
- **Coverage-guided dynamic / fuzzing hooks** — out of scope for v1.1.
- **Volatility / memory snapshot tooling** — out of scope for v1.1.
- **Web UI for case browsing** — already excluded in PROJECT.md.

---

## Future Requirements (deferred to v1.2+)

Captured here so they don't get lost; tracked outside this milestone.

- Per-`Mcp-Session-Id` keying for sessions and jobs (`GW-V2-03`)
- Job persistence across gateway restart
- Mount-namespace isolation for `run_shell` if `CAP_SYS_ADMIN` becomes acceptable
- Per-call `tool-logs/` rotation policy
- Sandboxed-network dynamic mode with INetSim/FakeDNS opt-in
- Convergence of v1.0 `subprocess_runner.run_script` and v1.1 `ReToolRunner` into one runner
- Memory snapshot tooling (Volatility)
- Coverage-guided dynamic / fuzzing hooks

---

## Traceability

Mapping from each v1.1 REQ-ID to its assigned phase. Plan column populated during `/gsd-plan-phase`. Verified column populated at phase verification.

| REQ-ID    | Phase    | Plan | Verified |
|-----------|----------|------|----------|
| FOUND-01  | Phase 5  | TBD  | Pending  |
| FOUND-02  | Phase 6  | TBD  | Pending  |
| FOUND-03  | Phase 6  | TBD  | Pending  |
| FOUND-04  | Phase 6  | TBD  | Pending  |
| SHELL-01  | Phase 7  | TBD  | Pending  |
| SHELL-02  | Phase 7  | TBD  | Pending  |
| SHELL-03  | Phase 7  | TBD  | Pending  |
| STATIC-01 | Phase 7  | TBD  | Pending  |
| STATIC-02 | Phase 7  | TBD  | Pending  |
| STATIC-03 | Phase 7  | TBD  | Pending  |
| STATIC-04 | Phase 7  | TBD  | Pending  |
| STATIC-05 | Phase 7  | TBD  | Pending  |
| STATIC-06 | Phase 7  | TBD  | Pending  |
| STATIC-07 | Phase 7  | TBD  | Pending  |
| STATIC-08 | Phase 7  | TBD  | Pending  |
| STATIC-09 | Phase 7  | TBD  | Pending  |
| STATIC-10 | Phase 7  | TBD  | Pending  |
| ARTIF-01  | Phase 7  | TBD  | Pending  |
| ARTIF-02  | Phase 7  | TBD  | Pending  |
| ARTIF-03  | Phase 7  | TBD  | Pending  |
| ARTIF-04  | Phase 7  | TBD  | Pending  |
| ARTIF-05  | Phase 7  | TBD  | Pending  |
| SESS-01   | Phase 8  | TBD  | Pending  |
| SESS-02   | Phase 8  | TBD  | Pending  |
| SESS-03   | Phase 8  | TBD  | Pending  |
| SESS-04   | Phase 8  | TBD  | Pending  |
| SESS-05   | Phase 8  | TBD  | Pending  |
| SESS-06   | Phase 8  | TBD  | Pending  |
| JOBS-01   | Phase 9  | TBD  | Pending  |
| JOBS-02   | Phase 9  | TBD  | Pending  |
| JOBS-03   | Phase 9  | TBD  | Pending  |
| JOBS-04   | Phase 9  | TBD  | Pending  |
| JOBS-05   | Phase 9  | TBD  | Pending  |
| JOBS-06   | Phase 9  | TBD  | Pending  |
| JOBS-07   | Phase 9  | TBD  | Pending  |
| EXTR-01   | Phase 10 | TBD  | Pending  |
| EXTR-02   | Phase 10 | TBD  | Pending  |
| EXTR-03   | Phase 10 | TBD  | Pending  |
| EXTR-04   | Phase 10 | TBD  | Pending  |
| EXTR-05   | Phase 10 | TBD  | Pending  |
| EXTR-06   | Phase 10 | TBD  | Pending  |
| DYN-01    | Phase 11 | TBD  | Pending  |
| DYN-02    | Phase 11 | TBD  | Pending  |
| DYN-03    | Phase 11 | TBD  | Pending  |
| DYN-04    | Phase 11 | TBD  | Pending  |
| DYN-05    | Phase 11 | TBD  | Pending  |
| DYN-06    | Phase 11 | TBD  | Pending  |
| DYN-07    | Phase 11 | TBD  | Pending  |
| SKILL-01  | Phase 12 | TBD  | Pending  |
| SKILL-02  | Phase 12 | TBD  | Pending  |
| SKILL-03  | Phase 12 | TBD  | Pending  |
| SKILL-04  | Phase 12 | TBD  | Pending  |

**Coverage:** 52/52 v1.1 requirements mapped (100%).

---

*Created 2026-05-12 by `/gsd-new-milestone` for v1.1 Remote RE Tool Expansion.*
*Roadmap mapped 2026-05-12 — Phases 5-12 (continued from v1.0's Phase 4).*
