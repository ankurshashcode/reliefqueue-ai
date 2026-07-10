import React, { useState } from 'react';
import { Filter, RefreshCw, User, CloudOff, AlertTriangle, ChevronRight, MessageSquare, ShieldAlert, Check } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { DetailDrawer } from '../components/Shared';
import { actionLog } from '../lib/actionLog';

const MOCK_UNITS = [
  { id: 'u1', name: 'Unit Alpha (J. Doe)', time: '2 mins ago', status: 'SYNCED', outbox: 0, pending: 0, active: true },
  { id: 'u2', name: 'Unit Bravo (S. Smith)', time: '15 mins ago', status: 'PENDING', outbox: 12, pending: 3, warning: true },
  { id: 'u3', name: 'Unit Charlie (M. Johnson)', time: '45 mins ago', status: 'HUMAN REVIEW REQUIRED', outbox: 5, pending: 2, error: true, conflict: 'Requires Quality Queue Review' },
  { id: 'u4', name: 'Unit Echo (T. Adams)', time: 'Offline • Last seen 2h ago', status: 'OFFLINE', outbox: '?', pending: 'Unknown', offline: true }
];

const MOCK_OUTBOX = [
  { id: 'MSG-912', type: 'SMS', to: '+123***89', status: 'Pending', idempotency: 'id-key-881' },
  { id: 'MSG-913', type: 'WhatsApp', to: 'whatsapp:+55***', status: 'DLQ', idempotency: 'id-key-882' },
];

export function FieldSync() {
  const { addLog, showToast } = useApp();
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null);

  const selectedUnit = MOCK_UNITS.find(u => u.id === selectedUnitId);

  const handleForceSync = () => {
    addLog('Force Sync All', 'Initiated manual field sync trigger.');
    showToast('Sync request queued locally for demo.', 'info');
  };

  const handleConflictResolve = (action: string) => {
    addLog(`Conflict Resolution`, `Action '${action}' chosen for ${selectedUnit?.name}`);
    showToast('Conflict status updated locally.', 'success');
    setSelectedUnitId(null);
  };
  
  const handleMessageAction = (action: string) => {
    showToast(`${action} applied.`, 'success');
    actionLog.add(`Messaging Action: ${action}`, 'API Call', 'Local Demo Fallback');
  };

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto h-full flex flex-col overflow-hidden">
      <div className="mb-6 flex flex-col sm:flex-row justify-between items-start sm:items-end gap-4 shrink-0">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900">Field Sync & Messaging</h1>
          <p className="text-slate-500 mt-1 md:mt-2 text-sm md:text-base">Field connectivity and local outbox monitoring.</p>
        </div>
        <div className="flex flex-wrap gap-2 md:gap-3 w-full sm:w-auto">
          <button onClick={() => showToast('Filter options opened (demo).', 'info')} className="flex-1 sm:flex-none px-4 py-2 bg-white border border-slate-300 rounded-lg font-medium text-sm text-slate-700 hover:bg-slate-50 transition-colors flex items-center justify-center gap-2 shadow-sm">
            <Filter className="w-4 h-4" /> Filter
          </button>
          <button onClick={handleForceSync} className="flex-1 sm:flex-none px-4 py-2 bg-rq-primary text-white rounded-lg font-medium text-sm hover:bg-rq-primary-hover transition-colors shadow-sm flex items-center justify-center gap-2">
            <RefreshCw className="w-4 h-4" /> Force Sync All
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col lg:flex-row gap-6">
        <div className="w-full lg:w-2/3 bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden h-full">
          <div className="p-4 border-b border-slate-200 bg-slate-50 flex justify-between items-center shrink-0">
            <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <User className="w-5 h-5 text-rq-primary" /> Active Units
            </h3>
            <div className="flex items-center gap-2">
               <span className="hidden sm:inline-flex items-center gap-1.5 px-2 py-1 bg-amber-50 border border-amber-200 rounded text-[10px] font-mono text-amber-700">
                 <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span> Demo Mode
               </span>
               <span className="font-mono text-xs font-bold bg-slate-200 text-slate-600 px-2 py-1 rounded uppercase">24 Active</span>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-50/50">
            {MOCK_UNITS.map(u => (
              <UnitRow key={u.id} unit={u} onClick={() => setSelectedUnitId(u.id)} />
            ))}
          </div>
        </div>

        <div className="w-full lg:w-1/3 bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden h-full">
          <div className="p-4 border-b border-slate-200 bg-slate-50 flex justify-between items-center shrink-0">
            <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <MessageSquare className="w-5 h-5 text-rq-primary" /> Outbox Safety
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3">
              <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <h4 className="font-semibold text-amber-900 text-sm">Idempotency Active</h4>
                <p className="text-sm text-amber-800 mt-1">Prevents duplicate sends to field providers (RapidPro, Twilio).</p>
              </div>
            </div>

            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Pending Messages</h4>
            <div className="space-y-3">
              {MOCK_OUTBOX.map(msg => (
                <div key={msg.id} className="border border-slate-200 rounded p-3">
                  <div className="flex justify-between items-start mb-1">
                    <span className="font-bold text-slate-900 text-sm">{msg.id}</span>
                    <span className={`px-2 py-0.5 text-[10px] font-bold rounded uppercase ${msg.status === 'DLQ' ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-600'}`}>{msg.status}</span>
                  </div>
                  <div className="text-xs text-slate-500 font-mono mb-2">To: {msg.to} ({msg.type})</div>
                  <div className="text-[10px] bg-slate-100 px-1.5 py-0.5 rounded text-slate-500 font-mono inline-block mb-3">Key: {msg.idempotency}</div>
                  {msg.status === 'DLQ' ? (
                    <button onClick={() => handleMessageAction('Replay DLQ')} className="w-full py-1.5 bg-white border border-slate-300 text-slate-700 text-xs font-medium rounded hover:bg-slate-50">
                      Replay DLQ for Review
                    </button>
                  ) : (
                    <button onClick={() => handleMessageAction('Queue Message')} className="w-full py-1.5 bg-rq-primary text-white text-xs font-medium rounded hover:bg-rq-primary-hover flex justify-center items-center gap-1">
                      <Check className="w-3 h-3" /> Process Queue
                    </button>
                  )}
                </div>
              ))}
            </div>
            
            <button onClick={() => handleMessageAction('Mark Needs Manual Review')} className="w-full mt-4 py-2 bg-white border border-slate-300 text-slate-700 text-sm font-medium rounded-lg hover:bg-slate-50">
              Mark All Needs Review
            </button>
          </div>
        </div>
      </div>

      <DetailDrawer
        isOpen={!!selectedUnit}
        onClose={() => setSelectedUnitId(null)}
        title="Sync Details"
      >
        {selectedUnit && (
          <div className="flex flex-col h-full gap-6">
             <div>
                <h3 className="text-2xl font-bold text-slate-900">{selectedUnit.name}</h3>
                <p className="text-sm text-slate-500 mt-1 flex items-center gap-2">
                  {selectedUnit.offline ? <CloudOff className="w-4 h-4"/> : <User className="w-4 h-4"/>} 
                  {selectedUnit.time}
                </p>
                <div className={`mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border font-mono text-[10px] font-bold uppercase tracking-wider
                  ${selectedUnit.error ? 'bg-red-100 text-red-700 border-red-200' : 
                    selectedUnit.warning ? 'bg-amber-100 text-amber-700 border-amber-200' : 
                    selectedUnit.offline ? 'bg-slate-200 text-slate-600 border-slate-300' : 
                    'bg-emerald-100 text-emerald-700 border-emerald-200'}`}
                >
                  {!selectedUnit.offline && <div className={`w-2 h-2 rounded-full ${selectedUnit.error ? 'bg-red-600' : selectedUnit.warning ? 'bg-amber-500 animate-pulse' : 'bg-emerald-600'}`}></div>}
                  {selectedUnit.status}
                </div>
             </div>
             
             {selectedUnit.error && (
               <div className="bg-red-50 border border-red-200 rounded-xl p-5">
                  <div className="flex gap-3">
                    <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
                    <div>
                      <h4 className="font-mono text-xs font-bold text-red-800 uppercase tracking-wider mb-2">Dead-Letter Queue (DLQ) Audit</h4>
                      <p className="text-sm text-red-900 mb-4 font-medium">1 item requires manual intervention to prevent data loss.</p>
                      <div className="bg-white rounded border border-red-200 p-3 text-xs font-mono text-slate-700 overflow-x-auto shadow-sm mb-4">
                        <div className="text-red-500 mb-1">// Conflict: optimistic lock failure on record ID 992</div>
                        {`{"action": "update_status", "id": "992", "status": "completed"}`}
                      </div>
                      <div className="flex flex-col sm:flex-row gap-3">
                        <button onClick={() => handleConflictResolve('Discard Field Update')} className="flex-1 bg-white border border-slate-300 text-slate-700 py-2.5 rounded-lg text-sm font-semibold hover:bg-slate-50 transition-colors">Discard Field Update</button>
                        <button onClick={() => handleConflictResolve('Force Field Update')} className="flex-1 bg-rq-red text-white py-2.5 rounded-lg text-sm font-semibold hover:bg-red-700 shadow-sm transition-colors">Force Field Update</button>
                      </div>
                    </div>
                  </div>
               </div>
             )}

             <div className="bg-slate-50 border border-slate-200 rounded-xl p-5">
                <h4 className="font-bold text-slate-900 mb-2">Assigned Tasks</h4>
                <div className="bg-white border border-slate-200 rounded-lg p-4 mb-3">
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-bold text-slate-900">Deliver Medical Supplies</span>
                    <span className="bg-amber-100 text-amber-800 text-[10px] font-mono font-bold px-2 py-1 rounded">PRIORITY: HIGH</span>
                  </div>
                  <div className="text-xs text-slate-500 font-mono mb-3 uppercase tracking-wider border-b border-slate-100 pb-2">Why this task appears</div>
                  <ul className="text-sm text-slate-700 space-y-2 list-disc pl-4 mb-4">
                    <li><span className="font-bold">Priority:</span> AI/rules suggested priority: HIGH</li>
                    <li><span className="font-bold">Coordinator Instruction:</span> Proceed with caution. Hand-deliver kit A2.</li>
                    <li><span className="font-bold">Need Type:</span> Medical Supply</li>
                    <li><span className="font-bold">Location Confidence:</span> High (GPS attached)</li>
                    <li><span className="font-bold">Missing Info for follow-up:</span> Exact number of adults requiring assistance unknown.</li>
                    <li><span className="font-bold">Contact:</span> Masked Relay Available (+1-***-***-8822) <button onClick={() => handleMessageAction('Open Masked Relay')} className="text-rq-primary hover:underline font-medium text-xs ml-2">Open Relay</button></li>
                    <li><span className="font-bold">Status:</span> Human-approved for field follow-up</li>
                  </ul>
                  <div className="text-xs font-mono text-slate-500 bg-slate-100 px-2 py-1 rounded inline-block mb-4">
                    Advisory Source: Live AMD/vLLM Inference
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => handleMessageAction('Add Field Note')} className="flex-1 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 py-2 rounded-lg text-xs font-semibold transition-colors">Add Note</button>
                    <button onClick={() => handleMessageAction('Report Status Update')} className="flex-1 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 py-2 rounded-lg text-xs font-semibold transition-colors">Update Status</button>
                    <button onClick={() => handleMessageAction('Request Clarification')} className="flex-1 bg-slate-800 hover:bg-slate-900 text-white py-2 rounded-lg text-xs font-semibold transition-colors">Ask Coord</button>
                  </div>
                  <button onClick={() => handleMessageAction('Queue Offline Update')} className="w-full mt-2 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 py-2 rounded-lg text-xs font-semibold transition-colors">Queue Offline Update</button>
                </div>
             </div>

             <div>
                <h4 className="font-mono text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 border-b border-slate-200 pb-2">Sync Telemetry</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-slate-50 p-4 rounded-lg border border-slate-200">
                    <p className="text-xs font-mono text-slate-500 uppercase tracking-wider mb-1">Last Contact</p>
                    <p className="font-bold text-slate-900 text-lg">{selectedUnit.time}</p>
                  </div>
                  <div className="bg-slate-50 p-4 rounded-lg border border-slate-200">
                    <p className="text-xs font-mono text-slate-500 uppercase tracking-wider mb-1">Signal Strength</p>
                    <p className={`font-bold text-lg ${selectedUnit.offline ? 'text-slate-500' : selectedUnit.warning ? 'text-amber-600' : 'text-emerald-600'}`}>
                      {selectedUnit.offline ? 'None' : selectedUnit.warning ? 'Weak' : 'Strong'}
                    </p>
                  </div>
                </div>
             </div>

             <div className="mt-auto pt-6 border-t border-slate-200">
               <button onClick={() => showToast('Export generated (demo)', 'info')} className="w-full bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 font-semibold py-3 rounded-lg transition-colors">
                 Export Telemetry Logs
               </button>
             </div>
          </div>
        )}
      </DetailDrawer>
    </div>
  );
}

function UnitRow({ unit, onClick }: any) {
  const { name, time, status, outbox, pending, warning, error, offline, conflict } = unit;
  
  const getBorderColor = () => {
    if (error) return 'border-l-rq-red border-y-red-200 border-r-red-200 bg-red-50/30 hover:bg-red-50/60';
    if (warning) return 'border-l-amber-500 border-y-amber-200 border-r-amber-200 bg-amber-50/20 hover:bg-amber-50/40';
    if (offline) return 'border-l-slate-400 border-y-slate-200 border-r-slate-200 bg-slate-50 hover:bg-slate-100 opacity-80';
    return 'border-l-emerald-500 border-y-slate-200 border-r-slate-200 bg-white hover:bg-slate-50';
  };

  const getIconColor = () => {
    if (error) return 'bg-red-100 text-red-600';
    if (warning) return 'bg-amber-100 text-amber-600';
    if (offline) return 'bg-slate-200 text-slate-500';
    return 'bg-slate-100 text-slate-600';
  };

  return (
    <div onClick={onClick} className={`p-4 md:p-5 rounded-xl border border-l-4 cursor-pointer transition-colors flex flex-col md:flex-row md:items-center justify-between group gap-4 shadow-sm hover:shadow ${getBorderColor()}`}>
      <div className="flex items-center gap-4">
        <div className={`w-10 h-10 md:w-12 md:h-12 rounded-full flex items-center justify-center shrink-0 ${getIconColor()}`}>
          {offline ? <CloudOff className="w-5 h-5" /> : error ? <AlertTriangle className="w-5 h-5" /> : <User className="w-5 h-5" />}
        </div>
        <div>
          <p className="font-bold text-slate-900 text-sm md:text-base leading-tight">{name}</p>
          {conflict && <p className="text-[10px] font-mono font-bold text-rq-red uppercase tracking-wider mt-1 bg-red-100 px-1.5 py-0.5 rounded w-fit">{conflict}</p>}
          <p className={`text-xs mt-1 ${error ? 'text-rq-red font-medium' : warning ? 'text-amber-600 font-medium' : 'text-slate-500'}`}>{time}</p>
        </div>
      </div>
      
      <div className="flex items-center justify-between md:justify-end gap-4 md:gap-8 w-full md:w-auto mt-2 md:mt-0 pt-3 md:pt-0 border-t border-slate-200 md:border-t-0">
        <div className="text-left md:text-right">
          <p className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">Outbox</p>
          <p className={`font-bold text-sm md:text-base ${warning ? 'text-amber-600' : error ? 'text-rq-red' : 'text-slate-900'}`}>{outbox}</p>
        </div>
        <div className="text-left md:text-right">
          <p className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">Pending</p>
          <p className={`font-bold text-sm md:text-base ${warning ? 'text-amber-600' : error ? 'text-rq-red' : 'text-slate-900'}`}>{pending}</p>
        </div>
        <div className={`px-2 py-1 md:px-3 md:py-1.5 rounded-md font-mono text-[10px] font-bold uppercase tracking-wider flex items-center gap-1.5 md:gap-2 shrink-0
          ${error ? 'bg-red-100 text-red-700 border border-red-200' : 
            warning ? 'bg-amber-100 text-amber-700 border border-amber-200' : 
            offline ? 'bg-slate-200 text-slate-600 border border-slate-300' : 
            'bg-emerald-100 text-emerald-700 border border-emerald-200'}`}
        >
          {!offline && <div className={`w-1.5 h-1.5 rounded-full ${error ? 'bg-red-600' : warning ? 'bg-amber-500 animate-pulse' : 'bg-emerald-600'}`}></div>}
          {status}
        </div>
        <ChevronRight className="w-5 h-5 text-slate-400 group-hover:text-slate-600 transition-colors hidden sm:block" />
      </div>
    </div>
  );
}
