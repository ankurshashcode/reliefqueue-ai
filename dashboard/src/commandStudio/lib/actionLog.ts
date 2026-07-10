export interface ActionLogEntry {
  id: string;
  time: string;
  action: string;
  type: 'Approval' | 'Config Update' | 'Advisory Gen' | 'Sync Conflict' | 'API Call' | 'Normalization' | 'Quality';
  status: 'Success' | 'Local Demo Fallback' | 'Error';
  details?: any;
}

let logs: ActionLogEntry[] = [];
let listeners: ((logs: ActionLogEntry[]) => void)[] = [];

export const actionLog = {
  add: (action: string, type: ActionLogEntry['type'], status: ActionLogEntry['status'], details?: any) => {
    const entry: ActionLogEntry = {
      id: `REQ-${Math.floor(Math.random() * 1000000)}`,
      time: new Date().toLocaleTimeString(),
      action,
      type,
      status,
      details
    };
    logs = [entry, ...logs].slice(0, 100);
    listeners.forEach(l => l(logs));
  },
  subscribe: (listener: (logs: ActionLogEntry[]) => void) => {
    listeners.push(listener);
    listener(logs);
    return () => {
      listeners = listeners.filter(l => l !== listener);
    };
  },
  get: () => logs
};
