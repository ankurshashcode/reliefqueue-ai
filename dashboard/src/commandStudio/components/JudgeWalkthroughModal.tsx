import React, { useEffect, useState } from 'react';
import { X, Play, Cpu, Bot, UserCheck, Smartphone, CheckCircle } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { actionLog } from '../lib/actionLog';

export function JudgeWalkthroughModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { showToast, navigate } = useApp();
  const [activeStep, setActiveStep] = useState(1);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleRunStep = (stepNumber: number, stepName: string, targetRoute: string) => {
    setRunning(true);
    showToast(`Executing Demo Step: ${stepName}...`, 'info');
    
    setTimeout(() => {
      setRunning(false);
      showToast(`${stepName} completed.`, 'success');
      actionLog.add(`Judge Demo Walkthrough`, 'Demo Execution', 'Success', { step: stepNumber, name: stepName });
      navigate(targetRoute);
      onClose();
    }, 1500);
  };

  const steps = [
    {
      id: 1,
      name: 'Step 1: Synthetic Intake Burst',
      desc: 'Show messy incoming reports from SMS, WhatsApp, field form, operator note, voice transcript, and media caption.',
      icon: Play,
      route: 'intake'
    },
    {
      id: 2,
      name: 'Step 2: AI Intake Fusion',
      desc: 'Show normalized messages, extracted urgency, need type, missing information, location confidence, possible duplicate candidates, and human_review_required=true.',
      icon: Cpu,
      route: 'intake'
    },
    {
      id: 3,
      name: 'Step 3: AMD/vLLM Advisory Run',
      desc: 'Show live AMD/vLLM advisory if configured. Otherwise show deterministic fallback with clear status. Show latency, provider status, schema validation, redaction check, safety phrase guard, and advisory object.',
      icon: Bot,
      route: 'amd'
    },
    {
      id: 4,
      name: 'Step 4: Human Coordinator Review',
      desc: 'Show assignment suggestion, possible duplicate review, public summary draft, and coordinator approval required.',
      icon: UserCheck,
      route: 'assignments'
    },
    {
      id: 5,
      name: 'Step 5: Field Coordinator Consumption',
      desc: 'Show the field-safe mobile task context: safe summary, priority, need type, location confidence, coordinator instruction, masked relay, and offline update action.',
      icon: Smartphone,
      route: 'sync'
    }
  ];

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
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
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
          {steps.map(step => {
            const Icon = step.icon;
            const isActive = activeStep === step.id;
            const isDone = activeStep > step.id;
            
            return (
              <div 
                key={step.id} 
                className={`bg-white border rounded-xl p-4 transition-all ${isActive ? 'border-emerald-500 ring-1 ring-emerald-500 shadow-md' : 'border-slate-200 shadow-sm opacity-80 hover:opacity-100'}`}
                onClick={() => setActiveStep(step.id)}
              >
                <div className="flex gap-4">
                  <div className={`p-3 rounded-lg shrink-0 h-fit ${isActive ? 'bg-emerald-100 text-emerald-700' : isDone ? 'bg-slate-100 text-slate-700' : 'bg-slate-50 text-slate-400'}`}>
                    <Icon className="w-6 h-6" />
                  </div>
                  <div className="flex-1">
                    <h3 className={`font-bold ${isActive ? 'text-slate-900' : 'text-slate-700'}`}>{step.name}</h3>
                    <p className="text-sm text-slate-600 mt-1">{step.desc}</p>
                    
                    {isActive && (
                      <div className="mt-4 pt-4 border-t border-slate-100 flex justify-end">
                        <button 
                          type="button"
                          disabled={running}
                          onClick={(e) => { e.stopPropagation(); handleRunStep(step.id, step.name, step.route); }} 
                          className="bg-slate-900 hover:bg-slate-800 text-white font-semibold py-2 px-6 rounded-lg text-sm transition-colors flex items-center gap-2 disabled:opacity-50"
                        >
                          {running ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Play className="w-4 h-4" />}
                          Try it
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
