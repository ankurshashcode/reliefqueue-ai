import React, { useState } from 'react';
import { RefreshCw, ArrowUpRight, AlertTriangle, Users } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { DetailDrawer } from '../components/Shared';

const MOCK_COORDS = [
  { id: 'c1', initials: 'JD', name: 'Jane Doe', load: 92, active: 34, overloaded: true, offline: false, zone: 'Zone Alpha' },
  { id: 'c2', initials: 'MS', name: 'Michael Smith', load: 45, active: 18, overloaded: false, offline: false, zone: 'Zone Alpha' },
  { id: 'c3', initials: 'AL', name: 'Anna Lee', load: 78, active: 28, overloaded: false, offline: false, zone: 'Zone Beta' },
  { id: 'c4', initials: 'DJ', name: 'David Jones', load: 0, active: 0, overloaded: false, offline: true, zone: 'Zone Beta' },
];

export function Workload() {
  const { addLog, showToast } = useApp();
  const [selectedCoordId, setSelectedCoordId] = useState<string | null>(null);
  const [filter, setFilter] = useState('ALL');

  const selectedCoord = MOCK_COORDS.find(c => c.id === selectedCoordId);

  const handleQueueReview = () => {
    addLog('Queue Rebalance Review', 'Initiated a rebalance review pending coordinator approval.');
    showToast('Rebalance request added to review queue.', 'success');
  };

  const displayedCoords = MOCK_COORDS.filter(c => {
    if (filter === 'ONLINE') return !c.offline;
    if (filter === 'CRITICAL') return c.overloaded;
    if (filter === 'STALE') return c.active > 0;
    return true;
  });

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-7xl mx-auto h-full overflow-y-auto">
      <div className="mb-6 flex flex-col sm:flex-row justify-between items-start sm:items-end gap-4 shrink-0">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900">Coordinator Workload</h1>
          <p className="text-slate-500 mt-1 md:mt-2 text-sm md:text-base">Human coordination capacity monitoring.</p>
        </div>
        <div className="flex flex-wrap gap-2 md:gap-3">
          <button onClick={() => showToast('Report export queued (demo)', 'info')} className="px-3 py-2 bg-white border border-slate-300 text-slate-700 rounded-lg text-xs md:text-sm font-medium hover:bg-slate-50 transition-colors shadow-sm">
            Export Report
          </button>
          <button onClick={handleQueueReview} className="px-3 py-2 bg-rq-primary text-white rounded-lg text-xs md:text-sm font-semibold hover:bg-rq-primary-hover transition-colors flex items-center gap-2 shadow-sm">
            <RefreshCw className="w-4 h-4" /> Queue Rebalance Review
          </button>
        </div>
      </div>

      {/* Advisory Banner */}
      <div className="mb-6 md:mb-8 p-4 md:p-5 bg-blue-50 border border-blue-200 rounded-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-4 shadow-sm">
        <div className="flex items-start gap-3 md:gap-4">
          <div className="bg-white p-2 rounded-lg shadow-sm mt-0.5 shrink-0">
            <AlertTriangle className="w-5 h-5 md:w-6 md:h-6 text-rq-primary" />
          </div>
          <div>
            <h4 className="font-bold text-slate-900 text-sm md:text-base">Suggest Rebalance</h4>
            <p className="text-xs md:text-sm text-slate-700 mt-1 leading-relaxed max-w-3xl">AI advisory only: AI suggests shifting 15% load from Zone Alpha to Zone Beta. Coordinator approval required.</p>
            <p className="text-[10px] md:text-xs font-mono text-rq-primary mt-2 uppercase tracking-wider font-bold">Safety Note: No worker assignment changes are applied until coordinator approval.</p>
          </div>
        </div>
        <button onClick={handleQueueReview} className="w-full md:w-auto px-5 py-2.5 bg-white border border-blue-200 text-rq-primary font-bold text-xs uppercase tracking-wider rounded-lg hover:bg-blue-100 transition-colors whitespace-nowrap shadow-sm">
          Queue Rebalance Review
        </button>
      </div>

      {/* Top Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-6 md:mb-8">
        <MetricBox title="Total Active Cases" value="1,248" trend="↑ 12%" color="default" onClick={() => setFilter('ALL')} active={filter === 'ALL'} />
        <MetricBox title="Coordinators Online" value="42" subtext="/ 50 Available" color="default" onClick={() => setFilter('ONLINE')} active={filter === 'ONLINE'} />
        <MetricBox title="Critical Escalations" value="7" subtext="Require immediate action" color="red" onClick={() => setFilter('CRITICAL')} active={filter === 'CRITICAL'} />
        <MetricBox title="Stale Cases (>48h)" value="23" subtext="Awaiting review" color="amber" onClick={() => setFilter('STALE')} active={filter === 'STALE'} />
      </div>

      {/* Zone Workloads */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 md:gap-8">
        <ZonePanel name="Zone Alpha" reach="15km" tags={['Medical', 'Food']}>
          {displayedCoords.filter(c => c.zone === 'Zone Alpha').map(c => (
            <CoordinatorRow key={c.id} coord={c} onClick={() => setSelectedCoordId(c.id)} />
          ))}
          {displayedCoords.filter(c => c.zone === 'Zone Alpha').length === 0 && (
            <div className="text-sm text-slate-500 py-4 text-center">No coordinators match filter in this zone.</div>
          )}
        </ZonePanel>

        <ZonePanel name="Zone Beta" reach="22km" tags={['Logistics', 'Water']}>
          {displayedCoords.filter(c => c.zone === 'Zone Beta').map(c => (
            <CoordinatorRow key={c.id} coord={c} onClick={() => setSelectedCoordId(c.id)} />
          ))}
          {displayedCoords.filter(c => c.zone === 'Zone Beta').length === 0 && (
            <div className="text-sm text-slate-500 py-4 text-center">No coordinators match filter in this zone.</div>
          )}
        </ZonePanel>
      </div>

      <DetailDrawer
        isOpen={!!selectedCoord}
        onClose={() => setSelectedCoordId(null)}
        title="Coordinator Details"
      >
        {selectedCoord && (
          <div className="flex flex-col gap-6 h-full">
            <div className="flex items-center gap-4">
              <div className={`w-16 h-16 rounded-full flex items-center justify-center font-bold text-xl ${selectedCoord.offline ? 'bg-slate-200 text-slate-500' : 'bg-blue-100 text-blue-700'}`}>
                {selectedCoord.initials}
              </div>
              <div>
                <h2 className="text-2xl font-bold text-slate-900">{selectedCoord.name}</h2>
                <p className="text-sm text-slate-500 font-mono mt-1">{selectedCoord.zone}</p>
              </div>
            </div>

            <div className="bg-slate-50 border border-slate-200 p-5 rounded-xl">
               <div className="flex justify-between items-center mb-3">
                 <span className="text-sm font-semibold text-slate-700">Current Load</span>
                 <span className={`font-mono font-bold ${selectedCoord.overloaded ? 'text-rq-red' : 'text-slate-900'}`}>{selectedCoord.load}%</span>
               </div>
               <div className="w-full bg-slate-200 rounded-full h-3 mb-4 overflow-hidden">
                 <div className={`h-full rounded-full transition-all duration-500 ${selectedCoord.overloaded ? 'bg-rq-red' : 'bg-blue-500'}`} style={{ width: `${selectedCoord.load}%` }}></div>
               </div>
               <div className="flex justify-between text-sm">
                 <span className="text-slate-600">Active Cases: <span className="font-bold">{selectedCoord.active}</span></span>
                 {selectedCoord.overloaded && <span className="text-rq-red font-bold text-xs flex items-center gap-1 uppercase tracking-wider"><AlertTriangle className="w-3 h-3"/> Overloaded</span>}
               </div>
            </div>

            <div className="mt-auto pt-6 flex flex-col gap-3 border-t border-slate-200">
               <button 
                 onClick={() => {
                   addLog(`Rebalance Queue for ${selectedCoord.name}`, 'Requested review queue.');
                   showToast('Added to pending coordinator review queue.', 'success');
                   setSelectedCoordId(null);
                 }}
                 className="w-full bg-rq-primary hover:bg-rq-primary-hover text-white font-semibold py-3 rounded-lg shadow-sm transition-colors"
               >
                 Suggest Rebalance for Coordinator
               </button>
               <p className="text-[10px] text-center text-slate-500 italic mt-2">
                 AI advisory only. Changes require coordinator approval.
               </p>
            </div>
          </div>
        )}
      </DetailDrawer>
    </div>
  );
}

function MetricBox({ title, value, trend, subtext, color, onClick, active }: any) {
  const isRed = color === 'red';
  const isAmber = color === 'amber';
  
  return (
    <div onClick={onClick} className={`bg-white p-4 md:p-5 rounded-xl border shadow-sm flex flex-col justify-between min-h-[110px] md:h-32 transition-all cursor-pointer hover:shadow-md 
      ${active ? 'ring-2 ring-rq-primary border-rq-primary bg-blue-50/20' : isRed ? 'border-l-4 border-l-rq-red border-y-slate-200 border-r-slate-200' : isAmber ? 'border-l-4 border-l-rq-amber border-y-slate-200 border-r-slate-200' : 'border-slate-200'}`}>
      <span className={`text-[10px] md:text-xs font-mono uppercase tracking-wider font-bold ${isRed ? 'text-rq-red flex items-center gap-1' : isAmber ? 'text-rq-amber' : 'text-slate-500'}`}>
        {isRed && <AlertTriangle className="w-3 h-3" />}
        {title}
      </span>
      <div className="flex items-baseline gap-2 mt-auto flex-wrap">
        <span className={`text-3xl md:text-4xl font-bold ${isRed ? 'text-rq-red' : 'text-slate-900'}`}>{value}</span>
        {trend && <span className="text-rq-emerald text-xs md:text-sm font-bold flex items-center"><ArrowUpRight className="w-3 h-3 mr-0.5"/> {trend}</span>}
        {subtext && <span className="text-slate-500 text-[10px] md:text-xs w-full sm:w-auto">{subtext}</span>}
      </div>
    </div>
  );
}

function ZonePanel({ name, reach, tags, children }: any) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 md:p-6 shadow-sm flex flex-col">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start mb-6 border-b border-slate-100 pb-4 gap-3 shrink-0">
        <div>
          <h3 className="text-xl font-bold text-slate-900">{name}</h3>
          <div className="flex flex-wrap gap-2 mt-2">
            {tags.map((t: string) => (
              <span key={t} className="px-2 py-0.5 bg-slate-100 text-slate-600 text-[10px] font-bold rounded uppercase tracking-wider border border-slate-200">{t}</span>
            ))}
          </div>
        </div>
        <span className="font-mono text-[10px] md:text-xs font-bold bg-slate-50 text-slate-500 border border-slate-200 px-2 py-1 rounded w-fit uppercase tracking-wider">Reach: {reach}</span>
      </div>
      <div className="space-y-3 md:space-y-4 flex-1">
        {children}
      </div>
    </div>
  );
}

function CoordinatorRow({ coord, onClick }: any) {
  const { initials, name, load, active, overloaded, offline } = coord;
  return (
    <div onClick={onClick} className={`p-4 rounded-lg border transition-all cursor-pointer ${offline ? 'opacity-70 bg-slate-50 border-slate-200 hover:bg-slate-100' : overloaded ? 'bg-red-50 border-red-200 hover:bg-red-100' : 'bg-white border-slate-200 hover:border-slate-300 shadow-sm hover:shadow'}`}>
      <div className="flex justify-between items-center mb-3">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm shrink-0 ${offline ? 'bg-slate-200 text-slate-500' : 'bg-blue-100 text-blue-700'}`}>
            {initials}
          </div>
          <span className="font-semibold text-slate-900 text-sm md:text-base">{name}</span>
        </div>
        <span className="font-mono text-[10px] md:text-xs font-bold text-slate-500 uppercase tracking-wider">{offline ? 'Offline' : `${load}% Load`}</span>
      </div>
      
      {!offline && (
        <>
          <div className="w-full bg-slate-200/50 rounded-full h-2 mb-2 overflow-hidden">
            <div className={`h-full rounded-full transition-all ${overloaded ? 'bg-rq-red' : 'bg-blue-500'}`} style={{ width: `${load}%` }}></div>
          </div>
          <div className="flex justify-between text-xs mt-2">
            <span className="text-slate-600 font-medium">{active} Active Cases</span>
            {overloaded ? (
              <span className="text-rq-red font-bold flex items-center gap-1"><AlertTriangle className="w-3 h-3"/> Overloaded</span>
            ) : (
              <span className="text-slate-500">Optimal</span>
            )}
          </div>
        </>
      )}
      {offline && (
        <div className="flex justify-between text-xs mt-2 text-slate-500">
          <span>0 Active Cases</span>
          <span>Last seen 2h ago</span>
        </div>
      )}
    </div>
  );
}
