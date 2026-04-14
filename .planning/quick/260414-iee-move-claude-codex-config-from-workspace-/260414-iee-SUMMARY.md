# Quick Task 260414-iee: Summary

## What Changed

1. **`docker-bin/configure-agent-mcp.sh`** — Added `data["model"] = "opus"` and `data["effortLevel"] = "high"` to the Python block that writes user-level `~/.claude/settings.json` at container boot
2. **`workspace/.codex/config.toml`** — Fixed values: `approval_policy = "never"` (was `"full-auto"`), `sandbox_mode = "danger-full-access"` (was `"none"`)
3. **`workspace/.claude/settings.json`** — Deleted (settings now written at user level by configure-agent-mcp.sh)

## Commits

- `2944cb0` — Merge Claude model settings into entrypoint script and fix Codex config values
- `a89af30` — Remove project-level Claude settings.json (now set at user level)

## Result

All Claude Code settings (`model`, `effortLevel`, `permissions.defaultMode`, `skipDangerousModePermissionPrompt`, `trustedDirectories`) are now written to user-level `~/.claude/settings.json` by `configure-agent-mcp.sh` at container start. No project-level Claude settings file needed. Codex config template remains in `workspace/.codex/config.toml` with corrected values, copied to user-level by the same script.
