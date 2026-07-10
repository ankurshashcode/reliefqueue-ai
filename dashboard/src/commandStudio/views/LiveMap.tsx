import React, { useState } from 'react';
import { AlertCircle, ZoomIn, ZoomOut, Crosshair, CheckCircle, Info, Map as MapIcon, Route, Plus, Save, Bot } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { DetailDrawer } from '../components/Shared';
import { AIAdvisoryDrawer } from '../components/AIAdvisoryDrawer';

const MOCK_CASES = [
  { id: 'RQ-8924', priority: 'CRITICAL', title: 'Medical Evacuation', desc: 'Immediate airlift required for 45 individuals. Weather deteriorating.', status: 'ACTIVE', zone: 'Sector Alpha', conf: '98% (High)', lat: '30%', lng: '25%' },
  { id: 'RQ-8925', priority: 'HIGH', title: 'Supply Route Clearance', desc: 'Debris removal required to re-establish primary supply line.', status: 'PENDING', zone: 'Route B', conf: '85%', lat: '50%', lng: '66%' },
  { id: 'RQ-8926', priority: 'MEDIUM', title: 'Generator Fuel Drop', desc: 'Backup power at Field Hospital Beta needs fuel within 12 hours.', status: 'REVIEW', zone: 'Sector Gamma', conf: '92%', lat: '70%', lng: '40%' },
];

export function LiveMap() {
  const { addLog, showToast, navigate } = useApp();
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('ALL');
  const [showScenario, setShowScenario] = useState(false);
  const [markingMode, setMarkingMode] = useState(false);
  const [advisoryOpen, setAdvisoryOpen] = useState(false);

  const selectedCase = MOCK_CASES.find(c => c.id === selectedCaseId);
  
  const filteredCases = filter === 'ALL' ? MOCK_CASES : MOCK_CASES.filter(c => c.priority === filter || c.status === filter);

  const handleAction = (actionName: string) => {
    addLog(`Map Action: ${actionName}`, `Applied on case ${selectedCase?.id}`);
    showToast(`Action '${actionName}' logged pending coordinator approval.`, 'success');
  };
  
  const handleToggleScenario = () => {
    setShowScenario(!showScenario);
    addLog('Map Layer Toggle', `Scenario boundaries ${!showScenario ? 'enabled' : 'disabled'}`);
    showToast(`Scenario overlay ${!showScenario ? 'loaded' : 'hidden'}`, 'info');
  };
  
  const handleMarkingMode = () => {
    setMarkingMode(!markingMode);
    addLog('Map Tool', `Area marking mode ${!markingMode ? 'activated' : 'deactivated'}`);
  };

  return (
    <div className="flex flex-col md:flex-row h-full w-full relative">
      {/* Map Area */}
      <div className="flex-1 bg-slate-200 relative overflow-hidden">
        {/* Synthetic Map Background Placeholder */}
        <div className="absolute inset-0 opacity-20" style={{ 
          backgroundImage: 'radial-gradient(#94a3b8 1px, transparent 1px)', 
          backgroundSize: '20px 20px' 
        }}></div>
        
        {/* Scenario Overlay Mock */}
        {showScenario && (
          <>
            <div className="absolute top-[20%] left-[20%] w-[30%] h-[30%] border-2 border-emerald-500 bg-emerald-500/10 rounded-full flex items-center justify-center">
              <span className="bg-emerald-900/80 text-emerald-100 text-[10px] font-mono px-2 py-1 rounded">Zone Alpha (Active)</span>
            </div>
            <div className="absolute top-[50%] left-[60%] w-[20%] h-[40%] border-2 border-rq-red bg-rq-red/10 border-dashed rounded-lg flex items-center justify-center">
              <span className="bg-red-900/80 text-red-100 text-[10px] font-mono px-2 py-1 rounded">Restricted Area</span>
            </div>
          </>
        )}
        
        {/* Marking Mode Overlay Mock */}
        {markingMode && (
          <div className="absolute inset-0 bg-rq-primary/5 cursor-crosshair z-10 flex items-center justify-center pointer-events-none">
             <div className="bg-white/90 backdrop-blur px-4 py-2 rounded-full shadow-lg border border-rq-primary/30 text-rq-primary font-medium text-sm flex items-center gap-2">
               <Crosshair className="w-4 h-4 animate-pulse" /> Click map to draw boundary
             </div>
          </div>
        )}
        
        {/* Mock Data Warning */}
        <div className="absolute top-4 left-4 md:top-6 md:left-6 z-20 bg-rq-amber border border-rq-amber shadow-lg rounded-lg px-3 md:px-4 py-2 md:py-3 flex items-center gap-2 md:gap-3 max-w-[calc(100%-80px)]">
          <AlertCircle className="w-4 h-4 md:w-5 md:h-5 text-white shrink-0" />
          <div className="text-white">
            <div className="font-bold text-xs md:text-sm leading-tight">Mock GPS / Demo Data</div>
            <div className="text-[10px] md:text-xs opacity-90">Synthetic Jakarta View</div>
          </div>
        </div>

        {/* Map Controls */}
        <div className="absolute bottom-4 right-4 md:bottom-6 md:right-6 flex flex-col gap-2 z-20">
          <button onClick={handleMarkingMode} aria-label={markingMode ? 'Save marked area draft' : 'Start marking an affected area'} className={`w-10 h-10 rounded-lg shadow border flex items-center justify-center transition-colors ${markingMode ? 'bg-rq-primary border-rq-primary text-white' : 'bg-white border-slate-200 text-slate-600 hover:text-rq-primary'}`} title="Mark Area">
            {markingMode ? <Save className="w-5 h-5" /> : <Plus className="w-5 h-5" />}
          </button>
          <button onClick={handleToggleScenario} aria-label={showScenario ? 'Hide scenario profile overlay' : 'Show scenario profile overlay'} className={`w-10 h-10 rounded-lg shadow border flex items-center justify-center mt-2 transition-colors ${showScenario ? 'bg-emerald-600 border-emerald-600 text-white' : 'bg-white border-slate-200 text-slate-600 hover:text-rq-primary'}`} title="Toggle Scenario Profile">
            <Route className="w-5 h-5" />
          </button>
          <div className="h-px bg-slate-300 w-6 mx-auto my-1"></div>
          <button onClick={() => showToast('Zoom changed', 'info')} aria-label="Zoom map in" className="w-10 h-10 bg-white rounded-lg shadow border border-slate-200 flex items-center justify-center text-slate-600 hover:text-rq-primary">
            <ZoomIn className="w-5 h-5" />
          </button>
          <button onClick={() => showToast('Zoom changed', 'info')} aria-label="Zoom map out" className="w-10 h-10 bg-white rounded-lg shadow border border-slate-200 flex items-center justify-center text-slate-600 hover:text-rq-primary">
            <ZoomOut className="w-5 h-5" />
          </button>
          <button onClick={() => showToast('Location re-centered', 'info')} aria-label="Re-center map on active response area" className="w-10 h-10 bg-white rounded-lg shadow border border-slate-200 flex items-center justify-center text-slate-600 hover:text-rq-primary mt-2">
            <Crosshair className="w-5 h-5" />
          </button>
        </div>

        {/* Mock Pins */}
        {filteredCases.map(c => {
          const isCritical = c.priority === 'CRITICAL';
          const isSelected = c.id === selectedCaseId;
          return (
            <div 
              key={c.id}
              role="button"
              tabIndex={0}
              aria-label={`Open map case ${c.id}: ${c.title} in ${c.zone}`}
              className={`absolute flex flex-col items-center cursor-pointer transform -translate-x-1/2 -translate-y-full transition-transform hover:scale-110 z-20 ${isSelected ? 'scale-110 z-30' : ''}`}
              style={{ top: c.lat, left: c.lng }}
              onClick={() => setSelectedCaseId(c.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  setSelectedCaseId(c.id);
                }
              }}
            >
              <div className={`text-white text-[10px] font-bold px-2 py-1 rounded shadow-sm mb-1 uppercase tracking-wide
                ${isCritical ? 'bg-rq-red' : c.priority === 'HIGH' ? 'bg-rq-amber' : 'bg-slate-600'}
              `}>
                {c.zone}
              </div>
              <div className={`w-4 h-4 rounded-full border-2 border-white shadow 
                ${isCritical ? 'bg-rq-red ring-4 ring-rq-red/30 animate-pulse' : c.priority === 'HIGH' ? 'bg-rq-amber' : 'bg-slate-600'}
              `}></div>
            </div>
          );
        })}
      </div>

      {/* List Sidebar */}
      <div className="w-full md:w-[350px] lg:w-[400px] bg-white border-t md:border-t-0 md:border-l border-slate-200 flex flex-col h-[40vh] md:h-full shadow-xl z-20 shrink-0">
        <div className="p-4 border-b border-slate-200 shrink-0 bg-slate-50 flex flex-col gap-3">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold">Active Cases (Demo)</h2>
            <button onClick={() => navigate('scenario')} className="text-[10px] uppercase font-bold tracking-wider text-rq-primary hover:underline flex items-center gap-1">
              <MapIcon className="w-3 h-3" /> Config
            </button>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {['ALL', 'CRITICAL', 'PENDING', 'REVIEW'].map(f => (
              <button 
                key={f} 
                onClick={() => setFilter(f)}
                className={`px-3 py-1 rounded-full text-xs font-bold whitespace-nowrap transition-colors border
                  ${filter === f ? 'bg-slate-800 text-white border-slate-800' : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-100'}
                `}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-50/50">
          {filteredCases.map(c => (
            <CaseCard 
              key={c.id}
              caseData={c}
              selected={c.id === selectedCaseId}
              onClick={() => setSelectedCaseId(c.id)}
            />
          ))}
          {filteredCases.length === 0 && (
            <div className="text-center text-sm text-slate-500 mt-10">No cases match the selected filter.</div>
          )}
        </div>
      </div>

      <DetailDrawer 
        isOpen={!!selectedCase} 
        onClose={() => setSelectedCaseId(null)}
        title={selectedCase ? `Case Details: ${selectedCase.id}` : ''}
      >
        {selectedCase && (
          <div className="flex flex-col gap-4 h-full">
            <div className="flex items-center gap-2 text-xs font-mono font-bold mb-1">
              <div className={`w-2 h-2 rounded-full ${selectedCase.priority === 'CRITICAL' ? 'bg-rq-red' : 'bg-rq-amber'}`}></div>
              <span className={selectedCase.priority === 'CRITICAL' ? 'text-rq-red' : 'text-rq-amber'}>
                {selectedCase.priority} PRIORITY
              </span>
            </div>
            <div>
              <h3 className="text-2xl font-bold leading-tight text-slate-900">{selectedCase.title}</h3>
              <p className="text-sm text-slate-500 mt-1">{selectedCase.zone}</p>
            </div>
            
            <p className="text-sm text-slate-700 bg-slate-50 p-4 rounded-lg border border-slate-200">
              {selectedCase.desc}
            </p>

            <div className="grid grid-cols-2 gap-3 mt-2">
              <DetailField label="Need Type" value="Medical / Evacuation" />
              <DetailField label="Loc. Confidence" value={selectedCase.conf} highlight />
            </div>

            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 mt-2 flex items-start gap-3">
              <CheckCircle className="w-5 h-5 text-emerald-600 mt-0.5 shrink-0" />
              <div>
                <div className="text-xs font-bold text-emerald-800 uppercase tracking-wider">Coordinator Approval</div>
                <div className="text-sm text-emerald-900 mt-0.5">Approved by S. Jenkins</div>
              </div>
            </div>

            <div className="mt-auto pt-6 flex flex-col gap-3">
              <button onClick={() => setAdvisoryOpen(true)} className="w-full bg-slate-900 hover:bg-slate-800 text-white py-3 rounded-lg text-sm font-semibold transition-colors shadow-sm flex items-center justify-center gap-2">
                <Bot className="w-4 h-4" /> Request AI Advisory
              </button>
              <div className="grid grid-cols-2 gap-3">
                 <button onClick={() => handleAction('Suggest Assignment')} className="w-full bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 py-2.5 rounded-lg text-xs font-semibold transition-colors">
                   Suggest Assignment
                 </button>
                 <button onClick={() => handleAction('Mark Needs Info')} className="w-full bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 py-2.5 rounded-lg text-xs font-semibold transition-colors">
                   Mark Needs Info
                 </button>
              </div>
              <p className="text-[10px] text-center text-slate-500 italic mt-2">
                AI advisory only. Coordinator approval required for all actions.
              </p>
            </div>
          </div>
        )}
      </DetailDrawer>
      
      {selectedCase && (
        <AIAdvisoryDrawer
          isOpen={advisoryOpen}
          onClose={() => setAdvisoryOpen(false)}
          caseId={selectedCase.id}
          data={{
            summary: selectedCase.desc,
            priority: selectedCase.priority,
            needType: 'Medical / Evacuation',
            locationConfidence: selectedCase.conf
          }}
        />
      )}
    </div>
  );
}

function CaseCard({ caseData, selected, onClick }: any) {
  const isCritical = caseData.priority === 'CRITICAL';
  return (
    <div onClick={onClick} className={`p-4 rounded-xl border cursor-pointer transition-all ${
      selected 
        ? `bg-blue-50/80 border-rq-primary shadow-sm ring-1 ring-rq-primary ring-opacity-50` 
        : `bg-white border-slate-200 hover:border-slate-300 shadow-sm hover:shadow`
    }`}>
      <div className="flex justify-between items-start mb-2">
        <div className={`flex items-center gap-1.5 text-[10px] sm:text-xs font-mono font-bold ${isCritical ? 'text-rq-red' : caseData.priority === 'HIGH' ? 'text-rq-amber' : 'text-slate-500'}`}>
          <div className={`w-1.5 h-1.5 rounded-full ${isCritical ? 'bg-rq-red animate-pulse' : caseData.priority === 'HIGH' ? 'bg-rq-amber' : 'bg-slate-500'}`}></div>
          {caseData.priority}
        </div>
        <div className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-600">{caseData.status}</div>
      </div>
      <h4 className="font-semibold text-slate-900 mb-1 leading-tight text-sm sm:text-base">{caseData.title}</h4>
      <p className="text-xs text-slate-500 line-clamp-2">{caseData.desc}</p>
    </div>
  );
}

function DetailField({ label, value, highlight }: any) {
  return (
    <div className="bg-white border border-slate-200 p-3 rounded-lg shadow-sm">
      <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-sm font-medium ${highlight ? 'text-rq-primary font-bold' : 'text-slate-900'}`}>{value}</div>
    </div>
  );
}
