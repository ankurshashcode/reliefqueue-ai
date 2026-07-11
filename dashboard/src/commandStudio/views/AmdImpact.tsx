import { useState } from 'react';
import { Cpu, Zap, Activity, ShieldAlert, Bot, Server, Printer, CheckCircle, XCircle, RefreshCw, Clock, Hash, Layers } from 'lucide-react';
import { config } from '../lib/publicConfig';

interface VerificationResult {
  status: string;
  verified_live: boolean;
  provider: string | null;
  runtime: string | null;
  accelerator: string | null;
  served_model: string | null;
  underlying_model: string | null;
  request_id: string | null;
  verified_at: string | null;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  fallback_used: boolean;
  human_review_required: boolean;
  synthetic_input: string | null;
  generated_advisory: string | null;
  warnings: string[];
  error: string | null;
}

export function AmdImpact() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VerificationResult | null>(null);

  const runVerification = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch('/api/ai/live-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data: VerificationResult = await res.json();
      setResult(data);
    } catch (err: any) {
      setResult({
        status: 'failed',
        verified_live: false,
        provider: 'AMD Developer Cloud',
        runtime: 'vLLM 0.23.0',
        accelerator: 'AMD Instinct MI300X',
        served_model: null,
        underlying_model: 'Qwen/Qwen2.5-7B-Instruct',
        request_id: null,
        verified_at: new Date().toISOString().replace('.000', '').replace(/\.\d+/, ''),
        latency_ms: null,
        prompt_tokens: null,
        completion_tokens: null,
        total_tokens: null,
        fallback_used: true,
        human_review_required: true,
        synthetic_input: null,
        generated_advisory: null,
        warnings: ['Network error contacting verification endpoint.'],
        error: err?.message || 'Network request failed',
      });
    } finally {
      setLoading(false);
    }
  };

  const verified = result?.verified_live === true && result?.fallback_used === false;
  const failed = result !== null && !verified;

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto h-full overflow-y-auto">
      {/* Header */}
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight flex items-center gap-3">
            AMD GPU / vLLM Impact
          </h2>
          <p className="text-slate-500 mt-2">
            Live verification against AMD Developer Cloud · AMD Instinct MI300X · vLLM 0.23.0 · Qwen2.5-7B-Instruct
          </p>
        </div>
        <button
          onClick={() => window.print()}
          aria-label="Print AMD and vLLM impact summary"
          className="no-print inline-flex items-center gap-2 rounded bg-white border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          <Printer className="w-4 h-4" /> Print AMD Summary
        </button>
      </div>

      {/* Primary CTA */}
      <div className="bg-slate-900 rounded-2xl p-6 md:p-8 mb-8 flex flex-col md:flex-row items-center justify-between gap-6">
        <div>
          <div className="text-slate-400 text-xs font-bold uppercase tracking-widest mb-1">Judge Verification</div>
          <h3 className="text-xl md:text-2xl font-bold text-white mb-1">Run Live AMD Verification</h3>
          <p className="text-slate-400 text-sm">
            Contacts the real AMD Developer Cloud vLLM endpoint with synthetic humanitarian input.
            Measures latency and returns verifiable evidence. No API key exposed.
          </p>
        </div>
        <button
          data-action-id="amd.run_live_verification"
          onClick={runVerification}
          disabled={loading}
          className="shrink-0 flex items-center gap-3 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-60 text-white font-bold px-8 py-4 rounded-xl text-base transition-colors shadow-lg"
        >
          {loading ? (
            <><RefreshCw className="w-5 h-5 animate-spin" /> Contacting AMD endpoint…</>
          ) : (
            <><Zap className="w-5 h-5" /> Run Live AMD Verification</>
          )}
        </button>
      </div>

      {/* Result Banner */}
      {result !== null && (
        <div
          data-result-id="amd.live_verification"
          className={`rounded-2xl p-6 mb-8 flex items-start gap-5 shadow-md ${
            verified
              ? 'bg-emerald-50 border-2 border-emerald-400'
              : 'bg-red-50 border-2 border-red-400'
          }`}
        >
          <div className={`shrink-0 w-12 h-12 rounded-full flex items-center justify-center ${verified ? 'bg-emerald-100' : 'bg-red-100'}`}>
            {verified ? <CheckCircle className="w-7 h-7 text-emerald-600" /> : <XCircle className="w-7 h-7 text-red-600" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className={`text-2xl font-black tracking-tight mb-1 ${verified ? 'text-emerald-800' : 'text-red-800'}`}>
              {verified ? '✓ VERIFIED LIVE' : '✗ LIVE VERIFICATION FAILED'}
            </div>
            <div className={`text-sm font-medium ${verified ? 'text-emerald-700' : 'text-red-700'}`}>
              {verified
                ? `Real AMD inference confirmed at ${result.verified_at ?? '—'}`
                : result.error || 'The AMD endpoint could not be contacted or returned an unexpected response.'}
            </div>
            {result.warnings?.length > 0 && (
              <ul className="mt-2 space-y-1">
                {result.warnings.map((w, i) => (
                  <li key={i} className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1 inline-block mr-1">{w}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Evidence Grid */}
      {result !== null && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          <EvidenceCard icon={<Server className="w-4 h-4" />} label="Provider" value={result.provider} verified={verified} />
          <EvidenceCard icon={<Cpu className="w-4 h-4" />} label="Accelerator" value={result.accelerator} verified={verified} />
          <EvidenceCard icon={<Activity className="w-4 h-4" />} label="Runtime" value={result.runtime} verified={verified} />
          <EvidenceCard icon={<Layers className="w-4 h-4" />} label="Served Model" value={result.served_model} verified={verified} />
          <EvidenceCard icon={<Bot className="w-4 h-4" />} label="Underlying Model" value={result.underlying_model} verified={verified} />
          <EvidenceCard
            icon={<ShieldAlert className="w-4 h-4" />}
            label="Human Review Required"
            value={result.human_review_required ? 'Yes' : 'No'}
            verified={verified}
            highlight={result.human_review_required ? 'amber' : undefined}
          />
          <EvidenceCard icon={<Hash className="w-4 h-4" />} label="Request ID" value={result.request_id} monospace verified={verified} />
          <EvidenceCard icon={<Clock className="w-4 h-4" />} label="Verified At (UTC)" value={result.verified_at} monospace verified={verified} />
          <EvidenceCard
            icon={<Zap className="w-4 h-4" />}
            label="Measured Latency"
            value={result.latency_ms != null ? `${result.latency_ms} ms` : null}
            verified={verified}
          />
          <EvidenceCard
            icon={<Activity className="w-4 h-4" />}
            label="Token Usage"
            value={
              result.prompt_tokens != null
                ? `${result.prompt_tokens} prompt / ${result.completion_tokens} completion / ${result.total_tokens} total`
                : null
            }
            verified={verified}
          />
          <EvidenceCard
            icon={<CheckCircle className="w-4 h-4" />}
            label="Fallback Used"
            value={result.fallback_used ? 'Yes — deterministic fallback' : 'No'}
            verified={verified}
            highlight={result.fallback_used ? 'red' : 'green'}
          />
        </div>
      )}

      {/* Synthetic Input + Advisory */}
      {result !== null && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
            <h3 className="font-bold text-slate-700 text-sm uppercase tracking-wider mb-3 flex items-center gap-2">
              <Bot className="w-4 h-4 text-slate-400" /> Synthetic Input Sent
            </h3>
            <p className="text-sm text-slate-600 bg-slate-50 rounded-lg p-3 border border-slate-100 font-mono">
              {result.synthetic_input ?? 'No synthetic input recorded.'}
            </p>
            <p className="text-xs text-slate-400 mt-2">Privacy-safe synthetic data only. No private reporter information sent.</p>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
            <h3 className="font-bold text-slate-700 text-sm uppercase tracking-wider mb-3 flex items-center gap-2">
              <Zap className="w-4 h-4 text-rq-primary" /> Generated Advisory (from AMD vLLM)
            </h3>
            {result.generated_advisory ? (
              <p className="text-sm text-slate-800 bg-blue-50 rounded-lg p-3 border border-blue-100 leading-relaxed">
                {result.generated_advisory}
              </p>
            ) : (
              <p className="text-sm text-slate-400 italic">No advisory generated — verification did not succeed.</p>
            )}
            <p className="mt-2 inline-block bg-amber-100 text-amber-800 px-2 py-1 rounded text-xs font-bold">
              Human Review Required — Advisory only; no dispatch authority
            </p>
          </div>
        </div>
      )}

      {/* Baseline vs AMD Comparison */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden mb-8">
        <div className="p-5 border-b border-slate-200 bg-slate-50 flex justify-between items-center">
          <h3 className="font-bold text-slate-900 flex items-center gap-2">
            <Activity className="w-5 h-5 text-rq-primary" /> Deterministic Baseline vs AMD/vLLM Advisory
          </h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-0">
          <div className="p-5 border-b md:border-b-0 md:border-r border-slate-200">
            <h4 className="font-bold text-slate-700 mb-3 text-sm">Deterministic Baseline</h4>
            <div className="space-y-2 text-xs text-slate-600">
              <p><strong>Status:</strong> Fallback retained — always available</p>
              <p><strong>Safe Summary:</strong> Raw intake text displayed as-is.</p>
              <p><strong>Missing Info:</strong> No questions generated automatically.</p>
              <p><strong>Operator Note:</strong> Manual coordinator sort required.</p>
              <p><strong>Latency:</strong> Sub-millisecond (in-process)</p>
            </div>
          </div>
          <div className="p-5 bg-blue-50/30">
            <h4 className="font-bold text-rq-primary mb-3 text-sm flex items-center gap-2">
              <Zap className="w-4 h-4" /> Live AMD/vLLM Advisory
            </h4>
            {verified && result ? (
              <div className="space-y-2 text-xs text-slate-800">
                <p><strong>Safe Summary:</strong> {result.generated_advisory ? 'Structured advisory generated.' : 'See advisory panel above.'}</p>
                <p><strong>Missing Info:</strong> Targeted questions prepared by the model.</p>
                <p><strong>Operator Note:</strong> Draft operator guidance included in output.</p>
                <p><strong>Latency:</strong> {result.latency_ms != null ? `${result.latency_ms} ms measured` : '—'}</p>
                <p><strong>Model:</strong> {result.underlying_model}</p>
                <p className="mt-3 inline-block bg-amber-100 text-amber-800 px-2 py-1 rounded font-bold">Human Review Required</p>
              </div>
            ) : (
              <div className="text-xs text-slate-500 italic">
                Run live verification above to populate real AMD advisory evidence here.
              </div>
            )}
          </div>
        </div>
        <div className="px-5 py-3 bg-blue-50 border-t border-blue-100 text-sm text-blue-800 flex items-center justify-center">
          {verified
            ? `✓ Live AMD inference verified at ${result?.latency_ms ?? '—'} ms · Request ${result?.request_id ?? '—'} · Unapproved dispatches: 0`
            : 'Run Live AMD Verification above to replace placeholder evidence with real proof.'}
        </div>
      </div>

      {/* Gemma 4 — truthful labeling */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden mb-8 ring-1 ring-purple-200/50">
        <div className="p-5 border-b border-slate-200 bg-purple-50/50 flex justify-between items-center">
          <h3 className="font-bold text-purple-900 flex items-center gap-2">
            <Bot className="w-5 h-5 text-purple-500" /> Gemma 4 Bonus Lane
          </h3>
          <span className="bg-slate-100 text-slate-600 text-[10px] font-bold px-2 py-1 rounded uppercase tracking-wider border border-slate-200">
            Experimental bonus lane — not active in this deployment
          </span>
        </div>
        <div className="p-5 text-sm text-slate-600">
          <p>
            The Gemma 4 bonus lane is prepared for structured triage via the same vLLM/OpenAI-compatible backend. It is{' '}
            <strong>not the active model in this deployment.</strong>{' '}
            The currently active model is <strong>Qwen/Qwen2.5-7B-Instruct</strong> served as <code className="bg-slate-100 px-1 rounded text-xs">reliefqueue-amd</code> on AMD Instinct MI300X via vLLM 0.23.0.
          </p>
          <p className="mt-2 text-slate-500 text-xs">Human review remains required for all advisory output regardless of which model is active.</p>
        </div>
      </div>

      {/* Static info cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8" data-print-surface="amd-vllm-operational-metrics">
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="flex justify-between items-start mb-3">
            <h3 className="font-bold text-slate-700 text-xs uppercase tracking-wider">Inference Mode</h3>
            <Server className={`w-5 h-5 ${config.featureAmdImpact ? 'text-green-500' : 'text-slate-400'}`} />
          </div>
          <p className="text-lg font-bold text-slate-900">{config.featureAmdImpact ? 'Live AMD/vLLM' : 'Deterministic Fallback'}</p>
          <p className="text-xs text-slate-500 mt-1">Data Source: Synthetic replay</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="flex justify-between items-start mb-3">
            <h3 className="font-bold text-slate-700 text-xs uppercase tracking-wider">AMD GPU</h3>
            <Cpu className="w-5 h-5 text-rq-primary" />
          </div>
          <p className="text-lg font-bold text-slate-900">{verified ? 'Verified Live' : 'Pending Verification'}</p>
          <p className="text-xs text-slate-500 mt-1">AMD Instinct MI300X</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="flex justify-between items-start mb-3">
            <h3 className="font-bold text-slate-700 text-xs uppercase tracking-wider">Data Safety</h3>
            <ShieldAlert className="w-5 h-5 text-rq-primary" />
          </div>
          <p className="text-xs text-slate-700 font-medium">private_text_sent: <span className="text-slate-900">false</span></p>
          <p className="text-xs text-slate-700 font-medium mt-1">secret_values_exposed: <span className="text-slate-900">false</span></p>
        </div>
        <div className="bg-slate-900 rounded-xl border border-slate-200 p-5 shadow-sm text-white">
          <div className="flex justify-between items-start mb-3">
            <h3 className="font-bold text-slate-300 text-xs uppercase tracking-wider">Human Review</h3>
            <ShieldAlert className="w-5 h-5 text-emerald-400" />
          </div>
          <p className="text-lg font-bold text-white">Required</p>
          <p className="text-xs text-slate-400 mt-1">No autonomous field-dispatch authority</p>
        </div>
      </div>
    </div>
  );
}

function EvidenceCard({
  icon,
  label,
  value,
  monospace,
  verified,
  highlight,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number | null | undefined;
  monospace?: boolean;
  verified: boolean;
  highlight?: 'amber' | 'red' | 'green';
}) {
  const highlightClass =
    highlight === 'amber'
      ? 'text-amber-700 bg-amber-50'
      : highlight === 'red'
      ? 'text-red-700 bg-red-50'
      : highlight === 'green'
      ? 'text-emerald-700 bg-emerald-50'
      : 'text-slate-900';

  return (
    <div className={`rounded-xl border p-4 shadow-sm ${verified ? 'bg-white border-slate-200' : 'bg-slate-50 border-slate-200'}`}>
      <div className="flex items-center gap-2 text-slate-500 text-xs font-bold uppercase tracking-wider mb-2">
        {icon}
        {label}
      </div>
      <div className={`text-sm font-semibold break-all ${monospace ? 'font-mono text-xs' : ''} ${highlightClass}`}>
        {value != null && value !== '' ? String(value) : <span className="text-slate-300 italic font-normal">—</span>}
      </div>
    </div>
  );
}
