import React, { useEffect, useState } from 'react';
import { AlertTriangle, Clock, Bot, Printer } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { DetailDrawer } from '../components/Shared';
import { AIAdvisoryDrawer } from '../components/AIAdvisoryDrawer';
import { actionKey, postProduct } from '../lib/productActions';

type Task = {
  id: string;
  status: string;
  title: string;
  meta: string;
  time?: string;
  urgent?: boolean;
  aiSuggestion?: string;
  aiConf?: string;
  reviewNeeded?: boolean;
  reason?: string;
  errorMsg?: string;
  active?: boolean;
  assignedTo?: string;
  timeSince?: string;
};

const INITIAL_TASKS: Task[] = [
  { id: 'RQ-1042', status: 'Unassigned', title: 'Med-Evac Coord Route B', meta: 'Zone 4 • Multiple Casualties', time: 'T-12M', urgent: true, aiSuggestion: 'Alpha Team (ETA 4m)', aiConf: '94%' },
  { id: 'RQ-1077', status: 'Unassigned', title: 'Supply Drop MREs', meta: 'Sector 7 • Staging Area', time: 'T-45M', urgent: false, aiSuggestion: 'Logistics Unit 3', aiConf: '72%' },
  { id: 'RQ-1105', status: 'Review Queue', title: 'Re-route Convoy 7', meta: 'Bridge out on Route A', urgent: true, reviewNeeded: true, reason: 'Auto-route failed: Obstruction\nReq: Human validation for Route C' },
  { id: 'RQ-1120', status: 'Assignment Suggested', title: 'Water Purification Deployment', meta: 'Sector 2 River', urgent: true, errorMsg: 'Missing equipment clearance docs.' },
  { id: 'RQ-1132', status: 'In Progress', title: 'Generator Setup', meta: 'Field Hospital Alpha', active: true, assignedTo: 'Tech Unit 2', timeSince: '15m ago' }
];

export function Assignments() {
  const { addLog, showToast } = useApp();
  const [tasks, setTasks] = useState<Task[]>(INITIAL_TASKS);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [advisoryOpen, setAdvisoryOpen] = useState(false);
  const [advisoryData, setAdvisoryData] = useState<any>(null);
  const [assignmentResult, setAssignmentResult] = useState('No assignment mutation has been requested.');
  const [statusResult, setStatusResult] = useState('No status mutation has been requested.');
  const [messageResult, setMessageResult] = useState('Local/mock outbox is ready; no message has been queued.');
  const [walkthroughNotice, setWalkthroughNotice] = useState<string | null>(null);

  const selectedTask = tasks.find((task) => task.id === selectedTaskId);

  useEffect(() => {
    const raw = window.sessionStorage.getItem('reliefqueue.walkthrough.assignment.v1');
    if (!raw) return;
    try {
      const handoff = JSON.parse(raw);
      const caseId = String(handoff?.case_id || 'RQ-1042');
      const task = INITIAL_TASKS.find(item => item.id === caseId);
      if (!task) return;
      const response = handoff?.advisory || {};
      setSelectedTaskId(caseId);
      setAdvisoryData({
        summary: response.summary || response.safe_summary || `Review ${caseId}.`,
        priority: task.urgent ? 'CRITICAL' : 'HIGH',
        needType: 'Logistics',
        locationConfidence: 'Medium',
        inferenceMode: 'Deterministic Local Advisory',
        providerStatus: 'Not contacted',
        latency: 'Local · no provider call',
        warnings: ['Coordinator approval required before any field action.'],
        questions: ['Confirm the latest field status before assignment.'],
      });
      setAdvisoryOpen(true);
      setWalkthroughNotice(`Walkthrough Step 2 handoff loaded: ${caseId} and its deterministic advisory are open for review.`);
      addLog('Walkthrough Assignment Handoff', `Opened ${caseId} deterministic advisory.`);
    } catch (error) {
      console.warn('Unable to restore walkthrough assignment handoff', error);
    } finally {
      window.sessionStorage.removeItem('reliefqueue.walkthrough.assignment.v1');
    }
  }, [addLog]);

  const getTasksByStatus = (status: string) => tasks.filter((task) => task.status === status);

  const openTask = (taskId: string) => {
    setSelectedTaskId(taskId);
    addLog('Case Detail Opened', `Opened ${taskId} for coordinator review.`);
  };

  const assignWorker = async () => {
    if (!selectedTask) return;
    const response: any = await postProduct<any>('/api/product/command/assign', {
      case_id: selectedTask.id,
      worker_id: 'worker-alpha-boat',
      actor_id: 'command-operator',
      idempotency_key: actionKey('assign')
    }, { status: 'assigned', case: { assigned_worker_id: 'worker-alpha-boat' } });
    setTasks((previous) => previous.map((task) => task.id === selectedTask.id
      ? { ...task, assignedTo: response.case?.assigned_worker_id || 'worker-alpha-boat', status: 'Assignment Suggested' }
      : task));
    const result = `${selectedTask.id} assignment suggestion recorded for ${response.case?.assigned_worker_id || 'worker-alpha-boat'}; coordinator approval required.`;
    setAssignmentResult(result);
    addLog('Assignment Suggestion Recorded', result);
    showToast('Assignment suggestion recorded.', 'success');
  };

  const setInProgress = async () => {
    if (!selectedTask) return;
    const response: any = await postProduct<any>('/api/product/command/status', {
      case_id: selectedTask.id,
      status: 'in_progress',
      actor_id: 'command-operator',
      note: 'Coordinator marked case in progress from Command Center.',
      idempotency_key: actionKey('status')
    }, { status: 'updated', case: { status: 'in_progress' } });
    setTasks((previous) => previous.map((task) => task.id === selectedTask.id
      ? { ...task, status: response.case?.status === 'in_progress' ? 'In Progress' : 'In Progress' }
      : task));
    const result = `${selectedTask.id} status updated to in progress and added to the audit timeline.`;
    setStatusResult(result);
    addLog('Case Status Updated', result);
    showToast('Case status updated.', 'success');
  };

  const queueMessage = async () => {
    if (!selectedTask) return;
    const response: any = await postProduct<any>('/api/product/command/message', {
      case_id: selectedTask.id,
      channel: 'sms',
      provider: 'local_mock',
      actor_id: 'command-operator',
      body: 'Local demo update queued for coordinator-reviewed delivery.',
      idempotency_key: actionKey('message')
    }, { status: 'queued', provider: 'local_mock', message_id: actionKey('local-message') });
    const result = `${selectedTask.id} message ${response.message_id || ''} queued in the local/mock outbox; paid providers remain disabled.`;
    setMessageResult(result);
    addLog('Local Message Queued', result);
    showToast('Message queued locally.', 'success');
  };

  const requestAdvisory = async () => {
    if (!selectedTask) return;
    const response: any = await postProduct<any>('/api/product/command/ai-advisory', {
      case_id: selectedTask.id,
      idempotency_key: actionKey('ai-advisory')
    }, {
      status: 'completed',
      summary: `Review ${selectedTask.id} with coordinator approval required.`,
      recommendation: 'Advisory only; do not dispatch automatically.',
      human_review_required: true,
      model_detail: 'deterministic local fallback'
    });
    setAdvisoryData({
      summary: response.summary || response.safe_summary || `Review ${selectedTask.id}.`,
      priority: selectedTask.urgent ? 'CRITICAL' : 'HIGH',
      needType: 'Logistics',
      locationConfidence: 'Medium',
      inferenceMode: 'Deterministic Local Advisory',
        providerStatus: 'Not contacted',
        latency: 'Local · no provider call',
      warnings: response.human_review_required ? ['Coordinator approval required before any field action.'] : [],
      questions: ['Confirm the latest field status before assignment.']
    });
    setAdvisoryOpen(true);
    addLog('Review-required AI Advisory', `${selectedTask.id} advisory returned with human review required.`);
  };

  const handleTaskAction = (action: string, taskId: string) => {
    addLog('Task Updated', `Action '${action}' applied to task ${taskId}`);
    showToast('Task action logged. Pending coordinator review.', 'success');
  };

  return (
    <div className="p-4 md:p-6 h-full flex flex-col overflow-hidden bg-slate-100">
      <div className="mb-6 flex justify-between items-end flex-shrink-0 gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900">Task Assignment Suggestions</h1>
          <p className="text-slate-500 mt-1 text-sm md:text-base">Review AI advisory triage and assignments. Coordinator approval required.</p>
          {walkthroughNotice && (
            <div data-testid="walkthrough-assignment-handoff" className="mt-3 rounded-lg border border-blue-300 bg-blue-50 px-4 py-3 text-sm font-semibold text-blue-900">
              {walkthroughNotice}
            </div>
          )}
        </div>
        <button onClick={() => window.print()} aria-label="Print assignment roster" className="no-print inline-flex items-center gap-2 rounded bg-white border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
          <Printer className="w-4 h-4" /> Print Roster
        </button>
      </div>

      <section data-print-surface="assignment-roster" className="print-only mb-4 rounded-lg border border-slate-300 bg-white p-4">
        <h1 className="text-xl font-bold">ReliefQueue Assignment Roster</h1>
        <p className="mt-1 text-sm">Printed at: {new Date().toLocaleString()} | Coordinator approval remains required for suggested assignments.</p>
        <ul className="mt-3 space-y-1 text-sm">
          {tasks.map(task => (
            <li key={task.id}><strong>{task.id} · {task.status}:</strong> {task.title} — {task.meta}{task.assignedTo ? ` — Assigned to ${task.assignedTo}` : ''}</li>
          ))}
        </ul>
      </section>

      <div className="no-print flex-1 flex gap-4 md:gap-6 overflow-x-auto pb-4 snap-x">
        <KanbanColumn title="Unassigned" count={getTasksByStatus('Unassigned').length}>
          {getTasksByStatus('Unassigned').map((task) => (
            <TaskCard key={task.id} task={task} onClick={() => openTask(task.id)} />
          ))}
        </KanbanColumn>

        <KanbanColumn title="Review Queue" count={getTasksByStatus('Review Queue').length}>
          {getTasksByStatus('Review Queue').map((task) => (
            <button key={task.id} type="button" onClick={() => openTask(task.id)} className="text-left bg-white border border-rq-amber border-t-4 rounded-lg shadow-sm p-4 cursor-pointer hover:shadow-md transition-shadow">
              <div className="flex items-center gap-2 text-rq-amber mb-2">
                <AlertTriangle className="w-4 h-4" />
                <span className="text-[10px] font-mono font-bold uppercase tracking-wider">Human Review Required</span>
              </div>
              <h4 className="font-semibold text-slate-900">{task.title}</h4>
              <p className="text-xs text-slate-500 mb-3">{task.meta}</p>
              <div className="bg-amber-50 p-3 rounded text-xs font-mono text-amber-800 border-l-2 border-rq-amber whitespace-pre-wrap">
                {task.reason?.split('\n').map((line, index) => <div key={index}>{`> ${line}`}</div>)}
              </div>
            </button>
          ))}
        </KanbanColumn>

        <KanbanColumn title="Assignment Suggested" count={getTasksByStatus('Assignment Suggested').length}>
          {getTasksByStatus('Assignment Suggested').map((task) => (
            <button key={task.id} type="button" onClick={() => openTask(task.id)} className="text-left bg-white border border-slate-200 border-l-4 border-l-rq-red rounded-lg shadow-sm p-4 cursor-pointer hover:shadow-md transition-shadow">
              <h4 className="font-semibold text-slate-900">{task.title}</h4>
              <p className="text-xs text-slate-500 mb-3">{task.meta}</p>
              {task.errorMsg && <div className="text-xs font-medium text-rq-red bg-red-50 p-2 rounded border border-red-100">{task.errorMsg}</div>}
            </button>
          ))}
        </KanbanColumn>

        <KanbanColumn title="In Progress" count={getTasksByStatus('In Progress').length}>
          {getTasksByStatus('In Progress').map((task) => (
            <button key={task.id} type="button" onClick={() => openTask(task.id)} className="text-left bg-white border border-slate-200 border-l-4 border-l-rq-emerald rounded-lg shadow-sm p-4 cursor-pointer hover:shadow-md transition-shadow">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <h4 className="font-semibold text-slate-900">{task.title}</h4>
                  <p className="text-xs text-slate-500">{task.meta}</p>
                </div>
                <span className="bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider">Active</span>
              </div>
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-100">
                <span className="text-xs font-bold text-slate-700">{task.assignedTo}</span>
                <span className="text-[10px] font-mono text-slate-500 flex items-center gap-1"><Clock className="w-3 h-3" /> {task.timeSince}</span>
              </div>
            </button>
          ))}
        </KanbanColumn>
      </div>

      <DetailDrawer isOpen={!!selectedTask} onClose={() => setSelectedTaskId(null)} title="Task Detail">
        {selectedTask && (
          <div data-result-id="command.case-detail" className="flex flex-col h-full gap-5" aria-live="polite">
            <div>
              <div className="inline-block bg-slate-100 text-slate-600 text-[10px] font-mono font-bold px-2 py-1 rounded uppercase tracking-wider mb-3">{selectedTask.status}</div>
              <h2 className="text-2xl font-bold text-slate-900">{selectedTask.id}: {selectedTask.title}</h2>
              <p className="text-sm text-slate-500 mt-1">{selectedTask.meta}</p>
              <p className="text-sm text-amber-700 mt-2 font-medium">Coordinator approval is required for all suggested actions.</p>
            </div>

            {selectedTask.aiSuggestion && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-center gap-2 text-rq-primary mb-2"><Bot className="w-5 h-5" /><span className="font-bold text-sm uppercase tracking-wide">AI Advisory Suggestion</span></div>
                <p className="text-slate-800 font-medium">{selectedTask.aiSuggestion}</p>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button data-action-id="command.assign_or_reassign_worker" type="button" onClick={assignWorker} className="py-3 rounded-lg bg-rq-primary text-white font-semibold">Assign Alpha</button>
              <button data-action-id="command.set_case_in_progress" type="button" onClick={setInProgress} className="py-3 rounded-lg bg-slate-900 text-white font-semibold">Set in progress</button>
              <button data-action-id="command.queue_local_message" type="button" onClick={queueMessage} className="py-3 rounded-lg border border-slate-300 bg-white text-slate-800 font-semibold">Queue message</button>
              <button data-action-id="command.request_review_required_ai_advisory" type="button" onClick={requestAdvisory} className="py-3 rounded-lg border border-emerald-500 bg-emerald-50 text-emerald-800 font-semibold">Run deterministic advisory</button>
              <button data-action-id="command.paid_sms_disabled" type="button" disabled className="sm:col-span-2 py-3 rounded-lg border border-slate-300 bg-slate-100 text-slate-500 font-semibold cursor-not-allowed">Paid SMS / WhatsApp provider disabled until configured</button>
            </div>

            <div className="space-y-2 text-sm">
              <div data-result-id="command.assignment" className="rounded border border-slate-200 bg-white p-3"><strong>Assignment</strong><p>{assignmentResult}</p></div>
              <div data-result-id="command.status" className="rounded border border-slate-200 bg-white p-3"><strong>Status timeline</strong><p>{statusResult}</p></div>
              <div data-result-id="command.message" className="rounded border border-slate-200 bg-white p-3"><strong>Local outbox</strong><p>{messageResult}</p></div>
              <div data-result-id="command.paid-sms" className="rounded border border-slate-200 bg-slate-50 p-3"><strong>Paid integration</strong><p>Disabled: local/mock outbox works, but paid SMS, WhatsApp, and call providers are not configured.</p></div>
            </div>

            <button type="button" onClick={() => handleTaskAction('Queue Coordinator Approval', selectedTask.id)} className="mt-auto w-full bg-rq-primary text-white font-semibold py-3 rounded-lg">Queue Coordinator Approval</button>
          </div>
        )}
      </DetailDrawer>

      {selectedTask && (
        <AIAdvisoryDrawer
          isOpen={advisoryOpen}
          onClose={() => setAdvisoryOpen(false)}
          caseId={selectedTask.id}
          data={advisoryData}
          resultId="command.ai"
        />
      )}
    </div>
  );
}

function KanbanColumn({ title, count, children }: any) {
  return (
    <div className="flex flex-col flex-shrink-0 w-[85vw] sm:w-[320px] md:w-[360px] bg-slate-50 border border-slate-200 rounded-xl overflow-hidden h-full snap-center">
      <div className="px-4 py-3 border-b border-slate-200 bg-white flex justify-between items-center shrink-0">
        <h3 className="font-semibold text-slate-900 flex items-center gap-2">{title}<span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full text-[10px] font-bold">{count}</span></h3>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-3 bg-slate-50/50">{children}</div>
    </div>
  );
}

function TaskCard({ task, onClick }: { task: Task; onClick: () => void }) {
  return (
    <button data-action-id="command.open_case_detail" type="button" onClick={onClick} className={`w-full text-left bg-white border rounded-lg shadow-sm p-4 cursor-pointer hover:shadow-md transition-shadow ${task.urgent ? 'border-l-4 border-l-rq-red border-y-slate-200 border-r-slate-200' : 'border-slate-200'}`}>
      <div className="flex justify-between items-start mb-2">
        <div className="bg-red-50 text-rq-red text-[8px] sm:text-[10px] font-mono font-bold px-2 py-1 rounded border border-red-100 w-max uppercase tracking-wider">Coordinator Approval Required</div>
        {task.time && <span className="bg-slate-100 text-slate-500 text-[10px] font-mono px-1.5 py-0.5 rounded">{task.time}</span>}
      </div>
      <div className="mb-3 mt-3">
        <h4 className="font-semibold text-slate-900 leading-tight text-sm sm:text-base">{task.title}</h4>
        <p className="text-xs text-slate-500 mt-1">{task.id} · {task.meta}</p>
      </div>
      {task.aiSuggestion && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 mt-4">
          <div className="flex items-center justify-between mb-2"><div className="flex items-center gap-1.5 text-rq-primary"><Bot className="w-4 h-4" /><span className="text-[10px] font-bold uppercase tracking-wider">AI Advisory</span></div><span className="text-[10px] font-mono font-bold text-slate-500">{task.aiConf} CONF</span></div>
          <p className="text-xs sm:text-sm font-medium text-slate-800">{task.aiSuggestion}</p>
        </div>
      )}
    </button>
  );
}
