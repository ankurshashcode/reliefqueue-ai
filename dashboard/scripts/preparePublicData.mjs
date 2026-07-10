import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(dashboardRoot, "..");
const publicRoot = path.resolve(dashboardRoot, "public");

const DATA_SOURCES = [
  {
    id: "latest",
    label: "Latest local demo",
    description: "Fresh output from make run-demo-local",
    runCommand: "make run-demo-local",
    sourceDir: path.resolve(repoRoot, "reports", "latest"),
    publicDir: path.resolve(publicRoot, "reports", "latest")
  },
  {
    id: "batch-100",
    label: "Batch demo: 100 cases",
    description: "Output from make run-demo-batch-100",
    runCommand: "make run-demo-batch-100",
    sourceDir: path.resolve(repoRoot, "reports", "batch-100", "latest"),
    publicDir: path.resolve(publicRoot, "reports", "batch-100", "latest")
  },
  {
    id: "batch-500",
    label: "Batch demo: 500 cases",
    description: "Output from make run-demo-batch-500",
    runCommand: "make run-demo-batch-500",
    sourceDir: path.resolve(repoRoot, "reports", "batch-500", "latest"),
    publicDir: path.resolve(publicRoot, "reports", "batch-500", "latest")
  },
  {
    id: "batch-5000",
    label: "Batch demo: 5,000 cases",
    description: "Output from make run-demo-batch-5000",
    runCommand: "make run-demo-batch-5000",
    sourceDir: path.resolve(repoRoot, "reports", "batch-5000", "latest"),
    publicDir: path.resolve(publicRoot, "reports", "batch-5000", "latest")
  }
];

const requiredReportFiles = [
  "summary.json",
  "cases.jsonl",
  "zone_summary.csv",
  "field_assignment_candidates.jsonl",
  "validation.md"
];

const selectedSourceId = process.env.DASHBOARD_DATA_SOURCE || process.env.DATA_SOURCE || "latest";

async function exists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function copyDirectoryFiltered(source, destination) {
  await fs.rm(destination, { recursive: true, force: true });
  await fs.mkdir(destination, { recursive: true });
  const entries = await fs.readdir(source, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.name === "evidence") continue;
    const sourcePath = path.join(source, entry.name);
    const destinationPath = path.join(destination, entry.name);
    if (entry.isDirectory()) {
      await copyDirectoryFiltered(sourcePath, destinationPath);
    } else if (entry.isFile()) {
      await fs.copyFile(sourcePath, destinationPath);
    }
  }
}

function parseJsonLines(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function safeList(value) {
  return Array.isArray(value) ? value.filter((item) => item !== null && item !== undefined) : [];
}

function toBrowserSafeCase(row) {
  return {
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
}

async function rewriteServedCases(publicReportsDir) {
  const casesPath = path.resolve(publicReportsDir, "cases.jsonl");
  const rows = parseJsonLines(await fs.readFile(casesPath, "utf-8")).map(toBrowserSafeCase);
  await fs.writeFile(casesPath, rows.map((row) => JSON.stringify(row)).join("\n") + "\n", "utf-8");
}

async function sourceReadiness(source) {
  const missing = [];
  for (const name of requiredReportFiles) {
    const filePath = path.resolve(source.sourceDir, name);
    if (!(await exists(filePath))) missing.push(path.relative(repoRoot, filePath));
  }
  return { source, missing, ready: missing.length === 0 };
}

async function readCaseCount(source) {
  try {
    const summary = JSON.parse(await fs.readFile(path.resolve(source.sourceDir, "summary.json"), "utf-8"));
    return Number(summary.case_count ?? summary.total_cases ?? summary.input_count ?? 0);
  } catch {
    return 0;
  }
}

async function copyAvailableSource(source) {
  await copyDirectoryFiltered(source.sourceDir, source.publicDir);
  await rewriteServedCases(source.publicDir);
  return {
    id: source.id,
    label: source.label,
    description: source.description,
    runCommand: source.runCommand,
    caseCount: await readCaseCount(source)
  };
}

async function main() {
  const selectedSource = DATA_SOURCES.find((source) => source.id === selectedSourceId);
  if (!selectedSource) {
    throw new Error(
      `Unknown dashboard data source: ${selectedSourceId}. Use one of: ${DATA_SOURCES.map((source) => source.id).join(", ")}.`
    );
  }

  const readiness = await Promise.all(DATA_SOURCES.map(sourceReadiness));
  const selectedReadiness = readiness.find((item) => item.source.id === selectedSource.id);
  if (!selectedReadiness.ready) {
    throw new Error(
      `Missing dashboard data source ${selectedSource.id}: ${selectedReadiness.missing.join(", ")}. Run ${selectedSource.runCommand} first.`
    );
  }

  await fs.mkdir(publicRoot, { recursive: true });
  await fs.rm(path.resolve(publicRoot, "reports"), { recursive: true, force: true });
  await fs.mkdir(path.resolve(publicRoot, "reports"), { recursive: true });

  const availableSources = [];
  for (const item of readiness) {
    if (!item.ready) continue;
    availableSources.push(await copyAvailableSource(item.source));
  }

  await fs.writeFile(
    path.resolve(publicRoot, "reports", "dashboard_sources.json"),
    JSON.stringify(
      {
        current_source: selectedSource.id,
        sources: availableSources
      },
      null,
      2
    ) + "\n",
    "utf-8"
  );

  const workersSource = path.resolve(repoRoot, "fixtures", "field_workers.json");
  if (!(await exists(workersSource))) {
    throw new Error("Missing fixtures/field_workers.json. Run make validate-fixtures first.");
  }
  await fs.rm(path.resolve(publicRoot, "fixtures"), { recursive: true, force: true });
  await fs.mkdir(path.resolve(publicRoot, "fixtures"), { recursive: true });
  await fs.copyFile(workersSource, path.resolve(publicRoot, "fixtures", "field_workers.json"));

  console.log(
    `Prepared dashboard data source ${selectedSource.id}. Available sources: ${availableSources
      .map((source) => `${source.id} (${source.caseCount} cases)`)
      .join(", ")}.`
  );
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
