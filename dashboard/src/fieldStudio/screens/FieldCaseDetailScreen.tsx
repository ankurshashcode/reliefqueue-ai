import { useState } from 'react';
import { Link, useParams } from '../routing';
import { FieldTopNav } from '../components/FieldTopNav';
import { useAppContext } from '../contexts/AppContext';
import { AlertTriangle, MapPin, ClipboardList, Stethoscope, Clock, FileEdit, RefreshCcw, Printer } from 'lucide-react';
import { FieldOfflineBanner } from '../components/FieldOfflineBanner';

function idempotencyKey(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function postField(endpoint: string, payload: Record<string, unknown>) {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export const FieldCaseDetailScreen = () => {
  const { id } = useParams<{ id: string }>();
  const { cases, networkStatus, showToast, fieldNotes, addNote, addToSyncQueue, updateCaseStatus, syncQueue } = useAppContext();
  const [actionResult, setActionResult] = useState('No field action has been recorded in this browser session.');
  const caseData = cases.find((item) => item.id === id) || cases[0];
  const caseNotes = fieldNotes[caseData.id] || [];

  const runStatusAction = async (label: string, status: any, note: string) => {
    try {
      const result = await postField('/api/product/field/action', {
        action: 'status',
        case_id: caseData.id,
        worker_id: 'worker-alpha-boat',
        status,
        note,
        idempotency_key: idempotencyKey(label.toLowerCase().replace(/\s+/g, '-'))
      });
      updateCaseStatus(caseData.id, status === 'needs_assistance' ? 'Needs Assistance' : status === 'complete' ? 'Complete' : status === 'acknowledged' ? 'Pending' : 'In Progress');
      addToSyncQueue({ type: 'Status Update', caseId: caseData.id, details: { label, status, note } });
      const message = `${label} recorded for ${caseData.id}; ${result.status || 'updated'} and queued for coordinator-safe sync.`;
      setActionResult(message);
      showToast(message);
    } catch (error: any) {
      const message = `${label} could not reach the local API: ${error.message}. The action remains available for retry.`;
      setActionResult(message);
      showToast(message);
    }
  };

  const addQuickNote = async () => {
    const text = 'Quick field note: situation checked; coordinator follow-up required.';
    try {
      await postField('/api/product/field/action', {
        action: 'status',
        case_id: caseData.id,
        worker_id: 'worker-alpha-boat',
        status: 'in_progress',
        note: text,
        idempotency_key: idempotencyKey('field-note')
      });
    } catch {
      // The local queue remains authoritative when the API is temporarily unavailable.
    }
    addNote(caseData.id, { type: 'General Note', text });
    addToSyncQueue({ type: 'Field Note', caseId: caseData.id, details: { text } });
    const message = `Field note for ${caseData.id} saved in localStorage schema 1 with pending sync state.`;
    setActionResult(message);
    showToast(message);
  };

  const addEvidenceMetadata = async () => {
    try {
      const result = await postField('/api/product/field/action', {
        action: 'evidence',
        case_id: caseData.id,
        worker_id: 'worker-alpha-boat',
        metadata: {
          media_type: 'text/plain',
          file_name: `${caseData.id}-field-note.txt`,
          file_base64: btoa('Synthetic field evidence metadata for demo validation.')
        },
        idempotency_key: idempotencyKey('field-evidence')
      });
      addToSyncQueue({ type: 'Evidence Metadata', caseId: caseData.id, details: { status: result.status || 'stored' } });
      const message = `Evidence metadata for ${caseData.id} stored without exposing private binary content.`;
      setActionResult(message);
      showToast(message);
    } catch (error: any) {
      const message = `Evidence metadata remains local for retry: ${error.message}`;
      setActionResult(message);
      showToast(message);
    }
  };

  return (
    <div data-result-id="field.detail" className="pt-16 pb-24 px-4 md:px-10 max-w-4xl mx-auto w-full flex flex-col gap-2" aria-live="polite">
      <FieldTopNav title={`Case ${caseData.id}`} showBack={true} backActionId="field.back_to_case_list" backTo="/field/my-cases" />

      {networkStatus === 'offline' && <FieldOfflineBanner className="mt-4 mb-2" />}

      <section data-print-surface="field-case-sheet" className="print-only mt-4 rounded-lg border border-outline-variant bg-surface p-4">
        <h1 className="text-2xl font-bold text-on-surface">Field Case Sheet: {caseData.id}</h1>
        <p className="mt-1 text-sm text-on-surface-variant">Printed at: {new Date().toLocaleString()} | Status: {caseData.status} | Zone: {caseData.zone}</p>
        <p className="mt-1 text-sm text-on-surface-variant">Safe field-coordination context only. Raw private intake text, credentials, and provider secrets are excluded.</p>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        <div className="bg-surface-container-high p-5 rounded-xl border-2 border-error flex flex-col justify-between min-h-[140px]">
          <div className="flex justify-between items-start mb-2">
            <div className="flex flex-col gap-2">
              <span className="text-sm text-error uppercase font-bold tracking-widest">{caseData.priority} PRIORITY</span>
              <div className="flex flex-wrap gap-2 mt-1">
                {caseData.vulnerabilityFlag && <span className="text-xs bg-error-container text-on-error-container px-2 py-1 rounded-full border border-error font-bold">{caseData.vulnerabilityFlag}</span>}
                <span className="text-xs bg-primary-container text-on-primary-container px-2 py-1 rounded-full border border-primary font-bold">{caseData.needType}</span>
                <span className="text-xs bg-surface-variant text-on-surface-variant px-2 py-1 rounded-full border border-outline-variant font-bold">{caseData.peopleCount} person(s)</span>
              </div>
            </div>
            <AlertTriangle className="text-error" size={32} />
          </div>
          <div className="mt-4">
            <h2 className="text-2xl font-bold text-on-surface mb-2">{caseData.title}</h2>
            <p className="text-lg text-on-surface-variant mb-4">Current Status: <strong>{caseData.status}</strong></p>
            <button onClick={() => showToast('Masked coordinator relay is demo-only in this prototype.')} className="w-full h-12 bg-surface text-on-surface text-base rounded-lg border-2 border-outline-variant font-bold">Contact via Coordinator</button>
          </div>
        </div>

        <div className="bg-surface-container-high p-5 rounded-xl border-2 border-outline-variant flex flex-col min-h-[140px]">
          <div className="flex items-center gap-2 mb-3"><MapPin className="text-primary" size={20} /><span className="text-sm text-primary uppercase font-bold tracking-widest">Location</span></div>
          <h3 className="text-xl font-bold text-on-surface mb-2">{caseData.landmarkClue}</h3>
          <p className="text-base text-on-surface-variant font-bold">Zone: {caseData.zone}</p>
          <p className="text-base text-on-surface-variant">Confidence: {caseData.locationConfidence}</p>
        </div>
      </section>

      {caseData.coordinatorInstruction && (
        <section className="bg-primary-container text-on-primary-container p-5 rounded-xl border-2 border-primary mt-2 shadow-sm">
          <div className="flex items-center gap-2 mb-3"><ClipboardList size={24} /><h3 className="text-xl font-bold">Coordinator Instructions</h3></div>
          <p className="text-lg leading-relaxed">{caseData.coordinatorInstruction}</p>
        </section>
      )}

      <section className="bg-surface p-5 rounded-xl border-2 border-outline-variant mt-2 shadow-sm">
        <div className="flex items-center gap-2 border-b-2 border-outline-variant pb-3 mb-3"><Stethoscope className="text-on-surface-variant" size={24} /><h3 className="text-xl font-bold text-on-surface">Needs</h3></div>
        <div className="flex flex-col gap-3">{caseData.safeNeedLabels.map((need, index) => <div key={need} className={`p-3 rounded-xl border-2 ${index === 0 ? 'bg-error-container border-error' : 'bg-surface-container border-outline-variant'}`}><span className="text-lg font-bold">{need}</span></div>)}</div>
      </section>

      <section className="bg-white p-5 rounded-xl border-2 border-primary mt-2 shadow-sm">
        <h3 className="text-xl font-bold text-on-surface mb-3">Field Action Controls</h3>
        <p className="text-sm text-on-surface-variant mb-4">Actions are advisory/operational records and remain subject to coordinator review.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button data-action-id="field.acknowledge_assignment" onClick={() => runStatusAction('Assignment acknowledged', 'acknowledged', 'Field coordinator acknowledged assignment.')} className="h-12 rounded-lg bg-primary text-on-primary font-bold">Acknowledge assignment</button>
          <button data-action-id="field.start_or_accept_work" onClick={() => runStatusAction('Work started', 'in_progress', 'Field coordinator accepted and started work.')} className="h-12 rounded-lg bg-primary text-on-primary font-bold">Start work</button>
          <button data-action-id="field.add_note" onClick={addQuickNote} className="h-12 rounded-lg border-2 border-primary text-primary font-bold">Add Note</button>
          <button data-action-id="field.add_evidence_metadata" onClick={addEvidenceMetadata} className="h-12 rounded-lg border-2 border-primary text-primary font-bold">Add evidence metadata</button>
          <button data-action-id="field.mark_complete_or_delivered" onClick={() => runStatusAction('Marked complete', 'complete', 'Delivery/work completion recorded.')} className="h-12 rounded-lg bg-tertiary-container text-on-tertiary-container font-bold">Mark complete</button>
          <button data-action-id="field.mark_blocked_or_needs_help" onClick={() => runStatusAction('Needs assistance', 'needs_assistance', 'Blocked route or help request recorded.')} className="h-12 rounded-lg bg-secondary-container text-on-secondary-container font-bold">Blocked / needs help</button>
          <Link data-action-id="field.review_outbox" to="/field/outbox" className="h-12 rounded-lg bg-surface-container text-primary border-2 border-primary font-bold flex items-center justify-center">Review outbox</Link>
          <button data-action-id="field.paid_call_disabled" type="button" disabled className="h-12 rounded-lg bg-surface-variant text-on-surface-variant border-2 border-outline-variant font-bold cursor-not-allowed">Paid call provider disabled</button>
        </div>
        <div data-result-id="field.action-log" className="mt-4 rounded-lg bg-surface-container p-4 border border-outline-variant text-sm font-bold">{actionResult}</div>
        <div data-result-id="field.outbox" className="mt-3 rounded-lg bg-surface-container-low p-4 border border-outline-variant text-sm">localStorage schema 1: {syncQueue.length} pending outbox update(s).</div>
        <div data-result-id="field.paid-call" className="mt-3 rounded-lg bg-surface-container-low p-4 border border-outline-variant text-sm">Paid phone/call integration is disabled until an external provider is configured; existing radio/phone protocols remain authoritative.</div>
      </section>

      <button
        onClick={() => window.print()}
        aria-label={`Print field case sheet for ${caseData.id}`}
        className="no-print h-12 bg-surface text-primary border-2 border-primary text-base font-bold rounded-xl flex items-center justify-center gap-2 active:scale-[0.98] transition-transform shadow-sm"
      >
        <Printer size={20} />
        Print Case Sheet
      </button>

      <section className="bg-surface p-5 rounded-xl border-2 border-outline-variant mt-2 flex-1 shadow-sm mb-4">
        <div className="flex items-center gap-2 border-b-2 border-outline-variant pb-3 mb-3"><Clock className="text-on-surface-variant" size={24} /><h3 className="text-xl font-bold text-on-surface">Notes from last check-in</h3></div>
        <div className="flex flex-col gap-3">{caseNotes.length > 0 ? caseNotes.map((note) => <div key={note.id} className="bg-surface-container-low p-4 rounded-xl border-2 border-outline-variant"><div className="flex justify-between mb-2"><span className="text-sm font-bold">{note.timestamp}</span><span className="text-xs font-bold">By: {note.author}</span></div><p className="text-lg">{note.text}</p></div>) : <p className="italic">No field notes yet.</p>}</div>
      </section>

      <div className="fixed bottom-0 left-0 w-full p-4 bg-surface border-t-2 border-outline-variant shadow-md z-40 md:relative md:bg-transparent md:border-none md:shadow-none md:p-0 md:mt-4 flex gap-3">
        <Link to={`/field/cases/${caseData.id}/note`} className="flex-1 h-16 bg-surface text-primary border-2 border-primary text-lg font-bold rounded-xl flex items-center justify-center gap-2"><FileEdit size={24} />Detailed Note</Link>
        <Link to={`/field/cases/${caseData.id}/status`} className="flex-[2] h-16 bg-primary text-on-primary text-lg font-bold rounded-xl flex items-center justify-center gap-2"><RefreshCcw size={24} />Detailed Status</Link>
      </div>
    </div>
  );
};
