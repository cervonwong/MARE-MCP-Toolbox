import { Mastra } from "@mastra/core";

import { mareAgent } from "./agents/mare-agent.js";
import { mareToolboxMcpServer } from "./mcp/mare-server.js";
import { mareStudioTools } from "./tools/mare-tools.js";

const studioPort = Number.parseInt(process.env.MARE_STUDIO_PORT ?? "", 10);

export const mastra = new Mastra({
  server: {
    host: process.env.MARE_STUDIO_HOST ?? "localhost",
    port: Number.isInteger(studioPort) ? studioPort : 4111,
  },
  agents: {
    mareAgent,
  },
  tools: mareStudioTools,
  mcpServers: {
    mareToolboxMcpServer,
  },
});
