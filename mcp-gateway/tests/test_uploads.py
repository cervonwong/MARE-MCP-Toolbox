"""Tests for POST /upload — streaming, size cap, sha256 dedupe, filename validation.

Maps to VALIDATION.md rows:
  - GW-06 test_upload_roundtrip
  - GW-06 test_upload_over_cap
  - GW-06 test_upload_dedupe
Plus auth regression (T-02-AUTH on /upload).
"""
from __future__ import annotations
import hashlib
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
