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
  Map as MapIcon,
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
    intake: 'command.nav_ai_intake',
    assignments: 'command.nav_assignments',
    sync: 'command.nav_field_sync',
    scenario: 'command.nav_scenario',
    aicontrol: 'command.nav_ai_control',
    quality: 'command.nav_quality',
    audit: 'command.nav_audit',
    amd: 'command.nav_amd_impact',
    capabilities: 'command.nav_capability_map'
  };

  const icons: Record<ViewState, React.ComponentType<{ className?: string }>> = {
    overview: LayoutDashboard,
    intake: Bot,
    links: Link2,
    map: MapIcon,
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

  const amdPriorityOrder: ViewState[] = ['amd', 'capabilities', 'aicontrol', 'intake'];
  const navigationById = new globalThis.Map(NAVIGATION.map((item) => [item.id, item]));
  const amdPriorityNavigation = amdPriorityOrder.flatMap((id) => {
    const item = navigationById.get(id);
    return item ? [item] : [];
  });
  const operationsNavigation = NAVIGATION.filter(
    (item) => !amdPriorityOrder.includes(item.id)
  );

  const renderNavigationItem = (item: (typeof NAVIGATION)[number]) => {
    const Icon = icons[item.id];
    const isActive = currentView === item.id;
    return (
      <button
        key={item.id}
        type="button"
        data-action-id={actionIds[item.id]}
        data-testid={`sidebar-nav-${item.id}`}
        data-nav-id={item.id}
        aria-current={isActive ? 'page' : undefined}
        onClick={() => { navigate(item.id); onClose(); }}
        className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-[13px] font-medium tracking-tight whitespace-nowrap transition-colors ${
          isActive
            ? 'bg-slate-800 text-white border-l-4 border-rq-primary'
            : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border-l-4 border-transparent'
        }`}
      >
        <Icon className={`w-[18px] h-[18px] flex-shrink-0 ${isActive ? 'text-rq-primary' : ''}`} />
        <span className="min-w-0 whitespace-nowrap">{item.label}</span>
      </button>
    );
  };

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-sm md:hidden"
          onClick={onClose}
        />
      )}
      <aside
        data-testid="command-sidebar"
        className={`fixed md:relative inset-y-0 left-0 z-50 w-64 md:w-56 bg-slate-900 flex-shrink-0 flex flex-col h-full border-r border-slate-800 transform transition-transform duration-200 ease-in-out ${isOpen ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0`}
      >
        <div className="h-16 flex items-center px-4 border-b border-slate-800">
          <ShieldAlert className="w-6 h-6 text-rq-primary mr-2.5" />
          <span className="font-semibold text-lg text-white tracking-wide">ReliefQueue</span>
        </div>

        <div
          className="px-3 py-4 flex-1 overflow-y-auto"
          data-testid="sidebar-navigation"
        >
          <section
            className="mb-5"
            data-testid="sidebar-priority-group"
            aria-labelledby="sidebar-priority-heading"
          >
            <div
              id="sidebar-priority-heading"
              className="mb-2 px-2.5 text-[11px] font-mono tracking-wider text-rq-primary uppercase"
            >
              AMD / vLLM Demo
            </div>
            <nav className="space-y-1" aria-label="AMD and AI demo navigation">
              {amdPriorityNavigation.map(renderNavigationItem)}
            </nav>
          </section>

          <section
            data-testid="sidebar-operations-group"
            aria-labelledby="sidebar-operations-heading"
          >
            <div
              id="sidebar-operations-heading"
              className="mb-2 px-2.5 text-[11px] font-mono tracking-wider text-slate-500 uppercase"
            >
              Operations
            </div>
            <nav className="space-y-1" aria-label="Command Center operations">
              {operationsNavigation.map(renderNavigationItem)}
            </nav>
          </section>
        </div>

        <div className="p-3 border-t border-slate-800">
          <div className="flex items-center gap-2.5 px-1 py-2">
            <div className="w-8 h-8 rounded-full bg-slate-700 flex-shrink-0 flex items-center justify-center text-white font-bold text-xs">
              CO
            </div>
            <div className="min-w-0 text-left">
              <div className="text-white text-[13px] font-medium leading-none whitespace-nowrap">Commander O.</div>
              <div className="text-slate-500 font-mono text-[10px] mt-1 uppercase">Auth Level 4</div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
