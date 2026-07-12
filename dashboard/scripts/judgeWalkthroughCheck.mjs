import fs from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(dashboardRoot, '..');
const reportDir = path.resolve(repoRoot, 'reports', 'judge-walkthrough', 'latest');
const reportPath = path.resolve(reportDir, 'report.json');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close(() => port ? resolve(port) : reject(new Error('unable to allocate port')));
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
      if (response.ok && contentType.includes('application/json')) return JSON.parse(body);
      last = `HTTP ${response.status} ${contentType} ${body.slice(0, 100)}`;
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
  ]) delete env[key];
  return env;
}

async function stopProcess(child) {
  if (!child?.pid || child.killed) return;
  try { process.kill(-child.pid, 'SIGTERM'); } catch { child.kill('SIGTERM'); }
  await Promise.race([new Promise((resolve) => child.once('exit', resolve)), sleep(3000)]);
  if (!child.killed && child.exitCode == null) {
    try { process.kill(-child.pid, 'SIGKILL'); } catch { child.kill('SIGKILL'); }
  }
}

async function openWalkthrough(page, appOrigin) {
  await page.goto(`${appOrigin}/dashboard?source=latest`, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Judge Demo Walkthrough' }).click();
  await page.getByRole('heading', { name: 'Judge Demo Walkthrough' }).waitFor({ state: 'visible' });
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
      env: { ...env, DISABLE_HMR: 'true', RELIEFQUEUE_PRODUCT_API_TARGET: apiOrigin },
      detached: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  );

  const browser = await chromium.launch({ headless: true });
  const checks = [];
  try {
    await waitForJson(`${apiOrigin}/api/health`, 'direct Product API health');
    await waitForJson(`${appOrigin}/api/health`, 'proxied health');

    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

    await openWalkthrough(page, appOrigin);
    const step1 = page.locator('[data-testid="walkthrough-step-1"]');
    await step1.click();
    await step1.getByRole('button', { name: 'Run Step' }).click();
    await step1.locator('[data-testid="walkthrough-step1-open-intake"]').waitFor({ state: 'visible' });
    await step1.locator('[data-testid="walkthrough-step1-open-intake"]').click();
    await page.waitForURL((url) => url.pathname === '/dashboard/intake');
    await page.locator('[data-testid="walkthrough-intake-handoff"]').waitFor({ state: 'visible' });
    const intakeText = await page.locator('[data-testid="ai-intake-original-input"]').innerText();
    if (!intakeText.includes('family of 5 stranded near north sector bridge')) {
      throw new Error('Step 1 handoff lost the exact report text');
    }

    await page.locator('[data-testid="ai-intake-scroll-cue"]').waitFor({
      state: 'visible',
    });

    const analysisRegion = page.locator('[data-testid="ai-intake-analysis-scroll"]');
    const persistentRail = page.locator('[data-testid="ai-intake-persistent-scrollbar"]');
    const persistentThumb = page.locator('[data-testid="ai-intake-scroll-thumb"]');

    await persistentRail.waitFor({ state: 'visible' });
    await persistentThumb.waitFor({ state: 'visible' });

    const railBox = await persistentRail.boundingBox();
    const thumbBox = await persistentThumb.boundingBox();
    if (!railBox || railBox.width < 20 || railBox.height < 100) {
      throw new Error('Persistent Intake analysis scroll rail is not visibly sized');
    }
    if (!thumbBox || thumbBox.width < 8 || thumbBox.height < 20) {
      throw new Error('Persistent Intake analysis scroll thumb is not visibly sized');
    }

    const beforeScrollTop = await analysisRegion.evaluate((element) => element.scrollTop);
    await page.getByRole('button', { name: 'Scroll analysis down' }).click();
    await page.waitForFunction(
      ({ selector, before }) => {
        const element = document.querySelector(selector);
        return element instanceof HTMLElement && element.scrollTop > before;
      },
      {
        selector: '[data-testid="ai-intake-analysis-scroll"]',
        before: beforeScrollTop,
      },
    );

    const afterScrollTop = await analysisRegion.evaluate((element) => element.scrollTop);
    if (afterScrollTop <= beforeScrollTop) {
      throw new Error('Persistent Intake scroll control did not move the analysis content');
    }

    checks.push('step1-intake-context');
    checks.push('step1-scroll-discoverability');

    await openWalkthrough(page, appOrigin);
    const step2 = page.locator('[data-testid="walkthrough-step-2"]');
    await step2.click();
    await step2.getByRole('button', { name: 'Run Step' }).click();
    await step2.locator('[data-testid="walkthrough-step2-open-assignment"]').waitFor({ state: 'visible' });
    await step2.locator('[data-testid="walkthrough-step2-open-assignment"]').click();
    await page.waitForURL((url) => url.pathname === '/dashboard/assignments');
    await page.locator('[data-testid="walkthrough-assignment-handoff"]').waitFor({ state: 'visible' });
    await page.locator('[data-result-id="command.ai"]').waitFor({ state: 'visible' });
    await page.locator('[data-testid="assignment-advisory-mode"]').filter({ hasText: 'Deterministic Local Advisory' }).waitFor({ state: 'visible' });
    checks.push('step2-assignment-context');

    await openWalkthrough(page, appOrigin);
    const step4 = page.locator('[data-testid="walkthrough-step-4"]');
    await step4.click();
    const dossierInput = step4.locator('[data-testid="walkthrough-dossier-input"]');
    await dossierInput.fill('WALKTHROUGH-DOSSIER-UNIQUE\nSynthetic report for handoff validation.');
    await step4.locator('[data-testid="walkthrough-step4-open-amd"]').click();
    await page.waitForURL((url) => url.pathname === '/dashboard/amd-impact');
    await page.locator('[data-testid="walkthrough-amd-handoff"]').waitFor({ state: 'visible' });
    const dossierValue = await page.locator('[data-testid="amd-complex-input"]').inputValue();
    if (!dossierValue.includes('WALKTHROUGH-DOSSIER-UNIQUE')) throw new Error('Step 4 dossier handoff failed');
    checks.push('step4-dossier-handoff');

    await openWalkthrough(page, appOrigin);
    const step5 = page.locator('[data-testid="walkthrough-step-5"]');
    await step5.click();
    const burstInput = step5.locator('[data-testid="walkthrough-burst-input"]');
    await burstInput.fill('{"id":"walkthrough-burst","text":"Synthetic burst handoff validation"}');
    await step5.locator('[data-testid="walkthrough-step5-open-amd"]').click();
    await page.waitForURL((url) => url.pathname === '/dashboard/amd-impact');
    await page.locator('[data-testid="walkthrough-amd-handoff"]').waitFor({ state: 'visible' });
    const burstValue = await page.locator('[data-testid="amd-burst-input"]').inputValue();
    if (!burstValue.includes('walkthrough-burst')) throw new Error('Step 5 burst handoff failed');
    checks.push('step5-burst-handoff');

    await openWalkthrough(page, appOrigin);
    const step7 = page.locator('[data-testid="walkthrough-step-7"]');
    await step7.click();
    await step7.locator('[data-testid="walkthrough-step7-open-field-task"]').click();
    await page.waitForURL((url) => url.pathname === '/field/cases/RQ-1042');
    await page.locator('[data-result-id="field.detail"]').waitFor({ state: 'visible' });
    const fieldText = await page.locator('body').innerText();
    if (!fieldText.includes('RQ-1042') || !fieldText.includes('Coordinator Instructions')) {
      throw new Error('Step 7 did not open the real field task context');
    }
    checks.push('step7-field-task');

    const output = {
      status: 'PASS',
      contract: 'reliefqueue-judge-walkthrough/v1',
      provider_calls: 0,
      checks,
      generated_at_utc: new Date().toISOString(),
    };
    await fs.mkdir(reportDir, { recursive: true });
    await fs.writeFile(reportPath, `${JSON.stringify(output, null, 2)}\n`, 'utf8');
    console.log(`JUDGE_WALKTHROUGH_CHECK=PASS checks=${checks.length} provider_calls=0`);
    console.log(`JUDGE_WALKTHROUGH_REPORT=${path.relative(repoRoot, reportPath)}`);
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
