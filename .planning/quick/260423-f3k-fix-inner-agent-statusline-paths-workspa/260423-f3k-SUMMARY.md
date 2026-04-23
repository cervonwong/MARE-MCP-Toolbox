---
phase: 260423-f3k
plan: 01
subsystem: workspace-config
tags: [quick-fix, statusline, container-paths, claude-config]
dependency_graph:
  requires: []
  provides:
    - "Working Claude statusline for agent running inside the container"
  affects:
    - workspace/.claude/settings.json
    - workspace/.claude/statusline.sh
tech_stack:
  added: []
  patterns:
    - "Align hardcoded paths with actual container mount point (/agent)"
key_files:
  created: []
  modified:
    - workspace/.claude/settings.json
    - workspace/.claude/statusline.sh
decisions:
  - "Use /agent (the real in-container mount) in place of the nonexistent /workspace"
metrics:
  duration: "<5 min"
  completed_date: "2026-04-23"
  tasks_completed: 2
  commits: 2
requirements:
  - QUICK-FIX-STATUSLINE-PATHS
---

# Phase 260423-f3k Plan 01: Fix Inner-Agent Statusline Paths Summary

One-liner: Realigned the in-container Claude statusline's hardcoded paths from the nonexistent `/workspace` to the actual bind-mount path `/agent`, restoring statusline rendering for Claude agents running inside the MARE container.

## Context

Commit 9593607 introduced a statusline for Claude running inside the MARE container but hardcoded `/workspace/...` paths. `run_docker.sh` sets `HOST_PWD="$SCRIPT_DIR/workspace"` and `compose.yaml` mounts that at `/agent` with `working_dir: /agent`. Consequently, the `bash /workspace/.claude/statusline.sh` command in `settings.json` pointed at a nonexistent path inside the container, and even if reached, the script's `/workspace/status` and `/workspace/.mcp.json` checks plus the short-path substitution would not match. The fix replaces `/workspace` with `/agent` across both files.

## Tasks Completed

| # | Name                                                   | Commit  | Files                               |
| - | ------------------------------------------------------ | ------- | ----------------------------------- |
| 1 | Fix statusline command path in settings.json           | 50a1ecb | workspace/.claude/settings.json     |
| 2 | Replace /workspace with /agent in statusline.sh        | bdae5ea | workspace/.claude/statusline.sh     |

## Changes

### workspace/.claude/settings.json

- `statusLine.command`: `bash /workspace/.claude/statusline.sh` → `bash /agent/.claude/statusline.sh`

### workspace/.claude/statusline.sh

- `if [ -d /workspace/status ]` → `if [ -d /agent/status ]`
- `ls -1t /workspace/status` → `ls -1t /agent/status`
- `if [ -f /workspace/.mcp.json ]` → `if [ -f /agent/.mcp.json ]`
- Three `grep -q ... /workspace/.mcp.json` calls → `/agent/.mcp.json`
- `short_path="${short_path/#\/workspace/🔬}"` → `short_path="${short_path/#\/agent/🔬}"`
- Comment `# Short path: replace /workspace with 🔬` updated to match (`/agent`)
- `/home/agent` substitution left untouched (intentional per plan)

## Verification

Plan's overall verification commands, all run after both tasks completed:

1. `python3 -c "import json; json.load(open('workspace/.claude/settings.json'))"` → valid JSON
2. `bash -n workspace/.claude/statusline.sh` → syntax OK
3. `grep -rn "/workspace" workspace/.claude/` → zero matches (no stale paths)

Task-level automated verifications from the plan both reported `OK`:

- Task 1: JSON parse + `statusLine.command == 'bash /agent/.claude/statusline.sh'`
- Task 2: `bash -n` + absence of `/workspace` + presence of `/agent/status`, `/agent/.mcp.json`, and the `/agent → 🔬` short-path substitution

## Success Criteria

- [x] `workspace/.claude/settings.json` points `statusLine.command` at `/agent/.claude/statusline.sh` and remains valid JSON.
- [x] `workspace/.claude/statusline.sh` has zero `/workspace` occurrences, passes `bash -n`, and uses `/agent` for the status dir check, `.mcp.json` check, and the short-path substitution.
- [x] No other files, logic, or behavior changed.

## Deviations from Plan

None - plan executed exactly as written. The comment on line 63 of `statusline.sh` (`# Short path: replace /workspace with 🔬`) was updated alongside the code so the comment continues to describe the code it sits above; this is a no-op documentation alignment and not a behavior change.

## Follow-up Verification (Manual)

Per the plan's "Manual" note: the next container session started via `./run_docker.sh` should render the statusline for Claude running inside the container. This cannot be automated within quick-mode constraints.

## Self-Check: PASSED

- FOUND: workspace/.claude/settings.json
- FOUND: workspace/.claude/statusline.sh
- FOUND commit: 50a1ecb (Task 1)
- FOUND commit: bdae5ea (Task 2)
