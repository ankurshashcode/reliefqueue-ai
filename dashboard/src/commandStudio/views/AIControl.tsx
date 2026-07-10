import React, { useState } from 'react';
import { Cpu, ShieldAlert, CheckCircle, Database, Shield, Lock, ShieldCheck, Bot } from 'lucide-react';
import { useApp } from '../context/AppContext';

export function AIControl() {
  const { addLog, showToast } = useApp();
  const [step, setStep] = useState<'settings' | 'test' | 'confirm'>('settings');
  const [provider, setProvider] = useState('Google Gemini');
  const [model, setModel] = useState('Gemini 1.5 Pro');
  
  const [testResult, setTestResult] = useState<string | null>(null);

  const handleTestConnection = () => {
    showToast('Testing simulated connection...', 'info');
    setTimeout(() => {
      setTestResult('ok');
      addLog('Connection Tested', 'Simulated health result returned nominal.');
      showToast('Connection verified successfully (Demo).', 'success');
    }, 800);
  };

  const handleRunTest = () => {
    addLog('Comparative Test Run', `Generated deterministic validation result for ${model}`);
    showToast('Validation test generated.', 'success');
  };

  const handleApprove = () => {
    addLog('Approve Advisory Model Change', 'Created review-approved advisory config state only. No dispatch authority granted.');
    showToast('Advisory config approved locally.', 'success');
    setStep('settings');
  };

  const renderSettings = () => (
    <div className="max-w-4xl mx-auto space-y-6">
       <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
          <h2 className="text-xl font-bold text-slate-900 mb-6">Model Configuration</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-bold text-slate-700 mb-2">Advisory Provider</label>
              <select 
                value={provider} 
                onChange={(e) => setProvider(e.target.value)}
                className="w-full bg-slate-50 border border-slate-300 text-slate-900 text-sm rounded-lg focus:ring-rq-primary focus:border-rq-primary block p-2.5"
              >
                <option>Google Gemini</option>
                <option>Anthropic Claude</option>
                <option>OpenAI / vLLM (Compatible)</option>
                <option>Local Fallback Model</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-bold text-slate-700 mb-2">Model Version</label>
              <select 
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full bg-slate-50 border border-slate-300 text-slate-900 text-sm rounded-lg focus:ring-rq-primary focus:border-rq-primary block p-2.5"
              >
                {provider.includes('Gemini') && <option>Gemini 1.5 Pro</option>}
                {provider.includes('Gemini') && <option>Gemini 1.5 Flash</option>}
                {provider.includes('Claude') && <option>Claude 3.5 Sonnet</option>}
                {!provider.includes('Gemini') && !provider.includes('Claude') && <option>Default Model</option>}
              </select>
            </div>
          </div>
          
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mt-6 ring-1 ring-purple-500/20 shadow-purple-500/10">
            <h2 className="text-xl font-bold text-slate-900 mb-6 flex items-center gap-2">
              <Bot className="w-5 h-5 text-purple-600" /> Gemma 4 Bonus Lane
            </h2>
            <div className="flex flex-col sm:flex-row gap-6">
              <div className="flex-1 space-y-4 text-sm text-slate-700">
                <p><strong>Lane Status:</strong> <span className="text-purple-600 font-bold bg-purple-50 px-2 py-1 rounded border border-purple-200">Validation Pending</span></p>
                <p><strong>Endpoint Type:</strong> vLLM/OpenAI-compatible through backend</p>
                <p><strong>Task:</strong> Structured triage and reasoning</p>
                <p><strong>Output Format:</strong> Strict advisory JSON</p>
              </div>
              <div className="flex-1 bg-purple-50 p-4 rounded-lg border border-purple-100">
                <h4 className="font-bold text-purple-900 mb-2 text-sm">Supported Demo Tasks:</h4>
                <ul className="text-xs text-purple-800 space-y-1 list-disc pl-4">
                  <li>Summarize synthetic field report</li>
                  <li>Explain urgency suggestion</li>
                  <li>Suggest missing fields</li>
                  <li>Identify possible duplicate rationale</li>
                  <li>Draft public redacted summary</li>
                  <li>Draft coordinator-safe reply</li>
                </ul>
                <div className="mt-3 text-xs font-bold text-purple-900 uppercase tracking-wider">human_review_required = true</div>
              </div>
            </div>
          </div>

          <div className="mt-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-t border-slate-100 pt-6">
            <button onClick={handleTestConnection} className="bg-white border border-slate-300 text-slate-700 font-semibold px-4 py-2 rounded-lg hover:bg-slate-50 transition-colors shadow-sm">
              Test Connection
            </button>
            {testResult === 'ok' && (
               <span className="flex items-center gap-2 text-emerald-600 font-bold text-sm bg-emerald-50 px-3 py-1.5 rounded-md border border-emerald-200">
                 <CheckCircle className="w-4 h-4"/> Connection Healthy
               </span>
            )}
          </div>
       </div>

       <div className="flex justify-end pt-4">
         <button onClick={() => setStep('test')} className="bg-rq-primary text-white font-semibold px-6 py-3 rounded-lg hover:bg-rq-primary-hover shadow-sm transition-colors">
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
                <Cpu className="w-5 h-5 text-rq-primary"/> Candidate Model Validation
              </h2>
              <p className="text-slate-500 text-sm mt-1">Run deterministic safety checks on selected advisory model.</p>
            </div>
            <button onClick={handleRunTest} className="bg-slate-800 text-white font-semibold px-4 py-2 rounded-lg hover:bg-slate-900 shadow-sm transition-colors">
              Run Comparative Test
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="border border-emerald-200 bg-emerald-50 p-4 rounded-lg flex gap-3">
              <ShieldCheck className="w-5 h-5 text-emerald-600 shrink-0"/>
              <div>
                <div className="font-bold text-sm text-emerald-900">Schema Validation</div>
                <div className="text-xs text-emerald-800 mt-1">Output strictly matches expected JSON interface.</div>
              </div>
            </div>
            <div className="border border-emerald-200 bg-emerald-50 p-4 rounded-lg flex gap-3">
              <Lock className="w-5 h-5 text-emerald-600 shrink-0"/>
              <div>
                <div className="font-bold text-sm text-emerald-900">Redaction Check</div>
                <div className="text-xs text-emerald-800 mt-1">PII and secrets are reliably masked.</div>
              </div>
            </div>
            <div className="border border-emerald-200 bg-emerald-50 p-4 rounded-lg flex gap-3">
              <ShieldAlert className="w-5 h-5 text-emerald-600 shrink-0"/>
              <div>
                <div className="font-bold text-sm text-emerald-900">Safety Phrase Guard</div>
                <div className="text-xs text-emerald-800 mt-1">No dispatch authority or rescue guarantees generated.</div>
              </div>
            </div>
          </div>

          <div className="bg-slate-900 text-emerald-400 p-4 rounded-lg font-mono text-xs overflow-x-auto relative">
             <div className="absolute top-2 right-2 bg-slate-800 text-slate-300 px-2 py-1 rounded text-[10px] uppercase font-bold tracking-wider">Advisory JSON Preview</div>
             <pre>
{`{
  "advisory_type": "Triage Suggestion",
  "recommended_priority": "CRITICAL",
  "suggested_assignment": "Alpha Team",
  "confidence_score": 0.94,
  "system_note": "COORDINATOR APPROVAL REQUIRED. Not a dispatch order.",
  "redacted_contact": "[MASKED_PHONE_NUMBER]"
}`}
             </pre>
          </div>
       </div>

       <div className="flex justify-end pt-4 gap-3">
         <button onClick={() => { addLog('Save Test Result'); showToast('Saved', 'info'); }} className="bg-white border border-slate-300 text-slate-700 font-semibold px-6 py-3 rounded-lg hover:bg-slate-50 shadow-sm transition-colors">
           Save Test Result
         </button>
         <button onClick={() => setStep('confirm')} className="bg-rq-primary text-white font-semibold px-6 py-3 rounded-lg hover:bg-rq-primary-hover shadow-sm transition-colors">
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
             <ShieldAlert className="w-8 h-8 text-rq-amber"/>
           </div>
           <div>
             <h2 className="text-2xl font-bold text-rq-amber-dark mb-2">Approve Advisory Model Change</h2>
             <p className="text-slate-800 mb-4 leading-relaxed font-medium">
               This changes the advisory triage suggestions and confidence models only. 
               <br/><br/>
               <span className="font-bold uppercase tracking-wide text-xs bg-amber-200 px-2 py-1 rounded border border-amber-300">Safety Boundary Requirement</span>
               <br/>
               It does <span className="underline font-bold">not</span> dispatch teams, confirm safety, close cases, or override coordinator approval. Human review remains strictly required for all assignments.
             </p>
             
             <div className="bg-white border border-amber-200 p-4 rounded-lg mt-4 text-sm font-mono text-slate-700 shadow-sm">
               Target Model: <span className="font-bold text-slate-900">{model}</span><br/>
               Provider: <span className="font-bold text-slate-900">{provider}</span><br/>
               Rollback Available: <span className="text-emerald-600 font-bold">Yes (Version -1 cached locally)</span>
             </div>
           </div>
         </div>
       </div>

       <div className="flex flex-col sm:flex-row justify-end gap-3 pt-4 border-t border-slate-200">
         <button onClick={() => showToast('Rollback available locally for demo.', 'info')} className="bg-white border border-slate-300 text-slate-700 font-semibold px-6 py-3 rounded-lg hover:bg-slate-50 transition-colors">
           Roll Back to Previous
         </button>
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
        
        {/* Progress Steps */}
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

function Step({ indicator, label, active }: any) {
  return (
    <div className={`flex flex-col items-center gap-2 ${active ? 'opacity-100' : 'opacity-50'}`}>
       <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm border-2 transition-colors
         ${active ? 'bg-rq-primary text-white border-rq-primary' : 'bg-white text-slate-500 border-slate-300'}
       `}>
         {indicator}
       </div>
       <div className="text-[10px] md:text-xs font-bold text-slate-700 uppercase tracking-wider hidden sm:block">{label}</div>
    </div>
  );
}
