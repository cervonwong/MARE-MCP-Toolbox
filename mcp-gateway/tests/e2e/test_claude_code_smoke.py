"""CLI-01 (D-12): Raw-MCP smoke test mimicking Claude Code's protocol-level behavior.

Two scenarios:
  (a) Authenticated `initialize` → `tools/list` → `tools/call(mare_list_uploads)` returns 200
      with sane bodies.
  (b) Same `tools/list` request without the bearer header returns 401 (T-04-02 auth bypass).
"""

from __future__ import annotations


def test_initialize_then_tools_list(mcp_client):
    """initialize fixture already ran; verify tools/list returns the curated surface."""
    resp = mcp_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    tools = body["result"]["tools"]
    names = [t["name"] for t in tools]
    assert "list_uploads" in names or "mare_list_uploads" in names, names
    # Phase 2 surface should include get_active_backend (D-07)
    assert any("get_active_backend" in n for n in names), names


def test_tools_call_list_uploads(mcp_client):
    """tools/call returns a structured result (not an error) for a no-arg gateway tool."""
    resp = mcp_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_uploads", "arguments": {}},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "error" not in body, body
    # Result shape: { content: [...], structuredContent: ... } or similar.
    assert "result" in body, body


def test_missing_bearer_returns_401(unauthed_client):
    """T-04-02: requests without Authorization header are rejected by BearerAuthMiddleware."""
    resp = unauthed_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/list",
            "params": {},
        },
    )
    assert resp.status_code == 401, f"expected 401, got {resp.status_code}: {resp.text}"


def test_wrong_bearer_returns_401(gateway_alive):
    """T-04-02: requests with a wrong bearer token are rejected."""
    import httpx

    r = httpx.post(
        f"{gateway_alive}/mcp",
        json={"jsonrpc": "2.0", "id": 100, "method": "tools/list", "params": {}},
        headers={
            "Authorization": "Bearer obviously-wrong-token-aaaa",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        timeout=5.0,
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}"
