import { Agent } from "@mastra/core/agent";

import { mareMcpTools } from "../mcp/mare-client.js";
import { mareStudioTools } from "../tools/mare-tools.js";

export const mareAgent = new Agent({
  id: "mare-agent",
  name: "MARE Malware Analysis Agent",
  description: "Coordinates malware sample triage through the MARE-MCP-Toolbox remote gateway.",
  instructions: `
You operate MARE-MCP-Toolbox through the remote MCP gateway.

Use mare_status first when checking connectivity or available tools.
Use mare_triage_sample_path when the user gives a local sample path or asks to run the bundled sample.
The bundled sample path is ../../workspace/examples/samples/mfc42ul.dll.

When a triage run finishes, summarize:
- the upload sample_id
- the case directory
- failed steps, if any
- the reporting draft excerpt

Keep analysis claims grounded in returned artifacts and tool outputs.
  `,
  model: process.env.MARE_AGENT_MODEL ?? "openai/gpt-4o-mini",
  tools: {
    ...mareStudioTools,
    ...mareMcpTools,
  },
});
