import fs from 'node:fs/promises';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(dashboardRoot, '..');
const reportDir = path.resolve(repoRoot, 'reports', 'judge-front-door', 'latest');
const reportPath = path.resolve(reportDir, 'report.json');

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close(() => port ? resolve(port) : reject(new Error('unable to allocate local port')));
    });
  });
}

async function waitForJson(url, label) {
  const deadline = Date.now() + 30000;
  let last = '';
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      const contentType = response.headers.get('content-type') || '';
      const body = await response.text();
      if (response.ok && contentType.includes('application/json')) {
        return JSON.parse(body);
      }
      last = `HTTP ${response.status} ${contentType} ${body.slice(0, 120)}`;
    } catch (error) {
      last = String(error);
    }
    await sleep(250);
  }
  throw new Error(`${label} did not return JSON: ${last}`);
}

function cleanProviderEnvironment() {
  const env = { ...process.env, AI_MODE: 'mock', PYTHONPATH: 'src' };
  for (const key of [
    'AI_API_KEY', 'AI_BASE_URL', 'AI_MODEL',
    'FIREWORKS_API_KEY', 'FIREWORKS_BASE_URL', 'FIREWORKS_MODEL',
    'OPENAI_COMPAT_API_KEY', 'OPENAI_COMPAT_BASE_URL', 'OPENAI_COMPAT_MODEL',
    'OPENAI_COMPAT_UNDERLYING_MODEL',
  ]) {
    delete env[key];
  }
  return env;
}

async function stopProcess(child) {
  if (!child?.pid || child.killed) return;
  try {
    process.kill(-child.pid, 'SIGTERM');
  } catch {
    child.kill('SIGTERM');
  }
  await Promise.race([
    new Promise((resolve) => child.once('exit', resolve)),
    sleep(3000),
  ]);
  if (!child.killed && child.exitCode == null) {
    try {
      process.kill(-child.pid, 'SIGKILL');
    } catch {
      child.kill('SIGKILL');
    }
  }
}

function rawJsonError(text) {
  return /JSON\.parse|unexpected end of data|unexpected character at line 1 column 1/i.test(text);
}

async function assertNoFrontDoorError(page, label) {
  const text = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
  if (rawJsonError(text)) throw new Error(`${label} exposes a raw JSON parser error`);
  if (/Evidence API unavailable/i.test(text)) throw new Error(`${label} says Evidence API unavailable`);
  return text;
}

async function main() {
  const apiPort = await freePort();
  const appPort = await freePort();
  const apiOrigin = `http://127.0.0.1:${apiPort}`;
  const appOrigin = `http://127.0.0.1:${appPort}`;
  const env = cleanProviderEnvironment();

  const api = spawn(
    'python3',
    ['-m', 'reliefqueue.product_api', 'serve', '--host', '127.0.0.1', '--port', String(apiPort)],
    { cwd: repoRoot, env, detached: true, stdio: ['ignore', 'pipe', 'pipe'] },
  );
  const vite = spawn(
    'npm',
    ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(appPort), '--strictPort'],
    {
      cwd: dashboardRoot,
      env: {
        ...env,
        DISABLE_HMR: 'true',
        RELIEFQUEUE_PRODUCT_API_TARGET: apiOrigin,
      },
      detached: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  );

  const browser = await chromium.launch({ headless: true });
  const checks = [];
  try {
    await waitForJson(`${apiOrigin}/healthz`, 'direct Product API health');
    await waitForJson(`${appOrigin}/healthz`, 'Vite-proxied health');
    const capability = await waitForJson(
      `${appOrigin}/api/product/amd/capability`,
      'Vite-proxied AMD capability',
    );
    if (capability.status !== 'ok') throw new Error('proxied AMD capability status is not ok');
    checks.push('proxy-json');

    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

    await page.goto(`${appOrigin}/dashboard/amd-impact`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('heading', { name: 'AMD GPU / vLLM Impact' }).waitFor({ state: 'visible' });
    await page.locator('[data-testid="amd-evidence-summary"]').waitFor({ state: 'visible' });
    await assertNoFrontDoorError(page, 'AMD Impact');
    checks.push('amd-impact-landing');

    await page.goto(`${appOrigin}/dashboard/capability-map`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('heading', { name: 'Capability Map & Readiness' }).waitFor({ state: 'visible' });
    await page.locator(
      '[data-testid="capability-runtime-status"][data-api-status="connected"][data-health-status="passing"]',
    ).waitFor({ state: 'visible', timeout: 15000 });
    await assertNoFrontDoorError(page, 'Capability Map');
    checks.push('capability-map-landing');

    await page.goto(`${appOrigin}/dashboard?source=latest`, { waitUntil: 'domcontentloaded' });
    await page.locator('[data-testid="overview-missing-info-card"]').click();
    await page.waitForURL((url) => url.pathname === '/dashboard/intake');
    checks.push('overview-missing-info-navigation');

    await page.goto(`${appOrigin}/dashboard?source=latest`, { waitUntil: 'domcontentloaded' });
    await page.locator('[data-testid="overview-malformed-output-card"]').click();
    await page.waitForURL((url) => url.pathname === '/dashboard/quality');
    checks.push('overview-malformed-navigation');

    await page.goto(`${appOrigin}/dashboard/assignments`, { waitUntil: 'domcontentloaded' });
    const openCase = page.locator('[data-action-id="command.open_case_detail"]');
    await openCase.first().waitFor({ state: 'visible' });
    const openCount = await openCase.count();
    await openCase.nth(openCount > 1 ? 1 : 0).click();
    await page.locator('[data-result-id="command.case-detail"]').waitFor({ state: 'visible' });
    await page.locator('[data-action-id="command.request_review_required_ai_advisory"]').click();
    await page.locator('[data-result-id="command.ai"]').waitFor({ state: 'visible' });
    await page.locator('[data-testid="assignment-advisory-mode"]').filter({
      hasText: 'Deterministic Local Advisory',
    }).waitFor({ state: 'visible' });
    await page.locator('[data-testid="assignment-advisory-provider"]').filter({
      hasText: 'Not contacted',
    }).waitFor({ state: 'visible' });
    await page.locator('[data-testid="assignment-advisory-latency"]').filter({
      hasText: 'Local · no provider call',
    }).waitFor({ state: 'visible' });
    const advisoryText = await page.locator('[data-result-id="command.ai"]').innerText();
    if (/Connected \(vLLM\)|450ms/i.test(advisoryText)) {
      throw new Error('Assignment advisory still fabricates live provider success');
    }
    await page.locator('[data-action-id="assignment.open_live_amd_test"]').click();
    await page.waitForURL((url) => url.pathname === '/dashboard/amd-impact');
    checks.push('assignment-advisory-truth-and-navigation');

    await page.goto(`${appOrigin}/dashboard/intake`, { waitUntil: 'domcontentloaded' });
    await page.locator('[data-testid^="ai-intake-normalize-"]').first().click();
    await page.locator('[data-testid="ai-intake-run-advisory"]').waitFor({ state: 'visible' });
    await page.locator('[data-testid="ai-intake-run-advisory"]').click();
    await sleep(600);
    const intakeText = await page.locator('body').innerText();
    if (rawJsonError(intakeText)) throw new Error('AI Intake exposes a raw JSON parser error');
    checks.push('intake-readable-response-boundary');

    await page.goto(`${appOrigin}/dashboard/ai-control`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Test Connection' }).click();
    await sleep(600);
    const controlText = await page.locator('body').innerText();
    if (rawJsonError(controlText)) throw new Error('AI Control exposes a raw JSON parser error');
    checks.push('ai-control-readable-response-boundary');

    const output = {
      status: 'PASS',
      contract: 'reliefqueue-judge-front-door/v1',
      provider_calls: 0,
      api_origin: apiOrigin,
      app_origin: appOrigin,
      checks,
      generated_at_utc: new Date().toISOString(),
    };
    await fs.mkdir(reportDir, { recursive: true });
    await fs.writeFile(reportPath, `${JSON.stringify(output, null, 2)}\n`, 'utf8');
    console.log(`JUDGE_FRONT_DOOR_CHECK=PASS checks=${checks.length} provider_calls=0`);
    console.log(`JUDGE_FRONT_DOOR_REPORT=${path.relative(repoRoot, reportPath)}`);
  } finally {
    await browser.close().catch(() => {});
    await stopProcess(vite);
    await stopProcess(api);
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
