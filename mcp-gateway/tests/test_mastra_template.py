"""CLI-02, CLI-03 (D-06..D-09): templates/mastra/ scaffold static checks.

This test runs WITHOUT npm — it asserts that the package.json pins, .env.example
fields, CLI/Studio API surface, and README drop-in snippet are present and correct.
The actual `npm install && npm start` smoke lives in Plan 05's e2e test.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "templates" / "mastra"


def test_template_dir_exists():
    assert TEMPLATE.is_dir(), f"missing mastra template at {TEMPLATE}"


def test_required_files_present():
    for name in ("package.json", "tsconfig.json", ".env.example",
                 "README.md", ".gitignore", "src/index.ts",
                 "src/mare.ts", "src/mastra/index.ts",
                 "src/mastra/agents/mare-agent.ts",
                 "src/mastra/tools/mare-tools.ts",
                 "src/mastra/mcp/mare-client.ts",
                 "src/mastra/mcp/mare-server.ts"):
        assert (TEMPLATE / name).is_file(), f"missing {name}"


def test_package_json_pins_mastra_mcp_to_1_3_x():
    """D-08: pin @mastra/mcp to ~1.3.1, NEVER caret/^."""
    pkg = json.loads((TEMPLATE / "package.json").read_text())
    assert pkg["dependencies"]["@mastra/mcp"] == "~1.3.1", pkg["dependencies"]


def test_package_json_declares_mastra_core_and_zod():
    pkg = json.loads((TEMPLATE / "package.json").read_text())
    assert pkg["dependencies"]["@mastra/core"].startswith("^1.")
    assert pkg["dependencies"]["zod"].startswith("^3.") or pkg["dependencies"]["zod"].startswith("^4.")


def test_package_json_engines_node_20():
    pkg = json.loads((TEMPLATE / "package.json").read_text())
    assert pkg["engines"]["node"] == ">=20"


def test_package_json_start_script_uses_tsx():
    pkg = json.loads((TEMPLATE / "package.json").read_text())
    assert "tsx" in pkg["scripts"]["start"]


def test_package_json_dev_script_uses_mastra_studio():
    pkg = json.loads((TEMPLATE / "package.json").read_text())
    assert pkg["scripts"]["dev"] == "mastra dev"
    assert pkg["scripts"]["studio"] == "mastra dev"
    assert pkg["devDependencies"]["mastra"].startswith("^1.")


def test_env_example_lists_locked_env_vars():
    """RESEARCH Pitfall 8: the locked Phase 4 env-var names."""
    text = (TEMPLATE / ".env.example").read_text()
    assert "MARE_GATEWAY_TOKEN" in text
    assert "MARE_GATEWAY_URL" in text


def test_index_ts_uses_MCPClient_not_legacy_class():
    """CLAUDE.md Do NOT Use: MastraMCPClient is deprecated."""
    text = "\n".join(path.read_text() for path in (TEMPLATE / "src").glob("*.ts"))
    assert "MCPClient" in text
    assert "MastraMCPClient" not in text


def test_index_ts_references_locked_env_vars():
    text = (TEMPLATE / "src" / "mare.ts").read_text()
    assert "MARE_GATEWAY_TOKEN" in text
    assert "MARE_GATEWAY_URL" in text


def test_index_ts_does_full_triage_path():
    """D-07: starter walks connect -> upload -> run_triage -> fetch report."""
    text = (TEMPLATE / "src" / "mare.ts").read_text()
    assert "/upload" in text
    assert "run_triage" in text
    assert "get_artifact" in text
    assert "10_reporting_draft.md" in text


def test_mastra_studio_registers_agent_tools_and_mcp_server():
    text = (TEMPLATE / "src" / "mastra" / "index.ts").read_text()
    assert "new Mastra" in text
    assert "mareAgent" in text
    assert "mareStudioTools" in text
    assert "mareToolboxMcpServer" in text


def test_mastra_studio_tools_wrap_gateway_workflow():
    text = (TEMPLATE / "src" / "mastra" / "tools" / "mare-tools.ts").read_text()
    assert "mare_status" in text
    assert "mare_triage_sample_path" in text
    assert "analyzeSamplePath" in text


def test_readme_has_dropin_snippet():
    """D-09: 5-10 line drop-in for users with an existing mastra project."""
    text = (TEMPLATE / "README.md").read_text()
    assert "Drop-in snippet" in text
    assert 'import { MCPClient } from "@mastra/mcp"' in text


def test_readme_documents_mastra_studio_command():
    text = (TEMPLATE / "README.md").read_text()
    assert "Mastra Studio" in text
    assert "npm run dev" in text
    assert "http://127.0.0.1:4111" in text
    assert "MARE Malware Analysis Agent" in text


@pytest.mark.parametrize("banned", ["mcp-remote", "MastraMCPClient", "/sse"])
def test_no_banned_tech_in_template(banned):
    """CLAUDE.md Do NOT Use list — none of these may appear anywhere in the template."""
    for path in TEMPLATE.rglob("*"):
        if "node_modules" in path.parts:
            continue
        if path.is_file() and path.suffix in (".json", ".ts", ".md", ".env"):
            text = path.read_text(encoding="utf-8", errors="replace")
            assert banned not in text, f"banned token {banned!r} present in {path}"
