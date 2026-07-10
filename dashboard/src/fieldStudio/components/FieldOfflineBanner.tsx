import { cn } from '../lib/utils';
import { useNavigate } from '../routing';

export const FieldOfflineBanner = ({ message = "Offline — updates are saved locally and will sync when connection is restored.", className }: { message?: string, className?: string }) => {
  const navigate = useNavigate();
  return (
    <button 
      onClick={() => navigate('/field/outbox')}
      className={cn("w-full bg-surface-variant border-2 border-outline text-on-surface px-4 py-3 flex items-center justify-center gap-2 shadow-sm rounded-xl active:scale-95 transition-all", className)}
    >
      <span className="text-sm font-bold text-center">{message}</span>
    </button>
  );
};
