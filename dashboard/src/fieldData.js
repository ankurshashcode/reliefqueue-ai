import { REPORT_PATHS, operatorStatusLabel, parseJsonLines } from "./reportData.js";

export const WORKER_PATH = "/fixtures/field_workers.json";

export const FIELD_CASE_ALLOWLIST = [
  "case_id",
  "safe_summary",
  "urgency",
  "need_type",
  "people_count",
  "vulnerable_flags",
  "operation_zone_id",
  "location_clue",
  "geo_confidence",
  "coordinator_instruction",
  "assignment_status"
];

export const FIELD_STATUS_OPTIONS = [
  "accepted",
  "on_the_way",
  "reached_area",
  "unable_to_locate",
  "needs_more_support",
  "completed_reported"
];

const PRIVATE_CASE_KEYS = new Set([
  "raw_text_private",
  "reporter_name_private_optional",
  "reporter_phone_private_optional",
  "media_note_private_optional",
  "source_channel",
  "source_report_id",
  "suggested_reply_draft",
  "privacy_level",
  "language_hint"
]);

export async function loadFieldBundle(fetchText) {
  const [casesText, assignmentsText, workersText] = await Promise.all([
    fetchText(REPORT_PATHS.cases),
    fetchText(REPORT_PATHS.assignments),
    fetchText(WORKER_PATH)
  ]);
  assertFieldDataText(casesText, "reports/latest/cases.jsonl");
  assertFieldDataText(assignmentsText, "reports/latest/field_assignment_candidates.jsonl");
  assertFieldDataText(workersText, "fixtures/field_workers.json");
  return {
    cases: parseJsonLines(casesText, "cases.jsonl"),
    assignments: parseJsonLines(assignmentsText, "field_assignment_candidates.jsonl"),
    workers: parseWorkerRows(workersText)
  };
}

export function toSafeWorker(row) {
  return {
    worker_id: row.worker_id || "",
    display_name_safe: row.display_name_safe || "Response team",
    authorized_zone_ids: safeList(row.authorized_zone_ids),
    skills: safeList(row.skills),
    current_status: row.current_status || "unknown",
    capacity_active_cases: Number(row.capacity_active_cases || 0),
    current_active_cases: Number(row.current_active_cases || 0),
    transport: row.transport || "not listed"
  };
}

export function findWorker(workers, workerId) {
  const selected = (workerId || "").trim();
  if (!selected) return null;
  return workers.find((worker) => worker.worker_id === selected) || null;
}

export function authorizedFieldCases(cases, assignments, worker) {
  if (!worker) return [];
  const authorizedZones = new Set(worker.authorized_zone_ids);
  const workerAssignments = assignments.filter((row) => assignmentWorkerId(row) === worker.worker_id);
  const byCaseId = new Map(workerAssignments.map((row) => [row.case_id, row]));
  return cases
    .filter((row) => byCaseId.has(row.case_id))
    .filter((row) => row.operation_zone_id && row.operation_zone_id !== "unknown")
    .filter((row) => authorizedZones.has(row.operation_zone_id))
    .map((row) => toWorkerSafeCase(row, byCaseId.get(row.case_id)))
    .sort(compareFieldCases);
}

export function toWorkerSafeCase(row, assignment = {}) {
  const safe = {
    case_id: row.case_id || "unknown-case",
    safe_summary: row.safe_summary || "No safe summary provided.",
    urgency: row.urgency || "REVIEW",
    need_type: row.need_type || "unknown",
    people_count: row.people_count ?? null,
    vulnerable_flags: safeList(row.vulnerable_flags),
    operation_zone_id: row.operation_zone_id || "unknown",
    location_clue: row.location_clue || "location unclear",
    geo_confidence: row.geo_confidence || "unknown",
    coordinator_instruction: "Pending coordinator instruction.",
    assignment_status: operatorStatusLabel(assignment.assignment_status || "suggested_not_dispatched")
  };
  return Object.fromEntries(FIELD_CASE_ALLOWLIST.map((key) => [key, safe[key]]));
}

export function createStatusAuditEvent({ workerId, caseId, newStatus, syncState = "pending_sync" }) {
  return {
    event_id: `evt-demo-${stableEventSuffix(workerId, caseId, newStatus)}`,
    created_at: new Date().toISOString(),
    actor_worker_id: workerId,
    case_id: caseId,
    event_type: "status_update",
    new_status: newStatus,
    source: "field_app",
    sync_state: syncState
  };
}

export function createContactAuditEvent({ workerId, caseId }) {
  return {
    event_id: `evt-contact-${stableEventSuffix(workerId, caseId, "reliefqueue_contact")}`,
    created_at: new Date().toISOString(),
    actor_worker_id: workerId,
    case_id: caseId,
    event_type: "contact_attempt_created",
    contact_mode: "reliefqueue_contact",
    private_number_revealed: false
  };
}

export function renderedFieldTextHasForbiddenContent(text) {
  const privateKeys = [...PRIVATE_CASE_KEYS].filter((key) => text.includes(key));
  const phones = text.match(/(?:\+\d{1,3}\s*)?\d{5}[\s-]\d{5}|\+\d{1,3}\d{8,12}/g) || [];
  return { privateKeys, phones };
}


export function parseWorkerRows(text) {
  try {
    const rows = JSON.parse(text);
    if (!Array.isArray(rows)) {
      throw new Error("worker fixture must be a JSON array");
    }
    return rows.map(toSafeWorker);
  } catch (error) {
    throw new Error(`Unable to read fixtures/field_workers.json. Run make run-demo-local, then restart make dashboard-dev. ${error.message}`);
  }
}

function assertFieldDataText(text, label) {
  const trimmed = String(text || "").trimStart().toLowerCase();
  if (trimmed.startsWith("<!doctype") || trimmed.startsWith("<html")) {
    throw new Error(`${label} was served as dashboard HTML instead of data. Run make run-demo-local, then restart make dashboard-dev.`);
  }
}

function assignmentWorkerId(row) {
  return row.candidate_worker_id || row.worker_id || "";
}

function compareFieldCases(a, b) {
  const priority = { RED: 0, AMBER: 1, REVIEW: 2, GREEN: 3 };
  return (priority[a.urgency] ?? 4) - (priority[b.urgency] ?? 4) || a.case_id.localeCompare(b.case_id);
}

function safeList(value) {
  return Array.isArray(value) ? value.filter((item) => item !== null && item !== undefined) : [];
}

function stableEventSuffix(...parts) {
  let hash = 0;
  for (const char of parts.join("|")) {
    hash = (hash * 31 + char.charCodeAt(0)) % 1000000;
  }
  return String(hash).padStart(6, "0");
}
