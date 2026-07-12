import React, { Suspense, lazy, useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { AppProvider, useApp } from './context/AppContext';
import { ToastContainer, ActionLogPanel } from './components/Shared';

const Overview = lazy(() => import('./views/Overview').then((module) => ({ default: module.Overview })));
const LiveMap = lazy(() => import('./views/LiveMap').then((module) => ({ default: module.LiveMap })));
const Assignments = lazy(() => import('./views/Assignments').then((module) => ({ default: module.Assignments })));
const Workload = lazy(() => import('./views/Workload').then((module) => ({ default: module.Workload })));
const FieldSync = lazy(() => import('./views/FieldSync').then((module) => ({ default: module.FieldSync })));
const Scenario = lazy(() => import('./views/Scenario').then((module) => ({ default: module.Scenario })));
const AIControl = lazy(() => import('./views/AIControl').then((module) => ({ default: module.AIControl })));
const Quality = lazy(() => import('./views/Quality').then((module) => ({ default: module.Quality })));
const Audit = lazy(() => import('./views/Audit').then((module) => ({ default: module.Audit })));
const IntakeFusion = lazy(() => import('./views/IntakeFusion').then((module) => ({ default: module.IntakeFusion })));
const IncidentLinks = lazy(() => import('./views/IncidentLinks').then((module) => ({ default: module.IncidentLinks })));
const AmdImpact = lazy(() => import('./views/AmdImpact').then((module) => ({ default: module.AmdImpact })));
const CapabilityMap = lazy(() => import('./views/CapabilityMap').then((module) => ({ default: module.CapabilityMap })));

function ViewLoading() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center text-sm font-semibold text-slate-500">
      Loading operational screen...
    </div>
  );
}

function MainLayout() {
  const { currentView } = useApp();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const renderView = () => {
    switch (currentView) {
      case 'overview': return <Overview />;
      case 'map': return <LiveMap />;
      case 'assignments': return <Assignments />;
      case 'workload': return <Workload />;
      case 'sync': return <FieldSync />;
      case 'scenario': return <Scenario />;
      case 'aicontrol': return <AIControl />;
      case 'quality': return <Quality />;
      case 'audit': return <Audit />;
      case 'intake': return <IntakeFusion />;
      case 'links': return <IncidentLinks />;
      case 'amd': return <AmdImpact />;
      case 'capabilities': return <CapabilityMap />;
      default: return <Overview />;
    }
  };

  return (
    <div className="flex h-screen w-full bg-slate-50 overflow-hidden font-sans text-slate-900">
      <Sidebar
        isOpen={isMobileMenuOpen}
        onClose={() => setIsMobileMenuOpen(false)}
      />
      <div className="flex-1 flex flex-col h-full relative min-w-0 overflow-hidden">
        <Header onMenuClick={() => setIsMobileMenuOpen(true)} />
        <main className="flex-1 flex flex-col min-h-0 relative">
          {/* Inference Mode Banner */}
          <div className="w-full bg-slate-900 border-b border-slate-800 px-4 py-2 flex items-center justify-center gap-2 shrink-0 z-10 relative">
            <span className="text-slate-200 text-xs font-mono font-medium text-center leading-tight">
              Synthetic flood-response replay <span className="text-slate-500 mx-2">|</span>
              <span className="text-blue-300">AMD/vLLM evidence available</span> <span className="text-slate-500 mx-2">|</span>
              <span className="text-emerald-400">Live status verified per request</span> <span className="text-slate-500 mx-2">|</span>
              <span className="text-amber-400">Coordinator approval required</span>
            </span>
          </div>
          <div
            className="flex-1 min-h-0 relative overflow-y-auto"
            data-result-id="command.active-panel"
            data-active-view={currentView}
            aria-live="polite"
          >
            <Suspense fallback={<ViewLoading />}>
              {renderView()}
            </Suspense>
          </div>
        </main>
      </div>
      <ToastContainer />
      <ActionLogPanel />
    </div>
  );
}

export default function App({ initialView = 'overview' }: { initialView?: any }) {
  return (
    <AppProvider initialView={initialView}>
      <MainLayout />
    </AppProvider>
  );
}
