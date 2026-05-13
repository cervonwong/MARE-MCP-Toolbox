import "dotenv/config";

import { MCPClient } from "@mastra/mcp";
import { constants } from "node:fs";
import { access, readFile } from "node:fs/promises";
import { basename, dirname, isAbsolute, resolve } from "node:path";

export const DEFAULT_GATEWAY_URL = "http://localhost:8080/mcp";
const DEFAULT_TIMEOUT_MS = 300_000;

export type GatewayConfig = {
  token: string;
  url: string;
  timeoutMs: number;
};

export type UploadedSample = {
  sample_id: string;
  path: string;
  size: number;
};

export type AnalysisResult = {
  toolsAvailable: number;
  toolNames: string[];
  upload: UploadedSample;
  triageResult: unknown;
  caseDir: string;
  reportText: string;
  reportExcerpt: string;
};

type ExecutableTool = {
  execute?: (input: Record<string, unknown>, context: Record<string, unknown>) => Promise<unknown>;
};

type ToolMap = Record<string, ExecutableTool>;

export class ConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConfigError";
  }
}

export function loadGatewayConfig(env: NodeJS.ProcessEnv = process.env): GatewayConfig {
  const token = env.MARE_GATEWAY_TOKEN;
  if (!token) {
    throw new ConfigError("MARE_GATEWAY_TOKEN env var is required");
  }

  const timeoutMs = Number.parseInt(env.MARE_GATEWAY_TIMEOUT_MS ?? "", 10);
  return {
    token,
    url: env.MARE_GATEWAY_URL ?? DEFAULT_GATEWAY_URL,
    timeoutMs: Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : DEFAULT_TIMEOUT_MS,
  };
}

export function gatewayEndpoint(mcpUrl: string, endpoint: string): string {
  const url = new URL(mcpUrl);
  const normalizedEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const basePath = url.pathname.replace(/\/mcp\/?$/, "").replace(/\/$/, "");
  url.pathname = `${basePath}${normalizedEndpoint}`;
  url.search = "";
  url.hash = "";
  return url.toString();
}

export async function listToolNames(config: GatewayConfig): Promise<string[]> {
  return withMareTools(config, async (tools) => Object.keys(tools).sort());
}

export async function analyzeSamplePath(config: GatewayConfig, samplePath: string): Promise<AnalysisResult> {
  const resolvedPath = await resolveReadablePath(samplePath);
  const sampleBytes = await readFile(resolvedPath);
  return analyzeSampleBytes(config, sampleBytes, basename(resolvedPath));
}

export async function analyzeSampleBytes(
  config: GatewayConfig,
  sampleBytes: Uint8Array,
  filename: string,
): Promise<AnalysisResult> {
  const upload = await uploadSampleBytes(config, sampleBytes, filename);

  return withMareTools(config, async (tools) => {
    const toolNames = Object.keys(tools).sort();
    const triageResult = await executeTool(tools["run_triage"], "run_triage", { sample: upload.sample_id });
    const failedSteps = getFailedSteps(triageResult);
    if (failedSteps.length > 0) {
      throw new Error(`triage failed: ${JSON.stringify(failedSteps).slice(0, 800)}`);
    }

    const caseDir = await resolveCaseDir(tools, triageResult, filename);
    const report = await executeTool(tools["get_artifact"], "get_artifact", {
      case_dir: caseDir,
      artifact_name: "10_reporting_draft.md",
    });
    const reportText = extractReportText(report);
    if (reportText.startsWith("Error executing tool")) {
      throw new Error(reportText);
    }

    return {
      toolsAvailable: toolNames.length,
      toolNames,
      upload,
      triageResult,
      caseDir,
      reportText,
      reportExcerpt: reportText.slice(0, 1200),
    };
  });
}

export async function uploadSampleBytes(
  config: GatewayConfig,
  sampleBytes: Uint8Array,
  filename: string,
): Promise<UploadedSample> {
  const uploadResp = await fetch(gatewayEndpoint(config.url, "/upload"), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${config.token}`,
      "X-Filename": basename(filename),
      "Content-Type": "application/octet-stream",
    },
    body: Buffer.from(sampleBytes),
  });

  if (!uploadResp.ok) {
    throw new Error(`upload failed: ${uploadResp.status} ${await uploadResp.text()}`);
  }

  return await uploadResp.json() as UploadedSample;
}

export async function withMareTools<T>(
  config: GatewayConfig,
  callback: (tools: ToolMap) => Promise<T>,
): Promise<T> {
  const mcp = new MCPClient({
    id: `mare-helper-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    servers: {
      mare: {
        url: new URL(config.url),
        requestInit: {
          headers: { Authorization: `Bearer ${config.token}` },
        },
      },
    },
    timeout: config.timeoutMs,
  });

  try {
    const toolsets = await mcp.listToolsets() as Record<string, ToolMap>;
    return await callback(toolsets.mare ?? {});
  } finally {
    await mcp.disconnect().catch(() => undefined);
  }
}

export async function executeTool(
  tool: ExecutableTool | undefined,
  name: string,
  input: Record<string, unknown>,
): Promise<unknown> {
  if (!tool?.execute) {
    throw new Error(`${name} tool not exposed by gateway`);
  }
  return unwrapToolResult(await tool.execute(input, { runId: `mare-mastra-${Date.now()}` }));
}

function unwrapToolResult(result: unknown): unknown {
  if (
    result
    && typeof result === "object"
    && "content" in result
    && Array.isArray((result as { content?: unknown }).content)
  ) {
    const text = (result as { content: Array<{ type?: string; text?: string }> }).content
      .find((item) => item.type === "text" && typeof item.text === "string")
      ?.text;
    if (text !== undefined) {
      try {
        return JSON.parse(text);
      } catch {
        return text;
      }
    }
  }
  return result;
}

function getFailedSteps(triageResult: unknown): Array<{ step: string; exit_code: number; stderr_head?: string }> {
  const steps = (triageResult as { steps?: Array<{ step: string; exit_code: number; stderr_head?: string }> })
    ?.steps;
  return steps?.filter((step) => step.exit_code !== 0) ?? [];
}

async function resolveCaseDir(tools: ToolMap, triageResult: unknown, filename: string): Promise<string> {
  const rawCaseDir = (triageResult as { case_dir?: string })?.case_dir
    ?? (triageResult as { case_id?: string })?.case_id
    ?? await findCaseDirFromListCases(tools, filename);

  if (!rawCaseDir) {
    throw new Error("could not determine case_id from triage result or list_cases");
  }

  return rawCaseDir.startsWith("/agent/status/")
    ? rawCaseDir
    : `/agent/status/${rawCaseDir}`;
}

async function findCaseDirFromListCases(tools: ToolMap, filename: string): Promise<string | undefined> {
  const cases = await executeTool(tools["list_cases"], "list_cases", {}) as unknown;
  if (!Array.isArray(cases)) {
    return undefined;
  }

  const sampleName = basename(filename);
  return cases
    .map((item) => (item as { name?: unknown }).name)
    .find((name): name is string => typeof name === "string" && name.endsWith(sampleName));
}

function extractReportText(report: unknown): string {
  return typeof report === "object" && report && "content" in report
    ? String((report as { content: unknown }).content)
    : String(report);
}

async function resolveReadablePath(samplePath: string): Promise<string> {
  const candidates = new Set<string>([samplePath]);

  if (!isAbsolute(samplePath)) {
    let current = process.cwd();
    for (let depth = 0; depth < 10; depth += 1) {
      candidates.add(resolve(current, samplePath));
      const parent = dirname(current);
      if (parent === current) {
        break;
      }
      current = parent;
    }
  }

  let lastError: unknown;
  for (const candidate of candidates) {
    try {
      await access(candidate, constants.R_OK);
      return candidate;
    } catch (err) {
      lastError = err;
    }
  }

  throw lastError instanceof Error ? lastError : new Error(`sample is not readable: ${samplePath}`);
}
