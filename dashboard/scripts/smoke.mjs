import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  FORBIDDEN_WORDING,
  assignmentsForCase,
  filterCases,
  groupDuplicateCases,
  loadDashboardSourceManifest,
  loadReportBundle,
  operatorStatusLabel,
  renderedTextHasForbiddenContent,
  selectedVisibleCaseId,
  textHasInternalOperatorLabels
} from "../src/reportData.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(dashboardRoot, "..");
const previewUrl = "http://127.0.0.1:4173/dashboard";

const checks = [];

function check(name, condition, detail = "") {
  if (!condition) {
    throw new Error(`${name} failed${detail ? `: ${detail}` : ""}`);
  }
  checks.push(name);
}

async function fetchTextFromPreview(urlPath) {
  const response = await fetch(`http://127.0.0.1:4173${urlPath}`);
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
  throw new Error(`dashboard route did not load from preview: ${lastError}`);
}

async function main() {
  const distIndex = path.resolve(dashboardRoot, "dist", "index.html");
  await fs.access(distIndex).catch(() => {
    throw new Error("dashboard/dist/index.html missing. Run make dashboard-build first.");
  });

  const preview = spawn(
    "npm",
    ["run", "preview", "--", "--host", "127.0.0.1", "--port", "4173"],
    {
      cwd: dashboardRoot,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"]
    }
  );

  try {
    const routeHtml = await waitForPreview();
    check("dashboard route loads", routeHtml.includes("root"));

    const manifest = await loadDashboardSourceManifest(fetchTextFromPreview);
    check("dashboard source manifest loads", manifest.sources.length > 0);
    check(
      "dashboard source selector has current source",
      manifest.sources.some((source) => source.id === manifest.currentSourceId),
      manifest.currentSourceId
    );

    for (const source of manifest.sources) {
      const sourceBundle = await loadReportBundle(fetchTextFromPreview, source.id);
      check(`data source loads: ${source.id}`, Number(sourceBundle.summary.case_count) === sourceBundle.cases.length);
    }

    const bundle = await loadReportBundle(fetchTextFromPreview, manifest.currentSourceId);
    check("summary count appears", Number(bundle.summary.case_count) === bundle.cases.length);
    check("RED filter works", filterCases(bundle.cases, "RED", "").every((row) => row.urgency === "RED"));
    check(
      "missing-info filter works",
      filterCases(bundle.cases, "Missing Info", "").some((row) => row.missing_fields.length > 0)
    );
    check("duplicate cluster appears when present", groupDuplicateCases(bundle.cases).length > 0);
    check("zone workload view appears", bundle.zones.length > 0 && bundle.zones[0].case_count >= 0);
    check("assignment suggestion appears", bundle.assignments.length > 0);

    const firstAssignedCase = bundle.assignments[0].case_id;
    check(
      "assignment detail joins by case id",
      assignmentsForCase(bundle.assignments, firstAssignedCase).length > 0
    );
    check(
      "internal assignment status is operator friendly",
      bundle.assignments.every((row) => !String(row.assignment_status).includes("suggested_not_dispatched"))
    );
    check(
      "operator status label maps internal status",
      operatorStatusLabel("suggested_not_dispatched") === "Suggested — awaiting coordinator approval"
    );

    const allFirstCase = bundle.cases[0]?.case_id || "";
    const redSelection = selectedVisibleCaseId(bundle.cases, "RED", "", allFirstCase);
    const redCase = bundle.cases.find((row) => row.case_id === redSelection);
    check("filter change resets selected detail", !redCase || redCase.urgency === "RED");
    check(
      "empty filter returns no selected detail",
      selectedVisibleCaseId(bundle.cases, "RED", "case-id-that-does-not-exist", allFirstCase) === ""
    );

    const safeRenderText = JSON.stringify({
      summary: bundle.summary,
      cases: bundle.cases,
      zones: bundle.zones,
      assignments: bundle.assignments,
      validation: bundle.validationMarkdown
    });
    const operatorRenderText = JSON.stringify({
      summaryCards: {
        case_count: bundle.summary.case_count,
        missing_info_count: bundle.summary.missing_info_count,
        duplicate_cluster_count: bundle.summary.duplicate_cluster_count,
        assignment_ready_count: bundle.summary.assignment_ready_count
      },
      cases: bundle.cases,
      zones: bundle.zones,
      assignments: bundle.assignments,
      requiredLabels: [
        "Suggestion only. A coordinator approves field action.",
        "possible duplicate",
        "Suggested — awaiting coordinator approval",
        "Review workspace",
        "Show raw validation details"
      ]
    });
    const forbidden = renderedTextHasForbiddenContent(safeRenderText);
    check("raw_text_private is not rendered", forbidden.privateKeys.length === 0, forbidden.privateKeys.join(", "));
    check("phone-like private values are not rendered", forbidden.phones.length === 0, forbidden.phones.join(", "));
    check("forbidden wording is absent", forbidden.wording.length === 0, forbidden.wording.join(", "));
    check(
      "internal operator labels are absent from visible UI text",
      textHasInternalOperatorLabels(operatorRenderText).length === 0,
      textHasInternalOperatorLabels(operatorRenderText).join(", ")
    );
    for (const phrase of FORBIDDEN_WORDING) {
      check(`forbidden phrase absent: ${phrase}`, !safeRenderText.toLowerCase().includes(phrase.toLowerCase()));
    }

    const mainSource = await fs.readFile(path.resolve(dashboardRoot, "src", "main.jsx"), "utf-8");
    check("validation report is collapsed by default", mainSource.includes('<details className="validation-details">'));
    check("dashboard source selector is present", mainSource.includes("DashboardSourceSelector"));
    check("command center portal is present", mainSource.includes("CommandCenterPortal"));
    check("AI settings controls are present", mainSource.includes("Test interaction") && mainSource.includes("Rollback"));

    const outputPath = path.resolve(repoRoot, "reports", "latest", "dashboard-smoke-preview.html");
    await fs.writeFile(
      outputPath,
      `<!doctype html><meta charset="utf-8"><title>ReliefQueue Dashboard Smoke</title><pre>${escapeHtml(
        checks.join("\n")
      )}</pre>\n`,
      "utf-8"
    );

    console.log(`dashboard smoke passed (${checks.length} checks)`);
    console.log(`preview artifact: ${path.relative(repoRoot, outputPath)}`);
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

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (char) => {
    return {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    }[char];
  });
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
