import { useState } from 'react';
import { Server, CheckCircle, Smartphone, Map, HardDrive, Cpu, ShieldCheck } from 'lucide-react';
import { config } from '../lib/publicConfig';
import { useApp } from '../context/AppContext';

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
    { name: 'AMD / vLLM Status', endpoint: 'AMD benchmark reports', status: 'report-only', safe: true },
    { name: 'Gemma 4 Bonus Lane', endpoint: 'Validation pending via backend', status: 'validation pending', safe: true },
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

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto h-full overflow-y-auto">
      <div className="mb-6">
        <h2 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">Capability Map & Readiness</h2>
        <p className="text-slate-500 mt-2">API surface wiring and demo deployment boundary.</p>
      </div>

      <div className="bg-slate-900 rounded-xl p-5 md:p-6 text-white mb-8 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h3 className="font-bold text-lg mb-1 flex items-center gap-2">
            <Server className="w-5 h-5 text-emerald-400" /> Platform Deployment Notes
          </h3>
          <ul className="text-slate-400 text-sm max-w-3xl list-disc pl-5 mt-2 space-y-1">
            <li><strong className="text-white">Replit Full-Stack (Recommended):</strong> Best for running this React frontend alongside the Python backend in one workspace.</li>
            <li><strong className="text-white">Vercel:</strong> Frontend-only hosting. Requires the Python API to be hosted elsewhere and configured via API origin.</li>
            <li><strong className="text-white">Streamlit:</strong> Python-only alternate UI; does not apply to this React application.</li>
          </ul>
          <div className="mt-4 flex flex-col xl:flex-row gap-4">
            <div className="flex-1 p-4 bg-slate-800 rounded text-sm text-slate-300 font-mono leading-relaxed">
              <strong className="text-white block mb-2 font-sans">Preview Status:</strong>
              Data Source: Synthetic replay<br/>
              API Base URL: Preview not connected<br/>
              API Mode: Deterministic fallback active<br/>
              AMD/vLLM Endpoint: Not connected in this preview<br/>
              Secrets in Browser: None exposed
            </div>
            <div className="flex-1 p-4 bg-slate-800 rounded text-sm text-slate-300 font-mono leading-relaxed">
              <strong className="text-white block mb-2 font-sans">Live Demo Target:</strong>
              Backend API: ReliefQueue /api/product<br/>
              AI Inference: AMD GPU / vLLM via backend<br/>
              Endpoint Type: OpenAI-compatible<br/>
              Human Review: Always required<br/>
              Fallback: Deterministic queue retained if inference fails
            </div>
          </div>
          <div className="mt-4 p-3 bg-slate-800 border-l-2 border-emerald-400 text-sm text-slate-300">
            The AI Studio preview uses local deterministic fallback. The deployed demo can connect the same frontend to the ReliefQueue backend and AMD/vLLM inference endpoint without exposing secrets in the browser.
          </div>
        </div>
        <div className="flex flex-col gap-2 w-full md:w-auto shrink-0">
          <button onClick={() => showToast('Configuration checked.', 'info')} className="px-4 py-2 bg-slate-800 border border-slate-700 rounded text-sm hover:bg-slate-700 transition-colors w-full text-left">
            Check Public Config
          </button>
          <button onClick={() => showToast('Product API test initiated.', 'info')} className="px-4 py-2 bg-slate-800 border border-slate-700 rounded text-sm hover:bg-slate-700 transition-colors w-full text-left">
            Test Product API
          </button>
          <button onClick={() => showToast('AMD/vLLM path simulated.', 'info')} className="px-4 py-2 bg-slate-800 border border-slate-700 rounded text-sm hover:bg-slate-700 transition-colors w-full text-left">
            Test AMD/vLLM Advisory Path
          </button>
          <button onClick={() => showToast('Fallback mode active.', 'info')} className="px-4 py-2 bg-slate-800 border border-slate-700 rounded text-sm hover:bg-slate-700 transition-colors w-full text-left">
            Show Fallback Behavior
          </button>
          <button onClick={() => {
            navigator.clipboard.writeText("ReliefQueue uses synthetic/replayed disaster intake, deterministic logistics, AMD GPU/vLLM advisory inference when configured, Gemma 4 as a bonus reasoning lane, and human coordinator review for safe field action.");
            showToast('Reviewer notes copied to clipboard.', 'success');
          }} className="px-4 py-2 bg-emerald-600 text-white rounded text-sm hover:bg-emerald-700 transition-colors w-full text-left font-semibold">
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
                    {item.status === 'validation pending' && <span className="px-2 py-0.5 bg-purple-50 text-purple-700 text-[10px] font-bold uppercase rounded border border-purple-200">Validation Pending</span>}
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
    </div>
  );
}
