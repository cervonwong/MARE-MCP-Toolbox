# Phase 1: IDA Pro Backend - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-14
**Phase:** 01-ida-pro-backend
**Areas discussed:** idalib setup, MCP transport model, Package installation
**Context:** Rediscussion — switching from jtsylve/ida-mcp to mrexodia/ida-pro-mcp

---

## idalib Setup

| Option | Description | Selected |
|--------|-------------|----------|
| Bundled install | Install from IDA's own idalib/python directory + run py-activate-idalib.py | ✓ |
| IDADIR only | Just set IDADIR env var, let ida-pro-mcp find idalib itself | |
| Skip idalib entirely | Don't set up idalib, use a different mode | |

**User's choice:** Bundled install
**Notes:** User explicitly stated: do NOT use idapro from PyPI (old/outdated), do NOT use ida-mcp from PyPI. Install from IDA's own bundled files only.

---

## MCP Transport Model

| Option | Description | Selected |
|--------|-------------|----------|
| SSE on localhost | Run idalib-mcp on localhost, write SSE URL to .mcp.json | ✓ |
| Wrap in stdio | Use mcp-proxy to bridge SSE back to stdio | |
| Direct process | Skip idalib-mcp, write a thin stdio wrapper | |

**User's choice:** SSE on localhost (after clarifying "both" meant stdio-like default now, SSE externally later)
**Notes:** User initially said "both" — clarified as: stdio by default pattern but since ida-pro-mcp only supports SSE, use SSE locally. Future phases will expose the same SSE endpoint externally for remote clients. Agent starts idalib-mcp per-analysis (not at boot).

### Follow-up: Binary path handling

| Option | Description | Selected |
|--------|-------------|----------|
| Start per-analysis | Agent starts idalib-mcp on demand with target binary path | ✓ |
| Start with default | Start at container boot with placeholder | |
| Not sure | Need to research binary loading via MCP tools | |

**User's choice:** Start per-analysis
**Notes:** Agent manages idalib-mcp lifecycle — start with target binary, analyze, stop when done.

---

## Package Installation

| Option | Description | Selected |
|--------|-------------|----------|
| pip from GitHub | pip install from GitHub archive zip (README-recommended) | ✓ |
| pip from PyPI | pip install ida-pro-mcp | |
| uv from GitHub | uv pip install from GitHub | |
| Git clone + pip install | Clone repo, install locally | |

**User's choice:** pip from GitHub
**Notes:** `pip install https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip`

---

## Claude's Discretion

- Python environment isolation strategy
- Multi-stage Docker build details
- idalib-mcp lifecycle management approach
- Port selection strategy

## Deferred Ideas

- Exposing idalib-mcp SSE endpoint externally — Phase 2/3 scope
- README documentation for IDA Pro setup — do after implementation
