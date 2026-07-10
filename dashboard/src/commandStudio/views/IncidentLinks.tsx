import { useState } from 'react';
import { useApp } from '../context/AppContext';
import { Link2, AlertTriangle, ShieldAlert, Check, X, FileText, Search, Bot } from 'lucide-react';
import { actionLog } from '../lib/actionLog';
import { AIAdvisoryDrawer } from '../components/AIAdvisoryDrawer';

const CLUSTERS = [
  { id: 'CLUS-801', size: 3, landmark: 'Main St Bridge', overlap: '45 mins', needMatch: 'High', locConf: 'Medium', status: 'Pending Review' },
  { id: 'CLUS-802', size: 2, landmark: 'Community Center', overlap: '10 mins', needMatch: 'Low', locConf: 'High', status: 'Pending Review' },
];

export function IncidentLinks() {
  const { showToast, addLog } = useApp();
  const [selectedCluster, setSelectedCluster] = useState<string | null>(CLUSTERS[0].id);
  const [advisoryOpen, setAdvisoryOpen] = useState(false);

  const handleAction = (action: string) => {
    showToast(`Action '${action}' applied to cluster ${selectedCluster}.`, 'success');
    addLog(`Cluster Action: ${action}`, 'Quality', 'Success', { cluster: selectedCluster });
  };

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto h-full flex flex-col overflow-hidden">
      <div className="mb-6 flex-shrink-0">
        <h2 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">Incident Linkage</h2>
        <p className="text-slate-500 mt-1 md:mt-2 text-sm md:text-base">Review Possible Duplicate clusters based on zone, need type, and text overlap.</p>
      </div>

      <div className="flex-1 flex flex-col md:flex-row gap-6 overflow-hidden">
        {/* Left: Clusters List */}
        <div className="w-full md:w-1/3 flex flex-col gap-3 overflow-y-auto pr-2">
          {CLUSTERS.map(cluster => (
            <div 
              key={cluster.id} 
              onClick={() => setSelectedCluster(cluster.id)}
              className={`bg-white border rounded-xl p-4 cursor-pointer transition-all ${selectedCluster === cluster.id ? 'ring-2 ring-rq-primary border-rq-primary shadow-md' : 'border-slate-200 hover:shadow-sm'}`}
            >
              <div className="flex justify-between items-start mb-2">
                <span className="font-bold text-slate-900">{cluster.id}</span>
                <span className="px-2 py-0.5 bg-blue-50 text-blue-700 text-xs font-semibold rounded-full flex items-center gap-1">
                  <Link2 className="w-3 h-3" /> {cluster.size} linked
                </span>
              </div>
              <div className="text-sm text-slate-600 mb-2">Landmark: <strong>{cluster.landmark}</strong></div>
              <div className="flex flex-wrap gap-2 text-[10px] font-mono text-slate-500">
                <span className="bg-slate-100 px-1.5 py-0.5 rounded">Loc: {cluster.locConf}</span>
                <span className="bg-slate-100 px-1.5 py-0.5 rounded">Need: {cluster.needMatch}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Right: Cluster Detail */}
        <div className="w-full md:w-2/3 bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
          {selectedCluster ? (
            <>
              <div className="p-5 border-b border-slate-200 bg-slate-50 flex justify-between items-center">
                <div>
                  <h3 className="font-bold text-slate-900 text-lg flex items-center gap-2">
                    Cluster {selectedCluster} Detail
                  </h3>
                  <p className="text-sm text-slate-500 mt-1">Review AI linkage rationale and confirm relation.</p>
                </div>
              </div>
              
              <div className="flex-1 overflow-y-auto p-5">
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6 flex items-start gap-3">
                  <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-semibold text-amber-900 text-sm">Coordinator Review Required</h4>
                    <p className="text-sm text-amber-800 mt-1">This is a <strong>possible duplicate</strong> candidate. AI suggests linkage based on shared landmark and time window ({CLUSTERS.find(c=>c.id===selectedCluster)?.overlap}). Confirming merge will collapse these into a single actionable case.</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {/* Mock side-by-side incidents */}
                  <div className="border border-slate-200 rounded-lg p-4">
                    <span className="text-xs text-slate-400 font-mono">Report A (10:42 AM)</span>
                    <p className="text-sm font-medium text-slate-800 mt-2">"help we are stuck in flooded basement by main st bridge"</p>
                  </div>
                  <div className="border border-slate-200 rounded-lg p-4">
                    <span className="text-xs text-slate-400 font-mono">Report B (10:55 AM)</span>
                    <p className="text-sm font-medium text-slate-800 mt-2">"Need rescue at main st bridge, water rising fast in house"</p>
                  </div>
                </div>
              </div>

              <div className="p-4 border-t border-slate-200 bg-slate-50 flex flex-wrap gap-3">
                <button onClick={() => handleAction('Mark Possible Duplicate')} className="px-4 py-2 bg-rq-primary text-white rounded font-medium text-sm hover:bg-rq-primary-hover flex items-center gap-2">
                  <Check className="w-4 h-4" /> Merge to Single Case
                </button>
                <button onClick={() => setAdvisoryOpen(true)} className="px-4 py-2 bg-slate-900 text-white rounded font-medium text-sm hover:bg-slate-800 flex items-center gap-2">
                  <Bot className="w-4 h-4" /> Run AMD/vLLM Link Review
                </button>
                <button onClick={() => handleAction('Keep Separate')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded font-medium text-sm hover:bg-slate-50 flex items-center gap-2">
                  <X className="w-4 h-4" /> Keep Separate
                </button>
                <button onClick={() => handleAction('Request Info')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded font-medium text-sm hover:bg-slate-50">
                  Request Info
                </button>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-400">
              Select a cluster to view details.
            </div>
          )}
        </div>
      </div>
      
      {selectedCluster && (
        <AIAdvisoryDrawer
          isOpen={advisoryOpen}
          onClose={() => setAdvisoryOpen(false)}
          caseId={selectedCluster}
          data={{
            summary: 'Cluster linkage review',
            priority: 'Unknown',
            needType: 'Review',
            locationConfidence: 'Medium'
          }}
        />
      )}
    </div>
  );
}
