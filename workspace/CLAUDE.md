# MARE Analysis Agent

You are a malware analysis agent running inside a Kali Linux container with 50+ RE tools.

## Skills

Your analysis skills are auto-discovered from `.claude/skills/`. Load the
`malware-analysis-orchestrator` skill for structured multi-phase analysis.

## Workspace Layout

- Samples: drop files directly into this directory (the workspace root)
- `examples/`: bundled example malware samples
- `mcp/`: MCP backend repos (auto-cloned at container start, gitignored)
- `status/`: per-sample case directories (created during analysis, gitignored)

## MCP Backends

The disassembler MCP backend (Binary Ninja or Ghidra) is configured automatically
at container start via `.mcp.json`.
