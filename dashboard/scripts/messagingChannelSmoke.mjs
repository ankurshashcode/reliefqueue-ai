import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { MESSAGING_CHANNEL_FLOW, messagingEventsForRole } from "../src/operationsData.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(dashboardRoot, "..");
const checks = [];

function check(name, condition, detail = "") {
  if (!condition) {
    throw new Error(`${name} failed${detail ? `: ${detail}` : ""}`);
  }
  checks.push(`PASS ${name}${detail ? ` - ${detail}` : ""}`);
}

async function main() {
  const flow = MESSAGING_CHANNEL_FLOW;
  check("provider env safely skipped", flow.providerStatus.status === "SKIP" && flow.providerStatus.secretValuesPrinted === false);
  check("resident HELP inbound exists", flow.events.some((event) => event.direction === "inbound" && event.summary.includes("HELP")));
  check("outbound acknowledgement exists", flow.events.some((event) => event.direction === "outbound" && event.summary.includes("Acknowledgement")));
  check("field-worker UPDATE exists", flow.events.some((event) => event.from === "worker-alpha-boat" && event.summary.includes("UPDATE")));
  check("IVR keypad transcript note exists", flow.events.some((event) => event.channel === "voice helpline" && event.summary.includes("IVR key 2")));
  check("duplicate suppression works", flow.duplicateCount === 1 && flow.events.some((event) => event.reviewState === "duplicate suppressed"));
  check("audit entries exist", flow.audit.length === flow.events.length && flow.audit.every((event) => event.rawContactStored === false));
  check("case handoff exists", flow.operationsCases.length >= 2 && flow.updates.length >= 2);
  check("uncertainty review flags exist", flow.events.some((event) => event.uncertaintyFlags.includes("location ambiguous")));
  check("role scoped messaging review exists", messagingEventsForRole("quality_reviewer").every((event) => event.reviewState.includes("review") || event.uncertaintyFlags.length > 0));

  const sourceText = await fs.readFile(path.resolve(dashboardRoot, "src", "main.jsx"), "utf-8");
  check("portal messaging panel exists", sourceText.includes("function MessagingChannelPanel"));
  check("public channel wording is visible", sourceText.includes("SMS, WhatsApp, and voice helpline intake"));

  const outputDir = path.resolve(repoRoot, "reports", "latest", "messaging-channel");
  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(
    path.resolve(outputDir, "messaging-channel-smoke.json"),
    `${JSON.stringify({ status: "PASS", checks, flow }, null, 2)}\n`,
    "utf-8"
  );
  await fs.writeFile(path.resolve(outputDir, "messaging-channel-smoke.txt"), checks.join("\n") + "\n", "utf-8");
  console.log(`messaging-channel smoke passed (${checks.length} checks)`);
  console.log(`evidence: ${path.relative(repoRoot, outputDir)}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
