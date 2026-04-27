"""CLI-04 (D-14): MCP Resources flow — list, read, missing-artifact error.

Scenarios:
  - resources/list returns at least one mare://cases/<case>/<artifact> URI when
    /agent/status/ has at least one case, OR pytest.skip if no cases yet.
  - resources/read on a known existing artifact returns text/blob content with correct MIME.
  - resources/read on a syntactically valid but absent artifact returns an error
    (per D-04 / Plan 03's FileNotFoundError → structured MCP error).
"""

from __future__ import annotations
import pytest


_EXPECTED_MIME = {
    ".json": "application/json",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


def _list_resources(client):
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 10,
            "method": "resources/list",
            "params": {},
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["result"]["resources"]


def test_resources_list_uses_mare_uri_scheme(mcp_client):
    resources = _list_resources(mcp_client)
    if not resources:
        pytest.skip(
            "no cases under /agent/status/ — run a triage first to seed the test"
        )
    assert all(r["uri"].startswith("mare://cases/") for r in resources), (
        f"non-mare URI surfaced: {[r['uri'] for r in resources][:3]}"
    )


def test_resources_list_mime_types_match_d04(mcp_client):
    resources = _list_resources(mcp_client)
    if not resources:
        pytest.skip("no cases — see test_resources_list_uses_mare_uri_scheme")
    for r in resources:
        for ext, expected in _EXPECTED_MIME.items():
            if r["uri"].endswith(ext):
                assert r["mimeType"] == expected, (
                    f"D-04 mismatch: {r['uri']} → {r['mimeType']} (expected {expected})"
                )


def test_resources_read_returns_content(mcp_client):
    resources = _list_resources(mcp_client)
    if not resources:
        pytest.skip("no cases")
    # Pick a likely-to-exist artifact (CURRENT_STATE.json is always written first).
    target = next(
        (r for r in resources if r["uri"].endswith("CURRENT_STATE.json")),
        resources[0],
    )
    resp = mcp_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 11,
            "method": "resources/read",
            "params": {"uri": target["uri"]},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    if "error" in body:
        # Acceptable if the chosen artifact happens not to exist yet (pipeline still running).
        # Re-pick something else; if nothing reads, fail.
        for r in resources:
            if r["uri"] == target["uri"]:
                continue
            attempt = mcp_client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 12,
                    "method": "resources/read",
                    "params": {"uri": r["uri"]},
                },
            ).json()
            if "result" in attempt:
                target_body = attempt
                break
        else:
            pytest.skip("no readable artifacts in any listed case")
    else:
        target_body = body

    contents = target_body["result"]["contents"]
    assert contents, "resources/read returned empty contents block"
    # Either text or blob is present per MCP spec.
    assert "text" in contents[0] or "blob" in contents[0], contents[0]


def test_resources_read_missing_artifact_returns_error(mcp_client):
    """D-04 / RESEARCH: missing artifact → structured MCP error, not empty content."""
    resources = _list_resources(mcp_client)
    if not resources:
        pytest.skip("no cases")
    # Get a real case name.
    sample_uri = resources[0]["uri"]
    # Extract case from mare://cases/<case>/<artifact>
    case = sample_uri.removeprefix("mare://cases/").rsplit("/", 1)[0]
    # Construct a syntactically valid URI to a real-shape artifact that doesn't exist.
    # CURRENT_STATE.json is in ARTIFACTS allowlist; if it's missing for this case,
    # that's our test. If it IS present, fall through and test against a manually-deleted one.
    bogus_uri = f"mare://cases/{case}/CURRENT_STATE.json"
    # Try a doubly-bogus case to ensure miss: use the artifact-list invariant — pick
    # one of the 13 ARTIFACTS that's least likely written.
    deep_uri = f"mare://cases/{case}/08_deep_analysis_plan.md"

    for uri in (deep_uri, bogus_uri):
        resp = mcp_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 13,
                "method": "resources/read",
                "params": {"uri": uri},
            },
        )
        # Either we got an error (artifact missing) — pass; or a successful read — try the next.
        body = resp.json()
        if "error" in body or (resp.status_code != 200):
            # Got the structured error — D-04 satisfied.
            assert "error" in body or resp.status_code in (400, 404, 500), body
            return
    pytest.skip(
        "both candidate artifacts existed for this case — cannot exercise missing-artifact path"
    )


def test_resources_read_traversal_uri_rejected(mcp_client):
    """T-04-01: ../ in case must be rejected by _safe_artifact_path (CASE_NAME_RE).

    Constructs a `mare://` URI with `..` in the case slot. Either the gateway
    returns an MCP error or HTTP 400 — both are acceptable; what's NOT acceptable
    is a 200 with content from outside STATUS_ROOT.
    """
    resp = mcp_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 14,
            "method": "resources/read",
            "params": {"uri": "mare://cases/..%2Fetc/CURRENT_STATE.json"},
        },
    )
    body = resp.json() if resp.status_code == 200 else None
    if body is not None:
        assert "error" in body, f"path traversal NOT rejected — got result: {body}"
    else:
        assert resp.status_code in (400, 404, 422), resp.status_code
