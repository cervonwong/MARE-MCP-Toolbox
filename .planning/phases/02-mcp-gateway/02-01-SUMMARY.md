---
phase: 02-mcp-gateway
plan: 01
subsystem: infra
tags: [mcp, auth, scaffold, python, starlette, bearer-token, origin-middleware, backend-detection]

# Dependency graph
requires:
  - phase: 01-ida-pro-backend
    provides: idalib-mcp binary on PATH, /opt/ida-pro installation (referenced by detect_backend IDA branch)
provides:
  - mcp_gateway Python package (editable-installable via pip install -e mcp-gateway/)
  - load_or_generate_token() with env-var-wins fallback, 0600 token file, MCP_GATEWAY_QUIET suppression
  - BearerAuthMiddleware (hmac.compare_digest, /mcp and /upload protected, /healthz open)
  - OriginMiddleware (DNS-rebind protection — localhost/127.0.0.1/null allowed, others 403)
  - detect_backend() IDA > BN > Ghidra priority chain mirroring docker-bin/configure-agent-mcp.sh
  - CLI entry point with default host=127.0.0.1 port=8080
  - Wave 0 test fixtures: bearer_token, tmp_upload_dir, tmp_status_dir, fake_backend_mcp
  - session_state module with PINNED_BACKEND / ACTIVE_CASE placeholders for Plan 03
affects: [02-02, 02-03, 02-04, 02-05]

# Tech tracking
tech-stack:
  added:
    - "mcp>=1.27,<1.28 (tight pin — reliance on _tool_manager stable until migration)"
    - "starlette>=0.37 (ASGI framework + BaseHTTPMiddleware)"
    - "uvicorn>=0.27 (ASGI server; access_log=False for token-leak mitigation)"
    - "python-multipart>=0.0.9 (prep for Plan 04 upload endpoint)"
    - "httpx>=0.27 (prep for Plan 03 backend client)"
    - "anyio>=4.5 (async primitives)"
    - "pytest>=8, pytest-asyncio>=0.23 (dev) — asyncio_mode=auto"
  patterns:
    - "Env-var-wins fallback for secrets (MCP_GATEWAY_TOKEN precedence over generation)"
    - "Starlette BaseHTTPMiddleware for cross-cutting concerns (auth, origin)"
    - "Lazy import inside main() so --help works before building full app"
    - "Constant-time bytes comparison via hmac.compare_digest for auth"
    - "Module-level Path constants monkeypatched in tests (avoids touching real /opt paths)"
    - "TDD RED -> GREEN commits per task"

key-files:
  created:
    - mcp-gateway/pyproject.toml
    - mcp-gateway/README.md
    - mcp-gateway/src/mcp_gateway/__init__.py
    - mcp-gateway/src/mcp_gateway/__main__.py
    - mcp-gateway/src/mcp_gateway/_version.py
    - mcp-gateway/src/mcp_gateway/cli.py
    - mcp-gateway/src/mcp_gateway/auth.py
    - mcp-gateway/src/mcp_gateway/session_state.py
    - mcp-gateway/src/mcp_gateway/backend/__init__.py
    - mcp-gateway/src/mcp_gateway/backend/detect.py
    - mcp-gateway/tests/__init__.py
    - mcp-gateway/tests/conftest.py
    - mcp-gateway/tests/test_auth.py
    - mcp-gateway/tests/test_cli.py
    - mcp-gateway/tests/test_detect.py
    - mcp-gateway/tests/e2e/smoke.sh
    - mcp-gateway/tests/e2e/test_upload_then_analyze.sh
  modified: []

key-decisions:
  - "D-09 fidelity: backend priority is IDA > BN > Ghidra, mirroring configure-agent-mcp.sh (REQUIREMENTS.md GW-03 stale wording noted in detect.py docstring)"
  - "D-16 env-var-wins: MCP_GATEWAY_TOKEN set → verbatim; unset → secrets.token_urlsafe(32)"
  - "D-17 token lifecycle: 0o600 token file via os.open+O_CREAT|O_TRUNC + belt-and-suspenders chmod; MCP_GATEWAY_QUIET=1 suppresses bearer log line; file still written"
  - "D-19 bind default: 127.0.0.1 (localhost-only); 0.0.0.0 is explicit opt-in via MCP_GATEWAY_HOST"
  - "D-20 port default: 8080"
  - "mcp SDK tight-pinned to >=1.27,<1.28 per planner note (stable _tool_manager API surface)"

patterns-established:
  - "Middleware ordering: Starlette add_middleware LIFO — OriginMiddleware (outermost) runs before BearerAuthMiddleware so DNS-rebind 403 precedes 401"
  - "Token file atomic write: os.open with O_CREAT|O_TRUNC|O_WRONLY + mode 0o600 + explicit os.chmod after close (umask-agnostic)"
  - "Test isolation via monkeypatching module-level Path constants rather than touching real filesystem"
  - "FakePath test double for detect_backend (is_dir / exists / iterdir minimal surface)"
  - "Lazy-import pattern inside CLI main() so argparse --help works without full app wiring"

requirements-completed: [GW-04, GW-05]

# Metrics
duration: 5min
completed: 2026-04-23
---

# Phase 02 Plan 01: Package Scaffold and Auth Summary

**Installable `mcp_gateway` Python package with bearer-token auth, Origin DNS-rebind middleware, IDA>BN>Ghidra backend detection, and Wave 0 pytest fixtures — 22 tests green.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-23T06:44:17Z
- **Completed:** 2026-04-23T06:49:33Z
- **Tasks:** 3
- **Files created:** 17
- **Tests added:** 22 (14 auth + 3 cli + 6 detect, pytest-asyncio auto mode)

## Accomplishments

- `mcp-gateway/` package installable via `pip install -e mcp-gateway/` (mcp 1.27.0 pin honored)
- Token lifecycle hardened: env-var-wins, 0600 file mode, `MCP_GATEWAY_QUIET` log suppression, never emitted on `access_log`
- BearerAuthMiddleware protects `/mcp*` and `/upload` with `hmac.compare_digest` constant-time compare; `/healthz` intentionally open
- OriginMiddleware allowlists `http://127.0.0.1*`, `http://localhost*`, `null`, missing Origin; rejects everything else with 403 (DNS-rebind protection per MCP spec 2025-03-26)
- `detect_backend()` implements authoritative IDA > BN > Ghidra priority mirroring `docker-bin/configure-agent-mcp.sh` lines 67-119
- CLI defaults host=127.0.0.1 port=8080; env vars `MCP_GATEWAY_HOST`/`MCP_GATEWAY_PORT` override; `--host`/`--port` flags take precedence
- Wave 0 test scaffolding ready for downstream plans: `bearer_token`, `tmp_upload_dir`, `tmp_status_dir`, `fake_backend_mcp` fixtures plus e2e shell placeholders
- `session_state.PINNED_BACKEND` / `ACTIVE_CASE` placeholders ready for Plan 03 lifespan + Plan 02 case tools

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1: Package scaffold + Wave 0 fixtures + pyproject** — `5538ccd` (feat)
2. **Task 2: Auth module + CLI (tests first)** — `d61cdaa` (test, RED) → `fe02efd` (feat, GREEN)
3. **Task 3: Backend detection (tests first)** — `d3287f7` (test, RED) → `8dab017` (feat, GREEN)

## Files Created/Modified

### Package core
- `mcp-gateway/pyproject.toml` — setuptools build, `mcp>=1.27,<1.28`, `pytest-asyncio` auto mode, `mcp-gateway` entry point
- `mcp-gateway/README.md` — operator quick-reference (env vars, auth header format)
- `mcp-gateway/src/mcp_gateway/__init__.py` — re-exports `__version__`
- `mcp-gateway/src/mcp_gateway/_version.py` — `__version__ = "0.1.0"`
- `mcp-gateway/src/mcp_gateway/__main__.py` — `python -m mcp_gateway` entry
- `mcp-gateway/src/mcp_gateway/cli.py` — argparse + env-var fallback + lazy `build_app` import
- `mcp-gateway/src/mcp_gateway/auth.py` — `load_or_generate_token`, `BearerAuthMiddleware`, `OriginMiddleware`
- `mcp-gateway/src/mcp_gateway/session_state.py` — `PINNED_BACKEND`, `ACTIVE_CASE` module-level placeholders
- `mcp-gateway/src/mcp_gateway/backend/__init__.py` — re-exports `detect_backend`
- `mcp-gateway/src/mcp_gateway/backend/detect.py` — IDA > BN > Ghidra priority with `shutil.which('idalib-mcp')` gate

### Tests
- `mcp-gateway/tests/__init__.py` — package marker
- `mcp-gateway/tests/conftest.py` — shared fixtures (`bearer_token`, `tmp_upload_dir`, `tmp_status_dir`, `fake_backend_mcp`)
- `mcp-gateway/tests/test_auth.py` — 13 tests (token lifecycle, bearer middleware, origin middleware)
- `mcp-gateway/tests/test_cli.py` — 3 tests (defaults, env overrides, flag precedence)
- `mcp-gateway/tests/test_detect.py` — 6 tests (priority chain, shutil.which gate, RuntimeError path)
- `mcp-gateway/tests/e2e/smoke.sh` — placeholder (0755, filled in Plan 05)
- `mcp-gateway/tests/e2e/test_upload_then_analyze.sh` — placeholder (0755, filled in Plan 04/05)

## Decisions Made

- **D-09 / D-16 / D-17 / D-19 / D-20** implemented verbatim per plan's `must_haves.truths` block
- **REQUIREMENTS.md GW-03 discrepancy** surfaced in `detect.py` docstring — the stale text says "BN > IDA > Ghidra" but CONTEXT.md D-09 and the authoritative bash script in `docker-bin/configure-agent-mcp.sh` enforce IDA > BN > Ghidra. Chose fidelity to CONTEXT.md + bash script; future requirement update can reconcile wording.
- **mcp SDK pin `>=1.27,<1.28`** per checker note keeps the gateway's reliance on private `_tool_manager` stable until Plan 02/03 can migrate to a public client API.

## Threat Mitigations

| Threat ID | Mitigation |
|-----------|------------|
| **T-02-AUTH** | `hmac.compare_digest` constant-time compare in `BearerAuthMiddleware.dispatch`; 401 JSON on missing/invalid bearer; `PROTECTED_PREFIXES = ("/mcp", "/upload")`; `/healthz` intentionally open |
| **T-02-NET** | `OriginMiddleware` allowlists `http://127.0.0.1`, `http://localhost`, `"null"`, missing Origin; 403 on everything else (DNS-rebind protection per MCP spec 2025-03-26); CLI defaults `host=127.0.0.1` so exposure requires explicit `MCP_GATEWAY_HOST=0.0.0.0` opt-in |
| **T-02-TOKENLEAK** | Token file written via `os.open(..., O_CREAT\|O_TRUNC\|O_WRONLY, 0o600)` + explicit `os.chmod(0o600)`; `MCP_GATEWAY_QUIET=1` suppresses the `[gateway] Bearer token:` log line; CLI sets `uvicorn.run(access_log=False)` so Authorization header never hits logs |
| **T-02-SUBPROC** / **T-02-PATHTRAVERSAL** / **T-02-UPLOAD** | Transferred to Plans 02/04 per plan's `threat_model` disposition. Not applicable to this plan. |

## Deviations from Plan

None — plan executed exactly as written. All `must_haves.truths` and `acceptance_criteria` satisfied. No Rule 1/2/3 auto-fixes required. No architectural (Rule 4) decisions triggered.

## Issues Encountered

- **Environment bootstrap (non-deviation, non-code):** Worktree had no `pip`/`venv` available (Debian's EXTERNALLY-MANAGED marker). Installed `python3.12-venv` via apt, created `/tmp/gw-venv`, installed `mcp-gateway` editable + `pytest`/`pytest-asyncio`. No project-level impact; tests ran in the isolated venv. Container image bootstrapping in Plan 05 will handle this via the Dockerfile.
- **Worktree base mismatch:** Initial worktree HEAD was at `db82837` (behind target base `a09fae3`). Reset via `git reset --hard a09fae3a747d58cfac52434e90c73e94e0297833` before any work. Noted per plan's worktree_branch_check instruction.

## Handoff to Downstream Plans

Plans 02 / 03 / 04 / 05 can now rely on these imports:

```python
from mcp_gateway.auth import BearerAuthMiddleware, OriginMiddleware, load_or_generate_token
from mcp_gateway.backend.detect import detect_backend
from mcp_gateway.session_state import PINNED_BACKEND, ACTIVE_CASE
from mcp_gateway.cli import build_parser, DEFAULT_HOST, DEFAULT_PORT
```

Open TODOs for downstream plans (not deviations — intentional handoff):
- `mcp_gateway.app.build_app` — stubbed as lazy import in `cli.main`; Plan 02 creates the Starlette assembly.
- `mcp_gateway.backend.client.PinnedBackend` — referenced in `session_state.py` TYPE_CHECKING block; Plan 03 creates the class.
- E2E shell scripts at `tests/e2e/` — executable placeholders; Plan 04 fills `test_upload_then_analyze.sh`, Plan 05 fills `smoke.sh`.

## Next Plan Readiness

- **Plan 02-02 (FastMCP server + tool surface):** Unblocked — can add `app.py` / `build_app()` that wires `BearerAuthMiddleware` and `OriginMiddleware` around a FastMCP-backed Starlette app.
- **Plan 02-03 (backend client routing):** Unblocked — `detect_backend()` return value is the pin input; `session_state.PINNED_BACKEND` is the write target.
- **Plan 02-04 (upload endpoint):** Unblocked — `BearerAuthMiddleware.PROTECTED_PREFIXES` already covers `/upload`; conftest already provides `tmp_upload_dir` fixture.
- **Plan 02-05 (container integration + smoke):** Unblocked — `mcp-gateway` entry point installable, `mcp-gateway --host --port` CLI stable.

## Self-Check: PASSED

- [x] `mcp-gateway/pyproject.toml` exists (mcp>=1.27,<1.28, asyncio_mode=auto, entry point present)
- [x] `mcp-gateway/src/mcp_gateway/auth.py` exists (hmac.compare_digest, secrets.token_urlsafe(32), 0o600)
- [x] `mcp-gateway/src/mcp_gateway/backend/detect.py` exists (IDA_DIR / BN_MCP_SCRIPT / GHIDRA_MCP_SCRIPT / BACKENDS tuple)
- [x] `mcp-gateway/src/mcp_gateway/cli.py` exists (DEFAULT_HOST="127.0.0.1", DEFAULT_PORT=8080)
- [x] `mcp-gateway/tests/conftest.py` exports `bearer_token`/`tmp_upload_dir`/`tmp_status_dir`/`fake_backend_mcp`
- [x] `mcp-gateway/tests/e2e/smoke.sh` executable (0755)
- [x] `mcp-gateway/tests/e2e/test_upload_then_analyze.sh` executable (0755)
- [x] Commit `5538ccd` exists (Task 1 scaffold)
- [x] Commit `d61cdaa` exists (Task 2 RED)
- [x] Commit `fe02efd` exists (Task 2 GREEN)
- [x] Commit `d3287f7` exists (Task 3 RED)
- [x] Commit `8dab017` exists (Task 3 GREEN)
- [x] `pytest mcp-gateway/tests/ -v` → 22 passed, 0 failed
- [x] `python -m mcp_gateway --help` exits 0

---
*Phase: 02-mcp-gateway*
*Completed: 2026-04-23*
