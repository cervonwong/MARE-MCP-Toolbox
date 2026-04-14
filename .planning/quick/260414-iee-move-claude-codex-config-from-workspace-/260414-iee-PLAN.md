---
phase: quick-260414-iee
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - docker-bin/configure-agent-mcp.sh
  - workspace/.codex/config.toml
  - workspace/.claude/settings.json
autonomous: true
must_haves:
  truths:
    - "Claude model and effortLevel are set at user level via configure-agent-mcp.sh"
    - "workspace/.claude/settings.json no longer exists (skills dir preserved)"
    - "Codex config template uses correct field values for approval_policy and sandbox_mode"
  artifacts:
    - path: "docker-bin/configure-agent-mcp.sh"
      provides: "Writes model and effortLevel to ~/.claude/settings.json"
      contains: "model.*opus"
    - path: "workspace/.codex/config.toml"
      provides: "Corrected Codex config template"
      contains: "danger-full-access"
  key_links:
    - from: "docker-bin/configure-agent-mcp.sh"
      to: "~/.claude/settings.json (inside container)"
      via: "Python block writes JSON at container start"
      pattern: "model.*effortLevel"
---

<objective>
Move Claude model/effortLevel settings from project-level (workspace/.claude/settings.json) to user-level (written by configure-agent-mcp.sh at container start), and fix incorrect Codex config values in the template.

Purpose: User-level settings are the correct location for agent defaults. Project-level settings.json duplicates what the script already handles. Codex template has wrong field values that won't work.
Output: Updated script, fixed Codex template, deleted project-level settings.json.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@docker-bin/configure-agent-mcp.sh
@workspace/.codex/config.toml
@workspace/.claude/settings.json
</context>

<tasks>

<task type="auto">
  <name>Task 1: Merge Claude settings into configure-agent-mcp.sh and fix Codex template</name>
  <files>docker-bin/configure-agent-mcp.sh, workspace/.codex/config.toml</files>
  <action>
1. In `docker-bin/configure-agent-mcp.sh`, find the Python block (lines 18-41) that writes `~/.claude/settings.json`. After the line `data["permissions"] = permissions` (line 38), add two lines:
   - `data["model"] = "opus"`
   - `data["effortLevel"] = "high"`
   These values come from the project-level settings.json being removed.

2. In `workspace/.codex/config.toml`, fix two incorrect values:
   - Change `approval_policy = "full-auto"` to `approval_policy = "never"` (correct Codex CLI value)
   - Change `sandbox_mode = "none"` to `sandbox_mode = "danger-full-access"` (correct Codex CLI value)
  </action>
  <verify>
    <automated>grep -q '"model"' docker-bin/configure-agent-mcp.sh && grep -q '"effortLevel"' docker-bin/configure-agent-mcp.sh && grep -q 'approval_policy = "never"' workspace/.codex/config.toml && grep -q 'sandbox_mode = "danger-full-access"' workspace/.codex/config.toml && echo "PASS" || echo "FAIL"</automated>
  </verify>
  <done>configure-agent-mcp.sh writes model and effortLevel to user-level Claude settings. Codex template has correct approval_policy and sandbox_mode values.</done>
</task>

<task type="auto">
  <name>Task 2: Delete workspace/.claude/settings.json</name>
  <files>workspace/.claude/settings.json</files>
  <action>
Delete `workspace/.claude/settings.json`. The `.claude/` directory MUST remain because it contains `skills/`. Only the `settings.json` file is removed.

Verify the `.claude/` directory still exists with its `skills/` subdirectory after deletion.
  </action>
  <verify>
    <automated>test ! -f workspace/.claude/settings.json && test -d workspace/.claude/skills && echo "PASS" || echo "FAIL"</automated>
  </verify>
  <done>workspace/.claude/settings.json is deleted. workspace/.claude/ directory and its skills/ subdirectory are preserved.</done>
</task>

</tasks>

<verification>
- `grep -A2 'model' docker-bin/configure-agent-mcp.sh` shows model and effortLevel being set
- `workspace/.claude/settings.json` does not exist
- `workspace/.claude/skills/` directory still exists
- `workspace/.codex/config.toml` shows `approval_policy = "never"` and `sandbox_mode = "danger-full-access"`
</verification>

<success_criteria>
- Claude model ("opus") and effortLevel ("high") are written at user level by the entrypoint script
- No project-level Claude settings.json exists (skills directory preserved)
- Codex template uses correct values that the Codex CLI actually accepts
</success_criteria>

<output>
After completion, create `.planning/quick/260414-iee-move-claude-codex-config-from-workspace-/260414-iee-SUMMARY.md`
</output>
