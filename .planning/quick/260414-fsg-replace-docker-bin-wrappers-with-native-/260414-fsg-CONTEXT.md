# Quick Task 260414-fsg: Replace docker-bin wrappers with native config files for Claude and Codex - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Task Boundary

Replace the docker-bin/claude and docker-bin/codex wrapper scripts with native config files that achieve the same defaults (model, effort, permissions). Remove the wrapper installation plumbing from the Dockerfile.

</domain>

<decisions>
## Implementation Decisions

### Config file placement
- Config files go in `workspace/.claude/settings.json` and `workspace/.codex/config.toml`
- These are repo-tracked, project-level configs mounted at `/agent/` inside the container
- Claude Code detects `.claude/settings.json` in the working directory as project-level config
- Codex detects `.codex/config.toml` in the working directory as project-level config
- `configure-agent-mcp.sh` already copies `workspace/.codex/config.toml` to `~/.codex/config.toml` and appends MCP server blocks — this existing flow handles Codex config

### Wrapper removal scope
- Delete `docker-bin/claude` and `docker-bin/codex` wrapper scripts
- Keep `docker-bin/configure-agent-mcp.sh` (entrypoint setup script, not a wrapper)
- Remove Dockerfile lines that: install wrappers, rename claude to claude-real, symlink wrapper
- Claude Code should be installed normally without the rename trick

### Permission prompt handling
- Claude's `skipDangerousModePermissionPrompt` only works at user-level (`~/.claude/settings.json`), not project-level
- Seed this into `~/.claude-docker/settings.json` via `run_docker.sh` (matching existing auth-seeding pattern)
- Or handle via `configure-agent-mcp.sh` which already writes to the user-level settings.json

</decisions>

<specifics>
## Specific Ideas

- The existing `configure-agent-mcp.sh` already merges `trustedDirectories` into user-level `~/.claude/settings.json` — could extend it to also merge `permissions.defaultMode` and `skipDangerousModePermissionPrompt`
- Codex config template path is already wired: `CODEX_BASE_CONFIG_TEMPLATE=/agent/.codex/config.toml` (line 9 of configure-agent-mcp.sh)
- Claude project-level settings: `model`, `effortLevel`, `permissions.defaultMode: "bypassPermissions"` all work
- Claude user-level only: `skipDangerousModePermissionPrompt: true`

</specifics>
