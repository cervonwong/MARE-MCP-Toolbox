---
phase: 05-f-1-image-hash-fix
reviewed: 2026-05-12T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - run_docker.sh
  - scripts/compute_image_hash.sh
  - mcp-gateway/tests/test_image_hash.py
findings:
  critical: 0
  warning: 2
  info: 5
  total: 7
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-05-12
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Phase 5 extracts the docker image-hash computation from `run_docker.sh` into a
standalone helper script (`scripts/compute_image_hash.sh`) with `LC_ALL=C`
applied to `sort` for locale stability, and adds a hermetic pytest regression
(`mcp-gateway/tests/test_image_hash.py`) that exercises the four success
criteria (SC-1..SC-4) plus a Binja-toggle bonus and a clear contract error case.

Overall the change set is small, focused, and well-scoped. The helper's
contract (positional build-root arg, 4 optional env vars, single 64-char hex
on stdout, non-zero on bad input) matches what `run_docker.sh:212-218` invokes
and what the pytest exercises. The test is hermetic (no docker, no network),
sets a clean env to prove locale-independence, and uses `timeout=10` plus
`capture_output=True` as good subprocess hygiene.

Two warnings are recorded around the `find … | xargs sha256sum` idiom: an
empty-input edge case where `xargs` falls back to running `sha256sum` on stdin,
and the lack of NUL-delimited file handling. Both are latent — they do not
affect today's `docker-bin/` or `mcp-gateway/` trees — but are easy to harden
now while the helper is freshly factored.

The remaining five findings are informational (style, consistency,
documentation).

## Warnings

### WR-01: `xargs sha256sum` invokes `sha256sum` with no arguments when find produces zero matches

**File:** `scripts/compute_image_hash.sh:35,40`
**Issue:**
The pipelines

```bash
find "$BUILD_ROOT/docker-bin" -type f -print | LC_ALL=C sort | xargs sha256sum
find "$BUILD_ROOT/mcp-gateway" … -o -type f -print | LC_ALL=C sort | xargs sha256sum
```

use GNU `xargs` without `-r` (a.k.a. `--no-run-if-empty`). When `find` matches
zero files (e.g., an empty `docker-bin/` during a misconfigured build, or a
`mcp-gateway/` where every file lives under a pruned directory), `xargs` still
invokes `sha256sum` once with no arguments, which then **reads from stdin**.
Since the pipe is closed it gets EOF immediately and produces the canonical
empty-stdin digest line:

```
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  -
```

That line gets mixed into the outer `sha256sum` aggregate, silently
contributing a "phantom" entry that is indistinguishable from "directory
genuinely contained one empty file". Today both directories are always
non-empty in practice, so this is latent — but it is exactly the kind of
hidden flap source the phase set out to eliminate.

**Fix:** Add `-r` (GNU) so `xargs` is a no-op on empty input. While there,
switch to NUL delimiters to also fix WR-02:

```bash
find "$BUILD_ROOT/docker-bin" -type f -print0 \
  | LC_ALL=C sort -z \
  | xargs -0 -r sha256sum
find "$BUILD_ROOT/mcp-gateway" \
  -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \
             -o -name .venv -o -name '*.egg-info' -o -name htmlcov \
             -o -name node_modules -o -name dist \) -prune \
  -o -type f -print0 \
  | LC_ALL=C sort -z \
  | xargs -0 -r sha256sum
```

If portability to non-GNU `xargs` matters, an equivalent guard is
`| { read -d '' first || exit 0; { printf '%s\0' "$first"; cat; } | xargs -0 sha256sum; }`,
but `-r` is fine on the Kali/Debian builder this repo targets.

### WR-02: `find … -print | xargs sha256sum` is not safe for filenames containing whitespace, quotes, or newlines

**File:** `scripts/compute_image_hash.sh:35,40`
**Issue:**
The default `xargs` parser splits on whitespace and treats single/double quotes
as delimiters, so a filename containing a space, tab, newline, or quote
character will be hashed under the wrong path — or `sha256sum` will fail with
"No such file or directory" and `set -o pipefail` will abort the helper.
Today's repo has no such filenames in `docker-bin/` or `mcp-gateway/`, but
a pytest fixture, a future contributor, or an editor's temp file could
trivially trip this.

**Fix:** Use NUL-delimited piping (see WR-01 patch). `find -print0`,
`sort -z`, and `xargs -0` are all available on the GNU coreutils the
container ships with. This collapses WR-01 and WR-02 into a single robust
idiom.

## Info

### IN-01: Inconsistent non-zero exit codes (2 vs 3) for "bad input"

**File:** `scripts/compute_image_hash.sh:11,15,26,30`
**Issue:**
The helper uses exit code `2` for missing build-root / missing Dockerfile and
exit code `3` for missing Binja/IDA zips. The D-05 contract only requires
"non-zero", and the pytest only checks `returncode != 0`, so this is purely
informational — but mixing 2 and 3 with no documented meaning invites
guesswork from future readers. Either pick one code or document the mapping in
a header comment.

**Fix (optional):**
```bash
# Exit codes:
#   0  success
#   2  missing build context (build root or Dockerfile not found)
#   3  configured optional input missing (Binja/IDA zip path declared but file absent)
```

### IN-02: `_hash` test helper does not assert `len(res.stdout.splitlines()) == 1`

**File:** `mcp-gateway/tests/test_image_hash.py:45-59`
**Issue:**
The D-05 contract says the helper must print "the 64-char sha256 hex hash to
stdout, *nothing else*". The test currently only checks that
`res.stdout.strip()` is 64 chars long, so a regression that printed an extra
debug line above the hash (e.g., `set -x` accidentally left in) and then
emitted the hash on the last line would still pass after `.strip()` collapses
trailing whitespace — but only when there is no leading content. A debug line
*above* the hash would actually fail (strip leaves the newline-joined string,
which exceeds 64 chars), so this is mostly a documentation gap rather than a
real hole. Worth tightening to lock the contract.

**Fix:**
```python
lines = res.stdout.splitlines()
assert len(lines) == 1, f"helper printed extra stdout: {res.stdout!r}"
out = lines[0]
assert len(out) == 64 and all(c in "0123456789abcdef" for c in out), \
    f"expected 64-char hex, got {out!r}"
```

### IN-03: `HOME` forwarded to helper but never read

**File:** `mcp-gateway/tests/test_image_hash.py:46-49`
**Issue:**
`base_env` forwards `HOME` "just in case", but neither `bash`, `sha256sum`,
`find`, `sort`, `xargs`, nor `awk` consults it for this workload. Harmless,
just dead env-plumbing. (`PATH` is genuinely required.) Trim if you want a
tighter "minimal env" demonstration.

**Fix (optional):**
```python
base_env = {"PATH": os.environ["PATH"]}
```

### IN-04: Helper's stderr error messages are not prefix-stable for future grep matching

**File:** `scripts/compute_image_hash.sh:10,14,25,29`
**Issue:**
Messages start with `[error]` which matches the convention in `run_docker.sh`
(`[info]`, `[warn]`, `[error]`, `[build]`, `[mcp]`). The
`test_missing_dockerfile_exits_nonzero` test currently asserts only that
`"Dockerfile"` appears anywhere in stderr — robust to wording changes — so
nothing is broken. Informational note for future maintainers: if you ever add
machine-readable error parsing, consider a stable prefix like
`[compute_image_hash] error:` so callers can grep by source.

**Fix:** None required.

### IN-05: Comment-only nit — `LC_ALL=C` placement is documented as "added to sort" in CONTEXT D-02; helper applies it inline rather than at the script level

**File:** `scripts/compute_image_hash.sh:3,35,40`
**Issue:**
The header comment says "extracted from run_docker.sh:212-229 with LC_ALL=C
added (D-02)". `LC_ALL=C` is applied per-pipeline-element on `sort` only, not
exported at the top of the helper. This is the correct minimal scope — `find`
traversal order is filesystem-dependent (not locale-dependent), `sha256sum`
is byte-oriented, `awk '{print $1}'` is column-1 by whitespace so locale
doesn't matter — but a quick reader scanning the script may wonder whether a
top-level `export LC_ALL=C` was forgotten. A one-line clarifying comment near
the `sort` calls (e.g., `# LC_ALL=C: stable byte-order sort across locales`)
would make intent obvious without changing behavior.

**Fix (optional):**
```bash
# LC_ALL=C ensures deterministic byte-order sort independent of host locale.
find "$BUILD_ROOT/docker-bin" -type f -print | LC_ALL=C sort | xargs sha256sum
```

## Notes on items explicitly checked and found clean

- **Prune-then-`-type f -print` ordering** in `find` (line 36-40 of the
  helper) is correct: `-type d \( … \) -prune -o -type f -print` only prunes
  *directories* whose names match, leaving regular files with those names
  (extremely unlikely, but technically possible) safe. This is the intended
  GNU-find idiom.
- **`LC_ALL=C` scope:** correctly applied to `sort`, where locale actually
  matters; not needed on `find`, `sha256sum`, `xargs`, or `awk` for this
  workload.
- **Env-var forwarding from `run_docker.sh:212-218`:** all four documented
  inputs (`INSTALL_BINARY_NINJA`, `BINARY_NINJA_ZIP`, `INSTALL_IDA_PRO`,
  `IDA_PRO_ZIP`) are exported into the helper subshell with `VAR=VAL bash …`
  syntax, and the helper defaults each to a safe value (`0` / empty) when
  unset — matching the D-05 contract and the test's "clean env" invocation.
- **`set -euo pipefail`** is set in both shell scripts; failures in any
  pipeline stage (helper missing, `sha256sum` error, `xargs` failure)
  propagate correctly and abort `run_docker.sh` before `SHORT_SHA` is computed
  from an empty hash.
- **Subprocess hygiene in pytest:** `subprocess.run` uses `timeout=10`,
  `capture_output=True`, `text=True`, explicit `env=`, and asserts
  `returncode == 0` — all good defensive defaults for a hermetic helper test.
- **Fixture isolation:** tests use `tmp_path` and never touch the real
  `mcp-gateway/` tree (D-08), so CI ordering / parallel-xdist runs are safe.
- **Pruned-path test coverage** (SC-3a-d) is implemented via
  `@pytest.mark.parametrize` over `__pycache__`, `.venv`, `*.egg-info`,
  `.pytest_cache` — directly matches the contract.
- **Binja toggle test** uses a stub zip whose content is hashed by
  `sha256sum`, not parsed as a ZIP, so the stub `b"PK\x03\x04stub"` is fine.

---

_Reviewed: 2026-05-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
