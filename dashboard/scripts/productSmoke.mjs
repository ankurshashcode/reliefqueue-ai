import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  API_CONTRACTS,
  COMMAND_CENTER_STATE,
  CRITICAL_NEEDS,
  contactsForWorker,
  createMediaAnalysisQueue,
  createOutboxItem,
  evictLocalCache,
  gpsPinState,
  mergeIncomingDeltas,
  needsForCase,
  outboxSummary,
  overlapAssignments,
  roleAuditSurfaces,
  roleProfile,
  runAiConfigLifecycle,
  voiceCaptureState
} from "../src/operationsData.js";
import {
  FIELD_CASE_ALLOWLIST,
  authorizedFieldCases,
  findWorker,
  loadFieldBundle,
  renderedFieldTextHasForbiddenContent
} from "../src/fieldData.js";
import { renderedTextHasForbiddenContent } from "../src/reportData.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(dashboardRoot, "..");
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

async function fetchTextFromDisk(urlPath) {
  const clean = urlPath.replace(/^\//, "");
  return fs.readFile(path.resolve(dashboardRoot, "public", clean), "utf-8");
}

async function main() {
  const bundle = await loadFieldBundle(fetchTextFromDisk);
  const worker = findWorker(bundle.workers, "worker-alpha-boat");
  const fieldCases = authorizedFieldCases(bundle.cases, bundle.assignments, worker);
  const firstCase = fieldCases[0];

  check("role scoping keeps command settings out of field role", roleProfile("field_coordinator").commandCenterAccess === false);
  check("command role can access command center", roleProfile("command_center_operator").commandCenterAccess === true);
  check("field case allowlist remains explicit", JSON.stringify(Object.keys(firstCase)) === JSON.stringify(FIELD_CASE_ALLOWLIST));
  check("field users see only assigned work", fieldCases.every((row) => row.operation_zone_id === "zone-ward-01"));

  const contacts = contactsForWorker(worker);
  check("people directory is role and zone scoped", contacts.length > 0 && contacts.every((row) => row.zone === "zone-ward-01" || row.zone === "all-zones"));
  check("people directory includes quick actions", contacts.every((row) => row.contactActions.includes("call") && row.contactActions.includes("block non-critical")));

  const outboxItem = createOutboxItem({
    workerId: worker.worker_id,
    caseId: firstCase.case_id,
    type: "field_note",
    payload: { note: "Reached school gate", createdAt: "2026-07-05T12:00:00.000Z" }
  });
  check("outbox write has idempotency key", outboxItem.idempotencyKey.startsWith("outbox-"));
  check("sync notifier reports pending work", outboxSummary([{ sync_state: "pending_sync" }]).state === "syncing");

  const needs = needsForCase(firstCase);
  check("multi-critical-needs selection uses stable ids", needs.length > 0 && needs.every((id) => CRITICAL_NEEDS.some((need) => need.id === id)));

  const overlap = overlapAssignments(bundle.assignments, firstCase.case_id);
  check("multi-team overlap assignments are exposed", overlap.length > 1 && overlap.some((row) => row.responsibility === "Owns next action"));

  const merge = mergeIncomingDeltas(firstCase, [
    { id: "safe-location", field: "location_clue", value: "School No. 3 north gate", confidence: 0.91, scope: firstCase.operation_zone_id },
    { id: "safe-need", field: "critical_need", value: "water", confidence: 0.95, scope: firstCase.operation_zone_id },
    { id: "risky-location", field: "coordinates", value: "conflict", confidence: 0.61, scope: firstCase.operation_zone_id }
  ]);
  check("safe incoming deltas auto-merge", merge.history.length === 2);
  check("risky incoming delta is flagged", merge.conflicts.length === 1);

  const mediaJobs = createMediaAnalysisQueue(
    [
      { name: "a.jpg", hash: "hash-a", type: "photo", sizeBytes: 100, capturedAt: "2026-07-05T12:00:00Z" },
      { name: "a-copy.jpg", hash: "hash-a", type: "photo", sizeBytes: 100, capturedAt: "2026-07-05T12:01:00Z" },
      { name: "b.wav", hash: "hash-b", type: "audio", sizeBytes: 200, capturedAt: "2026-07-05T12:02:00Z", offline: true }
    ],
    "2026-07-05.1"
  );
  check("media analysis dedupes by hash and config", mediaJobs.length === 2);
  check("media analysis preserves original metadata", mediaJobs.every((job) => job.original.name && job.analysis.summary === ""));
  check("offline media analysis is skipped until online", mediaJobs.some((job) => job.status === "skipped offline"));

  const gpsManual = gpsPinState({ geolocationAvailable: false, permission: "denied" });
  const gpsAuto = gpsPinState({ geolocationAvailable: true, permission: "granted" });
  check("GPS fallback allows manual pin editing", gpsManual.source === "manual" && gpsManual.editable);
  check("GPS auto-detect reports accuracy", gpsAuto.source === "gps" && gpsAuto.accuracyMeters > 0);

  const voiceFallback = voiceCaptureState({ supported: false, transcript: "" });
  const voiceReady = voiceCaptureState({ supported: true, transcript: "Reached area" });
  check("voice fallback remains available", voiceFallback.mode === "typing fallback" && voiceFallback.fallbackAvailable);
  check("voice review requires transcript before save", voiceReady.canSave === true);

  const cache = evictLocalCache(
    [
      { key: "outbox", scope: "outbox", sizeBytes: 10, lastUsedAt: "2026-07-05T12:00:00Z", unsynced: true },
      { key: "active-case", scope: "cases", sizeBytes: 20, lastUsedAt: "2026-07-05T12:00:00Z", pinnedReason: "current assignment" },
      { key: "old-detail", scope: "case-detail", sizeBytes: 100, lastUsedAt: "2026-07-04T12:00:00Z" }
    ],
    40
  );
  check("local cache never evicts unsynced work", cache.kept.some((entry) => entry.key === "outbox"));
  check("local cache evicts inactive non-critical data", cache.evicted.some((entry) => entry.key === "old-detail"));

  const lifecycle = runAiConfigLifecycle(COMMAND_CENTER_STATE.aiConfigs, {
    provider: "OpenAI-compatible",
    model: "relief-triage-next",
    version: "2026-07-05.2"
  });
  check("AI model lifecycle supports test", lifecycle.test.status === "passed");
  check("AI model lifecycle supports activate", lifecycle.activated.status === "active");
  check("AI model lifecycle supports rollback", Boolean(lifecycle.rollbackTarget.version));

  const audits = roleAuditSurfaces();
  check("field audit surface exists", audits.field.includes("outbox"));
  check("local coordinator audit surface exists", audits.localCoordinator.includes("assignment conflicts"));
  check("command center audit surface exists", audits.commandCenter.includes("AI settings changes"));
  check("quality reviewer audit surface exists", audits.qualityReviewer.includes("review outcomes"));

  check("sync contracts use cursor and role scope", API_CONTRACTS.sync.includes("cursor") && API_CONTRACTS.sync.includes("role"));
  check("media metadata sync is separate", API_CONTRACTS.caseMedia.includes("/media"));

  const publicText = JSON.stringify({ contacts, fieldCases, audits, lifecycle, contracts: API_CONTRACTS });
  const privateScan = renderedFieldTextHasForbiddenContent(publicText);
  const forbiddenScan = renderedTextHasForbiddenContent(publicText);
  check("public language guard private keys absent", privateScan.privateKeys.length === 0);
  check("public language guard phone values absent", privateScan.phones.length === 0);
  check("public language guard forbidden wording absent", forbiddenScan.wording.length === 0);

  const sourceText = await fs.readFile(path.resolve(dashboardRoot, "src", "main.jsx"), "utf-8");
  check("field floating call chip UI exists", sourceText.includes("function FloatingCallChip"));
  check("command-center AI settings UI exists", sourceText.includes("Test interaction") && sourceText.includes("Rollback"));
  check("mobile tabs keep field views reachable", sourceText.includes("field-tabs"));

  const outputPath = path.resolve(repoRoot, "reports", "latest", "field-command-product-smoke.txt");
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(
    outputPath,
    checks.map((item) => `${item.status} ${item.name}${item.detail ? ` - ${item.detail}` : ""}`).join("\n") + "\n",
    "utf-8"
  );
  console.log(`product smoke passed (${checks.length} checks)`);
  console.log(`evidence: ${path.relative(repoRoot, outputPath)}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
