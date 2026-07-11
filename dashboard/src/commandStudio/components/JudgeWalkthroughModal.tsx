import React, { useEffect, useState } from 'react';
import { X, Play, Cpu, Bot, UserCheck, Smartphone, CheckCircle, RefreshCw, Hash, Clock, Zap, XCircle } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { actionLog } from '../lib/actionLog';
import { postProduct, actionKey } from '../lib/productActions';

interface AmdResult {
  verified_live: boolean;
  fallback_used: boolean;
  request_id: string | null;
  verified_at: string | null;
  latency_ms: number | null;
  served_model: string | null;
  underlying_model: string | null;
  accelerator: string | null;
  runtime: string | null;
  generated_advisory: string | null;
  warnings: string[];
  error: string | null;
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

  // Step 3 state (AMD live)
  const [step3Loading, setStep3Loading] = useState(false);
  const [step3Result, setStep3Result] = useState<AmdResult | null>(null);

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
      });
      const data: AmdResult = await res.json();
      setStep3Result(data);
      actionLog.add('Judge Demo Walkthrough', 'AMD Live Verification', data.verified_live ? 'VERIFIED LIVE' : 'Failed', {
        step: 3,
        request_id: data.request_id,
        latency_ms: data.latency_ms,
      });
      if (data.verified_live && !data.fallback_used) {
        addLog('Step 3 — AMD VERIFIED LIVE', `Request ${data.request_id} · ${data.latency_ms} ms · ${data.underlying_model}`);
      } else {
        addLog('Step 3 — AMD Failed', data.error || 'Endpoint did not confirm live inference.');
      }
    } catch (err: any) {
      setStep3Result({
        verified_live: false,
        fallback_used: true,
        request_id: null,
        verified_at: null,
        latency_ms: null,
        served_model: null,
        underlying_model: null,
        accelerator: null,
        runtime: null,
        generated_advisory: null,
        warnings: [],
        error: err?.message || 'Network request failed',
      });
    } finally {
      setStep3Loading(false);
    }
  };

  const navigateStep = (route: string) => {
    navigate(route);
    onClose();
  };

  const step3Verified = step3Result?.verified_live === true && step3Result?.fallback_used === false;

  return (
    <div
      className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-[100] flex items-center justify-center p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
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
          <button
            type="button"
            onClick={onClose}
            aria-label="Close Judge Demo Walkthrough"
            className="p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50">

          {/* Step 1 */}
          <StepCard
            id={1}
            activeStep={activeStep}
            onSelect={() => setActiveStep(1)}
            icon={Play}
            name="Step 1: Synthetic Intake Burst"
            desc="Process an incoming synthetic report from SMS to show multi-source normalization. Result is displayed inline."
          >
            {activeStep === 1 && (
              <div className="mt-4 pt-4 border-t border-slate-100">
                <div className="flex items-center justify-between gap-3">
                  <button
                    type="button"
                    disabled={step1Loading}
                    onClick={runStep1}
                    className="bg-slate-900 hover:bg-slate-800 text-white font-semibold py-2 px-6 rounded-lg text-sm transition-colors flex items-center gap-2 disabled:opacity-50"
                  >
                    {step1Loading ? <><RefreshCw className="w-4 h-4 animate-spin" /> Running…</> : <><Play className="w-4 h-4" /> Run Step</>}
                  </button>
                  {step1Result && (
                    <button type="button" onClick={() => navigateStep('intake')} className="text-xs text-rq-primary hover:underline">
                      Open Intake view →
                    </button>
                  )}
                </div>
                {step1Result && (
                  <div className="mt-3 bg-white rounded-lg border border-slate-200 p-3 text-xs font-mono text-slate-700 space-y-1">
                    <div className="font-bold text-slate-500 uppercase tracking-wider mb-2 not-italic not-mono font-sans text-[10px]">Intake Result</div>
                    {Object.entries(step1Result).slice(0, 6).map(([k, v]) => (
                      <div key={k}><span className="text-slate-400">{k}:</span> <span className="text-slate-800">{String(v)}</span></div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </StepCard>

          {/* Step 2 */}
          <StepCard
            id={2}
            activeStep={activeStep}
            onSelect={() => setActiveStep(2)}
            icon={Cpu}
            name="Step 2: AI Intake Fusion"
            desc="Retrieve the AI advisory for case RQ-1042 — normalized urgency, need type, missing info, and human_review_required=true."
          >
            {activeStep === 2 && (
              <div className="mt-4 pt-4 border-t border-slate-100">
                <div className="flex items-center justify-between gap-3">
                  <button
                    type="button"
                    disabled={step2Loading}
                    onClick={runStep2}
                    className="bg-slate-900 hover:bg-slate-800 text-white font-semibold py-2 px-6 rounded-lg text-sm transition-colors flex items-center gap-2 disabled:opacity-50"
                  >
                    {step2Loading ? <><RefreshCw className="w-4 h-4 animate-spin" /> Running…</> : <><Play className="w-4 h-4" /> Run Step</>}
                  </button>
                  {step2Result && (
                    <button type="button" onClick={() => navigateStep('intake')} className="text-xs text-rq-primary hover:underline">
                      Open Intake view →
                    </button>
                  )}
                </div>
                {step2Result && (
                  <div className="mt-3 bg-white rounded-lg border border-slate-200 p-3 text-xs font-mono text-slate-700 space-y-1">
                    <div className="font-bold text-slate-500 uppercase tracking-wider mb-2 not-italic not-mono font-sans text-[10px]">Advisory Result</div>
                    {Object.entries(step2Result).slice(0, 6).map(([k, v]) => (
                      <div key={k}><span className="text-slate-400">{k}:</span> <span className="text-slate-800">{String(v)}</span></div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </StepCard>

          {/* Step 3 — AMD Live Verification */}
          <StepCard
            id={3}
            activeStep={activeStep}
            onSelect={() => setActiveStep(3)}
            icon={Bot}
            name="Step 3: AMD/vLLM Advisory Run"
            desc="Execute a real AMD Developer Cloud inference request. Displays request ID, model, timestamp, latency, and the generated advisory inline."
            highlight
          >
            {activeStep === 3 && (
              <div className="mt-4 pt-4 border-t border-slate-100">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <button
                    type="button"
                    disabled={step3Loading}
                    onClick={runStep3}
                    className="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-2 px-6 rounded-lg text-sm transition-colors flex items-center gap-2 disabled:opacity-50"
                  >
                    {step3Loading
                      ? <><RefreshCw className="w-4 h-4 animate-spin" /> Contacting AMD…</>
                      : <><Zap className="w-4 h-4" /> Run Live AMD Verification</>}
                  </button>
                  {step3Result && (
                    <button type="button" onClick={() => navigateStep('amd')} className="text-xs text-rq-primary hover:underline">
                      Open AMD Impact →
                    </button>
                  )}
                </div>

                {step3Result && (
                  <div className={`rounded-xl p-4 border text-xs ${step3Verified ? 'bg-emerald-50 border-emerald-300' : 'bg-red-50 border-red-300'}`}>
                    {/* Status banner */}
                    <div className={`flex items-center gap-2 font-black text-sm mb-3 ${step3Verified ? 'text-emerald-800' : 'text-red-800'}`}>
                      {step3Verified
                        ? <><CheckCircle className="w-5 h-5" /> VERIFIED LIVE</>
                        : <><XCircle className="w-5 h-5" /> LIVE VERIFICATION FAILED</>}
                    </div>

                    {/* Evidence grid */}
                    <div className="grid grid-cols-1 gap-1 font-mono mb-3">
                      <EvidRow icon={<Hash className="w-3 h-3" />} label="Request ID" value={step3Result.request_id} />
                      <EvidRow icon={<Clock className="w-3 h-3" />} label="Timestamp" value={step3Result.verified_at} />
                      <EvidRow icon={<Zap className="w-3 h-3" />} label="Latency" value={step3Result.latency_ms != null ? `${step3Result.latency_ms} ms` : null} />
                      <EvidRow icon={<Cpu className="w-3 h-3" />} label="Model" value={step3Result.underlying_model} />
                      <EvidRow label="Accelerator" value={step3Result.accelerator} />
                      <EvidRow label="Runtime" value={step3Result.runtime} />
                      <EvidRow label="Live / Fallback" value={step3Verified ? 'Live — no fallback' : 'Fallback used'} />
                    </div>

                    {/* Advisory output */}
                    {step3Result.generated_advisory && (
                      <div>
                        <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1 font-sans">Generated Advisory</div>
                        <div className="bg-white rounded p-2 border border-slate-200 text-slate-700 leading-relaxed not-italic font-sans">
                          {step3Result.generated_advisory}
                        </div>
                        <div className="mt-1 text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 inline-block font-sans font-bold">
                          Human Review Required — Advisory only
                        </div>
                      </div>
                    )}

                    {step3Result.error && (
                      <div className="text-red-700 font-mono bg-red-100 rounded p-2 mt-2">{step3Result.error}</div>
                    )}
                  </div>
                )}
              </div>
            )}
          </StepCard>

          {/* Step 4 */}
          <StepCard
            id={4}
            activeStep={activeStep}
            onSelect={() => setActiveStep(4)}
            icon={UserCheck}
            name="Step 4: Human Coordinator Review"
            desc="Show assignment suggestion, possible duplicate review, public summary draft, and coordinator approval required."
          >
            {activeStep === 4 && (
              <div className="mt-4 pt-4 border-t border-slate-100 flex justify-end">
                <button
                  type="button"
                  onClick={() => navigateStep('assignments')}
                  className="bg-slate-900 hover:bg-slate-800 text-white font-semibold py-2 px-6 rounded-lg text-sm transition-colors flex items-center gap-2"
                >
                  <Play className="w-4 h-4" /> Open Assignments
                </button>
              </div>
            )}
          </StepCard>

          {/* Step 5 */}
          <StepCard
            id={5}
            activeStep={activeStep}
            onSelect={() => setActiveStep(5)}
            icon={Smartphone}
            name="Step 5: Field Coordinator Consumption"
            desc="Show the field-safe mobile task context: safe summary, priority, need type, location confidence, coordinator instruction, masked relay, and offline update action."
          >
            {activeStep === 5 && (
              <div className="mt-4 pt-4 border-t border-slate-100 flex justify-end">
                <button
                  type="button"
                  onClick={() => navigateStep('sync')}
                  className="bg-slate-900 hover:bg-slate-800 text-white font-semibold py-2 px-6 rounded-lg text-sm transition-colors flex items-center gap-2"
                >
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
  id,
  activeStep,
  onSelect,
  icon: Icon,
  name,
  desc,
  highlight,
  children,
}: {
  id: number;
  activeStep: number;
  onSelect: () => void;
  icon: React.ElementType;
  name: string;
  desc: string;
  highlight?: boolean;
  children?: React.ReactNode;
}) {
  const isActive = activeStep === id;
  const isDone = activeStep > id;
  return (
    <div
      className={`bg-white border rounded-xl p-4 transition-all cursor-pointer ${
        isActive
          ? highlight
            ? 'border-emerald-500 ring-1 ring-emerald-500 shadow-md'
            : 'border-rq-primary ring-1 ring-rq-primary shadow-md'
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
