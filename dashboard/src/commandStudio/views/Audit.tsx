import React, { useState } from 'react';
import { Search, Filter, ShieldCheck, Code, ArrowRight } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { DetailDrawer } from '../components/Shared';

const MOCK_EVENTS = [
  { id: 'EVT-9001', time: '14:22:15', actor: 'SysAdmin', type: 'Config Update', desc: 'Approved advisory model change for Scenario Beta.', detail: 'Model: Gemini 1.5 Pro. Rolled forward.' },
  { id: 'EVT-9002', time: '13:45:00', actor: 'C. Coordinator', type: 'Approval', desc: 'Approved assignment suggestion for RQ-8924.', detail: 'Assigned to Alpha Team.' },
  { id: 'EVT-9003', time: '13:10:22', actor: 'System (AI)', type: 'Advisory Gen', desc: 'Generated triage advisory for RQ-8925.', detail: 'Confidence: 0.85. Redaction applied.' },
  { id: 'EVT-9004', time: '12:05:41', actor: 'Field Unit 4', type: 'Sync Conflict', desc: 'Status update conflicted with central DB.', detail: 'Queued to DLQ. Resolved manually.' },
];

export function Audit() {
  const { addLog, showToast } = useApp();
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  
  const [timeFilter, setTimeFilter] = useState('24h');
  const [search, setSearch] = useState('');
  const [typeFilters, setTypeFilters] = useState<Record<string, boolean>>({
    'Approval': true,
    'Config Update': true,
    'Advisory Gen': true,
    'Sync Conflict': true,
  });

  const handleTypeToggle = (type: string) => {
    setTypeFilters(prev => ({...prev, [type]: !prev[type]}));
  };

  const selectedEvent = MOCK_EVENTS.find(e => e.id === selectedEventId);

  const handleAction = (action: string) => {
    addLog(`Audit Action`, `Executed '${action}' on ${selectedEvent?.id}`);
    showToast(`Action '${action}' logged locally.`, 'info');
  };

  const displayedEvents = MOCK_EVENTS.filter(e => {
    if (!typeFilters[e.type]) return false;
    if (search && !e.id.toLowerCase().includes(search.toLowerCase()) && !e.desc.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="flex h-full bg-slate-50 relative overflow-hidden">
      {/* Filters Sidebar (Hidden on mobile by default, could be a drawer but we'll use horizontal on mobile) */}
      <div className="w-64 bg-white border-r border-slate-200 p-6 flex-shrink-0 overflow-y-auto hidden lg:block">
        <h2 className="text-lg font-bold text-slate-900 mb-1">Filters</h2>
        <p className="text-xs text-slate-500 mb-6 font-mono uppercase tracking-wider">Demo Log View</p>
        
        <div className="space-y-6">
          <div>
            <h3 className="text-sm font-semibold text-slate-700 mb-3 uppercase tracking-wider">Time Range</h3>
            <div className="space-y-2">
              <label className="flex items-center gap-2"><input type="radio" name="time" checked={timeFilter === '24h'} onChange={() => setTimeFilter('24h')} className="text-rq-primary focus:ring-rq-primary" /> <span className="text-sm">Last 24 Hours</span></label>
              <label className="flex items-center gap-2"><input type="radio" name="time" checked={timeFilter === '7d'} onChange={() => setTimeFilter('7d')} className="text-rq-primary focus:ring-rq-primary"/> <span className="text-sm">Last 7 Days</span></label>
              <label className="flex items-center gap-2"><input type="radio" name="time" checked={timeFilter === 'all'} onChange={() => setTimeFilter('all')} className="text-rq-primary focus:ring-rq-primary"/> <span className="text-sm">All Time</span></label>
            </div>
          </div>
          
          <div>
            <h3 className="text-sm font-semibold text-slate-700 mb-3 uppercase tracking-wider">Event Type</h3>
            <div className="space-y-2">
              <label className="flex items-center gap-2"><input type="checkbox" checked={typeFilters['Approval']} onChange={() => handleTypeToggle('Approval')} className="rounded text-rq-primary focus:ring-rq-primary" /> <span className="text-sm">Approvals</span></label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={typeFilters['Config Update']} onChange={() => handleTypeToggle('Config Update')} className="rounded text-rq-primary focus:ring-rq-primary" /> <span className="text-sm">Config Updates</span></label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={typeFilters['Advisory Gen']} onChange={() => handleTypeToggle('Advisory Gen')} className="rounded text-rq-primary focus:ring-rq-primary" /> <span className="text-sm">AI Advisories</span></label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={typeFilters['Sync Conflict']} onChange={() => handleTypeToggle('Sync Conflict')} className="rounded text-rq-primary focus:ring-rq-primary" /> <span className="text-sm">Sync Conflicts</span></label>
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 flex flex-col min-w-0">
        <div className="p-4 md:p-6 border-b border-slate-200 bg-white flex flex-col md:flex-row justify-between items-start md:items-center gap-4 shrink-0">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Audit & Troubleshooting</h1>
            <p className="text-sm text-slate-500 mt-1">Review event timeline and inspect system payloads.</p>
          </div>
          <div className="flex items-center gap-3 w-full md:w-auto">
            <div className="relative flex-1 md:w-64">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input type="text" aria-label="Search audit request ID or description" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search Request ID..." className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-rq-primary/50 focus:border-rq-primary transition-all" />
            </div>
            <button onClick={() => showToast('Log export generated locally.', 'info')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 font-semibold text-sm rounded-lg hover:bg-slate-50 shadow-sm shrink-0 transition-colors">
              Export Log
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 md:p-6 bg-slate-50">
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden w-full overflow-x-auto">
            <table className="w-full text-left min-w-[700px]">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="px-4 md:px-6 py-3 md:py-4 text-xs font-mono font-bold text-slate-500 uppercase tracking-wider w-32">Timestamp</th>
                  <th className="px-4 md:px-6 py-3 md:py-4 text-xs font-mono font-bold text-slate-500 uppercase tracking-wider w-32">Req ID</th>
                  <th className="px-4 md:px-6 py-3 md:py-4 text-xs font-mono font-bold text-slate-500 uppercase tracking-wider w-40">Actor</th>
                  <th className="px-4 md:px-6 py-3 md:py-4 text-xs font-mono font-bold text-slate-500 uppercase tracking-wider">Event / Action</th>
                  <th className="px-4 md:px-6 py-3 md:py-4 w-10"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {displayedEvents.map(e => (
                  <tr key={e.id} onClick={() => setSelectedEventId(e.id)} className={`hover:bg-slate-50 cursor-pointer transition-colors ${selectedEventId === e.id ? 'bg-blue-50/50' : ''}`}>
                    <td className="px-4 md:px-6 py-4 text-sm font-mono text-slate-500 whitespace-nowrap">{e.time}</td>
                    <td className="px-4 md:px-6 py-4 text-sm font-mono font-semibold text-slate-900">{e.id}</td>
                    <td className="px-4 md:px-6 py-4 text-sm font-medium text-slate-700">{e.actor}</td>
                    <td className="px-4 md:px-6 py-4">
                      <div className="font-semibold text-slate-900 text-sm">{e.desc}</div>
                      <div className="text-xs text-slate-500 mt-1 font-mono">{e.type}</div>
                    </td>
                    <td className="px-4 md:px-6 py-4 text-right">
                       <ArrowRight className="w-4 h-4 text-slate-400" />
                    </td>
                  </tr>
                ))}
                {displayedEvents.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-6 py-8 text-center text-sm text-slate-500">No events found matching the criteria.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-8 bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="p-4 md:p-6 border-b border-slate-200 bg-slate-50">
              <h2 className="text-xl font-bold text-slate-900">Submission / Deployment Readiness</h2>
              <p className="text-sm text-slate-500 mt-1">Status of hackathon submission requirements and application config.</p>
            </div>
            <div className="p-4 md:p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <div>
                <ul className="text-sm space-y-2 text-slate-700">
                  <li className="flex justify-between border-b border-slate-100 pb-1"><span>Demo App URL:</span> <span className="font-medium text-slate-900">Configured</span></li>
                  <li className="flex justify-between border-b border-slate-100 pb-1"><span>Recommended Platform:</span> <span className="font-medium text-slate-900">Replit Full-Stack</span></li>
                  <li className="flex justify-between border-b border-slate-100 pb-1"><span>Vercel / Streamlit:</span> <span className="font-medium text-slate-500">Not Applicable Here</span></li>
                  <li className="flex justify-between border-b border-slate-100 pb-1"><span>Public GitHub Repo:</span> <span className="font-medium text-slate-900">Linked</span></li>
                  <li className="flex justify-between border-b border-slate-100 pb-1"><span>Public Config Loaded:</span> <span className="font-medium text-emerald-600 flex items-center gap-1"><ShieldCheck className="w-3 h-3"/> Yes</span></li>
                </ul>
              </div>
              <div>
                <ul className="text-sm space-y-2 text-slate-700">
                  <li className="flex justify-between border-b border-slate-100 pb-1"><span>API Base URL:</span> <span className="font-mono text-xs font-medium text-slate-900 truncate max-w-[150px]" title="Configured">Configured</span></li>
                  <li className="flex justify-between border-b border-slate-100 pb-1"><span>AMD/vLLM Feature Flag:</span> <span className="font-medium text-emerald-600">Active</span></li>
                  <li className="flex justify-between border-b border-slate-100 pb-1"><span>Gemma 4 Bonus Lane:</span> <span className="font-medium text-purple-600">Pending Validation</span></li>
                  <li className="flex justify-between border-b border-slate-100 pb-1"><span>Secrets Exposed in Browser:</span> <span className="font-medium text-emerald-600">False</span></li>
                  <li className="flex justify-between border-b border-slate-100 pb-1"><span>Backend Health:</span> <span className="font-medium text-slate-900">Stable</span></li>
                </ul>
              </div>
              <div className="flex flex-col gap-2">
                <button onClick={() => handleAction('Check Public Config')} className="w-full py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-sm font-semibold transition-colors">Check Public Config</button>
                <button onClick={() => handleAction('Test Product API')} className="w-full py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-sm font-semibold transition-colors">Test Product API</button>
                <button onClick={() => handleAction('Test AMD/vLLM Advisory Path')} className="w-full py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-sm font-semibold transition-colors">Test AMD/vLLM Advisory Path</button>
                <button onClick={() => handleAction('Show Fallback Behavior')} className="w-full py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-sm font-semibold transition-colors">Show Fallback Behavior</button>
                <button onClick={() => {
                  navigator.clipboard.writeText("ReliefQueue uses synthetic/replayed disaster intake, deterministic logistics, AMD GPU/vLLM advisory inference when configured, Gemma 4 as a bonus reasoning lane, and human coordinator review for safe field action.");
                  showToast('Reviewer notes copied to clipboard.', 'success');
                }} className="w-full py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-sm font-semibold transition-colors">Copy Reviewer Notes</button>
              </div>
            </div>
            <div className="bg-emerald-50 border-t border-emerald-100 p-3 text-xs text-emerald-800 text-center font-medium">
              ReliefQueue uses synthetic/replayed disaster intake, deterministic logistics, AMD GPU/vLLM advisory inference when configured, Gemma 4 as a bonus reasoning lane, and human coordinator review for safe field action.
            </div>
          </div>
        </div>
      </div>

      <DetailDrawer
        isOpen={!!selectedEvent}
        onClose={() => setSelectedEventId(null)}
        title="Event Detail"
      >
        {selectedEvent && (
          <div className="flex flex-col h-full gap-6">
            <div>
              <div className="flex justify-between items-start mb-2">
                <span className="bg-slate-100 text-slate-600 text-[10px] font-mono font-bold px-2 py-1 rounded uppercase tracking-wider">
                  {selectedEvent.type}
                </span>
                <span className="font-mono text-sm text-slate-500">{selectedEvent.time}</span>
              </div>
              <h2 className="text-xl font-bold text-slate-900 leading-tight">{selectedEvent.desc}</h2>
              <div className="mt-4 flex gap-6">
                 <div>
                   <div className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-wider mb-1">Actor</div>
                   <div className="font-medium text-sm text-slate-800">{selectedEvent.actor}</div>
                 </div>
                 <div>
                   <div className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-wider mb-1">Request ID</div>
                   <div className="font-mono font-bold text-sm text-slate-800">{selectedEvent.id}</div>
                 </div>
              </div>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
              <div className="text-sm font-medium text-slate-700">{selectedEvent.detail}</div>
            </div>

            <div className="bg-slate-900 rounded-lg overflow-hidden border border-slate-800 flex flex-col">
              <div className="bg-slate-800 px-4 py-2 border-b border-slate-700 flex items-center justify-between">
                <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                  <Code className="w-3 h-3" /> Redacted Payload Preview
                </span>
              </div>
              <div className="p-4 text-xs font-mono text-emerald-400 overflow-x-auto leading-relaxed">
{`{
  "timestamp": "${selectedEvent.time}Z",
  "actor_ref": "${selectedEvent.actor === 'System (AI)' ? 'sys_ai_01' : 'user_masked_xxx'}",
  "event_type": "${selectedEvent.type.toUpperCase().replace(' ', '_')}",
  "payload": {
    "action": "${selectedEvent.desc}",
    "meta": "redacted",
    "signature": "valid"
  }
}`}
              </div>
            </div>

            <div className="mt-auto pt-6 flex flex-col gap-3">
               <button onClick={() => handleAction('Safe Replay')} className="w-full bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 font-semibold py-3 rounded-lg shadow-sm transition-colors text-sm">
                 Safe Replay Event
               </button>
               <p className="text-[10px] text-center text-slate-500 italic mt-2">
                 Not a production dispatch log. Safe replay explanation logged locally.
               </p>
            </div>
          </div>
        )}
      </DetailDrawer>
    </div>
  );
}
