# Codex Project Instructions

Use `CLAUDE.md` as the source of project architecture and planning context. This repository keeps the runnable agent workspace under `workspace/`, which is mounted as `/agent` inside the analysis container.

Codex-specific skills live in `workspace/.codex/skills/`. For malware sample triage or reverse-engineering work, load the `malware-analysis-orchestrator` skill from that directory and follow its artifact discipline.

When updating a shared analysis skill, keep the Claude and Codex copies synchronized:

1. Claude source: `workspace/.claude/skills/<skill-name>/`
2. Codex copy: `workspace/.codex/skills/<skill-name>/`
3. Codex wording should refer to Codex, not Claude, where the agent identity matters.
