import fs from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(dashboardRoot, '..');
const evidenceDir = path.resolve(repoRoot, 'reports', 'amd-evidence-ui', 'latest');
const screenshotsDir = path.resolve(evidenceDir, 'screenshots');
const host = '127.0.0.1';

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
function normalize(value) { return String(value || '').replace(/\s+/g, ' ').trim(); }

async function freePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once('error', reject);
    server.listen(0, host, () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close(() => port ? resolve(port) : reject(new Error('Unable to allocate free port')));
    });
  });
}

async function waitForHttp(url, label) {
  const started = Date.now();
  let lastError = '';
  while (Date.now() - started < 30000) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error.message;
    }
    await sleep(250);
  }
  throw new Error(`${label} did not become ready: ${lastError}`);
}

async function textOf(page, testId) {
  return normalize(await page.getByTestId(testId).innerText());
}

async function assertContains(page, testId, expected) {
  const value = await textOf(page, testId);
  if (!value.includes(expected)) {
    throw new Error(`${testId} missing ${JSON.stringify(expected)}; observed ${JSON.stringify(value)}`);
  }
  return value;
}

async function inspectRoute(page, origin, route, screenshotName) {
  await page.goto(`${origin}${route}`, { waitUntil: 'networkidle' });
  await page.getByTestId('amd-evidence-summary').waitFor({ timeout: 15000 });
  await page.getByTestId('amd-historical-resolved').waitFor({ timeout: 15000 });

  const historicalResolved = await assertContains(page, 'amd-historical-resolved', '24 / 24 resolved');
  const historicalScope = await assertContains(page, 'amd-historical-scope', 'Staged composite');
  const runtimeStatus = await assertContains(page, 'amd-current-runtime-status', 'Not configured in this process');
  const requestStatus = await assertContains(page, 'amd-current-request-status', 'Not attempted on this screen');
  const humanReviewStatus = await assertContains(page, 'amd-human-review-status', 'Required');
  const bodyText = normalize(await page.locator('body').innerText());

  for (const required of ['Historical verified campaign', 'Current runtime configuration', 'Current request result', 'Strict raw JSON']) {
    if (!bodyText.includes(required)) throw new Error(`${route} missing visible marker: ${required}`);
  }
  for (const forbidden of ['Current runtime: verified live', 'Configuration: Verified live']) {
    if (bodyText.includes(forbidden)) throw new Error(`${route} contains misleading current-live claim: ${forbidden}`);
  }

  const screenshotPath = path.resolve(screenshotsDir, screenshotName);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  return {
    route,
    historical_resolved: historicalResolved,
    historical_scope: historicalScope,
    runtime_status: runtimeStatus,
    request_status_before_test: requestStatus,
    human_review_status: humanReviewStatus,
    screenshot: path.relative(repoRoot, screenshotPath),
  };
}

async function main() {
  await fs.mkdir(screenshotsDir, { recursive: true });
  const port = await freePort();
  const origin = `http://${host}:${port}`;
  const apiLog = [];
  const cleanEnv = { ...process.env, PYTHONPATH: 'src', AI_MODE: 'mock' };
  for (const key of [
    'OPENAI_COMPAT_BASE_URL',
    'OPENAI_COMPAT_API_KEY',
    'OPENAI_COMPAT_MODEL',
    'OPENAI_COMPAT_UNDERLYING_MODEL',
  ]) delete cleanEnv[key];

  const server = spawn('python3', ['-m', 'reliefqueue.product_api', 'serve', '--host', host, '--port', String(port)], {
    cwd: repoRoot,
    env: cleanEnv,
    detached: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  server.stdout.on('data', chunk => apiLog.push(chunk.toString()));
  server.stderr.on('data', chunk => apiLog.push(chunk.toString()));

  let browser;
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  const failedResponses = [];
  try {
    await waitForHttp(`${origin}/api/product/amd/capability`, 'Product API');
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', error => pageErrors.push(error.message));
    page.on('requestfailed', request => failedRequests.push({ url: request.url(), error: request.failure()?.errorText || 'unknown' }));
    page.on('response', response => {
      if (response.status() >= 400) failedResponses.push({ url: response.url(), status: response.status() });
    });

    const amdImpact = await inspectRoute(page, origin, '/dashboard/amd-impact', 'amd-impact-before-request.png');
    const inferenceMode = await textOf(page, 'amd-inference-mode');
    if (inferenceMode.includes('Live AMD/vLLM')) {
      throw new Error(`AMD Impact still presents an unconditional live mode: ${inferenceMode}`);
    }
    amdImpact.inference_mode = inferenceMode;

    const capabilityMap = await inspectRoute(page, origin, '/dashboard/capability-map', 'capability-map-before-request.png');
    const currentAiRuntime = normalize(await page.getByTestId('capability-current-ai-runtime').innerText());
    if (!currentAiRuntime.includes('Not configured in this process') || !currentAiRuntime.includes('Provider: Not claimed')) {
      throw new Error(`Capability Map current runtime is not truthfully unconfigured: ${currentAiRuntime}`);
    }
    capabilityMap.current_ai_runtime = currentAiRuntime;

    await page.getByRole('button', { name: 'Test AMD/vLLM Advisory Path' }).click();
    await page.waitForFunction(() => {
      const node = document.querySelector('[data-testid="amd-current-request-status"]');
      const text = node?.textContent || '';
      return text && !text.includes('Not attempted') && !text.includes('in progress');
    }, null, { timeout: 15000 });
    const requestStatusAfter = await textOf(page, 'amd-current-request-status');
    if (!/not verified live|verification incomplete/i.test(requestStatusAfter)) {
      throw new Error(`Mock-mode request was not visibly labelled non-live: ${requestStatusAfter}`);
    }
    const historicalAfter = await textOf(page, 'amd-historical-resolved');
    if (!historicalAfter.includes('24 / 24 resolved')) {
      throw new Error('Historical evidence changed or disappeared after current-request test');
    }
    await page.screenshot({ path: path.resolve(screenshotsDir, 'capability-map-after-mock-request.png'), fullPage: true });

    const relevantFailedResponses = failedResponses.filter(item => !item.url.endsWith('/favicon.ico'));
    if (consoleErrors.length || pageErrors.length || failedRequests.length || relevantFailedResponses.length) {
      throw new Error(`Browser errors detected: ${JSON.stringify({ consoleErrors, pageErrors, failedRequests, failedResponses: relevantFailedResponses })}`);
    }

    const report = {
      status: 'PASS',
      runner: 'Playwright Chromium',
      provider_calls: 0,
      api_mode: 'mock',
      historical_evidence_preserved_after_request_test: true,
      routes: [amdImpact, capabilityMap],
      current_request_status_after_mock_test: requestStatusAfter,
      console_errors: consoleErrors,
      page_errors: pageErrors,
      failed_requests: failedRequests,
      failed_responses: relevantFailedResponses,
    };
    const reportPath = path.resolve(evidenceDir, 'report.json');
    await fs.writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
    console.log('AMD_EVIDENCE_UI_CHECK=PASS');
    console.log(`AMD_EVIDENCE_UI_REPORT=${path.relative(repoRoot, reportPath)}`);
  } finally {
    await browser?.close().catch(() => {});
    if (!server.killed && server.pid) {
      try { process.kill(-server.pid, 'SIGTERM'); } catch { server.kill('SIGTERM'); }
    }
    await sleep(300);
    await fs.writeFile(path.resolve(evidenceDir, 'product-api.log'), apiLog.join('')).catch(() => {});
  }
}

main().catch(error => {
  console.error(error.stack || error.message);
  process.exit(1);
});
