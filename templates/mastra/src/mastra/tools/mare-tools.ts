import { createTool } from "@mastra/core/tools";
import { z } from "zod";

import {
  analyzeSamplePath,
  DEFAULT_GATEWAY_URL,
  gatewayEndpoint,
  listToolNames,
  loadGatewayConfig,
} from "../../mare.js";

const uploadSchema = z.object({
  sample_id: z.string(),
  path: z.string(),
  size: z.number(),
});

const analysisResultSchema = z.object({
  toolsAvailable: z.number(),
  toolNames: z.array(z.string()),
  upload: uploadSchema,
  triageResult: z.unknown(),
  caseDir: z.string(),
  reportText: z.string(),
  reportExcerpt: z.string(),
});

export const mareStatusTool = createTool({
  id: "mare_status",
  description: "Check the MARE-MCP-Toolbox gateway health and list available remote MCP tools.",
  inputSchema: z.object({}),
  outputSchema: z.object({
    ok: z.boolean(),
    gatewayUrl: z.string(),
    toolsAvailable: z.number(),
    toolNames: z.array(z.string()),
    error: z.string().optional(),
  }),
  mcp: {
    annotations: {
      title: "MARE gateway status",
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false,
    },
  },
  execute: async () => {
    try {
      const config = loadGatewayConfig();
      const healthResp = await fetch(gatewayEndpoint(config.url, "/healthz"), {
        headers: { Authorization: `Bearer ${config.token}` },
      });
      const toolNames = await listToolNames(config);

      return {
        ok: healthResp.ok,
        gatewayUrl: config.url,
        toolsAvailable: toolNames.length,
        toolNames,
      };
    } catch (err) {
      return {
        ok: false,
        gatewayUrl: process.env.MARE_GATEWAY_URL ?? DEFAULT_GATEWAY_URL,
        toolsAvailable: 0,
        toolNames: [],
        error: err instanceof Error ? err.message : String(err),
      };
    }
  },
});

export const mareTriageSamplePathTool = createTool({
  id: "mare_triage_sample_path",
  description: "Upload a malware sample from a local path, run MARE triage through the remote MCP gateway, and return the generated reporting draft.",
  inputSchema: z.object({
    samplePath: z.string().default("../../workspace/examples/samples/mfc42ul.dll"),
  }),
  outputSchema: analysisResultSchema,
  mcp: {
    annotations: {
      title: "Run MARE triage for a sample path",
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: false,
    },
  },
  execute: async ({ samplePath }) => analyzeSamplePath(
    loadGatewayConfig(),
    samplePath ?? "../../workspace/examples/samples/mfc42ul.dll",
  ),
});

export const mareStudioTools = {
  mare_status: mareStatusTool,
  mare_triage_sample_path: mareTriageSamplePathTool,
};
