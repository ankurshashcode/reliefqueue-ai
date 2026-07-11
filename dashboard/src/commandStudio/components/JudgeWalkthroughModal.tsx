import React, { useEffect, useState } from 'react';
import { X, Play, Cpu, Bot, UserCheck, Smartphone, CheckCircle, RefreshCw, Hash, Clock, Zap, XCircle, List, FileText } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { actionLog } from '../lib/actionLog';
import { postProduct, actionKey } from '../lib/productActions';

interface AmdResult {
  verified_live: boolean;
  fallback_used: boolean;
  request_id: string | null;
  challenge_nonce?: string | null;
  verified_at: string | null;
  latency_ms: number | null;
  served_model: string | null;
  underlying_model: string | null;
  accelerator: string | null;
  runtime: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  generated_advisory: string | null;
  warnings: string[];
  error: string | null;
}

interface BurstResult {
  status: string;
  batch_id: string;
  succeeded: number;
  submitted: number;
  failed: number;
  total_elapsed_ms: number;
  median_latency_ms: number | null;
  total_tokens: number;
  human_review_required: boolean;
  cases: { case_id: string; verified_live: boolean; fallback_used: boolean; request_id: string | null; challenge_nonce: string | null; latency_ms: number | null; total_tokens: number | null; generated_advisory: string | null }[];
}

interface IntakeResult {
  status?: string;
  normalized?: boolean;
  urgency?: string;
  needType?: string;
  human_review_required?: boolean;
  [key: string]: unknown;
}

export function JudgeWalkthroughModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { navigate, addLog } = useApp();
  const [activeStep, setActiveStep] = useState(1);

  // Step 1 state
  const [step1Loading, setStep1Loading] = useState(false);
  const [step1Result, setStep1Result] = useState<IntakeResult | null>(null);

  // Step 2 state
  const [step2Loading, setStep2Loading] = useState(false);
  const [step2Result, setStep2Result] = useState<IntakeResult | null>(null);

  // Step 3 — AMD single incident (editable)
  const [step3Input, setStep3Input] = useState('Flood near north sector. Family of 5 stranded on rooftop. Elderly woman needs insulin. Two young children present.');
  const [step3Loading, setStep3Loading] = useState(false);
  const [step3Result, setStep3Result] = useState<AmdResult | null>(null);

  // Step 4 — AMD complex dossier
  const [step4Loading, setStep4Loading] = useState(false);
  const [step4Result, setStep4Result] = useState<AmdResult | null>(null);

  // Step 5 — AMD burst workload
  const [step5Loading, setStep5Loading] = useState(false);
  const [step5Result, setStep5Result] = useState<BurstResult | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const runStep1 = async () => {
    setStep1Loading(true);
    setStep1Result(null);
    try {
      const result = await postProduct(
        '/api/product/messaging/webhook',
        {
          provider: 'local_mock',
          payload: {
            source: 'sms',
            text: 'Urgent: family of 5 stranded near north sector bridge. Need rescue and medicine. No clean water.',
          },
        },
        { normalized: true, urgency: 'High', needType: 'rescue_medical', human_review_required: true }
      ) as IntakeResult;
      setStep1Result(result);
      actionLog.add('Judge Demo Walkthrough', 'Demo Execution', 'Success', { step: 1, name: 'Synthetic Intake Burst' });
      addLog('Step 1 Complete', 'Synthetic intake burst processed via real product API.');
    } catch (err: any) {
      setStep1Result({ normalized: false, error: err?.message });
    } finally {
      setStep1Loading(false);
    }
  };

  const runStep2 = async () => {
    setStep2Loading(true);
    setStep2Result(null);
    try {
      const result = await postProduct(
        '/api/product/command/ai-advisory',
        { case_id: 'RQ-1042', idempotency_key: actionKey('walkthrough-step2') },
        {
          case_id: 'RQ-1042',
          safe_summary: 'Boat evacuation request — human coordinator review required.',
          human_review_required: true,
          ai_status: 'Local Demo',
        }
      ) as IntakeResult;
      setStep2Result(result);
      actionLog.add('Judge Demo Walkthrough', 'Demo Execution', 'Success', { step: 2, name: 'AI Intake Fusion' });
      addLog('Step 2 Complete', 'AI intake fusion advisory retrieved.');
    } catch (err: any) {
      setStep2Result({ error: err?.message });
    } finally {
      setStep2Loading(false);
    }
  };

  const runStep3 = async () => {
    setStep3Loading(true);
    setStep3Result(null);
    try {
      const res = await fetch('/api/ai/live-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: step3Input }),
      });
      const data: AmdResult = await res.json();
      setStep3Result(data);
      const live = data.verified_live && !data.fallback_used;
      actionLog.add('Judge Demo Walkthrough', 'AMD Live — Your Incident', live ? 'VERIFIED LIVE' : 'Failed', {
        step: 3, request_id: data.request_id, challenge_nonce: data.challenge_nonce, latency_ms: data.latency_ms,
      });
      if (live) {
        addLog('Step 3 — AMD VERIFIED LIVE', `Req ${data.request_id} · Nonce ${data.challenge_nonce} · ${data.latency_ms} ms`);
      } else {
        addLog('Step 3 — AMD Failed', data.error || 'Endpoint did not confirm live inference.');
      }
    } catch (err: any) {
      setStep3Result({ verified_live: false, fallback_used: true, request_id: null, verified_at: null, latency_ms: null, served_model: null, underlying_model: null, accelerator: null, runtime: null, generated_advisory: null, warnings: [], error: err?.message || 'Network request failed' });
    } finally {
      setStep3Loading(false);
    }
  };

  const DOSSIER_SAMPLE = `[REPORT-A | SMS] Flood near Sector 7 bridge. 5 people on roof. Rescue needed. Kids present.\n[REPORT-B | WhatsApp] Bahut paani aa gaya north mein. Pregnant woman here. Need boat fast.\n[REPORT-C | Field] Ward 13 east road blocked by fallen tree. Alt route via Sector 9 south.\n[REPORT-D | IVR] Insulin needed at relief hub west lane 4. Diabetic elderly woman. 24 hours no medication.\n[REPORT-E | Update] Sector 7 roof rescue complete — 5 evacuated. 1 needs medical check.`;

  const runStep4 = async () => {
    setStep4Loading(true);
    setStep4Result(null);
    try {
      const res = await fetch('/api/ai/live-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: DOSSIER_SAMPLE }),
      });
      const data: AmdResult = await res.json();
      setStep4Result(data);
      const live = data.verified_live && !data.fallback_used;
      actionLog.add('Judge Demo Walkthrough', 'AMD Live — Complex Dossier', live ? 'VERIFIED LIVE' : 'Failed', {
        step: 4, request_id: data.request_id, latency_ms: data.latency_ms,
      });
      addLog(`Step 4 — AMD Dossier ${live ? 'LIVE' : 'Failed'}`, `Req ${data.request_id} · ${data.latency_ms} ms`);
    } catch (err: any) {
      setStep4Result({ verified_live: false, fallback_used: true, request_id: null, verified_at: null, latency_ms: null, served_model: null, underlying_model: null, accelerator: null, runtime: null, generated_advisory: null, warnings: [], error: err?.message || 'Network request failed' });
    } finally {
      setStep4Loading(false);
    }
  };

  const BURST_SAMPLE = [
    { id: 'burst-1', text: 'Family of 4 stranded on rooftop near Sector 7 bridge. Boat rescue needed.' },
    { id: 'burst-2', text: 'Elderly woman at relief hub west needs insulin. Diabetic emergency.' },
    { id: 'burst-3', text: 'Shelter B at school almost full. 20 more evacuees incoming. Overflow plan needed.' },
    { id: 'burst-4', text: 'Chest pain at pump station area. 6 people stranded, 1 possible cardiac event.' },
  ];

  const runStep5 = async () => {
    setStep5Loading(true);
    setStep5Result(null);
    try {
      const res = await fetch('/api/ai/burst-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reports: BURST_SAMPLE, concurrency: 2 }),
      });
      const data: BurstResult = await res.json();
      setStep5Result(data);
      actionLog.add('Judge Demo Walkthrough', 'AMD Burst Workload', 'Complete', {
        step: 5, batch_id: data.batch_id, succeeded: data.succeeded, submitted: data.submitted,
      });
      addLog(`Step 5 — Burst ${data.succeeded}/${data.submitted} live`, `Batch ${data.batch_id} · ${data.total_elapsed_ms} ms total`);
    } catch (err: any) {
      alert(`Burst failed: ${err?.message}`);
    } finally {
      setStep5Loading(false);
    }
  };

  const navigateStep = (route: string) => { navigate(route); onClose(); };

  const step3Verified = step3Result?.verified_live === true && step3Result?.fallback_used === false;
  const step4Verified = step4Result?.verified_live === true && step4Result?.fallback_used === false;

  return (
    <div
      className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-[100] flex items-center justify-center p-4"
      role="presentation"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-2xl flex flex-col max-h-[90vh] overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="judge-walkthrough-title"
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-200 shrink-0">
          <div>
            <h2 id="judge-walkthrough-title" className="text-xl font-bold text-slate-900">Judge Demo Walkthrough</h2>
            <p className="text-sm text-slate-500">Guided tour of ReliefQueue capabilities and AI safety boundaries.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50">

          {/* Step 1 — Synthetic Intake */}
          <StepCard id={1} activeStep={activeStep} onSelect={() => setActiveStep(1)} icon={Play}
            name="Step 1: Synthetic Intake Burst"
            desc="Process an incoming synthetic SMS report to show multi-source normalization."
          >
            {activeStep === 1 && (
              <div className="mt-4 pt-4 border-t border-slate-100">
                <div className="flex items-center justify-between gap-3">
                  <button type="button" disabled={step1Loading} onClick={runStep1}
                    className="bg-slate-900 hover:bg-slate-800 text-white font-semibold py-2 px-6 rounded-lg text-sm flex items-center gap-2 disabled:opacity-50">
                    {step1Loading ? <><RefreshCw className="w-4 h-4 animate-spin" /> Running…</> : <><Play className="w-4 h-4" /> Run Step</>}
                  </button>
                  {step1Result && <button type="button" onClick={() => navigateStep('intake')} className="text-xs text-rq-primary hover:underline">Open Intake view →</button>}
                </div>
                {step1Result && (
                  <div className="mt-3 bg-white rounded-lg border border-slate-200 p-3 text-xs font-mono text-slate-700 space-y-1">
                    <div className="font-bold text-slate-500 uppercase tracking-wider mb-2 not-italic font-sans text-[10px]">Intake Result</div>
                    {Object.entries(step1Result).slice(0, 6).map(([k, v]) => (
                      <div key={k}><span className="text-slate-400">{k}:</span> <span className="text-slate-800">{String(v)}</span></div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </StepCard>

          {/* Step 2 — AI Intake Fusion */}
          <StepCard id={2} activeStep={activeStep} onSelect={() => setActiveStep(2)} icon={Cpu}
            name="Step 2: AI Intake Fusion"
            desc="Retrieve the advisory for case RQ-1042 — normalized urgency, need type, missing info, human_review_required=true."
          >
            {activeStep === 2 && (
              <div className="mt-4 pt-4 border-t border-slate-100">
                <div className="flex items-center justify-between gap-3">
                  <button type="button" disabled={step2Loading} onClick={runStep2}
                    className="bg-slate-900 hover:bg-slate-800 text-white font-semibold py-2 px-6 rounded-lg text-sm flex items-center gap-2 disabled:opacity-50">
                    {step2Loading ? <><RefreshCw className="w-4 h-4 animate-spin" /> Running…</> : <><Play className="w-4 h-4" /> Run Step</>}
                  </button>
                  {step2Result && <button type="button" onClick={() => navigateStep('intake')} className="text-xs text-rq-primary hover:underline">Open Intake view →</button>}
                </div>
                {step2Result && (
                  <div className="mt-3 bg-white rounded-lg border border-slate-200 p-3 text-xs font-mono text-slate-700 space-y-1">
                    <div className="font-bold text-slate-500 uppercase tracking-wider mb-2 not-italic font-sans text-[10px]">Advisory Result</div>
                    {Object.entries(step2Result).slice(0, 6).map(([k, v]) => (
                      <div key={k}><span className="text-slate-400">{k}:</span> <span className="text-slate-800">{String(v)}</span></div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </StepCard>

          {/* Step 3 — Try Your Own Incident */}
          <StepCard id={3} activeStep={activeStep} onSelect={() => setActiveStep(3)} icon={FileText}
            name="Step 3: Try Your Own Incident"
            desc="Edit the synthetic incident text below and run it live on AMD MI300X. Displays request ID, nonce, latency, and advisory inline."
            highlight
          >
            {activeStep === 3 && (
              <div className="mt-4 pt-4 border-t border-slate-100">
                <textarea
                  value={step3Input}
                  onChange={e => setStep3Input(e.target.value)}
                  rows={3}
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-xs font-mono text-slate-800 focus:outline-none focus:ring-1 focus:ring-emerald-400 resize-none mb-3"
                  placeholder="Enter your synthetic incident text here…"
                />
                <div className="flex items-center justify-between gap-3 mb-3">
                  <button type="button" disabled={step3Loading || !step3Input.trim()} onClick={runStep3}
                    className="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-2 px-6 rounded-lg text-sm flex items-center gap-2 disabled:opacity-50">
                    {step3Loading ? <><RefreshCw className="w-4 h-4 animate-spin" /> Contacting AMD…</> : <><Zap className="w-4 h-4" /> Run My Input on AMD MI300X</>}
                  </button>
                  {step3Result && <button type="button" onClick={() => navigateStep('amd')} className="text-xs text-rq-primary hover:underline">Open AMD Impact →</button>}
                </div>

                {step3Result && (
                  <div className={`rounded-xl p-4 border text-xs ${step3Verified ? 'bg-emerald-50 border-emerald-300' : 'bg-red-50 border-red-300'}`}>
                    <div className={`flex items-center gap-2 font-black text-sm mb-3 ${step3Verified ? 'text-emerald-800' : 'text-red-800'}`}>
                      {step3Verified ? <><CheckCircle className="w-5 h-5" /> VERIFIED LIVE</> : <><XCircle className="w-5 h-5" /> LIVE VERIFICATION FAILED</>}
                    </div>
                    <div className="grid grid-cols-1 gap-1 font-mono mb-3">
                      <EvidRow icon={<Hash className="w-3 h-3" />} label="Request ID" value={step3Result.request_id} />
                      <EvidRow icon={<Hash className="w-3 h-3" />} label="Challenge Nonce" value={step3Result.challenge_nonce} />
                      <EvidRow icon={<Clock className="w-3 h-3" />} label="Timestamp" value={step3Result.verified_at} />
                      <EvidRow icon={<Zap className="w-3 h-3" />} label="Latency" value={step3Result.latency_ms != null ? `${step3Result.latency_ms} ms` : null} />
                      <EvidRow icon={<Cpu className="w-3 h-3" />} label="Model" value={step3Result.underlying_model} />
                      <EvidRow label="Tokens" value={step3Result.total_tokens != null ? String(step3Result.total_tokens) : null} />
                      <EvidRow label="Fallback Used" value={step3Verified ? 'No' : 'Yes'} />
                      <EvidRow label="Human Review" value="Required" />
                    </div>
                    {step3Result.generated_advisory && (
                      <div>
                        <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-sans">Generated Advisory</div>
                        <div className="bg-white rounded p-2 border border-slate-200 text-slate-700 leading-relaxed font-sans">{step3Result.generated_advisory.slice(0, 400)}</div>
                        <div className="mt-1 text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 inline-block font-sans font-bold">
                          Human Review Required — Advisory only
                        </div>
                      </div>
                    )}
                    {step3Result.error && <div className="text-red-700 font-mono bg-red-100 rounded p-2 mt-2">{step3Result.error}</div>}
                  </div>
                )}
              </div>
            )}
          </StepCard>

          {/* Step 4 — Run a Complex Dossier */}
          <StepCard id={4} activeStep={activeStep} onSelect={() => setActiveStep(4)} icon={Bot}
            name="Step 4: Run a Complex Dossier"
            desc="Submit a multi-report, multilingual, OCR-corrupted dossier to AMD MI300X. Shows how the model consolidates conflicting field reports."
            highlight
          >
            {activeStep === 4 && (
              <div className="mt-4 pt-4 border-t border-slate-100">
                <div className="bg-slate-50 rounded-lg border border-slate-200 p-2.5 mb-3 text-[10px] font-mono text-slate-600 max-h-32 overflow-y-auto leading-relaxed whitespace-pre-wrap">
                  {DOSSIER_SAMPLE}
                </div>
                <div className="flex items-center justify-between gap-3 mb-3">
                  <button type="button" disabled={step4Loading} onClick={runStep4}
                    className="bg-purple-600 hover:bg-purple-700 text-white font-semibold py-2 px-6 rounded-lg text-sm flex items-center gap-2 disabled:opacity-50">
                    {step4Loading ? <><RefreshCw className="w-4 h-4 animate-spin" /> Processing dossier…</> : <><Zap className="w-4 h-4" /> Run Complex Dossier on AMD MI300X</>}
                  </button>
                  {step4Result && <button type="button" onClick={() => navigateStep('amd')} className="text-xs text-rq-primary hover:underline">Open AMD Impact →</button>}
                </div>

                {step4Result && (
                  <div className={`rounded-xl p-4 border text-xs ${step4Verified ? 'bg-emerald-50 border-emerald-300' : 'bg-red-50 border-red-300'}`}>
                    <div className={`flex items-center gap-2 font-black text-sm mb-2 ${step4Verified ? 'text-emerald-800' : 'text-red-800'}`}>
                      {step4Verified ? <><CheckCircle className="w-5 h-5" /> VERIFIED LIVE — DOSSIER PROCESSED</> : <><XCircle className="w-5 h-5" /> DOSSIER PROCESSING FAILED</>}
                    </div>
                    <div className="grid grid-cols-1 gap-0.5 font-mono mb-2">
                      <EvidRow icon={<Hash className="w-3 h-3" />} label="Request ID" value={step4Result.request_id} />
                      <EvidRow icon={<Zap className="w-3 h-3" />} label="Latency" value={step4Result.latency_ms != null ? `${step4Result.latency_ms} ms` : null} />
                      <EvidRow label="Tokens" value={step4Result.total_tokens != null ? String(step4Result.total_tokens) : null} />
                      <EvidRow label="Fallback Used" value={step4Verified ? 'No' : 'Yes'} />
                    </div>
                    {step4Result.generated_advisory && (
                      <div className="bg-white rounded p-2 border border-slate-200 text-slate-700 leading-relaxed font-sans text-xs">
                        {step4Result.generated_advisory.slice(0, 400)}
                        <div className="mt-1 text-[10px] text-amber-700 font-bold">Human Review Required</div>
                      </div>
                    )}
                    {step4Result.error && <div className="text-red-700 font-mono bg-red-100 rounded p-2 mt-2">{step4Result.error}</div>}
                  </div>
                )}
              </div>
            )}
          </StepCard>

          {/* Step 5 — Simulate a Burst Workload */}
          <StepCard id={5} activeStep={activeStep} onSelect={() => setActiveStep(5)} icon={List}
            name="Step 5: Simulate a Burst Workload"
            desc="Run 4 concurrent AMD MI300X requests. Each case gets a unique challenge nonce and request ID. Shows aggregate metrics inline."
            highlight
          >
            {activeStep === 5 && (
              <div className="mt-4 pt-4 border-t border-slate-100">
                <div className="text-[10px] text-slate-500 font-mono mb-3">
                  {BURST_SAMPLE.map(c => <div key={c.id}><strong>{c.id}:</strong> {c.text}</div>)}
                </div>
                <div className="flex items-center justify-between gap-3 mb-3">
                  <button type="button" disabled={step5Loading} onClick={runStep5}
                    className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-6 rounded-lg text-sm flex items-center gap-2 disabled:opacity-50">
                    {step5Loading ? <><RefreshCw className="w-4 h-4 animate-spin" /> Running burst…</> : <><Zap className="w-4 h-4" /> Simulate Burst Workload on AMD MI300X</>}
                  </button>
                  {step5Result && <button type="button" onClick={() => navigateStep('amd')} className="text-xs text-rq-primary hover:underline">Open AMD Impact →</button>}
                </div>

                {step5Result && (
                  <div className="rounded-xl p-4 border border-blue-300 bg-blue-50 text-xs">
                    <div className="font-black text-sm text-blue-800 mb-2 flex items-center gap-2">
                      <CheckCircle className="w-5 h-5 text-emerald-600" />
                      Burst Complete — {step5Result.succeeded}/{step5Result.submitted} AMD Live Responses
                    </div>
                    <div className="grid grid-cols-2 gap-1 font-mono mb-3 text-slate-700">
                      <div>Batch ID: <span className="text-slate-900 font-bold">{step5Result.batch_id}</span></div>
                      <div>Elapsed: <span className="text-slate-900 font-bold">{step5Result.total_elapsed_ms} ms</span></div>
                      <div>Median latency: <span className="text-slate-900 font-bold">{step5Result.median_latency_ms ?? '—'} ms</span></div>
                      <div>Total tokens: <span className="text-slate-900 font-bold">{step5Result.total_tokens}</span></div>
                      <div>Human review: <span className="text-amber-700 font-bold">Required</span></div>
                      <div>Failed: <span className={step5Result.failed > 0 ? 'text-red-700 font-bold' : 'text-emerald-700 font-bold'}>{step5Result.failed}</span></div>
                    </div>
                    <div className="space-y-1">
                      {step5Result.cases.map(c => {
                        const live = c.verified_live && !c.fallback_used;
                        return (
                          <div key={c.case_id} className={`rounded p-2 border font-mono ${live ? 'bg-white border-emerald-200' : 'bg-red-50 border-red-200'}`}>
                            <span className="font-bold text-slate-900">{c.case_id}</span>
                            <span className={`ml-2 text-[10px] font-bold ${live ? 'text-emerald-700' : 'text-red-700'}`}>{live ? 'LIVE' : 'FALLBACK'}</span>
                            <span className="ml-2 text-slate-500">req: {c.request_id?.slice(-8) || '—'}</span>
                            <span className="ml-2 text-slate-500">nonce: {c.challenge_nonce || '—'}</span>
                            <span className="ml-2 text-slate-500">{c.latency_ms ?? '—'} ms</span>
                          </div>
                        );
                      })}
                    </div>
                    <div className="mt-2 text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 font-bold">
                      Human Review Required — All cases advisory only, no field dispatch
                    </div>
                  </div>
                )}
              </div>
            )}
          </StepCard>

          {/* Step 6 — Human Coordinator Review */}
          <StepCard id={6} activeStep={activeStep} onSelect={() => setActiveStep(6)} icon={UserCheck}
            name="Step 6: Human Coordinator Review"
            desc="Show assignment suggestion, possible duplicate review, coordinator approval required before any field action."
          >
            {activeStep === 6 && (
              <div className="mt-4 pt-4 border-t border-slate-100 flex justify-end">
                <button type="button" onClick={() => navigateStep('assignments')}
                  className="bg-slate-900 hover:bg-slate-800 text-white font-semibold py-2 px-6 rounded-lg text-sm flex items-center gap-2">
                  <Play className="w-4 h-4" /> Open Assignments
                </button>
              </div>
            )}
          </StepCard>

          {/* Step 7 — Field Coordinator Consumption */}
          <StepCard id={7} activeStep={activeStep} onSelect={() => setActiveStep(7)} icon={Smartphone}
            name="Step 7: Field Coordinator Consumption"
            desc="Show the field-safe mobile task context: safe summary, priority, need type, location confidence, coordinator instruction, and offline update action."
          >
            {activeStep === 7 && (
              <div className="mt-4 pt-4 border-t border-slate-100 flex justify-end">
                <button type="button" onClick={() => navigateStep('sync')}
                  className="bg-slate-900 hover:bg-slate-800 text-white font-semibold py-2 px-6 rounded-lg text-sm flex items-center gap-2">
                  <Play className="w-4 h-4" /> Open Field View
                </button>
              </div>
            )}
          </StepCard>
        </div>
      </div>
    </div>
  );
}

function StepCard({
  id, activeStep, onSelect, icon: Icon, name, desc, highlight, children,
}: {
  id: number; activeStep: number; onSelect: () => void; icon: React.ElementType;
  name: string; desc: string; highlight?: boolean; children?: React.ReactNode;
}) {
  const isActive = activeStep === id;
  const isDone = activeStep > id;
  return (
    <div
      className={`bg-white border rounded-xl p-4 transition-all cursor-pointer ${
        isActive
          ? highlight ? 'border-emerald-500 ring-1 ring-emerald-500 shadow-md' : 'border-rq-primary ring-1 ring-rq-primary shadow-md'
          : 'border-slate-200 shadow-sm opacity-80 hover:opacity-100'
      }`}
      onClick={onSelect}
    >
      <div className="flex gap-4">
        <div className={`p-3 rounded-lg shrink-0 h-fit ${isActive ? (highlight ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-rq-primary') : isDone ? 'bg-slate-100 text-slate-700' : 'bg-slate-50 text-slate-400'}`}>
          <Icon className="w-6 h-6" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className={`font-bold ${isActive ? 'text-slate-900' : 'text-slate-700'}`}>{name}</h3>
          <p className="text-sm text-slate-600 mt-1">{desc}</p>
          {children}
        </div>
      </div>
    </div>
  );
}

function EvidRow({ icon, label, value }: { icon?: React.ReactNode; label: string; value: string | number | null | undefined }) {
  return (
    <div className="flex items-start gap-1.5">
      {icon && <span className="text-slate-400 mt-0.5 shrink-0">{icon}</span>}
      <span className="text-slate-500">{label}:</span>
      <span className="text-slate-800 break-all">{value != null && value !== '' ? String(value) : '—'}</span>
    </div>
  );
}
