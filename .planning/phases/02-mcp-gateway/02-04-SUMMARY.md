---
phase: 02-mcp-gateway
plan: 04
subsystem: gateway
tags: [mcp, upload, python, starlette, streaming, sha256]

# Dependency graph
requires:
  - phase: 02-mcp-gateway
    plan: 01
    provides: BearerAuthMiddleware, OriginMiddleware (protect /upload)
  - phase: 02-mcp-gateway
    plan: 02
    provides: build_app() factory with /upload placeholder route + UPLOADS_ROOT + resolve_sample
  - phase: 02-mcp-gateway
    plan: 03
    provides: lifespan + PinnedBackend wiring (regression protection)
provides:
  - POST /upload streaming handler with sha256 content addressing
  - MCP_GATEWAY_MAX_UPLOAD_MB env override (default 1 GB per D-14)
  - MCP_GATEWAY_UPLOAD_DIR env override (default /agent/uploads)
  - Content-hashed dedup layout `<UPLOAD_DIR>/<sha256>/<filename>` (D-13)
  - sample_id usable by resolve_sample() and any subsequent tool call (D-15)
affects: [02-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Streaming upload: `async for chunk in request.stream()` with running sha256 + byte tally; never calls `request.body()` or `request.form()` (T-02-UPLOAD)"
    - "tempfile.NamedTemporaryFile(dir=UPLOAD_DIR, prefix='.incoming-', delete=False) so the final shutil.move is same-FS (atomic rename) and cleanup on error is local"
    - "Content-Length fast-fail: if the declared header exceeds max_bytes, return 413 before reading any body"
    - "Dedup first-write-wins: when target `<UPLOAD_DIR>/<sha256>/<filename>` already exists, drop the new tempfile instead of overwriting"
    - "Filename sanitization: reject `/`, `\\`, `..`, leading `.`, and ASCII control chars at the header boundary (T-02-PATHTRAVERSAL)"
    - "Multipart rejection: content-type starting with `multipart/` returns 415 with explanatory message (raw-body contract in Phase 2)"
    - "Test monkeypatch pattern: override MCP_GATEWAY_UPLOAD_DIR env + patch samples.UPLOADS_ROOT + samples.ALLOWED_PREFIXES so resolve_sample round-trips through tmp_path"

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/uploads.py
    - mcp-gateway/tests/test_uploads.py
    - .planning/phases/02-mcp-gateway/02-04-SUMMARY.md
  modified:
    - mcp-gateway/src/mcp_gateway/app.py

key-decisions:
  - "Env-vars read at call time (not import time) so tests can monkeypatch MCP_GATEWAY_MAX_UPLOAD_MB and MCP_GATEWAY_UPLOAD_DIR per-request"
  - "Empty body (total==0) returns 400 with `empty upload` message — refuses to hash/store the empty string as a legitimate sample"
  - "Tempfile placed INSIDE UPLOAD_DIR (not /tmp) so the final dedup rename is always on the same filesystem (POSIX rename is atomic only within one FS)"
  - "Dedup first-write-wins over replacement: if target file already exists with same sha256 hex dir + same filename, we drop the new tempfile and return 200 with the existing path — the existing file is never overwritten"
  - "Filename sanitizer also rejects backslash and ASCII control bytes in addition to the plan's minimum set (defense in depth against Windows-path traversal and NUL smuggling)"

requirements-completed: [GW-06]

# Metrics
duration: ~6min
completed: 2026-04-23
---

# Phase 02 Plan 04: Upload Endpoint Summary

**POST `/upload` streams raw request bodies to a sha256-keyed directory under `<UPLOAD_DIR>`, enforcing a 1 GB cap (env-overridable), rejecting path-traversal filenames, multipart content-types, and oversized Content-Length headers — 14 new tests (10 unit + 4 integration) green within a 95-test mcp-gateway suite.**

## Performance

- **Duration:** ~6 min
- **Completed:** 2026-04-23
- **Tasks:** 2 (both TDD RED -> GREEN cycles)
- **Files created:** 2 (uploads.py + test_uploads.py)
- **Files modified:** 1 (app.py — placeholder removed, route swapped)
- **Tests added this plan:** 14 new (10 unit in Task 1 + 4 integration in Task 2)
- **Full suite:** 95 passing (was 81 after Plan 03; +14 from Plan 04)
- **Commits:** 4 (`2f813a7`, `6f3efac`, `97903c6`, `ba82e25`)

## Accomplishments

### POST /upload Request/Response Contract

**Request:**

```http
POST /upload HTTP/1.1
Host: 127.0.0.1:8080
Authorization: Bearer <MCP_GATEWAY_TOKEN>
X-Filename: suspect.exe               # optional; defaults to "sample.bin"
Content-Type: application/octet-stream # optional; `multipart/*` is 415
Content-Length: 524288                 # optional; >MAX_BYTES fast-fails 413

<raw binary body>
```

**Success (200):**

```json
{
  "sample_id": "<sha256-hex>",
  "path": "/agent/uploads/<sha256-hex>/suspect.exe",
  "size": 524288
}
```

**Errors:**

| Code | Cause | Body |
|---|---|---|
| 401 | No/bad `Authorization: Bearer` header | BearerAuthMiddleware (Plan 01) |
| 403 | Evil `Origin` header (DNS rebind) | OriginMiddleware (Plan 01) |
| 400 | `X-Filename` contains `/`, `\`, `..`, leading `.`, or control chars | `{"error": "invalid filename"}` |
| 400 | Body is empty (total == 0) | `{"error": "empty upload"}` |
| 413 | `Content-Length` declares > MAX_BYTES | `{"error": "upload exceeds <N> bytes (content-length declared)"}` |
| 413 | Streamed body exceeds MAX_BYTES during upload | `{"error": "upload exceeds <N> bytes"}` |
| 415 | `Content-Type: multipart/*` | `{"error": "multipart not supported in Phase 2 ..."}` |

### Size-Cap Enforcement (T-02-UPLOAD / D-14)

Two independent paths:

1. **Content-Length fast-fail** — before reading any body, if the header declares a length over the cap, return 413 immediately. Protects against client-cooperating large uploads without wasting network bandwidth.
2. **Streaming tally** — inside `async for chunk in request.stream()`, each chunk's length is added to a running `total`. On the first chunk that pushes `total > MAX_BYTES`, the handler closes and unlinks the tempfile then returns 413. Protects against clients that lie in (or omit) the Content-Length header.

Default cap: `1024 * 1024 * 1024` bytes = **1 GB** (D-14). Env override `MCP_GATEWAY_MAX_UPLOAD_MB=N` substitutes `N * 1024 * 1024`. Setting `MCP_GATEWAY_MAX_UPLOAD_MB=0` effectively disables all uploads (test `test_upload_over_cap` uses this to trigger 413 on a one-byte body).

### Filename Sanitization (T-02-PATHTRAVERSAL)

`_is_invalid_filename(name)` rejects when any of:

- empty string
- contains `/` or `\` (directory separator, POSIX or Windows)
- contains `..` (traversal)
- starts with `.` (hidden file)
- contains any ASCII byte < 0x20 (NUL, newlines, control chars)

Tested rejections: `"../etc/passwd"`, `"a/b.bin"`, `".."`, `".hidden"`, `"a\\b.bin"`. All 400.

Because the final storage path is `<UPLOAD_DIR>/<sha256-hex>/<filename>`, the filename only ever becomes a leaf component — even if sanitization missed something, the sha256 hex directory boundary prevents escape outside `<UPLOAD_DIR>/<hex>/`. The filename is a human-readable hint, not a trust-bearing path element.

### Dedup Semantics (D-13)

- Two uploads with **identical bytes** produce the same sha256, hence the same `<UPLOAD_DIR>/<sha256>/` directory.
- When the target file `<UPLOAD_DIR>/<sha256>/<filename>` already exists: the newly-streamed tempfile is `unlink()`ed and the handler returns 200 with the **existing** file's path. First write wins — the original file is never overwritten (preserves file mtime for any downstream caching).
- Two uploads of identical bytes but **different X-Filename** headers will create two filename leaves under the same sha256 dir. The dedup logic intentionally keys on `(sha256, filename)` tuple, not sha256 alone, so renaming a duplicate is allowed.
- Test `test_upload_dedupe` posts the same bytes + filename twice and asserts exactly one file under exactly one sha256 dir.

### resolve_sample Round-Trip (D-15)

Uploaded files are immediately accessible by sha256 via Plan 02's `resolve_sample`:

```python
r = client.post("/upload", content=body, headers={"Authorization": f"Bearer {tok}", "X-Filename": "demo.bin"})
sample_id = r.json()["sample_id"]      # "<sha256-hex>"
path = resolve_sample(sample_id)       # absolute path to /agent/uploads/<hex>/demo.bin
```

Test `test_upload_roundtrip` verifies both the filesystem contents and the round-trip equivalence:
`Path(r.json()["path"]).resolve() == Path(resolve_sample(expected_sha))`.

### Wiring into build_app (Task 2)

**Before (Plan 02):**

```python
async def _upload_placeholder(request):
    return JSONResponse({"error": "upload handler not yet installed", "plan": "Plan 04"}, status_code=501)

routes=[Route("/upload", _upload_placeholder, methods=["POST"])]
```

**After (Plan 04):**

```python
from .uploads import upload_handler
routes=[Route("/upload", upload_handler, methods=["POST"])]
```

`_upload_placeholder` and its 501 stub message are fully removed (`grep _upload_placeholder src/mcp_gateway/app.py == 0`). Middleware chain unchanged: `OriginMiddleware` (outer, T-02-NET) -> `BearerAuthMiddleware` (inner, T-02-AUTH) -> route.

## Test Counts

| Test module | Count | Focus |
|---|---|---|
| `test_uploads.py` — unit (Task 1) | 10 | auth regression, roundtrip, dedupe, two cap paths, multipart, empty body, default filename, traversal, streaming-source smoke |
| `test_uploads.py` — integration (Task 2) | 4 | full-app happy path, unauth on full app, placeholder gone, evil Origin on /upload |
| **Plan 02-04 new total** | **14** | |
| Carryover (Plans 01/02/03) | 81 | all still green |
| **Full mcp-gateway suite** | **95** | 1.14s runtime |

## Deviations from Plan

None — plan executed exactly as written.

All grep acceptance patterns matched:

- `grep -c 'async for chunk in request.stream()' uploads.py` = 2
- `grep -c 'await request.body()' uploads.py` = 0
- `grep -c 'await request.form()' uploads.py` = 0
- `grep -c 'hashlib.sha256' uploads.py` = 1
- `grep -c 'tempfile.NamedTemporaryFile' uploads.py` = 1
- `grep -c 'status_code=413' uploads.py` = 2
- `grep -c 'status_code=415' uploads.py` = 1
- `grep -c 'MCP_GATEWAY_MAX_UPLOAD_MB' uploads.py` = 2
- `grep -c '0o644' uploads.py` = 1
- `grep -c '_is_invalid_filename' uploads.py` = 2
- `grep -c 'from .uploads import upload_handler' app.py` = 1
- `grep -c 'Route("/upload", upload_handler' app.py` = 1
- `grep -c '_upload_placeholder' app.py` = 0
- `grep -c 'plan": "Plan 04"' app.py` = 0

## Threat Mitigations Applied

| Threat ID | Mitigation | Evidence |
|---|---|---|
| T-02-UPLOAD (DoS memory) | Stream via `request.stream()`; enforce streaming tally | `test_upload_streams_not_buffers` greps source; `test_upload_over_cap` forces cap=0 and verifies no `.incoming-*` leftover |
| T-02-UPLOAD (DoS disk) | Content-Length fast-fail + streaming tally + tempfile cleanup on any exception | `test_upload_over_cap_via_content_length_fast_fail` |
| T-02-PATHTRAVERSAL | `_is_invalid_filename` rejects `/`, `\`, `..`, leading `.`, control chars | `test_upload_rejects_path_traversal_filename` over 5 patterns |
| T-02-AUTH (/upload) | BearerAuthMiddleware applied to whole app in Plan 01 is inherited by the new route | `test_upload_requires_bearer` + `test_upload_through_full_app_unauth` |
| T-02-NET (/upload) | OriginMiddleware outermost — evil Origin 403 precedes Bearer 401 | `test_upload_evil_origin_rejected` (full-app) |
| T-02-DISKEXHAUSTION | try/except unlinks tempfile on client disconnect or OSError | `test_upload_over_cap` checks no `.incoming-*` left behind |
| T-02-MULTIPART | 415 with explicit message; raw body only in Phase 2 (documented) | `test_upload_rejects_multipart` |

No new threat surface beyond what the plan's `<threat_model>` describes. No additional threat flags required.

## Handoffs

### To Plan 05 (smoke test + docker entrypoint)

- `/upload` is **live**, not a stub. The smoke test from Plan 05 should exercise it end-to-end against a running container:

  ```bash
  curl -sS -X POST "http://$HOST:$PORT/upload" \
    -H "Authorization: Bearer $TOKEN" \
    -H "X-Filename: smoke.bin" \
    --data-binary @/path/to/tiny-sample.bin \
    | jq -r .sample_id
  ```

  The returned sha256 can then be passed as the `sample` argument to any MCP tool call (e.g., `init_case`, `collect_strings`).

- Env knobs the smoke/container setup needs to be aware of:
  - `MCP_GATEWAY_UPLOAD_DIR` (default `/agent/uploads`) — the container mount point should cover this path; directory is auto-created with default mode by `uploads.py`.
  - `MCP_GATEWAY_MAX_UPLOAD_MB` (default `1024` = 1 GB per D-14) — override in docker-compose for tighter limits on shared deployments.

- The 501 placeholder is gone — any downstream code paths that check `response.status_code == 501` on `/upload` must be updated. Plan 02's SUMMARY.md listed this as a stub; it is now resolved.

### Round-trip continuity for tools

The sample stored at `<UPLOAD_DIR>/<sha256>/<filename>` is immediately resolvable by `resolve_sample(sample_id)` from Plan 02's `tools/samples.py`. No migration or index-rebuild step is needed — the filesystem layout IS the index, and directory iteration in `resolve_sample` picks the first non-hidden file under the sha256 dir (deterministic-sorted).

## Known Stubs

None introduced this plan. Plan 02's listed `/upload` stub is now resolved.

Plan 02's other stubs (PINNED_BACKEND disasm stub — wired in Plan 03; `run_deep_analysis` v2 stub) are unaffected by this plan.

## Verification Summary

- [x] `pytest mcp-gateway/tests/ --no-header -q` -> 95 passed in 1.14s
- [x] `pytest mcp-gateway/tests/test_uploads.py -q` -> 14 passed in 0.23s
- [x] `ruff check mcp-gateway/src/mcp_gateway/uploads.py mcp-gateway/src/mcp_gateway/app.py` -> All checks passed!
- [x] `grep -rn 'await request.body()' mcp-gateway/src/` -> no hits (T-02-UPLOAD)
- [x] `grep -rn 'await request.form()' mcp-gateway/src/` -> no hits (T-02-UPLOAD)
- [x] `grep -c '_upload_placeholder' mcp-gateway/src/mcp_gateway/app.py` == 0 (placeholder removed)
- [x] GW-06 met: POST /upload writes `<UPLOAD_DIR>/<sha256>/<filename>`, returns sample_id, uploaded file resolvable via `resolve_sample`
- [x] All plan must_haves truths validated by corresponding tests
- [x] No regression in Plan 01/02/03 suites (all 81 prior tests still green)

## Self-Check: PASSED

Verified artifacts exist and commits are recorded:

- FOUND: mcp-gateway/src/mcp_gateway/uploads.py
- FOUND: mcp-gateway/tests/test_uploads.py
- FOUND: mcp-gateway/src/mcp_gateway/app.py (modified)
- FOUND: 2f813a7 (test RED Task 1)
- FOUND: 6f3efac (feat GREEN Task 1)
- FOUND: 97903c6 (test RED Task 2)
- FOUND: ba82e25 (feat GREEN Task 2)
