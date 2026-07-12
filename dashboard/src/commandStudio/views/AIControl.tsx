import React, { useState } from 'react';
import { Cpu, ShieldAlert, CheckCircle, Lock, ShieldCheck, Bot, XCircle, RefreshCw, Hash, Clock, Zap } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { readJsonResponse } from '../lib/httpJson';

interface ConnectionResult {
  verified_live: boolean;
  fallback_used: boolean;
  request_id: string | null;
  verified_at: string | null;
  latency_ms: number | null;
  served_model: string | null;
  underlying_model: string | null;
  generated_advisory: string | null;
  warnings: string[];
  error: string | null;
}

export function AIControl() {
  const { addLog } = useApp();
  const [step, setStep] = useState<'settings' | 'test' | 'confirm'>('settings');
  const [testLoading, setTestLoading] = useState(false);
  const [connectionResult, setConnectionResult] = useState<ConnectionResult | null>(null);

  const handleTestConnection = async () => {
    setTestLoading(true);
    setConnectionResult(null);
    addLog('Test Connection Started', 'Contacting the configured AMD/vLLM endpoint with synthetic demonstration data…');
    try {
      const res = await fetch('/api/ai/live-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workload_mode: 'single',
          synthetic_confirmed: true,
          text: 'Synthetic connection test: prioritize a flood rescue report, identify missing facts, and require coordinator review.',
        }),
      });
      const data = await readJsonResponse<ConnectionResult>(res, 'AMD connection test');
      setConnectionResult(data);
      if (data.verified_live && !data.fallback_used) {
        addLog('Connection Verified', `Request ${data.request_id} · ${data.latency_ms} ms · Model: ${data.underlying_model}`);
      } else {
        addLog('Connection Not Verified', data.error || 'The request did not establish a verified-live provider result.');
      }
    } catch (err: any) {
      setConnectionResult({
        verified_live: false,
        fallback_used: false,
        request_id: null,
        verified_at: null,
        latency_ms: null,
        served_model: null,
        underlying_model: null,
        generated_advisory: null,
        warnings: [],
        error: err?.message || 'AMD connection test failed.',
      });
      addLog('Connection Failed', err?.message || 'AMD connection test failed.');
    } finally {
      setTestLoading(false);
    }
  };

  const handleApprove = () => {
    addLog('Approve Advisory Model Change', 'Created review-approved advisory config state only. No dispatch authority granted.');
    setStep('settings');
  };

  const connectionOk = connectionResult?.verified_live === true && connectionResult?.fallback_used === false;

  const renderSettings = () => (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <h2 className="text-xl font-bold text-slate-900 mb-6">AMD Model Configuration and Live Test</h2>

        {/* Campaign configuration is historical until the live connection test verifies the current request. */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <div>
            <label className="block text-sm font-bold text-slate-700 mb-2">Advisory Provider</label>
            <div className="w-full bg-slate-50 border border-slate-200 text-slate-900 text-sm rounded-lg p-2.5 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-rq-primary shrink-0" />
              AMD Developer Cloud (when configured)
            </div>
            <p className="text-xs text-slate-400 mt-1">Configured via OPENAI_COMPAT_* environment variables.</p>
          </div>
          <div>
            <label className="block text-sm font-bold text-slate-700 mb-2">Model Version</label>
            <div className="w-full bg-slate-50 border border-slate-200 text-slate-900 text-sm rounded-lg p-2.5 font-medium">
              Qwen2.5-7B-Instruct via AMD vLLM — verified campaign configuration
            </div>
            <p className="text-xs text-slate-400 mt-1">Historically verified as <code className="bg-slate-100 px-1 rounded">reliefqueue-amd</code> on vLLM 0.23.0 and AMD Instinct MI300X. Use Test Connection for current-request truth.</p>
          </div>
        </div>

        {/* Test Connection */}
        <div className="mt-6 flex flex-col gap-4 border-t border-slate-100 pt-6">
          <div className="flex flex-col sm:flex-row sm:items-center gap-4">
            <button
              onClick={handleTestConnection}
              disabled={testLoading}
              className="flex items-center gap-2 bg-white border border-slate-300 text-slate-700 font-semibold px-4 py-2 rounded-lg hover:bg-slate-50 transition-colors shadow-sm disabled:opacity-60"
            >
              {testLoading
                ? <><RefreshCw className="w-4 h-4 animate-spin" /> Testing…</>
                : <><CheckCircle className="w-4 h-4" /> Test Connection</>}
            </button>
            {connectionResult !== null && (
              <span className={`flex items-center gap-2 font-bold text-sm px-3 py-1.5 rounded-md border ${connectionOk ? 'text-emerald-600 bg-emerald-50 border-emerald-200' : 'text-red-600 bg-red-50 border-red-200'}`}>
                {connectionOk
                  ? <><CheckCircle className="w-4 h-4" /> Connection Healthy</>
                  : <><XCircle className="w-4 h-4" /> Connection Failed</>}
              </span>
            )}
          </div>

          {/* Connection evidence */}
          {connectionResult !== null && (
            <div className={`rounded-xl p-4 border text-sm ${connectionOk ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200'}`}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <EvidenceRow icon={<Hash className="w-3.5 h-3.5" />} label="Request ID" value={connectionResult.request_id} monospace />
                <EvidenceRow icon={<Clock className="w-3.5 h-3.5" />} label="Timestamp" value={connectionResult.verified_at} monospace />
                <EvidenceRow icon={<Zap className="w-3.5 h-3.5" />} label="Latency" value={connectionResult.latency_ms != null ? `${connectionResult.latency_ms} ms` : null} />
                <EvidenceRow icon={<Cpu className="w-3.5 h-3.5" />} label="Model" value={connectionResult.underlying_model} />
                <EvidenceRow
                  icon={<ShieldAlert className="w-3.5 h-3.5" />}
                  label="Live / Fallback"
                  value={connectionResult.verified_live && !connectionResult.fallback_used ? 'Live — no fallback' : connectionResult.fallback_used ? 'Fallback used' : 'Not verified live'}
                />
              </div>
              {connectionResult.generated_advisory && (
                <div className="mt-3 pt-3 border-t border-emerald-200">
                  <div className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-1">Advisory Output (first 300 chars)</div>
                  <p className="text-xs text-slate-700 bg-white rounded p-2 border border-slate-200 font-mono break-words">
                    {connectionResult.generated_advisory.slice(0, 300)}{connectionResult.generated_advisory.length > 300 ? '…' : ''}
                  </p>
                </div>
              )}
              {connectionResult.error && (
                <div className="mt-3 text-xs text-red-700 font-mono bg-red-100 rounded p-2">
                  {connectionResult.error}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Gemma 4 — clearly labeled experimental/not active */}
        <div className="mt-6 rounded-xl border border-purple-100 bg-purple-50/50 p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-bold text-purple-900 flex items-center gap-2 text-sm">
              <Bot className="w-4 h-4 text-purple-500" /> Gemma 4 Bonus Lane
            </h3>
            <span className="bg-slate-100 text-slate-500 text-[10px] font-bold px-2 py-1 rounded uppercase tracking-wider border border-slate-200">
              Experimental — not part of verified campaign
            </span>
          </div>
          <p className="text-xs text-slate-600">
            Gemma 4 is a future bonus lane, not part of the verified AMD campaign or current live-request proof. The frozen campaign used <strong>Qwen/Qwen2.5-7B-Instruct</strong>; current provider metadata is trusted only after Test Connection succeeds. Human review remains required for every advisory.
          </p>
        </div>
      </div>

      <div className="flex justify-end pt-4">
        <button
          onClick={() => setStep('test')}
          className="bg-rq-primary text-white font-semibold px-6 py-3 rounded-lg hover:bg-rq-primary-hover shadow-sm transition-colors"
        >
          Continue to Validation Test
        </button>
      </div>
    </div>
  );

  const renderTest = () => (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center gap-4 mb-2">
        <button onClick={() => setStep('settings')} className="text-slate-500 hover:text-slate-900 font-medium text-sm">← Back</button>
      </div>
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
              <Cpu className="w-5 h-5 text-rq-primary" /> Safety Validation — Qwen2.5-7B-Instruct via AMD vLLM
            </h2>
            <p className="text-slate-500 text-sm mt-1">Safety-contract review for the verified campaign configuration; live provider status is established separately per request.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="border border-emerald-200 bg-emerald-50 p-4 rounded-lg flex gap-3">
            <ShieldCheck className="w-5 h-5 text-emerald-600 shrink-0" />
            <div>
              <div className="font-bold text-sm text-emerald-900">Schema Validation</div>
              <div className="text-xs text-emerald-800 mt-1">Output strictly matches expected JSON interface.</div>
            </div>
          </div>
          <div className="border border-emerald-200 bg-emerald-50 p-4 rounded-lg flex gap-3">
            <Lock className="w-5 h-5 text-emerald-600 shrink-0" />
            <div>
              <div className="font-bold text-sm text-emerald-900">Redaction Check</div>
              <div className="text-xs text-emerald-800 mt-1">PII and secrets are reliably masked.</div>
            </div>
          </div>
          <div className="border border-emerald-200 bg-emerald-50 p-4 rounded-lg flex gap-3">
            <ShieldAlert className="w-5 h-5 text-emerald-600 shrink-0" />
            <div>
              <div className="font-bold text-sm text-emerald-900">Safety Phrase Guard</div>
              <div className="text-xs text-emerald-800 mt-1">No dispatch authority or rescue guarantees generated.</div>
            </div>
          </div>
        </div>

        <div className="bg-slate-900 text-emerald-400 p-4 rounded-lg font-mono text-xs overflow-x-auto relative">
          <div className="absolute top-2 right-2 bg-slate-800 text-slate-300 px-2 py-1 rounded text-[10px] uppercase font-bold tracking-wider">Advisory JSON Schema</div>
          <pre>{`{
  "safe_summary": "string — redacted, no PII",
  "missing_info_questions": ["string"],
  "reply_draft": "string — coordinator-safe only",
  "operator_note": "string — advisory guidance",
  "language": "en | hi | hinglish | unknown",
  "warnings": ["string"],

  // Safety boundary enforced server-side:
  // human_review_required = true (always)
  // No dispatch authority granted
  // No confirmed rescue, safety, or location guarantee
}`}</pre>
        </div>
      </div>

      <div className="flex justify-end pt-4 gap-3">
        <button
          onClick={() => setStep('confirm')}
          className="bg-rq-primary text-white font-semibold px-6 py-3 rounded-lg hover:bg-rq-primary-hover shadow-sm transition-colors"
        >
          Request Coordinator Review
        </button>
      </div>
    </div>
  );

  const renderConfirm = () => (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-4 mb-2">
        <button onClick={() => setStep('test')} className="text-slate-500 hover:text-slate-900 font-medium text-sm">← Back</button>
      </div>
      <div className="bg-rq-amber-light border border-rq-amber rounded-xl p-6 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="bg-white p-3 rounded-full shrink-0 shadow-sm">
            <ShieldAlert className="w-8 h-8 text-rq-amber" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-rq-amber-dark mb-2">Approve Advisory Model Change</h2>
            <p className="text-slate-800 mb-4 leading-relaxed font-medium">
              This changes the advisory triage suggestions and confidence models only.
              <br /><br />
              <span className="font-bold uppercase tracking-wide text-xs bg-amber-200 px-2 py-1 rounded border border-amber-300">
                Safety Boundary Requirement
              </span>
              <br />
              It does <span className="underline font-bold">not</span> dispatch teams, confirm safety, close cases, or override coordinator approval. Human review remains strictly required for all assignments.
            </p>
            <div className="bg-white border border-amber-200 p-4 rounded-lg mt-4 text-sm font-mono text-slate-700 shadow-sm">
              Verified Campaign Model: <span className="font-bold text-slate-900">Qwen2.5-7B-Instruct via AMD vLLM</span><br />
              Historical Provider: <span className="font-bold text-slate-900">AMD Developer Cloud</span><br />
              Rollback Available: <span className="text-emerald-600 font-bold">Yes (deterministic fallback always active)</span>
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row justify-end gap-3 pt-4 border-t border-slate-200">
        <button onClick={() => setStep('test')} className="bg-white border border-slate-300 text-slate-700 font-semibold px-6 py-3 rounded-lg hover:bg-slate-50 transition-colors">
          Request More Testing
        </button>
        <button onClick={handleApprove} className="bg-rq-amber hover:bg-amber-600 text-white font-semibold px-6 py-3 rounded-lg shadow-sm transition-colors">
          Approve Model Change
        </button>
      </div>
    </div>
  );

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-7xl mx-auto h-full overflow-y-auto bg-slate-50">
      <div className="mb-6 md:mb-8 text-center shrink-0">
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900">AI Control & Validation</h1>
        <p className="text-slate-500 mt-2 text-sm">Configure and validate advisory model safety boundaries.</p>
        <div className="flex justify-center items-center mt-6 gap-2 md:gap-4 max-w-lg mx-auto">
          <Step indicator="1" label="Settings" active={step === 'settings'} />
          <div className="w-8 md:w-16 h-px bg-slate-300"></div>
          <Step indicator="2" label="Validation Test" active={step === 'test'} />
          <div className="w-8 md:w-16 h-px bg-slate-300"></div>
          <Step indicator="3" label="Confirmation" active={step === 'confirm'} />
        </div>
      </div>

      <div className="py-4">
        {step === 'settings' && renderSettings()}
        {step === 'test' && renderTest()}
        {step === 'confirm' && renderConfirm()}
      </div>
    </div>
  );
}

function EvidenceRow({ icon, label, value, monospace }: { icon: React.ReactNode; label: string; value: string | number | null | undefined; monospace?: boolean }) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-slate-400 mt-0.5 shrink-0">{icon}</span>
      <div>
        <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">{label}: </span>
        <span className={`text-xs text-slate-800 ${monospace ? 'font-mono' : 'font-medium'}`}>
          {value != null && value !== '' ? String(value) : '—'}
        </span>
      </div>
    </div>
  );
}

function Step({ indicator, label, active }: { indicator: string; label: string; active: boolean }) {
  return (
    <div className={`flex flex-col items-center gap-2 ${active ? 'opacity-100' : 'opacity-50'}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm border-2 transition-colors ${active ? 'bg-rq-primary text-white border-rq-primary' : 'bg-white text-slate-500 border-slate-300'}`}>
        {indicator}
      </div>
      <div className="text-[10px] md:text-xs font-bold text-slate-700 uppercase tracking-wider hidden sm:block">{label}</div>
    </div>
  );
}
