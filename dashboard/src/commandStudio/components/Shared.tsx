import React from 'react';
import { useApp } from '../context/AppContext';
import { X, Info, CheckCircle, AlertTriangle, AlertCircle, Terminal } from 'lucide-react';

export function ToastContainer() {
  const { toasts, removeToast } = useApp();
  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
      {toasts.map(t => (
        <div key={t.id} className={`pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg border w-80 sm:w-96
          ${t.type === 'error' ? 'bg-red-50 border-red-200 text-red-800' :
            t.type === 'warning' ? 'bg-amber-50 border-amber-200 text-amber-800' :
            t.type === 'success' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' :
            'bg-white border-slate-200 text-slate-800'}`}
        >
          {t.type === 'error' && <AlertCircle className="w-5 h-5 shrink-0" />}
          {t.type === 'warning' && <AlertTriangle className="w-5 h-5 shrink-0" />}
          {t.type === 'success' && <CheckCircle className="w-5 h-5 shrink-0" />}
          {t.type === 'info' && <Info className="w-5 h-5 shrink-0" />}
          <div className="flex-1 text-sm font-medium">{t.message}</div>
          <button onClick={() => removeToast(t.id)} className="shrink-0 opacity-50 hover:opacity-100"><X className="w-4 h-4"/></button>
        </div>
      ))}
    </div>
  );
}

export function ActionLogPanel() {
  const { logs, isLogOpen, setLogOpen } = useApp();
  
  if (!isLogOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-full sm:w-80 bg-white border-l border-slate-200 shadow-2xl z-[90] flex flex-col">
      <div className="p-4 border-b border-slate-200 bg-slate-50 flex justify-between items-center">
        <h3 className="font-bold text-slate-900 flex items-center gap-2"><Terminal className="w-4 h-4"/> Demo Action Log</h3>
        <button onClick={() => setLogOpen(false)} className="p-1 hover:bg-slate-200 rounded text-slate-500"><X className="w-5 h-5"/></button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-50/50">
        {logs.length === 0 && <div className="text-sm text-slate-500 text-center mt-10">No actions logged yet.</div>}
        {logs.map(log => (
          <div key={log.id} className="bg-white border border-slate-200 p-3 rounded-lg shadow-sm text-sm">
            <div className="text-[10px] font-mono text-slate-400 mb-1">{log.timestamp}</div>
            <div className="font-semibold text-slate-800">{log.action}</div>
            {log.details && <div className="text-slate-600 mt-1 text-xs">{log.details}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function DetailDrawer({ isOpen, onClose, title, children }: any) {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white w-full md:w-[450px] lg:w-[500px] h-full flex flex-col shadow-2xl">
        <div className="p-4 md:p-6 border-b border-slate-200 flex justify-between items-center bg-slate-50 shrink-0">
          <h3 className="font-bold text-lg text-slate-900">{title}</h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full text-slate-500 transition-colors"><X className="w-5 h-5"/></button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 md:p-6 bg-slate-50/30">
          {children}
        </div>
      </div>
    </div>
  );
}
