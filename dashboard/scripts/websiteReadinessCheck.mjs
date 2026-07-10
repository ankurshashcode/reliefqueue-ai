import fs from 'node:fs/promises';
import path from 'node:path';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(dashboardRoot, '..');
const evidenceDir = path.resolve(repoRoot, 'reports', 'website-readiness', 'latest');
const screenshotsDir = path.resolve(evidenceDir, 'screenshots');
const host = '127.0.0.1';
const bannedText = [/Product API unavailable/i, /automatic dispatch/i, /connection refused/i, /Address already in use/i];

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function norm(value) { return String(value || '').replace(/\s+/g, ' ').trim(); }
function slug(value) { return norm(value).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'root'; }
async function writeJson(name, payload) { await fs.writeFile(path.join(evidenceDir, name), JSON.stringify(payload, null, 2) + '\n'); }

async function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, host, () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close(() => port ? resolve(port) : reject(new Error('no free port')));
    });
  });
}

async function waitForHttp(url) {
  const started = Date.now();
  let last = '';
  while (Date.now() - started < 30000) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      last = `${response.status} ${response.statusText}`;
    } catch (error) { last = error.message; }
    await sleep(250);
  }
  throw new Error(`dev server not ready: ${last}`);
}

const routeChecks = [
  ['/', ['Operations Overview', 'Judge Demo Walkthrough', 'AI Heavy Lifting Summary']],
  ['/dashboard?source=latest', ['Operations Overview', 'Raw Intake', 'AI-Enriched Queue', 'Queue Pressure']],
  ['/dashboard/map', ['Mock GPS / Demo Data', 'Active Cases']],
  ['/dashboard/assignments', ['Task Assignment Suggestions', 'Coordinator approval required']],
  ['/dashboard/workload', ['Coordinator Workload', 'Suggest Rebalance']],
  ['/dashboard/field-sync', ['Field Sync', 'Outbox']],
  ['/dashboard/scenario', ['Scenario Settings', 'Priority Needs']],
  ['/dashboard/ai-control', ['Model Configuration', 'Gemma 4 Bonus Lane']],
  ['/dashboard/quality', ['Quality & Evidence Queue', 'Review Packet']],
  ['/dashboard/audit', ['Audit & Troubleshooting', 'Submission / Deployment Readiness']],
  ['/dashboard/intake', ['AI Intake Fusion', 'Raw Inbound Queue']],
  ['/dashboard/incident-links', ['Incident Linkage', 'Duplicate']],
  ['/dashboard/amd-impact', ['AMD GPU', 'Human Review', 'Batch Impact']],
  ['/dashboard/capability-map', ['Capability Map', 'API Base URL', 'Backend API']],
  ['/field/sign-in', ['Field Coordinator', 'Sign In']],
  ['/field/my-work', ['My Work Dashboard', 'Current Zone', 'New Relief Request']],
  ['/field/my-cases', ['Assigned Cases', 'RQ-1042']],
  ['/field/cases/RQ-1042', ['RQ-1042', 'Status', 'Add Note']],
  ['/field/cases/RQ-1042/status', ['Update Status', 'In Progress']],
  ['/field/cases/RQ-1042/note', ['Field Note', 'Save Note']],
  ['/field/new-request', ['New Relief Request', 'Need Type']],
  ['/field/outbox', ['Outbox', 'Pending Sync']],
  ['/field/sync-conflicts', ['Sync Conflict', 'Keep Mine']],
  ['/field/help', ['Network Help', 'Offline']]
];

async function pageDiagnostics(page) {
  return await page.evaluate(() => {
    const root = document.querySelector('#root');
    const scripts = Array.from(document.scripts).map(s => s.src || s.textContent?.slice(0, 80) || '');
    return {
      title: document.title,
      location: window.location.href,
      body_text_length: document.body?.innerText?.trim().length || 0,
      body_text_sample: (document.body?.innerText || '').trim().slice(0, 500),
      body_html_sample: (document.body?.innerHTML || '').slice(0, 1000),
      root_child_count: root?.childElementCount || 0,
      root_html_sample: root?.innerHTML?.slice(0, 1000) || '',
      scripts,
    };
  });
}


async function tailwindStyleProbe(page) {
  return await page.evaluate(() => {
    const existingProbe = document.querySelector('[data-testid="rq-static-tailwind-probe"]');
    const probe = existingProbe || document.createElement('div');
    if (!existingProbe) {
      probe.className = 'rq-static-tailwind-probe flex bg-slate-900 text-white p-4 rounded-xl gap-2';
      probe.textContent = 'rq-tailwind-style-probe';
      probe.style.position = 'fixed';
      probe.style.left = '-9999px';
      probe.style.top = '-9999px';
      document.body.appendChild(probe);
    }
    const style = window.getComputedStyle(probe);
    const result = {
      source: existingProbe ? 'static_rendered_probe' : 'dynamic_fallback_probe',
      className: probe.getAttribute('class') || '',
      display: style.display,
      backgroundColor: style.backgroundColor,
      color: style.color,
      paddingTop: style.paddingTop,
      borderTopLeftRadius: style.borderTopLeftRadius,
      gap: style.gap,
      tailwind_utilities_active:
        style.display === 'flex' &&
        style.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
        style.backgroundColor !== 'transparent' &&
        parseFloat(style.paddingTop || '0') >= 12 &&
        parseFloat(style.borderTopLeftRadius || '0') >= 8
    };
    if (!existingProbe) probe.remove();
    return result;
  });
}

async function inspectRoute(page, origin, route, markers, routeErrors) {
  await page.goto(`${origin}${route}`, { waitUntil: 'domcontentloaded' });
  let waitStatus = 'app_content_seen';
  try {
    await page.waitForFunction((expectedMarkers) => {
      const text = document.body?.innerText || '';
      if (text.includes('Native AI Studio app failed to render')) return true;
      if (document.querySelector('[data-testid="native-loading-shell"]')) return false;
      return text.trim().length > 50 && expectedMarkers.some((marker) => text.includes(marker));
    }, markers, { timeout: 20000 });
  } catch (error) {
    waitStatus = `timeout_waiting_for_app_content: ${error.message}`;
    routeErrors.push(`${route} ${waitStatus}`);
  }
  await page.waitForTimeout(250);
  const text = norm(await page.locator('body').innerText().catch(() => ''));
  const controls = await page.locator('button,a,select,input,textarea,[role="button"],[role="link"],[role="tab"],[role="combobox"]').count().catch(() => 0);
  const scroll = await page.evaluate(() => ({
    viewport_height: window.innerHeight,
    document_scroll_height: document.documentElement.scrollHeight,
    body_scroll_height: document.body.scrollHeight,
    has_vertical_scroll: document.documentElement.scrollHeight > window.innerHeight + 20 || document.body.scrollHeight > window.innerHeight + 20,
  })).catch(() => ({ viewport_height: 0, document_scroll_height: 0, body_scroll_height: 0, has_vertical_scroll: false }));
  const diagnostics = await pageDiagnostics(page).catch(error => ({ diagnostic_error: error.message }));
  const screenshotPath = `screenshots/route-${slug(route)}.png`;
  await page.screenshot({ path: path.join(evidenceDir, screenshotPath), fullPage: true }).catch(() => {});
  return { route, controls, text_length: text.length, visible_text_sample: text.slice(0, 500), screenshot_path: screenshotPath, waitStatus, diagnostics, ...scroll, text };
}

async function clickIfPresent(page, labelPattern) {
  const locator = page.getByText(labelPattern, { exact: false }).first();
  if (!(await locator.count())) return { label: String(labelPattern), status: 'not_found' };
  const before = norm(await page.locator('body').innerText()).slice(0, 800);
  await locator.click({ timeout: 5000 });
  await page.waitForTimeout(350);
  const after = norm(await page.locator('body').innerText()).slice(0, 800);
  return { label: String(labelPattern), status: before === after ? 'clicked_no_sample_change' : 'clicked_visible_change' };
}

async function visibleBlockingOverlay(page) {
  return await page.evaluate(() => {
    const centerX = Math.floor(window.innerWidth / 2);
    const centerY = Math.floor(window.innerHeight / 2);
    const element = document.elementFromPoint(centerX, centerY);
    const overlay = element?.closest?.('.fixed.inset-0, [role="dialog"]');
    if (!overlay) return null;
    const style = window.getComputedStyle(overlay);
    if (style.display === 'none' || style.visibility === 'hidden' || style.pointerEvents === 'none') return null;
    const text = overlay.textContent?.replace(/\s+/g, ' ').trim().slice(0, 240) || '';
    return {
      tag: overlay.tagName,
      role: overlay.getAttribute('role') || '',
      className: overlay.getAttribute('class') || '',
      text
    };
  });
}

async function closeIntentionalOverlay(page) {
  const overlay = await visibleBlockingOverlay(page);
  if (!overlay) return { status: 'no_overlay' };
  if (!/Judge Demo Walkthrough/.test(overlay.text)) {
    return { status: 'unexpected_overlay', overlay };
  }

  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  if (!(await page.getByRole('dialog', { name: /Judge Demo Walkthrough/i }).count().catch(() => 0))) {
    return { status: 'closed_with_escape', overlay };
  }

  const closeButton = page.getByRole('button', { name: /Close Judge Demo Walkthrough/i }).first();
  if (await closeButton.count()) {
    await closeButton.click({ timeout: 3000 });
    await page.waitForTimeout(200);
  }
  const stillOpen = await page.getByRole('dialog', { name: /Judge Demo Walkthrough/i }).count().catch(() => 0);
  return { status: stillOpen ? 'failed_to_close' : 'closed_with_button', overlay };
}

async function main() {
  await fs.rm(evidenceDir, { recursive: true, force: true });
  await fs.mkdir(screenshotsDir, { recursive: true });
  const appPort = await getFreePort();
  const origin = `http://${host}:${appPort}`;
  const server = spawn('npm', ['--prefix', dashboardRoot, 'run', 'dev', '--', '--host', host, '--port', String(appPort), '--strictPort'], {
    cwd: repoRoot,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, DISABLE_HMR: 'true' }
  });
  let serverLog = '';
  server.stdout.on('data', chunk => { serverLog += chunk.toString(); });
  server.stderr.on('data', chunk => { serverLog += chunk.toString(); });

  const failures = [];
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  const unexpectedResponses = [];
  const routeEvidence = [];
  const clickManifest = [];
  let styleProbe = null;

  try {
    await waitForHttp(origin);
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 950 } });
    const page = await context.newPage();
    page.on('console', msg => { if (['error'].includes(msg.type())) consoleErrors.push({ type: msg.type(), text: msg.text(), route: page.url() }); });
    page.on('pageerror', error => pageErrors.push({ message: error.message, stack: error.stack, route: page.url() }));
    page.on('requestfailed', request => failedRequests.push({ url: request.url(), method: request.method(), failure: request.failure()?.errorText, route: page.url() }));
    page.on('response', response => {
      const status = response.status();
      if (status >= 400 && !response.url().includes('/favicon')) unexpectedResponses.push({ url: response.url(), status, route: page.url() });
    });

    for (const [route, markers] of routeChecks) {
      const evidence = await inspectRoute(page, origin, route, markers, failures);
      routeEvidence.push(Object.fromEntries(Object.entries(evidence).filter(([k]) => k !== 'text')));
      if (!styleProbe) {
        styleProbe = await tailwindStyleProbe(page).catch(error => ({ error: error.message, tailwind_utilities_active: false }));
        await writeJson('style-probe.json', styleProbe);
        if (!styleProbe.tailwind_utilities_active) failures.push(`Tailwind/native AI Studio utilities are not active: ${JSON.stringify(styleProbe)}`);
      }
      for (const marker of markers) {
        if (!evidence.text.includes(marker)) failures.push(`${route} missing marker: ${marker}`);
      }
      for (const banned of bannedText) {
        if (banned.test(evidence.text)) failures.push(`${route} contains banned text: ${banned}`);
      }
      if (evidence.text.includes('Native AI Studio app failed to render')) {
        failures.push(`${route} native runtime bridge displayed error panel`);
      }
    }

    await page.goto(`${origin}/dashboard?source=latest`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(500);
    for (const label of ['Judge Demo Walkthrough', 'Raw Intake', 'AI-Enriched Queue', 'View All']) {
      if (label !== 'Judge Demo Walkthrough') {
        const closeResult = await closeIntentionalOverlay(page);
        if (closeResult.status === 'unexpected_overlay' || closeResult.status === 'failed_to_close') {
          failures.push(`/dashboard?source=latest blocking overlay before ${label}: ${JSON.stringify(closeResult)}`);
          break;
        }
        if (closeResult.status !== 'no_overlay') {
          clickManifest.push({ route: '/dashboard?source=latest', label: 'intentional overlay cleanup', ...closeResult });
        }
      }
      clickManifest.push({ route: '/dashboard?source=latest', ...(await clickIfPresent(page, label)) });
    }
    await page.goto(`${origin}/field/my-work`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(500);
    for (const label of ['Review Now', 'New Relief Request', 'View Assigned Cases']) {
      clickManifest.push({ route: '/field/my-work', ...(await clickIfPresent(page, label)) });
    }

    await browser.close();
  } finally {
    server.kill('SIGTERM');
    setTimeout(() => { try { server.kill('SIGKILL'); } catch {} }, 1500).unref();
    await fs.writeFile(path.join(evidenceDir, 'dev-server.log'), serverLog);
  }

  await writeJson('route-matrix.json', routeEvidence);
  await writeJson('visual-richness-summary.json', routeEvidence);
  await writeJson('click-manifest.json', clickManifest);
  await writeJson('console.log.json', consoleErrors);
  await writeJson('page-errors.json', pageErrors);
  await writeJson('failed-requests.json', failedRequests);
  await writeJson('network-summary.json', { unexpected_4xx_5xx: unexpectedResponses });

  const totalControls = routeEvidence.reduce((sum, item) => sum + item.controls, 0);
  const visibleClickChanges = clickManifest.filter(item => item.status === 'clicked_visible_change').length;
  const summary = {
    status: failures.length || consoleErrors.length || pageErrors.length || unexpectedResponses.length ? 'FAIL' : 'PASS',
    routes_tested: routeEvidence.length,
    controls_observed: totalControls,
    smoke_clicks: clickManifest.length,
    smoke_clicks_with_visible_sample_change: visibleClickChanges,
    console_errors: consoleErrors.length,
    page_errors: pageErrors.length,
    unexpected_4xx_5xx: unexpectedResponses.length,
    failures,
    artifacts: evidenceDir,
    style_probe: styleProbe
  };
  await writeJson('summary.json', summary);
  if (summary.status !== 'PASS') {
    console.error(`website readiness FAIL: ${evidenceDir}`);
    console.error(JSON.stringify(summary, null, 2));
    process.exit(1);
  }
  console.log(`website readiness PASS: ${evidenceDir}`);
  console.log(`Routes tested: ${summary.routes_tested}`);
  console.log(`Controls observed: ${summary.controls_observed}`);
  console.log(`Smoke clicks: ${summary.smoke_clicks}`);
  console.log(`Console errors: ${summary.console_errors}`);
  console.log(`Page errors: ${summary.page_errors}`);
  console.log(`Unexpected 4xx/5xx: ${summary.unexpected_4xx_5xx}`);
  console.log(`Artifacts: ${evidenceDir}`);
  // Force termination after successful artifact writing. Vite/Playwright child handles
  // can otherwise keep Node alive even after the PASS summary is printed.
  process.exit(0);
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
