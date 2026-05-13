---
phase: 06-retoolrunner-artifacts-io-foundation
verified: 2026-05-13T00:00:00Z
status: passed
score: 5/5 success criteria verified
overrides_applied: 0
---

# Phase 6: ReToolRunner + artifacts_io Foundation Verification Report

**Phase Goal:** One auditable, OOM-safe execution path exists for every v1.1 subprocess invocation, and every path-accepting tool can reject traversal uniformly
**Verified:** 2026-05-13
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria + PLAN must_haves)

| #  | Truth                                                                                                                                                       | Status     | Evidence                                                                                                                                                  |
| -- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1  | SC-1: argv-only spawn via `asyncio.create_subprocess_exec`, cwd-confined to resolved case_dir, hard timeout, process-group SIGKILL on timeout/cancel        | VERIFIED   | runner.py:217 `create_subprocess_exec`, 219 `cwd=str(self._case_dir)`, 223 `start_new_session=True`, 245 `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)`; 4 tests pass: test_runner_never_uses_shell_true, test_cwd_is_resolved_case_dir, test_timeout_kills_process_group, test_cancel_propagates_to_killpg |
| 2  | SC-2: 12-key D-03 return shape (exit_code, timed_out, duration_s, stdout_head, stdout_truncated, stdout_bytes_total, stderr_head/truncated/bytes_total, log_path, argv, slug) in exact order | VERIFIED   | runner.py:274-287 return dict; test_return_shape_locked asserts `list(result.keys()) == expected_keys` exactly                                            |
| 3  | SC-3: full stdout/stderr auto-captured to `case_dir/tool-logs/<ts>-<slug>-<rand4>.txt`; only head-truncated preview returned over MCP                       | VERIFIED   | runner.py:210 `ensure_subdir(self._case_dir, "tool-logs")`, 211 `tool_log_path`, 212 `relative_to(self._case_dir)`, 284 `log_path: str(log_rel)`; test_log_capture_and_head_alignment passes |
| 4  | SC-4: 100 MB urandom completes with bounded RSS (no PIPE deadlock, no OOM)                                                                                  | VERIFIED   | runner.py:231-239 concurrent `asyncio.gather` of two `_drain` coros with head_cap_bytes + file sink; test_100mb_urandom_bounded_rss (slow) passed (stdout_bytes_total=104857600, stdout_truncated=True, RSS delta < 32 MB) |
| 5  | SC-5: canonical `confine_to(case_dir, path)` rejects path traversal and is importable from every v1.1 tool module                                          | VERIFIED   | artifacts_io.py:55-97 implements confine_to with NUL-byte rejection, strict=True case_dir resolve, is_relative_to containment; 9 confine_to tests pass (relative-inside, nonexisting-leaf, traversal, abs-outside, inside-symlink, escaping-symlink, NUL, nonexistent case_dir, non-dir case_dir) |

**Score:** 5/5 truths verified

### PLAN-level must-haves (truths beyond ROADMAP SC)

| #  | Truth                                                                                                                                              | Status   | Evidence                                                                                                  |
| -- | -------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | --------------------------------------------------------------------------------------------------------- |
| 6  | CancelledError handling: killpg + asyncio.shield(proc.wait()) then re-raise (D-17, Pitfall 18)                                                     | VERIFIED | runner.py:254-261 except CancelledError block matches contract; test_cancel_propagates_to_killpg passes  |
| 7  | TimeoutError swallowed (never raises); returns `{timed_out=True, exit_code=-9, ...}`                                                                | VERIFIED | runner.py:242-253 except TimeoutError sets timed_out=True; line 272 forces exit_code=-9; test_timeout_kills_process_group passes |
| 8  | Module-level env-var validation: 4 `MCP_GATEWAY_RUNNER_*` vars read at import; bad values RuntimeError                                              | VERIFIED | runner.py:52-79 `_env_int`/`_env_float` raise RuntimeError; test_env_validation_rejects_bad_values passes (subprocess.run with bad env exits non-zero + RuntimeError in stderr) |
| 9  | No new pip deps (manifest discipline): no psutil/aiofiles imports; stdlib + anyio only                                                              | VERIFIED | `grep psutil/aiofiles` returns empty; test_no_new_pip_deps passes                                         |
| 10 | DEFAULT_TIMEOUT_S below 60s MCP cap (5s margin)                                                                                                     | VERIFIED | runner.py:78 `DEFAULT_TIMEOUT_S = 55.0`; test_default_timeout_below_mcp_cap passes                        |
| 11 | artifacts_io leaf module (D-07): zero `mcp_gateway.*` imports                                                                                       | VERIFIED | `grep -E "from mcp_gateway|import mcp_gateway" artifacts_io.py` returns empty                             |
| 12 | EXPANDED_CASE_SUBDIRS tuple with exactly 9 names from D-16                                                                                          | VERIFIED | artifacts_io.py:29-39 defines tuple with 9 names; test_expanded_case_subdirs_catalog asserts set + len + isinstance(tuple) |
| 13 | ensure_subdir idempotent with slug regex validation (D-15)                                                                                          | VERIFIED | artifacts_io.py:100-115 mkdir(parents=False, exist_ok=True); _validate_slug; test_ensure_subdir_idempotent + test_ensure_subdir_validates_slug pass |
| 14 | tool_log_path format `<%Y%m%dT%H%M%SZ>-<slug>-<rand4>.txt` with secrets.token_hex(2)                                                                | VERIFIED | artifacts_io.py:118-133; test_tool_log_path_format + test_tool_log_path_no_collision + test_tool_log_path_rejects_bad_slug pass |
| 15 | Pytest `slow` marker registered                                                                                                                     | VERIFIED | pyproject.toml:32-34 `markers = ["slow: marks tests as slow..."]`                                         |

### Required Artifacts

| Artifact                                              | Expected                                                                 | Status     | Details                                                                                                              |
| ----------------------------------------------------- | ------------------------------------------------------------------------ | ---------- | -------------------------------------------------------------------------------------------------------------------- |
| `mcp-gateway/src/mcp_gateway/runner.py`               | ReToolRunner + run_tool + 4 env-var constants (~200+ LoC)                | VERIFIED   | 313 lines; exists; substantive; wired (imported by tests)                                                            |
| `mcp-gateway/src/mcp_gateway/artifacts_io.py`         | confine_to, ensure_subdir, tool_log_path, EXPANDED_CASE_SUBDIRS          | VERIFIED   | 133 lines; exists; substantive; wired (imported by runner.py + tests)                                                |
| `mcp-gateway/tests/test_runner.py`                    | 10 named test functions covering SC-1..SC-4 + D-08 + manifest regression | VERIFIED   | 168 lines; 10 test functions; all GREEN                                                                              |
| `mcp-gateway/tests/test_artifacts_io.py`              | 16 named test functions covering SC-5 matrix + D-09 + D-15 + D-16        | VERIFIED   | 167 lines; 16 test functions; all GREEN                                                                              |
| `mcp-gateway/pyproject.toml`                          | `slow` marker registered under `[tool.pytest.ini_options]`               | VERIFIED   | Lines 32-34 declare `markers = ["slow: ..."]`                                                                        |

### Key Link Verification

| From                                | To                                                  | Via                                                  | Status   | Details                                                                                          |
| ----------------------------------- | --------------------------------------------------- | ---------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------ |
| runner.py                           | mcp_gateway.artifacts_io                            | `from mcp_gateway import artifacts_io`; `from mcp_gateway.artifacts_io import ensure_subdir, tool_log_path` | WIRED    | runner.py:43-44                                                                                  |
| ReToolRunner.run                    | asyncio.create_subprocess_exec                      | argv-only spawn with start_new_session=True          | WIRED    | runner.py:217-224                                                                                |
| ReToolRunner cleanup                | os.killpg(getpgid) + asyncio.shield(proc.wait())    | except TimeoutError + except CancelledError blocks   | WIRED    | runner.py:244-249 (timeout); runner.py:254-260 (cancel)                                          |
| tests/test_runner.py                | mcp_gateway.runner                                  | `from mcp_gateway.runner import ReToolRunner, run_tool, DEFAULT_TIMEOUT_S` | WIRED    | test_runner.py:22-23; all 10 tests collect and pass                                              |
| tests/test_artifacts_io.py          | mcp_gateway.artifacts_io                            | `from mcp_gateway.artifacts_io import EXPANDED_CASE_SUBDIRS, confine_to, ensure_subdir, tool_log_path` | WIRED    | test_artifacts_io.py:14-19; all 16 tests collect and pass                                        |
| artifacts_io.py                     | stdlib only (D-07 leaf)                             | imports: datetime, os, re, secrets, pathlib         | WIRED    | artifacts_io.py:19-25; grep for `mcp_gateway` imports returns empty                              |

### Behavioral Spot-Checks

| Behavior                                                                        | Command                                                                                            | Result                                                                                  | Status |
| ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ------ |
| Import all 6 runner symbols + 4 artifacts_io symbols                            | `python -c "from mcp_gateway.runner import ...; from mcp_gateway.artifacts_io import ..."`         | OK; 9 entries in EXPANDED_CASE_SUBDIRS; DEFAULT_TIMEOUT_S=55.0; STDOUT_HEAD_KB=256       | PASS   |
| D-08 env-var validation rejects bad values                                      | `subprocess.run([python, -c, 'import mcp_gateway.runner'], env={...DEFAULT_TIMEOUT_S=abc})`        | returncode=1; RuntimeError in stderr                                                    | PASS   |
| Phase 6 test suite                                                              | `.venv/bin/pytest tests/test_runner.py tests/test_artifacts_io.py -ra`                              | 26 passed (10 runner + 16 artifacts_io)                                                 | PASS   |
| Full mcp-gateway test suite (regression check)                                  | `.venv/bin/pytest tests/ --ignore=tests/e2e -ra`                                                    | 204 passed                                                                              | PASS   |
| Chokepoint integrity (no shell=True in runner.py)                               | `grep -c 'shell=True' src/mcp_gateway/runner.py`                                                   | 0                                                                                       | PASS   |
| No proc.communicate (Pitfall 1)                                                 | `grep -c 'proc.communicate' src/mcp_gateway/runner.py`                                             | 0                                                                                       | PASS   |
| No forbidden deps (manifest)                                                    | `grep -cE 'import psutil\|import aiofiles' src/mcp_gateway/runner.py`                              | 0                                                                                       | PASS   |
| artifacts_io leaf module (D-07)                                                 | `grep -E 'from mcp_gateway\|import mcp_gateway' src/mcp_gateway/artifacts_io.py`                   | empty                                                                                   | PASS   |

### Requirements Coverage

| Requirement | Source Plan(s) | Description                                                                                                                                                | Status     | Evidence                                                                                                                                                              |
| ----------- | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FOUND-02    | 06-01, 06-03   | Every v1.1 subprocess invocation goes through `ReToolRunner` (argv-only, cwd-confined, hard timeout, pgroup SIGKILL, structured JSON result shape)         | SATISFIED  | runner.py implements full contract; tests 1-7 in test_runner.py verify each property; SC-1, SC-2, SC-4 satisfied                                                       |
| FOUND-03    | 06-01, 06-03   | Runner-driven tools auto-capture full stdout/stderr to `case_dir/tool-logs/<timestamp>-<slug>.txt` while returning only a head-truncated preview           | SATISFIED  | runner.py:210-212 ensure_subdir + tool_log_path + relative_to; runner.py:229 unbuffered append; runner.py:278-281 head decode + truncation flags; SC-3 verified by test_log_capture_and_head_alignment |
| FOUND-04    | 06-01, 06-02   | Canonical `confine_to(case_dir, path)` helper exists for path-accepting tools to reject path traversal (Phase 6 ships helper; adoption across tools is Phase 7+ scope per CONTEXT.md D-14, D-06) | SATISFIED (helper) | artifacts_io.py:55-97 confine_to fully implements D-11..D-14; 9 confine_to tests pass; helper is importable from any v1.1 module. Adoption inside `tools/artifacts.py:115-139` is explicitly deferred per CONTEXT.md "Deferred Ideas" (`Adopting confine_to inside existing tools/artifacts.py::get_artifact... Permitted but not required by Phase 6`) |

All 3 declared requirements satisfied at Phase 6 scope. No orphaned requirements found.

### Anti-Patterns Found

| File                                       | Line  | Pattern                                                | Severity | Impact                                                                                                                                                                       |
| ------------------------------------------ | ----- | ------------------------------------------------------ | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| mcp-gateway/src/mcp_gateway/artifacts_io.py | 100-115 | `ensure_subdir` does not perform containment check after `target.resolve(strict=True)` (REVIEW WR-01) | INFO     | Defense-in-depth gap. A pre-planted symlink at `case_dir/<name>` pointing inside an existing dir could redirect writes outside case_dir. Risk requires earlier filesystem-write vulnerability or operator misconfiguration -- case dirs are gateway-created. Not exploit-imminent; surfaced by REVIEW.md as Warning. Carry forward to Phase 7 hardening backlog. |
| mcp-gateway/src/mcp_gateway/runner.py       | 217-229 | Open-file leak window between spawn and try-block (REVIEW WR-02) | INFO     | If `open(log_abs, "ab", buffering=0)` raises post-spawn (PermissionError, OSError, IsADirectoryError), the freshly-spawned child is orphaned. Not exercised by any test; latent defect. Carry forward to Phase 7 hardening backlog. |
| mcp-gateway/src/mcp_gateway/runner.py       | 82-98 | `_truncate_to_utf8_boundary` can return non-boundary prefix on invalid UTF-8 (REVIEW WR-03) | INFO     | Cosmetic. Docstring contract not strictly met for binary/malformed input. `decode(errors="replace")` masks the artifact. No functional impact on valid UTF-8 streams. Carry forward to Phase 7 hardening backlog. |
| mcp-gateway/tests/test_artifacts_io.py      | 9     | Unused `import time` (REVIEW IN-06)                    | INFO     | Dead import; cosmetic. Linter cleanup.                                                                                                                                       |

No blocker anti-patterns. The 3 REVIEW Warnings are defense-in-depth or contract-clarity gaps; they do not block phase goal achievement and are documented for follow-up.

### Human Verification Required

None. All phase artifacts are testable programmatically, and all tests pass. No visual, real-time, external-service, or UX-quality dimensions are introduced by this phase.

### Gaps Summary

No gaps. The phase ships:
- Chokepoint subprocess primitive (`ReToolRunner`, `run_tool`) with all 12 D-03 return-shape keys, argv-only spawn, `start_new_session=True` + `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` + `asyncio.shield(proc.wait())` cleanup, concurrent `asyncio.gather` drain with head buffer + on-disk file sink, ANSI strip + UTF-8 boundary truncation, env-var validated module-level config knobs.
- Pure path helpers (`confine_to`, `ensure_subdir`, `tool_log_path`, `EXPANDED_CASE_SUBDIRS`) as a stdlib-only leaf module (D-07).
- 26 hermetic tests (10 runner + 16 artifacts_io) all GREEN; full mcp-gateway suite (204 tests) green; no regression.
- All 3 phase requirements (FOUND-02, FOUND-03, FOUND-04) satisfied at Phase 6 scope. FOUND-04's "used by every path-accepting tool" clause is explicitly scoped to Phase 7+ adoption (CONTEXT.md "Deferred Ideas") -- Phase 6 ships the helper and makes it importable, which is what the ROADMAP SC-5 mandates.

REVIEW.md identified 3 Warnings (WR-01 ensure_subdir symlink containment, WR-02 open-file leak window, WR-03 utf8-boundary fallback) and 6 Info items; all are non-blocking and documented above for Phase 7 hardening backlog. They do not affect the chokepoint contract Phase 7+ consumers will rely on.

---

_Verified: 2026-05-13_
_Verifier: Claude (gsd-verifier)_
