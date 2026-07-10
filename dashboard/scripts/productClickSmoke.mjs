import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import net from "node:net";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(dashboardRoot, "..");
const mode = process.argv[2] || "product-complete";
let appOrigin = "";
let apiOrigin = "";
const evidenceDir = path.resolve(repoRoot, "reports", "product-click-smoke", "latest");

const filesByMode = {
  command: "command-center.json",
  field: "field-app.json",
  local: "local-coordinator.json",
  "product-complete": "product-complete.json"
};

const requiredRouteLiterals = [
  "/dashboard?source=latest",
  "/field/my-cases?worker_id=worker-alpha-boat",
  "/local-coordinator?source=latest"
];

const surfaceTitles = {
  "Command Center": "Command Center",
  "Field Worker": "ReliefQueue Field",
  "Local Coordinator": "Local Coordinator",
  "Classic/debug only": "Classic Dashboard Debug View"
};

const modeSurfaces = {
  command: new Set(["Command Center"]),
  field: new Set(["Field Worker"]),
  local: new Set(["Local Coordinator"]),
  "product-complete": new Set(["Command Center", "Field Worker", "Local Coordinator", "Classic/debug only"])
};

const apiEndpoints = {
  "command.assign_or_reassign_worker": "/api/product/command/assign",
  "command.set_case_in_progress": "/api/product/command/status",
  "command.queue_local_message": "/api/product/command/message",
  "command.run_deterministic_drill": "/api/product/command/drill",
  "command.request_review_required_ai_advisory": "/api/product/command/ai-advisory",
  "field.acknowledge_assignment": "/api/product/field/action",
  "field.start_or_accept_work": "/api/product/field/action",
  "field.add_note": "/api/product/field/action",
  "field.add_evidence_metadata": "/api/product/field/action",
  "field.mark_complete_or_delivered": "/api/product/field/action",
  "field.mark_blocked_or_needs_help": "/api/product/field/action",
  "field.sync_pending_actions": "/api/product/field/sync",
  "local.update_scenario_profile": "/api/product/local/scenario",
  "local.update_operation_zone": "/api/product/local/scenario",
  "local.update_relief_hub": "/api/product/local/scenario",
  "local.update_reachable_radius": "/api/product/local/scenario",
  "local.update_priority_needs": "/api/product/local/scenario",
  "local.update_blocked_safe_areas": "/api/product/local/scenario"
};

function statusFor(action) {
  if (action.provider_status === "paid_disabled") return "PAID_DISABLED_PASS";
  if (action.provider_status === "informational") return "INFORMATIONAL_PASS";
  if (action.provider_status === "local_mock") return "LOCAL_MOCK_PASS";
  if (action.provider_status === "navigation") return "NAVIGATION_PASS";
  if (action.provider_status === "panel") return "PANEL_PASS";
  return "PASS";
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function getFreePort(host = "127.0.0.1") {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, host, () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close(() => {
        if (!port) {
          reject(new Error("failed to allocate a free local port"));
          return;
        }
        resolve(port);
      });
    });
  });
}

async function selectSmokePorts() {
  const host = "127.0.0.1";
  const apiPort = Number(process.env.RELIEFQUEUE_CLICK_SMOKE_API_PORT || await getFreePort(host));
  let appPort = Number(process.env.RELIEFQUEUE_CLICK_SMOKE_APP_PORT || await getFreePort(host));
  if (appPort === apiPort && !process.env.RELIEFQUEUE_CLICK_SMOKE_APP_PORT) {
    appPort = Number(await getFreePort(host));
  }
  if (!Number.isInteger(apiPort) || apiPort <= 0 || !Number.isInteger(appPort) || appPort <= 0 || appPort === apiPort) {
    throw new Error(`invalid click-smoke port selection: api=${apiPort} app=${appPort}`);
  }
  return { host, apiPort, appPort };
}

async function waitForHttp(url, label) {
  const started = Date.now();
  let lastError = "";
  while (Date.now() - started < 30000) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = `${response.status} ${response.statusText}`;
    } catch (error) {
      lastError = error.message;
    }
    await sleep(300);
  }
  throw new Error(`${label} did not become ready: ${lastError}`);
}

async function textOrEmpty(page, selector) {
  const locator = page.locator(selector).first();
  if (!(await locator.count())) return "";
  return normalize(await locator.innerText({ timeout: 3000 }));
}

function normalize(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

async function preparePageForAction(page, action) {
  const commandDetailActions = new Set([
    "command.assign_or_reassign_worker",
    "command.set_case_in_progress",
    "command.queue_local_message",
    "command.request_review_required_ai_advisory",
    "command.paid_sms_disabled"
  ]);
  if (commandDetailActions.has(action.action_id)) {
    await page.waitForSelector('[data-action-id="command.open_case_detail"]', { timeout: 10000 });
    await page.locator('[data-action-id="command.open_case_detail"]').first().click();
    await page.waitForSelector('[data-result-id="command.case-detail"]', { timeout: 10000 });
    return;
  }
  if (action.surface !== "Field Worker") return;
  if (!action.route.includes("/field/my-cases") || action.action_id === "field.open_case_detail") return;
  await page.waitForSelector('[data-action-id="field.open_case_detail"]', { timeout: 10000 });
  await page.locator('[data-action-id="field.open_case_detail"]').first().click();
  await page.waitForSelector('[data-result-id="field.detail"]', { timeout: 10000 });
}

async function clickLocatorForAction(page, action) {
  const locator = page.locator(action.selector);
  const count = await locator.count();
  if (!count) throw new Error(`selector absent: ${action.selector}`);
  if (action.action_id === "command.open_case_detail" && count > 1) {
    await locator.nth(1).click();
    return;
  }
  await locator.first().click();
}

async function runAction(page, action, observedApiCalls) {
  console.log(`ACTION_START action_id=${action.action_id} route=${action.route}`);
  await page.goto(`${appOrigin}${action.route}`, { waitUntil: "networkidle" });
  try {
    await page.waitForSelector("main", { timeout: 10000 });
  } catch (error) {
    const diagnostics = await page.evaluate(() => {
      const root = document.getElementById("root");
      const runtimeError = document.querySelector('[data-testid="native-runtime-error"]');
      return {
        href: window.location.href,
        pathname: window.location.pathname,
        main_count: document.querySelectorAll("main").length,
        root_child_count: root?.children.length || 0,
        root_text: (root?.textContent || "").replace(/\s+/g, " ").trim().slice(0, 1000),
        runtime_error: (runtimeError?.textContent || "").replace(/\s+/g, " ").trim().slice(0, 1000)
      };
    }).catch((diagnosticError) => ({ diagnostic_error: String(diagnosticError) }));
    console.error(`ACTION_MAIN_DIAGNOSTICS action_id=${action.action_id} ${JSON.stringify(diagnostics)}`);
    throw error;
  }
  await preparePageForAction(page, action);

  await page.waitForSelector(action.selector, { state: "attached", timeout: 10000 }).catch(() => {});
  const locator = page.locator(action.selector).first();
  const domSelectorFound = (await locator.count()) > 0;
  if (!domSelectorFound) throw new Error(`missing selector ${action.action_id}`);
  const beforeText = await textOrEmpty(page, action.result_selector) || normalize(await page.locator("main").innerText());
  let clicked = false;
  let disabled = false;
  let paidLabel = "";

  if (action.provider_status === "paid_disabled") {
    disabled = await locator.isDisabled().catch(() => false);
    paidLabel = normalize(await locator.innerText());
  } else if (action.provider_status !== "informational") {
    await clickLocatorForAction(page, action);
    clicked = true;
  }

  await page.waitForSelector(action.result_selector, { timeout: 10000 });
  await page.waitForTimeout(350);
  const afterText = await textOrEmpty(page, action.result_selector);
  const observedVisibleResult = afterText || normalize(await page.locator("main").innerText());
  const endpoint = apiEndpoints[action.action_id] || "";
  const apiCallObserved = endpoint ? observedApiCalls.some((url) => url.includes(endpoint)) : false;
  const visibleAssertionPassed = action.provider_status === "paid_disabled"
    ? disabled && /paid|disabled|not configured|external/i.test(`${paidLabel} ${observedVisibleResult}`)
    : action.provider_status === "informational"
      ? observedVisibleResult.length > 12
      : observedVisibleResult.length > 12 && (beforeText !== afterText || ["panel", "navigation"].includes(action.provider_status));

  if (endpoint && !apiCallObserved) throw new Error(`missing observed API call ${action.action_id} ${endpoint}`);
  if (!visibleAssertionPassed) throw new Error(`visible result did not change/pass for ${action.action_id}`);

  return {
    action_id: action.action_id,
    surface: action.surface,
    route: action.route,
    status: statusFor(action),
    selector: action.selector,
    result_selector: action.result_selector,
    served_browser_route: true,
    dom_selector_found: domSelectorFound,
    clicked,
    result_selector_found: (await page.locator(action.result_selector).count()) > 0,
    visible_assertion_passed: visibleAssertionPassed,
    before_text: beforeText,
    after_text: afterText,
    observed_visible_result: observedVisibleResult,
    api_call_observed: endpoint ? apiCallObserved : false,
    api_endpoint: endpoint,
    disabled,
    paid_disabled_label_visible: action.provider_status === "paid_disabled" ? /paid|disabled|not configured|external/i.test(`${paidLabel} ${observedVisibleResult}`) : false,
    paid_disabled_label: paidLabel
  };
}

async function checkFieldReloadPersistence(page) {
  await page.goto(`${appOrigin}/field/my-cases?worker_id=worker-alpha-boat`, { waitUntil: "networkidle" });
  await page.locator('[data-action-id="field.open_case_detail"]').first().click();
  await page.waitForSelector('[data-result-id="field.detail"]', { timeout: 5000 });
  await page.locator('[data-action-id="field.add_note"]').first().click();
  await page.waitForSelector('[data-result-id="field.outbox"]', { timeout: 5000 });
  const beforeReload = await textOrEmpty(page, '[data-result-id="field.outbox"]');
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector('[data-result-id="field.outbox"]', { timeout: 5000 });
  const afterReload = await textOrEmpty(page, '[data-result-id="field.outbox"]');
  const stored = await page.evaluate(() => {
    const raw = window.localStorage.getItem("reliefqueue.fieldQueue.v1");
    return raw ? JSON.parse(raw) : null;
  });
  const persisted = Boolean(stored?.schema === 1 && stored.entries?.some((entry) => entry.state === "pending"));
  if (!persisted || !/localStorage|schema|pending/i.test(afterReload)) {
    throw new Error("field offline queue did not persist across browser reload");
  }
  return {
    status: "PASS",
    storage: "localStorage",
    schema: stored.schema,
    pending_entries: stored.entries.filter((entry) => entry.state === "pending").length,
    before_text: beforeReload,
    after_text: afterReload,
    reload_persistence_proven: true
  };
}

async function routeCheck(page, route, surface) {
  await page.goto(`${appOrigin}${route}`, { waitUntil: "networkidle" });
  const title = surfaceTitles[surface];
  const titleLocator = page.getByText(title, { exact: false }).first();
  await titleLocator.waitFor({ timeout: 10000 });
  return {
    route,
    loaded: true,
    expected_surface_visible: await titleLocator.isVisible(),
    observed_surface_title: normalize(await titleLocator.innerText())
  };
}

async function main() {
  if (!filesByMode[mode]) throw new Error(`unknown click smoke mode: ${mode}`);
  const actionMap = JSON.parse(await fs.readFile(path.resolve(repoRoot, "acceptance", "product_action_map.json"), "utf-8"));
  for (const route of requiredRouteLiterals) {
    if (!actionMap.actions.some((action) => action.route === route)) throw new Error(`missing required route in action map: ${route}`);
  }
  const actions = actionMap.actions.filter((action) => modeSurfaces[mode].has(action.surface));
  const { host, apiPort, appPort } = await selectSmokePorts();
  apiOrigin = `http://${host}:${apiPort}`;
  appOrigin = `http://${host}:${appPort}`;

  console.log(`product click smoke ports: api=${apiPort} app=${appPort}`);

  const api = spawn("python3", ["-m", "reliefqueue.product_api", "serve", "--host", host, "--port", String(apiPort)], {
    cwd: repoRoot,
    env: { ...process.env, PYTHONPATH: "src" },
    detached: true,
    stdio: ["ignore", "pipe", "pipe"]
  });
  const vite = spawn("npm", ["run", "dev", "--", "--host", host, "--port", String(appPort), "--strictPort"], {
    cwd: dashboardRoot,
    env: { ...process.env, RELIEFQUEUE_PRODUCT_API_TARGET: apiOrigin },
    detached: true,
    stdio: ["ignore", "pipe", "pipe"]
  });

  const browser = await chromium.launch({ headless: true });
  try {
    await waitForHttp(`${apiOrigin}/api/product/command/overview`, "product API");
    await waitForHttp(`${appOrigin}/dashboard?source=latest`, "Vite app");
    const page = await browser.newPage({ viewport: { width: 1365, height: 950 } });
    const observedApiCalls = [];
    page.on("request", (request) => {
      const url = request.url();
      if (url.includes("/api/product/")) observedApiCalls.push(url);
    });

    const routeChecks = [];
    for (const [surface, route] of new Map(actions.map((action) => [action.surface, action.route]))) {
      routeChecks.push(await routeCheck(page, route, surface));
    }

    const entries = [];
    for (const action of actions) {
      entries.push(await runAction(page, action, observedApiCalls));
    }
    const fieldOfflineReloadPersistence = modeSurfaces[mode].has("Field Worker")
      ? await checkFieldReloadPersistence(page)
      : null;

    await fs.mkdir(evidenceDir, { recursive: true });
    const output = {
      status: "PASS",
      mode,
      runner: "Playwright Chromium real browser DOM click-through",
      automation: "playwright chromium browser",
      served_browser_route: true,
      route_checks: routeChecks,
      field_offline_reload_persistence: fieldOfflineReloadPersistence,
      actions: entries
    };
    const outputPath = path.resolve(evidenceDir, filesByMode[mode]);
    await fs.writeFile(outputPath, JSON.stringify(output, null, 2) + "\n", "utf-8");
    console.log(`${mode} click smoke PASS (${entries.length} actions)`);
    console.log(`evidence: ${path.relative(repoRoot, outputPath)}`);
  } finally {
    await browser.close().catch(() => {});
    for (const child of [vite, api]) {
      if (!child.killed && child.pid) {
        try {
          process.kill(-child.pid, "SIGTERM");
        } catch {
          child.kill("SIGTERM");
        }
      }
    }
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
