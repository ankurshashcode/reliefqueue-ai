import React from 'react';
import { NAVIGATION, ViewState } from '../types';
import {
  Bot,
  Briefcase,
  ClipboardList,
  Cpu,
  History,
  LayoutDashboard,
  Link2,
  Map,
  RefreshCw,
  Route,
  Server,
  ShieldAlert,
  ShieldCheck,
  Zap
} from 'lucide-react';
import { useApp } from '../context/AppContext';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const { currentView, navigate } = useApp();
  const actionIds: Partial<Record<ViewState, string>> = {
    overview: 'command.nav_overview',
    assignments: 'command.nav_assignments',
    sync: 'command.nav_field_sync',
    scenario: 'command.nav_scenario',
    aicontrol: 'command.nav_ai_control',
    quality: 'command.nav_quality',
    audit: 'command.nav_audit'
  };

  const icons: Record<ViewState, React.ComponentType<{ className?: string }>> = {
    overview: LayoutDashboard,
    intake: Bot,
    links: Link2,
    map: Map,
    assignments: ClipboardList,
    workload: Briefcase,
    sync: RefreshCw,
    scenario: Route,
    aicontrol: Cpu,
    quality: ShieldCheck,
    audit: History,
    amd: Zap,
    capabilities: Server
  };

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div 
          className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-sm md:hidden" 
          onClick={onClose} 
        />
      )}
      <aside className={`fixed md:relative inset-y-0 left-0 z-50 w-64 bg-slate-900 flex-shrink-0 flex flex-col h-full border-r border-slate-800 transform transition-transform duration-200 ease-in-out ${isOpen ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0`}>
        <div className="h-16 flex items-center px-6 border-b border-slate-800">
          <ShieldAlert className="w-6 h-6 text-rq-primary mr-3" />
          <span className="font-semibold text-lg text-white tracking-wide">ReliefQueue</span>
        </div>
        
        <div className="px-4 py-6 flex-1 overflow-y-auto">
          <div className="mb-2 px-3 text-xs font-mono tracking-wider text-slate-500 uppercase">
            Command Center
          </div>
          <nav className="space-y-1 mt-4">
            {NAVIGATION.map((item) => {
              const Icon = icons[item.id];
              const isActive = currentView === item.id;
              return (
                <button
                  key={item.id}
                  data-action-id={actionIds[item.id]}
                  onClick={() => { navigate(item.id); onClose(); }}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive 
                      ? 'bg-slate-800 text-white border-l-4 border-rq-primary' 
                      : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border-l-4 border-transparent'
                  }`}
                >
                  <Icon className={`w-5 h-5 ${isActive ? 'text-rq-primary' : ''}`} />
                  {item.label}
                </button>
              );
            })}
          </nav>
        </div>

        <div className="p-4 border-t border-slate-800">
          <div className="flex items-center gap-3 px-2 py-2">
            <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-white font-bold text-xs">
              CO
            </div>
            <div className="text-left">
              <div className="text-white text-sm font-medium leading-none">Commander O.</div>
              <div className="text-slate-500 font-mono text-[10px] mt-1 uppercase">Auth Level 4</div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
