/**
 * MARE-MCP-Toolbox — Mastra starter.
 *
 * Demonstrates the full triage happy path against a running gateway:
 *   1. Connect via @mastra/mcp MCPClient over Streamable HTTP with bearer auth.
 *   2. Upload a sample binary to POST /upload (raw bytes + X-Filename header).
 *   3. Call mare_run_triage with the returned sample_id (sha256 content hash).
 *   4. Fetch the resulting report via mare_get_artifact.
 *
 * Usage:  npm start <path-to-sample-binary>
 * Env:    MARE_GATEWAY_TOKEN (required), MARE_GATEWAY_URL (default localhost:8080/mcp)
 */
import "dotenv/config";
import { MCPClient } from "@mastra/mcp";
import { readFile } from "node:fs/promises";
import { basename } from "node:path";

const TOKEN = process.env.MARE_GATEWAY_TOKEN;
const URL_  = process.env.MARE_GATEWAY_URL ?? "http://localhost:8080/mcp";
if (!TOKEN) {
  console.error("[error] MARE_GATEWAY_TOKEN env var is required");
  console.error("[error] copy your token from `./run_docker.sh --print-config` and put it in .env");
  process.exit(2);
}

const samplePath = process.argv[2];
if (!samplePath) {
  console.error("[error] usage: npm start <path-to-sample-binary>");
  process.exit(2);
}

async function main() {
  // (1) Connect.
  const mcp = new MCPClient({
    servers: {
      mare: {
        url: new URL(URL_),
        requestInit: {
          headers: { Authorization: `Bearer ${TOKEN}` },
        },
      },
    },
  });

  const tools = await mcp.getTools();
  console.log(`Tools available: ${Object.keys(tools).length}`);

  // (2) Upload sample to /upload (separate HTTP endpoint per Phase 2 D-11..D-15).
  // Returns { sample_id: <sha256>, path: <stored-path>, size: <bytes> }.
  const sampleBytes = await readFile(samplePath);
  const uploadUrl = URL_.replace(/\/mcp\/?$/, "/upload");
  const uploadResp = await fetch(uploadUrl, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "X-Filename": basename(samplePath),
      "Content-Type": "application/octet-stream",
    },
    body: sampleBytes,
  });
  if (!uploadResp.ok) {
    throw new Error(`upload failed: ${uploadResp.status} ${await uploadResp.text()}`);
  }
  const uploadJson = await uploadResp.json() as { sample_id: string; size: number; path: string };
  const sampleId = uploadJson.sample_id;
  console.log(`Uploaded: ${sampleId}`);

  // (3) Run triage with the sample_id (sha256 hash used by resolve_sample internally).
  const triageTool = tools["mare_run_triage"];
  if (!triageTool) {
    throw new Error("mare_run_triage tool not exposed by gateway — is the backend up?");
  }
  const triageResult = await triageTool.execute({ context: { sample: sampleId } });
  console.log(`Triage result: ${JSON.stringify(triageResult).slice(0, 400)}`);

  // (4) Fetch the report.
  const artifactTool = tools["mare_get_artifact"];
  if (!artifactTool) {
    throw new Error("mare_get_artifact tool not exposed by gateway");
  }
  // Case ID convention: NNN-<basename>. The triage result usually carries the resolved case_id;
  // fall back to looking it up via list_cases if not present.
  const caseId = (triageResult as { case_id?: string })?.case_id
    ?? (await tools["mare_list_cases"].execute({ context: {} }) as Array<{ name: string }>)
        .find(c => c.name.endsWith(basename(samplePath)))?.name;
  if (!caseId) {
    throw new Error("could not determine case_id from triage result or list_cases");
  }
  const report = await artifactTool.execute({
    context: { case_id: caseId, artifact_name: "10_reporting_draft.md" },
  });
  console.log(`Report excerpt: ${String(report).slice(0, 200)}`);

  await mcp.disconnect();
}

main().catch((err) => {
  console.error("[error]", err);
  process.exit(1);
});
