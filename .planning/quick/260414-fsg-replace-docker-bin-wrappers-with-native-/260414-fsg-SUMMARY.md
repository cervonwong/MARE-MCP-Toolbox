---
phase: quick-260414-fsg
plan: 01
subsystem: docker-config
tags: [docker, claude-code, codex, config, wrapper-removal]
dependency_graph:
  requires: []
  provides: [native-agent-config]
  affects: [Dockerfile, configure-agent-mcp.sh]
tech_stack:
  added: []
  patterns: [project-level-config-files, user-level-permission-merge]
key_files:
  created:
    - workspace/.claude/settings.json
  modified:
    - workspace/.codex/config.toml
    - docker-bin/configure-agent-mcp.sh
    - Dockerfile
  deleted:
    - docker-bin/claude
    - docker-bin/codex
decisions:
  - Used approval_policy=full-auto and sandbox_mode=none in codex config.toml (equivalent to --dangerously-bypass-approvals-and-sandbox)
  - Extended configure-agent-mcp.sh Python block to merge skipDangerousModePermissionPrompt and permissions.defaultMode at user level
  - Removed baked-in trustedDirectories from Dockerfile since configure-agent-mcp.sh handles it at runtime
metrics:
  duration: 86s
  completed: 2026-04-14
  tasks_completed: 3
  tasks_total: 3
  files_changed: 6
---

# Quick Task 260414-fsg: Replace docker-bin wrappers with native config files

Native project-level config files for Claude Code (settings.json) and Codex (config.toml) replace fragile wrapper scripts that intercepted CLI arguments; configure-agent-mcp.sh now merges user-level permission bypass settings at container boot.

## Completed Tasks

| # | Task | Commit | Key Changes |
|---|------|--------|-------------|
| 1 | Create native config files and extend configure-agent-mcp.sh | 6f2a9cc | Created workspace/.claude/settings.json, added approval_policy/sandbox_mode to config.toml, extended Python merge block |
| 2 | Delete wrappers and simplify Dockerfile | 3b3c981 | Deleted docker-bin/claude and docker-bin/codex, removed claude-real rename trick, removed codex wrapper install, removed baked-in settings.json |
| 3 | Verify run_docker.sh | n/a | Confirmed no wrapper references exist, no changes needed |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing cleanup] Removed baked-in trustedDirectories from Dockerfile**
- **Found during:** Task 2
- **Issue:** Dockerfile line 104 wrote a hardcoded `trustedDirectories` JSON into `~/.claude/settings.json` at build time, but `configure-agent-mcp.sh` already handles this at runtime. Leaving it would be redundant and could mask runtime merge issues.
- **Fix:** Removed the `printf ... settings.json` line from the Dockerfile RUN block while keeping the `mkdir -p .claude` directory creation.
- **Files modified:** Dockerfile
- **Commit:** 3b3c981

## What Changed

### workspace/.claude/settings.json (new)
Project-level Claude Code config setting model=opus, effortLevel=high, permissions.defaultMode=bypassPermissions.

### workspace/.codex/config.toml (modified)
Added `approval_policy = "full-auto"` and `sandbox_mode = "none"` before the existing model settings. These replace the `--dangerously-bypass-approvals-and-sandbox` flag from the deleted wrapper.

### docker-bin/configure-agent-mcp.sh (modified)
Extended the embedded Python block to merge `skipDangerousModePermissionPrompt: true` and `permissions.defaultMode: "bypassPermissions"` into the user-level `~/.claude/settings.json`. These settings cannot be set at project level for security reasons.

### Dockerfile (modified)
- Removed codex wrapper install line (`install -m 0755 /opt/docker-bin/codex`)
- Simplified Claude install: no longer renames `claude` to `claude-real`, no longer installs wrapper script, just symlinks the real binary
- Removed baked-in `trustedDirectories` write (handled at runtime by configure-agent-mcp.sh)

### docker-bin/claude, docker-bin/codex (deleted)
78-line and 85-line wrapper scripts that parsed CLI arguments and injected defaults. No longer needed.

## Self-Check: PASSED
