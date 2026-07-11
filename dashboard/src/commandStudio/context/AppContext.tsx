import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { LogEntry, ToastMsg, ViewState, VIEW_ROUTES, viewForPath } from '../types';

interface AppContextType {
  currentView: ViewState;
  navigate: (view: ViewState) => void;
  logs: LogEntry[];
  addLog: (action: string, categoryOrDetails?: string, status?: string, details?: any) => void;
  toasts: ToastMsg[];
  showToast: (message: string, type?: ToastMsg['type']) => void;
  removeToast: (id: string) => void;
  isLogOpen: boolean;
  setLogOpen: (open: boolean) => void;
}

export const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children, initialView = 'overview' }: { children: React.ReactNode; initialView?: ViewState }) {
  const [currentView, setCurrentView] = useState<ViewState>(initialView);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [toasts, setToasts] = useState<ToastMsg[]>([]);
  const [isLogOpen, setLogOpen] = useState(false);

  const navigate = useCallback((view: ViewState) => {
    setCurrentView(view);
    if (typeof window !== 'undefined') {
      const next = VIEW_ROUTES[view];
      const current = `${window.location.pathname}${window.location.search}`;
      if (current !== next) window.history.pushState({ reliefQueueView: view }, '', next);
    }
  }, []);

  useEffect(() => {
    const syncFromHistory = () => setCurrentView(viewForPath(window.location.pathname));
    window.addEventListener('popstate', syncFromHistory);
    return () => window.removeEventListener('popstate', syncFromHistory);
  }, []);

  const addLog = useCallback((action: string, categoryOrDetails?: string, status?: string, detailsObj?: any) => {
    const detailsStr = typeof detailsObj === 'object' ? JSON.stringify(detailsObj) : (detailsObj || categoryOrDetails);
    
    setLogs(prev => [{
      id: Math.random().toString(36).substring(2, 9),
      timestamp: new Date().toLocaleTimeString(),
      action: status ? `[${status}] ${action}` : action,
      details: detailsStr
    }, ...prev]);
  }, []);

  const showToast = useCallback((message: string, type: ToastMsg['type'] = 'info') => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4000);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return (
    <AppContext.Provider value={{ currentView, navigate, logs, addLog, toasts, showToast, removeToast, isLogOpen, setLogOpen }}>
      {children}
    </AppContext.Provider>
  );
}

export const useApp = () => {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
};
