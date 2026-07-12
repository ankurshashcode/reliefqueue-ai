import React, { useState } from 'react';
import { Activity, FolderOpen, AlertTriangle, Truck, UserCheck, ShieldAlert, Bot, CheckCircle, PlayCircle } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { JudgeWalkthroughModal } from '../components/JudgeWalkthroughModal';
import { actionKey, postProduct } from '../lib/productActions';

export function Overview() {
  const { navigate, addLog } = useApp();
  const [viewMode, setViewMode] = useState<'raw' | 'enriched'>('enriched');
  const [demoWalkthroughOpen, setDemoWalkthroughOpen] = useState(false);
  const [drillResult, setDrillResult] = useState('No deterministic drill has been run in this browser session.');

  const handleMetricClick = (view: any, logMsg: string) => {
    addLog(`View Navigated`, `User navigated to ${logMsg} from Overview metric.`);
    navigate(view);
  };

  const handleAuditClick = () => {
    addLog(`Audit Detail Viewed`, `User opened recent audit events list.`);
    navigate('audit');
  };

  const runDeterministicDrill = async () => {
    const result = await postProduct('/api/product/command/drill', {
      idempotency_key: actionKey('command-drill')
    }, { status: 'recorded', result: { name: 'local command drill', deterministic: true, case_count: 3 } });
    const summary = `${result.result?.name || 'Deterministic drill'} recorded for ${result.result?.case_count ?? 0} cases; coordinator review remains required.`;
    setDrillResult(summary);
    addLog('Deterministic Drill Recorded', summary);
  };

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto h-full overflow-y-auto">
      <JudgeWalkthroughModal isOpen={demoWalkthroughOpen} onClose={() => setDemoWalkthroughOpen(false)} />
      <div className="mb-6 flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900">Operations Overview</h1>
          <p className="text-slate-500 mt-2 text-sm md:text-base">Real-time command center metrics and synthetic system status.</p>
        </div>
        
        <div className="flex flex-col sm:flex-row gap-3">
          <button 
            onClick={() => setDemoWalkthroughOpen(true)}
            className="px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-semibold hover:bg-slate-800 transition-colors flex items-center gap-2 shadow-sm"
          >
            <PlayCircle className="w-4 h-4" /> Judge Demo Walkthrough
          </button>
          <button
            data-action-id="command.run_deterministic_drill"
            onClick={runDeterministicDrill}
            className="px-4 py-2 bg-white text-slate-800 border border-slate-300 rounded-lg text-sm font-semibold hover:bg-slate-50 transition-colors shadow-sm"
          >
            Run Deterministic Drill
          </button>
          
          <div className="flex bg-slate-100 p-1 rounded-lg border border-slate-200">
            <button 
              onClick={() => setViewMode('raw')}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${viewMode === 'raw' ? 'bg-white text-slate-900 shadow-sm border border-slate-200' : 'text-slate-500 hover:text-slate-700'}`}
            >
              Raw Intake
            </button>
            <button 
              onClick={() => setViewMode('enriched')}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors flex items-center gap-2 ${viewMode === 'enriched' ? 'bg-white text-rq-primary shadow-sm border border-slate-200' : 'text-slate-500 hover:text-slate-700'}`}
            >
              <Bot className="w-4 h-4" /> AI-Enriched Queue
            </button>
          </div>
        </div>
      </div>

      <div data-result-id="command.drill" className="bg-slate-900 text-slate-100 rounded-lg p-4 mb-4 text-sm" aria-live="polite">
        <strong className="block text-xs uppercase tracking-wider text-cyan-300 mb-1">Deterministic drill history</strong>
        {drillResult}
      </div>

      <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 mb-6 shadow-sm flex gap-3 items-start">
        <CheckCircle className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
        <div className="text-sm text-emerald-800 font-medium">
          <strong className="font-bold uppercase tracking-wider text-xs block mb-1">Architecture Summary</strong>
          ReliefQueue uses synthetic/replayed disaster intake, deterministic logistics, AMD GPU/vLLM advisory inference when configured, Gemma 4 as a bonus reasoning lane, and human coordinator review for safe field action.
        </div>
      </div>

      {viewMode === 'enriched' && (
        <div className="mb-6 md:mb-8 bg-blue-50 border border-blue-100 rounded-xl p-5 shadow-sm">
          <h3 className="font-bold text-blue-900 flex items-center gap-2 mb-4">
            <Bot className="w-5 h-5" /> AI Heavy Lifting Summary
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white p-3 rounded-lg border border-blue-100 cursor-pointer hover:shadow-sm transition-shadow" onClick={() => handleMetricClick('intake', 'AI Intake')}>
              <div className="text-2xl font-bold text-slate-900">7</div>
              <div className="text-xs text-slate-500">Raw Messages Normalized</div>
            </div>
            <div className="bg-white p-3 rounded-lg border border-blue-100 cursor-pointer hover:shadow-sm transition-shadow" onClick={() => handleMetricClick('links', 'Incident Links')}>
              <div className="text-2xl font-bold text-slate-900">3</div>
              <div className="text-xs text-slate-500">Possible Incident Clusters</div>
            </div>
            <div className="bg-white p-3 rounded-lg border border-blue-100 cursor-pointer hover:shadow-sm transition-shadow" onClick={() => handleMetricClick('assignments', 'AI Advisories')}>
              <div className="text-2xl font-bold text-slate-900">6</div>
              <div className="text-xs text-slate-500">AI Advisory Objects Drafted</div>
            </div>
            <div className="bg-white p-3 rounded-lg border border-blue-100 cursor-pointer hover:shadow-sm transition-shadow" onClick={() => handleMetricClick('assignments', 'Assignments')}>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold text-slate-900">2</span>
                <span className="px-1.5 py-0.5 bg-amber-100 text-amber-800 text-[10px] rounded font-bold uppercase tracking-wider">Review Req</span>
              </div>
              <div className="text-xs text-slate-500 mt-1">Assignment Suggestions Pending Review</div>
            </div>
            <div className="bg-white p-3 rounded-lg border border-blue-100 col-span-2 md:col-span-1 cursor-pointer hover:shadow-sm transition-shadow" data-testid="overview-missing-info-card" role="button" tabIndex={0} onClick={() => handleMetricClick('intake', 'Missing-info prompts')} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); handleMetricClick('intake', 'Missing-info prompts'); } }}>
              <div className="text-xl font-bold text-slate-900">4 <span className="text-sm font-normal text-slate-500 ml-1">prompts</span></div>
              <div className="text-xs text-slate-500">Missing-info prompts prepared</div>
            </div>
            <div className="bg-white p-3 rounded-lg border border-blue-100 col-span-2 md:col-span-1 cursor-pointer hover:shadow-sm transition-shadow" data-testid="overview-malformed-output-card" role="button" tabIndex={0} onClick={() => handleMetricClick('quality', 'Malformed output review')} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); handleMetricClick('quality', 'Malformed output review'); } }}>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xl font-bold text-slate-900">1 <span className="text-sm font-normal text-slate-500 ml-1">rejected</span></div>
                  <div className="text-xs text-slate-500">Malformed output rejected</div>
                </div>
                <ShieldAlert className="w-5 h-5 text-amber-500" />
              </div>
            </div>
            <div className="bg-white p-3 rounded-lg border border-emerald-200 bg-emerald-50 col-span-2 md:col-span-2 flex items-center justify-between">
              <div>
                <div className="text-xl font-bold text-emerald-900">0</div>
                <div className="text-xs text-emerald-700 font-medium">Unapproved Dispatches (Safety boundary intact)</div>
              </div>
              <CheckCircle className="w-6 h-6 text-emerald-500" />
            </div>
          </div>
        </div>
      )}

      {viewMode === 'raw' && (
        <div className="mb-6 md:mb-8 bg-slate-100 border border-slate-200 rounded-xl p-5 shadow-inner">
          <h3 className="font-bold text-slate-700 flex items-center gap-2 mb-4">
            <Activity className="w-5 h-5" /> Raw Multi-Source Intake Queue
          </h3>
          <p className="text-sm text-slate-500 mb-4">Viewing messy, un-normalized reports from SMS, WhatsApp, and Voice endpoints.</p>
          <button onClick={() => setViewMode('enriched')} className="text-sm font-medium text-rq-primary hover:underline flex items-center gap-1">
             Switch to AI-Enriched Queue <Activity className="w-4 h-4" />
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-6 md:mb-8">
        <MetricCard 
          title="Operational Pulse" value="Active" subtitle="Normal operating conditions" 
          icon={Activity} color="emerald" onClick={() => handleMetricClick('map', 'Live Map')} 
        />
        <MetricCard 
          title="Active Cases" value="1,248" subtitle="Replayed demo data" 
          icon={FolderOpen} color="blue" onClick={() => handleMetricClick('assignments', 'Assignments')} 
        />
        <MetricCard 
          title="Critical Cases" value="42" subtitle="Requires immediate review" 
          icon={AlertTriangle} color="red" onClick={() => handleMetricClick('assignments', 'Assignments (Critical)')} 
        />
        <MetricCard 
          title="Field Units" value="156" subtitle="Simulated deployments" 
          icon={Truck} color="amber" onClick={() => handleMetricClick('sync', 'Field Sync')} 
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm p-4 md:p-6 flex flex-col">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-lg font-semibold">Queue Pressure (Simulated)</h3>
            <button onClick={() => navigate('assignments')} className="text-sm font-medium text-rq-primary hover:underline">View All</button>
          </div>
          <div className="flex-1 bg-slate-50 rounded-lg border border-slate-100 flex items-end justify-around p-4 min-h-[250px] md:min-h-[300px]">
             {/* Mock Chart - Clickable bars */}
             <ChartBar label="Open Zone Alpha assignment pressure" height="h-1/3" color="bg-blue-200" onClick={() => handleMetricClick('assignments', 'Zone Alpha')} />
             <ChartBar label="Open Zone Beta assignment pressure" height="h-1/2" color="bg-blue-300" onClick={() => handleMetricClick('assignments', 'Zone Beta')} />
             <ChartBar label="Open Zone Charlie amber pressure" height="h-3/4" color="bg-amber-400" onClick={() => handleMetricClick('assignments', 'Zone Charlie (Amber)')} />
             <ChartBar label="Open Zone Delta assignment pressure" height="h-2/3" color="bg-blue-400" onClick={() => handleMetricClick('assignments', 'Zone Delta')} />
             <div 
               onClick={() => handleMetricClick('assignments', 'Zone Echo (Critical)')}
               role="button"
               tabIndex={0}
               aria-label="Open Zone Echo critical assignment pressure"
               onKeyDown={(event) => {
                 if (event.key === 'Enter' || event.key === ' ') {
                   event.preventDefault();
                   handleMetricClick('assignments', 'Zone Echo (Critical)');
                 }
               }}
               className="w-8 sm:w-12 md:w-16 bg-red-500 h-full rounded-t-sm relative cursor-pointer hover:opacity-80 transition-opacity"
             >
                <div className="absolute -top-8 left-1/2 -translate-x-1/2 text-[10px] sm:text-xs font-mono font-bold text-red-600 bg-red-100 px-1 sm:px-2 py-1 rounded">CRITICAL</div>
             </div>
             <ChartBar label="Open Zone Foxtrot assignment pressure" height="h-1/4" color="bg-blue-200" onClick={() => handleMetricClick('assignments', 'Zone Foxtrot')} />
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 md:p-6 flex flex-col">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold">Recent Audit Events</h3>
            <button onClick={handleAuditClick} className="text-sm font-medium text-rq-primary hover:underline">View Log</button>
          </div>
          <div className="space-y-4 md:space-y-6 flex-1 overflow-y-auto">
            <EventItem 
              title="Approve Advisory Model Change" 
              desc="Admin user updated advisory threshold levels for Zone B." 
              time="10:42 AM" 
              icon={ShieldAlert}
              onClick={handleAuditClick}
            />
            <EventItem 
              title="Connection Drop Detected" 
              desc="Synthetic hub 4 experienced offline state." 
              time="09:15 AM" 
              icon={AlertTriangle}
              isAlert
              onClick={handleAuditClick}
            />
            <EventItem 
              title="Queue Rebalance Review" 
              desc="J. Doe initiated rebalance review for Sector 7." 
              time="08:30 AM" 
              icon={UserCheck}
              onClick={handleAuditClick}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ title, value, subtitle, icon: Icon, color, onClick }: any) {
  const colorClasses = {
    emerald: 'text-rq-emerald bg-rq-emerald-light border-transparent hover:border-rq-emerald',
    blue: 'text-rq-primary bg-blue-100 border-transparent hover:border-rq-primary',
    red: 'text-rq-red bg-rq-red-light border-transparent hover:border-rq-red',
    amber: 'text-rq-amber bg-rq-amber-light border-transparent hover:border-rq-amber',
  }[color as string];

  return (
    <div
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label={`Open ${title}: ${value}`}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onClick();
        }
      }}
      className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm cursor-pointer hover:shadow-md transition-all group">
      <div className="flex justify-between items-start mb-4">
        <div className="text-[10px] md:text-xs font-mono text-slate-500 uppercase tracking-wider">{title}</div>
        <div className={`p-2 rounded-md border ${colorClasses} transition-colors`}>
          <Icon className="w-4 h-4 md:w-5 md:h-5" />
        </div>
      </div>
      <div className="text-2xl md:text-3xl font-bold text-slate-900 group-hover:text-rq-primary transition-colors">{value}</div>
      <div className="text-xs md:text-sm text-slate-500 mt-2">{subtitle}</div>
    </div>
  );
}

function ChartBar({ label, height, color, onClick }: any) {
  return (
    <div 
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label={label}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onClick();
        }
      }}
      className={`w-8 sm:w-12 md:w-16 ${color} ${height} rounded-t-sm cursor-pointer hover:opacity-80 transition-opacity`}
    ></div>
  );
}

function EventItem({ title, desc, time, icon: Icon, isAlert, onClick }: any) {
  return (
    <div
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label={`Open audit event ${title}`}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onClick();
        }
      }}
      className="flex gap-3 md:gap-4 p-2 -mx-2 rounded-lg hover:bg-slate-50 cursor-pointer transition-colors">
      <div className={`p-2 rounded-full h-fit flex-shrink-0 ${isAlert ? 'bg-red-100 text-red-600' : 'bg-slate-100 text-slate-600'}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div>
        <div className="text-sm font-semibold text-slate-900 leading-tight">{title}</div>
        <div className="text-xs md:text-sm text-slate-500 mt-1 line-clamp-2">{desc}</div>
        <div className="text-[10px] md:text-xs font-mono text-slate-400 mt-1">{time}</div>
      </div>
    </div>
  );
}
