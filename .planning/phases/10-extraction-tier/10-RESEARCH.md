# Phase 10: Extraction Tier — Research

**Researched:** 2026-05-19
**Domain:** Subprocess-driven file carving (binwalk / unblob / UPX) + content-addressed sample promotion, integrated as MCP gateway tools layered on Phase 6 (ReToolRunner), Phase 7 (case-dir artifacts), and Phase 9 (BackgroundJobRegistry).
**Confidence:** HIGH for codebase integration (every dependent module exists and was directly inspected); MEDIUM for external-tool CLI shapes (verified via official docs and Debian/Kali package pages); MEDIUM-LOW for whether `binwalk` (v2 EOL) or `binwalk3` is the runtime target — this is a discretion call that must be made in planning before any wrapper code is paste-ready.

## Summary

Phase 10 has an unusually high "ratio of internal plumbing to external surface": the seven new MCP tools are mostly thin orchestrators over (a) Phase 6's `ReToolRunner` (sync wrappers), (b) Phase 9's `start_tool_job` / `get_tool_job` / `cancel_tool_job` (async wrappers), and (c) three small primitives this phase introduces — `extraction_dir` (mints `extracted/<engine>-<UTC>Z-<rand4>/`), `quarantine_symlinks` (post-extract recursive sweep), and `start_extract_monitor` (sibling asyncio task that polls `du`-style size against `MCP_GATEWAY_MAX_EXTRACT_MB` and cancels the underlying Phase 9 job on cap exceed). Every Phase 9 D-15 / D-19 / D-26 invariant carries forward unchanged; CONTEXT.md D-21 explicitly states "Lifespan changes — none."

The single largest open external question is **binwalk version**: the current `Dockerfile:52` line installs `binwalk` (apt package v2.4.3, EOL December 2025 per kali.org) but Kali Rolling has a separate `binwalk3` package (v3.1.0-0kali4 as of March 2026) which is a Rust rewrite with a different CLI surface. CONTEXT.md D-09 anticipates this: "the wrapper must handle both — fail-loud with a `{"error": "unsupported binwalk version", ...}` dict if the parser can't lock to a row schema." The robust planner choice is to **switch the Dockerfile to `binwalk3`** (Phase 5's image-hash fix means a Dockerfile edit triggers a rebuild correctly) and write the wrapper against binwalk3's documented surface, with a `binwalk_2_fallback` parser only if the planner decides to support both. This research recommends single-target binwalk3 — binwalk2 EOL'd five months ago.

**Primary recommendation:** Build Phase 10 against (1) `binwalk3 v3.1.0+` with JSON logging via `-l <path>` and extraction via `-e -M -C <dir> -d <depth>`; (2) `unblob v26.x` with `--report <path> -e <dir> -d <depth>`, dispatched as a Phase 9 job with `progress_parser=None` (unblob uses Rich's progress widget which is not line-parseable on stderr); (3) `upx-ucl v4.2.x` (apt) for sync `-t` / `-l` / `-d -o` parsing. Every wrapper layers onto Phase 6's locked 12-key dict (sync) or Phase 9's locked 25-key dict (async) and never raises. The new `extraction.py` primitive owns: extraction-dir minting, `_mare_meta.json` sidecar reads/writes, symlink quarantine, archive-bomb monitor, and `_build_unblob_argv` + `_build_binwalk_extract_argv` pure-function argv builders.

## Project Constraints (from CLAUDE.md)

- **Tech stack lock:** Custom FastMCP gateway in `mcp-gateway/`, Python 3.11+, `mcp>=1.27,<1.28`, Streamable HTTP. Phase 10 adds zero new top-level dependencies — `binwalk`/`unblob`/`upx-ucl` are subprocess targets, not Python imports. [VERIFIED: CLAUDE.md "Technology Stack" + `mcp-gateway/pyproject.toml` pin]
- **Licensing:** N/A for Phase 10 — extraction tools are open-source. [VERIFIED]
- **Security posture:** Container runs with elevated capabilities; Phase 10 wrappers must NOT widen the surface (CONTEXT.md is explicit on this). Symlink quarantine (D-15/D-16) is itself a security control: the Phase 7 Resources walker follows symlinks, so unquarantined extraction symlinks become host-FS traversal vectors. [VERIFIED: CLAUDE.md "Security" + CONTEXT.md D-15]
- **Backward compat:** "Existing 'agent inside container' mode must continue working unchanged." Phase 10 only adds tools; no v1.0 behavior changes. [VERIFIED]
- **GSD workflow:** Edits must go through a GSD command. Phase 10 must follow the Wave 0 RED-stub → Wave 1 primitive → Wave 2 surface → Wave 3 integration pattern established by Phases 6–9. [VERIFIED: CLAUDE.md "GSD Workflow Enforcement" + STATE.md plan history]
- **Commit style:** Single-line imperative sentence case, no conventional-commit syntax. [VERIFIED: global CLAUDE.md "Commit Messages"]

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (verbatim from CONTEXT.md `<decisions>`)

- **D-01:** Phase 10 ships **exactly seven** MCP-visible tools, one per EXTR-01..EXTR-05 spelling in REQUIREMENTS.md: `run_binwalk`, `run_unblob`, `run_upx_test`, `run_upx_list`, `run_upx_unpack`, `list_extracted_files`, `promote_extracted_sample`. Gateway-native tool count bumps **47 → 54**. `EXPECTED_TOOLS` in `test_tool_list.py` is updated (Rule-1 deviation; precedent Phase 7-08 / 9-03).
- **D-02:** `run_binwalk` is one MCP tool with internal `mode` discrimination (`signatures` / `entropy` / `extract`). Sync return for signatures/entropy (Phase 6 D-03 12-key dict + parsed rows + `extraction_dir: None` + `mode`); async return for extract (Phase 9 D-19 25-key job snapshot + `mode: "extract"` + `extraction_dir: str` + `engine: "binwalk"`). Agent discriminates by `result["mode"]`.
- **D-03:** `run_unblob` always dispatches a Phase 9 background job. Returns the 25-key job snapshot + `mode: "unblob"` + `extraction_dir: str` + `engine: "unblob"` + `meta_path: str`.
- **D-04:** UPX wrappers (`run_upx_test`, `run_upx_list`, `run_upx_unpack`) are all synchronous and all parsed. Output parsing is part of the wrapper — never raw-only.
- **D-05:** `list_extracted_files(case_dir, *, engine=None, limit=500, include_quarantined=True)` walks `case_dir/extracted/**` engine-agnostically, reads per-extraction `_mare_meta.json` sidecars, returns a top-level shape with per-extraction `files: list[dict]` capped at `MAX_FILES_PER_EXTRACTION` (env `MCP_GATEWAY_LIST_EXTRACT_FILES_PER_EXTRACTION`, default 5000), cross-extraction `limit` default 500 max 10000.
- **D-06:** `promote_extracted_sample(parent_case_dir, child_path, *, force_new=False)` flow is atomic: confine `child_path` under `<parent_case_dir>/extracted/**`, recompute sha256 (reject `.symlink-target.txt`), dedup via `<UPLOADS_ROOT>/<sha256>/`, idempotency via `_lineage.json` lookup, call existing `init_case(sample=<sha256>, new=True)`, write new `_lineage.json`. Returns the 10-key dict in D-06.
- **D-07:** Extraction-dir naming `extracted/<engine>-<UTC>Z-<rand4>/` (engine ∈ `{binwalk, unblob, upx}`). Reuses `artifacts_io.tool_log_path` rand4+UTC-Z slug machinery via new `extraction.extraction_dir(case_dir, engine) -> Path` helper.
- **D-08:** Per-extraction `_mare_meta.json` sidecar with the locked 17-field shape (engine / mode / started_at / completed_at / status / exit_code / case_dir / extraction_dir / sample / sample_sha256 / argv / job_id / log_path / symlinks_quarantined / cap_exceeded / extract_bytes_total / monitor_polls). Status values from a closed set including `cap_exceeded`. Written immediately at extraction-dir creation with `status="running"`, updated to terminal status on completion. The sidecar — not in-memory state — is the durable provenance record.
- **D-09:** Every wrapper parses tool output to JSON. Unblob already JSON via `--report`. Binwalk: prefer machine-readable mode if available else parse text rows; fail-loud `{"error": "unsupported binwalk version", ...}` if parser can't lock. UPX: parse stderr line patterns into structured rows. Robust fallback: raw line in `raw: str` field with structured fields None if parser misses.
- **D-10:** Result-dict layering — sync wrappers layer on Phase 6 D-03 12 keys; async wrappers layer on Phase 9 D-19 25 keys; extension keys come AFTER base keys (never rename/remove). Common Phase 10 extension fields: `engine`, `mode`, `extraction_dir`, `symlinks_quarantined`, `meta_path`.
- **D-11:** Two new `JobToolSpec` entries (`unblob`, `binwalk_extract`) register at module import time via the public `register_job_tool` API. Specs are public (no underscore). `default_timeout_s=3600.0` (unblob), `1800.0` (binwalk_extract). Unblob may have a `progress_parser`; binwalk_extract ships with `None`. Phase 9 D-04 `tools/job_specs/` refactor is **deferred to Phase 11** (count now 3, threshold is 5).
- **D-12:** `_build_unblob_argv` and `_build_binwalk_extract_argv` are pure functions in `extraction.py` (no I/O, no side effects). `extraction_dir` kwarg is pre-minted by the MCP wrapper before `start_tool_job` is called.
- **D-13:** Wrapper-side flow for job-dispatched tools: (1) `extraction.extraction_dir` mints subdir; (2) write initial `_mare_meta.json` `status="running"`; (3) dispatch via `tools_jobs.start_tool_job`; (4) `asyncio.create_task` spawns the sibling `start_extract_monitor`; (5) update meta with `job_id`; (6) return augmented snapshot.
- **D-14:** Promotion sha256 idempotency — `_existing_case_for_sha256(sha)` scans `STATUS_ROOT/*/_lineage.json` for matching `promoted_sha256`; first match wins. `force_new=True` bypasses. Cases without `_lineage.json` are NOT idempotent-reuse candidates. Lineage file shape: `promoted_sha256`, `parent_case_dir`, `parent_extraction_dir`, `child_path`, `promoted_at`, `promoted_by="promote_extracted_sample"`, `version=1`.
- **D-15:** `quarantine_symlinks(extraction_dir) -> (count, list)` recursively replaces every symlink with `<name>.symlink-target.txt`. Walk via `os.scandir` (does NOT follow symlinks). For sync wrappers: inside wrapper after subprocess. For job-dispatched: inside the sibling monitor's post-terminal hook (BEFORE agent polls).
- **D-16:** `.symlink-target.txt` body format — five lines: `SYMLINK QUARANTINE`, `Original symlink (relative within extraction):`, `Target (as-written by extractor):`, `Resolved target (canonical absolute):`, `Quarantined: <ISO8601 Z>`, `Reason: ...`.
- **D-17:** `start_extract_monitor(job_id, extraction_dir)` is a sibling `asyncio.Task` (NOT a registry). Loops `await asyncio.sleep(interval)` → check job terminal → `_du_sb(extraction_dir)` → if `> max_bytes` write `.MARE_EXTRACT_CAP_EXCEEDED` marker, update meta `cap_exceeded=True status="cap_exceeded"`, call `cancel_tool_job(job_id)`. Post-terminal hook: `quarantine_symlinks` → terminal snapshot fetch → final meta update.
- **D-18:** Env-var module constants in `extraction.py`: `MAX_EXTRACT_MB` (`MCP_GATEWAY_MAX_EXTRACT_MB`, default 4096), `EXTRACT_MONITOR_INTERVAL_S` (`MCP_GATEWAY_EXTRACT_MONITOR_INTERVAL_S`, default 5.0), `MAX_FILES_PER_EXTRACTION` (`MCP_GATEWAY_LIST_EXTRACT_FILES_PER_EXTRACTION`, default 5000), derived `MAX_EXTRACT_BYTES = MAX_EXTRACT_MB * 1024 * 1024`. Validated at import; RuntimeError on bad.
- **D-19:** Import graph — `extraction.py` imports `artifacts_io`, `runner`, `jobs` (for `JobToolSpec` + `register_job_tool`), `tools.samples` (`resolve_sample`), `uploads` (`UPLOAD_DIR`, `MAX_BYTES`); MUST NOT import `tools.*` except `samples`; MUST NOT import `mcp.server.fastmcp`. `tools/extract.py` imports `extraction`, `tools.jobs`, `tools.case_dirs`, `tools.samples`, `tools.cases` (or shell out via `subprocess_runner.run_script` for `init_status_tree.sh`). **Locked:** specs live in `extraction.py`; `jobs.py` body is untouched (refines Phase 9 D-04 without reopening).
- **D-20:** `tools/__init__.py::register_all_tools` adds one import (`from mcp_gateway.tools import extract as extract_tools`) + one register call (`extract_tools.register(mcp)`), AFTER `r2_sessions` and `jobs`, BEFORE `collision_check`.
- **D-21:** **Lifespan changes — NONE.** Phase 10 introduces no registry in `app.py::lifespan`. Sibling monitor tasks are leaf tasks; their lifetime is bounded by their job. Matches Phase 7 D-16 "register but no lifespan" precedent.
- **D-22:** Structured error dicts (Phase 9 D-15 inheritance) — six locked shapes: invalid `case_dir`, invalid `sample`, unsupported binwalk version, child not under `extracted/`, child is symlink quarantine sentinel, archive-bomb cap exceeded.
- **D-23:** Per-tool docstring disclaimer (verbatim text required in `run_unblob`, `run_binwalk` extract portion, `list_extracted_files`, `promote_extracted_sample`); tested via `assert disclaimer_text in tool.__doc__`. Sync-only UPX wrappers and binwalk scan modes get a shorter form (no in-memory job mention).
- **D-24:** Wave 0 RED-stub test layout under `mcp-gateway/tests/extraction/` — 13 test files + `conftest.py`. RED-stub discipline: test functions import not-yet-existing modules at function top so pytest collection passes but execution ImportErrors. `pytest.skip` forbidden except for `_require_<tool>_or_skip` slow-integration gates.

### Claude's Discretion (verbatim from CONTEXT.md)

- Internal naming of private helpers in `extraction.py` (`_du_sb`, `_utc_now_iso`, `_hash_file_streaming`, `_existing_case_for_sha256`). Public surface (`extraction_dir`, `quarantine_symlinks`, `start_extract_monitor`, `write_meta`, `update_meta`, `read_meta`, `enumerate_extractions`) is locked.
- Whether to inline `_env_int`/`_env_float` in `extraction.py` or import from `sessions.py`/`jobs.py`. Lean: import only if publicly exported (no underscore); else inline. Verified during planning by grep of `sessions.py`/`jobs.py` (both currently underscore-prefixed: `sessions._env_int`, `jobs._env_int` — so **inline is the locked-by-precedent choice**).
- Whether `run_binwalk(mode="signatures")` uses `binwalk --log <json>` (binwalk3) or parses `binwalk -B` text (binwalk2). Wrapper branches at runtime via one-shot capability detection. **This research recommends single-target binwalk3 in the Dockerfile (see Standard Stack table).**
- Exact wording of D-22 error hint strings (structure locked; prose flexible).
- Whether `list_extracted_files` adds `engine_specific_summary` block. Lean: yes for unblob (free signal from already-parsed `report.json`), maybe-not for binwalk/upx. Planning decision.
- Whether to expose `cancel_extraction(case_dir, extraction_dir)` helper. Lean: NO — agents cancel via Phase 9.
- Whether `_lineage.json` exposed as additional MCP Resource. Phase 7 D-26 depth-2 walker covers it automatically. Lean: yes (free), confirm during planning.
- ANSI-strip / UTF-8-boundary truncation reuse from Phase 6 — reuse if exported; otherwise inline.

### Deferred Ideas (OUT OF SCOPE, verbatim from CONTEXT.md)

- `tools/job_specs/` refactor (defer to Phase 11 when count crosses 5).
- Promotion lineage as versioned audit log (single `_lineage.json` for v1.1; `_lineage.jsonl` is v1.2+).
- "Interesting" file heuristic hot-list — orchestrator skill (Phase 12) is the right home.
- Cross-case extraction tree visualization — analysts build their own DAG.
- `MCP_GATEWAY_MAX_EXTRACT_MB` as hard FS quota (`prlimit --fsize` / tmpfs) — v1.2+.
- Auto-promotion of "interesting" children — composite tool, out of scope.
- Persistent extraction monitor state across gateway restart — marker + sidecar are durable; in-memory monitor is not.
- Per-engine quotas — one cap value across all three engines for v1.1.
- Run-shell extraction — already covered by Phase 7's `run_shell`.
- Composite `extract_and_promote` MCP tool — orchestration is the agent/skill's job.
- `run_strings` over extracted files — out of scope per REQUIREMENTS.md.
- Per-`Mcp-Session-Id` keying of promotion idempotency — promotion is sha256-idempotent globally.
- Disk-quota-aware case-dir cleanup — bounded only by analyst lifecycle.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXTR-01 | Agent can run binwalk for signatures and entropy via `run_binwalk(case_dir, sample, mode)`; extraction output confined to `case_dir/extracted/binwalk-<ts>/`. | binwalk3 v3.1.0+ CLI verified: `-l <json>` for log, `-E` entropy, `-e -M -C <dir> -d <depth>` extract. Extraction confinement enforced via `extraction.extraction_dir()` (D-07) returning a `confine_to`-validated path. |
| EXTR-02 | Agent can run unblob with structured `--report` JSON via `run_unblob(case_dir, sample)`; output confined to `case_dir/extracted/unblob-<ts>/`, dispatched as background job. | unblob v26.x CLI verified: `--report <path>`, `-e <dir>`, `-d <depth>`, `-p <workers>`. JSON shape includes StatReport/FileMagicReport/ChunkReport per task. Dispatched via Phase 9 `start_tool_job`. |
| EXTR-03 | Agent can test/list/unpack UPX via `run_upx_test`/`run_upx_list`/`run_upx_unpack`. | upx-ucl v4.2.x (apt) verified. `-t` for integrity test, `-l` for list, `-d -o <out>` for unpack. Stderr-driven output; parser per D-04 / D-09. |
| EXTR-04 | Agent can enumerate extracted files via `list_extracted_files(case_dir)` engine-agnostically. | Walker reads `case_dir/extracted/*/` directory names + `_mare_meta.json` sidecars (D-05/D-08). Engine identified by dir-name regex `^(binwalk\|unblob\|upx)-`. |
| EXTR-05 | Agent can promote extracted child to first-class new case via `promote_extracted_sample`; sha256 content-addressing; new case_dir returned. | Reuses `uploads.UPLOAD_DIR` (`<sha256>/<basename>`) layout from v1.0 D-13. Calls existing `init_case(sample=<sha256>, new=True)` MCP tool — see `tools/artifacts.py:27` and `scripts/init_status_tree.sh`. Lineage tracked in `_lineage.json` (D-14). |
| EXTR-06 | Extraction tools enforce: symlink quarantine (`.symlink-target.txt`), archive-bomb cap (`MCP_GATEWAY_MAX_EXTRACT_MB` default 4 GB), atomic promotion (sha256 recomputed). | `quarantine_symlinks()` (D-15/D-16) walks via `os.scandir` (no symlink follow). `start_extract_monitor()` (D-17) polls `_du_sb` against `MAX_EXTRACT_BYTES`. Promotion recomputes sha256 in step 2 of D-06 flow. |
</phase_requirements>

## Standard Stack

### Core (subprocess-target tools — already installed in the container)

| Library / Tool | Version | Purpose | Why Standard |
|----------------|---------|---------|--------------|
| `binwalk3` (Kali apt) | 3.1.0-0kali4 (migrated to kali-rolling 2026-03-09) | Signature scan, entropy plot, recursive extraction | Rust rewrite — 2-5x faster than v2, 60-80% fewer false positives, **active development**; binwalk v2.x reached EOL 2025-12-12 per kali.org. JSON logging via `-l <path>`. [CITED: https://www.kali.org/tools/binwalk3/ ; https://pkg.kali.org/pkg/binwalk3 ; https://www.kali.org/tools/binwalk/] |
| `unblob` (pip, already in Dockerfile) | 26.x current (26.3.30 latest at 2026-03-30 per GitHub releases) | Structured carving with JSON `--report` | Production carver maintained by onekey-sec; `--report` JSON is the canonical machine-readable surface; better format coverage than binwalk for complex firmware (squashfs/ubi/cramfs). [CITED: https://unblob.org/guide/ ; https://github.com/onekey-sec/unblob] |
| `upx-ucl` (apt) | 4.2.2-3 (current Debian/Kali) | UPX-packed binary test/list/unpack | The reference UPX CLI; stable stderr surface across versions (`upx-ucl` is the Debian package name for `upx` v4+). [VERIFIED: apt-cache show upx-ucl on local system; CITED: https://upx.github.io/] |

### Supporting (Python stdlib + existing gateway modules — no new deps)

| Module | From | Purpose | When to Use |
|--------|------|---------|-------------|
| `asyncio` | stdlib | Sibling monitor task (D-17), job dispatch await | Every wrapper that awaits subprocess/job; `asyncio.create_task` for monitor |
| `hashlib.sha256` | stdlib | Streaming sha256 for promotion (D-06 step 2) | `_hash_file_streaming` private helper |
| `os.scandir`, `os.readlink`, `os.path.realpath`, `os.unlink` | stdlib | Symlink-safe directory walk (D-15) | `quarantine_symlinks` implementation; **MUST NOT use `Path.iterdir()` if it follows symlinks** (it does not on most platforms, but `os.scandir` makes the no-follow guarantee explicit) |
| `secrets.token_hex(2)` | stdlib | rand4 suffix on extraction dirs (D-07) | Reuses `artifacts_io.tool_log_path` machinery |
| `datetime.now(timezone.utc).strftime` | stdlib | UTC-Z timestamp on extraction dirs / meta (D-07/D-08) | Reuses `artifacts_io.tool_log_path` pattern |
| `json` | stdlib | `_mare_meta.json` read/write, unblob `report.json` parse | `write_meta`, `update_meta`, `read_meta`, `list_extracted_files` |
| `tempfile.NamedTemporaryFile` + `os.rename` | stdlib | Atomic re-upload during promotion (D-06 step 4) | `extraction.write_upload(child_path, target_basename)` — pattern from `uploads.py:107-127` |
| `mcp_gateway.runner.run_tool` / `ReToolRunner` | existing | Sync subprocess execution | UPX wrappers + binwalk scan modes |
| `mcp_gateway.tools.jobs.start_tool_job / get_tool_job / cancel_tool_job` | existing | Async job dispatch | `run_unblob`, `run_binwalk(mode="extract")`, and the monitor |
| `mcp_gateway.jobs.JobToolSpec` + `register_job_tool` | existing | Two new specs (`unblob`, `binwalk_extract`) | Module-level registration in `extraction.py` |
| `mcp_gateway.artifacts_io.confine_to` / `ensure_subdir` / `tool_log_path` | existing | Path safety + slug machinery | Every path-accepting wrapper |
| `mcp_gateway.tools.samples.resolve_sample` + `UPLOADS_ROOT` | existing | sha256 / path → absolute; uploads root | Sample resolution + re-upload target |
| `mcp_gateway.tools.case_dirs.resolve_case_dir` | existing | STATUS_ROOT validation | First validation step in every wrapper |
| `mcp_gateway.uploads.UPLOAD_DIR` (and `_is_invalid_filename`) | existing | Re-upload target + basename validation | Promotion's atomic write |
| `mcp_gateway.tools.artifacts.init_case` MCP tool | existing | New case dir + 13 empty artifact files | Called programmatically from `promote_extracted_sample` (see "Integration points" in CONTEXT.md `<code_context>`) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff / Why Not |
|------------|-----------|--------------------|
| `binwalk3` (Rust v3.1.0) | `binwalk` (Python v2.4.3) — currently in Dockerfile | **binwalk v2 EOL'd 2025-12-12**; staying on v2 means committing to dead code. Migration is cheap because Phase 5 already fixed the image-hash rebuild trigger. RECOMMEND: change `Dockerfile:52` from `binwalk` to `binwalk3` as part of Phase 10. [CITED: https://www.kali.org/tools/binwalk/ "v2.x will reach EOL in 12/12/2025"] |
| `unblob --report` JSON | `binwalk -e` only | unblob has wider format coverage (squashfs/cramfs/ubi/sasquatch) and emits structured reports natively; binwalk alone leaves common firmware formats uncarved. The two are complementary, not substitutes — Phase 10 ships BOTH per EXTR-01 + EXTR-02. [VERIFIED: CONTEXT.md domain section] |
| Sibling `asyncio.Task` monitor (D-17) | Periodic check inside the job spec's `build_argv` / `progress_parser` | The cap is a Phase 10 concern; pushing it into `jobs.py` reopens Phase 9 D-06 vocabulary. The sibling task pattern keeps Phase 10 self-contained. [VERIFIED: CONTEXT.md `<specifics>` "Cap enforcement via sibling monitor task, not a new JobStatus"] |
| `du -sb` subprocess | `os.walk` + `os.stat` in-process | In-process avoids fork/exec overhead per poll (every 5s by default). CONTEXT.md D-17 line 853 commits to `os.walk + os.stat`. [VERIFIED: CONTEXT.md D-17] |
| sha256 via subprocess `sha256sum` | `hashlib.sha256` streaming | Native is faster and avoids a subprocess; uploads.py already uses `hashlib.sha256` (line 104). [VERIFIED: `mcp-gateway/src/mcp_gateway/uploads.py:104`] |
| New MCP tool `init_extracted_case(sha256, basename)` | Reuse existing `init_case` MCP tool | Per CONTEXT.md `<code_context>` and `<canonical_refs>` — calling `init_case(sample=<sha256>, new=True)` from `promote_extracted_sample` reuses 60+ lines of existing logic and the `init_status_tree.sh` invariants. [VERIFIED: `tools/artifacts.py:27`] |

**Installation (Dockerfile changes only):**

```diff
- # Dockerfile:52
-     binwalk \
+ # Switch to binwalk3 (Rust v3.1.0+); binwalk v2.4.3 reached EOL 2025-12-12
+     binwalk3 \
```

No pyproject.toml changes — every supporting module is already an import dependency of earlier phases.

**Version verification commands** (run during planning to lock numbers):

```bash
# Inside the container after Dockerfile edit:
binwalk --version            # expect 3.1.0+
unblob --version             # expect 26.x
upx-ucl --version | head -1  # expect 4.2.x

# At registry-confirmation time (planner runs):
apt-cache policy binwalk3    # confirm 3.1.0-0kali4 or newer
pip show unblob | grep ^Version
```

## Architecture Patterns

### Recommended Project Structure (matches Phase 6/8/9 layering verbatim)

```
mcp-gateway/src/mcp_gateway/
├── extraction.py                 # NEW — primitive layer (D-19)
│                                   # - extraction_dir(case_dir, engine) -> Path
│                                   # - quarantine_symlinks(extraction_dir) -> (count, list)
│                                   # - write_meta/update_meta/read_meta
│                                   # - enumerate_extractions(case_dir)
│                                   # - start_extract_monitor(job_id, extraction_dir)
│                                   # - _build_unblob_argv / _build_binwalk_extract_argv (pure)
│                                   # - register_job_tool(_UNBLOB_SPEC / _BINWALK_EXTRACT_SPEC)
│                                   # - write_upload(child_path, target_basename) — atomic re-upload
│                                   # - MAX_EXTRACT_MB / EXTRACT_MONITOR_INTERVAL_S / MAX_FILES_PER_EXTRACTION (D-18)
│                                   # NO import of mcp.server.fastmcp; NO import of tools.* except samples
│
├── tools/
│   └── extract.py                # NEW — MCP surface (D-19)
│                                   # 7 @mcp.tool() handlers + register(mcp)
│                                   # imports: extraction, tools.jobs, tools.case_dirs, tools.samples
│
├── jobs.py                       # UNCHANGED body (refines Phase 9 D-04 — specs live in extraction.py)
├── tools/__init__.py             # +1 import, +1 register call (D-20)
├── tools/resources.py            # UNCHANGED — depth-2 walker auto-exposes new sidecars
└── artifacts_io.py               # UNCHANGED — "extracted" already in EXPANDED_CASE_SUBDIRS (line 35)

mcp-gateway/tests/
└── extraction/                   # NEW — 13 test files + conftest.py + __init__.py
    ├── __init__.py
    ├── conftest.py               # _require_binwalk_or_skip, _require_unblob_or_skip, _require_upx_or_skip,
    │                             # fake extraction tree builders (no real subprocess)
    ├── test_extraction_dir.py
    ├── test_meta_sidecar.py
    ├── test_quarantine_symlinks.py
    ├── test_extract_monitor.py
    ├── test_list_extracted_files.py
    ├── test_promote_extracted_sample.py
    ├── test_run_binwalk.py
    ├── test_run_unblob.py
    ├── test_run_upx.py
    ├── test_job_specs_unblob.py             # _build_unblob_argv pure-function tests
    ├── test_job_specs_binwalk_extract.py    # _build_binwalk_extract_argv pure-function tests
    ├── test_disclaimers.py                  # D-23 docstring regression
    └── test_tool_list_phase10.py            # EXPECTED_TOOLS bump 47 → 54 invariant
```

### Pattern 1: Primitive + MCP-Surface Split (Phase 6/8/9 — exact replication)

**What:** Every Phase 6+ feature has two files: a primitive module (pure functions / classes, no MCP imports) and a `tools/<name>.py` surface (every callable `@mcp.tool()`-decorated, returns dicts, never raises).

**When to use:** Always. Phase 10's `extraction.py` (primitive) + `tools/extract.py` (surface) is the canonical example for this milestone.

**Why:** The primitive can be unit-tested without spinning up FastMCP; the surface enforces the "tools never raise out of MCP boundary" invariant in a single layer.

**Example (from Phase 9 — `jobs.py` line 619-684 and `tools/jobs.py` line 96-178):**

```python
# extraction.py (primitive — verbatim shape)
from mcp_gateway.jobs import JobToolSpec, register_job_tool
from mcp_gateway.artifacts_io import ensure_subdir, tool_log_path

MAX_EXTRACT_MB: int = _env_int("MCP_GATEWAY_MAX_EXTRACT_MB", 4096)
EXTRACT_MONITOR_INTERVAL_S: float = _env_float("MCP_GATEWAY_EXTRACT_MONITOR_INTERVAL_S", 5.0)
MAX_FILES_PER_EXTRACTION: int = _env_int("MCP_GATEWAY_LIST_EXTRACT_FILES_PER_EXTRACTION", 5000)
MAX_EXTRACT_BYTES: int = MAX_EXTRACT_MB * 1024 * 1024

def extraction_dir(case_dir: str | Path, engine: Literal["binwalk", "unblob", "upx"]) -> Path:
    """Mint extracted/<engine>-<UTC>Z-<rand4>/ subdir. Reuses Phase 6 D-09 machinery."""
    if engine not in ("binwalk", "unblob", "upx"):
        raise ValueError(f"engine must be one of binwalk|unblob|upx, got {engine!r}")
    ensure_subdir(case_dir, "extracted")
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rand4 = secrets.token_hex(2)
    target = Path(case_dir) / "extracted" / f"{engine}-{ts}-{rand4}"
    target.mkdir(parents=False, exist_ok=False)  # rand4 collision guarantees False is safe
    return target.resolve(strict=True)

def _build_unblob_argv(case_dir: Path, kwargs: dict) -> list[str]:
    """Pure function — no I/O, no side effects."""
    from mcp_gateway.tools import samples  # local import — same pattern as jobs.py:363
    sample = samples.resolve_sample(kwargs["sample"])
    extraction_path = Path(kwargs["extraction_dir"])
    # extraction_dir is pre-minted by tools/extract.py wrapper; confine here defensively
    if not extraction_path.is_relative_to(case_dir):
        raise ValueError(f"extraction_dir not under case_dir: {extraction_path}")
    depth = int(kwargs.get("depth", 8))
    # unblob v26.x: -e <dir>, --report <path>, -d <depth>, plus -v for stderr progress lines
    return [
        "unblob",
        "--report", str(extraction_path / "report.json"),
        "-e", str(extraction_path),
        "-d", str(depth),
        sample,
    ]

_UNBLOB_SPEC = JobToolSpec(
    name="unblob",
    slug="unblob",
    build_argv=_build_unblob_argv,
    default_timeout_s=3600.0,
    progress_parser=None,  # unblob uses Rich Progress — not line-parseable on stderr (see Pitfall 3)
    kwargs_schema={
        "case_dir":       {"type": "string", "required": True},
        "sample":         {"type": "string", "required": True},
        "extraction_dir": {"type": "string", "required": True},
        "depth":          {"type": "integer", "min": 1, "max": 16},
    },
    description="Carve embedded files from a sample via unblob. ...",
)
register_job_tool(_UNBLOB_SPEC)
```

```python
# tools/extract.py (surface — verbatim shape from tools/jobs.py)
from mcp.server.fastmcp import FastMCP
from mcp_gateway import extraction
from mcp_gateway.tools import jobs as tools_jobs
from mcp_gateway.tools.case_dirs import resolve_case_dir
from mcp_gateway.tools.samples import resolve_sample

_EXTRACTION_DISCLAIMER = """
    Extraction state lives in case_dir/extracted/<engine>-<ts>-<rand4>/
    with a `_mare_meta.json` provenance sidecar. The in-memory job registry
    for unblob/binwalk_extract is volatile (gateway restart cancels in-flight
    jobs and forgets terminal jobs), but the on-disk extraction tree + sidecar
    are preserved.
    [...full text per D-23...]
"""

async def run_unblob(case_dir: str, sample: str, *, depth: int = 8, ctx=None) -> dict:
    """[Docstring with {_EXTRACTION_DISCLAIMER} splice marker per D-23]"""
    try:
        case_path = Path(resolve_case_dir(case_dir))
    except (ValueError, TypeError) as e:
        return {"error": "invalid case_dir", "case_dir": case_dir, "hint": str(e)}
    try:
        sample_abs = resolve_sample(sample)
    except (ValueError, FileNotFoundError) as e:
        return {"error": "invalid sample", "sample": sample, "hint": str(e)}
    extraction_path = extraction.extraction_dir(case_path, "unblob")
    sample_sha = extraction._hash_file_streaming(sample_abs)
    extraction.write_meta(extraction_path, {
        "engine": "unblob", "mode": "extract", "started_at": extraction._utc_now_iso(),
        "status": "running", "case_dir": str(case_path),
        "extraction_dir": str(extraction_path.relative_to(case_path)),
        "sample": sample_abs, "sample_sha256": sample_sha,
        "argv": [], "job_id": None, "log_path": "", "symlinks_quarantined": 0,
        "cap_exceeded": False, "extract_bytes_total": 0, "monitor_polls": 0,
        "exit_code": None, "completed_at": None,
    })
    snapshot = await tools_jobs.start_tool_job(
        tool="unblob",
        kwargs={"case_dir": str(case_path), "sample": sample,
                "extraction_dir": str(extraction_path), "depth": depth},
        case_dir=str(case_path),
        ctx=ctx,
    )
    if "error" in snapshot:
        # propagate Phase 9 D-15 error shape upward
        return snapshot
    asyncio.create_task(
        extraction.start_extract_monitor(
            job_id=snapshot["job_id"],
            extraction_dir=extraction_path,
        )
    )
    extraction.update_meta(extraction_path, {"job_id": snapshot["job_id"], "argv": snapshot["argv"], "log_path": snapshot["log_path"]})
    return {
        **snapshot,
        "engine": "unblob",
        "mode": "extract",
        "extraction_dir": str(extraction_path.relative_to(case_path)),
        "meta_path": str((extraction_path / "_mare_meta.json").relative_to(case_path)),
        "symlinks_quarantined": 0,  # not yet swept; final count in meta after job terminal
    }

run_unblob.__doc__ = (run_unblob.__doc__ or "").replace("{_EXTRACTION_DISCLAIMER}", _EXTRACTION_DISCLAIMER)

def register(mcp: FastMCP) -> None:
    mcp.tool()(run_binwalk)
    mcp.tool()(run_unblob)
    mcp.tool()(run_upx_test)
    mcp.tool()(run_upx_list)
    mcp.tool()(run_upx_unpack)
    mcp.tool()(list_extracted_files)
    mcp.tool()(promote_extracted_sample)
```

### Pattern 2: JobToolSpec Registration at Module Import (Phase 9 D-04)

**What:** New job-tool specs live as module-level constants in the module that owns the `build_argv` function; `register_job_tool(spec)` is called at the bottom of the module.

**When to use:** Any tool that dispatches via Phase 9's job system. Phase 10's two specs (`unblob`, `binwalk_extract`) follow this pattern.

**Example (`jobs.py:326-335` for `_sleep_probe`):**

```python
_UNBLOB_SPEC = JobToolSpec(name="unblob", slug="unblob", build_argv=_build_unblob_argv, ...)
register_job_tool(_UNBLOB_SPEC)  # module-import time
```

### Pattern 3: Sibling Monitor Task (Phase 10-specific)

**What:** A long-running watcher (the archive-bomb monitor) is an `asyncio.create_task` of a primitive coroutine, NOT a registry slot.

**When to use:** Watchers whose lifetime is strictly bounded by a parent's lifetime (here: the Phase 9 job). The watcher exits cleanly when it observes the parent in terminal state.

**Why no registry:** CONTEXT.md D-17 (line 845-852): "monitor tasks self-terminate when the job hits terminal status; gateway shutdown cancels all jobs via `BackgroundJobRegistry.__aexit__`, which causes the monitor's next `get_tool_job` to return a terminal status, which causes the monitor to exit cleanly within `interval_s + post_terminal_hook`."

**Pitfall to avoid:** The `asyncio.create_task(...)` return value MUST be retained somewhere (assigned to a local in the wrapper) — or use a module-level set to hold strong refs — otherwise Python's GC may discard the task. Phase 9 hit this exact issue (`Pitfall 2: retain task on the Job so GC does not drop it`, jobs.py:189-190). For Phase 10 the monitor task is sibling, not owned by the Job — a module-level `_extract_monitor_tasks: set[asyncio.Task]` with `task.add_done_callback(self._extract_monitor_tasks.discard)` is the robust idiom.

### Pattern 4: Structured Error Dicts (Phase 6 D-04 / Phase 8 D-18 / Phase 9 D-15)

**What:** MCP tools NEVER raise. They return a dict that either is a success snapshot or matches one of the locked error shapes.

**Phase 10 error shapes (D-22):** six locked shapes. Implementation pattern matches `tools/jobs.py:139-145` — `try / except (ValueError, TypeError) as e: return {"error": ..., "field": ..., "hint": str(e)}`.

### Anti-Patterns to Avoid

- **DON'T register `_UNBLOB_SPEC` in `jobs.py` body.** The Phase 9 ship-with specs (`_sleep_probe`, `_log_burst_probe`, `capa`) live in `jobs.py` for bootstrapping convenience; Phase 10 specs co-locate with their `build_argv` in `extraction.py` (CONTEXT.md D-19 — "Locked: specs live in `extraction.py`"). This avoids adding a circular import (`jobs.py → extraction.py → jobs.py`).
- **DON'T add a new MCP tool to cancel extractions.** Agents cancel via Phase 9's `cancel_tool_job(job_id)`. The monitor calls it internally on cap-exceed (CONTEXT.md D-17).
- **DON'T extend `JobStatus` to add `cap_exceeded`.** That literal lives only in `_mare_meta.json`; the underlying Phase 9 job status is `cancelled` (CONTEXT.md domain section line 67-73).
- **DON'T use `Path.iterdir()` for the symlink-quarantine walk.** Use `os.scandir(...)` with `follow_symlinks=False`-semantics and explicit `os.readlink` (D-15). On some filesystems `Path.iterdir` may attempt to `lstat` differently than expected; `os.scandir` is the documented no-follow primitive.
- **DON'T parse unblob's stderr line-by-line for progress.** unblob uses Rich Progress which writes terminal-control sequences (cursor moves, line erases), not newline-terminated progress lines. The Rich `redirect_stderr=True` default also makes the surface even worse. `_UNBLOB_SPEC.progress_parser = None` (matching `capa`'s Q1 finding — CONTEXT.md `<canonical_refs>` Phase 9 D-16..D-18 reference).
- **DON'T call `subprocess.run` or `os.system` directly.** Sync wrappers use `mcp_gateway.runner.run_tool`; async wrappers use `tools.jobs.start_tool_job`. Both layers enforce the argv-only contract (CLAUDE.md "argv-only" / Phase 6 D-04 / T-6-02 threat).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Subprocess with timeout + cwd-confine + log capture | Custom `asyncio.create_subprocess_exec` plumbing | `mcp_gateway.runner.run_tool` (sync wrappers) or `tools_jobs.start_tool_job` (async wrappers) | Phase 6 D-01..D-04 already implements 12-key result dict, process-group SIGKILL, log capture, head truncation. Reinventing it forks the audit boundary. |
| Path-traversal rejection | String prefix checks, `..` regex | `mcp_gateway.artifacts_io.confine_to(case_dir, path)` | Verified canonical via `Path.resolve()` + `is_relative_to`; rejects NUL byte and non-existent case_dir; tested in 16 cases (Phase 6 SC). |
| Sample resolution (sha256 or path → absolute) | Manual `if SHA256_RE: ...` | `mcp_gateway.tools.samples.resolve_sample(s)` | Enforces ALLOWED_PREFIXES allowlist (`uploads`/`examples`/`status`); T-02-PATHTRAVERSAL mitigation. |
| sha256 hashing of large files | Loading file via `Path.read_bytes()` then `hashlib.sha256` | Streaming `hashlib.sha256` with chunked reads — pattern from `uploads.py:103-126` | A multi-GB child file blows RAM if read whole; the upload handler is the verified template. |
| Atomic file write (re-upload during promotion) | Direct `open + write + close` on the final path | `tempfile.NamedTemporaryFile(dir=upload_dir, prefix=".incoming-", suffix=".bin")` + `os.rename` — pattern from `uploads.py:107-127` | Same FS + same dir guarantees atomic rename; crash-safety preserved. |
| Job spec registration | New dict / list / discovery code | `register_job_tool(spec)` + `JOB_TOOL_REGISTRY` | Phase 9 D-02/D-03 already implements the registry with idempotency check and `list_tool_jobs(state="_specs")` discovery surface. |
| ANSI-strip on tool output | New regex / library | `mcp_gateway.runner._ANSI_ESCAPE` or `mcp_gateway.jobs._ANSI_ESCAPE_TEXT` | Pattern 2 / Pattern 7 from Phase 6. Either inline (CONTEXT.md discretion) or import — verify export naming first (Phase 9 uses underscore-prefixed `_strip_ansi`). |
| UTF-8 boundary truncation | Naive `text[:N]` | `mcp_gateway.runner._truncate_to_utf8_boundary` / `mcp_gateway.jobs._truncate_for_response` | Naive truncation can split codepoints and break `.decode()`; Phase 6 has verified helpers. |
| Slug validation | Custom regex per module | `mcp_gateway.artifacts_io._validate_slug` (or reuse `tool_log_path` which validates transitively) | Shared regex `^[a-z0-9][a-z0-9_-]{0,39}$`; matches engine names `binwalk` / `unblob` / `upx` cleanly. |
| New-case creation | Re-implement case-dir layout | Existing `init_case(sample=<sha256>, new=True)` MCP tool — call programmatically (FastMCP tools are also callable Python coroutines) | The `init_status_tree.sh` script (`scripts/init_status_tree.sh`) creates 13 empty artifact files and the canonical `status/<NNN>-<basename>/` shape; reuse is mandatory. |

**Key insight:** Phase 10 has near-zero novel infrastructure. The seven new tools are 90% existing-machinery composition + 10% three new primitive functions (`extraction_dir`, `quarantine_symlinks`, `start_extract_monitor`) and one new sidecar shape (`_mare_meta.json`). Any plan task that proposes building a new subprocess layer, new path-safety helper, new hashing routine, or new case-dir creator is **wrong** and should be sent back to consume an existing primitive.

## Common Pitfalls

### Pitfall 1: Binwalk Version Drift (HIGH severity)

**What goes wrong:** Wrapper code targets `binwalk -B` text output (binwalk v2) but the Dockerfile installs `binwalk3` (which logs JSON via `-l <path>` instead). Tests pass locally on dev hosts with binwalk2 but fail in the container.

**Why it happens:** The Dockerfile currently installs `binwalk` (apt v2.4.3). Kali also has `binwalk3` (v3.1.0). The names are similar; the CLIs differ enough that a wrapper written against one will fail-loud against the other.

**How to avoid:** **Switch the Dockerfile to `binwalk3` as part of Phase 10's Wave 0 / Wave 1**, write the wrapper against binwalk3's documented surface (`-l <json>` for log, `-E` for entropy, `-e -M -C <dir> -d <depth>` for extract), and add a startup capability probe (`binwalk --version | grep -E '^binwalk v?3'`) that fails-loud if v2 is installed. Document in `_UNBLOB_SPEC.description` / `_BINWALK_EXTRACT_SPEC.description` that binwalk3 is the target.

**Warning signs:** `binwalk` apt package version on the build machine reports `2.x`. Wrapper test output shows column mismatch in the parser. `binwalk --help` does not list `-l` (binwalk2 uses `-f` for logging).

### Pitfall 2: Symlink Quarantine Race (MEDIUM severity)

**What goes wrong:** Agent calls `list_extracted_files` (or browses Resources) BEFORE the monitor's post-terminal hook runs `quarantine_symlinks`. The Phase 7 Resources walker follows symlinks; an attacker firmware extracts a symlink to `/etc/shadow` and the walker exposes its contents.

**Why it happens:** The job is terminal but the monitor hasn't yet swept symlinks. The monitor's `interval_s` is 5s default; in the worst case the agent polls `get_tool_job` immediately on job-terminal and races the sweep.

**How to avoid:** `quarantine_symlinks` runs in the monitor's post-terminal hook BEFORE the final `update_meta` (D-15 timing rule). Tests must assert that for a job that exits `succeeded`, `_mare_meta.json["status"]` does not flip to `succeeded` (or any terminal value other than `running`) until AFTER the sweep is complete. Agents that need to be sure should poll `_mare_meta.json["status"]` (which is updated by the monitor) rather than relying solely on the Phase 9 job status (which is updated by the registry's drive task before the monitor sweeps).

**Warning signs:** A test that opens a symlink-bearing fixture as the unblob target and then immediately browses the extraction dir before the monitor poll cycle completes.

### Pitfall 3: Unblob Progress Parsing Mirage (LOW severity)

**What goes wrong:** Plan assumes unblob emits parseable progress on stderr; the `progress_parser` is wired up; in practice it never fires because unblob uses Rich's Progress widget which writes ANSI cursor-move sequences, not newline-terminated text.

**Why it happens:** unblob v26.x uses the Rich library's progress bar; Rich `redirect_stderr=True` is the default. The output is visually a progress bar but byte-wise it's a stream of `\r` + ANSI escapes that never contains a `\n`-terminated parseable line.

**How to avoid:** `_UNBLOB_SPEC.progress_parser = None` (CONTEXT.md D-11 already says binwalk_extract's parser is None; this research recommends None for unblob too). Document in the spec description: "no parseable progress — poll `get_tool_job` for status." This matches the Phase 9 `capa` spec's Q1 finding verbatim (`jobs.py:374`).

**Warning signs:** A unit test feeds Rich-formatted bytes to `_parse_unblob_progress` and the parser returns `None` on every line. Or stderr capture in the log shows `^[[2K^[[1A` patterns rather than text.

### Pitfall 4: Phase 9 Job Cap Reached Before Monitor Can Cancel (MEDIUM severity)

**What goes wrong:** `MAX_JOBS_INFLIGHT=4` is the Phase 9 default. If 4 unblob jobs are in flight and a 5th wrapper call dispatches, Phase 9 returns `JobCapReached.to_dict()` — but the Phase 10 wrapper has already minted `extraction_dir` and written the `running` sidecar. The extraction dir is orphaned (no job ever ran) and the sidecar will sit at `running` forever because there's no monitor.

**How to avoid:** In the wrapper flow (D-13), check `start_tool_job`'s return for `{"error": "job cap reached", ...}` BEFORE spawning the monitor. On error: delete the empty extraction dir, write `_mare_meta.json` with `status: "failed"` + a one-shot termination reason, return the Phase 9 error dict unchanged.

**Warning signs:** A test runs N+1 unblob jobs (N = `MAX_JOBS_INFLIGHT`) and the (N+1)th wrapper call leaves a `running`-status sidecar with no associated job.

### Pitfall 5: `init_case` Programmatic Call Side Effects (MEDIUM severity)

**What goes wrong:** `promote_extracted_sample` calls `init_case(sample=<sha256>, new=True)` programmatically. `init_case` is defined inside `tools/artifacts.py::register(mcp)` as a closure under the `@mcp.tool()` decorator — it's not directly importable as a Python function from outside the register closure.

**Why it happens:** Phase 1-4 v1.0 used a different pattern from Phase 7+ (`register_all_tools` calls `register(mcp)` which defines tools inline). Phase 10 calling `init_case` requires either (a) refactoring `init_case` out of the closure into a module-level coroutine that `register` decorates (the Phase 7+ pattern, e.g. `tools/jobs.py:start_tool_job`), OR (b) shelling out to `scripts/init_status_tree.sh` directly via `subprocess_runner.run_script` — bypassing the MCP tool.

**How to avoid:** Recommend option (a) — small refactor of `tools/artifacts.py:init_case` to module-level coroutine, preserving the `@mcp.tool()` registration via `mcp.tool()(init_case)` in `register`. This matches Phase 7-08's pattern and unlocks programmatic reuse. If the planner deems (a) out of scope for Phase 10, option (b) shells out via `subprocess_runner.run_script(["bash", str(SCRIPTS / "init_status_tree.sh"), <upload_path>, "--new"], cwd="/agent", timeout=FAST_TIMEOUT_S)` — same as `artifacts.py:30-33`. Either way the planner must NOT call `init_case` as if it were importable today.

**Warning signs:** A wave-1 plan task that does `from mcp_gateway.tools.artifacts import init_case` — that import will fail.

### Pitfall 6: `_mare_meta.json` Concurrent Writers (LOW severity)

**What goes wrong:** The wrapper writes initial meta (`status=running`), then the monitor writes updates every 5s (`extract_bytes_total`, `monitor_polls`), and the post-terminal hook writes the final state (`status=succeeded`, `completed_at`, ...). If `update_meta` is naive `read → mutate → write`, two updates can race and one loses fields.

**How to avoid:** `update_meta` should be `read → mutate → atomic-write` (write to tmp + rename). Same pattern as the upload atomic move. Phase 8's `r2_sessions` transcript writes are append-only and so don't hit this, but the Phase 10 sidecar is read-modify-write. The monitor is the only mutator after the wrapper returns; the wrapper writes once at dir creation; the monitor writes ~once per `EXTRACT_MONITOR_INTERVAL_S`. With a single monitor task per extraction the race is between monitor and external readers — making writes atomic prevents readers from seeing partial JSON.

**Warning signs:** A `list_extracted_files` call returns and the meta_path contains a partial JSON document because a write was interrupted.

### Pitfall 7: `du -sb` vs `os.walk` Counting Discrepancy (LOW severity)

**What goes wrong:** CONTEXT.md D-17 line 854 says "prefer `os.walk` + `os.stat` ... skip symlinks during the walk (matches `du -sb -P`); count regular files only." But `du` by default counts disk-block usage including hardlinks once and skips symlink targets. The Python equivalent `sum(st.st_size for f in os.walk(...))` counts each regular file once; if the extraction creates hardlinks they're double-counted relative to `du`.

**How to avoid:** Track inodes seen (`seen: set[int]`) during the walk; skip duplicates. Or document that the cap is an upper bound (slightly over-conservative). For Phase 10 the upper-bound semantics are fine — extraction tools almost never produce hardlinks; the rare case where they do (squashfs unpack) means the cap fires slightly earlier than `du -sb` would, which is the safe direction.

**Warning signs:** A test fixture deliberately uses hardlinks and the monitor cap fires at half the expected byte count.

### Pitfall 8: `confine_to` on Pre-existing Extraction Dir (LOW severity)

**What goes wrong:** `confine_to(case_dir, extraction_dir)` resolves both paths with `Path.resolve(strict=False)` for the target. If the extraction dir doesn't exist YET when `_build_unblob_argv` is called, the resolve still works (strict=False). But if it does exist, `Path.resolve()` follows symlinks during resolution — and if the case_dir was set up with a symlinked extraction tree (unusual but possible), the resolved path may escape.

**How to avoid:** The wrapper-side flow (D-13) mints `extraction_dir` BEFORE building argv, so by the time `_build_unblob_argv` runs, the dir exists and is `Path.resolve(strict=True)`-able. The `extraction.extraction_dir()` helper does `target.resolve(strict=True)` after `mkdir(exist_ok=False)` — this enforces the contract.

**Warning signs:** A test that symlinks `case_dir/extracted` to somewhere outside case_dir and expects the wrapper to fail-loud. (It should — `ensure_subdir(case_dir, "extracted")` calls `mkdir(parents=False, exist_ok=True)` and then the subsequent symlink follow would land outside case_dir; `confine_to` catches it.)

### Pitfall 9: Promotion of Symlink-Quarantine Sentinel (LOW severity — covered by D-22)

**What goes wrong:** Agent calls `promote_extracted_sample(parent, "extracted/unblob-.../usr/lib/libc.so.6.symlink-target.txt")`. The sentinel file looks like a regular text file but represents a symlink that was quarantined. Promoting it as a "sample" makes no sense.

**How to avoid:** D-22 has the explicit error shape: `{"error": "child is a symlink quarantine sentinel (.symlink-target.txt) — read it for the original target, do not promote it", "child_path": str}`. Implement the check after `confine_to` and before `hashlib.sha256` — short-circuit on suffix match.

### Pitfall 10: Test-Host Tool Availability (LOW severity)

**What goes wrong:** Wave 0 / 1 tests that exercise real binwalk/unblob/upx fail on developer hosts without those tools installed. Pytest collection fails (RED stub) cleanly, but slow-integration tests need a graceful skip.

**How to avoid:** `conftest.py` defines `_require_binwalk_or_skip`, `_require_unblob_or_skip`, `_require_upx_or_skip` fixtures that `pytest.skip("binwalk not on PATH")` when the tool is missing. Slow-integration tests marked `@pytest.mark.slow + @pytest.mark.usefixtures("_require_<tool>_or_skip")`. Pure-function tests (argv builders, parsers, monitor logic with mocked subprocess) don't use these gates — they run on every dev host. Same pattern as Phase 7-05 / 7-06 / 7-07 (host-missing setfacl skips).

## Code Examples

### Example 1: `_build_binwalk_extract_argv` for binwalk3 (Pure Function)

```python
# extraction.py
# Source: Kali binwalk3 v3.1.0 CLI verified at https://www.kali.org/tools/binwalk3/
def _build_binwalk_extract_argv(case_dir: Path, kwargs: dict) -> list[str]:
    """Pure function — build argv for binwalk3 recursive extraction."""
    from mcp_gateway.tools import samples  # local import per jobs.py:363 precedent
    sample = samples.resolve_sample(kwargs["sample"])
    extraction_path = Path(kwargs["extraction_dir"])
    if not extraction_path.is_relative_to(case_dir):
        raise ValueError(f"extraction_dir not under case_dir: {extraction_path}")
    depth = int(kwargs.get("depth", 8))
    matryoshka = bool(kwargs.get("matryoshka", True))
    # binwalk3 flags:
    #   -e / --extract    Automatically extract known file types
    #   -M / --matryoshka Recursively scan extracted files
    #   -C <dir>          Custom extraction directory
    #   -l <path>         Log JSON results to file
    #   -q / --quiet      Suppress stdout output (keep our log clean)
    # NOTE: binwalk3 does NOT expose -d/--depth — depth is implicit via -M recursion.
    #       If the planner wants depth control, the script wrapping binwalk3 must
    #       enforce it post-hoc (count extracted dirs deeper than N and prune).
    argv = [
        "binwalk",
        "-e",
        "-C", str(extraction_path),
        "-l", str(extraction_path / "binwalk-report.json"),
        "-q",
        sample,
    ]
    if matryoshka:
        argv.insert(1, "-M")
    return argv
```

**Verification note:** The binwalk3 CLI flag set as documented at kali.org excludes a top-level `--depth` flag. If depth control is mandatory, the planner has three options: (1) drop the `matryoshka` flag entirely (recursion off → depth 0); (2) post-process the extraction tree to prune at depth N; (3) require the planner to verify against the in-container `binwalk --help` output (Pitfall 1 capability probe is the right place). This contradicts CONTEXT.md D-11's stated `kwargs_schema` for `binwalk_extract` which includes `depth`. **Recommend planner mark this as an open question for the discuss phase OR drop depth from binwalk's schema and document as a known limitation.** [CITED: https://www.kali.org/tools/binwalk3/ ; https://manpages.debian.org/testing/binwalk/binwalk.1.en.html shows `-d, --depth` for binwalk2 only]

### Example 2: `quarantine_symlinks` (D-15 + D-16)

```python
# extraction.py
def quarantine_symlinks(extraction_dir: Path) -> tuple[int, list[str]]:
    """Recursively replace symlinks with .symlink-target.txt sentinels.

    Walks via os.scandir (does NOT follow symlinks). Idempotent.
    Returns (count, list_of_quarantined_paths_relative_to_extraction_dir).
    """
    count = 0
    paths: list[str] = []
    iso = _utc_now_iso()
    for root, dirs, files in os.walk(str(extraction_dir), followlinks=False):
        # os.walk(followlinks=False) is the default; explicit for clarity.
        # Find symlinks in `files` AND `dirs` (a symlinked dir shows up in dirs).
        for name in list(files) + list(dirs):
            full = Path(root) / name
            if not full.is_symlink():
                continue
            try:
                as_written = os.readlink(str(full))
                resolved = os.path.realpath(str(full))
            except OSError as exc:
                log.warning("[extraction] readlink failed for %s: %s", full, exc)
                continue
            rel = str(full.relative_to(extraction_dir))
            body = (
                "SYMLINK QUARANTINE\n"
                f"Original symlink (relative within extraction): {rel}\n"
                f"Target (as-written by extractor):              {as_written}\n"
                f"Resolved target (canonical absolute):          {resolved}\n"
                f"Quarantined: {iso}\n"
                "Reason: Symlinks outside an extraction can read host files via the MCP Resources walker; "
                "quarantining preserves the original link metadata as plain text without enabling traversal.\n"
            )
            sentinel = full.parent / f"{full.name}.symlink-target.txt"
            sentinel.write_text(body, encoding="utf-8")
            full.unlink()
            count += 1
            paths.append(rel)
    return count, paths
```

**Source pattern:** matches the documented body format in CONTEXT.md D-16 verbatim. `os.walk(followlinks=False)` is the safe default.

### Example 3: Atomic Re-Upload (`extraction.write_upload` for D-06 step 4)

```python
# extraction.py
# Source pattern: uploads.py:107-127 (tempfile + os.rename atomic move)
def write_upload(child_path: Path, target_basename: str) -> tuple[str, Path]:
    """Stream child_path into <UPLOADS_ROOT>/<sha256>/<basename> atomically.

    Returns (sha256_hex, final_absolute_path).
    Idempotent: if <UPLOADS_ROOT>/<sha256>/<basename> already exists, returns it
    without rewriting.
    """
    from mcp_gateway.tools.samples import UPLOADS_ROOT
    from mcp_gateway.uploads import _is_invalid_filename, MAX_BYTES

    if _is_invalid_filename(target_basename):
        raise ValueError(f"invalid target_basename: {target_basename!r}")

    sha = hashlib.sha256()
    size = 0
    UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        dir=str(UPLOADS_ROOT), delete=False, prefix=".incoming-", suffix=".bin"
    )
    try:
        try:
            with open(child_path, "rb") as src:
                while True:
                    chunk = src.read(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError(f"child exceeds {MAX_BYTES} bytes")
                    sha.update(chunk)
                    tmp.write(chunk)
        finally:
            tmp.close()
    except Exception:
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass
        raise

    digest = sha.hexdigest()
    target_dir = UPLOADS_ROOT / digest
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / target_basename
    if target.exists():
        # Dedup: same content already present.
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass
    else:
        shutil.move(tmp.name, str(target))
        os.chmod(target, 0o644)
    return digest, target
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| binwalk v2 (Python) | binwalk v3 (Rust) | Original author EOL'd v2 2025-12-12; v3 active dev | Different CLI: `-l <json>` instead of `-f <log>`; no `-d/--depth` flag (recursion controlled by `-M` alone); 2-5x faster; 60-80% fewer FPs. Plan must target binwalk3. |
| Single CLI `--log <file>` text dump | JSON log via `binwalk3 -l <path>` | binwalk3 release | Machine-readable parser path; no need for fragile text-row regex. |
| Unblob v23.x with `--extract-dir` | Unblob v26.x with `-e <dir>` (alias preserved) | Continuous (last release 26.3.30 on 2026-03-30) | The short flag `-e` is preferred per current `unblob/docs/guide.md`. Long form `--extract-dir` still accepted. |
| Hand-rolled progress parsing on Rich-emitting tools | Tier-2 poll-side push only (`ctx.report_progress` triggered by `get_tool_job` when the underlying tool DOES emit) | Phase 9 D-16..D-18 Q1 finding (capa) | For Phase 10 unblob + binwalk_extract: `progress_parser=None`. Agents poll for status. |
| `MastraMCPClient` (deprecated) | `MCPClient` from `@mastra/mcp` | Mastra 1.3+ | N/A for Phase 10 server-side, but documented in CLAUDE.md for external clients. |

**Deprecated/outdated:**
- **binwalk v2.x apt package** — EOL 2025-12-12. Phase 10 must migrate. [CITED: kali.org/tools/binwalk/]
- **`subprocess.run(shell=True)`** — forbidden by Phase 6 D-04 / T-6-02. Use argv-only via `ReToolRunner` / `start_tool_job`. [VERIFIED: existing codebase grep returns zero hits]
- **Manual case-dir creation** — superseded by `init_case(sample=<sha256>, new=True)`. [VERIFIED: `tools/artifacts.py:27`]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `binwalk3` ships in the same `kalilinux/kali-rolling` repo as `binwalk` and can be installed via apt with no extra config | Standard Stack | Dockerfile change fails build; planner has to add a custom repo or rollback to binwalk2. Mitigation: verify via `apt-cache policy binwalk3` in a planner-stage Dockerfile probe. [CITED: pkg.kali.org/pkg/binwalk3 says "migrated to kali-rolling 2026-03-09" — should be available, but build-time verification is the safe path.] |
| A2 | binwalk3 has no `-d/--depth` flag and recursion is controlled solely by `-M/--matryoshka` | Code Examples (Example 1), Pitfall in same | If wrong, the `binwalk_extract` JobToolSpec `kwargs_schema["depth"]` is ignored (or rejected by binwalk). Plan should either remove `depth` from schema OR post-process. Mitigation: planner runs `binwalk --help` in container as Wave-0 verification. [CITED: kali.org/tools/binwalk3 lists flags; `--depth` is NOT listed there.] |
| A3 | Unblob v26.x uses Rich Progress that emits non-line-parseable ANSI on stderr | Pitfall 3, Code Examples Example 1 | If unblob actually emits parseable progress lines, Phase 10 loses a free signal (progress reporting); functionality is unaffected (status polling still works). Mitigation: run `unblob --report /tmp/r.json -e /tmp/u sample.bin 2>&1 | head -200` against a real firmware to confirm stderr surface. |
| A4 | Calling `init_case` programmatically requires a small `tools/artifacts.py` refactor OR a fall-back to `subprocess_runner.run_script("init_status_tree.sh", ...)` | Pitfall 5 | If `init_case` is already module-level callable, no refactor needed and the wrapper is simpler. Mitigation: planner reads `tools/artifacts.py:27` — current code is a closure inside `register(mcp)`, confirming refactor or shellout is necessary. [VERIFIED: file read in this research session, line 27 shows `async def init_case` defined inside `def register(mcp)` body.] |
| A5 | The Phase 7 D-26 Resources walker (depth ≤ 2) does NOT special-case symlinks — it follows them by default | Pitfall 2 | If the walker already refuses symlinks, the quarantine sweep is belt-and-suspenders rather than mandatory. Mitigation: planner reads `tools/resources.py` to confirm symlink-following behavior; CONTEXT.md `<specifics>` line 1247 asserts "Resources walker follows them by default" — treat that as locked unless source disagrees. |
| A6 | `default_timeout_s=3600.0` for unblob and `1800.0` for binwalk_extract are reasonable per CONTEXT.md D-11 | Code Examples Example 1 | If firmware in practice exceeds 1h for unblob, jobs killed_timeout before completing. User must raise `MCP_GATEWAY_JOB_TIMEOUT_S` per-call via `timeout=` kwarg. Mitigation: doc disclaimer in spec description; CONTEXT.md D-11 explicitly states `default_timeout_s=3600.0` for unblob. |
| A7 | `os.walk(followlinks=False)` is the correct primitive (the default; explicit for safety) | Code Examples Example 2 | If `followlinks=True` is the default somewhere, the quarantine sweep itself follows symlinks. Mitigation: Python stdlib docs verify `followlinks=False` is the default; explicit kwarg in Example 2 makes it visible. [VERIFIED: Python 3.11+ stdlib docs: `os.walk(top, ..., followlinks=False)` is the default signature.] |

**If this table is empty:** Not empty — A1, A2, A4 are the highest-risk assumptions and the planner should resolve them in Wave 0 via container probes.

## Runtime State Inventory

> Phase 10 is NOT a rename/refactor/migration phase. **Section omitted per template guidance** (no stored data, OS-registered state, or build artifacts being renamed). All new state (case-dir extraction trees, `_mare_meta.json` sidecars, `<UPLOADS_ROOT>/<sha256>/` entries) is created fresh by Phase 10 code; nothing pre-existing changes name or location.

## Environment Availability

| Dependency | Required By | Available in target container | Version | Fallback |
|------------|------------|-------------------------------|---------|----------|
| Python 3.11+ | Gateway runtime | ✓ | 3.11+ (Dockerfile pin) | — |
| `mcp` Python SDK 1.27.x | FastMCP gateway | ✓ | 1.27 | — |
| `binwalk` (apt) | `run_binwalk` | ✓ (but EOL — see migration) | 2.4.3 currently; SHOULD migrate to `binwalk3` 3.1.0 | binwalk2 fallback parser if migration is deferred (NOT RECOMMENDED) |
| `binwalk3` (apt) | `run_binwalk` after migration | ✗ (not in current Dockerfile) | 3.1.0-0kali4 available in kali-rolling | Stay on binwalk2 with EOL acknowledgement |
| `unblob` (pip) | `run_unblob` | ✓ (Dockerfile:61 `unblob`) | 26.x current (verify via `unblob --version`) | None — required |
| `upx-ucl` (apt) | UPX wrappers | ✓ (Dockerfile:53 `upx-ucl`) | 4.2.2-3 | None — required |
| `7z` / `unar` / `lz4` / `zstd` / `e2fsprogs` / `unzip` | unblob's external extractors | ✓ (Dockerfile:51,53,55 install these) | as per Kali rolling | Reduced format coverage if missing |
| `sasquatch` (squashfs hardened extractor for unblob) | unblob squashfs handler | ✗ (NOT in current Dockerfile — uses standard squashfs-tools if installed) | N/A | unblob falls back to whatever squashfs tool is available; squashfs extraction may fail or be lossy [CITED: https://github.com/onekey-sec/unblob/blob/main/docs/installation.md] |
| Python stdlib `asyncio`, `hashlib`, `json`, `os`, `secrets`, `tempfile`, `shutil` | All Phase 10 code | ✓ | 3.11+ | — |

**Missing dependencies with no fallback:**
- None blocking — every required tool is either present (unblob, upx-ucl, binwalk2) or migrate-able (binwalk2 → binwalk3 via Dockerfile edit).

**Missing dependencies with fallback:**
- `sasquatch` is not installed; unblob falls back to system squashfs-tools (if any). Recommendation: planner adds `apt-get install -y squashfs-tools` to the Dockerfile alongside the binwalk3 migration, or installs sasquatch from the onekey-sec releases (out of scope for v1.1 — out-of-the-box `unblob`'s default extractors are sufficient for most firmware).
- `binwalk3` is missing from the current image; add it via Dockerfile edit (recommended Wave-1 task).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (already pinned in `mcp-gateway/pyproject.toml`, Phase 6+ precedent) |
| Config file | `mcp-gateway/pyproject.toml` (Phase 6 D-XX registers `slow` marker; Phase 9 D-XX adds `capa_slow` precedent) |
| Quick run command | `pytest mcp-gateway/tests/extraction -x --no-header -m "not slow"` (~30s target — pure-function + mocked-subprocess) |
| Full suite command | `pytest mcp-gateway/tests/ -x --no-header` (includes Phase 10 slow integration when tools are present) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXTR-01 | `run_binwalk(case_dir, sample, mode="signatures")` returns 12-key + `signatures` rows | unit (mock) | `pytest mcp-gateway/tests/extraction/test_run_binwalk.py::test_signatures_mode_parses_rows -x` | ❌ Wave 0 |
| EXTR-01 | `run_binwalk(..., mode="entropy")` returns 12-key + `entropy` rows | unit (mock) | `pytest .../test_run_binwalk.py::test_entropy_mode_parses_rows -x` | ❌ Wave 0 |
| EXTR-01 | `run_binwalk(..., mode="extract")` dispatches job, returns 25-key + `mode="extract"` + `job_id` + `extraction_dir` | integration | `pytest .../test_run_binwalk.py::test_extract_mode_dispatches_job -x` | ❌ Wave 0 |
| EXTR-01 | binwalk extraction confined to `case_dir/extracted/binwalk-<ts>-<rand4>/` (D-07) | unit | `pytest .../test_extraction_dir.py::test_binwalk_engine_prefix -x` | ❌ Wave 0 |
| EXTR-02 | `run_unblob(case_dir, sample)` always returns a Phase 9 25-key job snapshot with `engine="unblob"`, `mode="unblob"`, `extraction_dir` | integration | `pytest .../test_run_unblob.py::test_dispatches_job_with_meta -x` | ❌ Wave 0 |
| EXTR-02 | unblob job's `--report report.json` is parsed and embedded in `result["unblob_report"]` once job terminal | integration (slow + `_require_unblob_or_skip`) | `pytest .../test_run_unblob.py::test_report_json_parsed -x -m slow` | ❌ Wave 0 |
| EXTR-03 | `run_upx_test` parses `Not packed by UPX` → `is_upx_packed=False`, `test_result="not_packed"` | unit (mock stderr) | `pytest .../test_run_upx.py::test_test_not_packed -x` | ❌ Wave 0 |
| EXTR-03 | `run_upx_list` parses table columns into `rows: list[dict]` | unit (mock stderr) | `pytest .../test_run_upx.py::test_list_parses_columns -x` | ❌ Wave 0 |
| EXTR-03 | `run_upx_unpack` writes unpacked binary under `case_dir/extracted/upx-<ts>-<rand4>/` | integration (slow + `_require_upx_or_skip`) | `pytest .../test_run_upx.py::test_unpack_writes_output -x -m slow` | ❌ Wave 0 |
| EXTR-04 | `list_extracted_files(case_dir)` enumerates extractions across all three engines via dir-name + sidecar | unit (fake tree) | `pytest .../test_list_extracted_files.py::test_engine_agnostic_enumeration -x` | ❌ Wave 0 |
| EXTR-04 | Per-extraction file list cap (`MAX_FILES_PER_EXTRACTION`) enforced; `files_truncated=True` on overflow | unit (fake tree with 5001 files) | `pytest .../test_list_extracted_files.py::test_files_per_extraction_cap -x` | ❌ Wave 0 |
| EXTR-04 | Cross-extraction `limit` cap enforced; top-level `truncated=True` | unit | `pytest .../test_list_extracted_files.py::test_limit_truncation -x` | ❌ Wave 0 |
| EXTR-04 | `engine=` filter narrows by directory-name prefix | unit | `pytest .../test_list_extracted_files.py::test_engine_filter -x` | ❌ Wave 0 |
| EXTR-04 | `include_quarantined=False` strips `.symlink-target.txt` entries | unit | `pytest .../test_list_extracted_files.py::test_exclude_quarantined -x` | ❌ Wave 0 |
| EXTR-05 | `promote_extracted_sample` re-uploads via sha256 + creates new case dir + writes `_lineage.json` | integration | `pytest .../test_promote_extracted_sample.py::test_promotion_flow -x` | ❌ Wave 0 |
| EXTR-05 | Same child promoted twice → idempotent reuse (same case_dir, `idempotent_reuse=True`) | integration | `pytest .../test_promote_extracted_sample.py::test_idempotent_by_sha256 -x` | ❌ Wave 0 |
| EXTR-05 | `force_new=True` bypasses idempotency | integration | `pytest .../test_promote_extracted_sample.py::test_force_new_bypasses_idempotent -x` | ❌ Wave 0 |
| EXTR-05 | Rejects child outside `<parent_case_dir>/extracted/` with `error="child_path must live under parent case's extracted/"` | unit | `pytest .../test_promote_extracted_sample.py::test_rejects_outside_extracted -x` | ❌ Wave 0 |
| EXTR-05 | Rejects `.symlink-target.txt` sentinels | unit | `pytest .../test_promote_extracted_sample.py::test_rejects_symlink_sentinel -x` | ❌ Wave 0 |
| EXTR-06 | `quarantine_symlinks(dir)` replaces symlinks with `.symlink-target.txt` containing the 5-line body (D-16) | unit | `pytest .../test_quarantine_symlinks.py::test_sentinel_body_format -x` | ❌ Wave 0 |
| EXTR-06 | Quarantine is idempotent (re-run produces zero new sentinels) | unit | `pytest .../test_quarantine_symlinks.py::test_idempotent -x` | ❌ Wave 0 |
| EXTR-06 | `start_extract_monitor` fires `.MARE_EXTRACT_CAP_EXCEEDED` marker + cancels job + updates meta `cap_exceeded=True` on cap exceed | integration (fast, sleep-probe based) | `pytest .../test_extract_monitor.py::test_cap_exceeded_cancels_job -x` | ❌ Wave 0 |
| EXTR-06 | Monitor exits cleanly on job-terminal (no leak) | integration | `pytest .../test_extract_monitor.py::test_clean_exit_on_terminal -x` | ❌ Wave 0 |
| EXTR-06 | Promotion sha256 recomputed (not trusted from parent metadata) | unit | `pytest .../test_promote_extracted_sample.py::test_sha256_recomputed -x` | ❌ Wave 0 |
| D-23 | Disclaimer text appears verbatim in `run_unblob.__doc__`, `run_binwalk.__doc__`, `list_extracted_files.__doc__`, `promote_extracted_sample.__doc__` | unit | `pytest .../test_disclaimers.py -x` | ❌ Wave 0 |
| D-01 | `EXPECTED_TOOLS` bumped 47 → 54 invariant | unit | `pytest .../test_tool_list_phase10.py -x` | ❌ Wave 0 (additionally update existing `mcp-gateway/tests/test_tool_list.py`) |
| D-22 | All six structured error shapes round-trip (`error` key present, `hint` key present, never raises) | unit | `pytest .../test_run_unblob.py::test_errors_structured` + `pytest .../test_promote_extracted_sample.py::test_errors_structured` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest mcp-gateway/tests/extraction -x --no-header -m "not slow"` (pure-function + mocked-subprocess — ~30s target).
- **Per wave merge:** `pytest mcp-gateway/tests/extraction -x --no-header` (includes slow-integration with `_require_<tool>_or_skip` gates).
- **Phase gate:** Full suite `pytest mcp-gateway/tests/` green before `/gsd-verify-work`. Existing Phase 7-9 invariants (`test_tool_list.py::test_tool_count_in_range`, Phase 7 collision check, Phase 9 disclaimer regression) MUST continue passing.

### Wave 0 Gaps

- [ ] `mcp-gateway/tests/extraction/__init__.py` — package marker
- [ ] `mcp-gateway/tests/extraction/conftest.py` — `_require_binwalk_or_skip`, `_require_unblob_or_skip`, `_require_upx_or_skip` fixtures + fake extraction-tree builder helper
- [ ] `mcp-gateway/tests/extraction/test_extraction_dir.py` — `extraction.extraction_dir()` naming + rand4 collision
- [ ] `mcp-gateway/tests/extraction/test_meta_sidecar.py` — `write_meta`/`update_meta`/`read_meta` semantics + atomic-write race
- [ ] `mcp-gateway/tests/extraction/test_quarantine_symlinks.py` — D-15/D-16 sentinel body + idempotency + no-follow walk
- [ ] `mcp-gateway/tests/extraction/test_extract_monitor.py` — D-17 cap-exceeded behavior + clean exit on terminal + monitor poll count
- [ ] `mcp-gateway/tests/extraction/test_list_extracted_files.py` — D-05 caps + engine filter + quarantine flag
- [ ] `mcp-gateway/tests/extraction/test_promote_extracted_sample.py` — D-06/D-13/D-14 atomic + idempotent + force_new + lineage shape
- [ ] `mcp-gateway/tests/extraction/test_run_binwalk.py` — D-02 mode-discriminated returns
- [ ] `mcp-gateway/tests/extraction/test_run_unblob.py` — D-03 job dispatch + report parsing + meta updates
- [ ] `mcp-gateway/tests/extraction/test_run_upx.py` — D-04 parsing for test/list/unpack
- [ ] `mcp-gateway/tests/extraction/test_job_specs_unblob.py` — `_build_unblob_argv` pure function tests (argv shape, sample resolution, depth bounds, extraction_dir confinement)
- [ ] `mcp-gateway/tests/extraction/test_job_specs_binwalk_extract.py` — `_build_binwalk_extract_argv` pure function tests
- [ ] `mcp-gateway/tests/extraction/test_disclaimers.py` — D-23 docstring regression (4 long form + 3 short form)
- [ ] `mcp-gateway/tests/extraction/test_tool_list_phase10.py` — EXPECTED_TOOLS bump 47 → 54 invariant (Rule-1 deviation — also update `mcp-gateway/tests/test_tool_list.py::EXPECTED_TOOLS` to add the seven Phase 10 names)

*(All gaps are Wave-0 RED-stubs per CONTEXT.md D-24 and Phase 6/7/8/9 precedent. Function bodies import the not-yet-existing Phase 10 modules at the function top so pytest collection passes but execution ImportErrors. Wave 1/2 turns them GREEN.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (inherited) | Bearer token validated at the gateway layer (Phase 2 D-XX) — Phase 10 inherits with no additions. |
| V3 Session Management | yes (inherited) | SESS-05 single-tenancy: extractions/jobs shared across same-bearer-token clients (CONTEXT.md D-23 disclaimer). |
| V4 Access Control | yes | `confine_to` + `resolve_case_dir` + `resolve_sample` enforce STATUS_ROOT / UPLOADS_ROOT / EXAMPLES_ROOT containment on every path-accepting kwarg. |
| V5 Input Validation | yes | `JobToolSpec.kwargs_schema` walker (`jobs._validate_kwargs`) validates depth bounds, sample string shape, engine enum; mode literal type validated by FastMCP from `Literal[...]` annotations. |
| V6 Cryptography | yes | sha256 via `hashlib.sha256` for promotion content-addressing — stdlib, never hand-rolled. |
| V12 Files and Resources | **central** | **Phase 10's primary security domain.** Symlink quarantine (D-15/D-16) is a V12 control: extracted symlinks can break out of the case-dir on Resources read. Archive-bomb cap (D-17) is a V12 control against decompression bombs. Atomic re-upload (D-06 step 4) prevents partial-file states. |

### Known Threat Patterns for {Phase 10 stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Symlink in extraction → host file read via Resources walker | Information Disclosure | Recursive `quarantine_symlinks` post-extract; sentinel `.symlink-target.txt` preserves metadata as text (D-15/D-16). |
| Decompression bomb (zip/squashfs/cramfs that expands to TB) | Denial of Service | Periodic `os.walk + os.stat` cap check against `MAX_EXTRACT_BYTES` (D-17); `cancel_tool_job` on exceed; `.MARE_EXTRACT_CAP_EXCEEDED` marker is durable signal. |
| Path traversal in promotion (`child_path = "../../etc/passwd"`) | Tampering / Elevation of Privilege | `confine_to(parent_case_dir, child_path)` rejects; additional check that resolved path is under `<parent_case_dir>/extracted/**` (D-06 step 1). |
| Promotion of attacker-named binary into `<UPLOADS_ROOT>/<sha256>/<basename>` with traversal in basename | Tampering | `uploads._is_invalid_filename(target_basename)` rejects `/`, `\\`, `..`, leading dot, control chars (reused via `extraction.write_upload`). |
| Argv injection through `sample` kwarg containing flags or `--` | Tampering / RCE | `resolve_sample` returns absolute path; argv builders place sample as a POSITIONAL last argument; `--` separator added in `_build_unblob_argv` / `_build_binwalk_extract_argv` if planner decides it's worth the defense-in-depth (recommend YES — `["unblob", ..., "--", sample]`). |
| Race between symlink-creation in extraction and quarantine sweep | Information Disclosure | The job is terminal BEFORE the monitor's post-terminal hook runs `quarantine_symlinks` and finalizes the sidecar; agents that poll `_mare_meta.json["status"] == "succeeded"` are guaranteed to see the post-sweep state (Pitfall 2 mitigation). |
| In-memory job state lost on gateway restart → orphaned extraction dirs | Information Disclosure / Confusion | D-23 docstring disclaimer; durable sidecar + marker preserve enough state that analyst can investigate manually; out-of-scope automatic re-spawn deferred to v1.2. |
| Concurrent meta-sidecar writes corrupt JSON | Tampering / Integrity | Atomic write via tmp + rename in `update_meta` (Pitfall 6 mitigation). |
| Hardlink-counting blind spot in `_du_sb` | Denial of Service (cap not enforced for hardlinked content) | Track inodes in `seen: set[int]` during walk (Pitfall 7); err on the side of over-counting. |

## Sources

### Primary (HIGH confidence)

- `mcp-gateway/src/mcp_gateway/jobs.py` (read in full) — Phase 9 `JobToolSpec` shape, `register_job_tool` API, `JOB_TOOL_REGISTRY`, drain machinery, `_TERMINAL_STATUSES`, status vocabulary
- `mcp-gateway/src/mcp_gateway/runner.py` (read 100 lines + key sections) — `ReToolRunner` contract, env-var constants, `_drain` chunked read
- `mcp-gateway/src/mcp_gateway/artifacts_io.py` (read in full) — `confine_to`, `ensure_subdir`, `tool_log_path`, `EXPANDED_CASE_SUBDIRS` (line 35: "extracted" already present), slug regex
- `mcp-gateway/src/mcp_gateway/uploads.py` (read in full) — `<sha256>/<basename>` layout, atomic tempfile + rename pattern, `_is_invalid_filename` predicate, `MAX_BYTES` cap (line 50)
- `mcp-gateway/src/mcp_gateway/tools/samples.py` (read in full) — `resolve_sample`, `UPLOADS_ROOT` / `EXAMPLES_ROOT` / `STATUS_ROOT`, `ALLOWED_PREFIXES`, SHA256 regex
- `mcp-gateway/src/mcp_gateway/tools/jobs.py` (read in full) — surface pattern (`start_tool_job` body), disclaimer splice via `.replace("{_JOBS_DISCLAIMER}", ...)`, `_require_registry`, register pattern
- `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` (read first 120 lines) — surface pattern, disclaimer splice, module-attribute import idiom (`from mcp_gateway import jobs`)
- `mcp-gateway/src/mcp_gateway/tools/__init__.py` (read in full) — `register_all_tools` ordering (Phase 8 D-05, Phase 9 D-05; Phase 10 adds AFTER `jobs`, BEFORE `backend_passthrough`)
- `mcp-gateway/src/mcp_gateway/tools/artifacts.py` (read first 80 lines) — `init_case` closure (Pitfall 5), `subprocess_runner.run_script` pattern, `SCRIPTS` constant
- `mcp-gateway/tests/test_tool_list.py` (read first 60 lines) — `EXPECTED_TOOLS` set, FastMCP public API for tool listing, Rule-1 deviation precedent
- `Dockerfile` (read lines 40-115) — confirms `binwalk` (v2.4.3 apt), `unblob` (pip), `upx-ucl` (apt) are present; absence of `binwalk3` flagged as Pitfall 1
- `.planning/phases/10-extraction-tier/10-CONTEXT.md` (read in full, 1285 lines) — all 24 decisions, claude's-discretion list, deferred ideas, canonical refs, code context
- `.planning/REQUIREMENTS.md` §Extraction Tier (EXTR-01..EXTR-06) — six requirements verbatim
- `.planning/ROADMAP.md` §Phase 10 — six success criteria
- `.planning/STATE.md` — Phase 5-9 SUMMARY notes documenting register/test patterns
- Python stdlib docs for `os.walk(followlinks=False)`, `tempfile.NamedTemporaryFile`, `hashlib.sha256`, `asyncio.create_task` — all stable contracts

### Secondary (MEDIUM confidence)

- https://www.kali.org/tools/binwalk3/ — binwalk3 v3.1.0 CLI flag list, package status
- https://www.kali.org/tools/binwalk/ — binwalk v2.4.3 EOL 2025-12-12 confirmation
- https://pkg.kali.org/pkg/binwalk3 — "migrated to kali-rolling 2026-03-09"
- https://unblob.org/guide/ — unblob CLI: `-e/--extract-dir`, `-d/--depth`, `--report`, `-p/--process-num`, `-S/--skip-magic`, etc.
- https://github.com/onekey-sec/unblob — current release 26.3.30 (2026-03-30)
- https://github.com/onekey-sec/unblob/blob/main/docs/installation.md — unblob external dep list (7z, lz4, zstd, e2fsprogs, unar)
- https://github.com/upx/upx — UPX 5.1.1 (2026-03-05) latest; CLI flag reference (limited content extracted)
- https://manpages.debian.org/testing/binwalk/binwalk.1.en.html — binwalk v2.x man page (`-B`, `-E`, `-e`, `-M`, `-d/--depth`, `-C/--directory`, `-f/--log`)

### Tertiary (LOW confidence — flagged for verification in Wave 0 / planning)

- Exact unblob progress-bar emission shape (Rich Progress confirmed via web search; in-container probe verifies — A3)
- Exact UPX 4.2.x stderr text for "not packed by UPX" (cited in GitHub discussion; planner runs `upx -t <non-upx-file>` in container — A3 sibling)
- Whether `binwalk3 -E` writes a PNG or a text summary table (kali.org page says entropy plot; planner runs `binwalk3 -E sample.bin` to confirm output surface)

## Metadata

**Confidence breakdown:**
- Standard stack (existing gateway modules): HIGH — every dependency was read in this session
- Standard stack (external tools): MEDIUM — official docs cited, but exact CLI flags for the current container versions need Wave-0 in-container probe per Pitfall 1 + Assumption A1/A2
- Architecture patterns (primitive + surface split, registration, error dicts, disclaimer splice): HIGH — verbatim replication of Phase 8/9 with existing precedent files read
- Pitfalls (binwalk version drift, symlink race, unblob progress, init_case closure): HIGH for the four primary pitfalls; MEDIUM for the secondary ones (hardlink counting, meta sidecar races)
- Validation architecture: HIGH — directly maps CONTEXT.md D-24 file list to EXTR-XX requirements

**Research date:** 2026-05-19
**Valid until:** ~30 days for binwalk3 / unblob version pins (active development); ~7 days for kali-rolling package versions (rolling release); the architectural and pattern guidance is valid until v1.2 milestone begins.

## RESEARCH COMPLETE

**Phase:** 10 - Extraction Tier
**Confidence:** HIGH (codebase integration) / MEDIUM (external tool CLI specifics)

### Key Findings

- **binwalk version is the single biggest plan-impacting question.** The Dockerfile currently installs `binwalk` (v2.4.3, EOL 2025-12-12). Kali Rolling has `binwalk3` (v3.1.0-0kali4) available. The plan SHOULD migrate to binwalk3 in Phase 10's Wave 1 (Dockerfile edit). Wrapper code must target binwalk3's CLI (`-l <json>` for log, no `-d/--depth` flag, recursion via `-M` alone). Assumption A2 means `kwargs_schema["depth"]` for `binwalk_extract` either drops `depth` or post-processes.
- **`init_case` is currently a closure inside `tools/artifacts.py:register(mcp)` — not module-level importable.** `promote_extracted_sample` (EXTR-05) either refactors it to module-level OR shells out via `subprocess_runner.run_script(["bash", str(SCRIPTS / "init_status_tree.sh"), <upload_path>, "--new"])`. The shellout path is simpler and lower-risk for Phase 10 scope.
- **Phase 10 has ZERO new lifespan changes, ZERO new top-level Python deps, ZERO `app.py` edits.** Every wire is composition over Phase 6/7/8/9 primitives. The new code is concentrated in `extraction.py` (primitive) and `tools/extract.py` (MCP surface).
- **`progress_parser=None` for BOTH unblob and binwalk_extract specs.** Unblob uses Rich Progress (ANSI cursor moves, not newline-terminated); binwalk3's quiet-mode stderr is silent per current docs. Agents poll `get_tool_job` for status — same UX as Phase 9's `capa` spec.
- **Symlink quarantine timing is non-negotiable for security.** Per D-15, the sweep runs in the monitor's post-terminal hook BEFORE the meta sidecar's status flips out of `running`. The Phase 7 Resources walker follows symlinks; unquarantined extraction symlinks are a host-FS traversal vector.

### File Created

`/home/cervon/Code/MARE-MCP-Toolbox/.planning/phases/10-extraction-tier/10-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Existing gateway primitives (Phase 6/7/8/9 reuse) | HIGH | Every source file relied on was read in this session; integration points verified against actual code, not memory. |
| External tool CLI shapes (binwalk3, unblob, upx) | MEDIUM | Official docs cited; in-container empirical verification deferred to Wave 0 planner probes (A1/A2/A3). |
| Architectural pattern (primitive + surface + disclaimer splice + register-wraps) | HIGH | Verbatim replication of Phase 8/9 with reference code in `tools/jobs.py` and `tools/r2_sessions.py`. |
| Pitfalls (10 documented) | HIGH for top-4; MEDIUM for the rest | Top-4 are derived from explicit CONTEXT.md decisions or current-Dockerfile state; lower-priority pitfalls are good-practice extrapolations from Phase 6/7/8/9 SUMMARY notes. |
| Validation architecture | HIGH | One-to-one map from CONTEXT.md D-24 test files to EXTR-XX requirements; Wave 0 RED-stub gaps enumerated. |
| Security (V12 Files and Resources) | HIGH | Symlink-quarantine and archive-bomb-cap are the two primary threats; both have explicit CONTEXT.md decisions and standard mitigation patterns. |

### Open Questions for Planning

1. **Migrate Dockerfile to `binwalk3`, or stay on `binwalk` v2 with EOL acknowledgment?** Research recommends migrate; planner makes the call. Affects `_build_binwalk_extract_argv`, the `run_binwalk(mode="signatures")` parser, and the `kwargs_schema["depth"]` design.
2. **`init_case` reuse path: refactor to module-level OR shell out via `subprocess_runner.run_script`?** Research recommends shellout for Phase 10 scope; refactor (small) is also acceptable.
3. **Should `_lineage.json` count as a 14th MCP Resource explicitly?** Phase 7 D-26 depth-2 walker covers it automatically; CONTEXT.md discretion item leans yes (free signal).
4. **`engine_specific_summary` field on `list_extracted_files`?** CONTEXT.md discretion; lean yes-for-unblob (`top_chunk_types` from already-parsed `report.json`), maybe-not for binwalk/upx.
5. **`--` argv separator before `sample` positional in argv builders (defense in depth against accidental flag-in-filename)?** Not in CONTEXT.md; research recommends YES.

### Ready for Planning

Research complete. The planner can now create PLAN.md files. Recommended plan partitioning (mirrors Phase 9's 4–5 plan structure):

- **Plan 01 — Wave 0:** 13-file RED-stub test scaffold + Dockerfile binwalk3 migration + Wave-0 in-container CLI probe script (resolves A1/A2/A3).
- **Plan 02 — Wave 1 (primitive):** `extraction.py` — `extraction_dir`, `quarantine_symlinks`, `_du_sb`, `write_meta`/`update_meta`/`read_meta`, env constants, `_build_unblob_argv` + `_build_binwalk_extract_argv`, `_UNBLOB_SPEC` + `_BINWALK_EXTRACT_SPEC` registration, `write_upload`.
- **Plan 03 — Wave 1 (monitor):** `start_extract_monitor` + module-level monitor task set + post-terminal hook. Separated from Plan 02 because the monitor is the most concurrency-sensitive piece and benefits from a focused review.
- **Plan 04 — Wave 2 (surface):** `tools/extract.py` — 7 `@mcp.tool()` handlers + `register(mcp)` + D-23 disclaimer splice + 6 D-22 error shapes.
- **Plan 05 — Wave 3 (integration):** `tools/__init__.py` edit + `mcp-gateway/tests/test_tool_list.py::EXPECTED_TOOLS` bump 47 → 54 + Wave-0 RED → GREEN flip of all 13 test files + final `_lineage.json` Resource confirmation.
