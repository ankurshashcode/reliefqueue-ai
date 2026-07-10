export const DASHBOARD_DATA_SOURCES = [
  {
    id: "latest",
    label: "Latest local demo",
    description: "Fresh output from make run-demo-local",
    runCommand: "make run-demo-local",
    basePath: "/reports/latest"
  },
  {
    id: "batch-100",
    label: "Batch demo: 100 cases",
    description: "Output from make run-demo-batch-100",
    runCommand: "make run-demo-batch-100",
    basePath: "/reports/batch-100/latest"
  },
  {
    id: "batch-500",
    label: "Batch demo: 500 cases",
    description: "Output from make run-demo-batch-500",
    runCommand: "make run-demo-batch-500",
    basePath: "/reports/batch-500/latest"
  },
  {
    id: "batch-5000",
    label: "Batch demo: 5,000 cases",
    description: "Output from make run-demo-batch-5000",
    runCommand: "make run-demo-batch-5000",
    basePath: "/reports/batch-5000/latest"
  }
];

export const DEFAULT_DATA_SOURCE_ID = "latest";
export const DASHBOARD_SOURCE_MANIFEST_PATH = "/reports/dashboard_sources.json";

export const REPORT_PATHS = reportPathsForSource(DEFAULT_DATA_SOURCE_ID);

export const FILTERS = [
  "All",
  "RED",
  "AMBER",
  "GREEN",
  "REVIEW",
  "Missing Info",
  "Possible Duplicates",
  "Not Assignment Ready"
];

export const FORBIDDEN_WORDING = [
  "auto-dispatched",
  "confirmed rescued",
  "confirmed safe",
  "guaranteed location",
  "AI rescued the person",
  "AI verified the emergency",
  "worker definitely reached victim"
];

export const INTERNAL_OPERATOR_LABELS = ["suggested_not_dispatched"];

export const OPERATOR_STATUS_LABELS = {
  suggested_not_dispatched: "Suggested — awaiting coordinator approval",
  pending_sync: "Saved locally — not synced yet",
  synced_review: "Synced for review",
  local_demo_only: "Local only",
  status_update: "Status update",
  contact_attempt_created: "Contact attempt",
  accepted: "Accepted",
  on_the_way: "On the way",
  reached_area: "Reached area",
  unable_to_locate: "Unable to locate",
  needs_more_support: "Needs more support",
  completed_reported: "Completed, reported"
};

const PRIVATE_KEYS = new Set([
  "raw_text_private",
  "reporter_name_private_optional",
  "reporter_phone_private_optional",
  "media_note_private_optional"
]);

export function parseJsonLines(text, label) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      try {
        return JSON.parse(line);
      } catch (error) {
        throw new Error(`${label} line ${index + 1} is not valid JSON.`);
      }
    });
}

export function parseCsv(text) {
  const rows = text.trim().split(/\r?\n/);
  if (rows.length < 2) return [];
  const headers = splitCsvLine(rows[0]);
  return rows.slice(1).map((row) => {
    const values = splitCsvLine(row);
    return Object.fromEntries(headers.map((header, index) => [header, values[index] || ""]));
  });
}

function splitCsvLine(line) {
  const values = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === '"' && line[index + 1] === '"') {
      value += '"';
      index += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      values.push(value);
      value = "";
    } else {
      value += char;
    }
  }
  values.push(value);
  return values;
}

export function dataSourceById(sourceId) {
  return DASHBOARD_DATA_SOURCES.find((source) => source.id === sourceId) || DASHBOARD_DATA_SOURCES[0];
}

export function reportPathsForSource(sourceId) {
  const source = dataSourceById(sourceId);
  return {
    summary: `${source.basePath}/summary.json`,
    cases: `${source.basePath}/cases.jsonl`,
    zones: `${source.basePath}/zone_summary.csv`,
    assignments: `${source.basePath}/field_assignment_candidates.jsonl`,
    validation: `${source.basePath}/validation.md`
  };
}

export async function loadDashboardSourceManifest(fetchText) {
  try {
    const manifest = JSON.parse(await fetchText(DASHBOARD_SOURCE_MANIFEST_PATH));
    const knownIds = new Set(DASHBOARD_DATA_SOURCES.map((source) => source.id));
    const sources = Array.isArray(manifest.sources)
      ? manifest.sources.filter((source) => knownIds.has(source.id))
      : [];
    if (sources.length > 0) {
      return {
        currentSourceId: knownIds.has(manifest.current_source) ? manifest.current_source : sources[0].id,
        sources
      };
    }
  } catch {
    // Older prepared dashboards only served reports/latest; keep that path usable.
  }
  return { currentSourceId: DEFAULT_DATA_SOURCE_ID, sources: [dataSourceById(DEFAULT_DATA_SOURCE_ID)] };
}

export async function loadReportBundle(fetchText, sourceId = DEFAULT_DATA_SOURCE_ID) {
  const source = dataSourceById(sourceId);
  const paths = reportPathsForSource(source.id);
  const texts = {};
  for (const [key, path] of Object.entries(paths)) {
    try {
      texts[key] = await fetchText(path);
    } catch (error) {
      const missing = error?.status === 404 || /not found|ENOENT/i.test(String(error?.message || error));
      throw new Error(
        missing
          ? `Missing ${path}. Run make run-demo-local first.`
          : `Could not load ${path}: ${error.message || error}`
      );
    }
  }

  try {
    const summary = JSON.parse(texts.summary);
    const cases = parseJsonLines(texts.cases, "cases.jsonl").map(toSafeCase);
    const assignments = parseJsonLines(texts.assignments, "field_assignment_candidates.jsonl").map(
      toSafeAssignment
    );
    const zones = parseCsv(texts.zones).map(toSafeZone);
    return {
      summary,
      cases,
      zones,
      assignments,
      source,
      validationMarkdown: texts.validation
    };
  } catch (error) {
    throw new Error(`Invalid report data. ${error.message}`);
  }
}

export function toSafeCase(row) {
  const safe = {
    case_id: row.case_id || "unknown-case",
    safe_summary: row.safe_summary || "No safe summary provided.",
    urgency: row.urgency || "REVIEW",
    urgency_reasons: safeList(row.urgency_reasons),
    need_type: row.need_type || "unknown",
    people_count: row.people_count ?? null,
    vulnerable_flags: safeList(row.vulnerable_flags),
    location_clue: row.location_clue || "location unclear",
    geo_scope_type: row.geo_scope_type || "unknown",
    geo_confidence: row.geo_confidence || "unknown",
    operation_zone_id: row.operation_zone_id || "unknown",
    missing_fields: safeList(row.missing_fields),
    duplicate_cluster_id: row.duplicate_cluster_id || "",
    duplicate_cluster_size: Number(row.duplicate_cluster_size || 0),
    assignment_ready: Boolean(row.assignment_ready),
    required_skills: safeList(row.required_skills),
    suggested_reply_draft: row.suggested_reply_draft || "",
    human_review_required: Boolean(row.human_review_required),
    source_channel: row.source_channel || "unknown"
  };
  for (const key of PRIVATE_KEYS) {
    delete safe[key];
  }
  return safe;
}

export function toSafeAssignment(row) {
  return {
    case_id: row.case_id || "unknown-case",
    candidate_display_name_safe:
      row.candidate_display_name_safe || row.display_name_safe || "Unnamed response team",
    required_skills: safeList(row.required_skills),
    match_reasons: safeList(row.match_reasons || row.reasons),
    constraint_warnings: safeList(row.constraint_warnings),
    rank: Number(row.rank || 0),
    operation_zone_id: row.operation_zone_id || "unknown",
    assignment_status: operatorStatusLabel(row.assignment_status || "suggested_not_dispatched")
  };
}

export function operatorStatusLabel(status) {
  return OPERATOR_STATUS_LABELS[status] || String(status || "Needs coordinator review").replaceAll("_", " ");
}

export function toSafeZone(row) {
  return {
    operation_zone_id: row.operation_zone_id || "unknown",
    zone_name: row.zone_name || "Unknown / untagged",
    case_count: toNumber(row.case_count),
    red_count: toNumber(row.red_count),
    amber_count: toNumber(row.amber_count),
    green_count: toNumber(row.green_count),
    review_count: toNumber(row.review_count),
    missing_location_count: toNumber(row.missing_location_count),
    assignment_ready_count: toNumber(row.assignment_ready_count),
    assignment_candidate_count: toNumber(row.assignment_candidate_count)
  };
}

export function selectedVisibleCaseId(cases, activeFilter, search, currentCaseId) {
  const visibleCases = filterCases(cases, activeFilter, search);
  if (visibleCases.some((row) => row.case_id === currentCaseId)) return currentCaseId;
  return visibleCases[0]?.case_id || "";
}

export function filterCases(cases, activeFilter, search) {
  const query = (search || "").trim().toLowerCase();
  return cases.filter((row) => {
    const filterMatch =
      activeFilter === "All" ||
      row.urgency === activeFilter ||
      (activeFilter === "Missing Info" && isMissingInfo(row)) ||
      (activeFilter === "Possible Duplicates" && Boolean(row.duplicate_cluster_id)) ||
      (activeFilter === "Not Assignment Ready" && !row.assignment_ready);
    if (!filterMatch) return false;
    if (!query) return true;
    return [row.case_id, row.operation_zone_id, row.need_type].some((value) =>
      String(value || "").toLowerCase().includes(query)
    );
  });
}

export function isMissingInfo(row) {
  return (
    row.missing_fields.length > 0 ||
    !row.assignment_ready ||
    row.geo_confidence === "low" ||
    row.geo_confidence === "unknown"
  );
}

export function groupDuplicateCases(cases) {
  const groups = new Map();
  for (const row of cases) {
    if (!row.duplicate_cluster_id) continue;
    if (!groups.has(row.duplicate_cluster_id)) groups.set(row.duplicate_cluster_id, []);
    groups.get(row.duplicate_cluster_id).push(row);
  }
  return [...groups.entries()].map(([clusterId, rows]) => ({
    clusterId,
    rows,
    size: Math.max(...rows.map((row) => row.duplicate_cluster_size || rows.length))
  }));
}

export function assignmentsForCase(assignments, caseId) {
  return assignments
    .filter((row) => row.case_id === caseId)
    .sort((a, b) => a.rank - b.rank)
    .slice(0, 3);
}

export function renderedTextHasForbiddenContent(text) {
  const lower = text.toLowerCase();
  const wording = FORBIDDEN_WORDING.filter((phrase) => lower.includes(phrase.toLowerCase()));
  const phones = text.match(/(?:\+\d{1,3}\s*)?\d{5}[\s-]\d{5}|\+\d{1,3}\d{8,12}/g) || [];
  const privateKeys = [...PRIVATE_KEYS].filter((key) => text.includes(key));
  return { wording, phones, privateKeys };
}

export function textHasInternalOperatorLabels(text) {
  const lower = text.toLowerCase();
  return INTERNAL_OPERATOR_LABELS.filter((phrase) => lower.includes(phrase.toLowerCase()));
}

function safeList(value) {
  return Array.isArray(value) ? value.filter((item) => item !== null && item !== undefined) : [];
}

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
