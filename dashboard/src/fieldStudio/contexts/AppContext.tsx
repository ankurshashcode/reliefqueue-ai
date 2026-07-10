import React, { createContext, useContext, useState, ReactNode, useCallback, useEffect } from 'react';
import { NetworkStatus, Case, SyncItem, FieldNote } from '../types';
import { INITIAL_CASES } from '../data';

const QUEUE_KEY = 'reliefqueue.fieldQueue.v1';
const DEFAULT_QUEUE: SyncItem[] = [
  { id: '1', type: 'Status Update', caseId: 'RQ-1042', timestamp: '10:42 AM' },
  { id: '2', type: 'Field Note', caseId: 'RQ-1042', timestamp: '09:15 AM' }
];

function loadQueue(): SyncItem[] {
  try {
    const raw = window.localStorage.getItem(QUEUE_KEY);
    if (!raw) return DEFAULT_QUEUE;
    const parsed = JSON.parse(raw);
    if (parsed?.schema !== 1 || !Array.isArray(parsed.entries)) return DEFAULT_QUEUE;
    return parsed.entries.map((entry: any) => ({
      id: String(entry.id),
      type: String(entry.type || 'Field Update'),
      caseId: String(entry.caseId || 'RQ-1042'),
      timestamp: String(entry.timestamp || 'Pending')
    }));
  } catch {
    return DEFAULT_QUEUE;
  }
}

interface AppContextType {
  networkStatus: NetworkStatus;
  setNetworkStatus: (status: NetworkStatus) => void;
  cases: Case[];
  updateCaseStatus: (id: string, status: Case['status']) => void;
  syncQueue: SyncItem[];
  addToSyncQueue: (item: Omit<SyncItem, 'id' | 'timestamp'>) => void;
  clearSyncQueue: () => void;
  hasConflict: boolean;
  resolveConflict: (keepMine: boolean) => void;
  fieldNotes: Record<string, FieldNote[]>;
  addNote: (caseId: string, note: Omit<FieldNote, 'id' | 'timestamp' | 'author'>) => void;
  toastMessage: string | null;
  showToast: (message: string) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider = ({ children }: { children: ReactNode }) => {
  const [networkStatus, setNetworkStatus] = useState<NetworkStatus>('online');
  const [cases, setCases] = useState<Case[]>(INITIAL_CASES);
  const [syncQueue, setSyncQueue] = useState<SyncItem[]>(loadQueue);
  const [hasConflict, setHasConflict] = useState(true);
  const [fieldNotes, setFieldNotes] = useState<Record<string, FieldNote[]>>({
    'RQ-1042': [
      { id: 'n1', type: 'General Note', text: 'Situation verified. Awaiting transport.', timestamp: 'Today, 08:45 AM', author: 'Officer Chen' }
    ]
  });
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  useEffect(() => {
    window.localStorage.setItem(QUEUE_KEY, JSON.stringify({
      schema: 1,
      entries: syncQueue.map((entry) => ({ ...entry, state: 'pending' }))
    }));
  }, [syncQueue]);

  const showToast = useCallback((message: string) => {
    setToastMessage(message);
    setTimeout(() => setToastMessage(null), 4000);
  }, []);

  const updateCaseStatus = (id: string, status: Case['status']) => {
    setCases((previous) => previous.map((item) => item.id === id ? { ...item, status } : item));
  };

  const addToSyncQueue = (item: Omit<SyncItem, 'id' | 'timestamp'>) => {
    const newItem: SyncItem = {
      ...item,
      id: Math.random().toString(36).slice(2, 11),
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };
    setSyncQueue((previous) => [...previous, newItem]);
  };

  const clearSyncQueue = () => setSyncQueue([]);
  const resolveConflict = (_keepMine: boolean) => setHasConflict(false);

  const addNote = (caseId: string, note: Omit<FieldNote, 'id' | 'timestamp' | 'author'>) => {
    const newNote: FieldNote = {
      ...note,
      id: Math.random().toString(36).slice(2, 11),
      author: 'Field Coordinator',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };
    setFieldNotes((previous) => ({
      ...previous,
      [caseId]: [newNote, ...(previous[caseId] || [])]
    }));
  };

  return (
    <AppContext.Provider value={{
      networkStatus, setNetworkStatus, cases, updateCaseStatus,
      syncQueue, addToSyncQueue, clearSyncQueue,
      hasConflict, resolveConflict,
      fieldNotes, addNote,
      toastMessage, showToast
    }}>
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => {
  const context = useContext(AppContext);
  if (!context) throw new Error('useAppContext must be used within AppProvider');
  return context;
};
