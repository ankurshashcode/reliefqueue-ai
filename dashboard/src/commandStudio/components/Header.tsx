import React from 'react';
import { Bell, Plus, Settings, AlertTriangle, Database, Menu, Terminal } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { ProductRoleSwitcher } from '../../components/ProductRoleSwitcher';

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const { setLogOpen, showToast, addLog } = useApp();

  const handleNewIntake = () => {
    addLog('New Intake Initiated', 'Opened new crisis intake form (demo).');
    showToast('New Intake form opened.', 'info');
  };

  return (
    <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-4 md:px-6 flex-shrink-0 z-10 shadow-sm relative">
      <div className="flex items-center gap-3 md:gap-4">
        <button onClick={onMenuClick} aria-label="Open Command Center navigation" className="md:hidden text-slate-500 hover:text-slate-700 p-1 rounded-md hover:bg-slate-100 transition-colors">
          <Menu className="w-6 h-6" />
        </button>
        <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-rq-amber-light text-rq-amber rounded-md border border-rq-amber/20">
          <AlertTriangle className="w-4 h-4" />
          <span className="font-mono text-xs font-semibold uppercase tracking-wider">AI Advisory Only</span>
        </div>
        <div className="hidden lg:flex items-center gap-2 px-3 py-1.5 bg-slate-100 text-slate-600 rounded-md border border-slate-200">
          <Database className="w-4 h-4" />
          <span className="font-mono text-xs font-semibold uppercase tracking-wider">Mock GPS / Demo Data</span>
        </div>
      </div>

      <div className="flex items-center gap-2 md:gap-4">
        <ProductRoleSwitcher currentRole="command" compact />
        <div className="text-right mr-2 md:mr-4 hidden lg:block">
          <div className="text-xs font-medium text-slate-500">System Status</div>
          <div className="text-sm font-semibold text-rq-emerald">Nominal</div>
        </div>
        <button onClick={handleNewIntake} className="bg-rq-primary hover:bg-rq-primary-hover text-white px-3 py-1.5 md:px-4 md:py-2 rounded-md text-sm font-medium flex items-center gap-2 transition-colors shadow-sm">
          <Plus className="w-4 h-4" />
          <span className="hidden sm:inline">New Intake</span>
        </button>
        <div className="h-6 w-px bg-slate-200 mx-1 md:mx-2"></div>
        <button onClick={() => setLogOpen(true)} aria-label="View action log" className="text-slate-400 hover:text-rq-primary transition-colors flex items-center gap-1 bg-slate-50 px-2 py-1.5 rounded border border-slate-200" title="View Action Log">
          <Terminal className="w-4 h-4" />
          <span className="text-[10px] font-mono font-bold hidden sm:inline">LOGS</span>
        </button>
        <button onClick={() => showToast('Settings opened (demo)', 'info')} aria-label="Open demo settings" className="text-slate-400 hover:text-slate-600 transition-colors p-1.5">
          <Settings className="w-5 h-5" />
        </button>
      </div>
    </header>
  );
}
