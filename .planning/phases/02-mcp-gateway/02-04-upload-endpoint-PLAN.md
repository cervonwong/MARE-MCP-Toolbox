---
phase: 02-mcp-gateway
plan: 04
type: execute
wave: 3
depends_on:
  - 02-01
  - 02-02
files_modified:
  - mcp-gateway/src/mcp_gateway/uploads.py
  - mcp-gateway/src/mcp_gateway/app.py
  - mcp-gateway/tests/test_uploads.py
autonomous: true
requirements:
  - GW-06
tags:
  - mcp
  - upload
  - python

must_haves:
  truths:
    - "POST /upload with raw body + X-Filename header creates `<UPLOAD_DIR>/<sha256>/<filename>`"
    - "POST /upload returns `{sample_id: <sha256>, path: <abs>, size: <bytes>}`"
    - "POST /upload without Authorization → 401 (BearerAuthMiddleware from Plan 01)"
    - "POST /upload with body > MCP_GATEWAY_MAX_UPLOAD_MB → 413 (streamed, no memory OOM)"
    - "Duplicate upload (same sha256) reuses existing directory — original file not overwritten"
    - "Filename containing `/` or `..` → 400 (T-02-PATHTRAVERSAL)"
    - "Upload handler streams via `async for chunk in request.stream()` — never calls `request.body()`"
    - "Uploaded file is mode 0644; directory mode default"
    - "Uploaded file can subsequently be resolved via `resolve_sample(<sha256>)` from Plan 02"
    - "Default MAX_BYTES = 1024*1024*1024 (1 GB per D-14); env override `MCP_GATEWAY_MAX_UPLOAD_MB=50` → 50 MB cap"
    - "Multipart Content-Type returns 415 in Phase 2 (planner's discretion: raw body only, multipart deferred)"
  artifacts:
    - path: "mcp-gateway/src/mcp_gateway/uploads.py"
      provides: "upload_handler async Starlette route; streaming body + sha256 + content-hashed target"
      exports: ["upload_handler", "MAX_BYTES", "UPLOAD_DIR"]
    - path: "mcp-gateway/tests/test_uploads.py"
      provides: "Integration tests for roundtrip, cap, dedupe, filename validation, auth"
  key_links:
    - from: "mcp-gateway/src/mcp_gateway/uploads.py::upload_handler"
      to: "request.stream()"
      via: "async chunk iteration — never buffers full body"
      pattern: "async for chunk in request\\.stream"
    - from: "mcp-gateway/src/mcp_gateway/uploads.py::upload_handler"
      to: "hashlib.sha256"
      via: "streaming hash computed as bytes arrive"
      pattern: "sha256\\(\\).*update\\(chunk\\)"
    - from: "mcp-gateway/src/mcp_gateway/app.py"
      to: "uploads.upload_handler"
      via: "Starlette Route replaces the _upload_placeholder"
      pattern: 'Route\("/upload", upload_handler'
---

<objective>
Replace the Plan 02 `_upload_placeholder` with a real streaming upload handler that accepts a binary sample, computes sha256 on-the-fly, enforces the 1 GB default cap, and stores the file at `<UPLOAD_DIR>/<sha256>/<original_filename>` (content-hashed dedup layout per D-13). The handler is wired into `app.py`'s Starlette route table and sits behind `BearerAuthMiddleware` + `OriginMiddleware`.

Purpose: Fulfills GW-06 (remote clients can submit samples). The resulting sample can be referenced by sha256 in any subsequent tool call (D-15, works with `resolve_sample` from Plan 02).

Output: POST `/upload` with `Authorization: Bearer <token>` + `X-Filename: foo.bin` + `--data-binary @file` returns `{sample_id, path, size}` and writes to disk; round-trips via `resolve_sample`; enforces size cap (413), auth (401), filename sanitization (400); dedupes by content hash.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/02-mcp-gateway/02-CONTEXT.md
@.planning/phases/02-mcp-gateway/02-RESEARCH.md
@.planning/phases/02-mcp-gateway/02-VALIDATION.md
@.planning/phases/02-mcp-gateway/02-01-package-scaffold-and-auth-PLAN.md
@.planning/phases/02-mcp-gateway/02-02-fastmcp-server-and-tool-surface-PLAN.md

<interfaces>
<!-- From Plan 01 -->
```python
from mcp_gateway.auth import BearerAuthMiddleware  # already on the app — /upload is already protected
```

<!-- From Plan 02 -->
```python
from mcp_gateway.tools.samples import UPLOADS_ROOT, resolve_sample
# UPLOADS_ROOT is Path(os.environ.get("MCP_GATEWAY_UPLOAD_DIR", "/agent/uploads"))
```

<!-- RESEARCH Pattern 4 (verbatim skeleton) -->
```python
async def upload_handler(request: Request) -> JSONResponse:
    filename = request.headers.get("x-filename", "sample.bin")
    if "/" in filename or ".." in filename:
        return JSONResponse({"error": "invalid filename"}, status_code=400)
    total = 0
    sha = hashlib.sha256()
    with tempfile.NamedTemporaryFile(dir=UPLOAD_DIR, delete=False, prefix=".incoming-", suffix=".bin") as tmp:
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_BYTES:
                tmp.close(); os.unlink(tmp.name)
                return JSONResponse({"error": f"upload exceeds {MAX_BYTES} bytes"}, status_code=413)
            sha.update(chunk); tmp.write(chunk)
        tmp_path = tmp.name
    digest = sha.hexdigest()
    target_dir = os.path.join(UPLOAD_DIR, digest)
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, filename)
    if os.path.exists(target):
        os.unlink(tmp_path)  # dedupe
    else:
        shutil.move(tmp_path, target)
    os.chmod(target, 0o644)
    return JSONResponse({"sample_id": digest, "path": target, "size": total})
```

<!-- Client usage -->
```bash
curl -X POST http://127.0.0.1:8080/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Filename: suspect.exe" \
  --data-binary @suspect.exe
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: uploads.py — streaming handler with size cap + sha256 + filename sanitization</name>
  <files>
    mcp-gateway/src/mcp_gateway/uploads.py,
    mcp-gateway/tests/test_uploads.py
  </files>
  <read_first>
    - .planning/phases/02-mcp-gateway/02-RESEARCH.md (§ Pattern 4 Streaming upload; § Pitfall 6 OOM; § Security Domain — upload threats)
    - .planning/phases/02-mcp-gateway/02-CONTEXT.md (D-11 POST /upload; D-13 <UPLOAD_DIR>/<sha256>/<name>; D-14 1 GB default cap; D-15 sha256 as sample id)
    - mcp-gateway/src/mcp_gateway/tools/samples.py (from Plan 02 — UPLOADS_ROOT, resolve_sample: new uploads must be resolvable by sha256)
  </read_first>
  <behavior>
    - Default `MAX_BYTES` = 1024*1024*1024 (1 GB); reads `MCP_GATEWAY_MAX_UPLOAD_MB` env var at call time and multiplies by 1024*1024
    - Default `UPLOAD_DIR` = `/agent/uploads`; reads `MCP_GATEWAY_UPLOAD_DIR` env var at call time
    - Missing X-Filename header → uses `sample.bin` (documented default)
    - X-Filename containing `/` → 400 `{"error": "invalid filename"}`
    - X-Filename containing `..` → 400
    - X-Filename starting with `.` → 400 (hidden files)
    - Multipart Content-Type (starts with `multipart/`) → 415 `{"error": "multipart not supported in Phase 2 — use raw body with X-Filename"}`
    - Content-Length header claiming > MAX_BYTES → 413 immediately (before streaming)
    - Streamed body > MAX_BYTES → 413 during streaming (accumulated tally); incomplete tempfile unlinked
    - Successful upload: writes to `<UPLOAD_DIR>/<sha256-hex>/<filename>` (sha256 computed from actual bytes received)
    - Successful upload response: `{"sample_id": "<hex>", "path": "<abs>", "size": <bytes>}` with HTTP 200
    - Duplicate upload (same content): sha256 matches existing dir → new temp file unlinked → response still 200 with existing path
    - Uploaded file mode is 0644; directory exists at end of handler
    - `resolve_sample(sample_id)` (Plan 02) returns the uploaded file path
    - Uses `async for chunk in request.stream()` — never `await request.body()` or `request.form()` (T-02-UPLOAD memory safety)
  </behavior>
  <action>
Create `mcp-gateway/src/mcp_gateway/uploads.py`:

```python
"""POST /upload: streaming file upload with sha256-based content addressing.

D-11: separate POST endpoint on the same port as MCP.
D-13: samples stored at `<UPLOAD_DIR>/<sha256>/<original_name>` (dedup by hash).
D-14: default 1 GB cap, overridable via MCP_GATEWAY_MAX_UPLOAD_MB.
D-15: returned sample_id is usable by tools/resolve_sample.

Threat mitigations:
  T-02-UPLOAD       — stream via request.stream(), enforce cap during streaming, 413 on overflow.
  T-02-PATHTRAVERSAL — reject filenames containing '/', '..', or starting with '.'.
  T-02-TOKENLEAK    — (not applicable here; auth is upstream)
"""
from __future__ import annotations
import hashlib
import logging
import os
import shutil
import tempfile
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger("mcp_gateway.uploads")

DEFAULT_UPLOAD_DIR = "/agent/uploads"
DEFAULT_MAX_UPLOAD_MB = 1024  # 1 GB
DEFAULT_FILENAME = "sample.bin"


def _upload_dir() -> Path:
    return Path(os.environ.get("MCP_GATEWAY_UPLOAD_DIR", DEFAULT_UPLOAD_DIR))


def _max_bytes() -> int:
    mb = int(os.environ.get("MCP_GATEWAY_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB)))
    return mb * 1024 * 1024


# Re-exported at module level for test visibility — tests check `uploads.MAX_BYTES` etc.
# These are callables in code; expose the evaluated defaults for introspection too.
MAX_BYTES = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
UPLOAD_DIR = Path(DEFAULT_UPLOAD_DIR)


def _is_invalid_filename(name: str) -> bool:
    if not name:
        return True
    if "/" in name or "\\" in name:
        return True
    if ".." in name:
        return True
    if name.startswith("."):
        return True
    # Control characters / NUL
    if any(ord(c) < 32 for c in name):
        return True
    return False


async def upload_handler(request: Request) -> JSONResponse:
    """Handle POST /upload: stream body to disk, hash, dedupe by sha256, return sample_id.

    MUST use `async for chunk in request.stream()` — never `request.body()` (OOM on 1 GB).
    """
    # Reject multipart in Phase 2 (raw body + X-Filename only).
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/"):
        return JSONResponse(
            {"error": "multipart not supported in Phase 2 — use raw body with X-Filename"},
            status_code=415,
        )

    filename = request.headers.get("x-filename", DEFAULT_FILENAME)
    if _is_invalid_filename(filename):
        return JSONResponse({"error": "invalid filename"}, status_code=400)

    max_bytes = _max_bytes()

    # Fast-fail on Content-Length > max (client cooperating). Streaming check still applies.
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > max_bytes:
                return JSONResponse(
                    {"error": f"upload exceeds {max_bytes} bytes (content-length declared)"},
                    status_code=413,
                )
        except ValueError:
            pass  # malformed header; continue and rely on streaming cap

    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    sha = hashlib.sha256()

    # Stream to a temporary file INSIDE upload_dir so the final atomic move is on the same FS.
    tmp = tempfile.NamedTemporaryFile(
        dir=str(upload_dir), delete=False, prefix=".incoming-", suffix=".bin"
    )
    try:
        try:
            async for chunk in request.stream():
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    tmp.close()
                    try:
                        os.unlink(tmp.name)
                    except FileNotFoundError:
                        pass
                    return JSONResponse(
                        {"error": f"upload exceeds {max_bytes} bytes"},
                        status_code=413,
                    )
                sha.update(chunk)
                tmp.write(chunk)
        finally:
            tmp.close()
    except Exception:
        # Best-effort cleanup on any streaming exception (client disconnect, etc.)
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass
        raise

    if total == 0:
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass
        return JSONResponse({"error": "empty upload"}, status_code=400)

    digest = sha.hexdigest()
    target_dir = upload_dir / digest
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename

    if target.exists():
        # Dedupe: content-hashed path already exists. Drop tmp.
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass
        log.info("[upload] dedupe hit sha256=%s filename=%s size=%d", digest, filename, total)
    else:
        shutil.move(tmp.name, str(target))
        os.chmod(target, 0o644)
        log.info("[upload] stored sha256=%s filename=%s size=%d", digest, filename, total)

    return JSONResponse(
        {"sample_id": digest, "path": str(target), "size": total},
        status_code=200,
    )
```

Create `mcp-gateway/tests/test_uploads.py`:

```python
"""Tests for POST /upload — streaming, size cap, sha256 dedupe, filename validation.

Maps to VALIDATION.md rows:
  - GW-06 test_upload_roundtrip
  - GW-06 test_upload_over_cap
  - GW-06 test_upload_dedupe
Plus auth regression (T-02-AUTH on /upload).
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from mcp_gateway.auth import BearerAuthMiddleware
from mcp_gateway.uploads import upload_handler


@pytest.fixture
def tmp_uploads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setenv("MCP_GATEWAY_UPLOAD_DIR", str(upload_dir))
    # Also align the Plan 02 samples module so resolve_sample() round-trip works.
    from mcp_gateway.tools import samples as samples_mod
    monkeypatch.setattr(samples_mod, "UPLOADS_ROOT", upload_dir)
    monkeypatch.setattr(
        samples_mod,
        "ALLOWED_PREFIXES",
        (upload_dir, samples_mod.EXAMPLES_ROOT, samples_mod.STATUS_ROOT),
    )
    return upload_dir


def _build_upload_app(token: str) -> Starlette:
    app = Starlette(routes=[Route("/upload", upload_handler, methods=["POST"])])
    app.add_middleware(BearerAuthMiddleware, token=token)
    return app


def test_upload_requires_bearer(tmp_uploads):
    with TestClient(_build_upload_app("tok")) as c:
        r = c.post("/upload", content=b"hello")
        assert r.status_code == 401


def test_upload_roundtrip(tmp_uploads):
    body = b"hello world binary data\x00\xff"
    expected_sha = hashlib.sha256(body).hexdigest()
    with TestClient(_build_upload_app("tok")) as c:
        r = c.post(
            "/upload",
            content=body,
            headers={
                "Authorization": "Bearer tok",
                "X-Filename": "demo.bin",
                "Content-Type": "application/octet-stream",
            },
        )
        assert r.status_code == 200, r.text
        body_json = r.json()
        assert body_json["sample_id"] == expected_sha
        assert body_json["size"] == len(body)
        # File exists at the advertised path with correct content.
        path = Path(body_json["path"])
        assert path.exists()
        assert path.read_bytes() == body
        # Can be resolved by sha256 via Plan 02's resolve_sample.
        from mcp_gateway.tools.samples import resolve_sample
        assert resolve_sample(expected_sha) == str(path.resolve())


def test_upload_dedupe(tmp_uploads):
    body = b"dedup me"
    with TestClient(_build_upload_app("tok")) as c:
        r1 = c.post(
            "/upload",
            content=body,
            headers={"Authorization": "Bearer tok", "X-Filename": "a.bin"},
        )
        r2 = c.post(
            "/upload",
            content=body,
            headers={"Authorization": "Bearer tok", "X-Filename": "a.bin"},
        )
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["sample_id"] == r2.json()["sample_id"]
        # Upload dir should contain exactly one sha256 dir for this content.
        sha_dirs = [p for p in tmp_uploads.iterdir() if p.is_dir() and len(p.name) == 64]
        assert len(sha_dirs) == 1
        files_in_dir = [p for p in sha_dirs[0].iterdir() if p.is_file()]
        assert len(files_in_dir) == 1  # dedupe: no duplicate filename


def test_upload_over_cap(tmp_uploads, monkeypatch):
    monkeypatch.setenv("MCP_GATEWAY_MAX_UPLOAD_MB", "0")  # cap = 0 MB = 0 bytes
    with TestClient(_build_upload_app("tok")) as c:
        r = c.post(
            "/upload",
            content=b"even one byte is too many",
            headers={"Authorization": "Bearer tok", "X-Filename": "x.bin"},
        )
        assert r.status_code == 413
        assert "exceeds" in r.text
        # No leftover .incoming-* tempfile.
        leftovers = list(tmp_uploads.glob(".incoming-*"))
        assert leftovers == [], f"stale tempfiles: {leftovers}"


def test_upload_over_cap_via_content_length_fast_fail(tmp_uploads, monkeypatch):
    monkeypatch.setenv("MCP_GATEWAY_MAX_UPLOAD_MB", "1")  # 1 MB
    huge = 2 * 1024 * 1024  # 2 MB declared
    with TestClient(_build_upload_app("tok")) as c:
        r = c.post(
            "/upload",
            content=b"x" * huge,
            headers={
                "Authorization": "Bearer tok",
                "X-Filename": "big.bin",
                "Content-Length": str(huge),
            },
        )
        assert r.status_code == 413


def test_upload_rejects_path_traversal_filename(tmp_uploads):
    with TestClient(_build_upload_app("tok")) as c:
        for bad in ["../etc/passwd", "a/b.bin", "..", ".hidden", "a\\b.bin"]:
            r = c.post(
                "/upload",
                content=b"x",
                headers={"Authorization": "Bearer tok", "X-Filename": bad},
            )
            assert r.status_code == 400, f"filename {bad!r} should be rejected"


def test_upload_rejects_multipart(tmp_uploads):
    with TestClient(_build_upload_app("tok")) as c:
        r = c.post(
            "/upload",
            content=b"--boundary\r\nContent-Disposition: form-data; name=\"f\"\r\n\r\nx\r\n--boundary--",
            headers={
                "Authorization": "Bearer tok",
                "X-Filename": "ok.bin",
                "Content-Type": "multipart/form-data; boundary=boundary",
            },
        )
        assert r.status_code == 415
        assert "multipart" in r.text


def test_upload_empty_body_rejected(tmp_uploads):
    with TestClient(_build_upload_app("tok")) as c:
        r = c.post(
            "/upload",
            content=b"",
            headers={"Authorization": "Bearer tok", "X-Filename": "x.bin"},
        )
        assert r.status_code == 400
        assert "empty" in r.text


def test_upload_default_filename(tmp_uploads):
    with TestClient(_build_upload_app("tok")) as c:
        r = c.post(
            "/upload",
            content=b"hello",
            headers={"Authorization": "Bearer tok"},
        )
        assert r.status_code == 200
        path = Path(r.json()["path"])
        assert path.name == "sample.bin"


def test_upload_streams_not_buffers(tmp_uploads, monkeypatch):
    """Smoke test: verify upload_handler source uses request.stream(), not body()."""
    import inspect
    from mcp_gateway import uploads as uploads_mod
    src = inspect.getsource(uploads_mod.upload_handler)
    assert "request.stream()" in src, "T-02-UPLOAD: must use streaming"
    assert "await request.body()" not in src, "T-02-UPLOAD: must NOT call request.body()"
    assert "await request.form()" not in src, "T-02-UPLOAD: must NOT call request.form()"
```
  </action>
  <verify>
    <automated>pytest mcp-gateway/tests/test_uploads.py -x --no-header -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest mcp-gateway/tests/test_uploads.py -x --no-header -q` exits 0 (10 tests)
    - `grep -q 'async for chunk in request.stream()' mcp-gateway/src/mcp_gateway/uploads.py`
    - `grep -c 'await request.body()' mcp-gateway/src/mcp_gateway/uploads.py` == 0 (T-02-UPLOAD)
    - `grep -c 'await request.form()' mcp-gateway/src/mcp_gateway/uploads.py` == 0 (T-02-UPLOAD)
    - `grep -q 'hashlib.sha256' mcp-gateway/src/mcp_gateway/uploads.py`
    - `grep -q 'tempfile.NamedTemporaryFile' mcp-gateway/src/mcp_gateway/uploads.py`
    - `grep -q 'status_code=413' mcp-gateway/src/mcp_gateway/uploads.py` (cap enforcement)
    - `grep -q 'status_code=415' mcp-gateway/src/mcp_gateway/uploads.py` (multipart rejection)
    - `grep -q 'MCP_GATEWAY_MAX_UPLOAD_MB' mcp-gateway/src/mcp_gateway/uploads.py`
    - `grep -q '0o644' mcp-gateway/src/mcp_gateway/uploads.py`
    - `grep -q '_is_invalid_filename' mcp-gateway/src/mcp_gateway/uploads.py`
  </acceptance_criteria>
  <done>Streaming upload handler complete with size cap, sha256 dedupe, filename sanitization, multipart rejection; 10 tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire upload_handler into app.py (replace placeholder) + integration test via full app</name>
  <files>
    mcp-gateway/src/mcp_gateway/app.py,
    mcp-gateway/tests/test_uploads.py
  </files>
  <read_first>
    - mcp-gateway/src/mcp_gateway/app.py (Plan 02/03 version — contains _upload_placeholder returning 501)
    - mcp-gateway/src/mcp_gateway/uploads.py (Task 1 of this plan)
    - mcp-gateway/tests/test_uploads.py (Task 1 — append the integration test here)
  </read_first>
  <behavior>
    - `build_app()` mounts `upload_handler` on POST `/upload` (replacing `_upload_placeholder`)
    - Integration test: POST `/upload` against full app (with auth middleware, Origin middleware, all 21 tools, lifespan) returns 200 with sample_id when sent with valid bearer; /upload still returns 401 without bearer
    - `_upload_placeholder` stub is removed (or kept as private helper only if referenced elsewhere — audit)
    - No regression in tool_list / server_init / routing tests
  </behavior>
  <action>
**Step 1 — Edit `mcp-gateway/src/mcp_gateway/app.py`:**

Find the current import section near the top and add:
```python
from .uploads import upload_handler
```

Find the `_upload_placeholder` function and DELETE it (it is superseded by `upload_handler`).

Find the `routes=[...]` list inside `build_app()` and replace the `Route("/upload", _upload_placeholder, methods=["POST"])` line with:
```python
Route("/upload", upload_handler, methods=["POST"]),
```

No other changes to `app.py` are required. The middleware chain (OriginMiddleware + BearerAuthMiddleware) continues to protect `/upload`.

**Step 2 — Append an integration test to `mcp-gateway/tests/test_uploads.py`:**

```python
# ---------- Full-app integration: /upload behind build_app() ----------

@pytest.fixture
def full_app(monkeypatch, tmp_path, tmp_uploads):
    monkeypatch.setenv("MCP_GATEWAY_TOKEN", "integration-token")
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_FILE", str(tmp_path / "tok"))
    monkeypatch.setenv("MCP_GATEWAY_SKIP_BACKEND", "1")
    import mcp_gateway.app as app_mod
    app_mod._MCP_INSTANCE = None
    return app_mod.build_app()


def test_upload_through_full_app_happy_path(full_app, tmp_uploads):
    body = b"integration-test-sample-bytes"
    expected = hashlib.sha256(body).hexdigest()
    with TestClient(full_app) as c:
        r = c.post(
            "/upload",
            content=body,
            headers={
                "Authorization": "Bearer integration-token",
                "X-Filename": "integration.bin",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["sample_id"] == expected


def test_upload_through_full_app_unauth(full_app):
    with TestClient(full_app) as c:
        r = c.post("/upload", content=b"x", headers={"X-Filename": "x.bin"})
        assert r.status_code == 401


def test_upload_through_full_app_placeholder_gone(full_app):
    """The 501 placeholder must no longer fire for POST /upload with valid bearer."""
    with TestClient(full_app) as c:
        r = c.post(
            "/upload",
            content=b"xx",
            headers={"Authorization": "Bearer integration-token", "X-Filename": "p.bin"},
        )
        # Must NOT be 501 (the old placeholder). 200 on success.
        assert r.status_code != 501


def test_upload_evil_origin_rejected(full_app):
    """OriginMiddleware must still block malicious Origin even on /upload."""
    with TestClient(full_app) as c:
        r = c.post(
            "/upload",
            content=b"x",
            headers={
                "Authorization": "Bearer integration-token",
                "X-Filename": "x.bin",
                "Origin": "http://evil.com",
            },
        )
        assert r.status_code == 403
```
  </action>
  <verify>
    <automated>pytest mcp-gateway/tests/ -x --no-header -q</automated>
  </verify>
  <acceptance_criteria>
    - `pytest mcp-gateway/tests/ -x --no-header -q` exits 0 (full suite including Plan 01/02/03 regression)
    - `grep -q 'from .uploads import upload_handler' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -q 'Route("/upload", upload_handler' mcp-gateway/src/mcp_gateway/app.py`
    - `grep -c '_upload_placeholder' mcp-gateway/src/mcp_gateway/app.py` == 0 (placeholder removed)
    - `grep -c 'plan": "Plan 04"' mcp-gateway/src/mcp_gateway/app.py` == 0 (stub message gone)
    - 4 new integration tests added and green (`test_upload_through_full_app_*`)
    - Full test count increased by Plan 04's additions (10 unit + 4 integration = 14 new)
  </acceptance_criteria>
  <done>upload_handler wired into app.py; placeholder removed; Origin + Bearer middleware still protect /upload; no regression in Plan 01/02/03 tests.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| remote client → POST /upload | Untrusted body and `X-Filename` header |
| upload handler → filesystem `/agent/uploads/` | Trusted target; content-hashed layout prevents overwrites between different content |
| sha256 of uploaded bytes | Cryptographic content identifier; used for dedup AND for later tool invocation (D-15) |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-02-UPLOAD | DoS (disk + memory) | `upload_handler` | HIGH | mitigate | Task 1: stream via `async for chunk in request.stream()`, enforce `MAX_BYTES` tally during streaming → 413. Source greps verify NO `request.body()` / `request.form()` calls. Content-Length header also fast-fails over cap. Default 1 GB (D-14), env-overridable. |
| T-02-PATHTRAVERSAL | Tampering / EoP | `X-Filename` header | HIGH | mitigate | Task 1: `_is_invalid_filename` rejects `/`, `\`, `..`, leading `.`, and control chars → 400. Content-hashed directory layout `<UPLOAD_DIR>/<sha256>/<name>` means filename is a hint, not a path component that can escape. |
| T-02-AUTH | Spoofing / EoP | `/upload` route | HIGH | mitigate | Task 2: `upload_handler` mounted inside app that has BearerAuthMiddleware (Plan 01). Test `test_upload_requires_bearer` and `test_upload_through_full_app_unauth` verify 401 without bearer. |
| T-02-NET | Spoofing (DNS rebind) | `/upload` route | MEDIUM | mitigate | Task 2: OriginMiddleware is applied before Bearer — evil Origin → 403 even on /upload. Test `test_upload_evil_origin_rejected`. |
| T-02-TOKENLEAK | Info Disclosure | — | — | — | Plan 01 handles |
| T-02-SUBPROC | Tampering | — | — | — | Not applicable (upload handler does not shell out) |
| T-02-DISKEXHAUSTION | DoS | tempfile leftover on crash | MEDIUM | mitigate | Task 1: `try/except` around streaming unlinks the tempfile on any exception (client disconnect, OSError). Test `test_upload_over_cap` verifies no `.incoming-*` leftovers. |
| T-02-MULTIPART | Ambiguous input | multipart/form-data content type | LOW | accept | Phase 2 planner's discretion: only raw body accepted. Multipart content-type → 415. Documented in response body. |
</threat_model>

<verification>
After all 2 tasks:
1. Full test suite: `pytest mcp-gateway/tests/ -x --no-header -q` — exits 0 (~60+ tests across Plan 01/02/03/04)
2. `ruff check mcp-gateway/src/mcp_gateway/uploads.py` clean
3. Security greps:
   - `grep -rn 'await request.body()' mcp-gateway/src/` → no hits
   - `grep -rn 'await request.form()' mcp-gateway/src/` → no hits
   - `grep -c '_upload_placeholder' mcp-gateway/src/mcp_gateway/app.py` == 0
4. Round-trip: upload a file then `resolve_sample(sample_id)` returns the path (test_upload_roundtrip)
5. Cap enforcement on both paths: Content-Length fast-fail + streaming tally
</verification>

<success_criteria>
- GW-06 met: POST /upload creates `<UPLOAD_DIR>/<sha256>/<filename>`, returns sample_id, and uploaded sample is resolvable by sha256 through `resolve_sample`
- T-02-UPLOAD mitigated: streamed upload, cap enforced during streaming, no full-body buffering
- T-02-PATHTRAVERSAL mitigated: filename sanitized; bad filenames rejected with 400
- T-02-AUTH enforced: `/upload` requires bearer (via BearerAuthMiddleware from Plan 01)
- T-02-NET enforced: OriginMiddleware blocks evil Origin on /upload
- Dedup: same content → same sha256 dir, no duplicate files
- All decisions honored: D-11 (POST /upload), D-12 (same bearer), D-13 (content-hashed layout), D-14 (1 GB default), D-15 (sample_id usable by tools)
- No regression: Plans 01/02/03 tests all still green
</success_criteria>

<output>
After completion, create `.planning/phases/02-mcp-gateway/02-04-SUMMARY.md`.
Include:
- Request/response contract for POST /upload
- Size-cap enforcement path (Content-Length fast-fail + streaming tally + 413)
- Filename sanitization rules and rejected patterns
- Dedup semantics (content-hashed directory, first-write wins)
- Test counts: test_uploads.py total (10 unit + 4 integration = 14)
- Threat mitigations: T-02-UPLOAD, T-02-PATHTRAVERSAL, T-02-AUTH, T-02-NET, T-02-DISKEXHAUSTION, T-02-MULTIPART
- Handoff to Plan 05: /upload is live; smoke test should exercise it against the real container
</output>
