"""CLI-02 (D-13): the templates/mastra/ starter doubles as the e2e test.

Copies the template into tmp_path, runs `npm install` then `npm start <sample>`,
asserts on stdout markers from src/index.ts. Skips cleanly when:
  - npm is not on PATH (Node not installed)
  - the gateway is not reachable (gateway_alive fixture skips the whole session)
  - the example sample binary is missing from the repo
"""

from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MASTRA_TEMPLATE = REPO_ROOT / "templates" / "mastra"
SAMPLE = REPO_ROOT / "workspace" / "examples" / "samples" / "mfc42ul.dll"


@pytest.mark.skipif(
    shutil.which("npm") is None,
    reason="npm not on PATH — install Node.js 20+ to run the mastra starter test",
)
@pytest.mark.skipif(
    not MASTRA_TEMPLATE.is_dir(),
    reason=f"mastra template not found at {MASTRA_TEMPLATE} — Plan 04 not landed",
)
@pytest.mark.skipif(
    not SAMPLE.is_file(),
    reason=f"e2e sample binary missing at {SAMPLE}",
)
def test_mastra_starter_full_triage_path(tmp_path, gateway_alive, bearer_token):
    """D-07: connect → upload → run_triage → fetch report. Asserts on stdout markers.

    Note on subprocess hygiene (RESEARCH Pattern 5):
      - shell=False everywhere (avoids T-04-04 subprocess injection)
      - capture_output + text=True for clean assertions
      - timeouts on every subprocess.run (npm-install can stall on flaky registry)
      - tmp_path keeps node_modules out of the repo tree
    """
    # 1. Copy template to a fresh dir.
    work = tmp_path / "mastra"
    shutil.copytree(MASTRA_TEMPLATE, work)

    env = {
        **os.environ,
        "MARE_GATEWAY_TOKEN": bearer_token,
        "MARE_GATEWAY_URL": f"{gateway_alive}/mcp",
        "npm_config_loglevel": "error",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
    }

    # 2. npm install (cold cache budget: 180s).
    install = subprocess.run(
        ["npm", "install", "--no-audit", "--no-fund"],
        cwd=str(work),
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
        shell=False,
    )
    if install.returncode != 0:
        # Provide a tail of stderr for diagnosis without dumping multi-MB output.
        pytest.fail(
            f"npm install failed (rc={install.returncode}): {install.stderr[-2000:]}"
        )

    # 3. npm start <sample> (triage end-to-end).
    run = subprocess.run(
        ["npm", "start", "--silent", "--", str(SAMPLE)],
        cwd=str(work),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        shell=False,
    )
    if run.returncode != 0:
        pytest.fail(
            f"npm start failed (rc={run.returncode})\n"
            f"--- stdout ---\n{run.stdout[-2000:]}\n"
            f"--- stderr ---\n{run.stderr[-2000:]}"
        )

    # 4. Assert on stdout markers from src/index.ts (Plan 04, D-07).
    out = run.stdout
    assert "Tools available:" in out, (
        f"missing 'Tools available:' in stdout: {out[-500:]}"
    )
    assert "Uploaded:" in out, f"missing 'Uploaded:' in stdout: {out[-500:]}"
    assert "Triage result:" in out, f"missing 'Triage result:' in stdout: {out[-500:]}"
    assert "Report excerpt:" in out, (
        f"missing 'Report excerpt:' in stdout: {out[-500:]}"
    )
