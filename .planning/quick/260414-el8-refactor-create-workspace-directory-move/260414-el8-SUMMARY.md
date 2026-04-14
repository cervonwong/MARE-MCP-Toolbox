---
phase: quick-260414-el8
plan: 01
subsystem: repository-structure
tags: [refactor, workspace, docker, layout]
dependency_graph:
  requires: []
  provides: [workspace-directory, workspace-mount-point]
  affects: [run_docker.sh, compose.yaml, Dockerfile, configure-agent-mcp.sh, README.md]
tech_stack:
  added: []
  patterns: [workspace-isolation]
key_files:
  created:
    - workspace/CLAUDE.md
    - workspace/.gitignore
  modified:
    - run_docker.sh
    - Dockerfile
    - docker-bin/configure-agent-mcp.sh
    - .gitignore
    - README.md
    - workspace/examples/README.md
  moved:
    - agent_helpers/claude/skills/ -> workspace/.claude/skills/
    - agent_helpers/codex/skills/ -> workspace/.codex/skills/
    - agent_helpers/codex/skills/.../agents/openai.yaml -> workspace/.codex/agents/openai.yaml
    - docker-config/codex-config.toml -> workspace/.codex/config.toml
    - examples/ -> workspace/examples/
decisions:
  - Keep CODEX_USER_DIR volume mount in compose.yaml for auth persistence; codex config now comes from workspace mount
metrics:
  duration: 314s
  completed: 2026-04-14
  tasks: 3
  files: 73
---

# Quick Task 260414-el8: Create workspace/ directory and move agent files

Created workspace/ as the sole container mount point, isolating the analysis agent from dev infrastructure (Dockerfile, .planning/, .git/).

## One-liner

Restructured repo to mount workspace/ at /agent -- moved skills into native .claude/skills/ and .codex/skills/, relocated codex config and examples, updated all Docker tooling and docs.

## What Changed

### Task 1: Create workspace/ structure, move skills, config, and examples (2f17ef8)
- Moved Claude skills from `agent_helpers/claude/skills/` to `workspace/.claude/skills/`
- Moved Codex skills from `agent_helpers/codex/skills/` to `workspace/.codex/skills/`
- Moved `openai.yaml` from skill subdirectory to `workspace/.codex/agents/`
- Moved `docker-config/codex-config.toml` to `workspace/.codex/config.toml`
- Moved `examples/` to `workspace/examples/`
- Created `workspace/CLAUDE.md` with analysis-agent instructions
- Created `workspace/.gitignore` for runtime artifacts (mcp/, .mcp.json, status/, examples/samples/)
- Removed runtime artifact entries from root `.gitignore` (now in workspace/.gitignore)
- Deleted empty `agent_helpers/` and `docker-config/` directories

### Task 2: Update Docker tooling (e6eec6b)
- `run_docker.sh`: Changed HOST_PWD from `$(pwd -P)` to `$SCRIPT_DIR/workspace`
- `run_docker.sh`: Removed `docker-config` from build input checksum find command
- `Dockerfile`: Removed `COPY docker-config/ /opt/docker-config/` line
- `Dockerfile`: Removed codex config seeding from install step (config now comes via workspace mount)
- `docker-bin/configure-agent-mcp.sh`: Changed CODEX_BASE_CONFIG_TEMPLATE from `/opt/docker-config/codex-config.toml` to `/agent/.codex/config.toml`

### Task 3: Update README.md (5a7ac16)
- Updated Quick Start to explain workspace/ mount instead of current directory mount
- Updated MCP clone path to `workspace/mcp/`
- Simplified prompt example (removed explicit skill path; Claude auto-discovers from .claude/skills/)
- Updated skill links to workspace/.claude/ and workspace/.codex/ paths
- Updated volume mount docs to show `workspace/` instead of `.`
- Replaced Repository Layout with new workspace/ structure
- Removed agent_helpers/ and docker-config/ from layout tree

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stale agent_helpers path in workspace/examples/README.md (dfa6cdb)**
- **Found during:** Final verification
- **Issue:** The examples README.md prompt example still referenced `/agent/agent_helpers/claude/skills/malware-analysis-orchestrator/`
- **Fix:** Simplified the prompt to remove the explicit skill path (matching main README change)
- **Files modified:** workspace/examples/README.md

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 2f17ef8 | Create workspace/ directory and move skills, config, and examples |
| 2 | e6eec6b | Update Docker tooling to use workspace/ as mount point |
| 3 | 5a7ac16 | Update README with new workspace/ layout and simplified prompt |
| fix | dfa6cdb | Remove stale skill path from examples README prompt |

## Self-Check: PASSED

All 8 workspace files verified present. Both deleted directories confirmed gone. All 4 commits verified in git log.
