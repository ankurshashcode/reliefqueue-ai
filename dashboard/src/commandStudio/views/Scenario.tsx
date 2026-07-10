import React, { useState } from 'react';
import { useApp } from '../context/AppContext';
import { Map, Edit3, Check, Crosshair } from 'lucide-react';
import { actionLog } from '../lib/actionLog';

export function Scenario() {
  const { addLog, showToast, navigate } = useApp();
  const [activeProfile, setActiveProfile] = useState('alpha');

  const handleActivate = (profile: string) => {
    setActiveProfile(profile);
    addLog(`Scenario Activated`, `Changed active scenario profile to ${profile}.`);
    showToast(`Scenario activated locally for demo.`, 'success');
  };
  
  const handleEdit = (profile: string) => {
    showToast(`Opened ${profile} configuration.`, 'info');
    actionLog.add('Edit Scenario', 'Config Update', 'Success');
  };
  
  const handleMarkArea = (profile: string) => {
    showToast(`Opening map to mark restricted areas for ${profile}.`, 'info');
    navigate('map');
  };

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-5xl mx-auto h-full overflow-y-auto">
      <div className="mb-6 md:mb-8 flex flex-col sm:flex-row justify-between items-start sm:items-end gap-4 shrink-0">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900">Scenario Settings</h1>
          <p className="text-slate-500 mt-1 md:mt-2 text-sm md:text-base">Scenario profiles for AI advisory boundary policies.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => showToast('Import disabled in demo.', 'warning')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 font-semibold text-sm rounded-lg hover:bg-slate-50 transition-colors shadow-sm">
            Import Scenario
          </button>
          <button onClick={() => showToast('Create new scenario opened.', 'info')} className="px-4 py-2 bg-rq-primary text-white font-semibold text-sm rounded-lg hover:bg-rq-primary-hover transition-colors shadow-sm">
            Create Scenario
          </button>
        </div>
      </div>

      <div className="space-y-6 md:space-y-8">
        <ScenarioCard 
          id="alpha"
          title="Flood Response Alpha"
          subtitle="Coastal Sector 4"
          isActive={activeProfile === 'alpha'}
          onActivate={() => handleActivate('alpha')}
          zones="Zone 4A, 4B (Delta)"
          gps="34.0522° N, 118.2437° W"
          radius="45 km"
          policy="Strict Within Radius"
          needs={['Water', 'Medical']}
          blocked="3 Blocked Routes"
          safe="12 Safe Areas"
          onEdit={() => handleEdit('alpha')}
          onMarkArea={() => handleMarkArea('alpha')}
        />

        <ScenarioCard 
          id="beta"
          title="Earthquake Protocol Beta"
          subtitle="Urban Core Sector 1"
          isActive={activeProfile === 'beta'}
          onActivate={() => handleActivate('beta')}
          zones="Zone 1A-1D"
          gps="34.0407° N, 118.2468° W"
          radius="15 km (Restricted)"
          policy="Permissive Routing"
          needs={['Shelter', 'Search/Rescue']}
          blocked="14 Blocked Routes"
          safe="2 Safe Areas"
          onEdit={() => handleEdit('beta')}
          onMarkArea={() => handleMarkArea('beta')}
        />
      </div>
    </div>
  );
}

function ScenarioCard({ title, subtitle, isActive, onActivate, onEdit, onMarkArea, zones, gps, radius, policy, needs, blocked, safe }: any) {
  return (
    <div className={`bg-white border rounded-xl overflow-hidden transition-all duration-300 ${isActive ? 'border-slate-200 shadow-md ring-1 ring-emerald-500/20' : 'border-slate-200 opacity-75 hover:opacity-100 hover:shadow-sm'}`}>
      <div className={`h-32 md:h-40 w-full relative ${isActive ? 'bg-slate-800' : 'bg-slate-200 grayscale'}`}>
        {isActive && <div className="absolute inset-0 opacity-40 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-blue-900 via-slate-900 to-slate-900"></div>}
        <div className="absolute inset-0 flex items-center justify-center opacity-30">
          <Map className={`w-24 h-24 ${isActive ? 'text-blue-500' : 'text-slate-500'}`} />
        </div>
        
        {isActive && (
          <div className="absolute top-4 left-4 bg-emerald-900/90 text-emerald-300 border border-emerald-500/50 font-mono text-[10px] font-bold px-3 py-1.5 rounded uppercase tracking-wider backdrop-blur-sm shadow-sm flex items-center gap-1.5">
            <Check className="w-3 h-3" /> Active Profile
          </div>
        )}
      </div>
      
      <div className={`p-4 md:p-6 border-l-4 ${isActive ? 'border-l-emerald-500' : 'border-l-slate-300'} flex flex-col`}>
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start mb-6 gap-4">
          <div>
            <h3 className="text-xl md:text-2xl font-bold text-slate-900 leading-tight">{title}</h3>
            <p className="text-sm text-slate-500 mt-1">{subtitle}</p>
          </div>
          <div className="flex gap-2">
            {isActive && (
              <button onClick={onMarkArea} className="w-full sm:w-auto bg-white border border-slate-300 text-slate-700 font-semibold text-sm px-3 py-2 rounded-lg hover:bg-slate-50 transition-colors shrink-0 flex items-center justify-center gap-1.5">
                <Crosshair className="w-4 h-4" /> Mark Map
              </button>
            )}
            {isActive ? (
               <button onClick={onEdit} className="w-full sm:w-auto bg-blue-50 text-rq-primary border border-blue-200 font-semibold text-sm px-4 py-2 rounded-lg hover:bg-blue-100 transition-colors shrink-0 flex items-center justify-center gap-1.5">
                 <Edit3 className="w-4 h-4" /> Parameters
               </button>
            ) : (
               <button onClick={onActivate} className="w-full sm:w-auto bg-white border border-slate-300 text-slate-700 font-semibold text-sm px-4 py-2 rounded-lg hover:bg-slate-50 transition-colors shrink-0">
                 Activate
               </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 md:gap-6 mb-6">
          <ParamField label="Operation Zone" value={zones} />
          <ParamField label="Relief Hub GPS" value={gps} mono />
          <ParamField label="Reachable Radius" value={radius} />
          <ParamField label="Case Location Policy" value={policy} />
        </div>

        <div className="mb-6">
           <span className="text-[10px] font-mono text-slate-500 tracking-wider font-bold block mb-2">Priority Needs</span>
           <div className="flex flex-wrap gap-2">
             {needs.map((n: string) => (
               <span key={n} className="bg-slate-100 border border-slate-200 text-slate-700 text-xs font-bold px-3 py-1 rounded-md uppercase tracking-wide">{n}</span>
             ))}
           </div>
        </div>

        <div className="border-t border-slate-100 pt-4 flex justify-between text-xs md:text-sm">
           <span className="text-rq-red font-semibold">{blocked}</span>
           <span className="text-emerald-600 font-semibold">{safe}</span>
        </div>
      </div>
    </div>
  );
}

function ParamField({ label, value, mono }: any) {
  return (
    <div className="bg-slate-50 border border-slate-100 p-3 rounded-lg">
      <span className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-wider block mb-1">{label}</span>
      <span className={`text-sm font-semibold text-slate-900 ${mono ? 'font-mono tracking-tight text-[11px] sm:text-xs' : ''}`}>{value}</span>
    </div>
  );
}
