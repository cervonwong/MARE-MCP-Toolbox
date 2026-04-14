---
phase: quick-260414-fsg
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - workspace/.claude/settings.json
  - workspace/.codex/config.toml
  - docker-bin/configure-agent-mcp.sh
  - Dockerfile
  - docker-bin/claude
  - docker-bin/codex
  - run_docker.sh
autonomous: true

must_haves:
  truths:
    - "Claude Code inside container uses model opus, effort high, bypassPermissions mode without wrapper script"
    - "Codex inside container uses model gpt-5.4, reasoning effort xhigh, full-auto mode without wrapper script"
    - "skipDangerousModePermissionPrompt is set at user level so Claude does not prompt for dangerous mode confirmation"
    - "docker-bin/claude and docker-bin/codex wrapper scripts no longer exist"
    - "Dockerfile installs claude normally without rename trick"
    - "configure-agent-mcp.sh still works for MCP server setup and now also merges permission settings"
  artifacts:
    - path: "workspace/.claude/settings.json"
      provides: "Project-level Claude config"
      contains: "bypassPermissions"
    - path: "workspace/.codex/config.toml"
      provides: "Project-level Codex config"
      contains: "model_reasoning_effort"
    - path: "docker-bin/configure-agent-mcp.sh"
      provides: "Extended boot script merging user-level permission settings"
      contains: "skipDangerousModePermissionPrompt"
  key_links:
    - from: "workspace/.claude/settings.json"
      to: "Claude Code runtime"
      via: "mounted at /agent/.claude/settings.json, detected as project-level config"
    - from: "docker-bin/configure-agent-mcp.sh"
      to: "~/.claude/settings.json"
      via: "merges skipDangerousModePermissionPrompt and permissions.defaultMode at boot"
---

<objective>
Replace docker-bin/claude and docker-bin/codex CLI wrapper scripts with native project-level config files. Remove the wrapper installation plumbing from the Dockerfile. Extend configure-agent-mcp.sh to handle user-level permission settings that cannot live at project level.

Purpose: Eliminate fragile wrapper scripts that intercept CLI arguments. Native config files are the supported mechanism for setting defaults.
Output: Two config files (settings.json, config.toml), simplified Dockerfile, extended configure-agent-mcp.sh, deleted wrappers.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@workspace/.codex/config.toml
@docker-bin/configure-agent-mcp.sh
@docker-bin/claude
@docker-bin/codex
@Dockerfile
@run_docker.sh
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create native config files and extend configure-agent-mcp.sh</name>
  <files>workspace/.claude/settings.json, workspace/.codex/config.toml, docker-bin/configure-agent-mcp.sh</files>
  <action>
1. Create `workspace/.claude/settings.json` with project-level Claude defaults:
```json
{
  "permissions": {
    "defaultMode": "bypassPermissions"
  },
  "model": "opus",
  "effortLevel": "high"
}
```

2. Update `workspace/.codex/config.toml` — the file already exists with `model`, `model_reasoning_effort`, `plan_mode_reasoning_effort`, `suppress_unstable_features_warning`, and `[features]`. Add two new top-level keys for sandbox/approval policy:
```toml
approval_policy = "full-auto"
sandbox_mode = "none"
```
Add these BEFORE the existing `model = "gpt-5.4"` line. Keep all existing content intact.

Note: Codex `--dangerously-bypass-approvals-and-sandbox` is equivalent to `approval_policy = "full-auto"` + `sandbox_mode = "none"` in config.toml. The wrapper also injected `-c 'model_reasoning_effort="xhigh"'` which is already in the config.toml template.

3. Extend `docker-bin/configure-agent-mcp.sh` — the existing Python block (lines 18-34) merges `trustedDirectories` into `~/.claude/settings.json`. Extend it to ALSO merge:
   - `"skipDangerousModePermissionPrompt": true`
   - `"permissions": {"defaultMode": "bypassPermissions"}`

Update the Python script embedded at lines 18-34 to:
```python
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = {}
if path.exists():
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        data = {}

trusted = list(dict.fromkeys((data.get("trustedDirectories") or []) + ["/agent", "/home/agent"]))
data["trustedDirectories"] = trusted

# User-level permission settings (cannot be set at project level)
data["skipDangerousModePermissionPrompt"] = True
permissions = data.get("permissions", {})
permissions["defaultMode"] = "bypassPermissions"
data["permissions"] = permissions

path.write_text(json.dumps(data))
```

This replaces the need for `--dangerously-skip-permissions` from the wrapper. The project-level settings.json also sets `permissions.defaultMode`, but the user-level `skipDangerousModePermissionPrompt` is what prevents the confirmation prompt.
  </action>
  <verify>
    <automated>python3 -c "import json; d=json.load(open('workspace/.claude/settings.json')); assert d['permissions']['defaultMode']=='bypassPermissions'; assert d['model']=='opus'; assert d['effortLevel']=='high'; print('claude settings OK')" && grep -q 'approval_policy' workspace/.codex/config.toml && grep -q 'sandbox_mode' workspace/.codex/config.toml && grep -q 'model_reasoning_effort' workspace/.codex/config.toml && grep -q 'skipDangerousModePermissionPrompt' docker-bin/configure-agent-mcp.sh && echo "All config files OK"</automated>
  </verify>
  <done>
- workspace/.claude/settings.json exists with model, effortLevel, permissions.defaultMode
- workspace/.codex/config.toml has approval_policy, sandbox_mode, model, model_reasoning_effort
- configure-agent-mcp.sh merges skipDangerousModePermissionPrompt and permissions.defaultMode into user-level settings
  </done>
</task>

<task type="auto">
  <name>Task 2: Delete wrappers and simplify Dockerfile</name>
  <files>docker-bin/claude, docker-bin/codex, Dockerfile</files>
  <action>
1. Delete `docker-bin/claude` and `docker-bin/codex` wrapper scripts entirely.

2. Simplify Dockerfile — make these specific changes:

   a. Line 113 — Remove the Codex wrapper install line:
      DELETE: `RUN install -m 0755 /opt/docker-bin/codex /usr/local/bin/codex`

   b. Lines 118-128 — Replace the Claude install block with a simplified version that does NOT rename claude to claude-real and does NOT install a wrapper:
      REPLACE the entire block from `# Install Claude Code CLI (native installer)` through the `gosu agent env ... claude --version` line with:
      ```dockerfile
      # Install Claude Code CLI (native installer)
      RUN set -eux; \
          printf '#!/bin/bash\ncurl -fsSL https://claude.ai/install.sh | bash\n' > /tmp/install-claude.sh; \
          chmod +x /tmp/install-claude.sh; \
          gosu agent env HOME=/home/agent USER=agent LOGNAME=agent /tmp/install-claude.sh; \
          rm -f /tmp/install-claude.sh; \
          ln -sf /home/agent/.local/bin/claude /usr/local/bin/claude; \
          gosu agent env HOME=/home/agent USER=agent LOGNAME=agent claude --version
      ```
      Key changes: removed `mv claude claude-real`, removed `install wrapper`, kept the symlink to `/usr/local/bin/claude` pointing at the real binary.

   c. The `COPY docker-bin/ /opt/docker-bin/` on line 9 can stay — configure-agent-mcp.sh still needs it. But the deleted wrapper files simply won't be there anymore.

3. Verify the Dockerfile still references configure-agent-mcp.sh install on line 116 — that stays unchanged.
  </action>
  <verify>
    <automated>test ! -f docker-bin/claude && test ! -f docker-bin/codex && test -f docker-bin/configure-agent-mcp.sh && ! grep -q 'claude-real' Dockerfile && ! grep -q 'docker-bin/codex' Dockerfile && grep -q 'configure-agent-mcp.sh' Dockerfile && echo "Wrappers removed and Dockerfile simplified"</automated>
  </verify>
  <done>
- docker-bin/claude deleted
- docker-bin/codex deleted
- docker-bin/configure-agent-mcp.sh still exists
- Dockerfile no longer renames claude to claude-real
- Dockerfile no longer installs codex wrapper
- Dockerfile still installs configure-agent-mcp.sh
- Claude installed normally with symlink to /usr/local/bin/claude
  </done>
</task>

<task type="auto">
  <name>Task 3: Update run_docker.sh build hash inputs</name>
  <files>run_docker.sh</files>
  <action>
The build hash calculation in run_docker.sh (lines 85-94) includes `find "$SCRIPT_DIR/docker-bin" -type f` in the checksum. Since we deleted two files from docker-bin, the hash will naturally change on next build — no code change needed for correctness.

However, review and confirm that `run_docker.sh` does NOT need any other changes:
- The `CLAUDE_USER_DIR` seeding (lines 133-146) copies `.credentials.json` and `state.json` into `~/.claude-docker/` which gets mounted as `~/.claude/` — this is fine, configure-agent-mcp.sh will merge permission settings into whatever is already there.
- No wrapper-specific logic exists in run_docker.sh.
- compose.yaml volume mounts are already correct (workspace/ -> /agent/).

The only change needed: add a comment near the CLAUDE_USER_DIR section noting that permission settings are now handled by configure-agent-mcp.sh at boot, not by run_docker.sh seeding. This is documentation-only for maintainability.

Actually, on reflection, no changes are needed to run_docker.sh at all. The configure-agent-mcp.sh approach handles everything at container boot. Skip this task if the executor confirms no run_docker.sh changes are needed after reviewing.

Mark this task as: verify-only. Read run_docker.sh, confirm no wrapper references exist, confirm no changes needed.
  </action>
  <verify>
    <automated>! grep -q 'claude-real' run_docker.sh && ! grep -q 'docker-bin/claude' run_docker.sh && ! grep -q 'docker-bin/codex' run_docker.sh && echo "run_docker.sh has no wrapper references"</automated>
  </verify>
  <done>
- run_docker.sh confirmed to have no wrapper-specific logic
- No changes needed to run_docker.sh
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Host -> Container | Config files mounted from host into container at /agent/ |
| Boot script -> User config | configure-agent-mcp.sh writes to ~/.claude/settings.json |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-fsg-01 | T (Tampering) | workspace/.claude/settings.json | accept | Project-level config is repo-tracked; any tampering is visible in git diff. Container runs in trusted local environment. |
| T-fsg-02 | E (Elevation) | bypassPermissions in settings | accept | Intentional for autonomous agent operation inside sandboxed container. Container already runs with elevated capabilities by design. |
</threat_model>

<verification>
1. `workspace/.claude/settings.json` exists with correct model, effort, permissions
2. `workspace/.codex/config.toml` has approval_policy, sandbox_mode, model, reasoning effort
3. `docker-bin/claude` and `docker-bin/codex` do not exist
4. `docker-bin/configure-agent-mcp.sh` merges skipDangerousModePermissionPrompt
5. Dockerfile has no claude-real rename, no codex wrapper install
6. run_docker.sh has no wrapper references
</verification>

<success_criteria>
- All wrapper functionality replaced by native config files
- Dockerfile simplified (fewer lines, no rename trick)
- configure-agent-mcp.sh handles user-level permission bypass at boot
- No references to claude-real or wrapper scripts remain in any file
- Existing MCP configuration flow in configure-agent-mcp.sh unchanged
</success_criteria>

<output>
After completion, create `.planning/quick/260414-fsg-replace-docker-bin-wrappers-with-native-/260414-fsg-SUMMARY.md`
</output>
