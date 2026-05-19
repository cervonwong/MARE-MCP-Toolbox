---
phase: 10-extraction-tier
reviewed: 2026-05-19T00:00:00Z
depth: standard
files_reviewed: 21
files_reviewed_list:
  - Dockerfile
  - mcp-gateway/src/mcp_gateway/extraction.py
  - mcp-gateway/src/mcp_gateway/tools/__init__.py
  - mcp-gateway/src/mcp_gateway/tools/extract.py
  - mcp-gateway/tests/extraction/__init__.py
  - mcp-gateway/tests/extraction/conftest.py
  - mcp-gateway/tests/extraction/test_disclaimers.py
  - mcp-gateway/tests/extraction/test_extract_monitor.py
  - mcp-gateway/tests/extraction/test_extraction_dir.py
  - mcp-gateway/tests/extraction/test_job_specs_binwalk_extract.py
  - mcp-gateway/tests/extraction/test_job_specs_unblob.py
  - mcp-gateway/tests/extraction/test_list_extracted_files.py
  - mcp-gateway/tests/extraction/test_meta_sidecar.py
  - mcp-gateway/tests/extraction/test_promote_extracted_sample.py
  - mcp-gateway/tests/extraction/test_quarantine_symlinks.py
  - mcp-gateway/tests/extraction/test_run_binwalk.py
  - mcp-gateway/tests/extraction/test_run_unblob.py
  - mcp-gateway/tests/extraction/test_run_upx.py
  - mcp-gateway/tests/extraction/test_tool_list_phase10.py
  - mcp-gateway/tests/test_tool_list.py
  - scripts/probe_extraction_tools.sh
findings:
  critical: 0
  warning: 6
  info: 7
  total: 13
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-05-19
**Depth:** standard
**Files Reviewed:** 21
**Status:** issues_found

## Summary

Phase 10 introduces the extraction tier (binwalk3, unblob, upx) with three layers: (1) a leaf primitive module `extraction.py` that owns directory minting, `_mare_meta.json` sidecar I/O, symlink quarantine, atomic re-upload, and the cap-monitor task; (2) seven MCP tools in `tools/extract.py` that wrap those primitives behind D-22 structured error envelopes; and (3) JobToolSpec registrations that integrate with the Phase 9 background-job runtime.

Overall the implementation is careful and well-aligned with the locked decisions (D-07 dir-naming, D-08 atomic sidecar, D-15/D-16 quarantine semantics, D-22 error shapes, D-23 disclaimer splice). Atomic writes use POSIX `os.rename` correctly, symlink quarantine uses `followlinks=False`, hard-link dedup is correct in `_du_sb`, and the GC-safe monitor retention pattern is solid. Tests cover happy paths and key edge cases comprehensively.

Issues found are predominantly **Warning** and **Info** level — most relate to misleading error-envelope reuse, missed cleanup of empty extraction directories on failure, and a couple of small logic glitches in monitor finalisation and list truncation. No security-grade defects detected.

## Warnings

### WR-01: `run_binwalk` returns "invalid sample" envelope for an invalid `mode` argument

**File:** `mcp-gateway/src/mcp_gateway/tools/extract.py:422-430`
**Issue:** When `mode` is outside the allowed set, the function returns `{"error": "invalid sample", ...}` with a hint about `mode`. The error key mis-classifies the failure as a sample problem, which will confuse callers and break any client that branches on `error == "invalid sample"`. There is no `invalid mode` shape defined in D-22, but reusing the sample shape is incorrect — at minimum the hint text contradicts the error key.
**Fix:**
```python
if mode not in ("signatures", "entropy", "extract"):
    return {
        "error": "invalid mode",
        "mode": str(mode),
        "hint": "mode must be one of signatures|entropy|extract",
    }
```
If introducing a new error key is out of scope, change the existing key to `"invalid argument"` or `"invalid mode"` and update the hint accordingly. The current label is actively misleading.

### WR-02: `_BINWALK_ENTROPY_RE` fails to match the test-provided format

**File:** `mcp-gateway/src/mcp_gateway/tools/extract.py:102-104`, `mcp-gateway/tests/extraction/test_run_binwalk.py:74-77`
**Issue:** The entropy regex requires a `[-\s]+` block between `block_start` and `block_end`, with `block_end` matched against `0?x?[0-9A-Fa-f]+` (note the `\s+` after `[-\s]+\s*` plus the entropy group). Lines like `0x00000000  0.123456 rising` (the test fixture format) have only one offset before the floating-point entropy value. The regex will greedily match `0.123456` as `block_end` and then try to consume `rising` as `entropy` — but `rising` doesn't match `[0-9.]+`, so the line falls through to the `raw` fallback branch. The test still passes because `_parse_binwalk_entropy` emits a raw-line row for every unmatched line and the test only asserts `len(...) >= 2`, but the parsed `block_start`/`entropy` fields are never populated for the typical single-offset format.
**Fix:** Make `block_end` truly optional with a clear alternation, e.g.:
```python
_BINWALK_ENTROPY_RE = re.compile(
    r"^\s*(?P<block_start>0?x?[0-9A-Fa-f]+)"
    r"(?:\s*[-]\s*(?P<block_end>0?x?[0-9A-Fa-f]+))?"
    r"\s+(?P<entropy>[0-9]+(?:\.[0-9]+)?)"
)
```
Then add a positive assertion to `test_entropy_mode_parses_rows` that at least one row has a non-None `entropy` value — otherwise the parser regression that this code silently has now will recur unnoticed.

### WR-03: Failed `start_tool_job` leaves an empty extraction directory on disk

**File:** `mcp-gateway/src/mcp_gateway/tools/extract.py:476-494`, `697-715`, `852-868`
**Issue:** Both `run_binwalk(mode="extract")` and `run_unblob` mint a fresh `<case>/extracted/<engine>-...-<rand4>/` directory *before* calling `start_tool_job`. If `start_tool_job` returns an error dict (cap exceeded, invalid kwargs, etc.), the code updates the meta sidecar to `status=failed` but never removes the now-orphaned, otherwise-empty extraction directory. Over time, repeated client mistakes (e.g., bad sample path that slips past `resolve_sample`) accumulate stale extraction dirs visible from `list_extracted_files` and `enumerate_extractions`. `run_upx_unpack` (line 852) has the same shape: extraction_dir is minted before any work, and on `run_tool` failure or exception, an empty directory persists.
**Fix:** On the error branch, attempt a best-effort cleanup:
```python
if isinstance(snapshot, dict) and "error" in snapshot:
    try:
        extraction.update_meta(extraction_path, {...})
    except OSError as e:
        log.warning("[run_binwalk] update_meta(failed) failed: %s", e)
    # Best-effort cleanup of empty extraction dir + meta sidecar
    try:
        meta_p = extraction_path / "_mare_meta.json"
        if meta_p.exists():
            meta_p.unlink()
        # rmdir only if empty (preserves anything the user may have inspected)
        extraction_path.rmdir()
    except OSError:
        pass  # leave dir if non-empty
    return {**snapshot, ...}
```
Alternatively, defer `extraction_dir()` minting until *after* `start_tool_job` succeeds — but that complicates the meta-sidecar contract.

### WR-04: Monitor post-terminal hook may write `completed_at` after job was already terminal at first poll

**File:** `mcp-gateway/src/mcp_gateway/extraction.py:537-574`
**Issue:** When `start_extract_monitor` enters its loop and the *very first* `get_tool_job` call returns a terminal status, the loop breaks immediately without ever incrementing `polls` or writing `extract_bytes_total`. That part is fine. However, the post-terminal hook then unconditionally writes `completed_at: _utc_now_iso()`, overwriting any `completed_at` that the wrapper or the job-runtime may have already set. In the cancellation path (`CancelledError`), the hook *still* runs and stamps a `completed_at` even though the underlying job may still be in flight. This is a soft data-quality issue (timing accuracy) rather than a correctness bug, but it does mean `_mare_meta.json` `completed_at` can drift from `final_snap.exit_code`'s actual termination instant by tens of seconds in the cancellation case.
**Fix:** Prefer the job snapshot's terminal timestamp when available:
```python
final_completed_at = (
    final_snap.get("completed_at")
    if isinstance(final_snap, dict) and final_snap.get("completed_at")
    else _utc_now_iso()
)
update_meta(Path(extraction_dir), {
    "completed_at": final_completed_at,
    ...
})
```
Also consider skipping the `completed_at` write on the `CancelledError` branch when the job is still non-terminal — or emit a distinct `cancelled_at` field.

### WR-05: `list_extracted_files` global-cap truncation logic over-counts and may misreport `truncated`

**File:** `mcp-gateway/src/mcp_gateway/tools/extract.py:1026-1035`
**Issue:** The truncation block runs after the entry is appended with its full `files` list, then trims from the tail:
```python
total_listed += len(files)
if total_listed >= limit_i:
    truncated_overall = total_listed > limit_i or truncated_overall
    overflow = total_listed - limit_i
    if overflow > 0:
        entry["files"] = entry["files"][: max(0, len(entry["files"]) - overflow)]
        total_listed = limit_i
        truncated_overall = True
    break
```
Two issues:
1. If `total_listed == limit_i` exactly (overflow == 0), `truncated_overall` is set to `total_listed > limit_i or truncated_overall` = `False or False = False`, but the loop still `break`s. Subsequent extractions are silently dropped without setting `truncated_overall=True`. A caller asking "did I see everything?" gets a wrong answer when later extractions exist but the limit happened to land exactly on a boundary.
2. The check `if total_listed >= limit_i: ... break` only fires when the *current* extraction pushes the total to or past the limit. If the per-cap already truncated the current extraction, we may have set `files_truncated=True` on the entry but the global `truncated` flag will not reflect that.
**Fix:**
```python
total_listed += len(files)
if files_truncated:
    truncated_overall = True
if total_listed >= limit_i:
    overflow = total_listed - limit_i
    if overflow > 0:
        entry["files"] = entry["files"][:-overflow] if overflow <= len(entry["files"]) else []
        total_listed = limit_i
    # If there are remaining extractions we won't visit, that's truncation too.
    remaining_after = all_extractions.index(ext) + 1 < len(all_extractions)
    if overflow > 0 or remaining_after:
        truncated_overall = True
    break
```

### WR-06: `_existing_case_for_sha256` re-resolves `STATUS_ROOT` from a stale module-level import after test monkeypatching

**File:** `mcp-gateway/src/mcp_gateway/tools/extract.py:168-192`, `1188-1219`
**Issue:** `promote_extracted_sample` calls `_existing_case_for_sha256(sha)` (line 1148), which reads the module-level `STATUS_ROOT` imported at the top of `extract.py` (line 52). Then later (lines 1190, 1216) the wrapper does `STATUS_ROOT.iterdir()` *also* via the module-level alias. This is fine in production, but the test in `test_promote_extracted_sample.py::_setup_roots` already had to monkeypatch both `tools_samples.STATUS_ROOT` and `extract.STATUS_ROOT` to make things work — meaning the dependency on module-level state is fragile and one missed patch will silently use `/agent/status` in tests, causing hard-to-debug filesystem pollution or false-negatives.

This isn't a runtime correctness bug today, but it's a maintainability time bomb: any future caller forgetting the `extract.STATUS_ROOT` patch will trigger filesystem races. Either (a) make these functions take `status_root` as a parameter, or (b) always read through a single accessor function so there's exactly one place to patch.
**Fix:**
```python
def _get_status_root() -> Path:
    from mcp_gateway.tools.samples import STATUS_ROOT
    return STATUS_ROOT

# In _existing_case_for_sha256 and promote_extracted_sample, replace
# STATUS_ROOT with _get_status_root().
```
Then tests only need to patch `tools_samples.STATUS_ROOT`.

## Info

### IN-01: `dedup` flag misuses `Path.exists()`

**File:** `mcp-gateway/src/mcp_gateway/tools/extract.py:1262`
**Issue:** In the non-idempotent return shape, `"dedup": target_path.exists()` will always be `True` because `write_upload` either moved the temp file into `target_path` or detected a pre-existing identical content at `target_path` — in both cases the path exists after the call. The intent appears to be "did write_upload deduplicate?" (i.e., was the file already present pre-call), but the post-call existence test cannot distinguish the two cases.
**Fix:** Have `write_upload` return a `(digest, target_path, was_dedup)` triple, or change the field name to something accurate (e.g., `"upload_finalized": True` if the boolean is meant to indicate success). Currently the field is functionally always `True` on the new-promotion branch and conveys no information.

### IN-02: Unused `Optional` and `asyncio` imports

**File:** `mcp-gateway/src/mcp_gateway/tools/extract.py:31`
**Issue:** Line 31: `import asyncio  # noqa: F401  -- kept for future use; _spawn_monitor is the only spawn site`. The `noqa: F401` masks the unused-import warning, but the comment explains it's "kept for future use." However, `asyncio.TimeoutError` is in fact used (line 1198). The comment is wrong; the import is actively required. Update the comment so a future reader doesn't delete the import based on the misleading rationale.
**Fix:**
```python
import asyncio  # used by `except asyncio.TimeoutError` in promote_extracted_sample
```

### IN-03: `_atomic_write_json` doesn't fsync the parent directory

**File:** `mcp-gateway/src/mcp_gateway/extraction.py:116-127`
**Issue:** The function correctly does `tmp.flush()` + `os.fsync(tmp.fileno())` + `os.rename`, but for true crash-safety on ext4 with default mount options, the *parent directory* should also be fsynced after the rename so the directory entry update is durable. In a container that crashes mid-extraction, the file rename may be lost. Given the workload (per-poll meta updates), full durability isn't critical — but the doc-string claim of POSIX-atomic rename only covers visibility, not durability across crashes.
**Fix (optional):**
```python
os.rename(tmp.name, str(path))
dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
try:
    os.fsync(dir_fd)
finally:
    os.close(dir_fd)
```
Or update the docstring to clarify "atomic visibility, not crash durability."

### IN-04: `_dirname_re` in `extraction.py` and tests duplicate the regex

**File:** `mcp-gateway/src/mcp_gateway/extraction.py:71`, `mcp-gateway/tests/extraction/test_extraction_dir.py:15`
**Issue:** Two distinct regexes describe the same dirname grammar. They are equivalent today, but a future change to (say) `rand4` -> `rand6` will require updating both, and the test won't catch a divergence in production code. Re-export the production regex for test use:
```python
# extraction.py
DIRNAME_RE = _DIRNAME_RE  # public re-export for tests

# test_extraction_dir.py
from mcp_gateway.extraction import DIRNAME_RE as _DIRNAME_RE
```

### IN-05: `_parse_upx_test_stderr` may double-match "tested OK" via case-insensitive check

**File:** `mcp-gateway/src/mcp_gateway/tools/extract.py:316-325`
**Issue:** Minor: `"tested ok" in s.lower()` and `"tested OK" in s.lower()` are redundant — the second can never match because `s.lower()` already lowercases the haystack. The `[OK]` literal is still useful (case-sensitive marker). Cosmetic, but it suggests an unfinished refactor.
**Fix:** Drop the duplicate; keep only `"tested ok" in s.lower()`.

### IN-06: `_find_entropy_plot` only returns the first `.png` filename, not its path

**File:** `mcp-gateway/src/mcp_gateway/tools/extract.py:305-313`, `622`
**Issue:** Returns the bare filename (e.g., `"entropy.png"`). The returned value is then placed into `res["entropy_plot"]` — a top-level field documented as case-relative. The caller can't reconstruct the path without knowing `extraction_dir`. Make the contract explicit by returning a case-relative path (matches `extraction_dir` convention):
**Fix:**
```python
def _find_entropy_plot(extraction_path: Path, case_path: Path) -> Optional[str]:
    try:
        for p in sorted(extraction_path.iterdir()):
            if p.is_file() and p.suffix.lower() == ".png":
                try:
                    return str(p.relative_to(case_path))
                except ValueError:
                    return p.name
    except OSError:
        return None
    return None
```

### IN-07: Empty `__init__.py` raises a system-reminder about file length

**File:** `mcp-gateway/tests/extraction/__init__.py`
**Issue:** The file is empty (0/1 lines per the Read tool). Empty `__init__.py` files are valid Python but some lint configs prefer a single-character newline. Cosmetic only; no action required unless project lint flags it.

---

_Reviewed: 2026-05-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
