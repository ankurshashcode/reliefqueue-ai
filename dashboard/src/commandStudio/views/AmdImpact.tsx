import { useState } from 'react';
import {
  Cpu, Zap, Activity, ShieldAlert, Bot, Server, CheckCircle, XCircle,
  RefreshCw, Clock, Hash, Layers, AlertTriangle, FileText, List,
} from 'lucide-react';

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
}

interface BurstCaseResult extends LiveResult {
  case_id: string;
}

interface BurstResult {
  status: string;
  batch_id: string;
  started_at: string;
  completed_at: string;
  submitted: number;
  succeeded: number;
  failed: number;
  live_amd_responses: number;
  fallback_responses: number;
  total_elapsed_ms: number;
  median_latency_ms: number | null;
  p95_latency_ms: number | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  approximate_throughput_rps: number;
  active_model: string;
  served_model: string;
  runtime: string;
  accelerator: string;
  human_review_required: boolean;
  cases: BurstCaseResult[];
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
  return r?.verified_live === true && r?.fallback_used === false;
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
  const [burstLoading, setBurstLoading] = useState(false);
  const [burstResult, setBurstResult] = useState<BurstResult | null>(null);
  const [expandedCases, setExpandedCases] = useState<Set<string>>(new Set());

  // ── Single Incident ──────────────────────────────────────────────────────

  const runSingle = async () => {
    if (!singleConsent) return;
    setSingleLoading(true);
    setSingleResult(null);
    try {
      const res = await fetch('/api/ai/live-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: singleInput }),
      });
      const data: LiveResult = await res.json();
      setSingleResult(data);
    } catch (err: any) {
      setSingleResult({
        status: 'failed', verified_live: false, provider: 'AMD Developer Cloud',
        runtime: 'vLLM 0.23.0', accelerator: 'AMD Instinct MI300X',
        served_model: null, underlying_model: 'Qwen/Qwen2.5-7B-Instruct',
        request_id: null, verified_at: null, latency_ms: null,
        prompt_tokens: null, completion_tokens: null, total_tokens: null,
        fallback_used: true, human_review_required: true,
        generated_advisory: null,
        warnings: ['Network error contacting verification endpoint.'],
        error: err?.message || 'Network request failed',
      });
    } finally {
      setSingleLoading(false);
    }
  };

  // ── Complex Dossier ──────────────────────────────────────────────────────

  const runDossier = async () => {
    if (!dossierConsent || !dossierInput.trim()) return;
    setDossierLoading(true);
    setDossierResult(null);
    try {
      const res = await fetch('/api/ai/live-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: dossierInput }),
      });
      const data: LiveResult = await res.json();
      setDossierResult(data);
    } catch (err: any) {
      setDossierResult({
        status: 'failed', verified_live: false, provider: 'AMD Developer Cloud',
        runtime: 'vLLM 0.23.0', accelerator: 'AMD Instinct MI300X',
        served_model: null, underlying_model: 'Qwen/Qwen2.5-7B-Instruct',
        request_id: null, verified_at: null, latency_ms: null,
        prompt_tokens: null, completion_tokens: null, total_tokens: null,
        fallback_used: true, human_review_required: true,
        generated_advisory: null,
        warnings: ['Network error contacting verification endpoint.'],
        error: err?.message || 'Network request failed',
      });
    } finally {
      setDossierLoading(false);
    }
  };

  // ── Burst Workload ────────────────────────────────────────────────────────

  const parseBurstInput = (raw: string): { cases: { id: string; text: string }[] | null; error: string | null } => {
    const trimmed = raw.trim();
    if (!trimmed) return { cases: null, error: 'Input is empty.' };

    // Try JSON array
    if (trimmed.startsWith('[')) {
      try {
        const arr = JSON.parse(trimmed);
        if (!Array.isArray(arr)) return { cases: null, error: 'Expected a JSON array.' };
        const cases = arr.map((item, i) => {
          if (typeof item === 'string') return { id: `case-${i + 1}`, text: item };
          if (typeof item === 'object' && item !== null && 'text' in item) {
            return { id: String(item.id || `case-${i + 1}`), text: String(item.text || '') };
          }
          return { id: `case-${i + 1}`, text: JSON.stringify(item) };
        });
        return { cases, error: null };
      } catch {
        return { cases: null, error: 'Invalid JSON array.' };
      }
    }

    // Try JSONL
    const lines = trimmed.split('\n').filter(l => l.trim());
    if (lines[0].trim().startsWith('{')) {
      try {
        const cases = lines.map((line, i) => {
          const obj = JSON.parse(line);
          return { id: String(obj.id || `case-${i + 1}`), text: String(obj.text || '') };
        });
        return { cases, error: null };
      } catch {
        return { cases: null, error: 'Invalid JSONL — each line must be valid JSON with at least an "id" and "text" field.' };
      }
    }

    // One report per line
    const cases = lines.map((line, i) => ({ id: `case-${i + 1}`, text: line.trim() })).filter(c => c.text);
    return { cases, error: null };
  };

  const handleParseBurst = () => {
    const { cases, error } = parseBurstInput(burstInput);
    if (error) {
      setParsedCases(null);
      setParseError(error);
      return;
    }
    if (cases && cases.length > 24) {
      setParsedCases(null);
      setParseError(`Too many cases: ${cases.length} exceeds maximum of 24.`);
      return;
    }
    setParsedCases(cases);
    setParseError(null);
  };

  const runBurst = async () => {
    if (!parsedCases || parsedCases.length === 0) return;
    setBurstLoading(true);
    setBurstResult(null);
    setExpandedCases(new Set());
    try {
      const res = await fetch('/api/ai/burst-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reports: parsedCases, concurrency: burstConcurrency }),
      });
      const data: BurstResult = await res.json();
      if ((data as any).error) throw new Error((data as any).error);
      setBurstResult(data);
    } catch (err: any) {
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
          Long-context, multilingual and concurrent humanitarian analysis accelerated by AMD Instinct MI300X.
        </p>
      </div>

      {/* Infrastructure Info Cards — always factual, never "Pending" */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
        <InfraCard icon={<Server className="w-4 h-4" />} label="Inference Mode" value="Live AMD/vLLM" sub="Deterministic fallback available" />
        <InfraCard icon={<Cpu className="w-4 h-4 text-rq-primary" />} label="AMD Accelerator" value="AMD Instinct MI300X" sub="Provider: AMD Developer Cloud" highlight />
        <InfraCard icon={<Activity className="w-4 h-4" />} label="Runtime" value="vLLM 0.23.0" sub="OpenAI-compatible backend" />
        <InfraCard icon={<Layers className="w-4 h-4" />} label="Active Model" value="Qwen/Qwen2.5-7B-Instruct" sub="Served as: reliefqueue-amd" />
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
              className="mt-4 flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold px-6 py-3 rounded-xl text-sm transition-colors shadow"
            >
              {singleLoading
                ? <><RefreshCw className="w-4 h-4 animate-spin" /> Contacting AMD MI300X…</>
                : <><Zap className="w-4 h-4" /> Run My Input on AMD MI300X</>}
            </button>
          </div>

          {singleResult && <LiveResultPanel result={singleResult} label="Single Incident" />}
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
                    <AlertTriangle className="w-3 h-3" /> Dossier will be truncated to 4,000 characters before submission.
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
              className="mt-4 flex items-center gap-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-bold px-6 py-3 rounded-xl text-sm transition-colors shadow"
            >
              {dossierLoading
                ? <><RefreshCw className="w-4 h-4 animate-spin" /> Processing dossier on AMD MI300X…</>
                : <><Zap className="w-4 h-4" /> Run Complex Dossier on AMD MI300X</>}
            </button>
          </div>

          {dossierResult && <LiveResultPanel result={dossierResult} label="Complex Dossier" showOriginalInput />}
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
              Supported formats: one report per line · JSON array of strings · JSONL (<code className="bg-slate-100 px-1 rounded text-[11px]">{"{ \"id\": \"case-1\", \"text\": \"...\" }"}</code>).
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
                className="px-3 py-1.5 bg-blue-100 hover:bg-blue-200 text-blue-800 text-xs font-semibold rounded-lg transition-colors disabled:opacity-50"
              >
                Parse Workload
              </button>
              <button
                onClick={() => { setBurstInput(''); setParsedCases(null); setParseError(null); setBurstResult(null); }}
                className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-500 text-xs font-semibold rounded-lg transition-colors"
              >
                Clear
              </button>
            </div>
            <textarea
              value={burstInput}
              onChange={e => { setBurstInput(e.target.value); setParsedCases(null); setParseError(null); }}
              rows={10}
              className="w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y"
              placeholder="Paste reports here (one per line, JSON array, or JSONL) then click Parse Workload…"
            />

            {parseError && (
              <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> {parseError}
              </div>
            )}
            {parsedCases && (
              <div className="mt-2 p-2 bg-emerald-50 border border-emerald-200 rounded text-xs text-emerald-800 flex items-center gap-1.5">
                <CheckCircle className="w-3.5 h-3.5 shrink-0" />
                Parsed <strong>{parsedCases.length}</strong> case{parsedCases.length !== 1 ? 's' : ''} — ready to run (max 24).
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
              <button
                onClick={runBurst}
                disabled={burstLoading || !parsedCases || parsedCases.length === 0}
                data-action-id="amd.run_burst"
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
            <div className="space-y-4">
              {/* Aggregate stats */}
              <div className="bg-slate-900 text-white rounded-2xl p-6">
                <div className="text-slate-400 text-xs font-bold uppercase tracking-widest mb-1">Burst Verification Result</div>
                <div className="flex items-center gap-3 mb-4">
                  <div className={`text-2xl font-black ${burstResult.succeeded > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {burstResult.succeeded}/{burstResult.submitted} AMD Live Responses
                  </div>
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
                  <BurstStat label="Prompt Tokens" value={String(burstResult.prompt_tokens)} />
                  <BurstStat label="Completion Tokens" value={String(burstResult.completion_tokens)} />
                  <BurstStat label="Total Tokens" value={String(burstResult.total_tokens)} />
                  <BurstStat label="Throughput" value={`${burstResult.approximate_throughput_rps} req/s`} />
                  <BurstStat label="Model" value={burstResult.active_model} />
                  <BurstStat label="Accelerator" value={burstResult.accelerator} />
                  <BurstStat label="Succeeded" value={String(burstResult.succeeded)} green />
                  <BurstStat label="Failed" value={String(burstResult.failed)} red={burstResult.failed > 0} />
                  <BurstStat label="Human Review" value="Required" amber />
                </div>
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
                        const live = c.verified_live && !c.fallback_used;
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
          The Gemma 4 bonus lane is prepared for structured triage via the same vLLM/OpenAI-compatible backend. It is{' '}
          <strong>not the active model in this deployment.</strong>{' '}
          The currently active model is <strong>Qwen/Qwen2.5-7B-Instruct</strong> served as{' '}
          <code className="bg-slate-100 px-1 rounded">reliefqueue-amd</code> on AMD Instinct MI300X via vLLM 0.23.0.
          Human review is required regardless of which model is active.
        </div>
      </div>
    </div>
  );
}

// ─── Shared Sub-Components ────────────────────────────────────────────────────

function InfraCard({ icon, label, value, sub, highlight, amber }: {
  icon: React.ReactNode; label: string; value: string; sub: string;
  highlight?: boolean; amber?: boolean;
}) {
  return (
    <div className={`rounded-xl border p-3 shadow-sm ${highlight ? 'bg-rq-primary/5 border-rq-primary/20' : amber ? 'bg-amber-50 border-amber-200' : 'bg-white border-slate-200'}`}>
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
  return (
    <div className="space-y-4">
      {/* Banner */}
      <div className={`rounded-2xl p-5 flex items-start gap-4 shadow-md ${ok ? 'bg-emerald-50 border-2 border-emerald-400' : 'bg-red-50 border-2 border-red-400'}`}>
        <div className={`shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${ok ? 'bg-emerald-100' : 'bg-red-100'}`}>
          {ok ? <CheckCircle className="w-6 h-6 text-emerald-600" /> : <XCircle className="w-6 h-6 text-red-600" />}
        </div>
        <div className="flex-1">
          <div className={`text-xl font-black tracking-tight ${ok ? 'text-emerald-800' : 'text-red-800'}`}>
            {ok ? '✓ VERIFIED LIVE' : '✗ LIVE VERIFICATION FAILED'}
          </div>
          <div className={`text-sm font-medium mt-0.5 ${ok ? 'text-emerald-700' : 'text-red-700'}`}>
            {ok ? `Real AMD inference confirmed · ${label}` : result.error || 'AMD endpoint did not return a verified live response.'}
          </div>
          {result.warnings?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {result.warnings.map((w, i) => (
                <span key={i} className="text-[10px] bg-amber-50 border border-amber-200 text-amber-800 rounded px-2 py-0.5">{w}</span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Evidence grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        <ECard icon={<Server className="w-3.5 h-3.5" />} label="Provider" value={result.provider} />
        <ECard icon={<Cpu className="w-3.5 h-3.5" />} label="Accelerator" value={result.accelerator} />
        <ECard icon={<Activity className="w-3.5 h-3.5" />} label="Runtime" value={result.runtime} />
        <ECard icon={<Layers className="w-3.5 h-3.5" />} label="Served Model" value={result.served_model} />
        <ECard icon={<Bot className="w-3.5 h-3.5" />} label="Underlying Model" value={result.underlying_model} />
        <ECard icon={<Hash className="w-3.5 h-3.5" />} label="Request ID" value={result.request_id} mono />
        {result.challenge_nonce && <ECard icon={<Hash className="w-3.5 h-3.5" />} label="Challenge Nonce" value={result.challenge_nonce} mono />}
        <ECard icon={<Clock className="w-3.5 h-3.5" />} label="Verified At (UTC)" value={result.verified_at} mono />
        <ECard icon={<Zap className="w-3.5 h-3.5" />} label="Latency" value={result.latency_ms != null ? `${result.latency_ms} ms` : null} />
        <ECard icon={<Activity className="w-3.5 h-3.5" />} label="Tokens" value={result.prompt_tokens != null ? `${result.prompt_tokens}p / ${result.completion_tokens}c / ${result.total_tokens}t` : null} />
        <ECard icon={<CheckCircle className="w-3.5 h-3.5" />} label="Fallback Used" value={result.fallback_used ? 'Yes' : 'No'} highlight={result.fallback_used ? 'red' : 'green'} />
        <ECard icon={<ShieldAlert className="w-3.5 h-3.5" />} label="Human Review" value="Required" highlight="amber" />
      </div>

      {/* Input + Advisory */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {showOriginalInput && (result.original_input || result.sanitized_input) && (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
            <h4 className="font-bold text-slate-700 text-xs uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Bot className="w-3.5 h-3.5 text-slate-400" /> Original Input
            </h4>
            <p className="text-xs text-slate-600 bg-slate-50 rounded-lg p-2.5 border border-slate-100 font-mono leading-relaxed max-h-40 overflow-y-auto">
              {result.original_input || result.synthetic_input || '—'}
            </p>
            {result.sanitized_input && result.sanitized_input !== result.original_input && (
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
            <Zap className="w-3.5 h-3.5 text-rq-primary" /> Generated Advisory (from AMD vLLM)
          </h4>
          {result.generated_advisory ? (
            <p className="text-xs text-slate-800 bg-blue-50 rounded-lg p-2.5 border border-blue-100 leading-relaxed max-h-48 overflow-y-auto">
              {result.generated_advisory}
            </p>
          ) : (
            <p className="text-xs text-slate-400 italic">No advisory — verification did not succeed.</p>
          )}
          <span className="mt-2 inline-block bg-amber-100 text-amber-800 px-2 py-0.5 rounded text-[10px] font-bold">
            Human Review Required — Advisory only; no dispatch authority
          </span>
        </div>
      </div>
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
  const live = c.verified_live && !c.fallback_used;
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
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Generated Advisory</div>
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
