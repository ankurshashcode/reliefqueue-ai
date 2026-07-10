import { useState } from 'react';
import { useNavigate, useParams } from '../routing';
import { FieldTopNav } from '../components/FieldTopNav';
import { useAppContext } from '../contexts/AppContext';
import { Send, CheckCircle2 } from 'lucide-react';
import { cn } from '../lib/utils';
import { Case } from '../types';

export const FieldStatusUpdateScreen = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { updateCaseStatus, networkStatus, addToSyncQueue, showToast, cases } = useAppContext();
  
  const caseData = cases.find(c => c.id === id) || cases[0];
  const [status, setStatus] = useState<Case['status']>(caseData.status === 'Pending' ? 'In Progress' : caseData.status);
  const [notes, setNotes] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (networkStatus === 'offline') {
      addToSyncQueue({ type: 'Status Update', caseId: id!, details: { status, notes } });
      showToast('Status update queued locally.');
    } else {
      updateCaseStatus(id!, status);
      showToast('Field update submitted for coordinator review.');
    }
    navigate(`/field/cases/${id}`);
  };

  return (
    <div className="pt-16 pb-10 px-4 md:px-10 max-w-3xl mx-auto w-full flex flex-col min-h-screen">
      <FieldTopNav title={`Update Case ${id}`} showBack={true} />
      
      <div className="flex flex-col gap-2 my-6">
        <h1 className="text-2xl md:text-3xl font-bold text-on-background">Update Status — Case Status</h1>
        <p className="text-lg text-on-surface-variant">Coordinator approval required before closure.</p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4 flex-1">
        {/* Status Options */}
        <label className={cn("relative flex cursor-pointer rounded-xl border-2 transition-colors duration-200 p-5 items-center gap-4 shadow-sm",
          status === 'In Progress' ? "border-primary bg-primary-fixed" : "border-outline-variant bg-surface hover:bg-surface-container-low"
        )}>
          <input type="radio" name="status" value="In Progress" checked={status === 'In Progress'} onChange={() => setStatus('In Progress')} className="sr-only" />
          <div className={cn("w-6 h-6 rounded-full border-2 flex items-center justify-center", status === 'In Progress' ? "border-primary" : "border-outline")}>
             {status === 'In Progress' && <div className="w-3 h-3 rounded-full bg-primary" />}
          </div>
          <div className="flex flex-col flex-1">
            <span className="text-xl font-bold text-on-surface">In Progress</span>
          </div>
        </label>

        <label className={cn("relative flex cursor-pointer rounded-xl border-2 transition-colors duration-200 p-5 items-center gap-4 shadow-sm",
          status === 'Paused' ? "border-on-surface-variant bg-surface-container-high" : "border-outline-variant bg-surface hover:bg-surface-container-low"
        )}>
          <input type="radio" name="status" value="Paused" checked={status === 'Paused'} onChange={() => setStatus('Paused')} className="sr-only" />
          <div className={cn("w-6 h-6 rounded-full border-2 flex items-center justify-center", status === 'Paused' ? "border-on-surface-variant" : "border-outline")}>
             {status === 'Paused' && <div className="w-3 h-3 rounded-full bg-on-surface-variant" />}
          </div>
          <div className="flex flex-col flex-1">
            <span className="text-xl font-bold text-on-surface">Paused</span>
          </div>
        </label>

        <label className={cn("relative flex cursor-pointer rounded-xl border-2 transition-colors duration-200 p-5 items-center gap-4 shadow-sm",
          status === 'Needs Assistance' ? "border-secondary bg-secondary-fixed" : "border-outline-variant bg-surface hover:bg-surface-container-low"
        )}>
          <input type="radio" name="status" value="Needs Assistance" checked={status === 'Needs Assistance'} onChange={() => setStatus('Needs Assistance')} className="sr-only" />
          <div className={cn("w-6 h-6 rounded-full border-2 flex items-center justify-center", status === 'Needs Assistance' ? "border-secondary" : "border-outline")}>
             {status === 'Needs Assistance' && <div className="w-3 h-3 rounded-full bg-secondary" />}
          </div>
          <div className="flex flex-col flex-1">
            <span className="text-xl font-bold text-on-surface">Needs Assistance</span>
          </div>
        </label>

        <label className={cn("relative flex cursor-pointer rounded-xl border-2 transition-colors duration-200 p-5 items-center gap-4 shadow-sm",
          status === 'Complete' ? "border-tertiary-container bg-tertiary-fixed" : "border-outline-variant bg-surface hover:bg-surface-container-low"
        )}>
          <input type="radio" name="status" value="Complete" checked={status === 'Complete'} onChange={() => setStatus('Complete')} className="sr-only" />
          <div className={cn("w-6 h-6 rounded-full border-2 flex items-center justify-center", status === 'Complete' ? "border-tertiary-container" : "border-outline")}>
             {status === 'Complete' && <div className="w-3 h-3 rounded-full bg-tertiary-container" />}
          </div>
          <div className="flex flex-col flex-1">
            <span className="text-xl font-bold text-on-surface">Complete</span>
            {status === 'Complete' && (
              <span className="text-sm font-bold text-tertiary-container mt-1 flex items-center gap-1">
                <CheckCircle2 size={16} />
                Coordinator approval required before closure.
              </span>
            )}
          </div>
        </label>

        <div className="flex-1 min-h-[32px]"></div>

        {/* Notes Field */}
        <div className="flex flex-col gap-2 mb-4">
          <label htmlFor="status_notes" className="text-base font-bold text-on-surface-variant">Additional Notes (Optional)</label>
          <textarea 
            id="status_notes" 
            rows={3} 
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full bg-surface border-2 border-outline-variant rounded-xl p-4 text-lg text-on-surface focus:border-primary focus:outline-none focus:ring-0 shadow-sm resize-none" 
            placeholder="Enter relevant field details..."
          />
        </div>

        {/* Action Area */}
        <div className="mt-auto pt-6 border-t-2 border-outline-variant/30 flex flex-col gap-3 pb-8">
          <button type="submit" className="w-full bg-primary text-on-primary h-16 rounded-xl text-xl font-bold flex items-center justify-center gap-2 hover:bg-primary-container active:scale-[0.98] border-2 border-primary shadow-sm">
            <Send size={24} />
            {networkStatus === 'offline' ? 'Queue for Sync' : 'Submit Update'}
          </button>
          <p className="text-base text-on-surface-variant text-center font-bold">This will update the primary queue.</p>
        </div>
      </form>
    </div>
  );
};
