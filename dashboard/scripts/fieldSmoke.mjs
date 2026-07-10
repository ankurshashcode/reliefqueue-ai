import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  FIELD_CASE_ALLOWLIST,
  FIELD_STATUS_OPTIONS,
  WORKER_PATH,
  authorizedFieldCases,
  createContactAuditEvent,
  createStatusAuditEvent,
  findWorker,
  loadFieldBundle,
  renderedFieldTextHasForbiddenContent
} from "../src/fieldData.js";
import { FORBIDDEN_WORDING, renderedTextHasForbiddenContent } from "../src/reportData.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(dashboardRoot, "..");
const previewOrigin = "http://127.0.0.1:4174";
const previewUrl = `${previewOrigin}/field/my-cases?worker_id=worker-alpha-boat`;
const checks = [];

function pass(name, detail = "") {
  checks.push({ name, status: "PASS", detail });
  console.log(`PASS ${name}${detail ? ` - ${detail}` : ""}`);
}

function check(name, condition, detail = "") {
  if (!condition) {
    console.log(`FAIL ${name}${detail ? ` - ${detail}` : ""}`);
    throw new Error(`${name} failed${detail ? `: ${detail}` : ""}`);
  }
  pass(name, detail);
}

async function fetchTextFromPreview(urlPath) {
  const response = await fetch(`${previewOrigin}${urlPath}`);
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${urlPath} was not served by dashboard preview: ${response.status} ${response.statusText}`);
  }
  const trimmed = text.trimStart().toLowerCase();
  if (trimmed.startsWith("<!doctype") || trimmed.startsWith("<html")) {
    throw new Error(`${urlPath} returned dashboard HTML instead of data`);
  }
  return text;
}

async function waitForPreview() {
  const started = Date.now();
  let lastError = "";
  while (Date.now() - started < 15000) {
    try {
      const response = await fetch(previewUrl);
      if (response.ok) return response.text();
      lastError = `${response.status} ${response.statusText}`;
    } catch (error) {
      lastError = error.message;
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`field route did not load from preview: ${lastError}`);
}

async function main() {
  console.log("ReliefQueue field smoke");
  console.log("Route: /field/my-cases?worker_id=worker-alpha-boat");

  const distIndex = path.resolve(dashboardRoot, "dist", "index.html");
  await fs.access(distIndex).catch(() => {
    throw new Error("dashboard/dist/index.html missing. Run make dashboard-build first.");
  });

  const preview = spawn(
    "npm",
    ["run", "preview", "--", "--host", "127.0.0.1", "--port", "4174"],
    {
      cwd: dashboardRoot,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"]
    }
  );

  try {
    const routeHtml = await waitForPreview();
    check("field route served by preview", routeHtml.includes("root"));

    const bundle = await loadFieldBundle(fetchTextFromPreview);
    pass("field data fetched through preview server", "fixtures and reports loaded from dashboard public data");
    check("required worker fixture exists", bundle.workers.length > 0, WORKER_PATH);
    check("required cases exist", bundle.cases.length > 0);
    check("required assignment candidates exist", bundle.assignments.length > 0);

    const worker = findWorker(bundle.workers, "worker-alpha-boat");
    check("valid worker lookup succeeds", Boolean(worker));
    check("missing worker shows no cases", authorizedFieldCases(bundle.cases, bundle.assignments, null).length === 0);
    check("invalid worker shows no cases", authorizedFieldCases(bundle.cases, bundle.assignments, { worker_id: "missing", authorized_zone_ids: [] }).length === 0);

    const fieldCases = authorizedFieldCases(bundle.cases, bundle.assignments, worker);
    const authorizedCaseIds = new Set(
      bundle.assignments
        .filter((row) => (row.candidate_worker_id || row.worker_id) === worker.worker_id)
        .map((row) => row.case_id)
    );
    check("worker has authorized cases", fieldCases.length > 0, `${fieldCases.length} cases`);
    check(
      "worker sees only candidate cases",
      fieldCases.every((row) => authorizedCaseIds.has(row.case_id))
    );
    check(
      "unknown-location cases excluded",
      fieldCases.every((row) => row.operation_zone_id && row.operation_zone_id !== "unknown")
    );
    check(
      "case adapter uses explicit allowlist",
      fieldCases.every((row) => JSON.stringify(Object.keys(row)) === JSON.stringify(FIELD_CASE_ALLOWLIST))
    );

    const fieldText = JSON.stringify(fieldCases);
    const privateScan = renderedFieldTextHasForbiddenContent(fieldText);
    const forbiddenScan = renderedTextHasForbiddenContent(fieldText);
    check("raw private keys absent", privateScan.privateKeys.length === 0, privateScan.privateKeys.join(", "));
    check("phone-like values absent", privateScan.phones.length === 0, privateScan.phones.join(", "));
    check("forbidden product wording absent", forbiddenScan.wording.length === 0, forbiddenScan.wording.join(", "));
    for (const phrase of FORBIDDEN_WORDING) {
      check(`forbidden phrase absent in field data: ${phrase}`, !fieldText.toLowerCase().includes(phrase.toLowerCase()));
    }

    const statusEvent = createStatusAuditEvent({
      workerId: worker.worker_id,
      caseId: fieldCases[0].case_id,
      newStatus: FIELD_STATUS_OPTIONS[1]
    });
    check("status audit schema", statusEvent.event_type === "status_update" && statusEvent.sync_state === "pending_sync");
    check("status audit is safe", !JSON.stringify(statusEvent).match(/(?:\+?\d[\s-]?){10,}/));

    const contactEvent = createContactAuditEvent({ workerId: worker.worker_id, caseId: fieldCases[0].case_id });
    check(
      "contact audit schema",
      contactEvent.event_type === "contact_attempt_created" &&
        contactEvent.contact_mode === "reliefqueue_contact" &&
        contactEvent.private_number_revealed === false
    );

    const css = await fs.readFile(path.resolve(dashboardRoot, "src", "styles.css"), "utf-8");
    check("mobile single-column shell present", css.includes(".field-shell") && css.includes("max-width: 520px"));
    check("large field buttons present", css.includes("min-height: 44px"));
    check("people directory styles present", css.includes(".people-grid") && css.includes(".person-card"));
    check("floating call chip styles present", css.includes(".call-chip"));

    const evidenceDir = path.resolve(repoRoot, "reports/latest/field", "evidence");
    await fs.mkdir(evidenceDir, { recursive: true });
    const auditSamplePath = path.resolve(evidenceDir, "field_audit_demo_sample.jsonl");
    await fs.writeFile(
      auditSamplePath,
      `${JSON.stringify(statusEvent)}\n${JSON.stringify(contactEvent)}\n`,
      "utf-8"
    );
    const outputPath = path.resolve(evidenceDir, "field-smoke.txt");
    await fs.writeFile(
      outputPath,
      checks.map((item) => `${item.status} ${item.name}${item.detail ? ` - ${item.detail}` : ""}`).join("\n") + "\n",
      "utf-8"
    );
    console.log(`PASS evidence written - ${path.relative(repoRoot, auditSamplePath)}`);
    console.log(`field smoke passed (${checks.length} checks)`);
  } finally {
    if (preview.pid) {
      try {
        process.kill(-preview.pid, "SIGTERM");
      } catch {
        preview.kill("SIGTERM");
      }
    }
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
