# Phase 10: Extraction Tier - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Land the three-engine extraction surface plus the cross-engine enumerator
and the child→new-case promotion primitive. This is the first v1.1 phase
that *consumes* Phase 9's `BackgroundJobRegistry` from a tool wrapper:
unblob and binwalk-extract dispatch as background jobs; binwalk
signatures/entropy, UPX test/list/unpack, enumeration, and promotion
return synchronously.

Scope:

- New module files:
  - `mcp-gateway/src/mcp_gateway/extraction.py` — primitive layer.
    `extraction_dir(case_dir, engine)` helper, `quarantine_symlinks(dir)`
    recursive post-extract sweep, `write_meta(extraction_dir, payload)`
    sidecar writer, `read_meta(extraction_dir)` reader,
    `enumerate_extractions(case_dir)` walker,
    `start_extract_monitor(job_id, extraction_dir)` archive-bomb watcher,
    `MAX_EXTRACT_BYTES` / `EXTRACT_MONITOR_INTERVAL_S` env-var module
    constants. Mirrors the `runner.py` / `sessions.py` / `jobs.py`
    primitive layering pattern. Phase 9 D-24 import discipline applies
    (no `mcp.server.fastmcp` import).
  - `mcp-gateway/src/mcp_gateway/tools/extract.py` — MCP surface. Seven
    `@mcp.tool()` handlers: `run_binwalk`, `run_unblob`, `run_upx_test`,
    `run_upx_list`, `run_upx_unpack`, `list_extracted_files`,
    `promote_extracted_sample`. Mirrors the `tools/r2_sessions.py` /
    `tools/jobs.py` register-pattern.
- Extensions to existing modules:
  - `mcp-gateway/src/mcp_gateway/jobs.py::JOB_TOOL_REGISTRY` gains two
    `JobToolSpec` entries: `unblob` and `binwalk_extract`. These are
    registered at `jobs.py` import time (matches Phase 9 D-04 ship-with
    pattern), NOT lazily inside `tools/extract.py.register(mcp)`. Phase
    9 D-04 noted that once spec count crosses ~5, a `tools/job_specs/`
    package becomes appropriate; Phase 10 brings the count to 3 (capa,
    unblob, binwalk_extract) which is still inside `jobs.py`. The
    `tools/job_specs/` refactor is deferred to Phase 11 (which adds
    strace/ltrace/qemu_user/ghidra_analyze specs and crosses the
    threshold).
  - `mcp-gateway/src/mcp_gateway/tools/__init__.py::register_all_tools`
    gains one import + one register call for `tools/extract.py`.
  - `mcp-gateway/src/mcp_gateway/artifacts_io.py::EXPANDED_CASE_SUBDIRS`
    grows by **zero entries** — Phase 6 D-16 already includes
    `"extracted"`. Extraction-dir subdirs (`extracted/<engine>-<ts>-<rand4>/`)
    are lazy-created inside `extracted/` and require no catalog change.
  - `mcp-gateway/src/mcp_gateway/uploads.py` — Phase 10 reuses the
    existing `<UPLOADS_ROOT>/<sha256>/<filename>` layout from v1.0 D-13
    via a small re-upload helper (`extraction.write_upload(child_path,
    target_basename)`) that streams hashes + atomically moves into
    place. No new uploads-tool surface is added; promotion uses the
    primitive directly.

Explicitly NOT in this phase:

- A new `Mcp-Session-Id`-keyed promotion log — promotion lineage lives
  in the new case's `_lineage.json`, plus a per-extraction
  `_mare_meta.json` sidecar; no per-session bookkeeping. Matches Phase
  8 SESS-05 / Phase 9 D-26 "shared across bearer-token clients"
  invariant.
- Refactoring `JOB_TOOL_REGISTRY` into a `tools/job_specs/` package —
  see D-01 above; deferred to Phase 11.
- Extending Phase 9's `JobStatus` vocabulary (D-06) with a
  `killed_extract_cap` literal. The cap is enforced by Phase 10's
  sibling monitor task, surfaced via a `.MARE_EXTRACT_CAP_EXCEEDED`
  marker file + `_mare_meta.json` field; the underlying job's status
  reports `cancelled`. This avoids reopening Phase 9's locked vocabulary
  for one new state and keeps the durable evidence in the case-dir, not
  in the (volatile, evictable) in-memory job registry.
- A new MCP tool for "list job-tool specs filtered by extraction engines"
  — Phase 9 D-20's `list_tool_jobs(state="_specs")` already provides
  spec discovery; Phase 10's two new specs surface there automatically.
- Persistent extraction monitor state across gateway restart — monitor
  tasks die with the gateway. The marker file + `_mare_meta.json`
  sidecar are durable; the in-memory monitor is not.
- Composite `extract_and_promote` MCP tool — orchestration is the
  agent's responsibility (PROJECT.md "Out of Scope"). `run_unblob` →
  poll → `list_extracted_files` → `promote_extracted_sample` is the
  composition; the gateway exposes primitives.
- `run_strings` over extracted files (out of scope per
  `REQUIREMENTS.md §"Out of Scope (v1.1)"`); agents use `run_shell` or
  v1.0 `collect_strings`.
- Per-`Mcp-Session-Id` keying of promotion idempotency — promotion is
  idempotent by sha256 globally (D-13 below); two clients promoting
  the same child converge to one case dir.
- Disk-quota-aware case-dir cleanup — bounded only by analyst lifecycle
  (consistent with Phase 9 deferred "disk-quota-aware log management").

</domain>

<decisions>
## Implementation Decisions

### Tool surface and dispatch policy (Area 1)

- **D-01:** Phase 10 ships **exactly seven** MCP-visible tools, one per
  EXTR-01..EXTR-05 spelling in REQUIREMENTS.md:

  ```python
  # tools/extract.py — register order matters for collision_check trace
  run_binwalk              # EXTR-01 — sync OR dispatches job depending on mode
  run_unblob               # EXTR-02 — always dispatches job
  run_upx_test             # EXTR-03 — sync
  run_upx_list             # EXTR-03 — sync
  run_upx_unpack           # EXTR-03 — sync
  list_extracted_files     # EXTR-04 — sync
  promote_extracted_sample # EXTR-05 — sync
  ```

  Gateway-native tool count bumps **47 → 54**. The Phase 7
  `test_tool_list.py::EXPECTED_TOOLS` set must add these seven names;
  the 35–50 invariant bound from Phase 7 D-16 needs to bump to 35–60 to
  absorb Phase 10 + 11 (Phase 11 adds another 7 dynamic tools when
  env-enabled, but those are conditionally registered so the static
  invariant stays at 54 for default-off operation). The `EXPECTED_TOOLS`
  bump is a Rule-1 deviation, precedent set by Phase 7-08 SUMMARY and
  Phase 9-03 SUMMARY.

- **D-02:** `run_binwalk` API — single MCP tool, mode-branching internal
  dispatch:

  ```python
  @mcp.tool()
  async def run_binwalk(
      case_dir: str,
      sample: str,
      *,
      mode: Literal["signatures", "entropy", "extract"] = "signatures",
      ctx: Context | None = None,
  ) -> dict:
      """Run binwalk in one of three modes.

      mode="signatures": fast scan via `binwalk -B`; sync return; parsed
          rows in result["signatures"].
      mode="entropy":    fast entropy plot via `binwalk -E`; sync return;
          parsed rows in result["entropy"]; plot image (if produced)
          captured under extracted/<engine>-<ts>-<rand4>/.
      mode="extract":    recursive extraction via `binwalk -e --depth=8`;
          dispatches via Phase 9 start_tool_job(tool="binwalk_extract", ...);
          returns the initial job snapshot — agent polls via get_tool_job.

      [Phase 9 D-26 in-memory disclaimer is spliced in only on the extract
       branch's docstring portion; signatures/entropy share the standard
       "snapshot now" docstring contract.]
      """
  ```

  Result shape differs by mode:

  - `mode="signatures"|"entropy"`: full Phase 6 D-03 12-key dict +
    parsed `signatures: list[dict]` or `entropy: list[dict]`
    +  `extraction_dir: None` (no extraction happens)
    +  `mode: "signatures"|"entropy"`.
  - `mode="extract"`: Phase 9 D-19 25-key job snapshot dict
    +  `mode: "extract"`
    +  `extraction_dir: str` (case-relative path to the new
       `extracted/binwalk-<ts>-<rand4>/`)
    +  `engine: "binwalk"`.

  The agent discriminates by reading `result["mode"]`. The asymmetric
  return is documented exhaustively in the docstring.

  *Rationale:* EXTR-01 literally spells `run_binwalk(case_dir, sample,
  mode)`. Splitting into `run_binwalk_scan` + `start_binwalk_extract_job`
  would diverge from the requirement spelling and force agents to
  remember a second tool name for an arguably-related operation. The
  single tool with `mode`-discriminated result shape is the more robust
  and featureful choice: discovery via `mode` enum auto-completes;
  extract-mode agents naturally call `get_tool_job` because the
  `job_id` is in the response.

- **D-03:** `run_unblob` API — always job-dispatched:

  ```python
  @mcp.tool()
  async def run_unblob(
      case_dir: str,
      sample: str,
      *,
      depth: int = 8,
      ctx: Context | None = None,
  ) -> dict:
      """Carve embedded files via unblob's --report JSON pipeline.

      Always dispatches as a Phase 9 background job (unblob on real
      firmware exceeds the 60s MCP request cap). Returns the initial job
      snapshot — agent polls via get_tool_job(job_id) until status is
      terminal, then calls list_extracted_files(case_dir) to enumerate
      results and inspect _mare_meta.json sidecars.

      [Phase 9 D-26 in-memory disclaimer is spliced in verbatim.]
      """
  ```

  Returns the Phase 9 D-19 25-key snapshot + `mode: "unblob"` +
  `extraction_dir: str` + `engine: "unblob"`. Same shape as
  `run_binwalk(mode="extract")` so agent polling code is uniform.

- **D-04:** UPX wrappers — all three synchronous, all parsed:

  ```python
  @mcp.tool()
  async def run_upx_test(case_dir: str, sample: str) -> dict:
      """Verify a UPX-packed binary via `upx -t`. Sync; returns:
      {... Phase 6 D-03 12-key dict ...,
       "engine": "upx",
       "mode": "test",
       "is_upx_packed": bool,         # parsed from stderr ("not packed by UPX")
       "test_result": Literal["ok","not_packed","corrupt","error"],
      }
      """

  @mcp.tool()
  async def run_upx_list(case_dir: str, sample: str) -> dict:
      """List UPX section metadata via `upx -l`. Sync; returns:
      {... Phase 6 D-03 12-key dict ...,
       "engine": "upx",
       "mode": "list",
       "rows": list[{
           "file": str,
           "compressed_size": int,
           "uncompressed_size": int,
           "ratio": float,           # 0.0–1.0
           "format": str,            # e.g. "linux/ElfAMD"
           "name": str,              # original filename column
       }],
      }
      """

  @mcp.tool()
  async def run_upx_unpack(case_dir: str, sample: str) -> dict:
      """Unpack a UPX-packed binary via `upx -d -o <out>`. Sync; returns:
      {... Phase 6 D-03 12-key dict ...,
       "engine": "upx",
       "mode": "unpack",
       "extraction_dir": str,        # case-rel: extracted/upx-<ts>-<rand4>
       "unpacked_path": str,         # case-rel path of the unpacked binary
       "unpacked_size": int,
       "symlinks_quarantined": int,  # always 0 for upx in practice
      }
      """
  ```

  UPX is fast enough on real samples (<10s on typical packed ELF/PE) to
  fit inside Phase 6's default 60s `RUNNER_TIMEOUT_S`. No job dispatch.
  Output parsing is part of the wrapper (D-09 below) — robust default,
  not "return raw and let the agent parse."

- **D-05:** `list_extracted_files` API — engine-agnostic enumeration:

  ```python
  @mcp.tool()
  async def list_extracted_files(
      case_dir: str,
      *,
      engine: Literal["binwalk", "unblob", "upx"] | None = None,
      limit: int = 500,
      include_quarantined: bool = True,
  ) -> dict:
      """Enumerate files extracted by any prior run_binwalk / run_unblob
      / run_upx_unpack call. Walks `case_dir/extracted/**` and reads
      per-extraction `_mare_meta.json` sidecars for provenance.
      """
  ```

  Returns:

  ```python
  {
      "case_dir": str,                                # absolute
      "extractions": [
          {
              "engine": "binwalk"|"unblob"|"upx",
              "extraction_dir": str,                  # case-rel
              "started_at": str,                      # ISO8601 Z (from dir name)
              "completed_at": str | None,             # ISO8601 Z (from meta)
              "exit_code": int | None,                # from meta; None if job still running
              "status": str,                          # from meta: "succeeded"|"failed"|"cancelled"|"cap_exceeded"|"running"
              "job_id": str | None,                   # only set for binwalk_extract / unblob
              "symlinks_quarantined": int,
              "cap_exceeded": bool,                   # true iff .MARE_EXTRACT_CAP_EXCEEDED marker present
              "file_count": int,                      # files (not dirs); quarantine markers counted iff include_quarantined
              "total_bytes": int,                     # sum of regular file sizes
              "files": [
                  {
                      "path": str,                    # case-rel
                      "size": int,
                      "is_symlink_quarantine": bool,  # true iff name ends in ".symlink-target.txt"
                  }, ...
              ],
              "files_truncated": bool,                # true iff this extraction's files exceed per-extraction cap
          }, ...
      ],
      "total_extractions": int,
      "total_files_listed": int,                      # post-cap
      "truncated": bool,                              # true iff cap reached
  }
  ```

  Caps:

  - Per-extraction file list capped at `MAX_FILES_PER_EXTRACTION` (env
    `MCP_GATEWAY_LIST_EXTRACT_FILES_PER_EXTRACTION`, default 5000) —
    firmware unblob runs routinely produce 10k+ files; this bounds the
    MCP response size.
  - Cross-extraction `limit` kwarg (default 500, max 10000) caps the
    sum of files across all extractions in the response.
  - `engine=` filter narrows by engine prefix on the directory name.
  - `include_quarantined=False` strips `.symlink-target.txt` entries.

  *Rationale:* Returning every file path for a multi-GB firmware
  extraction would blow the MCP 25k-token response cap. The two-level
  cap (per-extraction + total) keeps the response bounded while still
  giving agents a useful overview. Agents that need the full tree call
  `get_artifact_tree(case_dir)` (Phase 7 D-25) or browse via Resources.

- **D-06:** `promote_extracted_sample` API — atomic, idempotent,
  lineage-tracked:

  ```python
  @mcp.tool()
  async def promote_extracted_sample(
      parent_case_dir: str,
      child_path: str,
      *,
      force_new: bool = False,
  ) -> dict:
      """Promote an extracted child file to a first-class new case.

      Flow (atomic — either all steps complete or none persist):
      1. resolve_case_dir(parent_case_dir); confine_to(parent_case_dir,
         child_path) — child must live under
         <parent_case_dir>/extracted/**.
      2. Recompute sha256 of child_path (streaming hash; reject if file
         is a symlink-quarantine sentinel `.symlink-target.txt`).
      3. Dedup check: if <UPLOADS_ROOT>/<sha256>/ already exists,
         skip re-upload (D-13).
      4. Else: atomically stream child into
         <UPLOADS_ROOT>/<sha256>/<basename> via tmp+rename
         (extraction.write_upload).
      5. Idempotency: scan status/*/_lineage.json for an entry with the
         same sha256 — if found AND force_new=False, return that
         existing case_dir.
      6. Else: call existing init_case(sample=<sha256>, new=True) →
         materializes status/<NNN>-<basename>/ with 13 empty artifacts.
      7. Write <new_case_dir>/_lineage.json (D-14 shape).
      8. Return the dict below.
      """
  ```

  Returns:

  ```python
  {
      "new_case_dir": str,                # absolute (resolved)
      "new_case_name": str,               # e.g. "004-libssl.so.1.1"
      "sha256": str,                      # 64-hex
      "dedup": bool,                      # true iff sample already in uploads/
      "idempotent_reuse": bool,           # true iff returned an existing case dir
      "parent_case_dir": str,             # absolute
      "parent_extraction_dir": str,       # case-rel: "extracted/unblob-..."
      "child_path": str,                  # case-rel to parent
      "promoted_at": str,                 # ISO8601 Z
      "lineage_path": str,                # case-rel: "_lineage.json"
  }
  ```

  *Rationale:* SC-5 explicitly says "re-uploads with sha256
  content-addressing, initializes a new case directory, and returns the
  new case_dir." Idempotency by sha256 is the robust default for an
  analyst workflow where the same child file may be reached via
  multiple extraction paths (binwalk-then-unblob, unblob-then-binwalk).
  `force_new=True` is the safety valve for analysts who want a fresh
  case for a known-already-promoted child.

### Extraction-dir layout, sidecar, and parsing (Area 2)

- **D-07:** Extraction-dir naming: **`extracted/<engine>-<UTC>Z-<rand4>/`**
  exactly mirroring Phase 6 D-09's `tool_log_path` shape. Examples:

  ```
  extracted/binwalk-2026-05-19T14:32:11Z-a3f9/
  extracted/unblob-2026-05-19T14:32:11Z-7b1c/
  extracted/upx-2026-05-19T14:32:11Z-9d2e/
  ```

  Why `rand4`: concurrent extractions in the same second are possible
  (Phase 9 jobs run in parallel up to `MAX_JOBS_INFLIGHT`); the
  4-hex-char suffix avoids collision under burst. Same anti-collision
  rationale as Phase 6's per-call log files.

  New helper, in `extraction.py`:

  ```python
  def extraction_dir(case_dir: str, engine: Literal["binwalk","unblob","upx"]) -> Path:
      """Mint a new extracted/<engine>-<UTC>Z-<rand4>/ subdir under case_dir.

      Reuses the existing rand4 + UTC-Z slug machinery from
      artifacts_io.tool_log_path; the directory is created on call
      (lazy ensure on extracted/ first if absent, per Phase 6 D-15).
      Returns absolute Path.
      """
  ```

  Engine value in the dir name is the durable identifier — `list_extracted_files`
  reads it back via a `^(binwalk|unblob|upx)-` regex on directory
  names. Sidecar (D-08) is the secondary source of truth; the dir name
  is the primary.

- **D-08:** Per-extraction `_mare_meta.json` sidecar. Written into
  the extraction dir IMMEDIATELY after extraction-dir creation
  (status="running"), updated to terminal status when extraction
  finishes (sync) or when the job hits terminal status (async). Shape:

  ```python
  {
      "engine": "binwalk"|"unblob"|"upx",
      "mode": "signatures"|"entropy"|"extract"|"test"|"list"|"unpack",
      "started_at": str,                  # ISO8601 Z
      "completed_at": str | None,
      "status": Literal[
          "running",
          "succeeded",
          "failed",
          "cancelled",                    # job cancelled by user
          "cap_exceeded",                 # archive-bomb cap fired
          "killed_timeout",
          "killed_log_cap",
      ],
      "exit_code": int | None,
      "case_dir": str,                    # absolute
      "extraction_dir": str,              # case-rel
      "sample": str,                      # absolute
      "sample_sha256": str,
      "argv": list[str],
      "job_id": str | None,               # set for unblob + binwalk_extract
      "log_path": str,                    # case-rel tool-logs/...
      "symlinks_quarantined": int,
      "cap_exceeded": bool,
      "extract_bytes_total": int,         # final du -sb of extraction_dir
      "monitor_polls": int,               # how many size polls ran
  }
  ```

  Sidecar is the durable provenance record. `list_extracted_files`
  reads it per-extraction. After the Phase 9 in-memory job is evicted,
  the sidecar is still on disk; `list_extracted_files` continues
  reporting full state. Also exposed via Phase 7 D-26 Resources walker
  at `mare://cases/<case>/extracted/<engine>-<ts>-<rand4>/_mare_meta.json`.

- **D-09:** Per-engine output parsing — every wrapper parses its tool's
  text output to JSON before returning. **Always parsed, never
  raw-only:**

  - **unblob:** Already JSON via `--report <path>`. After job completes,
    `tools/extract.py.run_unblob` reads `<extraction_dir>/report.json`
    (unblob's default report filename) and embeds it as
    `result["unblob_report"]: dict`. If unblob's CLI prefers
    `--report-file=<path>`, the wrapper passes that.
    Research-phase will confirm exact unblob 25.x CLI; planner adds
    the correct flag.

  - **binwalk signatures** (`mode="signatures"`): prefer `binwalk --json`
    if available; else parse `binwalk -B` text into rows of
    `{offset_dec: int, offset_hex: str, description: str}`. Binwalk
    is available in Kali, but the rust-rewritten binwalk3 has a
    different CLI than legacy python binwalk2; research phase
    determines which is installed in `kalilinux/kali-rolling` and the
    planner picks the parser path. **Wrapper must handle both** —
    fail-loud with a `{"error": "unsupported binwalk version", ...}`
    dict if the parser can't lock to a row schema.

  - **binwalk entropy** (`mode="entropy"`): parse `binwalk -E`'s
    summary table into
    `{block_start: int, block_end: int, entropy: float}` rows. If
    binwalk generates a PNG plot under `--save`, capture it into
    extraction_dir; reference via meta sidecar.

  - **UPX test/list/unpack:** parse `upx`'s stderr line patterns into
    structured rows (D-04). UPX's CLI is stable across Debian versions
    (`upx-ucl` in Kali), so the parser is locked.

  Robust default: every parser falls back gracefully — if a field
  can't be extracted, the row contains the raw line in a `raw: str`
  field and structured fields are None. Tests assert the parser
  doesn't crash on edge inputs (zero-length output, ANSI-coloured
  output, partial output from killed_log_cap jobs).

- **D-10:** Result-dict layering — extraction tools layer onto
  Phase 6 D-03's 12 keys for sync tools and onto Phase 9 D-19's 25
  keys for job-dispatched tools. Layering convention matches Phase 8
  D-11 / Phase 9 D-19: extension keys come AFTER the base keys, never
  rename or remove existing keys.

  Common Phase 10 extension fields (always present, all sync + async
  paths):

  ```python
  "engine":              Literal["binwalk","unblob","upx"],
  "mode":                str,
  "extraction_dir":      str | None,        # case-rel; None for upx test/list
  "symlinks_quarantined": int,              # 0 if no extraction or quarantine skipped
  "meta_path":           str | None,        # case-rel _mare_meta.json
  ```

  Per-tool extras:

  - `run_binwalk` adds `signatures: list[dict] | None` (signatures
    mode), `entropy: list[dict] | None` (entropy mode), `entropy_plot:
    str | None` (case-rel PNG path if produced), `job_id: str | None`
    (extract mode).
  - `run_unblob` adds `unblob_report: dict | None` (populated once job
    terminal; absent in the immediate snapshot — agent polls and
    re-calls list/`get_tool_job` to read the report when status is
    `succeeded`), `job_id: str`.
  - `run_upx_test` adds `is_upx_packed: bool`, `test_result: Literal[...]`.
  - `run_upx_list` adds `rows: list[dict]`.
  - `run_upx_unpack` adds `unpacked_path: str`, `unpacked_size: int`.
  - `list_extracted_files` returns a different top-level shape (D-05);
    not a 12-key extension.
  - `promote_extracted_sample` returns a custom shape (D-06); not a
    12-key extension.

### JobToolSpec registrations (Area 1 part 2 — Phase 9 integration)

- **D-11:** Two new `JobToolSpec` entries land in `jobs.py` (NOT in
  `tools/extract.py`), registered at `jobs.py` import time alongside
  the existing `_sleep_probe`, `_log_burst_probe`, and `capa` specs
  from Phase 9 D-04. The specs are public (no underscore prefix —
  these are user-visible tools, unlike Phase 9's `_sleep_probe`):

  ```python
  # In jobs.py — appended below the capa spec

  _UNBLOB_SPEC = JobToolSpec(
      name="unblob",
      slug="unblob",
      build_argv=_build_unblob_argv,            # see D-12 below
      default_timeout_s=3600.0,                 # 1h; firmware can be huge
      progress_parser=_parse_unblob_progress,   # see D-15 below
      kwargs_schema={
          "case_dir":       {"type": "string"},
          "sample":         {"type": "string"},
          "extraction_dir": {"type": "string"},   # absolute, pre-minted by wrapper
          "depth":          {"type": "integer", "min": 1, "max": 16, "default": 8},
      },
      description=(
          "Carve embedded files from a sample via unblob. Writes "
          "results under <extraction_dir> with a structured "
          "--report JSON. Auto-quarantines symlinks post-extract. "
          "Enforces MCP_GATEWAY_MAX_EXTRACT_MB cap via sibling monitor."
      ),
  )

  _BINWALK_EXTRACT_SPEC = JobToolSpec(
      name="binwalk_extract",
      slug="binwalk_extract",
      build_argv=_build_binwalk_extract_argv,   # see D-12 below
      default_timeout_s=1800.0,                 # 30m
      progress_parser=None,                     # binwalk2 silent on stderr; planner re-checks
      kwargs_schema={
          "case_dir":       {"type": "string"},
          "sample":         {"type": "string"},
          "extraction_dir": {"type": "string"},
          "depth":          {"type": "integer", "min": 1, "max": 8, "default": 8},
          "matryoshka":     {"type": "boolean", "default": True},
      },
      description=(
          "Recursive extraction via binwalk -e. Writes carved children "
          "under <extraction_dir>. Auto-quarantines symlinks. Cap via "
          "MCP_GATEWAY_MAX_EXTRACT_MB."
      ),
  )

  # Registered at module import:
  register_job_tool(_UNBLOB_SPEC)
  register_job_tool(_BINWALK_EXTRACT_SPEC)
  ```

  *Rationale for living in `jobs.py` (not a separate `job_specs/`
  package):* Phase 9 D-04 noted that the `tools/job_specs/` refactor
  is appropriate "when there are 5+ specs"; Phase 10 takes the count
  to 3 (capa, unblob, binwalk_extract). Still inside `jobs.py`. The
  Phase 11 ghidra/strace/ltrace/qemu_user additions cross the
  threshold and trigger the refactor.

- **D-12:** `build_argv` callables — pure functions, `extraction.py`
  exports them so `jobs.py` can import without circularity. Phase 9
  D-02 locks `build_argv: Callable[[Path, dict], list[str]]` and Phase 10
  honors the signature. Shape:

  ```python
  # In extraction.py
  def _build_unblob_argv(case_dir: Path, kwargs: dict) -> list[str]:
      sample = resolve_sample(kwargs["sample"])
      extraction_dir = confine_to(case_dir, kwargs["extraction_dir"])
      depth = int(kwargs.get("depth", 8))
      # unblob CLI shape verified in research phase; placeholder:
      return [
          "unblob",
          "--report", str(extraction_dir / "report.json"),
          "--extract-to", str(extraction_dir),
          "--depth", str(depth),
          sample,
      ]

  def _build_binwalk_extract_argv(case_dir: Path, kwargs: dict) -> list[str]:
      sample = resolve_sample(kwargs["sample"])
      extraction_dir = confine_to(case_dir, kwargs["extraction_dir"])
      depth = int(kwargs.get("depth", 8))
      matryoshka = bool(kwargs.get("matryoshka", True))
      argv = [
          "binwalk", "-e",
          "--directory", str(extraction_dir),
          "--depth", str(depth),
          sample,
      ]
      if matryoshka:
          argv.insert(1, "--matryoshka")  # -M
      return argv
  ```

  Both functions are pure (no I/O, no side effects). The `extraction_dir`
  kwarg is **pre-minted** by the MCP wrapper (`tools/extract.py.run_unblob`
  calls `extraction.extraction_dir(case_dir, "unblob")` BEFORE calling
  `start_tool_job`, then passes the resulting path as the `extraction_dir`
  kwarg). This decouples directory creation (sync, fast) from the job's
  argv build, and gives the wrapper the path immediately so it can
  spawn the sibling monitor task (D-17) before returning.

- **D-13:** Wrapper-side flow for job-dispatched tools (`run_unblob`,
  `run_binwalk(mode="extract")`):

  ```python
  async def run_unblob(case_dir, sample, *, depth=8, ctx=None):
      case_path = Path(resolve_case_dir(case_dir))
      extraction_path = extraction.extraction_dir(case_path, "unblob")
      sample_abs = resolve_sample(sample)
      sample_sha = _hash_file_streaming(sample_abs)

      # 1. Write initial meta with status="running"
      extraction.write_meta(extraction_path, {
          "engine": "unblob",
          "mode": "extract",
          "started_at": _utc_now_iso(),
          "status": "running",
          "case_dir": str(case_path),
          "extraction_dir": str(extraction_path.relative_to(case_path)),
          "sample": sample_abs,
          "sample_sha256": sample_sha,
          ...
      })

      # 2. Dispatch via Phase 9
      snapshot = await tools_jobs.start_tool_job(
          tool="unblob",
          kwargs={
              "case_dir": str(case_path),
              "sample": sample,
              "extraction_dir": str(extraction_path),
              "depth": depth,
          },
          case_dir=str(case_path),
          ctx=ctx,
      )

      # 3. Spawn sibling archive-bomb monitor (D-17)
      asyncio.create_task(
          extraction.start_extract_monitor(
              job_id=snapshot["job_id"],
              extraction_dir=extraction_path,
          )
      )

      # 4. Update meta with job_id, return augmented snapshot
      extraction.update_meta(extraction_path, {"job_id": snapshot["job_id"]})
      return {
          **snapshot,
          "engine": "unblob",
          "mode": "extract",
          "extraction_dir": str(extraction_path.relative_to(case_path)),
          "meta_path": str((extraction_path / "_mare_meta.json").relative_to(case_path)),
      }
  ```

  This wrapper layer is what `run_unblob` calls from `tools/extract.py`.
  The agent-visible MCP tool is just this wrapper — the agent never
  needs to know it's job-dispatched (the result dict tells them via
  `mode: "extract"` + `job_id`).

- **D-14:** Promotion sha256 idempotency — sample dedup mechanism for
  `promote_extracted_sample`:

  ```python
  def _existing_case_for_sha256(sha: str) -> Path | None:
      """Scan STATUS_ROOT for status/*/_lineage.json with matching sha256.
      Returns the FIRST matching case dir (the original promotion)."""
      for case in sorted(STATUS_ROOT.iterdir()):
          if not case.is_dir() or not CASE_NAME_RE.match(case.name):
              continue
          lineage = case / "_lineage.json"
          if not lineage.is_file():
              continue
          try:
              meta = json.loads(lineage.read_text())
              if meta.get("promoted_sha256") == sha:
                  return case
          except (json.JSONDecodeError, OSError):
              continue
      return None
  ```

  - Default: idempotent re-use of existing case dir.
  - `force_new=True`: skip this check, always init a fresh case dir.
  - Cases that exist but lack `_lineage.json` (e.g., cases created via
    `init_case` directly on a manually uploaded sample) are NOT
    candidates for idempotent reuse — promotion always creates a new
    case dir in that scenario, even if the sample sha256 already has
    a non-promoted case. This avoids cross-contaminating the
    sha256-keyed lineage index with non-promoted history.

  Lineage file shape:

  ```python
  # <new_case_dir>/_lineage.json
  {
      "promoted_sha256": str,             # 64-hex
      "parent_case_dir": str,             # absolute
      "parent_extraction_dir": str,       # case-rel under parent
      "child_path": str,                  # case-rel under parent
      "promoted_at": str,                 # ISO8601 Z
      "promoted_by": "promote_extracted_sample",
      "version": 1,                       # schema version
  }
  ```

### Symlink quarantine + archive-bomb cap (Area 4)

- **D-15:** Symlink quarantine — recursive post-extract sweep. New
  helper in `extraction.py`:

  ```python
  def quarantine_symlinks(extraction_dir: Path) -> tuple[int, list[str]]:
      """Recursively replace every symlink under extraction_dir with a
      regular file <name>.symlink-target.txt containing the target
      path (as written + resolved). Returns (count, list_of_paths).

      Walks via os.scandir (does NOT follow symlinks). For each symlink:
        1. Read target via os.readlink (no follow).
        2. Resolve absolute target via os.path.realpath(symlink_path).
        3. Write <symlink_path>.symlink-target.txt with the body in D-16.
        4. os.unlink(symlink_path).

      Idempotent: re-running on the same extraction_dir is a no-op
      (there are no symlinks left after the first run).
      """
  ```

  **Timing:**

  - For **sync** wrappers (`run_upx_unpack`, `run_binwalk` in scan
    modes that may incidentally write symlinks — rare): called from
    inside the wrapper AFTER the subprocess returns and BEFORE the
    result dict is returned. `result["symlinks_quarantined"] = count`.

  - For **job-dispatched** wrappers (`run_unblob`, `run_binwalk(mode="extract")`):
    quarantine runs as part of the **post-terminal hook in the sibling
    monitor task** (D-17). When the monitor observes the job has hit a
    terminal status (`succeeded`, `failed`, `cancelled`,
    `killed_timeout`, `killed_log_cap`, `cap_exceeded`), it calls
    `quarantine_symlinks(extraction_dir)`, updates `_mare_meta.json`
    with the final count, then exits. This guarantees the quarantine
    happens BEFORE the agent polls `list_extracted_files` and sees the
    extracted files via Resources.

- **D-16:** `.symlink-target.txt` file body — exact format:

  ```
  SYMLINK QUARANTINE
  Original symlink (relative within extraction): <relpath under extraction_dir>
  Target (as-written by extractor):              <os.readlink result>
  Resolved target (canonical absolute):          <os.path.realpath result>
  Quarantined: <UTC ISO8601 Z timestamp>
  Reason: Symlinks outside an extraction can read host files via the MCP Resources walker; quarantining preserves the original link metadata as plain text without enabling traversal.
  ```

  Filenames retain the original final segment; only the OS-level link
  type changes. Example: `extracted/unblob-2026-05-19T14:32:11Z-7b1c/usr/lib/libc.so.6`
  (a symlink to `/lib/x86_64-linux-gnu/libc.so.6` on a typical Linux
  rootfs) becomes
  `extracted/unblob-2026-05-19T14:32:11Z-7b1c/usr/lib/libc.so.6.symlink-target.txt`.

  Tests:

  - Quarantine produces the marker file with all four fields populated.
  - Original symlink is gone (`os.path.islink(orig) == False`).
  - Subsequent extraction monitor poll counts the marker as a regular
    file (size > 0, name ends in `.symlink-target.txt`).
  - `list_extracted_files` flags entries with
    `is_symlink_quarantine=True` based on suffix match.

- **D-17:** Archive-bomb cap monitor — lightweight sibling
  `asyncio.Task`, NOT a registry:

  ```python
  # In extraction.py
  async def start_extract_monitor(
      job_id: str,
      extraction_dir: Path,
      *,
      interval_s: float | None = None,
      max_bytes: int | None = None,
  ) -> None:
      """Periodically `du -sb extraction_dir` until the job hits terminal.

      Behavior:
      1. Read interval_s and max_bytes from module constants if None.
      2. Loop:
         a. await asyncio.sleep(interval_s)
         b. snap = tools_jobs.get_tool_job(job_id)  # programmatic, no ctx
         c. if snap["status"] in TERMINAL: break  (run post-terminal hook)
         d. size = _du_sb(extraction_dir)
         e. update_meta(extraction_dir, {"extract_bytes_total": size, "monitor_polls": <n>})
         f. if size > max_bytes:
              # Mark + cancel + break
              (extraction_dir / ".MARE_EXTRACT_CAP_EXCEEDED").write_text(
                  f"Cap: {max_bytes} bytes; observed: {size} bytes; at: {ISO}\n"
              )
              update_meta(extraction_dir, {"cap_exceeded": True, "status": "cap_exceeded"})
              await tools_jobs.cancel_tool_job(job_id)
              break
      3. Post-terminal hook (runs on any exit path):
         - quarantine_symlinks(extraction_dir)
         - final = tools_jobs.get_tool_job(job_id) — get terminal snapshot
         - update_meta with completed_at, exit_code, status (mapping
           job status -> meta status; cap_exceeded sticky if already set),
           symlinks_quarantined, final extract_bytes_total.
      """
  ```

  **Why no separate registry:** monitor tasks self-terminate when the
  job hits terminal status; gateway shutdown cancels all jobs via
  `BackgroundJobRegistry.__aexit__`, which causes the monitor's next
  `get_tool_job` to return a terminal status, which causes the monitor
  to exit cleanly within `interval_s + post_terminal_hook`. Worst-case
  leak is one monitor task per in-flight job at shutdown, all of
  which exit within ~5 seconds of the cancel.

  **`_du_sb` implementation:** prefer `os.walk` + `os.stat` (in-process,
  no subprocess) for speed and robustness. Skip symlinks during the
  walk (matches `du -sb -P`); count regular files only. Test asserts
  `_du_sb` over a 100 MB extraction completes in <50 ms.

- **D-18:** Cap value + monitor interval — env-var module constants in
  `extraction.py`, matching Phase 6 D-08 / Phase 8 D-14 / Phase 9 D-13
  pattern:

  ```python
  MAX_EXTRACT_MB              = _env_int("MCP_GATEWAY_MAX_EXTRACT_MB",               4096)
  EXTRACT_MONITOR_INTERVAL_S  = _env_float("MCP_GATEWAY_EXTRACT_MONITOR_INTERVAL_S", 5.0)
  MAX_FILES_PER_EXTRACTION    = _env_int("MCP_GATEWAY_LIST_EXTRACT_FILES_PER_EXTRACTION", 5000)
  MAX_EXTRACT_BYTES           = MAX_EXTRACT_MB * 1024 * 1024
  ```

  Validated at import (RuntimeError on bad values), same fail-fast
  contract as prior phases. `_env_int` / `_env_float` either imported
  from `sessions.py` (if Phase 8 exports them) or inlined; the
  imports-or-inline choice matches Phase 8 D-06 + Phase 9 D-13 ("MAY
  reuse, MAY inline").

### Module imports and lifespan integration

- **D-19:** Import graph (matches Phase 8 D-06 / Phase 9 D-24 layering
  pattern):

  ```
  extraction.py        imports: artifacts_io, runner, jobs (for
                                JobToolSpec + register_job_tool),
                                tools.samples (resolve_sample), uploads
                                (UPLOAD_DIR, MAX_BYTES)
                       MUST NOT import: tools.* except samples; mcp.server.fastmcp;
                                tools.jobs (avoid circular through register)

  tools/extract.py     imports: extraction, jobs (for spec registration
                                inspection only), tools.jobs (for
                                start_tool_job / cancel_tool_job /
                                get_tool_job programmatic calls per D-13/D-17),
                                tools.case_dirs (resolve_case_dir),
                                tools.samples (resolve_sample),
                                tools.cases (init_case helper if exposed;
                                otherwise call init_status_tree.sh via
                                run_script)
                       MUST NOT import: tools.r2_sessions, tools.shell,
                                tools.re_static (no cross-tool coupling)

  jobs.py              imports extraction._build_unblob_argv +
                       extraction._build_binwalk_extract_argv lazily
                       inside the spec init (top-of-module import is
                       OK; circularity is avoided because extraction.py
                       does not import jobs.py at module top — it
                       imports JobToolSpec inside a function).
  ```

  *Lazy-import detail:* `extraction.py` imports `from .jobs import
  JobToolSpec, register_job_tool` at module top (no circular concern
  because `jobs.py` doesn't import from `extraction.py` at module top
  — instead `jobs.py` references `_build_unblob_argv` lazily inside
  spec construction via `from .extraction import _build_unblob_argv`
  inside a guarded block, OR `jobs.py` and `extraction.py` split the
  build_argv callables so the spec lives in `extraction.py` and is
  registered there via `register_job_tool(_UNBLOB_SPEC)`, NOT in
  `jobs.py`). The cleaner choice is **the second**: specs live where
  the build_argv lives, and `jobs.py` just exports `register_job_tool`
  as the public API. This matches Phase 9 D-04's note that the spec
  REGISTRY is in `jobs.py` but specs themselves can live anywhere that
  imports `register_job_tool`. Phase 9's three ship-with specs
  (`_sleep_probe`, `_log_burst_probe`, `capa`) live in `jobs.py` for
  bootstrapping convenience; Phase 10's two specs live in
  `extraction.py` so the build_argv functions are co-located with the
  Phase-10-owned extraction helpers.

  **Locked:** specs live in `extraction.py`; `jobs.py` is untouched
  except for the public `register_job_tool` API surface (already
  exported per Phase 9 D-04). This refines Phase 9 D-04 without
  reopening it.

- **D-20:** `tools/__init__.py::register_all_tools` adds one import +
  one register call:

  ```python
  from mcp_gateway.tools import extract as extract_tools
  ...
  extract_tools.register(mcp)
  ```

  Order: AFTER `r2_sessions` and `jobs` (Phase 8 + 9 conventions),
  BEFORE the collision check fires. The order matters because
  collision_check (Phase 7 D-11) runs after ALL registrations and
  asserts no overlap; Phase 10's seven new tool names
  (`run_binwalk`, `run_unblob`, `run_upx_test`, `run_upx_list`,
  `run_upx_unpack`, `list_extracted_files`, `promote_extracted_sample`)
  are gateway-domain and have no backend-pass-through analogues, so
  collision is structurally impossible. The collision check still
  runs to enforce the invariant.

- **D-21:** Lifespan changes — **none**. Phase 10 does NOT introduce a
  new registry in `app.py::lifespan`. The two extraction-related
  registries that DO matter for Phase 10 (`BackgroundJobRegistry`
  from Phase 9, `SessionRegistry` from Phase 8) are already wired.
  Phase 10's sibling monitor tasks (D-17) are leaf tasks; they don't
  need a registry because their lifetime is bounded by the job they
  monitor.

  This is the first v1.1 phase that touches `tools/__init__.py` but
  NOT `app.py::lifespan`. Matches Phase 7 D-16's "register but no
  lifespan" pattern, not Phase 8/9's "register + lifespan
  block" pattern.

### Error contract and edge cases

- **D-22:** Structured error dicts (returned by tool surface, NOT
  raised; matches Phase 6 D-04 / Phase 8 D-18 / Phase 9 D-15 "never
  raises" contract):

  ```python
  # case_dir not under STATUS_ROOT or doesn't exist
  {"error": "invalid case_dir",
   "case_dir": str, "hint": "must be a case directory under <STATUS_ROOT>"}

  # sample not under uploads/examples/status or sha256 not found
  {"error": "invalid sample",
   "sample": str, "hint": "pass a sha256 hex string or a path under uploads/ | examples/ | status/"}

  # binwalk version unsupported (CLI shape doesn't match expected parser)
  {"error": "unsupported binwalk version",
   "stderr_head": str, "hint": "expected binwalk2 or binwalk3; report this to the gateway maintainers"}

  # child_path not under <parent_case_dir>/extracted/
  {"error": "child_path must live under parent case's extracted/",
   "parent_case_dir": str, "child_path": str}

  # child is a symlink-quarantine sentinel (not promotable)
  {"error": "child is a symlink quarantine sentinel (.symlink-target.txt) — read it for the original target, do not promote it",
   "child_path": str}

  # archive-bomb cap exceeded (returned by post-job inspection helpers)
  {"error": "extraction cap exceeded",
   "cap_bytes": int, "observed_bytes": int,
   "extraction_dir": str,
   "hint": "the partial extraction tree is preserved; increase MCP_GATEWAY_MAX_EXTRACT_MB if needed"}

  # promotion idempotent re-use (NOT an error; included for parity)
  # — promote_extracted_sample returns idempotent_reuse=True instead of an error dict
  ```

  Every MCP tool returns one of these shapes or a success snapshot —
  never both, never a Python exception bubbling out. Phase 9 D-15 set
  this contract; Phase 10 inherits.

- **D-23:** Per-tool docstring disclaimers — verbatim text MUST appear
  in `run_unblob`, `run_binwalk` (extract-mode portion), `list_extracted_files`,
  and `promote_extracted_sample` (matches Phase 8 SESS-05 + Phase 9
  D-26 pattern):

  ```
  Extraction state lives in case_dir/extracted/<engine>-<ts>-<rand4>/
  with a `_mare_meta.json` provenance sidecar. The in-memory job
  registry for unblob/binwalk_extract is volatile (gateway restart
  cancels in-flight jobs and forgets terminal jobs), but the on-disk
  extraction tree + sidecar are preserved.

  Promotion lineage lives in <new_case_dir>/_lineage.json. Promotion
  is idempotent by sha256 (re-promoting the same child returns the
  existing case dir); pass force_new=True to bypass.

  Extraction tools are shared across all bearer-token clients
  (no per-Mcp-Session-Id keying). Any client with the bearer token
  can see and cancel any extraction job. (Per-session keying deferred
  to v1.2.)
  ```

  Tested via the same docstring-regression mechanism Phase 8 / Phase 9
  established — a single test that `assert disclaimer_text in tool.__doc__`
  for each of the four named tools. Sync-only UPX tools and `run_binwalk`
  scan modes have a shorter disclaimer (no in-memory job mention).

### Test scaffolding

- **D-24:** Wave 0 RED-stub test layout, mirroring Phase 7/8/9 patterns:

  ```
  mcp-gateway/tests/
    extraction/                          # new test package
      __init__.py
      conftest.py                        # shared fixtures (fake extraction tree builders,
                                         #   _require_binwalk_or_skip, _require_unblob_or_skip,
                                         #   _require_upx_or_skip)
      test_extraction_dir.py             # extraction.extraction_dir naming, rand4 collision
      test_meta_sidecar.py               # write_meta / update_meta / read_meta semantics
      test_quarantine_symlinks.py        # D-15, D-16 — sym link sweep + marker file shape
      test_extract_monitor.py            # D-17 — cap-exceed kills job; status="cap_exceeded";
                                         #   gateway-shutdown monitor exit
      test_list_extracted_files.py       # D-05 — engine filter, caps, truncation, quarantine flag
      test_promote_extracted_sample.py   # D-06, D-13, D-14 — re-upload, dedup, idempotent reuse,
                                         #   force_new, lineage shape
      test_run_binwalk.py                # D-02 — signatures parse, entropy parse, extract->job
      test_run_unblob.py                 # D-03 — job dispatch, meta sidecar update,
                                         #   unblob_report population on terminal
      test_run_upx.py                    # D-04 — test/list/unpack parsing
      test_job_specs_unblob.py           # _build_unblob_argv pure-function tests
      test_job_specs_binwalk_extract.py  # _build_binwalk_extract_argv pure-function tests
      test_disclaimers.py                # D-23 docstring regression
      test_tool_list_phase10.py          # bumps EXPECTED_TOOLS 47 -> 54 invariant
  ```

  All test files start as RED stubs (Phase 6 D-XX, Phase 7 D-XX, Phase
  8 D-XX, Phase 9 D-XX consistent practice): the test functions import
  the not-yet-existing Phase 10 modules at function top, so pytest
  collection passes but execution ImportErrors. Wave 1/2 turns them
  GREEN. Pytest.skip is forbidden EXCEPT for `_require_<tool>_or_skip`
  fixtures that gate slow integration tests when the underlying tool
  isn't installed on the dev host (matches Phase 7 + Phase 9
  precedent).

  Slow integration tests (e.g., real unblob on a known firmware
  fixture) are gated with `@pytest.mark.slow + _require_unblob_or_skip`
  per Phase 6's `slow` marker convention.

### Claude's Discretion

- Internal naming of private helpers in `extraction.py`
  (`_du_sb`, `_utc_now_iso`, `_hash_file_streaming`, `_existing_case_for_sha256`,
  etc.). The PUBLIC surface (`extraction_dir`, `quarantine_symlinks`,
  `start_extract_monitor`, `write_meta`, `update_meta`, `read_meta`,
  `enumerate_extractions`) is locked.

- Whether to inline `_env_int` / `_env_float` in `extraction.py` or
  import from `sessions.py`. Phase 8 D-06 said "MAY import"; Phase 9
  D-13 said "MAY inline." Phase 10's lean: import if `sessions.py`
  already exports them publicly (no underscore); otherwise inline. The
  research phase will verify.

- Whether `run_binwalk(mode="signatures")` uses `binwalk --json` (if
  binwalk3 is in Kali) or parses `binwalk -B` text. The wrapper code
  branches at runtime via a one-shot capability detection on first
  call; the research phase locks the binwalk-version-detection
  approach.

- Exact wording of error-hint strings in D-22 (the structure is
  locked; the prose can be polished).

- Whether `list_extracted_files`'s response also includes a
  per-extraction `engine_specific_summary` block (e.g., for unblob,
  the top-level chunk types from the report.json; for upx, the
  packer version). Probably yes for unblob (free signal from the
  already-parsed report), maybe-not for binwalk/upx. Final call made
  during planning.

- Whether to expose a thin `cancel_extraction(case_dir, extraction_dir)`
  helper that fronts `cancel_tool_job(job_id)` using the meta sidecar
  for job_id lookup. Convenience-only — agents can already cancel via
  Phase 9. Lean: NO — keeps the surface minimal and orthogonal.

- Whether `promote_extracted_sample`'s `_lineage.json` is also
  registered as a 14th MCP Resources artifact (so it surfaces in
  `mare://cases/<case>/_lineage.json`). Phase 7 D-26's Resources
  walker walks depth ≤ 2 and includes top-level files automatically,
  so _lineage.json is exposed by default. Lean: yes (free), confirm
  during planning.

- ANSI-strip / UTF-8-codepoint-boundary truncation reuse from Phase 6
  in the per-engine output parsers — if Phase 6 exports the helpers,
  reuse; otherwise inline (same Phase 9 D-discretion item 4 pattern).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### v1.1 milestone requirements

- `.planning/REQUIREMENTS.md` §"Extraction Tier (EXTR)" (EXTR-01..EXTR-06) — the six authoritative requirements for this phase
- `.planning/REQUIREMENTS.md` §"Out of Scope (v1.1)" — confirms mount-namespace isolation deferred, no INetSim/sandboxed-network for dynamic mode (relevant context for extraction running with same posture-only confinement)
- `.planning/ROADMAP.md` §"Phase 10: Extraction Tier" — phase goal, depends-on (Phases 6, 7, 9), six success criteria

### Project & milestone framing

- `.planning/PROJECT.md` §"Current Milestone: v1.1 Remote RE Tool Expansion" — "Extraction tier" target-feature paragraph naming `run_unblob`, `binwalk -e`, `run_upx_test`/`run_upx_unpack`, `extract_embedded_files`, `list_extracted_files`, `promote_extracted_sample`
- `.planning/PROJECT.md` §"Key Decisions" / "Out of Scope" — confirms gateway exposes primitives, orchestrator composes; no composite `extract_and_promote`

### Phase 6 chokepoint runner (the layer this phase sits on)

- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` D-01..D-04 — `ReToolRunner` class shape, the 12-key locked result dict, the "never raises on subprocess state" contract
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` D-08, D-09 — env-var module-constant pattern, `tool-logs/<UTC>Z-<slug>-<rand4>.txt` log filename shape (Phase 10 D-07 mirrors for `extracted/<engine>-<UTC>Z-<rand4>/`)
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` D-15, D-16 — `ensure_subdir` lazy creation + `EXPANDED_CASE_SUBDIRS` 9-name catalog (Phase 10 reuses `extracted/`, adds zero entries)
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` D-17 — `start_new_session=True` + `killpg` process-group contract (Phase 10's extract monitor relies on Phase 9 enforcing this when cancelling)

### Phase 7 case-dir conventions

- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` D-09 — `tool_log_path` API and filename shape (Phase 10 D-07 calls the same rand4+UTC machinery)
- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` D-11..D-15 — `assert_no_collisions` invariant (Phase 10's seven tool names must not collide with backend-pass-through)
- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` D-16 — `register_all_tools` single registration entry point + EXPECTED_TOOLS bump precedent (Phase 10 D-01 bumps 47 → 54)
- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` D-21..D-25 — `write_artifact` / `append_artifact` / `list_artifacts` / `get_artifact_tree` / `get_tool_log` (Phase 10 may use `write_artifact` for `_mare_meta.json` writes; planner decides)
- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` D-26 — depth-2 Resources walker (Phase 10's `_mare_meta.json` sidecars, `.symlink-target.txt` quarantine files, and `_lineage.json` are auto-exposed without walker changes)

### Phase 8 registry pattern (precedent for extraction monitor — even though Phase 10 does NOT introduce a registry)

- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-06 — primitive (`sessions.py`) + MCP surface (`tools/r2_sessions.py`) split; import-direction invariants (Phase 10 D-19 mirrors)
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-14 — env-var module-constant pattern + `_env_float`/`_env_int` helpers (Phase 10 D-18 reuses-or-inlines)

### Phase 9 background jobs (the layer extract/unblob sit on)

- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-01..D-05 — `start_tool_job` signature, `JobToolSpec` shape, registry pattern (Phase 10 D-11 registers two new specs via `register_job_tool`)
- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-06 — `JobStatus` 7-state vocabulary (Phase 10 does NOT extend; "cap_exceeded" is a meta-sidecar field, not a JobStatus)
- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-15 — structured error dicts contract (Phase 10 D-22 inherits)
- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-16..D-18 — two-tier progress reporting (Phase 10 unblob spec MAY supply a progress_parser; binwalk_extract spec ships with None — research-phase verifies)
- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-19 — job snapshot 25-key result shape (Phase 10 D-10 layers `engine`, `mode`, `extraction_dir`, `symlinks_quarantined`, `meta_path` on top)
- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-20 — `list_tool_jobs(state="_specs")` discovery (Phase 10's two new specs auto-surface)
- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-25 — LIFO lifespan nesting (Phase 10 adds no new registry layer)
- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-26 — docstring disclaimer regression (Phase 10 D-23 adds a 4-tool disclaimer)

### Existing source files (read before writing plans)

- `mcp-gateway/src/mcp_gateway/runner.py` — `ReToolRunner` implementation; Phase 10 sync wrappers (UPX, binwalk scan modes) use `run_tool` convenience helper directly
- `mcp-gateway/src/mcp_gateway/jobs.py` — `register_job_tool`, `JobToolSpec`, `JOB_TOOL_REGISTRY`; Phase 10 registers two new specs from `extraction.py` import
- `mcp-gateway/src/mcp_gateway/tools/jobs.py` — `start_tool_job` / `get_tool_job` / `cancel_tool_job`; Phase 10 wrappers call these programmatically (not via MCP roundtrip)
- `mcp-gateway/src/mcp_gateway/tools/samples.py` — `resolve_sample` (sha256 or path), `UPLOADS_ROOT`; Phase 10 promotion writes new files under `UPLOADS_ROOT/<sha256>/`
- `mcp-gateway/src/mcp_gateway/uploads.py` — `<UPLOAD_DIR>/<sha256>/<filename>` layout, 1 GB cap (relevant for promotion's re-upload — Phase 10 reuses the layout, does NOT re-implement the streaming server endpoint)
- `mcp-gateway/src/mcp_gateway/tools/cases.py` — `CASE_NAME_RE` (`^\d{3}-.+`), `STATUS_ROOT`; Phase 10 promotion writes lineage to `<new_case_dir>/_lineage.json`
- `mcp-gateway/src/mcp_gateway/tools/artifacts.py` — `init_case(sample, new=True)` MCP tool (calls `init_status_tree.sh`); Phase 10 promotion calls this to materialize the new case dir + 13 empty artifact files
- `mcp-gateway/src/mcp_gateway/artifacts_io.py` — `confine_to`, `ensure_subdir`, `tool_log_path`, `EXPANDED_CASE_SUBDIRS`; Phase 10 `extraction_dir` helper reuses the slug+rand4 machinery
- `mcp-gateway/src/mcp_gateway/tools/__init__.py::register_all_tools` — single registration entry point; Phase 10 D-20 adds one import + one register line
- `mcp-gateway/src/mcp_gateway/tools/resources.py` — depth-2 walker; Phase 10 sidecars + quarantine markers + `_lineage.json` are auto-exposed
- `mcp-gateway/tests/test_tool_list.py::EXPECTED_TOOLS` — invariant set bumped 47 → 54 in Phase 10 (Rule-1 deviation precedent set by Phase 7-08 and 9-03)
- `scripts/init_status_tree.sh` — the existing case-init script invoked by `init_case`; Phase 10 promotion calls `init_case` via the existing MCP-tool path (NOT by exec'ing the script directly)
- `Dockerfile` — confirms `binwalk`, `unblob`, `upx-ucl` are pre-installed in the Kali container (`apt-get install binwalk yara upx-ucl ... unblob`)

### MCP protocol references

- MCP spec 2025-03-26 progress notifications — Phase 10 unblob spec MAY emit progress via Phase 9 D-16's Tier-2 poll-side push; binwalk_extract starts with no progress_parser
- FastMCP `Context` parameter injection — Phase 10 wrappers accept `ctx: Context | None` as the last positional arg per FastMCP convention (matches Phase 9 D-05)

### Tools to be wrapped — research-phase verification needed

- **binwalk** documentation — verify whether Kali (`kalilinux/kali-rolling`) ships binwalk2 (python) or binwalk3 (rust); CLI flag differences affect `_build_binwalk_extract_argv` and the `mode="signatures"` parser path. Also verify `binwalk -E` entropy output format (text vs PNG) and whether `--json` is supported.
- **unblob** documentation (https://unblob.org/) — verify CLI shape for `--report`, `--extract-to`, `--depth`; verify exit codes; verify whether unblob emits parseable progress on stderr (informs D-11's `_parse_unblob_progress`).
- **upx-ucl** documentation — exact stderr format for `-t` ("tested 1 file"), `-l` table columns, `-d -o <out>` behavior on non-UPX inputs (informs D-04 parsers).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets

- `mcp_gateway.runner.ReToolRunner` + `run_tool(...)` — synchronous extraction wrappers (UPX, binwalk scan modes) use `run_tool` directly. Job-dispatched wrappers (`run_unblob`, `run_binwalk` extract mode) use `start_tool_job` which calls `ReToolRunner.run` internally through `BackgroundJobRegistry._spawn_and_drive`.
- `mcp_gateway.jobs.register_job_tool(JobToolSpec)` + `JOB_TOOL_REGISTRY` — Phase 10's two new specs (`unblob`, `binwalk_extract`) land via this public surface from `extraction.py` import.
- `mcp_gateway.tools.jobs.start_tool_job / get_tool_job / cancel_tool_job` — Phase 10 wrappers + monitor task call these programmatically (no MCP roundtrip; calling MCP tools as Python functions is supported because they're registered FastMCP handlers that double as callable Python coroutines).
- `mcp_gateway.tools.samples.resolve_sample` — sha256 or container-path → absolute; Phase 10 wrappers call before `confine_to`.
- `mcp_gateway.tools.samples.UPLOADS_ROOT` — `<sha256>/<basename>` layout; Phase 10 promotion's re-upload writes under this root.
- `mcp_gateway.tools.case_dirs.resolve_case_dir` — case_dir → absolute, with STATUS_ROOT enforcement; Phase 10 wrappers call as the first validation step.
- `mcp_gateway.tools.cases.CASE_NAME_RE` + `init_case` MCP tool — Phase 10 promotion calls `init_case(sample=<sha256>, new=True)` to materialize the new case dir.
- `mcp_gateway.artifacts_io.confine_to` — Phase 10 calls on every path-accepting kwarg (`case_dir`, `child_path`, `extraction_dir`).
- `mcp_gateway.artifacts_io.tool_log_path` — Phase 10 `extraction_dir` helper reuses the slug-encoding + UTC-Z + rand4 machinery (parameterizing on subdir + prefix instead of `tool-logs` + slug).
- `mcp_gateway.artifacts_io.EXPANDED_CASE_SUBDIRS` — `extracted/` is in the catalog; lazy-creation works on first call to `extraction.extraction_dir`.
- `mcp_gateway.uploads.UPLOAD_DIR` + `MAX_BYTES` — Phase 10 re-upload helper writes streaming via `os.rename(tmp, final)` for atomicity.
- Phase 7 D-26 Resources walker — already walks depth ≤ 2 under `extracted/`, so per-extraction `_mare_meta.json`, `.symlink-target.txt` markers, and the unblob `report.json` are auto-exposed via `mare://cases/<case>/extracted/<engine>-<ts>-<rand4>/<file>` URIs without walker changes.

### Established patterns

- **Primitive + tools/ surface split** (Phase 6, 8, 9) — Phase 10 follows literally: `extraction.py` is the primitive (no MCP decorators), `tools/extract.py` is the surface (every function `@mcp.tool()`-decorated, returns dicts, never raises).
- **JobToolSpec registration at module import** (Phase 9 D-04) — Phase 10's two specs land via `register_job_tool(...)` at `extraction.py` module-level.
- **Layer onto Phase 6's 12-key result dict** (Phase 8 D-11 / Phase 9 D-19) — Phase 10 D-10 follows for both sync (12-key + extensions) and async (25-key + extensions) wrappers.
- **Module-level env-var constants validated at import** (Phase 6 D-08 / Phase 8 D-14 / Phase 9 D-13) — Phase 10 D-18 follows identically.
- **Structured error dicts, never raise out of MCP tools** (Phase 6 D-04 / Phase 8 D-18 / Phase 9 D-15) — Phase 10 D-22.
- **Docstring disclaimer regression test** (Phase 8 SESS-05 / Phase 9 D-26) — Phase 10 D-23 adds a four-tool disclaimer.
- **Collision check at lifespan** (Phase 7 D-11) — Phase 10's seven tool names enforce non-collision (gateway-domain names, structurally non-colliding with backend pass-through).
- **No new lifespan registry when work fits as sibling tasks** (Phase 7 D-16 precedent — Phase 7 registered tools without adding a lifespan block) — Phase 10 D-21 adds zero lifespan changes.

### Integration points

- `tools/__init__.py::register_all_tools` — one new import + one register call.
- `jobs.py` — no edits to the module body; Phase 10's specs are registered via the existing `register_job_tool` public API from `extraction.py`.
- `session_state.py` — no new slot. Phase 10 uses Phase 9's `JOB_REGISTRY` slot transparently via `tools.jobs.start_tool_job`.
- `app.py::lifespan` — no changes (D-21).
- `artifacts_io.py::EXPANDED_CASE_SUBDIRS` — no changes (D-07 reuses `extracted/`).
- `tools/resources.py` — no changes (depth-2 walker already covers extraction trees).
- `tests/test_tool_list.py::EXPECTED_TOOLS` — bumped 47 → 54 (Rule-1 deviation, precedent set by Phase 7-08 and 9-03 SUMMARY notes).

</code_context>

<specifics>
## Specific Ideas

- **"Asymmetric return shape via `mode` discrimination"** for `run_binwalk` is the explicit decision (D-02). Agent reads `result["mode"]` and discriminates: sync-mode reads `signatures`/`entropy`, extract-mode reads `job_id` and polls. This is the more robust shape for analyst-facing ergonomics — one tool name per requirement spelling, asymmetric result documented exhaustively.

- **"Promotion idempotency by sha256 globally"** (D-14) is the analyst-trust decision. Re-extracting the same firmware twice and promoting the same child file converges to ONE case dir. Two clients promoting the same child converge. The `_lineage.json` is the durable lineage record; `_existing_case_for_sha256` is the lookup index. `force_new=True` is the safety valve.

- **"Cap enforcement via sibling monitor task, not a new JobStatus"** (D-17) is the don't-reopen-Phase-9 decision. The cap is a Phase 10 concern enforced via a Phase 10 helper; Phase 9's vocabulary stays locked. The durable signal (`.MARE_EXTRACT_CAP_EXCEEDED` marker + `_mare_meta.json` `cap_exceeded=true`) is on disk; the in-memory Phase 9 job status remains `cancelled`. Analysts inspecting `list_extracted_files` or browsing Resources see the cap-exceeded state immediately.

- **"Symlink quarantine is post-extract, recursive, before result return"** (D-15) is the Resources-walker-safety invariant. Symlinks in firmware extractions can resolve to `/etc/shadow` on the host; the Resources walker follows them by default. Replacing symlinks with text sentinels eliminates the traversal vector while preserving the metadata an analyst needs.

- **"Specs live where build_argv lives"** (D-11, D-19) is the import-graph clean-up of Phase 9 D-04's "ship-with capa spec lives in jobs.py" pragma. Phase 10's `unblob` and `binwalk_extract` specs co-locate with the build_argv functions in `extraction.py`; `jobs.py` exports `register_job_tool` as the public API only. This refines (does not reopen) Phase 9 D-04.

- **"No new lifespan block"** (D-21) is the don't-add-unnecessary-machinery decision. Phase 10 has zero registry-shaped work — extraction-dir creation is leaf-helper-shaped, extraction monitor is a sibling task bounded by its job's lifetime. Phase 7 set the precedent for "register but no lifespan."

</specifics>

<deferred>
## Deferred Ideas

- **`tools/job_specs/` refactor** — defer to Phase 11. Phase 10 brings spec count to 3 (capa + unblob + binwalk_extract); Phase 11 adds 4–5 more (ghidra_analyze, strace, ltrace, qemu_user, possibly ida_analyze) and crosses the 5-spec threshold Phase 9 D-04 marked.

- **Promotion lineage as a versioned audit log** — Phase 10 writes a single `_lineage.json` at promotion time; updates (e.g., re-promoting with different parent context) overwrite. A future v1.2 phase could turn this into an append-only `_lineage.jsonl` for full history, especially if multi-parent attribution becomes valuable.

- **Hot-list of "interesting" extracted files** — Phase 10 returns a flat file list; future phases could compute a heuristic interestingness score (executables, scripts, configs, certs, key material) and surface a `hot_files` field. Out of scope here; orchestrator skill (Phase 12) is the right home.

- **Cross-case extraction tree visualization** — out of scope. Analysts can build their own DAG by walking `_lineage.json` across cases; a gateway-side graph API is a v1.2+ concern.

- **`MCP_GATEWAY_MAX_EXTRACT_MB` as a hard FS quota** — Phase 10 enforces via periodic stat (D-17). A future phase could use `prlimit --fsize` on the extraction subprocess or a tmpfs mount with size cap; both require additional capabilities or container setup and are out of scope for v1.1's posture-only confinement.

- **Auto-promotion of "interesting" children** — explicitly out of scope per PROJECT.md "Out of Scope" (composite tools). Orchestrator skill (Phase 12) composes `run_unblob` → `list_extracted_files` → heuristic → `promote_extracted_sample`.

- **Persistent extraction monitor state across gateway restart** — Phase 10 monitor tasks die with the gateway. The marker file + sidecar are durable, so analysts can observe the truncated state on restart and re-run. A future "registry hydration" phase (companion to Phase 9 deferred "persistent job state") could re-spawn monitors on restart; orthogonal to Phase 10.

- **Per-engine quotas (e.g., a tighter cap for binwalk than unblob)** — Phase 10 enforces one cap value across all three engines. A future phase could differentiate; not warranted by current usage data.

- **Run-shell extraction (using `run_shell` to call binwalk/unblob/upx with custom args)** — already covered by Phase 7's `run_shell`; not in Phase 10 scope. Phase 10 wrappers exist for discoverability + parsing + provenance, not as the exclusive surface.

### Reviewed todos (not folded)

None — no pending todos matched Phase 10 scope (the open items in STATE.md "Pending Todos" target Phases 7/8/9/11; none apply to extraction).

</deferred>

---

*Phase: 10-extraction-tier*
*Context gathered: 2026-05-19*
