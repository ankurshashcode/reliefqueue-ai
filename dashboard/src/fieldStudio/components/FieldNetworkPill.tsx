import { cn } from '../lib/utils';
import { Wifi, WifiOff, RefreshCcw, SignalLow } from 'lucide-react';
import { NetworkStatus } from '../types';

export const FieldNetworkPill = ({ status, onClick, compact = false }: { status: NetworkStatus, onClick?: () => void, compact?: boolean }) => {
  const label = status === 'online' ? 'Online' : status === 'slow' ? 'Slow' : status === 'syncing' ? 'Syncing' : 'Offline';

  return (
    <button 
      onClick={onClick}
      disabled={!onClick}
      aria-label={`Network status: ${label}${onClick ? '. Open network help' : ''}`}
      className={cn(
        "text-[10px] px-2 sm:px-3 py-1.5 rounded-full flex items-center gap-1.5 font-bold uppercase tracking-wider border-2 transition-transform",
        onClick && "active:scale-95 cursor-pointer",
        status === 'online' ? "bg-tertiary-container text-on-tertiary-container border-tertiary" :
        status === 'syncing' ? "bg-primary-container text-on-primary-container border-primary" :
        status === 'slow' ? "bg-secondary-container text-on-secondary-container border-secondary" :
        "bg-surface-variant text-on-surface-variant border-outline"
      )}
    >
      {status === 'online' && <Wifi size={14} />}
      {status === 'syncing' && <RefreshCcw size={14} className="animate-spin" />}
      {status === 'slow' && <SignalLow size={14} />}
      {status === 'offline' && <WifiOff size={14} />}
      <span className={compact ? 'hidden sm:inline' : undefined}>{label}</span>
    </button>
  );
};
