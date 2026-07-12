import { useEffect, useState } from 'react';
import {
  Cpu, Zap, Activity, ShieldAlert, Bot, Server, CheckCircle, XCircle,
  RefreshCw, Clock, Hash, Layers, AlertTriangle, FileText, List,
} from 'lucide-react';
import { AmdEvidenceSummary } from '../components/AmdEvidenceSummary';
import {
  currentRequestFromBurstResult,
  currentRequestFromLiveResult,
  fetchAmdCapability,
  pendingCurrentRequest,
  type AmdCapabilityPayload,
  type CurrentRequestPlane,
} from '../lib/amdEvidence';

// ─── Types ────────────────────────────────────────────────────────────────────

interface LiveResult {
  status: string;
  verified_live: boolean;
  provider: string | null;
  runtime: string | null;
  accelerator: string | null;
  served_model: string | null;
  underlying_model: string | null;
  request_id: string | null;
  challenge_nonce?: string | null;
  verified_at: string | null;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  fallback_used: boolean;
  human_review_required: boolean;
  synthetic_input?: string | null;
  original_input?: string | null;
  sanitized_input?: string | null;
  generated_advisory: string | null;
  warnings: string[];
  error: string | null;
  workload_mode?: string;
  structured_output?: any;
  normalized_structured_record?: any;
  source_evidence_mapping?: any[];
  operational_analysis?: any;
  compact_json?: any;
  request_settings?: any;
  context_budget?: any;
  model_metadata?: any;
  analysis_source?: 'provider' | 'local_safe_fallback' | 'none' | string;
  provider_transport_verified_live?: boolean;
  provider_response_received?: boolean;
  nonce_sent_to_provider?: boolean;
  nonce_echoed_by_provider?: boolean;
  verification_bound_to_nonce?: boolean;
  verification_failure_reason?: string;
  provider_call_count?: number;
  provider_request_ids?: string[];
  provider_prompt_tokens?: number;
  provider_completion_tokens?: number;
  provider_total_tokens?: number;
  provider_latency_ms?: number;
  semantic_completeness?: boolean;
  semantic_issues?: string[];
  repair_attempted?: boolean;
  repair_succeeded?: boolean;
  repair_reason?: string[];
  repair_evidence?: any;
  deterministic_prompt_support?: {
    source_report_count?: number;
    calculation_candidate_count?: number;
    conflict_update_signal_count?: number;
    support_type?: string;
    final_analysis_source?: string;
  } | null;
  synthetic_text_sent?: boolean;
  private_text_sent?: boolean;
  secret_values_exposed?: boolean;
}

interface BurstCaseResult extends LiveResult {
  case_id: string;
}

interface BurstResult {
  status: string;
  verified_live?: boolean;
  fallback_used?: boolean;
  batch_id: string;
  started_at: string;
  completed_at: string;
  submitted: number;
  parsed?: number;
  succeeded: number;
  failed: number;
  live_amd_responses: number;
  live_provider_calls_succeeded?: number;
  provider_call_count?: number;
  fallback_responses: number;
  total_elapsed_ms: number;
  median_latency_ms: number | null;
  p95_latency_ms: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  synthesis_prompt_tokens?: number;
  synthesis_completion_tokens?: number;
  synthesis_total_tokens?: number;
  provider_prompt_tokens?: number;
  provider_completion_tokens?: number;
  provider_total_tokens?: number;
  approximate_throughput_rps: number;
  active_model: string;
  served_model: string;
  runtime: string;
  accelerator: string;
  human_review_required: boolean;
  cases: BurstCaseResult[];
  parsed_preview?: { id: string; text: string }[];
  cross_case_synthesis?: any;
  cross_case_evidence?: LiveResult;
  request_settings?: any;
  model_metadata?: any;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const DEFAULT_SINGLE_INPUT = `Flood situation near north sector riverbank. Three families require rescue and medical support. One elderly resident needs insulin. Children present. Location: near old bridge pillar.`;

const COMPLEX_DOSSIER_EXAMPLE = `[REPORT-001 | 2024-01-15 06:12 | SMS]
Flood near Sector 7 bridge. 5 log stuck on roof. Need baat aur khana. Kids bhi hain.

[REPORT-002 | 2024-01-15 06:18 | WhatsApp]
Bahut paani aa gaya north embankment mein. Hamara ghar dub raha hai. Teenager aur ek pregnant lady hai. Please jaldi bhejo.

[REPORT-003 | 2024-01-15 06:19 | SMS]
OCR: F100d s1tuat10n @ S3ct0r-7 br1dg3. Fam1ly of 4. Med1c1ne reqd. D1abet1c patient.

[REPORT-004 | 2024-01-15 06:31 | Field Radio]
Shelter B at school is 80% full. Capacity 120, currently 96 adults + 18 children. Running low on drinking water - 40 liters left. Generator fuel 6 hours remaining.

[REPORT-005 | 2024-01-15 06:35 | SMS]
Sector 7 bridge area - 5 people on roof needing rescue. Repeat of earlier report but now 1 person has fallen into water briefly - recovered but needs medical check.

[REPORT-006 | 2024-01-15 06:44 | WhatsApp forward — UNVERIFIED SOCIAL MEDIA]
Rumour: Road via Ward 13 east is completely blocked by military checkpoint. Cannot confirm. Source: unknown social post.

[REPORT-007 | 2024-01-15 07:02 | IVR]
Mujhe ambulance chahiye relief hub west ke paas. Meri maa ko sugar ki problem hai. Insulin khatam ho gayi. Address: relief hub west lane 4.

[REPORT-008 | 2024-01-15 07:05 | Field Coordinator]
Ward 13 east road: confirmed blocked by fallen tree + debris, not checkpoint. Alternative route via Sector 9 south road operational. Estimated clearance 4-6 hours.

[REPORT-009 | 2024-01-15 07:08 | SMS]
3 families at north sector riverbank need evacuation. 12 people total including 2 elderly and 1 disabled person (wheelchair). Location unclear - somewhere near pump station.

[REPORT-010 | 2024-01-15 07:11 | WhatsApp]
North embankment - now 15 people according to neighbour. Earlier count of 12 may be wrong. All need evacuation. Water level rising.

[REPORT-011 | 2024-01-15 07:15 | Field Worker]
Shelter A at community hall: capacity 80, occupied 67. Has kitchen. Accessible for wheelchairs. Currently accepting new arrivals.

[REPORT-012 | 2024-01-15 07:22 | SMS]
Bacche aur bujurg log sector 7 mein phanse hain. Boat chahiye. Khana nahi hai 18 ghante se. Paani bhi nahi peena ka.

[REPORT-013 | 2024-01-15 07:30 | Update — Field Team Alpha]
North embankment count confirmed 12 people (not 15). 2 elderly, 1 wheelchair user, 2 children under 5, 1 pregnancy (approx 32 weeks). Boat dispatched ETA 25 min.

[REPORT-014 | 2024-01-15 07:33 | SMS]
Relief hub west mein 200 rice bags aur 150 water cans available. Truck driver needs route clearance confirmation before moving.

[REPORT-015 | 2024-01-15 07:40 | Field Coordinator]
Sector 7 bridge roof rescue complete - all 5 evacuated to shelter B. Medical check needed for 1 adult (water exposure). Shelter B now 101/120.

[REPORT-016 | 2024-01-15 07:45 | SMS]
OCR corrupt: Sh3lt3r B n3arly fu11. N33d ov3rfl0w pl@n. 20 m0re p30p1e c0ming.

[REPORT-017 | 2024-01-15 07:50 | WhatsApp]
Insulin delivery needed at relief hub west lane 4. Diabetic elderly woman. Critical. Has been 24 hours without medication.

[REPORT-018 | 2024-01-15 07:55 | Field Radio]
Road via Sector 9 south now passable for small vehicles. Heavy trucks still not advised. Medical runner can use this route.

[REPORT-019 | 2024-01-15 08:00 | IVR]
We are 6 people at pump station area near north river. Need food water rescue. Ek aadmi ko chest pain ho raha hai - medical emergency.`;

const BURST_EXAMPLE_CASES = [
  { id: "burst-001", text: "Family of 4 stranded on rooftop near Sector 7 bridge. Need boat rescue. Children aged 3 and 7 present." },
  { id: "burst-002", text: "Elderly woman at relief hub west lane 4 needs insulin urgently. Diabetic, 24 hours without medication." },
  { id: "burst-003", text: "Shelter B at school almost full (101/120). 20 more people incoming from north sector. Need overflow plan." },
  { id: "burst-004", text: "Road blocked via Ward 13 east due to fallen tree. Alternative route via Sector 9 south operational for small vehicles." },
  { id: "burst-005", text: "12 people confirmed at north embankment including 2 elderly, 1 wheelchair user, 2 infants, 1 pregnant woman. Boat en route." },
  { id: "burst-006", text: "Sector 9 medical runner requesting route clearance to deliver insulin from relief hub west to pump station area." },
  { id: "burst-007", text: "Chest pain reported at pump station area near north river. 6 people present, 1 possible cardiac event. Medical team needed." },
  { id: "burst-008", text: "Relief hub west has 200 rice bags and 150 water cans. Truck driver requesting route confirmation before dispatch." },
  { id: "burst-009", text: "Shelter A at community hall: 67/80 occupied. Wheelchair accessible. Kitchen operational. Accepting new arrivals." },
  { id: "burst-010", text: "Shelter B water supply: 40 liters remaining. Request emergency water delivery for 101 current occupants." },
  { id: "burst-011", text: "Sector 7 bridge rescue complete. 5 evacuated. 1 adult needs medical check for water exposure. Now at Shelter B." },
  { id: "burst-012", text: "Generator fuel at Shelter B: 6 hours remaining. Request fuel delivery for overnight operations at 120-capacity school shelter." },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function isVerified(r: LiveResult | null) {
  return r?.verified_live === true
    && r?.fallback_used === false
    && r?.analysis_source === 'provider'
    && r?.verification_bound_to_nonce === true;
}

function parseTokenEstimate(text: string): number {
  return Math.ceil(text.length / 4);
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function AmdImpact() {
  const [activeTab, setActiveTab] = useState<'single' | 'dossier' | 'burst'>('single');

  // Single incident
  const [singleInput, setSingleInput] = useState(DEFAULT_SINGLE_INPUT);
  const [singleConsent, setSingleConsent] = useState(false);
  const [singleLoading, setSingleLoading] = useState(false);
  const [singleResult, setSingleResult] = useState<LiveResult | null>(null);

  // Complex dossier
  const [dossierInput, setDossierInput] = useState('');
  const [dossierConsent, setDossierConsent] = useState(false);
  const [dossierLoading, setDossierLoading] = useState(false);
  const [dossierResult, setDossierResult] = useState<LiveResult | null>(null);

  // Burst workload
  const [burstInput, setBurstInput] = useState('');
  const [parsedCases, setParsedCases] = useState<{ id: string; text: string }[] | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [burstConcurrency, setBurstConcurrency] = useState(4);
  const [burstConsent, setBurstConsent] = useState(false);
  const [burstLoading, setBurstLoading] = useState(false);
  const [burstResult, setBurstResult] = useState<BurstResult | null>(null);
  const [expandedCases, setExpandedCases] = useState<Set<string>>(new Set());

  // Frozen historical evidence, current configuration, and current-request state
  // are deliberately loaded and displayed as separate planes.
  const [capability, setCapability] = useState<AmdCapabilityPayload | null>(null);
  const [capabilityLoading, setCapabilityLoading] = useState(true);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState<CurrentRequestPlane | null>(null);
  const [lastVerifiedMetadata, setLastVerifiedMetadata] = useState<any | null>(null);

  const refreshEvidence = async () => {
    setCapabilityLoading(true);
    setCapabilityError(null);
    try {
      setCapability(await fetchAmdCapability());
    } catch (error: any) {
      setCapabilityError(error?.message || 'Unknown error');
    } finally {
      setCapabilityLoading(false);
    }
  };

  useEffect(() => { void refreshEvidence(); }, []);

  const historicalDeployment = capability?.historical_evidence?.deployment || null;
  const latestMetadata = lastVerifiedMetadata;
  const metadataSource = latestMetadata ? 'Latest verified request' : historicalDeployment ? 'Historical verified campaign' : 'Evidence unavailable';
  const displayedProvider = latestMetadata?.provider || historicalDeployment?.provider || 'Not reported';
  const displayedAccelerator = latestMetadata?.accelerator || historicalDeployment?.accelerator || 'Not reported';
  const displayedRuntime = latestMetadata?.runtime || historicalDeployment?.runtime || 'Not reported';
  const displayedModel = latestMetadata?.underlying_model || latestMetadata?.served_model || historicalDeployment?.underlying_model || historicalDeployment?.served_model || 'Not reported';
  const displayedModelSub = latestMetadata?.underlying_model
    ? `Latest verified request · served as ${latestMetadata?.served_model || 'not reported'}`
    : latestMetadata?.served_model
      ? 'Latest verified request · underlying model not reported'
      : historicalDeployment
        ? `Historical campaign · served as ${historicalDeployment.served_model}`
        : 'No model claim available';
  const inferenceMode = lastRequest?.verified_live
    ? 'Verified live request'
    : capability?.live_runtime?.configured
      ? 'Configured · not live verified'
      : capability
        ? 'Historical evidence only'
        : 'Checking evidence';

  // ── Single Incident ──────────────────────────────────────────────────────

  const runSingle = async () => {
    if (!singleConsent) return;
    setSingleLoading(true);
    setSingleResult(null);
    setLastRequest(pendingCurrentRequest('Single-incident live verification is in progress.'));
    try {
      const res = await fetch('/api/ai/live-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: singleInput, workload_mode: 'single', synthetic_confirmed: true }),
      });
      const data: LiveResult = await res.json();
      setSingleResult(data);
      setLastRequest(currentRequestFromLiveResult(data));
      if (isVerified(data)) setLastVerifiedMetadata({ ...data, ...(data.model_metadata || {}) });
    } catch (err: any) {
      const failure: LiveResult = {
        status: 'failed', verified_live: false, provider: 'AMD Developer Cloud',
        runtime: null, accelerator: 'AMD Instinct MI300X',
        served_model: null, underlying_model: null,
        request_id: null, verified_at: null, latency_ms: null,
        prompt_tokens: null, completion_tokens: null, total_tokens: null,
        fallback_used: true, human_review_required: true,
        generated_advisory: null,
        warnings: ['Network error contacting verification endpoint.'],
        error: err?.message || 'Network request failed',
      };
      setSingleResult(failure);
      setLastRequest(currentRequestFromLiveResult(failure));
    } finally {
      setSingleLoading(false);
    }
  };

  // ── Complex Dossier ──────────────────────────────────────────────────────

  const runDossier = async () => {
    if (!dossierConsent || !dossierInput.trim()) return;
    setDossierLoading(true);
    setDossierResult(null);
    setLastRequest(pendingCurrentRequest('Complex-dossier live verification is in progress.'));
    try {
      const res = await fetch('/api/ai/live-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: dossierInput, workload_mode: 'complex_dossier', synthetic_confirmed: true }),
      });
      const data: LiveResult = await res.json();
      setDossierResult(data);
      setLastRequest(currentRequestFromLiveResult(data));
      if (isVerified(data)) setLastVerifiedMetadata({ ...data, ...(data.model_metadata || {}) });
    } catch (err: any) {
      const failure: LiveResult = {
        status: 'failed', verified_live: false, provider: 'AMD Developer Cloud',
        runtime: null, accelerator: 'AMD Instinct MI300X',
        served_model: null, underlying_model: null,
        request_id: null, verified_at: null, latency_ms: null,
        prompt_tokens: null, completion_tokens: null, total_tokens: null,
        fallback_used: true, human_review_required: true,
        generated_advisory: null,
        warnings: ['Network error contacting verification endpoint.'],
        error: err?.message || 'Network request failed',
      };
      setDossierResult(failure);
      setLastRequest(currentRequestFromLiveResult(failure));
    } finally {
      setDossierLoading(false);
    }
  };

  // ── Burst Workload ────────────────────────────────────────────────────────

  const handleParseBurst = async () => {
    try {
      const res = await fetch('/api/ai/burst-parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: burstInput }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || data?.message || 'Unable to parse burst workload.');
      setParsedCases(data.cases);
      setParseError(null);
    } catch (err: any) {
      setParsedCases(null);
      setParseError(err?.message || 'Unable to parse burst workload.');
    }
  };

  const runBurst = async () => {
    if (!burstConsent || !parsedCases || parsedCases.length === 0) return;
    setBurstLoading(true);
    setBurstResult(null);
    setExpandedCases(new Set());
    setLastRequest(pendingCurrentRequest('Burst live verification is in progress.'));
    try {
      const res = await fetch('/api/ai/burst-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reports: parsedCases, concurrency: burstConcurrency, synthetic_confirmed: true }),
      });
      const data: BurstResult = await res.json();
      if ((data as any).error) throw new Error((data as any).error);
      setBurstResult(data);
      setLastRequest(currentRequestFromBurstResult(data));
      if (data.verified_live === true && Number(data.fallback_responses || 0) === 0) {
        setLastVerifiedMetadata({ ...data, ...(data.cross_case_evidence || {}), ...(data.cross_case_evidence?.model_metadata || data.model_metadata || {}) });
      }
    } catch (err: any) {
      setLastRequest({
        attempted: true,
        verified_live: false,
        fallback_used: null,
        provider_error: err?.message || 'Burst verification failed',
        note: 'Burst verification did not establish a verified-live result.',
      });
      alert(`Burst verification failed: ${err?.message || 'Unknown error'}`);
    } finally {
      setBurstLoading(false);
    }
  };

  const toggleCaseExpand = (id: string) => {
    setExpandedCases(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto h-full overflow-y-auto">

      {/* Header */}
      <div className="mb-6">
        <h2 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">AMD GPU / vLLM Impact</h2>
        <p className="text-slate-500 mt-1">
          Frozen AMD/vLLM campaign evidence plus opt-in, nonce-bound verification of the current request path.
        </p>
      </div>

      <AmdEvidenceSummary
        capability={capability}
        loading={capabilityLoading}
        error={capabilityError}
        currentRequest={lastRequest}
        onRefresh={() => void refreshEvidence()}
      />

      {/* Infrastructure cards identify whether values come from historical evidence or a verified request. */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
        <InfraCard testId="amd-inference-mode" icon={<Server className="w-4 h-4" />} label="Inference Mode" value={inferenceMode} sub="Live status is established per request; fallback is never counted as verified" />
        <InfraCard icon={<Cpu className="w-4 h-4 text-rq-primary" />} label="AMD Accelerator" value={displayedAccelerator} sub={`${metadataSource} · ${displayedProvider}`} highlight />
        <InfraCard icon={<Activity className="w-4 h-4" />} label="Runtime" value={displayedRuntime} sub={metadataSource} />
        <InfraCard icon={<Layers className="w-4 h-4" />} label="Active Model" value={displayedModel} sub={displayedModelSub} />
        <InfraCard icon={<ShieldAlert className="w-4 h-4 text-emerald-600" />} label="Data Safety" value="Synthetic input only" sub="Private text: false · Secrets: false" />
        <InfraCard icon={<CheckCircle className="w-4 h-4 text-amber-600" />} label="Human Review" value="Required" sub="No autonomous dispatch" amber />
      </div>

      {/* Workload Tabs */}
      <div className="flex gap-1 mb-6 bg-slate-100 p-1 rounded-xl w-fit">
        {(['single', 'dossier', 'burst'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
              activeTab === tab
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {tab === 'single' ? 'A. Single Incident' : tab === 'dossier' ? 'B. Complex Dossier' : 'C. Burst Workload'}
          </button>
        ))}
      </div>

      {/* ── Tab A: Single Incident ───────────────────────────────────────────── */}
      {activeTab === 'single' && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
            <h3 className="font-bold text-slate-900 mb-1 flex items-center gap-2">
              <FileText className="w-5 h-5 text-rq-primary" /> Single Incident — Judge Input
            </h3>
            <p className="text-sm text-slate-500 mb-4">Edit the synthetic report below, confirm it contains no real personal information, and submit it directly to the AMD MI300X endpoint.</p>
            <textarea
              value={singleInput}
              onChange={e => setSingleInput(e.target.value)}
              data-testid="amd-single-input"
              rows={5}
              className="w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-rq-primary resize-y"
              placeholder="Enter your synthetic incident report here…"
            />
            <div className="flex items-center gap-3 mt-4">
              <label className="flex items-start gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={singleConsent}
                  onChange={e => setSingleConsent(e.target.checked)}
                  data-testid="amd-single-consent"
                  className="mt-0.5 w-4 h-4 rounded accent-rq-primary"
                />
                <span className="text-xs text-slate-600">
                  I confirm this is synthetic demonstration data and contains no real personal information.
                </span>
              </label>
            </div>
            <button
              onClick={runSingle}
              disabled={singleLoading || !singleConsent || !singleInput.trim()}
              data-action-id="amd.run_single_incident"
              data-testid="amd-single-run"
              className="mt-4 flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold px-6 py-3 rounded-xl text-sm transition-colors shadow"
            >
              {singleLoading
                ? <><RefreshCw className="w-4 h-4 animate-spin" /> Contacting AMD MI300X…</>
                : <><Zap className="w-4 h-4" /> Run My Input on AMD MI300X</>}
            </button>
          </div>

          {singleResult && <div data-testid="amd-single-structured-result"><LiveResultPanel result={singleResult} label="Single Incident" showOriginalInput /></div>}
        </div>
      )}

      {/* ── Tab B: Complex Dossier ───────────────────────────────────────────── */}
      {activeTab === 'dossier' && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
            <h3 className="font-bold text-slate-900 mb-1 flex items-center gap-2">
              <FileText className="w-5 h-5 text-purple-600" /> Complex Multi-Report Dossier
            </h3>
            <p className="text-sm text-slate-500 mb-4">
              Paste a large mixture of reports, updates, OCR text, multilingual content, and conflicting information.
              The AMD MI300X endpoint will process the full dossier and return a structured advisory.
            </p>
            <div className="flex gap-3 mb-3">
              <button
                onClick={() => setDossierInput(COMPLEX_DOSSIER_EXAMPLE)}
                className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition-colors"
              >
                Load Complex Flood Dossier Example
              </button>
              <button
                onClick={() => { setDossierInput(''); setDossierResult(null); }}
                className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-500 text-xs font-semibold rounded-lg transition-colors"
              >
                Clear
              </button>
            </div>
            <textarea
              value={dossierInput}
              onChange={e => setDossierInput(e.target.value)}
              data-testid="amd-complex-input"
              rows={14}
              className="w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-purple-400 resize-y"
              placeholder="Paste your complex dossier here, or click Load Example above…"
            />
            {/* Token estimate */}
            {dossierInput && (
              <div className="mt-2 flex gap-4 text-xs text-slate-500">
                <span>Characters: <strong className="text-slate-700">{dossierInput.length.toLocaleString()}</strong></span>
                <span>~Tokens: <strong className="text-slate-700">{parseTokenEstimate(dossierInput).toLocaleString()}</strong></span>
                <span>Safe max: <strong className="text-slate-700">~6,000 tokens</strong></span>
                {parseTokenEstimate(dossierInput) > 6000 && (
                  <span className="text-amber-600 font-semibold flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" /> Dossier exceeds the reviewed context estimate and will be rejected rather than silently truncated.
                  </span>
                )}
              </div>
            )}
            <div className="flex items-start gap-2 mt-4">
              <input
                type="checkbox"
                id="dossier-consent"
                checked={dossierConsent}
                onChange={e => setDossierConsent(e.target.checked)}
                className="mt-0.5 w-4 h-4 rounded accent-purple-600"
              />
              <label htmlFor="dossier-consent" className="text-xs text-slate-600 cursor-pointer">
                I confirm this is synthetic demonstration data and contains no real personal information.
              </label>
            </div>
            <button
              onClick={runDossier}
              disabled={dossierLoading || !dossierConsent || !dossierInput.trim()}
              data-action-id="amd.run_complex_dossier"
              data-testid="amd-complex-run"
              className="mt-4 flex items-center gap-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-bold px-6 py-3 rounded-xl text-sm transition-colors shadow"
            >
              {dossierLoading
                ? <><RefreshCw className="w-4 h-4 animate-spin" /> Processing dossier on AMD MI300X…</>
                : <><Zap className="w-4 h-4" /> Run Complex Dossier on AMD MI300X</>}
            </button>
          </div>

          {dossierResult && <div data-testid="amd-complex-structured-result"><LiveResultPanel result={dossierResult} label="Complex Dossier" showOriginalInput /></div>}
        </div>
      )}

      {/* ── Tab C: Burst Workload ─────────────────────────────────────────────── */}
      {activeTab === 'burst' && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
            <h3 className="font-bold text-slate-900 mb-1 flex items-center gap-2">
              <List className="w-5 h-5 text-blue-600" /> Burst Workload — Batch of Incidents
            </h3>
            <p className="text-sm text-slate-500 mb-4">
              Submit up to 24 synthetic incident reports at once. Each case gets a unique challenge nonce and fresh AMD request.
              Supported formats: blank-line-separated reports · JSON array of strings · JSONL (<code className="bg-slate-100 px-1 rounded text-[11px]">{"{ \"id\": \"case-1\", \"text\": \"...\" }"}</code>).
            </p>
            <div className="flex gap-3 mb-3 flex-wrap">
              <button
                onClick={() => {
                  const jsonl = BURST_EXAMPLE_CASES.map(c => JSON.stringify(c)).join('\n');
                  setBurstInput(jsonl);
                  setParsedCases(null);
                  setParseError(null);
                }}
                className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition-colors"
              >
                Load 12-Case Example
              </button>
              <button
                onClick={handleParseBurst}
                disabled={!burstInput.trim()}
                data-testid="amd-parse-burst"
                className="px-3 py-1.5 bg-blue-100 hover:bg-blue-200 text-blue-800 text-xs font-semibold rounded-lg transition-colors disabled:opacity-50"
              >
                Parse Workload
              </button>
              <button
                onClick={() => { setBurstInput(''); setParsedCases(null); setParseError(null); setBurstResult(null); setBurstConsent(false); }}
                className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-500 text-xs font-semibold rounded-lg transition-colors"
              >
                Clear
              </button>
            </div>
            <textarea
              value={burstInput}
              onChange={e => { setBurstInput(e.target.value); setParsedCases(null); setParseError(null); }}
              data-testid="amd-burst-input"
              rows={10}
              className="w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y"
              placeholder="Paste reports here (separate multiline reports with a blank line, or use JSON/JSONL), then click Parse Workload…"
            />

            {parseError && (
              <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> {parseError}
              </div>
            )}
            {parsedCases && (
              <div data-testid="amd-parsed-count" className="mt-2 p-2 bg-emerald-50 border border-emerald-200 rounded text-xs text-emerald-800">
                <div className="flex items-center gap-1.5">
                <CheckCircle className="w-3.5 h-3.5 shrink-0" />
                Parsed <strong>{parsedCases.length}</strong> case{parsedCases.length !== 1 ? 's' : ''} — ready to run (max 24).
                </div>
                <div data-testid="amd-parsed-preview" className="mt-2 grid gap-1 text-[11px] text-emerald-900">
                  {parsedCases.slice(0, 6).map(c => <div key={c.id}><strong>{c.id}</strong>: {c.text.slice(0, 110)}</div>)}
                </div>
              </div>
            )}

            <div className="mt-4 flex flex-wrap gap-6 items-end">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">Concurrency</label>
                <select
                  value={burstConcurrency}
                  onChange={e => setBurstConcurrency(Number(e.target.value))}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
                >
                  {[1, 2, 4, 6, 8].map(n => (
                    <option key={n} value={n}>{n} concurrent{n === 4 ? ' (default)' : ''}</option>
                  ))}
                </select>
              </div>
              <label className="flex items-start gap-2 cursor-pointer select-none max-w-md">
                <input
                  type="checkbox"
                  checked={burstConsent}
                  onChange={e => setBurstConsent(e.target.checked)}
                  data-testid="amd-burst-consent"
                  className="mt-0.5 w-4 h-4 rounded accent-blue-600"
                />
                <span className="text-xs text-slate-600">
                  I confirm every parsed case is synthetic demonstration data and contains no real personal information.
                </span>
              </label>
              <button
                onClick={runBurst}
                disabled={burstLoading || !burstConsent || !parsedCases || parsedCases.length === 0}
                data-action-id="amd.run_burst"
                data-testid="amd-run-burst"
                className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold px-6 py-3 rounded-xl text-sm transition-colors shadow"
              >
                {burstLoading
                  ? <><RefreshCw className="w-4 h-4 animate-spin" /> Running burst on AMD MI300X…</>
                  : <><Zap className="w-4 h-4" /> Run Burst on AMD MI300X</>}
              </button>
            </div>
          </div>

          {/* Burst Results */}
          {burstResult && (
            <div className="space-y-4" data-testid="amd-burst-result">
              {/* Aggregate stats */}
              <div className="bg-slate-900 text-white rounded-2xl p-6">
                <div className="text-slate-400 text-xs font-bold uppercase tracking-widest mb-1">Burst Verification Result</div>
                <div className="flex items-center gap-3 mb-4">
                  <div className={`text-2xl font-black ${burstResult.verified_live ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {burstResult.verified_live ? '✓ VERIFIED LIVE BATCH + SYNTHESIS' : 'PARTIAL / UNVERIFIED BATCH'}
                  </div>
                  <span className="text-xs text-slate-300">{burstResult.succeeded}/{burstResult.submitted} nonce-bound case analyses</span>
                  {burstResult.fallback_responses > 0 && (
                    <span className="bg-amber-700 text-amber-100 text-xs font-bold px-2 py-0.5 rounded">
                      {burstResult.fallback_responses} fallback
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <BurstStat label="Batch ID" value={burstResult.batch_id} mono />
                  <BurstStat label="Started" value={burstResult.started_at} />
                  <BurstStat label="Completed" value={burstResult.completed_at} />
                  <BurstStat label="Total Elapsed" value={`${burstResult.total_elapsed_ms} ms`} />
                  <BurstStat label="Median Latency" value={burstResult.median_latency_ms != null ? `${burstResult.median_latency_ms} ms` : '—'} />
                  <BurstStat label="P95 Latency" value={burstResult.p95_latency_ms != null ? `${burstResult.p95_latency_ms} ms` : '—'} />
                  <BurstStat label="Case Prompt Tokens" value={String(burstResult.prompt_tokens)} />
                  <BurstStat label="Case Completion Tokens" value={String(burstResult.completion_tokens)} />
                  <BurstStat label="Case Total Tokens" value={String(burstResult.total_tokens)} />
                  <BurstStat label="Synthesis Tokens" value={String(burstResult.synthesis_total_tokens ?? burstResult.cross_case_evidence?.total_tokens ?? '—')} />
                  <BurstStat label="All Provider Tokens" value={String(burstResult.provider_total_tokens ?? '—')} />
                  <BurstStat label="Throughput" value={`${burstResult.approximate_throughput_rps} req/s`} />
                  <BurstStat label="Model" value={burstResult.active_model} />
                  <BurstStat label="Accelerator" value={burstResult.accelerator} />
                  <BurstStat label="Parsed" value={String(burstResult.parsed ?? burstResult.submitted)} />
                  <BurstStat label="Provider Calls" value={String(burstResult.provider_call_count ?? '—')} />
                  <BurstStat label="Succeeded" value={String(burstResult.succeeded)} green={burstResult.succeeded === burstResult.submitted} />
                  <BurstStat label="Failed" value={String(burstResult.failed)} red={burstResult.failed > 0} />
                  <BurstStat label="Human Review" value="Required" amber />
                </div>
                {burstResult.cross_case_synthesis && (
                  <div data-testid="amd-burst-cross-case-synthesis" className="mt-5 bg-slate-800 border border-slate-700 rounded-xl p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                      <div className="text-slate-300 text-xs font-bold uppercase tracking-widest">Cross-Case Command-Centre Synthesis</div>
                      <span className={`text-[10px] font-bold px-2 py-1 rounded ${isVerified(burstResult.cross_case_evidence || null) ? 'bg-emerald-700 text-emerald-50' : 'bg-amber-700 text-amber-50'}`}>
                        {isVerified(burstResult.cross_case_evidence || null) ? 'AMD-GENERATED · NONCE-BOUND' : `${burstResult.cross_case_evidence?.analysis_source || 'unknown source'} · NOT VERIFIED`}
                      </span>
                    </div>
                    {burstResult.cross_case_evidence && (
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3 text-[10px] text-slate-300">
                        <div>Request: <span className="font-mono text-white">{burstResult.cross_case_evidence.request_id || '—'}</span></div>
                        <div>Nonce: <span className="font-mono text-white">{burstResult.cross_case_evidence.challenge_nonce || '—'}</span></div>
                        <div>Latency: <span className="text-white">{burstResult.cross_case_evidence.latency_ms ?? '—'} ms</span></div>
                        <div>Fallback: <span className="text-white">{burstResult.cross_case_evidence.fallback_used ? 'Yes' : 'No'}</span></div>
                      </div>
                    )}
                    <pre className="text-xs text-slate-100 whitespace-pre-wrap overflow-auto max-h-80">{JSON.stringify(burstResult.cross_case_synthesis, null, 2)}</pre>
                  </div>
                )}
              </div>

              {/* Per-case table */}
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="p-4 border-b border-slate-200 bg-slate-50">
                  <h4 className="font-bold text-slate-900">Per-Case Results</h4>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200">
                        {['Case ID', 'Status', 'Request ID', 'Nonce', 'Latency', 'Tokens', 'Fallback', 'Review', 'Details'].map(h => (
                          <th key={h} className="px-3 py-2 text-left text-[10px] font-bold text-slate-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {burstResult.cases.map(c => {
                        const live = isVerified(c);
                        const isExpanded = expandedCases.has(c.case_id);
                        return [
                          <tr key={c.case_id} className="border-b border-slate-100 hover:bg-slate-50">
                            <td className="px-3 py-2 font-mono font-bold text-slate-900">{c.case_id}</td>
                            <td className="px-3 py-2">
                              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${live ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                                {live ? 'LIVE' : 'FALLBACK'}
                              </span>
                            </td>
                            <td className="px-3 py-2 font-mono text-slate-600 max-w-[120px] truncate">{c.request_id || '—'}</td>
                            <td className="px-3 py-2 font-mono text-slate-600">{c.challenge_nonce || '—'}</td>
                            <td className="px-3 py-2 text-slate-700">{c.latency_ms != null ? `${c.latency_ms} ms` : '—'}</td>
                            <td className="px-3 py-2 text-slate-700">{c.total_tokens != null ? c.total_tokens : '—'}</td>
                            <td className="px-3 py-2">
                              <span className={c.fallback_used ? 'text-amber-600 font-semibold' : 'text-emerald-600 font-semibold'}>
                                {c.fallback_used ? 'Yes' : 'No'}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-amber-700 font-semibold">Yes</td>
                            <td className="px-3 py-2">
                              <button
                                onClick={() => toggleCaseExpand(c.case_id)}
                                className="text-rq-primary hover:underline text-[10px] font-semibold"
                              >
                                {isExpanded ? 'Hide' : 'View Details'}
                              </button>
                            </td>
                          </tr>,
                          isExpanded && (
                            <tr key={`${c.case_id}-detail`} className="bg-slate-50 border-b border-slate-200">
                              <td colSpan={9} className="px-4 py-3">
                                <CaseDetailPanel c={c} />
                              </td>
                            </tr>
                          ),
                        ];
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Gemma 4 — truthful experimental label */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden mt-8 ring-1 ring-purple-200/50">
        <div className="p-4 border-b border-slate-200 bg-purple-50/50 flex justify-between items-center">
          <h3 className="font-bold text-purple-900 flex items-center gap-2 text-sm">
            <Bot className="w-4 h-4 text-purple-500" /> Gemma 4 Bonus Lane
          </h3>
          <span className="bg-slate-100 text-slate-600 text-[10px] font-bold px-2 py-1 rounded uppercase tracking-wider border border-slate-200">
            Experimental bonus lane — not active in this deployment
          </span>
        </div>
        <div className="p-4 text-xs text-slate-600">
          The Gemma 4 bonus lane is prepared for structured triage via the same OpenAI-compatible backend, but it is{' '}
          <strong>not active in this deployment.</strong>{' '}
          The served/underlying model identity shown above is labelled by source: either the frozen historical campaign or a nonce-bound verified request.
          Current runtime configuration alone is never presented as verified live. Human review is required regardless of which model is active.
        </div>
      </div>
    </div>
  );
}

// ─── Shared Sub-Components ────────────────────────────────────────────────────

function InfraCard({ icon, label, value, sub, highlight, amber, testId }: {
  icon: React.ReactNode; label: string; value: string; sub: string;
  highlight?: boolean; amber?: boolean; testId?: string;
}) {
  return (
    <div data-testid={testId} className={`rounded-xl border p-3 shadow-sm ${highlight ? 'bg-rq-primary/5 border-rq-primary/20' : amber ? 'bg-amber-50 border-amber-200' : 'bg-white border-slate-200'}`}>
      <div className="flex items-center gap-1.5 text-slate-500 text-[10px] font-bold uppercase tracking-wider mb-1">
        {icon} {label}
      </div>
      <div className={`text-xs font-bold leading-tight ${highlight ? 'text-rq-primary' : amber ? 'text-amber-800' : 'text-slate-900'}`}>{value}</div>
      <div className="text-[10px] text-slate-400 mt-0.5 leading-tight">{sub}</div>
    </div>
  );
}

function LiveResultPanel({ result, label, showOriginalInput }: {
  result: LiveResult; label: string; showOriginalInput?: boolean;
}) {
  const ok = isVerified(result);
  const localFallback = result.analysis_source === 'local_safe_fallback';
  const providerIncomplete = result.analysis_source === 'provider_incomplete';
  const providerUnbound = result.provider_response_received === true && !ok && !localFallback;
  const bannerClass = ok
    ? 'bg-emerald-50 border-2 border-emerald-400'
    : localFallback || providerUnbound
      ? 'bg-amber-50 border-2 border-amber-400'
      : 'bg-red-50 border-2 border-red-400';
  const iconClass = ok ? 'bg-emerald-100' : localFallback || providerUnbound ? 'bg-amber-100' : 'bg-red-100';
  const titleClass = ok ? 'text-emerald-800' : localFallback || providerUnbound ? 'text-amber-800' : 'text-red-800';
  const bodyClass = ok ? 'text-emerald-700' : localFallback || providerUnbound ? 'text-amber-700' : 'text-red-700';
  const title = ok
    ? '✓ VERIFIED LIVE AMD ANALYSIS'
    : localFallback
      ? 'LOCAL SAFE FALLBACK — NOT LIVE AMD ANALYSIS'
      : providerUnbound
        ? 'AMD RESPONSE RECEIVED — VERIFICATION INCOMPLETE'
        : '✗ LIVE VERIFICATION FAILED';
  const subtitle = ok
    ? `Provider-generated, nonce-bound analysis confirmed · ${label}`
    : localFallback
      ? 'The provider response could not be safely used as structured analysis. Local deterministic fallback is shown and labelled.'
      : providerUnbound
        ? result.verification_failure_reason || (providerIncomplete ? 'AMD returned structured JSON, but required operational sections were incomplete.' : 'The provider response was not bound to the displayed challenge nonce or was otherwise incomplete.')
        : result.error || 'AMD endpoint did not return a usable response.';

  return (
    <div className="space-y-4">
      <div className={`rounded-2xl p-5 flex items-start gap-4 shadow-md ${bannerClass}`}>
        <div className={`shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${iconClass}`}>
          {ok
            ? <CheckCircle className="w-6 h-6 text-emerald-600" />
            : localFallback || providerUnbound
              ? <AlertTriangle className="w-6 h-6 text-amber-600" />
              : <XCircle className="w-6 h-6 text-red-600" />}
        </div>
        <div className="flex-1">
          <div className={`text-xl font-black tracking-tight ${titleClass}`}>{title}</div>
          <div className={`text-sm font-medium mt-0.5 ${bodyClass}`}>{subtitle}</div>
          {result.warnings?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {result.warnings.map((w, i) => (
                <span key={i} className="text-[10px] bg-amber-50 border border-amber-200 text-amber-800 rounded px-2 py-0.5">{w}</span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        <ECard icon={<Server className="w-3.5 h-3.5" />} label="Provider" value={result.provider} />
        <ECard icon={<Cpu className="w-3.5 h-3.5" />} label="Accelerator" value={result.accelerator} />
        <ECard icon={<Activity className="w-3.5 h-3.5" />} label="Runtime" value={result.runtime} />
        <ECard icon={<Layers className="w-3.5 h-3.5" />} label="Served Model" value={result.served_model} />
        <ECard icon={<Bot className="w-3.5 h-3.5" />} label="Underlying Model" value={result.underlying_model || 'Not reported by endpoint'} />
        <ECard icon={<Hash className="w-3.5 h-3.5" />} label="Request ID" value={result.request_id} mono />
        <ECard icon={<Hash className="w-3.5 h-3.5" />} label="Challenge Nonce" value={result.challenge_nonce} mono />
        <ECard icon={<Clock className="w-3.5 h-3.5" />} label="Verified At (UTC)" value={result.verified_at} mono />
        <ECard icon={<Zap className="w-3.5 h-3.5" />} label="Latency" value={result.latency_ms != null ? `${result.latency_ms} ms` : null} />
        <ECard icon={<Activity className="w-3.5 h-3.5" />} label="Displayed Analysis Tokens" value={result.prompt_tokens != null ? `${result.prompt_tokens}p / ${result.completion_tokens}c / ${result.total_tokens}t` : null} />
        <ECard icon={<Activity className="w-3.5 h-3.5" />} label="Provider Calls" value={result.provider_call_count != null ? String(result.provider_call_count) : '1'} />
        <ECard icon={<Activity className="w-3.5 h-3.5" />} label="All Provider Tokens" value={result.provider_total_tokens != null ? String(result.provider_total_tokens) : result.total_tokens != null ? String(result.total_tokens) : null} />
        <ECard
          icon={<CheckCircle className="w-3.5 h-3.5" />}
          label="Semantic Completeness"
          value={result.semantic_completeness === false ? 'Failed' : result.semantic_completeness === true ? 'Passed' : 'Not evaluated'}
          highlight={result.semantic_completeness === false ? 'red' : result.semantic_completeness === true ? 'green' : undefined}
        />
        <ECard
          icon={<Activity className="w-3.5 h-3.5" />}
          label="AMD Repair Pass"
          value={result.repair_attempted ? (result.repair_succeeded ? 'Used · Passed' : 'Used · Failed') : 'Not needed'}
          highlight={result.repair_attempted ? (result.repair_succeeded ? 'green' : 'red') : undefined}
        />
        <ECard
          icon={<FileText className="w-3.5 h-3.5" />}
          label="Deterministic Prompt Support"
          value={result.deterministic_prompt_support
            ? `${result.deterministic_prompt_support.source_report_count ?? '—'} sources · ${result.deterministic_prompt_support.calculation_candidate_count ?? 0} arithmetic anchors`
            : 'Not used'}
        />
        <ECard icon={<FileText className="w-3.5 h-3.5" />} label="Analysis Source" value={result.analysis_source || 'not reported'} highlight={result.analysis_source === 'provider' ? 'green' : result.analysis_source === 'local_safe_fallback' ? 'amber' : 'red'} />
        <ECard icon={<CheckCircle className="w-3.5 h-3.5" />} label="Nonce Bound" value={result.verification_bound_to_nonce ? 'Yes' : 'No'} highlight={result.verification_bound_to_nonce ? 'green' : 'red'} />
        <ECard icon={<CheckCircle className="w-3.5 h-3.5" />} label="Fallback Used" value={result.fallback_used ? 'Yes' : 'No'} highlight={result.fallback_used ? 'red' : 'green'} />
        <ECard icon={<ShieldAlert className="w-3.5 h-3.5" />} label="Human Review" value="Required" highlight="amber" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {showOriginalInput && (result.original_input || result.sanitized_input) && (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
            <h4 className="font-bold text-slate-700 text-xs uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Bot className="w-3.5 h-3.5 text-slate-400" /> Original Input
            </h4>
            <p className="text-xs text-slate-600 bg-slate-50 rounded-lg p-2.5 border border-slate-100 font-mono leading-relaxed max-h-40 overflow-y-auto">
              {result.original_input || result.synthetic_input || '—'}
            </p>
            {result.sanitized_input && (
              <>
                <h4 className="font-bold text-slate-700 text-xs uppercase tracking-wider mb-2 mt-3 flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5 text-emerald-500" /> Sanitized Input Sent to AMD
                </h4>
                <p className="text-xs text-slate-600 bg-emerald-50 rounded-lg p-2.5 border border-emerald-100 font-mono leading-relaxed max-h-40 overflow-y-auto">
                  {result.sanitized_input}
                </p>
              </>
            )}
          </div>
        )}
        {!showOriginalInput && (result.synthetic_input || result.original_input) && (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
            <h4 className="font-bold text-slate-700 text-xs uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Bot className="w-3.5 h-3.5 text-slate-400" /> Synthetic Input Sent
            </h4>
            <p className="text-xs text-slate-600 bg-slate-50 rounded-lg p-2.5 border border-slate-100 font-mono leading-relaxed">
              {result.synthetic_input || result.original_input}
            </p>
            <p className="text-[10px] text-slate-400 mt-1">Privacy-safe synthetic data only.</p>
          </div>
        )}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
          <h4 className="font-bold text-slate-700 text-xs uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-rq-primary" /> {result.analysis_source === 'provider' ? 'AMD-Generated Situation Summary' : result.analysis_source === 'provider_incomplete' ? 'AMD-Generated Incomplete Summary' : 'Local Safe Fallback Summary'}
          </h4>
          {result.generated_advisory ? (
            <p className={`text-xs rounded-lg p-2.5 border leading-relaxed max-h-48 overflow-y-auto ${result.analysis_source === 'provider' ? 'text-slate-800 bg-blue-50 border-blue-100' : result.analysis_source === 'provider_incomplete' ? 'text-amber-900 bg-amber-50 border-amber-200' : 'text-amber-900 bg-amber-50 border-amber-200'}`}>
              {result.generated_advisory}
            </p>
          ) : (
            <p className="text-xs text-slate-400 italic">No usable advisory was produced.</p>
          )}
          <span className="mt-2 inline-block bg-amber-100 text-amber-800 px-2 py-0.5 rounded text-[10px] font-bold">
            Human Review Required — Advisory only; no dispatch authority
          </span>
        </div>
      </div>

      {result.semantic_issues && result.semantic_issues.length > 0 && (
        <div className="bg-amber-50 rounded-xl border border-amber-300 shadow-sm p-4" data-testid="amd-semantic-issues">
          <h4 className="font-bold text-amber-900 text-xs uppercase tracking-wider mb-2">Deterministic Completeness Defects</h4>
          <ul className="list-disc pl-5 text-xs text-amber-900 space-y-1">
            {result.semantic_issues.map((issue, index) => <li key={index}>{issue}</li>)}
          </ul>
        </div>
      )}

      {result.structured_output && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <h4 className="font-bold text-slate-700 text-xs uppercase tracking-wider">Structured Sections</h4>
            <span className={`text-[10px] font-bold px-2 py-1 rounded ${result.analysis_source === 'provider' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>
              {result.analysis_source === 'provider' ? 'Complete provider output' : result.analysis_source === 'provider_incomplete' ? 'Incomplete provider output' : 'Local safe fallback'}
            </span>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 text-xs">
            <StructuredBlock title="Situation Summary" value={result.structured_output.situation_summary} />
            <StructuredBlock title="Critical Facts / Consolidated Incidents" value={result.structured_output.critical_facts || result.structured_output.consolidated_incidents} />
            <StructuredBlock title="Contradictions" value={result.structured_output.contradictions} />
            <StructuredBlock title="Superseded / Unverified Updates" value={[...(result.structured_output.superseded_updates || []), ...(result.structured_output.unverified_claims || [])]} />
            <StructuredBlock title="Risk / Capacity / Resource Implications" value={result.structured_output.risk_escalators || result.structured_output.capacity_pressure || result.structured_output.resource_gaps} />
            <StructuredBlock title="Route and Access Analysis" value={result.structured_output.route_and_access_analysis || result.structured_output.route_constraints} />
            <StructuredBlock title="Ranked Operational Plan" value={result.structured_output.recommended_priorities || result.structured_output.prioritized_operational_plan} />
            <StructuredBlock title="Missing Information / Coordinator Questions" value={result.structured_output.missing_information || result.structured_output.coordinator_questions || result.structured_output.missing_information_questions} />
            <StructuredBlock title="Confidence / Warnings" value={[...(result.structured_output.confidence_notes || []), ...(result.structured_output.warnings || [])]} />
          </div>
        </div>
      )}

      {result.source_evidence_mapping && result.source_evidence_mapping.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
          <h4 className="font-bold text-slate-700 text-xs uppercase tracking-wider mb-3">Field | Source Evidence | Normalized Value | Confidence</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <tbody>
                {result.source_evidence_mapping.map((row, idx) => (
                  <tr key={idx} className="border-b border-slate-100">
                    <td className="py-2 pr-3 font-bold text-slate-700">{row.field}</td>
                    <td className="py-2 pr-3 text-slate-500">{row.source_evidence}</td>
                    <td className="py-2 pr-3 text-slate-800">{row.normalized_value}</td>
                    <td className="py-2 text-slate-600">{row.confidence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(result.compact_json || result.structured_output || result.request_settings || result.context_budget) && (
        <div className="bg-slate-900 text-white rounded-xl p-4">
          <h4 className="font-bold text-slate-300 text-xs uppercase tracking-wider mb-2">Compact JSON</h4>
          <pre className="text-xs whitespace-pre-wrap overflow-auto max-h-96">{JSON.stringify({
            provenance: {
              verified_live: result.verified_live,
              provider_response_received: result.provider_response_received,
              analysis_source: result.analysis_source,
              fallback_used: result.fallback_used,
              challenge_nonce: result.challenge_nonce,
              nonce_sent_to_provider: result.nonce_sent_to_provider,
              nonce_echoed_by_provider: result.nonce_echoed_by_provider,
              verification_bound_to_nonce: result.verification_bound_to_nonce,
            },
            structured_output: result.compact_json || result.structured_output,
            request_settings: result.request_settings,
            context_budget: result.context_budget,
            model_metadata: result.model_metadata,
          }, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

function StructuredBlock({ title, value }: { title: string; value: any }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 min-h-24">
      <div className="font-bold text-slate-500 uppercase tracking-wider text-[10px] mb-1">{title}</div>
      <pre className="whitespace-pre-wrap break-words text-slate-800 font-sans">{typeof value === 'string' ? value : JSON.stringify(value ?? '—', null, 2)}</pre>
    </div>
  );
}

function ECard({ icon, label, value, mono, highlight }: {
  icon: React.ReactNode; label: string; value: string | number | null | undefined;
  mono?: boolean; highlight?: 'amber' | 'red' | 'green';
}) {
  const hl = highlight === 'amber' ? 'text-amber-700 bg-amber-50' :
    highlight === 'red' ? 'text-red-700 bg-red-50' :
    highlight === 'green' ? 'text-emerald-700 bg-emerald-50' : 'text-slate-900';
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-3 shadow-sm">
      <div className="flex items-center gap-1.5 text-slate-500 text-[10px] font-bold uppercase tracking-wider mb-1.5">{icon}{label}</div>
      <div className={`text-xs font-semibold break-all leading-tight ${mono ? 'font-mono' : ''} ${hl}`}>
        {value != null && value !== '' ? String(value) : <span className="text-slate-300 italic font-normal">—</span>}
      </div>
    </div>
  );
}

function BurstStat({ label, value, mono, green, red, amber }: {
  label: string; value: string; mono?: boolean; green?: boolean; red?: boolean; amber?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] text-slate-400 uppercase tracking-wider">{label}</div>
      <div className={`text-sm font-semibold ${mono ? 'font-mono' : ''} ${green ? 'text-emerald-400' : red ? 'text-red-400' : amber ? 'text-amber-400' : 'text-white'}`}>
        {value}
      </div>
    </div>
  );
}

function CaseDetailPanel({ c }: { c: BurstCaseResult }) {
  const live = isVerified(c);
  return (
    <div className="space-y-2 text-xs">
      <div className="flex flex-wrap gap-4">
        <div><span className="text-slate-400 font-semibold">Request ID:</span> <span className="font-mono text-slate-800">{c.request_id || '—'}</span></div>
        <div><span className="text-slate-400 font-semibold">Nonce:</span> <span className="font-mono text-slate-800">{c.challenge_nonce || '—'}</span></div>
        <div><span className="text-slate-400 font-semibold">Timestamp:</span> <span className="font-mono text-slate-800">{c.verified_at || '—'}</span></div>
        <div><span className="text-slate-400 font-semibold">Latency:</span> <span className="text-slate-800">{c.latency_ms != null ? `${c.latency_ms} ms` : '—'}</span></div>
        <div><span className="text-slate-400 font-semibold">Tokens:</span> <span className="text-slate-800">{c.total_tokens ?? '—'}</span></div>
        <div><span className="text-slate-400 font-semibold">Fallback:</span> <span className={c.fallback_used ? 'text-amber-600 font-bold' : 'text-emerald-600 font-bold'}>{c.fallback_used ? 'Yes' : 'No'}</span></div>
        <div><span className="text-slate-400 font-semibold">Live:</span> <span className={live ? 'text-emerald-600 font-bold' : 'text-red-600 font-bold'}>{live ? 'Yes' : 'No'}</span></div>
      </div>
      {(c.original_input || c.sanitized_input) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {c.original_input && (
            <div>
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Original Input</div>
              <div className="bg-slate-100 rounded p-2 font-mono text-slate-700 leading-relaxed">{c.original_input}</div>
            </div>
          )}
          {c.sanitized_input && (
            <div>
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Sanitized Input</div>
              <div className="bg-slate-100 rounded p-2 font-mono text-slate-700 leading-relaxed">{c.sanitized_input}</div>
            </div>
          )}
        </div>
      )}
      {c.generated_advisory && (
        <div>
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">{c.analysis_source === 'provider' ? 'AMD-Generated Advisory' : c.analysis_source === 'provider_incomplete' ? 'AMD-Generated Incomplete Advisory' : 'Local Safe Fallback Summary'}</div>
          <div className="bg-blue-50 border border-blue-100 rounded p-2 text-slate-700 leading-relaxed">{c.generated_advisory}</div>
          <span className="mt-1 inline-block bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded text-[10px] font-bold">Human Review Required</span>
        </div>
      )}
      {c.warnings?.length > 0 && (
        <div>
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Warnings</div>
          <ul className="space-y-0.5">
            {c.warnings.map((w, i) => <li key={i} className="text-amber-700 bg-amber-50 rounded px-2 py-0.5">{w}</li>)}
          </ul>
        </div>
      )}
      {c.error && (
        <div className="text-red-700 bg-red-50 rounded p-2">{c.error}</div>
      )}
    </div>
  );
}
