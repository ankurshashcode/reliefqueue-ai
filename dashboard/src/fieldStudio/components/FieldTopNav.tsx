import { useNavigate } from '../routing';
import { useAppContext } from '../contexts/AppContext';
import { ArrowLeft } from 'lucide-react';
import { FieldNetworkPill } from './FieldNetworkPill';

export const FieldTopNav = ({ title, showBack = false, backActionId, backTo }: { title: string, showBack?: boolean, backActionId?: string, backTo?: string }) => {
  const navigate = useNavigate();
  const { networkStatus } = useAppContext();

  return (
    <header className="fixed top-0 w-full z-50 flex justify-between items-center px-4 h-16 bg-surface border-b-2 border-outline-variant transition-colors duration-200">
      <div className="flex items-center gap-2">
        {showBack && (
          <button data-action-id={backActionId} onClick={() => navigate(backTo || -1)} className="h-12 w-12 flex items-center justify-center -ml-3 text-on-surface hover:bg-surface-container-high rounded-full" aria-label="Back to previous field screen">
            <ArrowLeft size={24} />
          </button>
        )}
        <div><div className="text-[10px] uppercase tracking-widest font-bold text-on-surface-variant">ReliefQueue Field</div><h1 className="font-bold text-xl text-primary truncate max-w-[200px]">{title}</h1></div>
      </div>
      <div className="flex items-center">
        <FieldNetworkPill status={networkStatus} onClick={() => navigate('/field/help')} />
      </div>
    </header>
  );
};
