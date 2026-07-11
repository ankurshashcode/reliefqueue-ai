import { chromium } from 'playwright';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

const title = '@amd-quality AMD Impact / Intake provenance smoke';
const baseUrl = process.env.AMD_QUALITY_BASE_URL || 'http://127.0.0.1:5173';
const evidenceRoot = path.resolve(process.env.AMD_QUALITY_EVIDENCE_ROOT || 'reports/amd-inference-quality/latest');
const screenshotDir = path.join(evidenceRoot, 'screenshots');

function hash(value) {
  return crypto.createHash('sha256').update(String(value)).digest('hex');
}

function priority(rank, action) {
  return { rank, action, reason: 'Source-grounded reason', dependency: 'Coordinator approval', verify_before_action: 'Verify location, route and resources' };
}

function metadata() {
  return {
    provider: 'AMD Developer Cloud',
    accelerator: 'AMD Instinct MI300X',
    runtime: 'vLLM',
    served_model: 'reliefqueue-amd',
    underlying_model: null,
    metadata_source: 'provider_response:served_model+backend_deployment_config',
    underlying_model_reported: false,
  };
}

function liveResult(mode, input, requestId, nonce) {
  const dossier = mode === 'complex_dossier';
  const structured = dossier ? {
    schema_version: 'reliefqueue-dossier-analysis/v1',
    workload_mode: 'complex_dossier',
    challenge_nonce: nonce,
    situation_summary: 'Source-grounded dossier synthesis across medical, shelter, route and inventory constraints.',
    source_report_count: 20,
    consolidated_incidents: [
      { incident_id: 'I-1', source_ids: ['REPORT-001', 'REPORT-003'], evidence: ['Likely duplicate Old Bus Stand reports'], confidence: 'high' },
      { incident_id: 'I-2', source_ids: ['REPORT-006', 'REPORT-007'], evidence: ['Police correction supersedes social rumour'], confidence: 'high' },
      { incident_id: 'I-3', source_ids: ['REPORT-008', 'REPORT-020'], evidence: ['Community Hall safe capacity changed'], confidence: 'high' },
      { incident_id: 'I-4', source_ids: ['REPORT-011', 'REPORT-016'], evidence: ['Insulin and vehicle constraints'], confidence: 'medium' },
    ],
    duplicate_clusters: [{ source_ids: ['REPORT-001', 'REPORT-003'], reason: 'same location and need' }],
    contradictions: [
      { source_ids: ['REPORT-006', 'REPORT-007'], conflict: 'collapsed versus damaged', working_assumption: 'damaged, not collapsed' },
      { source_ids: ['REPORT-008', 'REPORT-020'], conflict: 'capacity 80 versus safe capacity 43', working_assumption: 'use 43' },
    ],
    superseded_updates: [{ older_source_id: 'REPORT-005', newer_source_id: 'REPORT-015', change: 'textile godown supersedes Clinic Road' }],
    unverified_claims: [{ source_ids: ['REPORT-006'], claim: 'bridge collapsed', verification_needed: 'police confirmation' }],
    people_count_ranges: ['67 registered versus safe capacity 43: over capacity by 24'],
    resource_gaps: ['12 insulin doses for 19 listed patients: shortfall 7 before duplicate reconciliation'],
    capacity_pressure: ['Community Hall safe capacity reduced from 80 to 43 while 67 remain registered'],
    route_constraints: ['Wheelchair-ramp van and oxygen-reserved van are both scarce'],
    cross_incident_dependencies: ['Small van needed for accessible evacuation and water purification access'],
    prioritized_operational_plan: [priority(1, 'Confirm medical cases'), priority(2, 'Reconcile shelter overflow'), priority(3, 'Protect transformer exclusion zone'), priority(4, 'Allocate accessible van'), priority(5, 'Confirm bridge route')],
    missing_information_questions: ['Confirm duplicate insulin patients'],
    coordinator_review_gates: ['No automatic dispatch'],
    confidence_notes: ['Mocked browser evidence'],
    warnings: [],
    human_review_required: true,
  } : {
    schema_version: 'reliefqueue-operational-analysis/v1',
    workload_mode: 'single',
    challenge_nonce: nonce,
    situation_summary: '17 people, possibly 21, include two wheelchair users; water lasts six hours.',
    critical_facts: ['east road blocked by transformer', 'west route small vehicles only'],
    contradictions: ['17 versus 21 people'],
    risk_escalators: ['wheelchair users', 'six-hour water window'],
    recommended_priorities: [priority(1, 'Verify transformer isolation'), priority(2, 'Reserve accessible small vehicle'), priority(3, 'Move water before six-hour deadline')],
    resource_implications: ['Accessible vehicle and emergency water'],
    route_and_access_analysis: ['Avoid east transformer zone; verify west route clearance'],
    missing_information: ['Confirm current people count'],
    coordinator_questions: ['Is utility isolation confirmed?', 'Which ramp-equipped vehicle fits the west route?'],
    public_reply_draft: 'Coordinator review pending.',
    confidence_notes: ['Mocked browser evidence'],
    warnings: ['No automatic dispatch'],
    human_review_required: true,
  };
  return {
    status: 'ok',
    verified_live: true,
    provider_transport_verified_live: true,
    provider_response_received: true,
    analysis_source: 'provider',
    fallback_used: false,
    provider: 'AMD Developer Cloud',
    runtime: 'vLLM',
    accelerator: 'AMD Instinct MI300X',
    served_model: 'reliefqueue-amd',
    underlying_model: null,
    model_metadata: metadata(),
    request_id: requestId,
    challenge_nonce: nonce,
    nonce_sent_to_provider: true,
    nonce_echoed_by_provider: true,
    verification_bound_to_nonce: true,
    verified_at: '2026-07-11T12:00:00Z',
    latency_ms: 321,
    prompt_tokens: 400,
    completion_tokens: 600,
    total_tokens: 1000,
    human_review_required: true,
    original_input: input,
    sanitized_input: input,
    synthetic_text_sent: true,
    private_text_sent: false,
    secret_values_exposed: false,
    structured_output: structured,
    normalized_structured_record: structured,
    compact_json: structured,
    source_evidence_mapping: [
      { field: 'situation_summary', source_evidence: input.slice(0, 120), normalized_value: structured.situation_summary, confidence: 'high' },
      { field: 'contradictions', source_evidence: 'source reports', normalized_value: JSON.stringify(structured.contradictions), confidence: 'medium' },
    ],
    operational_analysis: { priorities: structured.recommended_priorities || structured.prioritized_operational_plan, contradictions: structured.contradictions, human_review_required: true },
    generated_advisory: structured.situation_summary,
    warnings: ['Human coordinator review required before any field action.'],
    error: null,
  };
}

function burstResult(reports) {
  const cases = reports.map((report, index) => ({
    ...liveResult('burst_case', report.text, `req-case-${index + 1}`, `nonce-case-${index + 1}`),
    case_id: report.id,
    structured_output: {
      schema_version: 'reliefqueue-burst-case-analysis/v1',
      workload_mode: 'burst_case',
      case_id: report.id,
      challenge_nonce: `nonce-case-${index + 1}`,
      situation_summary: report.text,
      critical_facts: [report.text],
      contradictions: [],
      risk_escalators: ['review required'],
      recommended_priorities: [priority(1, `Review ${report.id}`)],
      resource_implications: ['coordinate shared resources'],
      route_and_access_analysis: ['confirm route'],
      missing_information: ['confirm exact facts'],
      coordinator_questions: ['What changes priority?'],
      confidence_notes: ['mock'],
      warnings: [],
      human_review_required: true,
    },
  }));
  const synthesisNonce = 'nonce-synthesis-1';
  const synthesis = {
    schema_version: 'reliefqueue-cross-case-synthesis/v1',
    workload_mode: 'cross_case_synthesis',
    challenge_nonce: synthesisNonce,
    highest_risk_cases: [{ case_id: reports[2].id, reason: 'insulin shortfall' }],
    resource_competition: ['Accessible vehicle competes with medical transport'],
    shared_route_bottlenecks: ['south lane'],
    possible_duplicate_cases: [],
    inventory_conflicts: ['12 doses versus 19 patients'],
    suggested_sequence: [priority(1, 'Medical shortage'), priority(2, 'Accessible evacuation'), priority(3, 'Water supply')],
    cases_that_can_wait_with_reason: [],
    missing_facts_that_could_change_order: ['duplicate patient count'],
    aggregate_resource_implications: ['reserve accessible vehicle and insulin supply'],
    coordinator_review_gates: ['human approval'],
    human_review_required: true,
  };
  return {
    status: 'ok', verified_live: true, fallback_used: false,
    batch_id: 'batch-mock', started_at: '2026-07-11T12:00:00Z', completed_at: '2026-07-11T12:00:02Z',
    submitted: 3, parsed: 3, succeeded: 3, failed: 0, live_amd_responses: 3,
    live_provider_calls_succeeded: 4, provider_call_count: 4, fallback_responses: 0,
    total_elapsed_ms: 2000, median_latency_ms: 300, p95_latency_ms: 350,
    prompt_tokens: 1200, completion_tokens: 1600, total_tokens: 2800,
    approximate_throughput_rps: 1.5, active_model: 'reliefqueue-amd', served_model: 'reliefqueue-amd',
    runtime: 'vLLM', accelerator: 'AMD Instinct MI300X', human_review_required: true,
    cases, parsed_preview: reports,
    cross_case_synthesis: synthesis,
    cross_case_evidence: {
      ...liveResult('cross_case_synthesis', JSON.stringify(reports), 'req-synthesis-1', synthesisNonce),
      structured_output: synthesis,
      generated_advisory: 'Cross-case synthesis',
    },
    request_settings: { burst_case_completion_max_tokens: 900, cross_case_synthesis_completion_max_tokens: 1600 },
    model_metadata: metadata(),
  };
}

async function main() {
  console.log(title);
  await fs.mkdir(screenshotDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  const unexpectedHttp = [];
  const clicks = [];
  const routes = [];

  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
  page.on('pageerror', error => pageErrors.push(error.message));
  page.on('requestfailed', request => failedRequests.push({ url: request.url(), error: request.failure()?.errorText || 'unknown' }));
  page.on('response', response => { if (response.status() >= 400 && !response.url().includes('favicon')) unexpectedHttp.push({ url: response.url(), status: response.status() }); });

  await page.route('**/api/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    let body = {};
    try { body = request.postDataJSON() || {}; } catch { body = {}; }
    if (url.pathname === '/api/ai/live-verification') {
      const mode = body.workload_mode || 'single';
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(liveResult(mode, body.text || '', `req-${mode}`, `nonce-${mode}`)) });
    }
    if (url.pathname === '/api/ai/burst-parse') {
      const cases = String(body.text || '').split(/\n\s*\n+/).filter(Boolean).map((text, index) => ({ id: `case-${String(index + 1).padStart(2, '0')}`, text }));
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', parsed_count: cases.length, cases }) });
    }
    if (url.pathname === '/api/ai/burst-verification') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(burstResult(body.reports || [])) });
    }
    if (url.pathname === '/api/product/messaging/webhook') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ normalized: true, source: body.source, provider: body.provider, external_id: body.external_id, urgency: 'RED', needType: 'rescue', human_review_required: true }) });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });

  async function clickWithEvidence(actionId, routePath, locator, resultLocator) {
    const before = await page.locator('body').innerText();
    await locator.click();
    await resultLocator.waitFor({ state: 'visible', timeout: 30000 });
    const after = await page.locator('body').innerText();
    clicks.push({
      action_id: actionId,
      route: routePath,
      selector_used: await locator.getAttribute('data-testid') || actionId,
      dom_selector_found: true,
      clicked: true,
      before_state_hash: hash(before),
      after_state_hash: hash(after),
      result_selector_found: true,
      post_click_assertion: before !== after ? 'PASS' : 'FAIL',
      observed_result_text: (await resultLocator.innerText()).slice(0, 800),
    });
  }

  try {
    const impactRoute = '/dashboard/amd-impact';
    await page.goto(`${baseUrl}${impactRoute}`, { waitUntil: 'domcontentloaded' });
    routes.push({ route: impactRoute, status: 'loaded' });
    await page.getByTestId('amd-single-input').fill('Lotus Warehouse: 17 people, possibly 21; two wheelchair users; east transformer road blocked; west route small vehicles; water lasts six hours.');
    await page.getByTestId('amd-single-consent').check();
    await clickWithEvidence('amd.single.run', impactRoute, page.getByTestId('amd-single-run'), page.getByTestId('amd-single-structured-result'));
    await page.getByText('VERIFIED LIVE AMD ANALYSIS').waitFor();
    await page.screenshot({ path: path.join(screenshotDir, 'amd-single.png'), fullPage: true });

    await page.getByRole('button', { name: /Complex Dossier/i }).click();
    await page.getByTestId('amd-complex-input').fill('REPORT-001 and REPORT-003 likely duplicate. REPORT-006 says bridge collapsed; REPORT-007 police says damaged, not collapsed. Community Hall 80 reduced to 43 with 67 registered. 12 insulin doses for 19 patients. Wheelchair-ramp van and oxygen-reserved van. Textile godown supersedes Clinic Road.');
    await page.locator('#dossier-consent').check();
    await clickWithEvidence('amd.dossier.run', impactRoute, page.getByTestId('amd-complex-run'), page.getByTestId('amd-complex-structured-result'));
    await page.screenshot({ path: path.join(screenshotDir, 'amd-dossier.png'), fullPage: true });

    await page.getByRole('button', { name: /Burst Workload/i }).click();
    await page.getByTestId('amd-burst-input').fill('Case one: 9 people need water.\n\nCase two: wheelchair user, north road blocked, south lane open.\n\nCase three: 12 insulin doses for 19 patients.');
    await clickWithEvidence('amd.burst.parse', impactRoute, page.getByTestId('amd-parse-burst'), page.getByTestId('amd-parsed-count'));
    const parsedCountRoot = page.getByTestId('amd-parsed-count');
    const parsedText = await parsedCountRoot.innerText();
    const parsedCountValue = (await parsedCountRoot.locator('strong').first().innerText()).trim();
    const parsedPreviewCount = await page.getByTestId('amd-parsed-preview').locator(':scope > div').count();
    if (parsedCountValue !== '3' || parsedPreviewCount !== 3) {
      throw new Error(
        `Expected exactly 3 parsed cases and 3 preview rows; count=${parsedCountValue}, previewRows=${parsedPreviewCount}, text=${parsedText}`,
      );
    }
    await page.getByTestId('amd-burst-consent').check();
    await clickWithEvidence('amd.burst.run', impactRoute, page.getByTestId('amd-run-burst'), page.getByTestId('amd-burst-result'));
    await page.getByText('AMD-GENERATED · NONCE-BOUND').waitFor();
    await page.screenshot({ path: path.join(screenshotDir, 'amd-burst.png'), fullPage: true });

    const intakeRoute = '/dashboard/intake';
    await page.goto(`${baseUrl}${intakeRoute}`, { waitUntil: 'domcontentloaded' });
    routes.push({ route: intakeRoute, status: 'loaded' });
    await clickWithEvidence('intake.normalize', intakeRoute, page.getByTestId('ai-intake-normalize-RM-001'), page.getByTestId('ai-intake-normalized-record'));
    await clickWithEvidence('intake.run_amd', intakeRoute, page.getByTestId('ai-intake-run-advisory'), page.getByTestId('ai-intake-operational-analysis'));
    await page.getByText('VERIFIED LIVE AMD ANALYSIS').waitFor();
    await page.screenshot({ path: path.join(screenshotDir, 'ai-intake.png'), fullPage: true });

    const capabilityRoute = '/dashboard/capability-map';
    await page.goto(`${baseUrl}${capabilityRoute}`, { waitUntil: 'domcontentloaded' });
    routes.push({ route: capabilityRoute, status: 'loaded' });
    const capabilityText = await page.locator('body').innerText();
    if (capabilityText.includes('Pending Verification') || capabilityText.includes('Default Model')) throw new Error('Capability Map contains forbidden placeholder copy.');
    await page.screenshot({ path: path.join(screenshotDir, 'capability-map.png'), fullPage: true });
  } finally {
    await browser.close();
  }

  const browserEvidence = {
    status: consoleErrors.length || pageErrors.length || failedRequests.length || unexpectedHttp.length ? 'FAIL' : 'PASS',
    console_errors: consoleErrors.length,
    page_errors: pageErrors.length,
    failed_requests: failedRequests.length,
    unexpected_4xx_5xx: unexpectedHttp.length,
    parser_regression_exact_count: 3,
    screenshots_captured: 4,
    screenshots_reviewed: 0,
    visual_checks_performed: [
      'required result regions became visible',
      'verified-live provenance banner became visible',
      'burst parsed exactly three cases',
      'forbidden placeholder copy absent on Capability Map',
    ],
    details: { consoleErrors, pageErrors, failedRequests, unexpectedHttp },
  };
  await fs.writeFile(path.join(evidenceRoot, 'browser-evidence.json'), JSON.stringify(browserEvidence, null, 2));
  await fs.writeFile(path.join(evidenceRoot, 'click-manifest.json'), JSON.stringify(clicks, null, 2));
  await fs.writeFile(path.join(evidenceRoot, 'route-matrix.json'), JSON.stringify({ routes }, null, 2));
  if (browserEvidence.status !== 'PASS' || clicks.some(click => click.post_click_assertion !== 'PASS')) {
    throw new Error('Browser evidence contains failures.');
  }
  console.log(`${title} PASS; routes=${routes.length}; clicks=${clicks.length}`);
}

main().catch(error => {
  console.error(`${title} failed: ${error.stack || error.message}`);
  process.exit(1);
});
