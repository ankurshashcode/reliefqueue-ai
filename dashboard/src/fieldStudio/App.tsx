/**
 * Native ReliefQueue Field Coordinator bridge.
 * This keeps the AI Studio screen components and state model, but uses a tiny local router
 * so the main ReliefQueue dashboard does not need react-router-dom as a hard runtime dependency.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AppProvider, useAppContext } from './contexts/AppContext';
import { NativeRouterProvider } from './routing';
import { FieldBottomNav } from './components/FieldBottomNav';
import { FieldOfflineBanner } from './components/FieldOfflineBanner';
import { FieldSignInScreen } from './screens/FieldSignInScreen';
import { FieldMyWorkScreen } from './screens/FieldMyWorkScreen';
import { FieldCaseListScreen } from './screens/FieldCaseListScreen';
import { FieldCaseDetailScreen } from './screens/FieldCaseDetailScreen';
import { FieldStatusUpdateScreen } from './screens/FieldStatusUpdateScreen';
import { FieldNoteScreen } from './screens/FieldNoteScreen';
import { FieldNewRequestScreen } from './screens/FieldNewRequestScreen';
import { FieldOutboxScreen } from './screens/FieldOutboxScreen';
import { FieldSyncConflictScreen } from './screens/FieldSyncConflictScreen';
import { FieldNetworkHelpScreen } from './screens/FieldNetworkHelpScreen';

function screenFor(path: unknown) {
  if (typeof path !== 'string' || path.length === 0) return '/field/my-work';
  if (path === '/' || path === '/field') return '/field/my-work';
  return path;
}

function FieldToast() {
  const { toastMessage } = useAppContext();
  if (!toastMessage) return null;
  return <div className="fixed bottom-24 left-1/2 z-[100] -translate-x-1/2 rounded-full bg-inverse-surface px-5 py-3 text-inverse-on-surface shadow-xl">{toastMessage}</div>;
}

function RoutedFieldApp({ initialPath }: { initialPath?: string }) {
  const [path, setPath] = useState<string>(screenFor(initialPath || window.location.pathname));

  const syncFromLocation = useCallback(() => {
    setPath(screenFor(window.location.pathname));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  useEffect(() => {
    window.addEventListener('popstate', syncFromLocation);
    return () => window.removeEventListener('popstate', syncFromLocation);
  }, [syncFromLocation]);

  const navigate = useCallback((to: string | number) => {
    if (typeof to === 'number') {
      window.history.go(to);
      return;
    }
    const next = screenFor(to);
    window.history.pushState({}, '', next);
    setPath(next);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [syncFromLocation]);

  const screen = useMemo(() => {
    if (path === '/field/sign-in') return <FieldSignInScreen />;
    if (path === '/field/my-work') return <FieldMyWorkScreen />;
    if (path === '/field/my-cases') return <FieldCaseListScreen />;
    if (/^\/field\/cases\/[^/]+\/status$/.test(path)) return <FieldStatusUpdateScreen />;
    if (/^\/field\/cases\/[^/]+\/note$/.test(path)) return <FieldNoteScreen />;
    if (/^\/field\/cases\/[^/]+$/.test(path)) return <FieldCaseDetailScreen />;
    if (path === '/field/new-request') return <FieldNewRequestScreen />;
    if (path === '/field/outbox') return <FieldOutboxScreen />;
    if (path === '/field/sync-conflicts') return <FieldSyncConflictScreen />;
    if (path === '/field/help') return <FieldNetworkHelpScreen />;
    return <FieldMyWorkScreen />;
  }, [path]);

  return (
    <NativeRouterProvider path={path} navigate={navigate}>
      <div className="min-h-screen bg-background font-sans text-on-background">
        <FieldOfflineBanner />
        <main id="field-main-content">{screen}</main>
        <FieldBottomNav />
        <FieldToast />
      </div>
    </NativeRouterProvider>
  );
}

export default function App({ initialPath }: { initialPath?: string }) {
  return (
    <AppProvider>
      <RoutedFieldApp initialPath={initialPath} />
    </AppProvider>
  );
}
