import { useNavigate } from '../routing';
import { FieldTopNav } from '../components/FieldTopNav';
import { useAppContext } from '../contexts/AppContext';
import { AlertTriangle, Clock } from 'lucide-react';
import { cn } from '../lib/utils';

export const FieldSyncConflictScreen = () => {
  const navigate = useNavigate();
  const { resolveConflict, hasConflict, showToast } = useAppContext();

  const handleResolve = (keepMine: boolean) => {
    resolveConflict(keepMine);
    showToast(keepMine ? 'Merge choice saved for coordinator review.' : 'Merge choice saved for coordinator review.');
    navigate(-1);
  };

  if (!hasConflict) {
    return (
      <div className="pt-16 pb-20 px-4 md:px-10 max-w-4xl mx-auto w-full flex flex-col items-center justify-center h-screen">
        <FieldTopNav title="Sync Conflicts" showBack={true} />
        <h2 className="text-2xl font-bold">No Sync Conflicts</h2>
        <button onClick={() => navigate(-1)} className="mt-4 text-primary font-bold">Go Back</button>
      </div>
    );
  }

  return (
    <div className="pt-16 pb-20 px-4 md:px-10 max-w-4xl mx-auto w-full">
      <FieldTopNav title="Sync Conflict" showBack={true} />
      
      <div className="my-6">
        <div className="flex items-center gap-3 text-error mb-2">
          <AlertTriangle size={32} />
          <h1 className="text-3xl font-bold">Review Required</h1>
        </div>
        <p className="text-lg text-on-surface-variant font-bold leading-relaxed">
          Case <span className="text-on-surface">RQ-1042</span> was updated by another user while you were offline.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Local Draft */}
        <div className="bg-surface-container rounded-xl border-2 border-primary p-5 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 bg-primary text-on-primary text-xs font-bold px-3 py-1 rounded-bl-lg uppercase">
            Your Draft
          </div>
          <h3 className="text-xl font-bold text-on-surface mb-4 mt-2">Status: Complete</h3>
          <div className="space-y-3">
             <div>
               <span className="text-xs font-bold text-on-surface-variant uppercase">Note</span>
               <p className="text-base text-on-surface bg-surface p-3 rounded border border-outline-variant mt-1">Situation verified. Awaiting transport.</p>
             </div>
             <div className="flex items-center gap-2 text-sm text-on-surface-variant font-bold">
               <Clock size={16} /> Modified Today, 08:45 AM
             </div>
          </div>
          
          <button 
            onClick={() => handleResolve(true)} 
            className="mt-6 w-full h-14 bg-primary text-on-primary text-lg font-bold rounded-xl hover:bg-primary-container active:scale-[0.98] transition-transform shadow-sm flex items-center justify-center"
          >
            Keep Mine
          </button>
        </div>

        {/* Server Version */}
        <div className="bg-surface-container rounded-xl border-2 border-outline-variant p-5 shadow-sm relative">
          <div className="absolute top-0 right-0 bg-surface-variant text-on-surface-variant text-xs font-bold px-3 py-1 rounded-bl-lg uppercase">
            Server Version
          </div>
          <h3 className="text-xl font-bold text-on-surface mb-4 mt-2">Status: In Progress</h3>
          <div className="space-y-3">
             <div>
               <span className="text-xs font-bold text-on-surface-variant uppercase">Note</span>
               <p className="text-base text-on-surface bg-surface p-3 rounded border border-outline-variant mt-1">Transport dispatched. ETA 20 mins.</p>
             </div>
             <div className="flex items-center gap-2 text-sm text-on-surface-variant font-bold">
               <Clock size={16} /> Modified Today, 08:50 AM
             </div>
          </div>
          
          <button 
            onClick={() => handleResolve(false)} 
            className="mt-6 w-full h-14 bg-surface text-primary border-2 border-primary text-lg font-bold rounded-xl hover:bg-primary-container active:scale-[0.98] transition-transform shadow-sm flex items-center justify-center"
          >
            Use Server Version
          </button>
        </div>
      </div>

      <div className="mt-6 p-5 bg-surface-variant rounded-xl border-2 border-outline-variant flex flex-col md:flex-row justify-between items-center gap-4">
        <p className="text-base text-on-surface-variant font-bold">
          Cannot decide? You can manually merge changes.
        </p>
        <button onClick={() => showToast('Manual merge saved for coordinator review.')} className="h-12 px-6 bg-transparent text-primary text-sm font-bold rounded-full border-2 border-primary flex items-center justify-center gap-2 hover:bg-primary-container">
          Merge Manually
        </button>
      </div>

    </div>
  );
};
