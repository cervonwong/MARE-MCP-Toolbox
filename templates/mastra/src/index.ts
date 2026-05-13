import { analyzeSamplePath, ConfigError, loadGatewayConfig } from "./mare.js";

const samplePath = process.argv[2];
if (!samplePath) {
  console.error("[error] usage: npm start <path-to-sample-binary>");
  process.exit(2);
}

async function main() {
  const config = loadGatewayConfig();
  const result = await analyzeSamplePath(config, samplePath);

  console.log(`Tools available: ${result.toolsAvailable}`);
  console.log(`Uploaded: ${result.upload.sample_id}`);
  console.log(`Triage result: ${JSON.stringify(result.triageResult).slice(0, 400)}`);
  console.log(`Report excerpt: ${result.reportText.slice(0, 200)}`);
}

main().catch((err) => {
  if (err instanceof ConfigError) {
    console.error("[error]", err.message);
    console.error("[error] copy your token from `./run_docker.sh --print-config` and put it in .env");
    process.exit(2);
  }
  console.error("[error]", err);
  process.exit(1);
});
