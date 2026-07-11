import net from 'node:net';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(dashboardRoot, '..');
const host = '127.0.0.1';

function freePort() {
  return new Promise((resolve, reject) => {
    const listener = net.createServer();
    listener.on('error', reject);
    listener.listen(0, host, () => {
      const address = listener.address();
      listener.close(() => resolve(address.port));
    });
  });
}

async function waitFor(url) {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`server not ready: ${url}`);
}

async function openWorkspaceSwitcher(page, label) {
  const switcher = page.locator('summary[aria-label="Switch ReliefQueue workspace"]');
  await switcher.waitFor({ state: 'visible' });
  await switcher.scrollIntoViewIfNeeded();
  const box = await switcher.boundingBox();
  const viewport = page.viewportSize();
  if (
    !box ||
    !viewport ||
    box.x < 0 ||
    box.y < 0 ||
    box.x + box.width > viewport.width ||
    box.y + box.height > viewport.height
  ) {
    throw new Error(
      `${label} workspace switcher is outside the viewport: ${JSON.stringify({ box, viewport })}`,
    );
  }
  await switcher.click();
}

async function waitForFieldNavigation(page, label) {
  const navigation = page.getByRole('navigation', { name: 'Field Coordinator navigation' });
  await navigation.waitFor({ state: 'visible' });

  const links = {};
  for (const item of ['My Work', 'My Cases', 'Outbox', 'Help']) {
    const link = navigation.getByRole('link', { name: item, exact: true });
    await link.waitFor({ state: 'visible' });
    const count = await link.count();
    if (count !== 1) {
      throw new Error(`${label} expected exactly one visible ${item} link, found ${count}`);
    }
    links[item] = link;
  }
  return { navigation, links };
}

const port = await freePort();
const origin = `http://${host}:${port}`;
const server = spawn(
  'python3',
  ['-m', 'reliefqueue.product_api', 'serve', '--host', host, '--port', String(port)],
  {
    cwd: repoRoot,
    env: { ...process.env, PYTHONPATH: path.join(repoRoot, 'src') },
    stdio: ['ignore', 'pipe', 'pipe'],
  },
);
let serverLog = '';
server.stdout.on('data', (chunk) => { serverLog += chunk.toString(); });
server.stderr.on('data', (chunk) => { serverLog += chunk.toString(); });

const failures = [];
const consoleErrors = [];
const pageErrors = [];
const httpErrors = [];

try {
  await waitFor(`${origin}/healthz`);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  page.on('response', (response) => {
    if (
      response.url().startsWith(origin) &&
      response.status() >= 400 &&
      !response.url().includes('favicon')
    ) {
      httpErrors.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto(`${origin}/dashboard?source=latest`, { waitUntil: 'networkidle' });
  const commandItems = [
    'Overview',
    'AI Intake',
    'Incident Links',
    'Live Map',
    'Assignments',
    'Workload',
    'Field Sync',
    'Scenario',
    'AI Control',
    'Quality',
    'Audit / Troubleshooting',
    'AMD Impact',
    'Capability Map',
  ];
  for (const item of commandItems) {
    if (!(await page.getByRole('button', { name: item, exact: true }).count())) {
      failures.push(`missing command sidebar item: ${item}`);
    }
  }

  await page.getByRole('button', { name: 'AMD Impact', exact: true }).click();
  await page.waitForURL('**/dashboard/amd-impact');
  await page.getByText('AMD GPU', { exact: false }).first().waitFor();

  await page.getByRole('button', { name: 'Assignments', exact: true }).click();
  await page.waitForURL('**/dashboard/assignments');
  await page.goBack();
  await page.waitForURL('**/dashboard/amd-impact');
  await page.goForward();
  await page.waitForURL('**/dashboard/assignments');

  await openWorkspaceSwitcher(page, 'command');
  await Promise.all([
    page.waitForURL('**/field/my-work'),
    page.getByRole('link', { name: /Field Coordinator/ }).click(),
  ]);

  const desktopFieldNavigation = await waitForFieldNavigation(page, 'field desktop');
  await desktopFieldNavigation.links['My Cases'].click();
  await page.waitForURL('**/field/my-cases');
  await page.locator('[data-action-id="field.open_case_detail"]').first().click();
  await page.waitForURL('**/field/cases/RQ-1042');
  await page.getByText('Add Note', { exact: true }).waitFor();
  const caseDetailFieldNavigation = await waitForFieldNavigation(page, 'field case detail');
  await caseDetailFieldNavigation.links.Outbox.click();
  await page.waitForURL('**/field/outbox');

  await openWorkspaceSwitcher(page, 'field');
  await Promise.all([
    page.waitForURL('**/local-coordinator?source=latest'),
    page.getByRole('link', { name: /Local Coordinator/ }).click(),
  ]);
  await page.getByRole('heading', { name: 'Local Coordinator', exact: true }).waitFor();

  await openWorkspaceSwitcher(page, 'local');
  await Promise.all([
    page.waitForURL('**/dashboard?source=latest'),
    page.getByRole('link', { name: /Command Center/ }).click(),
  ]);
  await page.getByRole('button', { name: 'Capability Map', exact: true }).click();
  await page.waitForURL('**/dashboard/capability-map');
  for (const marker of [
    'Product API: Connected',
    'Health check: Passing',
    'State persistence: Ephemeral',
  ]) {
    await page.getByText(marker, { exact: false }).waitFor();
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${origin}/field/outbox`, { waitUntil: 'networkidle' });
  const mobileFieldNavigation = await waitForFieldNavigation(page, 'field mobile');
  const mobileOutboxClass = await mobileFieldNavigation.links.Outbox.getAttribute('class');
  if (!mobileOutboxClass?.includes('bg-primary-container')) {
    throw new Error(`field mobile Outbox link is not visibly active: ${mobileOutboxClass}`);
  }
  const networkStatus = page.getByRole('button', { name: /Network status:/ });
  await networkStatus.waitFor();
  const networkBox = await networkStatus.boundingBox();
  if (!networkBox || networkBox.x < 0 || networkBox.x + networkBox.width > 390) {
    throw new Error(`mobile network status is outside the viewport: ${JSON.stringify(networkBox)}`);
  }
  await openWorkspaceSwitcher(page, 'field mobile');
  await page.getByRole('link', { name: /Command Center/ }).waitFor();
  await page.locator('summary[aria-label="Switch ReliefQueue workspace"]').click();

  await browser.close();
} finally {
  server.kill('SIGTERM');
}

if (consoleErrors.length || pageErrors.length || httpErrors.length) {
  failures.push(`runtime errors: ${JSON.stringify({ consoleErrors, pageErrors, httpErrors })}`);
}
if (failures.length) {
  console.error(`replit navigation smoke FAIL: ${JSON.stringify(failures, null, 2)}`);
  if (serverLog) console.error(serverLog.slice(-4000));
  process.exit(1);
}
console.log(
  'replit navigation smoke PASS: command=13 field=4 role_switches=3 history=PASS runtime_status=PASS mobile_field=PASS',
);
