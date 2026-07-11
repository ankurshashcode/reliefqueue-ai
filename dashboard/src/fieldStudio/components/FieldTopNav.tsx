import { useNavigate } from '../routing';
import { useAppContext } from '../contexts/AppContext';
import { ArrowLeft } from 'lucide-react';
import { FieldNetworkPill } from './FieldNetworkPill';
import { ProductRoleSwitcher } from '../../components/ProductRoleSwitcher';

export const FieldTopNav = ({ title, showBack = false, backActionId, backTo }: { title: string, showBack?: boolean, backActionId?: string, backTo?: string }) => {
  const navigate = useNavigate();
  const { networkStatus } = useAppContext();

  return (
    <header className="fixed inset-x-0 top-0 z-50 flex h-16 w-full items-center justify-between border-b-2 border-outline-variant bg-surface px-4 transition-colors duration-200">
      <div className="flex min-w-0 items-center gap-2">
        {showBack && (
          <button data-action-id={backActionId} onClick={() => navigate(backTo || -1)} className="h-12 w-12 flex items-center justify-center -ml-3 text-on-surface hover:bg-surface-container-high rounded-full" aria-label="Back to previous field screen">
            <ArrowLeft size={24} />
          </button>
        )}
        <div className="min-w-0"><div className="text-[10px] uppercase tracking-widest font-bold text-on-surface-variant">ReliefQueue Field</div><h1 className="max-w-[100px] truncate text-xl font-bold text-primary sm:max-w-[200px]">{title}</h1></div>
      </div>
      <div className="flex shrink-0 items-center gap-1 sm:gap-2">
        <ProductRoleSwitcher currentRole="field" compact />
        <FieldNetworkPill status={networkStatus} onClick={() => navigate('/field/help')} compact />
      </div>
    </header>
  );
};
