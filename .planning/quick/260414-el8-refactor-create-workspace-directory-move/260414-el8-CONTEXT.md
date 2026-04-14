# Quick Task 260414-el8: Workspace refactor - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Task Boundary

Create a `workspace/` directory that becomes the sole mount at `/agent` in the container. Move skills from `agent_helpers/` into native `.claude/skills/` and `.codex/skills/` inside workspace. Update Docker mount config, configure-agent-mcp.sh, and README.md.

</domain>

<decisions>
## Implementation Decisions

### Sample directory
- Users drop samples directly into `workspace/` root — no dedicated subfolder
- `examples/` stays as-is inside workspace (moved from repo root)

### Codex config
- Move `codex-config.toml` into `workspace/.codex/config.toml` — version-controlled alongside skills
- Remove `docker-config/` directory and runtime seeding from `configure-agent-mcp.sh`

### Workspace CLAUDE.md
- Create a minimal `workspace/CLAUDE.md` with analysis-agent instructions (e.g. load skills)
- Separate from the dev-level `CLAUDE.md` at repo root

### agent_helpers/ cleanup
- Delete `agent_helpers/` entirely after moving contents — clean break

### Claude's Discretion
- `.gitignore` entries for `workspace/mcp/`, `workspace/status/`, `workspace/.mcp.json` (runtime-generated)
- Internal paths in SKILL.md scripts use relative paths — should mostly work without changes
- The prompt example in README simplifies (no long skill path — Claude auto-discovers from `.claude/skills/`)

</decisions>

<specifics>
## Specific Ideas

- Codex `agents/openai.yaml` moves to `workspace/.codex/agents/`
- The entrypoint `configure-agent-mcp.sh` still writes `.mcp.json` to `/agent/` — no change needed since `/agent` is now `workspace/`
- `run_docker.sh` changes `HOST_PWD` to always use `$SCRIPT_DIR/workspace` instead of `$(pwd -P)`

</specifics>
