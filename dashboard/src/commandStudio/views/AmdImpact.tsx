import { useState } from 'react';
import { useApp } from '../context/AppContext';
import { Cpu, Zap, Activity, ShieldAlert, Bot, Server, LayoutDashboard, Printer } from 'lucide-react';
import { config } from '../lib/publicConfig';
import { AIAdvisoryDrawer } from '../components/AIAdvisoryDrawer';

export function AmdImpact() {
  const { addLog, showToast } = useApp();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const simulateAction = (action: string) => {
    addLog(`Simulated: ${action}`, 'Config Update', 'Action Recorded');
    showToast(`Simulation active: ${action}`, 'info');
  };

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto h-full overflow-y-auto">
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight flex items-center gap-3">
            AMD GPU / vLLM Impact
          </h2>
          <p className="text-slate-500 mt-2">Visibility into hardware acceleration, model endpoints, and Gemma 4 bonus validation.</p>
        </div>
        <button onClick={() => window.print()} aria-label="Print AMD and vLLM impact summary" className="no-print inline-flex items-center gap-2 rounded bg-white border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
          <Printer className="w-4 h-4" /> Print AMD Summary
        </button>
      </div>

      <section data-print-surface="amd-vllm-impact-summary" className="print-only mb-6 rounded-lg border border-slate-300 bg-white p-4">
        <h1 className="text-xl font-bold">ReliefQueue AMD/vLLM Impact Summary</h1>
        <p className="mt-1 text-sm">Printed at: {new Date().toLocaleString()} | Source: synthetic replay | Status: {config.featureAmdImpact ? 'Live AMD/vLLM mode configured' : 'Deterministic fallback visible'}</p>
        <p className="mt-1 text-sm">Safety boundary: advisory output only; coordinator review is required before any field instruction or assignment.</p>
      </section>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8" data-print-surface="amd-vllm-operational-metrics">
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="flex justify-between items-start mb-4">
            <h3 className="font-bold text-slate-700 text-sm uppercase tracking-wider">Inference Mode</h3>
            <Server className={`w-5 h-5 ${config.featureAmdImpact ? 'text-green-500' : 'text-slate-400'}`} />
          </div>
          <p className="text-xl font-bold text-slate-900 mb-1">{config.featureAmdImpact ? 'Live AMD/vLLM' : 'Deterministic Fallback'}</p>
          <p className="text-xs text-slate-500 mt-1">Data Source: Synthetic replay</p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="flex justify-between items-start mb-4">
            <h3 className="font-bold text-slate-700 text-sm uppercase tracking-wider">AMD GPU</h3>
            <ShieldAlert className="w-5 h-5 text-amber-500" />
          </div>
          <p className="text-xl font-bold text-slate-900 mb-1">Pending Verification</p>
          <p className="text-xs text-slate-500 mt-1">vLLM endpoint: Redacted</p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="flex justify-between items-start mb-4">
            <h3 className="font-bold text-slate-700 text-sm uppercase tracking-wider">Data Safety</h3>
            <Cpu className="w-5 h-5 text-rq-primary" />
          </div>
          <p className="text-xs text-slate-700 font-medium">private_text_sent: <span className="text-slate-900">false</span></p>
          <p className="text-xs text-slate-700 font-medium mt-1">secret_values_exposed: <span className="text-slate-900">false</span></p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm bg-slate-900 text-white">
          <div className="flex justify-between items-start mb-4">
            <h3 className="font-bold text-slate-300 text-sm uppercase tracking-wider">Human Review</h3>
            <ShieldAlert className="w-5 h-5 text-emerald-400" />
          </div>
          <p className="text-xl font-bold text-white mb-1">Required</p>
          <p className="text-xs text-slate-400 mt-1">No autonomous field-dispatch authority</p>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden mb-8">
        <div className="p-5 border-b border-slate-200 bg-slate-50 flex justify-between items-center">
          <h3 className="font-bold text-slate-900 flex items-center gap-2">
            <LayoutDashboard className="w-5 h-5 text-rq-primary" /> Batch Impact (Sample Benchmark)
          </h3>
        </div>
        <div className="p-5 grid grid-cols-2 md:grid-cols-4 gap-6">
          <div>
            <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Cases Processed</div>
            <div className="text-2xl font-bold text-slate-900">142</div>
            <div className="text-xs text-slate-400">Synthetic inputs</div>
          </div>
          <div>
            <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Fallback Count</div>
            <div className="text-2xl font-bold text-slate-900">0</div>
          </div>
          <div>
            <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Avg Latency</div>
            <div className="text-2xl font-bold text-slate-900">320ms</div>
            <div className="text-xs text-slate-400">p95: 410ms</div>
          </div>
          <div>
            <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Unsafe Rejected</div>
            <div className="text-2xl font-bold text-slate-900">2</div>
            <div className="text-xs text-slate-400">Schema validation fail</div>
          </div>
        </div>
        <div className="px-5 py-3 bg-blue-50 border-t border-blue-100 text-sm text-blue-800 flex items-center justify-center">
          Sample values until live AMD run is connected. Unapproved dispatches: 0.
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col">
          <div className="p-5 border-b border-slate-200 bg-slate-50 flex justify-between items-center">
            <h3 className="font-bold text-slate-900 flex items-center gap-2">
              <Activity className="w-5 h-5 text-rq-primary" /> Baseline vs AMD/vLLM
            </h3>
          </div>
          <div className="p-5 flex flex-col gap-6 flex-1">
            <div className="border border-slate-200 rounded-lg p-4">
              <h4 className="font-bold text-slate-700 mb-3 text-sm">Deterministic Baseline</h4>
              <div className="space-y-2 text-xs text-slate-600">
                <p><strong>Status:</strong> Fallback retained</p>
                <p><strong>Safe Summary:</strong> Raw message displayed.</p>
                <p><strong>Missing Info:</strong> None generated.</p>
                <p><strong>Review:</strong> Manual sort required.</p>
              </div>
            </div>
            <div className="border border-rq-primary/30 bg-blue-50/20 rounded-lg p-4 relative flex-1">
              <div className="absolute top-4 right-4"><Zap className="w-4 h-4 text-rq-primary" /></div>
              <h4 className="font-bold text-rq-primary mb-3 text-sm">Live AMD/vLLM Advisory</h4>
              <div className="space-y-2 text-xs text-slate-800">
                <p><strong>Safe Summary:</strong> Structured safe summary generated.</p>
                <p><strong>Missing Info:</strong> Targeted questions prepared.</p>
                <p><strong>Operator Note:</strong> Draft response ready.</p>
                <p><strong>Redaction Check:</strong> Passed.</p>
                <p><strong>Latency:</strong> ~320ms</p>
                <p className="mt-3 inline-block bg-amber-100 text-amber-800 px-2 py-1 rounded font-bold">Human Review Required</p>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden ring-1 ring-purple-500/20 shadow-purple-500/10">
          <div className="p-5 border-b border-slate-200 bg-purple-50/50 flex justify-between items-center">
            <h3 className="font-bold text-purple-900 flex items-center gap-2">
              <Bot className="w-5 h-5 text-purple-600" /> Gemma 4 Bonus Lane
            </h3>
            <span className="bg-purple-100 text-purple-700 text-[10px] font-bold px-2 py-1 rounded uppercase tracking-wider border border-purple-200">Validation Pending</span>
          </div>
          <div className="p-5 flex flex-col flex-1">
            <p className="text-sm text-slate-600 mb-4">
              Gemma 4 lane prepared; live validation pending on AMD/vLLM endpoint.
            </p>
            <div className="space-y-3 mb-6">
              <div className="flex items-center gap-2 text-sm text-slate-700">
                <div className="w-1.5 h-1.5 rounded-full bg-slate-300"></div>
                <strong>Task:</strong> Structured triage and reasoning
              </div>
              <div className="flex items-center gap-2 text-sm text-slate-700">
                <div className="w-1.5 h-1.5 rounded-full bg-slate-300"></div>
                <strong>Endpoint:</strong> vLLM/OpenAI-compatible through backend
              </div>
              <div className="flex items-center gap-2 text-sm text-slate-700">
                <div className="w-1.5 h-1.5 rounded-full bg-slate-300"></div>
                <strong>Output:</strong> Strict advisory JSON
              </div>
            </div>

            <div className="mt-auto space-y-2">
              <button onClick={() => simulateAction('Test Gemma 4 Triage')} className="w-full py-2 bg-purple-600 hover:bg-purple-700 text-white rounded text-sm font-semibold transition-colors">Test Gemma 4 Triage</button>
              <button onClick={() => simulateAction('Compare Gemma 4 vs Baseline')} className="w-full py-2 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 rounded text-sm font-semibold transition-colors">Compare Gemma 4 vs Baseline</button>
              <button onClick={() => simulateAction('Send Result to Quality Review')} className="w-full py-2 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 rounded text-sm font-semibold transition-colors">Send Result to Quality Review</button>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 mb-8">
        <h3 className="font-bold text-slate-900 mb-2">Simulation & Safety Controls</h3>
        <p className="text-sm text-slate-500 mb-4">ReliefQueue works without AI. AMD GPU/vLLM improves advisory enrichment and burst throughput when configured. Human review remains required.</p>
        <div className="flex flex-wrap gap-3">
          <button onClick={() => setDrawerOpen(true)} className="px-4 py-2 bg-slate-900 text-white rounded font-medium text-sm hover:bg-slate-800">Run Live AMD Advisory</button>
          <button onClick={() => simulateAction('Run Deterministic Baseline')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded font-medium text-sm hover:bg-slate-50">Run Deterministic Baseline</button>
          <button onClick={() => simulateAction('Compare Results')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded font-medium text-sm hover:bg-slate-50">Compare Results</button>
          <button onClick={() => simulateAction('Simulate Provider Timeout')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded font-medium text-sm hover:bg-slate-50">Simulate Provider Timeout</button>
          <button onClick={() => simulateAction('Simulate Malformed Output')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded font-medium text-sm hover:bg-slate-50">Simulate Malformed Output</button>
          <button onClick={() => simulateAction('Simulate Unsafe Phrase')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded font-medium text-sm hover:bg-slate-50">Simulate Unsafe Phrase</button>
          <button onClick={() => simulateAction('Restore Live Mode')} className="px-4 py-2 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded font-medium text-sm hover:bg-emerald-100">Restore Live Mode</button>
          <button onClick={() => simulateAction('Open Reviewer Evidence')} className="px-4 py-2 bg-blue-50 border border-blue-200 text-blue-800 rounded font-medium text-sm hover:bg-blue-100">Open Reviewer Evidence</button>
        </div>
      </div>

      <AIAdvisoryDrawer isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} caseId="DEMO-AMD-1" />
    </div>
  );
}
