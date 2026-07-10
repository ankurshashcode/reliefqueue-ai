import React from 'react';
import { createRoot } from 'react-dom/client';
import './aiStudioTailwind.css';
import './visualApps.css';

const CommandStudioApp = React.lazy(() => import('./commandStudio/App'));
const FieldStudioApp = React.lazy(() => import('./fieldStudio/App'));
const LocalCoordinatorApp = React.lazy(() => import('./localStudio/App'));

const commandRouteToView: Record<string, string> = {
  '/': 'overview',
  '/dashboard': 'overview',
  '/dashboard/overview': 'overview',
  '/dashboard/map': 'map',
  '/dashboard/assignments': 'assignments',
  '/dashboard/workload': 'workload',
  '/dashboard/field-sync': 'sync',
  '/dashboard/scenario': 'scenario',
  '/dashboard/ai-control': 'aicontrol',
  '/dashboard/ai-control/test': 'aicontrol',
  '/dashboard/ai-control/confirm-change': 'aicontrol',
  '/dashboard/quality': 'quality',
  '/dashboard/audit': 'audit',
  '/dashboard/troubleshooting': 'audit',
  '/dashboard/intake': 'intake',
  '/dashboard/incident-links': 'links',
  '/dashboard/amd-impact': 'amd',
  '/dashboard/capability-map': 'capabilities',
  '/internal/classic-dashboard': 'overview',
  '/internal/classic-dashboard?source=latest': 'overview'
};

function routeLabel(path: string) {
  if (path.startsWith('/field')) return 'Field Coordinator mobile app';
  if (path.includes('amd-impact')) return 'AMD Impact';
  if (path.includes('capability-map')) return 'Capability Map';
  if (path.includes('assignments')) return 'Assignments';
  if (path.includes('field-sync')) return 'Field Sync';
  if (path.includes('map')) return 'Live Map';
  return 'Operations Overview';
}

function LoadingShell() {
  const label = routeLabel(window.location.pathname);
  return (
    <main className="min-h-screen bg-slate-950 text-white p-8 font-sans" data-testid="native-loading-shell">
      <div className="mx-auto max-w-5xl rounded-2xl border border-slate-700 bg-slate-900 p-8 shadow-2xl">
        <p className="text-sm uppercase tracking-[0.3em] text-cyan-300">ReliefQueue AI</p>
        <h1 className="mt-3 text-3xl font-bold">Loading {label}</h1>
        <p className="mt-4 text-slate-300">
          Preparing the role-scoped ReliefQueue interface. If startup fails, a visible error panel will replace this screen instead of leaving a blank page.
        </p>
      </div>
    </main>
  );
}

function RuntimeErrorPanel({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  const stack = error instanceof Error && error.stack ? error.stack : '';
  return (
    <main className="min-h-screen bg-red-950 text-white p-8 font-sans" data-testid="native-runtime-error">
      <div className="mx-auto max-w-5xl rounded-2xl border border-red-500 bg-red-900/70 p-8 shadow-2xl">
        <p className="text-sm uppercase tracking-[0.3em] text-red-200">ReliefQueue AI runtime bridge</p>
        <h1 className="mt-3 text-3xl font-bold">Native AI Studio app failed to render</h1>
        <p className="mt-4 text-red-100">
          The dashboard is not hiding this failure behind a blank page. Copy this message back for repair.
        </p>
        <pre className="mt-6 max-h-[50vh] overflow-auto rounded-xl bg-black/40 p-4 text-sm text-red-50 whitespace-pre-wrap">{message}{stack ? `\n\n${stack}` : ''}</pre>
      </div>
    </main>
  );
}

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: unknown }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: unknown) {
    return { error };
  }
  componentDidCatch(error: unknown) {
    console.error('ReliefQueue native AI Studio render error', error);
  }
  render() {
    if (this.state.error) return <RuntimeErrorPanel error={this.state.error} />;
    return this.props.children;
  }
}

function StaticTailwindProbe() {
  return (
    <div
      aria-hidden="true"
      data-testid="rq-static-tailwind-probe"
      className="rq-static-tailwind-probe flex bg-slate-900 text-white p-4 rounded-xl gap-2"
    >
      rq-tailwind-style-probe
    </div>
  );
}

function RootApp() {
  const path = window.location.pathname;
  if (path.startsWith('/field')) {
    return (
      <React.Suspense fallback={<LoadingShell />}>
        <FieldStudioApp initialPath={path} />
      </React.Suspense>
    );
  }
  if (path.startsWith('/local-coordinator')) {
    return (
      <React.Suspense fallback={<LoadingShell />}>
        <LocalCoordinatorApp />
      </React.Suspense>
    );
  }
  const initialView = commandRouteToView[path] || 'overview';
  const internalClassic = path.startsWith('/internal/classic-dashboard');
  return (
    <React.Suspense fallback={<LoadingShell />}>
      {internalClassic && (
        <section
          data-action-id="internal.classic_dashboard_debug_notice"
          data-result-id="internal.debug-notice"
          className="border-b border-amber-300 bg-amber-50 px-6 py-3 text-sm font-semibold text-amber-900"
        >
          Classic Dashboard Debug View — internal engineering comparison only; this route is not the primary ReliefQueue product surface.
        </section>
      )}
      <CommandStudioApp initialView={initialView as any} />
    </React.Suspense>
  );
}

const rootElement = document.getElementById('root');
if (!rootElement) {
  document.body.innerHTML = '<main style="padding:2rem;font-family:sans-serif"><h1>ReliefQueue AI root element missing</h1></main>';
  throw new Error('Missing #root element');
}

createRoot(rootElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <StaticTailwindProbe />
      <RootApp />
    </ErrorBoundary>
  </React.StrictMode>
);
