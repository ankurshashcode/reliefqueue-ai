import { useState } from 'react';
import { FieldTopNav } from '../components/FieldTopNav';
import { useAppContext } from '../contexts/AppContext';
import { Printer, RefreshCw } from 'lucide-react';
import { cn } from '../lib/utils';

export const FieldOutboxScreen = () => {
  const { syncQueue, networkStatus, clearSyncQueue, showToast } = useAppContext();
  const [syncOutcome, setSyncOutcome] = useState(
    'No sync attempt recorded in this browser session. Pending updates remain local until replay succeeds.'
  );

  const handleSync = async () => {
    const pendingCount = syncQueue.length;
    if (networkStatus === 'offline') {
      const message = `Sync not attempted: offline. ${pendingCount} pending update(s) remain safely stored locally.`;
      setSyncOutcome(message);
      showToast(message);
      return;
    }
    try {
      const response = await fetch('/api/product/field/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          worker_id: 'worker-alpha-boat',
          updates: syncQueue.map((item) => ({
            case_id: item.caseId,
            status: 'in_progress',
            note: `${item.type} replayed from local outbox`,
            idempotency_key: `field-sync-${item.id}`
          }))
        })
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const status = String(payload.status || 'complete');
      const conflictCount = Array.isArray(payload.conflicts) ? payload.conflicts.length : 0;
      clearSyncQueue();
      const message = conflictCount > 0
        ? `Sync ${status}: ${pendingCount} update(s) replayed with ${conflictCount} conflict(s). Coordinator review is required.`
        : `Sync ${status}: ${pendingCount} pending update(s) replayed. The local outbox is cleared and coordinator review is required.`;
      setSyncOutcome(message);
      showToast(message);
    } catch (error: any) {
      const message = `Sync failed safely: ${error.message}. ${pendingCount} pending update(s) remain stored locally for retry.`;
      setSyncOutcome(message);
      showToast(message);
    }
  };

  return (
    <div data-result-id="field.outbox" className="pt-16 pb-20 px-4 md:px-10 max-w-3xl mx-auto w-full flex flex-col h-screen" aria-live="polite">
      <FieldTopNav title="Offline Outbox" showBack={true} />

      <div className="my-6 flex flex-col h-full">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-on-background mb-2">Outbox</h1>
            <p className="text-lg text-on-surface-variant mb-2">Pending Sync updates are stored in localStorage schema 1. Do not clear app data while offline.</p>
            <p className="text-sm text-on-surface-variant mb-6">Offline mode disables network replay, avoiding repeated failed sync attempts until connectivity returns.</p>
          </div>
          <button onClick={() => window.print()} aria-label="Print pending field outbox" className="no-print shrink-0 h-11 px-3 bg-surface text-primary border-2 border-primary text-sm font-bold rounded-xl flex items-center justify-center gap-2 active:scale-[0.98] transition-transform shadow-sm">
            <Printer size={18} /> Print
          </button>
        </div>
        <section data-print-surface="outbox-pending-sync" className="print-only mb-4 rounded-lg border border-outline-variant bg-surface p-4">
          <h1 className="text-xl font-bold text-on-surface">Pending Sync / Outbox Sheet</h1>
          <p className="mt-1 text-sm text-on-surface-variant">Printed at: {new Date().toLocaleString()} | Network: {networkStatus} | Queued updates: {syncQueue.length}</p>
          <p className="mt-1 text-sm text-on-surface-variant">Offline-safe queueing avoids repeated failed network attempts. Coordinator review remains required after replay.</p>
        </section>

        <div className={cn('p-5 rounded-xl border-2 flex flex-col gap-3 shadow-sm', networkStatus === 'offline' ? 'bg-surface-container border-outline-variant' : 'bg-primary-fixed border-primary')}>
          <h2 className="text-xl font-bold text-on-surface">Sync Status</h2>
          <p className="text-base text-on-surface-variant font-bold">
            {networkStatus === 'offline' ? 'Currently offline. Updates remain pending locally.' : `Online. ${syncQueue.length} update(s) ready to sync.`}
          </p>
          <p
            data-sync-result-id="field.sync_pending_actions"
            className="rounded-lg border-2 border-outline-variant bg-surface px-4 py-3 text-sm font-bold text-on-surface"
            aria-live="polite"
          >
            {syncOutcome}
          </p>
          <button
            data-action-id="field.sync_pending_actions"
            onClick={handleSync}
            disabled={networkStatus === 'offline' || syncQueue.length === 0}
            className={cn('mt-3 w-full h-14 flex flex-col items-center justify-center rounded-xl border-2 font-bold transition-transform active:scale-95',
              networkStatus === 'offline' || syncQueue.length === 0 ? 'bg-surface-variant text-on-surface-variant border-outline-variant opacity-60 cursor-not-allowed' : 'bg-primary text-on-primary border-primary hover:bg-primary-container shadow-sm')}
          >
            <div className="flex items-center gap-2 text-lg"><RefreshCw size={20} />{networkStatus === 'offline' ? 'Sync All (Offline)' : 'Sync Now'}</div>
          </button>
        </div>

        <div className="mt-8 flex flex-col gap-3 flex-1 overflow-y-auto hide-scrollbar pb-8">
          <h3 className="text-sm font-bold text-on-surface-variant px-1 uppercase tracking-widest border-b-2 border-outline-variant pb-2 shrink-0">Queued Updates ({syncQueue.length})</h3>
          {syncQueue.length === 0 ? <p className="text-center py-8 text-lg font-bold text-on-surface-variant">No items in outbox. Sync complete.</p> : syncQueue.map((item) => (
            <div key={item.id} className="bg-surface p-5 rounded-xl border-2 border-outline-variant flex justify-between items-start shadow-sm shrink-0">
              <div className="flex flex-col gap-1"><span className="text-xl font-bold text-on-surface">{item.type}</span><span className="text-base text-on-surface-variant font-bold">{item.caseId}</span></div>
              <div className="flex flex-col items-end gap-2"><span className="bg-surface-variant text-on-surface-variant text-xs font-bold px-3 py-1.5 rounded border-2 border-outline-variant uppercase">Waiting to send</span><span className="text-sm font-bold text-outline">{item.timestamp}</span></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
