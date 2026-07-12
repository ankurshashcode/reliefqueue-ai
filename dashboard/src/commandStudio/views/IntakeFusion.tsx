import { useState } from 'react';
import { useApp } from '../context/AppContext';
import { readJsonResponse } from '../lib/httpJson';
import { Bot, Link as LinkIcon, AlertTriangle, ShieldAlert, FileText, Share2, Check, Smartphone, MessageSquare, Zap, XCircle } from 'lucide-react';
import { productApi } from '../lib/productApi';

const RAW_MESSAGES = [
  { id: 'RM-001', provider: 'RapidPro', source: '+123***89', text: 'help we are stuck in flooded basement 3 ppl need boat soon', time: '10:42 AM', confidence: 'Medium', external_id: 'RP-992' },
  { id: 'RM-002', provider: 'WhatsApp', source: 'whatsapp:+55***', text: 'Medical emergency at the community center, asthma attack no inhaler', time: '10:45 AM', confidence: 'High', external_id: 'WA-102' },
  { id: 'RM-003', provider: 'local_mock', source: 'demo_user', text: 'Tree fell on car on main st, looks bad but driver is out', time: '10:50 AM', confidence: 'High', external_id: 'LM-005' },
];

function sanitizePreview(text: string): string {
  return String(text || '')
    .replace(/\+?\d[\d\s().-]{8,}\d/g, '[phone-redacted]')
    .replace(/\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b/g, '[email-redacted]');
}

export function IntakeFusion() {
  const { addLog, showToast } = useApp();
  const [normalizedMsg, setNormalizedMsg] = useState<any | null>(null);
  const [advisoryResult, setAdvisoryResult] = useState<any | null>(null);
  const [selectedRaw, setSelectedRaw] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [advisoryLoading, setAdvisoryLoading] = useState(false);
  const [advisoryError, setAdvisoryError] = useState<string | null>(null);

  const handleNormalize = async (msg: any) => {
    setLoading(true);
    setSelectedRaw(msg.id);
    setAdvisoryResult(null);
    setAdvisoryError(null);
    try {
      const result = await productApi.normalizeMessage(msg);
      setNormalizedMsg({ ...result, original: msg });
      showToast('Message normalized locally. Run AMD/vLLM Advisory for live structured analysis.', 'success');
    } catch (error: any) {
      showToast(error?.message || 'Normalization failed.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const runAdvisory = async () => {
    if (!normalizedMsg?.original?.text) return;
    setAdvisoryLoading(true);
    setAdvisoryResult(null);
    setAdvisoryError(null);
    try {
      const response = await fetch('/api/ai/live-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workload_mode: 'single', text: normalizedMsg.original.text, synthetic_confirmed: true }),
      });
      const data = await readJsonResponse<any>(response, 'AMD intake advisory');
      setAdvisoryResult(data);
      addLog('Run AMD/vLLM Advisory', 'Quality', data.verified_live ? 'Success' : 'Review Required', {
        ref: normalizedMsg.original.id,
        request_id: data.request_id,
        analysis_source: data.analysis_source,
      });
      showToast(data.verified_live ? 'Live AMD analysis received.' : 'Analysis returned but is not verified live; review provenance.', data.verified_live ? 'success' : 'warning');
    } catch (error: any) {
      setAdvisoryError(error?.message || 'AMD advisory request failed.');
      showToast(error?.message || 'AMD advisory request failed.', 'error');
    } finally {
      setAdvisoryLoading(false);
    }
  };

  const handleAction = (actionName: string) => {
    addLog(actionName, 'Quality', 'Success', { ref: normalizedMsg?.original?.id });
    showToast(`${actionName} applied.`, 'success');
    setNormalizedMsg(null);
    setAdvisoryResult(null);
    setSelectedRaw(null);
  };

  const originalText = String(normalizedMsg?.original?.text || '');
  const sanitizedInput = advisoryResult?.sanitized_input || sanitizePreview(originalText);
  const normalizedRecord = advisoryResult?.normalized_structured_record || {
    provider: normalizedMsg?.provider,
    external_id: normalizedMsg?.external_id,
    urgency: normalizedMsg?.urgency,
    need_type: normalizedMsg?.needType,
    analysis_source: 'local_normalization_preview',
    human_review_required: true,
  };
  const sourceRows = advisoryResult?.source_evidence_mapping || [
    {
      field: 'urgency',
      source_evidence: originalText,
      normalized_value: normalizedMsg?.urgency,
      confidence: normalizedMsg?.original?.confidence || 'Unknown',
    },
    {
      field: 'need_type',
      source_evidence: originalText,
      normalized_value: normalizedMsg?.needType,
      confidence: normalizedMsg?.original?.confidence || 'Unknown',
    },
  ];
  const operationalAnalysis = advisoryResult?.operational_analysis || null;
  const verifiedLive = advisoryResult?.verified_live === true
    && advisoryResult?.fallback_used === false
    && advisoryResult?.analysis_source === 'provider'
    && advisoryResult?.verification_bound_to_nonce === true;

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto h-full flex flex-col overflow-hidden">
      <div className="mb-6 flex-shrink-0">
        <h2 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">AI Intake Fusion</h2>
        <p className="text-slate-500 mt-1 md:mt-2 text-sm md:text-base">Normalize messy inbound reports, then request source-grounded AMD analysis with visible provenance.</p>
      </div>

      <div className="flex-1 flex flex-col md:flex-row gap-6 overflow-hidden">
        <div className="w-full md:w-1/2 lg:w-1/3 flex flex-col gap-4 overflow-y-auto pr-2">
          <h3 className="font-bold text-slate-700 tracking-wider text-xs border-b border-slate-200 pb-2">Raw Inbound Queue</h3>
          {RAW_MESSAGES.map(msg => (
            <div key={msg.id} className={`bg-white border rounded-lg p-4 shadow-sm transition-all ${selectedRaw === msg.id ? 'ring-2 ring-rq-primary border-rq-primary bg-blue-50/10' : 'border-slate-200 hover:border-slate-300'}`}>
              <div className="flex justify-between items-start mb-2">
                <span className="inline-flex items-center gap-1.5 px-2 py-1 bg-slate-100 text-slate-600 rounded text-[10px] font-mono font-bold">
                  {msg.provider === 'WhatsApp' ? <MessageSquare className="w-3 h-3" /> : <Smartphone className="w-3 h-3" />}
                  {msg.provider}
                </span>
                <span className="text-xs text-slate-400 font-mono">{msg.time}</span>
              </div>
              <p className="text-sm text-slate-800 mb-3 italic">"{msg.text}"</p>
              <div className="flex justify-between items-center mt-3 pt-3 border-t border-slate-100">
                <span className="text-[10px] font-mono text-slate-400">ID: {msg.external_id}</span>
                <button
                  data-testid={`ai-intake-normalize-${msg.id}`}
                  onClick={() => handleNormalize(msg)}
                  disabled={loading && selectedRaw === msg.id}
                  className="px-3 py-1.5 bg-rq-primary text-white text-xs font-medium rounded hover:bg-rq-primary-hover disabled:opacity-50 flex items-center gap-2"
                >
                  <Bot className="w-3.5 h-3.5" /> Normalize
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="w-full md:w-1/2 lg:w-2/3 bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
          <div className="p-4 border-b border-slate-200 bg-slate-50">
            <h3 className="font-bold text-slate-900 flex items-center gap-2">
              <FileText className="w-5 h-5 text-rq-primary" /> Extraction, Evidence & Analysis
            </h3>
          </div>
          <div className="flex-1 p-6 overflow-y-auto">
            {!normalizedMsg && !loading && (
              <div className="h-full flex flex-col items-center justify-center text-slate-400">
                <Bot className="w-12 h-12 mb-4 opacity-20" />
                <p>Select a raw message to normalize.</p>
              </div>
            )}
            {loading && (
              <div className="h-full flex flex-col items-center justify-center text-slate-400">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-rq-primary mb-4"></div>
                <p>Normalizing via product API / local fallback…</p>
              </div>
            )}
            {normalizedMsg && !loading && (
              <div className="space-y-6 max-w-3xl">
                {advisoryResult && (
                  <div className={`rounded-lg border p-3 text-sm ${verifiedLive ? 'bg-emerald-50 border-emerald-300 text-emerald-800' : 'bg-amber-50 border-amber-300 text-amber-900'}`}>
                    <strong>{verifiedLive ? 'VERIFIED LIVE AMD ANALYSIS' : 'NOT VERIFIED LIVE'}</strong>
                    <span className="ml-2">Source: {advisoryResult.analysis_source || 'unknown'} · Fallback: {advisoryResult.fallback_used ? 'Yes' : 'No'} · Nonce bound: {advisoryResult.verification_bound_to_nonce ? 'Yes' : 'No'}</span>
                  </div>
                )}
                {advisoryError && (
                  <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800 flex items-center gap-2"><XCircle className="w-4 h-4" />{advisoryError}</div>
                )}

                <div>
                  <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Original Payload</h4>
                  <div data-testid="ai-intake-original-input" className="bg-slate-100 p-3 rounded font-mono text-xs text-slate-600">
                    Source: {normalizedMsg.original.source} <br />
                    Provider: {normalizedMsg.original.provider} <br />
                    Text: {originalText}
                  </div>
                </div>

                <div>
                  <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Sanitized Input {advisoryResult ? 'Sent to AMD' : 'Preview'}</h4>
                  <div data-testid="ai-intake-sanitized-input" className="bg-emerald-50 p-3 rounded font-mono text-xs text-emerald-900 border border-emerald-100">
                    {sanitizedInput}
                  </div>
                  {!advisoryResult && <p className="text-[10px] text-slate-400 mt-1">Preview only. No AMD request occurs until “Run AMD/vLLM Advisory” is clicked.</p>}
                </div>

                <div data-testid="ai-intake-normalized-record" className="bg-slate-50 p-4 rounded-lg border border-slate-200">
                  <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Normalized Structured Record</h4>
                  <pre className="text-xs text-slate-700 whitespace-pre-wrap">{JSON.stringify(normalizedRecord, null, 2)}</pre>
                </div>

                <div data-testid="ai-intake-source-evidence-table" className="overflow-x-auto border border-slate-200 rounded-lg">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-50 text-slate-500 uppercase">
                      <tr><th className="p-2 text-left">Field</th><th className="p-2 text-left">Source evidence</th><th className="p-2 text-left">Normalized value</th><th className="p-2 text-left">Confidence</th></tr>
                    </thead>
                    <tbody>
                      {sourceRows.map((row: any, index: number) => (
                        <tr key={`${row.field}-${index}`} className="border-t border-slate-100">
                          <td className="p-2 font-bold">{row.field}</td>
                          <td className="p-2 max-w-xs break-words">{row.source_evidence}</td>
                          <td className="p-2 max-w-sm break-words">{row.normalized_value}</td>
                          <td className="p-2">{row.confidence}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div data-testid="ai-intake-operational-analysis" className="bg-blue-50/50 p-4 rounded-lg border border-blue-100">
                  <h4 className="text-xs font-bold text-blue-800 uppercase tracking-wider mb-2">Operational Analysis</h4>
                  {operationalAnalysis
                    ? <pre className="text-xs text-blue-900 whitespace-pre-wrap">{JSON.stringify(operationalAnalysis, null, 2)}</pre>
                    : <p className="text-sm text-blue-900">Run AMD/vLLM Advisory to generate source-grounded priorities, contradictions, route/resource implications and review questions.</p>}
                </div>

                <div data-testid="ai-intake-compact-json" className="bg-slate-900 text-white p-4 rounded-lg">
                  <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-2">Compact JSON</h4>
                  <pre className="text-xs whitespace-pre-wrap">{JSON.stringify(advisoryResult || normalizedMsg, null, 2)}</pre>
                </div>

                <div className="bg-blue-50/50 p-4 rounded-lg border border-blue-100">
                  <h4 className="text-xs font-bold text-blue-800 uppercase tracking-wider mb-2 flex items-center gap-1">
                    <AlertTriangle className="w-4 h-4" /> Missing Information / Review Questions
                  </h4>
                  <pre className="text-xs text-blue-900 whitespace-pre-wrap">{JSON.stringify(
                    advisoryResult?.structured_output?.coordinator_questions
                      || advisoryResult?.structured_output?.missing_information
                      || ['Precise location', 'Current people count', 'Route and resource status'],
                    null,
                    2,
                  )}</pre>
                </div>

                <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 p-3 rounded border border-amber-200">
                  <ShieldAlert className="w-4 h-4 shrink-0" />
                  <span><strong>Human Review Required:</strong> Review redaction, evidence, uncertainty and intent before creating a Review Packet. No automatic dispatch.</span>
                </div>
              </div>
            )}
          </div>
          {normalizedMsg && !loading && (
            <div className="p-4 border-t border-slate-200 bg-slate-50 flex flex-wrap gap-3">
              <button
                data-testid="ai-intake-run-advisory"
                onClick={runAdvisory}
                disabled={advisoryLoading}
                className="px-4 py-2 bg-slate-900 text-white rounded font-medium text-sm hover:bg-slate-800 disabled:opacity-50 flex items-center gap-2"
              >
                <Zap className="w-4 h-4" /> {advisoryLoading ? 'Running AMD analysis…' : 'Run AMD/vLLM Advisory'}
              </button>
              <button onClick={() => handleAction('Create Review Packet')} className="px-4 py-2 bg-rq-primary text-white rounded font-medium text-sm hover:bg-rq-primary-hover flex items-center gap-2">
                <Check className="w-4 h-4" /> Create Review Packet
              </button>
              <button onClick={() => handleAction('Request Missing Info')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded font-medium text-sm hover:bg-slate-50 flex items-center gap-2">
                <Share2 className="w-4 h-4" /> Request Missing Info
              </button>
              <button onClick={() => handleAction('Link as Possible Duplicate')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded font-medium text-sm hover:bg-slate-50 flex items-center gap-2">
                <LinkIcon className="w-4 h-4" /> Link as Possible Duplicate
              </button>
              <button onClick={() => handleAction('Keep Separate')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded font-medium text-sm hover:bg-slate-50">
                Keep Separate
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
