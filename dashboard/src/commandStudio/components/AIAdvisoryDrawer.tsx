import React, { useState } from 'react';
import { DetailDrawer } from './Shared';
import { useApp } from '../context/AppContext';
import { Cpu, CheckCircle, Clock, AlertTriangle, ShieldCheck } from 'lucide-react';
import { actionLog } from '../lib/actionLog';

export function AIAdvisoryDrawer({ isOpen, onClose, caseId, data, resultId }: any) {
  const { showToast, navigate } = useApp();
  const [isRunning, setIsRunning] = useState(false);
  const [localData, setLocalData] = useState(data);

  if (!isOpen) return null;

  const handleRunAdvisory = (mode: 'live' | 'fallback') => {
    if (mode === 'live') {
      showToast('Opening the consented, nonce-bound live AMD test.', 'info');
      actionLog.add('Open Live AMD Test', 'Navigation', 'Opened', { caseId });
      onClose();
      navigate('amd');
      return;
    }

    setIsRunning(true);
    showToast('Preparing deterministic local advisory support. No provider call will be made.', 'info');

    setTimeout(() => {
      setIsRunning(false);
      showToast('Deterministic advisory prepared for coordinator review.', 'success');
      actionLog.add('Deterministic Advisory Run', 'Local Processing', 'Success', { mode, caseId });

      setLocalData({
        ...localData,
        inferenceMode: 'Deterministic Local Advisory',
        providerStatus: 'Not contacted',
        latency: 'Local · no provider call',
        summary: localData?.summary || 'Review this case with coordinator approval required.',
        questions: localData?.questions?.length
          ? localData.questions
          : ['Have you verified the exact coordinate precision?', 'Are there secondary hazards?'],
        warnings: localData?.warnings?.length
          ? localData.warnings
          : ['Local deterministic support only; no provider-authored synthesis was requested.']
      });
    }, 300);
  };

  const handleAction = (action: string) => {
    showToast(`Action '${action}' applied to ${caseId}.`, 'success');
    actionLog.add(`Advisory Action: ${action}`, 'UI Interaction', 'Success', { caseId });
    if (action === 'Queue Coordinator Approval' || action === 'Send to Quality Review') {
      onClose();
    }
  };

  const sourceData = localData || data || {
    summary: 'Awaiting deterministic enrichment...',
    priority: 'Unknown',
    needType: 'Unknown',
    locationConfidence: 'Low',
    questions: [],
    duplicateCluster: null,
    assignment: null,
    publicSummary: '',
    replyDraft: '',
    operatorNote: '',
    warnings: []
  };
  const currentData = {
    ...sourceData,
    inferenceMode: 'Deterministic Local Advisory',
    providerStatus: 'Not contacted',
    latency: 'Local · no provider call'
  };

  return (
    <DetailDrawer isOpen={isOpen} onClose={onClose} title={`Case: ${caseId}`}>
      <div className="flex flex-col gap-6 h-full" data-result-id={resultId} aria-live="polite">
        <div className="bg-slate-900 text-white rounded-lg p-4 flex flex-col gap-3">
          <div className="flex justify-between items-center">
            <h4 className="font-bold flex items-center gap-2"><Cpu className="w-5 h-5 text-emerald-400" /> AI Advisory State</h4>
            <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${currentData.inferenceMode?.includes('Live') ? 'bg-emerald-900/50 text-emerald-400 border border-emerald-500/30' : 'bg-slate-800 text-slate-400 border border-slate-700'}`}>
              <span data-testid="assignment-advisory-mode">{currentData.inferenceMode}</span>
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="bg-slate-800 p-2 rounded border border-slate-700">
              <span className="text-slate-400 block text-[10px] uppercase font-bold tracking-wider mb-1">Provider</span>
              <span data-testid="assignment-advisory-provider">{currentData.providerStatus}</span>
            </div>
            <div className="bg-slate-800 p-2 rounded border border-slate-700 flex flex-col justify-center">
              <span className="text-slate-400 block text-[10px] uppercase font-bold tracking-wider mb-1">Latency</span>
              <div data-testid="assignment-advisory-latency" className="flex items-center gap-1"><Clock className="w-3 h-3 text-emerald-400"/> {currentData.latency}</div>
            </div>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            data-action-id="assignment.open_live_amd_test"
            disabled={isRunning}
            onClick={() => handleRunAdvisory('live')}
            className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold py-2 rounded shadow-sm disabled:opacity-50 transition-colors"
          >
            Open Live AMD Test
          </button>
          <button
            data-action-id="assignment.run_deterministic_advisory"
            disabled={isRunning}
            onClick={() => handleRunAdvisory('fallback')}
            className="flex-1 bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 text-sm font-semibold py-2 rounded shadow-sm disabled:opacity-50 transition-colors"
          >
            Run Deterministic
          </button>
        </div>

        {isRunning ? (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-3">
            <div className="w-8 h-8 border-4 border-slate-200 border-t-emerald-500 rounded-full animate-spin"></div>
            <div className="text-sm font-medium">Preparing Deterministic Advisory...</div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto space-y-5">
            <div>
              <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Safe Summary</h4>
              <p className="text-sm text-slate-800 bg-white p-3 rounded-lg border border-slate-200">{currentData.summary}</p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="bg-white p-3 rounded-lg border border-slate-200">
                <div className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-1">Suggested Priority</div>
                <div className="font-semibold text-slate-900">{currentData.priority}</div>
              </div>
              <div className="bg-white p-3 rounded-lg border border-slate-200">
                <div className="text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-1">Need Type</div>
                <div className="font-semibold text-slate-900">{currentData.needType}</div>
              </div>
            </div>

            {currentData.warnings?.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 p-3 rounded-lg flex gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
                <div>
                  <h5 className="text-sm font-bold text-amber-900">Advisory Warnings</h5>
                  <ul className="text-sm text-amber-800 list-disc pl-4 mt-1 space-y-1">
                    {currentData.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              </div>
            )}

            {currentData.questions?.length > 0 && (
              <div>
                <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 flex justify-between">
                  Missing Info Prompts 
                  <button onClick={() => handleAction('Request Missing Info')} className="text-rq-primary hover:underline">Send Request</button>
                </h4>
                <ul className="text-sm text-slate-700 bg-white p-3 rounded-lg border border-slate-200 list-disc pl-5 space-y-1">
                  {currentData.questions.map((q: string, i: number) => <li key={i}>{q}</li>)}
                </ul>
              </div>
            )}
            
            {currentData.publicSummary && (
              <div>
                <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 flex justify-between">
                  Public Redacted Draft
                  <button onClick={() => handleAction('Copy Public Summary Draft')} className="text-rq-primary hover:underline">Copy Draft</button>
                </h4>
                <div className="text-sm text-slate-700 bg-slate-50 p-3 rounded-lg border border-slate-200 font-serif">
                  {currentData.publicSummary}
                </div>
              </div>
            )}

            <div className="bg-slate-100 border border-slate-200 p-3 rounded-lg flex items-center justify-between text-sm">
              <div className="flex items-center gap-2 font-semibold text-slate-700">
                <ShieldCheck className="w-5 h-5 text-rq-primary" /> Coordinator Approval Required
              </div>
            </div>
          </div>
        )}
        
        <div className="pt-4 mt-auto border-t border-slate-200 flex flex-col gap-2 shrink-0">
          <button onClick={() => handleAction('Queue Coordinator Approval')} className="w-full py-2.5 bg-rq-primary hover:bg-rq-primary-hover text-white rounded-lg font-semibold shadow-sm transition-colors flex items-center justify-center gap-2">
            <CheckCircle className="w-4 h-4" /> Queue Coordinator Approval
          </button>
          <button onClick={() => handleAction('Send to Quality Review')} className="w-full py-2.5 bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 rounded-lg font-semibold shadow-sm transition-colors">
            Send to Quality Review
          </button>
        </div>
      </div>
    </DetailDrawer>
  );
}
