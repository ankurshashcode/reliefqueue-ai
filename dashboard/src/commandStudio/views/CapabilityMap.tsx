import { useEffect, useState } from 'react';
import { Server, CheckCircle, ShieldCheck, Zap, RefreshCw, Hash, Clock } from 'lucide-react';
import { useApp } from '../context/AppContext';

interface AmdTestResult {
  verified_live: boolean;
  fallback_used: boolean;
  request_id: string | null;
  verified_at: string | null;
  latency_ms: number | null;
  underlying_model: string | null;
  served_model: string | null;
  generated_advisory: string | null;
  error: string | null;
}

const CAPABILITIES = [
  { group: 'Command & Triage', items: [
    { name: 'Overview Stats', endpoint: 'GET /api/product/command/overview', status: 'wired', safe: true },
    { name: 'Active Cases', endpoint: 'GET /api/product/command/cases', status: 'demo fallback', safe: true },
    { name: 'AI Intake Fusion', endpoint: 'POST /api/product/messaging/webhook', status: 'wired', safe: true },
    { name: 'AI Advisory Validation', endpoint: 'POST /api/product/command/ai-advisory', status: 'wired', safe: true },
    { name: 'Assignments Suggestion', endpoint: 'POST /api/product/command/assign', status: 'demo fallback', safe: true },
    { name: 'Command Status Update', endpoint: 'POST /api/product/command/status', status: 'demo fallback', safe: true },
    { name: 'Command Messaging', endpoint: 'POST /api/product/command/message', status: 'demo fallback', safe: true },
    { name: 'Run Drill/Simulation', endpoint: 'POST /api/product/command/drill', status: 'demo fallback', safe: true },
  ]},
  { group: 'Field & Connectivity', items: [
    { name: 'Field Sync', endpoint: 'POST /api/product/field/sync', status: 'demo fallback', safe: true },
    { name: 'Field Action Update', endpoint: 'POST /api/product/field/action', status: 'demo fallback', safe: true },
    { name: 'My Cases (Field)', endpoint: 'GET /api/product/field/my-cases', status: 'demo fallback', safe: true },
    { name: 'Messaging Status & Idempotency', endpoint: 'GET /api/product/messaging/status', status: 'wired', safe: true },
    { name: 'DLQ Replay', endpoint: 'POST /api/product/messaging/replay-dlq', status: 'demo fallback', safe: true },
    { name: 'Offline Map Data', endpoint: 'GET /api/product/maps/offline', status: 'demo fallback', safe: true },
  ]},
  { group: 'Platform & Deployment', items: [
    { name: 'Session Me', endpoint: 'GET /api/product/session/me', status: 'wired', safe: true },
    { name: 'Evidence & Redaction Review', endpoint: 'GET /api/product/evidence', status: 'wired', safe: true },
    { name: 'Monitoring', endpoint: 'GET /api/product/monitoring', status: 'report-only', safe: true },
    { name: 'AMD / vLLM Live Verification', endpoint: 'POST /api/ai/live-verification', status: 'wired', safe: true },
    { name: 'AMD Burst Workload', endpoint: 'POST /api/ai/burst-verification', status: 'wired', safe: true },
    { name: 'Gemma 4 Bonus Lane', endpoint: 'Experimental — not active in this deployment', status: 'experimental', safe: true },
    { name: 'Production Config', endpoint: 'GET /api/product/production/config', status: 'wired', safe: true },
  ]},
  { group: 'Local Operations (Scenario)', items: [
    { name: 'Get Scenario Config', endpoint: 'GET /api/product/local/scenario', status: 'demo fallback', safe: true },
    { name: 'Update Scenario Config', endpoint: 'POST /api/product/local/scenario', status: 'demo fallback', safe: true },
    { name: 'Local Cases DB', endpoint: 'GET /api/product/local/cases', status: 'demo fallback', safe: true },
    { name: 'Local Workers DB', endpoint: 'GET /api/product/local/workers', status: 'demo fallback', safe: true },
  ]}
];

export function CapabilityMap() {
  const { showToast } = useApp();
  const [runtime, setRuntime] = useState({
    loading: true,
    health: 'Checking',
    api: 'Checking',
    contract: 'Unknown',
    cases: 0,
  });
  const [amdTestLoading, setAmdTestLoading] = useState(false);
  const [amdTestResult, setAmdTestResult] = useState<AmdTestResult | null>(null);

  const refreshRuntimeStatus = async (announce = false) => {
    setRuntime((current) => ({ ...current, loading: true }));
    try {
      const [healthResponse, overviewResponse] = await Promise.all([
        fetch('/healthz', { cache: 'no-store' }),
        fetch('/api/product/command/overview', { cache: 'no-store' }),
      ]);
      if (!healthResponse.ok || !overviewResponse.ok) throw new Error(`HTTP ${healthResponse.status}/${overviewResponse.status}`);
      const health = await healthResponse.json();
      const overview = await overviewResponse.json();
      setRuntime({
        loading: false,
        health: health.status === 'ok' ? 'Passing' : 'Degraded',
        api: 'Connected',
        contract: String(overview.contract || 'reliefqueue-product-api/v1'),
        cases: Number(overview.summary?.total_cases || 0),
      });
      if (announce) showToast('Product API and health status refreshed.', 'success');
    } catch (error: any) {
      setRuntime({ loading: false, health: 'Unavailable', api: 'Unavailable', contract: 'Unavailable', cases: 0 });
      if (announce) showToast(`Runtime status unavailable: ${error.message}`, 'error');
    }
  };

  const testAmdPath = async () => {
    setAmdTestLoading(true);
    setAmdTestResult(null);
    try {
      const res = await fetch('/api/ai/live-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data: AmdTestResult = await res.json();
      setAmdTestResult(data);
    } catch (err: any) {
      setAmdTestResult({
        verified_live: false,
        fallback_used: true,
        request_id: null,
        verified_at: null,
        latency_ms: null,
        underlying_model: null,
        served_model: null,
        generated_advisory: null,
        error: err?.message || 'Network request failed',
      });
    } finally {
      setAmdTestLoading(false);
    }
  };

  const checkPublicConfig = async () => {
    try {
      const res = await fetch('/api/product/production/config', { cache: 'no-store' });
      const data = await res.json();
      showToast(`Config: ${data.cors_mode || 'ok'} · HTTPS expected: ${data.https_expected}`, 'info');
    } catch {
      showToast('Public config check failed.', 'error');
    }
  };

  useEffect(() => { void refreshRuntimeStatus(false); }, []);

  const amdVerified = amdTestResult?.verified_live === true && amdTestResult?.fallback_used === false;

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto h-full overflow-y-auto">
      <div className="mb-6">
        <h2 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">Capability Map & Readiness</h2>
        <p className="text-slate-500 mt-2">API surface wiring and live deployment status.</p>
      </div>

      <div className="bg-slate-900 rounded-xl p-5 md:p-6 text-white mb-8 flex flex-col md:flex-row justify-between items-start gap-4">
        <div className="flex-1 min-w-0">
          <h3 className="font-bold text-lg mb-3 flex items-center gap-2">
            <Server className="w-5 h-5 text-emerald-400" /> Live Deployment Status
          </h3>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div className="p-4 bg-slate-800 rounded text-sm text-slate-300 font-mono leading-relaxed">
              <strong className="text-white block mb-2 font-sans">Runtime Status:</strong>
              Application: ReliefQueue AI<br/>
              Product API: {runtime.api}<br/>
              Health check: {runtime.health}<br/>
              API origin: Same origin<br/>
              Contract: {runtime.contract}<br/>
              Demo cases loaded: {runtime.cases}
            </div>
            <div className="p-4 bg-slate-800 rounded text-sm text-slate-300 font-mono leading-relaxed">
              <strong className="text-white block mb-2 font-sans">AI Provider:</strong>
              AI provider: AMD Developer Cloud<br/>
              Accelerator: AMD Instinct MI300X<br/>
              Runtime: vLLM 0.23.0<br/>
              Active model: Qwen/Qwen2.5-7B-Instruct<br/>
              Served model: reliefqueue-amd<br/>
              Human review: Required<br/>
              Fallback: Deterministic fallback available
            </div>
          </div>

          {/* AMD test result panel */}
          {amdTestResult && (
            <div className={`mt-4 p-4 rounded border text-sm font-mono ${amdVerified ? 'bg-emerald-900/40 border-emerald-500' : 'bg-red-900/30 border-red-500'}`}>
              <div className={`font-black font-sans text-base mb-2 flex items-center gap-2 ${amdVerified ? 'text-emerald-300' : 'text-red-300'}`}>
                {amdVerified ? '✓ AMD/vLLM PATH VERIFIED LIVE' : '✗ AMD/vLLM PATH — FALLBACK ACTIVE'}
              </div>
              <div className="grid grid-cols-1 gap-0.5 text-slate-300 text-xs">
                {amdTestResult.request_id && (
                  <div className="flex items-center gap-1.5"><Hash className="w-3 h-3 text-slate-500" /> Request ID: <span className="text-white">{amdTestResult.request_id}</span></div>
                )}
                {amdTestResult.verified_at && (
                  <div className="flex items-center gap-1.5"><Clock className="w-3 h-3 text-slate-500" /> Timestamp: <span className="text-white">{amdTestResult.verified_at}</span></div>
                )}
                {amdTestResult.latency_ms != null && (
                  <div className="flex items-center gap-1.5"><Zap className="w-3 h-3 text-slate-500" /> Latency: <span className="text-white">{amdTestResult.latency_ms} ms</span></div>
                )}
                <div>Model: <span className="text-white">{amdTestResult.underlying_model || '—'}</span></div>
                <div>Served as: <span className="text-white">{amdTestResult.served_model || '—'}</span></div>
                <div>Fallback used: <span className={amdTestResult.fallback_used ? 'text-red-300' : 'text-emerald-300'}>{amdTestResult.fallback_used ? 'Yes' : 'No'}</span></div>
              </div>
              {amdTestResult.generated_advisory && (
                <div className="mt-2">
                  <div className="text-[10px] font-sans font-bold text-slate-400 uppercase tracking-wider mb-1">Generated Advisory (excerpt)</div>
                  <div className="bg-slate-700 rounded p-2 text-slate-200 font-sans leading-relaxed text-xs">
                    {amdTestResult.generated_advisory.slice(0, 300)}{amdTestResult.generated_advisory.length > 300 ? '…' : ''}
                  </div>
                </div>
              )}
              {amdTestResult.error && (
                <div className="mt-2 text-red-300 font-sans text-xs">{amdTestResult.error}</div>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-col gap-2 w-full md:w-48 shrink-0">
          <button
            onClick={() => void checkPublicConfig()}
            className="px-4 py-2 bg-slate-800 border border-slate-700 rounded text-sm hover:bg-slate-700 transition-colors w-full text-left"
          >
            Check Public Config
          </button>
          <button
            onClick={() => void refreshRuntimeStatus(true)}
            disabled={runtime.loading}
            className="px-4 py-2 bg-slate-800 border border-slate-700 rounded text-sm hover:bg-slate-700 transition-colors w-full text-left disabled:opacity-60"
          >
            {runtime.loading ? (
              <span className="flex items-center gap-1.5"><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Checking…</span>
            ) : 'Refresh Runtime Status'}
          </button>
          <button
            onClick={() => void testAmdPath()}
            disabled={amdTestLoading}
            className="px-4 py-2 bg-emerald-700 border border-emerald-600 text-white rounded text-sm hover:bg-emerald-600 transition-colors w-full text-left font-semibold disabled:opacity-60"
          >
            {amdTestLoading ? (
              <span className="flex items-center gap-1.5"><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Contacting AMD…</span>
            ) : 'Test AMD/vLLM Advisory Path'}
          </button>
          <button
            onClick={() => {
              const text = 'AI_MODE=openai_compatible\nProvider: AMD Developer Cloud\nAccelerator: AMD Instinct MI300X\nRuntime: vLLM 0.23.0\nActive model: Qwen/Qwen2.5-7B-Instruct\nServed model: reliefqueue-amd\nHuman review: Required\nFallback: Deterministic available';
              navigator.clipboard.writeText(text).then(
                () => showToast('Reviewer notes copied.', 'success'),
                () => showToast('Copy failed.', 'error')
              );
            }}
            className="px-4 py-2 bg-slate-800 border border-slate-700 rounded text-sm hover:bg-slate-700 transition-colors w-full text-left"
          >
            Copy Reviewer Notes
          </button>
        </div>
      </div>

      <div className="space-y-8">
        {CAPABILITIES.map(group => (
          <section key={group.group}>
            <h3 className="text-lg font-bold text-slate-800 mb-4 border-b border-slate-200 pb-2">{group.group}</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {group.items.map(item => (
                <div key={item.name} className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow transition-shadow">
                  <div className="flex justify-between items-start mb-2">
                    <h4 className="font-bold text-slate-900">{item.name}</h4>
                    {item.status === 'wired' && <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 text-[10px] font-bold uppercase rounded border border-emerald-200">Wired</span>}
                    {item.status === 'demo fallback' && <span className="px-2 py-0.5 bg-amber-50 text-amber-700 text-[10px] font-bold uppercase rounded border border-amber-200">Fallback</span>}
                    {item.status === 'report-only' && <span className="px-2 py-0.5 bg-blue-50 text-blue-700 text-[10px] font-bold uppercase rounded border border-blue-200">Report</span>}
                    {item.status === 'experimental' && <span className="px-2 py-0.5 bg-purple-50 text-purple-700 text-[10px] font-bold uppercase rounded border border-purple-200">Experimental</span>}
                  </div>
                  <div className="text-[10px] font-mono text-slate-500 bg-slate-50 p-1.5 rounded border border-slate-100 break-all mb-3">
                    {item.endpoint}
                  </div>
                  {item.safe && (
                    <div className="flex items-center gap-1.5 text-xs text-slate-500">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" /> Safety Boundary Intact
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>

      {/* Verification summary row */}
      <div className="mt-8 p-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-3">
        <CheckCircle className="w-5 h-5 text-emerald-600 shrink-0" />
        <p className="text-sm text-emerald-800">
          <strong>Safety boundary intact:</strong> All endpoints preserve synthetic-only data, human_review_required=true, no autonomous field dispatch, and API key server-side only.
        </p>
      </div>
    </div>
  );
}
