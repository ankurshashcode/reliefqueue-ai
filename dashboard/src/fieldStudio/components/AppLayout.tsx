import { Outlet, useNavigate, useLocation } from '../routing';
import { FieldBottomNav } from './FieldBottomNav';
import { useAppContext } from '../contexts/AppContext';
import { AlertTriangle, Info } from 'lucide-react';
import { cn } from '../lib/utils';
import { useEffect } from 'react';

export const AppLayout = () => {
  const { hasConflict, toastMessage } = useAppContext();
  const navigate = useNavigate();
  const location = useLocation();

  // Hide bottom nav on specific screens
  const hideBottomNav = ['/field/sign-in'].includes(location.pathname);

  return (
    <div className="bg-background text-on-background min-h-screen flex flex-col font-sans">
      {hasConflict && location.pathname !== '/field/sync-conflicts' && (
        <button 
          onClick={() => navigate('/field/sync-conflicts')}
          className="fixed top-16 left-0 w-full z-40 bg-secondary-container text-on-secondary-container px-4 py-2 text-sm font-bold flex items-center justify-center gap-2 shadow-sm border-b-2 border-secondary"
        >
          <AlertTriangle size={18} />
          <span>Sync Conflict Detected — Tap to Review</span>
        </button>
      )}

      {/* Global Toast */}
      {toastMessage && (
        <div className="fixed top-24 left-1/2 -translate-x-1/2 z-[100] bg-inverse-surface text-inverse-on-surface px-6 py-3 rounded-xl shadow-lg flex items-center gap-3 w-[90%] max-w-md animate-in fade-in slide-in-from-top-4">
          <Info size={24} className="text-primary-fixed-dim shrink-0" />
          <span className="font-bold text-lg">{toastMessage}</span>
        </div>
      )}

      <div className={cn("flex-1", !hideBottomNav && "pb-16 md:pb-0")}>
        <Outlet />
      </div>
      {!hideBottomNav && <FieldBottomNav />}
    </div>
  );
};
