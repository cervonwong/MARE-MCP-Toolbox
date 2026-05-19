# Phase 10: Extraction Tier - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 10-CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 10-extraction-tier
**Mode:** Discuss (auto — user instructed "Choose the best robust and featured option for each question")
**Areas discussed:** Sync vs background dispatch, Extraction subdir layout + list_extracted_files, promote_extracted_sample semantics, Symlink quarantine + archive-bomb cap

---

## Gray-Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Sync vs background dispatch | Which tools sync vs Phase 9 job; does run_binwalk return job snapshot or sync dict? Do unblob/binwalk_extract also register as JobToolSpecs? | ✓ |
| Extraction subdir layout + list_extracted_files | Naming of extracted/<engine>-<ts>/, walker shape, per-engine parsing strategy | ✓ |
| promote_extracted_sample semantics | Re-upload flow, dedup, lineage, idempotency | ✓ |
| Symlink quarantine + archive-bomb cap | When sweep runs, how MAX_EXTRACT_MB is enforced | ✓ |

**User's choice:** All four areas, with instruction to "Choose the best robust and featured option for each question."

---

## Area 1: Sync vs background dispatch

### Q1.1 — Tool surface count and dispatch policy

| Option | Description | Selected |
|--------|-------------|----------|
| 7 MCP tools, mode-discriminated return for run_binwalk | run_binwalk single tool, mode=signatures/entropy returns 12-key dict, mode=extract returns 25-key job snapshot. run_unblob always job. UPX wrappers sync. Two new JobToolSpecs (`unblob`, `binwalk_extract`) registered alongside Phase 9 capa spec. | ✓ |
| Split run_binwalk into run_binwalk_scan (sync) + start_binwalk_extract_job (async) | 8 MCP tools; explicit names per dispatch mode; symmetrical with start_tool_job. | |
| Make all extraction job-only; route through Phase 9's start_tool_job | Minimal MCP-tool count (only list/promote as new tools); but breaks EXTR-01/03/04 spelling. | |

**Selected:** 7 MCP tools with mode-discriminated return on run_binwalk. EXTR-01 literally spells `run_binwalk(case_dir, sample, mode)`; the requirement spelling drives the API shape.

### Q1.2 — JobToolSpec registration location

| Option | Description | Selected |
|--------|-------------|----------|
| Specs live in extraction.py; jobs.py only exposes register_job_tool | Co-locates build_argv with spec; refines Phase 9 D-04's "ship-with capa lives in jobs.py" pragma without reopening. | ✓ |
| Specs live in jobs.py alongside Phase 9's capa | Matches Phase 9 D-04 literally; jobs.py grows but no new modules. | |
| New tools/job_specs/ package | Cleanest long-term; but Phase 9 D-04 set the threshold at 5+ specs (Phase 10 brings count to 3 — refactor deferred to Phase 11). | |

**Selected:** Specs in `extraction.py`. Phase 9 D-04 explicitly allows specs to live wherever `register_job_tool` is imported.

---

## Area 2: Extraction subdir layout + list_extracted_files

### Q2.1 — Subdir naming

| Option | Description | Selected |
|--------|-------------|----------|
| `extracted/<engine>-<UTC>Z-<rand4>/` mirroring Phase 6 D-09 tool_log_path | Anti-collision under concurrent jobs (rand4); engine prefix is durable identifier readable by list_extracted_files via regex; reuses existing slug machinery. | ✓ |
| `extracted/<engine>-<UTC>Z/` (no rand4) | Simpler; but collides under concurrent extract jobs in the same second. | |
| `extracted/<UTC>Z-<engine>-<rand4>/` | Date-first sorts chronologically by default; but engine prefix is more useful for filtering. | |

**Selected:** `extracted/<engine>-<UTC>Z-<rand4>/` — robust under burst, engine-first for filterability.

### Q2.2 — Provenance sidecar

| Option | Description | Selected |
|--------|-------------|----------|
| Per-extraction `_mare_meta.json` sidecar | Durable provenance (survives Phase 9 job eviction); read by list_extracted_files; exposed via Resources walker. | ✓ |
| Provenance only in Phase 9 job snapshot | No new file; but lost on registry eviction (~200 jobs, gateway restart). | |
| Append to a central `.planning/extractions.jsonl` | Single index file; but contention under concurrent writes, harder to evict per-case. | |

**Selected:** Per-extraction `_mare_meta.json` sidecar in extraction_dir.

### Q2.3 — list_extracted_files response caps

| Option | Description | Selected |
|--------|-------------|----------|
| Per-extraction cap (5000) + total cap (500 default, 10000 max) + truncated flag | Bounds MCP response size for firmware with 10k+ files while preserving useful overview. | ✓ |
| Single flat cap (1000) | Simpler; but huge extractions become unusable (one extraction monopolizes the cap). | |
| No cap — return everything | Will blow the MCP 25k-token response cap on real firmware. | |

**Selected:** Two-level cap with truncation flags. Agents needing full tree call `get_artifact_tree` or browse Resources.

### Q2.4 — Output parsing strategy per engine

| Option | Description | Selected |
|--------|-------------|----------|
| Always parse to JSON in-process; never raw-only | unblob report.json pass-through, binwalk text→rows, UPX text→structured. Agents get structured data without writing parsers; tests assert parser robustness. | ✓ |
| Return raw stdout; let agent parse | Minimal wrapper LoC; but pushes parsing complexity onto agent prompts. | |
| Parse on best-effort + always include raw | Hedge; but doubles response size and creates two sources of truth. | |

**Selected:** Always parse, fall back gracefully on edge cases (`raw: str` field in row when structured fields can't be extracted).

---

## Area 3: promote_extracted_sample semantics

### Q3.1 — Re-upload flow

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse uploads.py `<UPLOAD_DIR>/<sha256>/<filename>` layout via streaming helper | Content-addressed dedup; matches v1.0 D-13; atomic via tmp+rename. | ✓ |
| Copy file in-place to a separate `promoted/` tree | Avoids touching uploads/; but breaks `resolve_sample` contract that uploads/ is the canonical sample location. | |
| Skip re-upload; reference child_path directly in new case | Lightweight; but breaks sha256 content-addressing invariant; promoted case has no canonical uploads/ entry. | |

**Selected:** Reuse uploads.py layout via `extraction.write_upload(child_path, basename)` helper.

### Q3.2 — Idempotency

| Option | Description | Selected |
|--------|-------------|----------|
| Idempotent by sha256 globally (scan status/*/_lineage.json) + force_new override | Robust default for analyst workflow; same child via two extraction paths converges; force_new as safety valve. | ✓ |
| Always create new case (no idempotency check) | Simpler; but bloats status/ with duplicate cases for the same content. | |
| Idempotent per (parent_case, child_path) pair | Narrower; same child reached via different parents creates separate cases. Not the intuitive behavior. | |

**Selected:** Global sha256 idempotency + `force_new` kwarg.

### Q3.3 — Lineage tracking

| Option | Description | Selected |
|--------|-------------|----------|
| `_lineage.json` in new case dir (gateway-managed, distinct from 13 artifact files) | Durable, structured, machine-readable; auto-exposed via Resources walker; underscore prefix marks gateway-owned. | ✓ |
| Append lineage to 00_sample_profile.md | Reuses existing artifact; but 00_sample_profile.md is owned by collect_strings.sh and would conflict. | |
| Encode lineage in new case name (e.g., `004-from-001-firmware`) | Visible in `list_cases`; but lossy (no parent_extraction_dir, no promoted_at). | |

**Selected:** `_lineage.json` sidecar. Keeps 13-artifact contract clean; full structured data preserved.

---

## Area 4: Symlink quarantine + archive-bomb cap

### Q4.1 — Symlink quarantine timing

| Option | Description | Selected |
|--------|-------------|----------|
| Post-extract recursive sweep, BEFORE result return / BEFORE terminal job status | Atomic from agent's perspective; runs as part of sibling monitor's post-terminal hook for jobs, inline in sync wrappers. | ✓ |
| Pre-walk Resources walker to skip symlinks | Doesn't quarantine — agents using `os.path.realpath` or local FS access still vulnerable. | |
| Mount-namespace isolation for extraction subprocess | Best-in-class; but requires CAP_SYS_ADMIN — explicitly deferred to v1.2 per REQUIREMENTS.md "Out of Scope". | |

**Selected:** Post-extract recursive sweep replacing symlinks with `<name>.symlink-target.txt` files preserving metadata.

### Q4.2 — Archive-bomb cap enforcement mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Sibling asyncio.Task polling `du -sb extraction_dir` every 5s; cancels job on cap | Bounded latency to detect bomb (5s window); reuses Phase 9 cancel infrastructure; no Phase 9 vocabulary changes. | ✓ |
| Pre-flight free-disk check | Too conservative; doesn't bound the extraction's actual footprint. | |
| Post-extract verify (du after completion) | Too late — bomb already happened. | |
| prlimit --fsize on subprocess | Per-file limit, not per-tree; doesn't catch many-small-files bombs. | |
| tmpfs mount with size cap | Requires container setup change; out of scope for posture-only confinement. | |

**Selected:** Sibling asyncio.Task with 5s polling. Monitor self-terminates on terminal job status; no separate registry needed.

### Q4.3 — Cap-exceed signaling

| Option | Description | Selected |
|--------|-------------|----------|
| `.MARE_EXTRACT_CAP_EXCEEDED` marker file + sidecar `cap_exceeded=true` field | Durable across gateway restart; Phase 9 vocabulary unchanged; list_extracted_files surfaces state. | ✓ |
| Extend Phase 9 JobStatus with `killed_extract_cap` literal | Cleaner in the job snapshot; but reopens Phase 9 D-06 locked vocabulary. | |
| Only in job snapshot stderr | Lost on registry eviction. | |

**Selected:** Marker file + sidecar field. Don't reopen Phase 9.

---

## Claude's Discretion (areas where Claude has flexibility)

- Internal naming of private helpers (`_du_sb`, `_utc_now_iso`, `_hash_file_streaming`, `_existing_case_for_sha256`)
- Inline vs import of `_env_int`/`_env_float` helpers (research phase decides based on Phase 8 export surface)
- `binwalk --json` vs `binwalk -B` parser path (research phase determines binwalk2 vs binwalk3 in Kali)
- Inclusion of per-engine `engine_specific_summary` block in list_extracted_files response
- Whether to add convenience `cancel_extraction(case_dir, extraction_dir)` (lean: NO, keeps surface minimal)
- ANSI-strip / UTF-8-safe truncation helper reuse from Phase 6

## Deferred Ideas

- `tools/job_specs/` refactor — Phase 11 (crosses 5+ spec threshold)
- Append-only `_lineage.jsonl` audit log — v1.2+
- Hot-list of "interesting" extracted files — orchestrator skill (Phase 12)
- Cross-case extraction tree visualization — v1.2+
- Hard FS quota via prlimit/tmpfs — needs additional caps, v1.2+
- Auto-promotion of interesting children — composite (out of scope)
- Persistent extraction monitor state across restart — orthogonal v1.2+ phase
- Per-engine quotas — not warranted yet
- run_shell-based extraction — already covered by Phase 7

---

*All four gray areas resolved in a single auto pass per user instruction.*
