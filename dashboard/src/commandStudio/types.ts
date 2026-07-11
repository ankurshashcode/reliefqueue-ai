export type ViewState = 
  | 'overview' 
  | 'map' 
  | 'assignments' 
  | 'workload' 
  | 'sync' 
  | 'scenario' 
  | 'aicontrol' 
  | 'quality' 
  | 'audit'
  | 'intake'
  | 'links'
  | 'amd'
  | 'capabilities';


export const VIEW_ROUTES: Record<ViewState, string> = {
  overview: '/dashboard?source=latest',
  intake: '/dashboard/intake',
  links: '/dashboard/incident-links',
  map: '/dashboard/map',
  assignments: '/dashboard/assignments',
  workload: '/dashboard/workload',
  sync: '/dashboard/field-sync',
  scenario: '/dashboard/scenario',
  aicontrol: '/dashboard/ai-control',
  quality: '/dashboard/quality',
  audit: '/dashboard/audit',
  amd: '/dashboard/amd-impact',
  capabilities: '/dashboard/capability-map',
};

export function viewForPath(rawPath: string): ViewState {
  const path = (rawPath || '/').replace(/\/+$/, '') || '/';
  const aliases: Record<string, ViewState> = {
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
  };
  return aliases[path] || 'overview';
}

export interface NavItem {
  id: ViewState;
  label: string;
  icon: string;
}

export const NAVIGATION: NavItem[] = [
  { id: 'overview', label: 'Overview', icon: 'LayoutDashboard' },
  { id: 'intake', label: 'AI Intake', icon: 'Bot' },
  { id: 'links', label: 'Incident Links', icon: 'Link2' },
  { id: 'map', label: 'Live Map', icon: 'Map' },
  { id: 'assignments', label: 'Assignments', icon: 'ClipboardList' },
  { id: 'workload', label: 'Workload', icon: 'Briefcase' },
  { id: 'sync', label: 'Field Sync', icon: 'RefreshCw' },
  { id: 'scenario', label: 'Scenario', icon: 'Route' },
  { id: 'aicontrol', label: 'AI Control', icon: 'Cpu' },
  { id: 'quality', label: 'Quality', icon: 'ShieldCheck' },
  { id: 'audit', label: 'Audit / Troubleshooting', icon: 'History' },
  { id: 'amd', label: 'AMD Impact', icon: 'Zap' },
  { id: 'capabilities', label: 'Capability Map', icon: 'Server' },
];

export interface LogEntry {
  id: string;
  timestamp: string;
  action: string;
  details?: string;
}

export interface ToastMsg {
  id: string;
  message: string;
  type: 'info' | 'success' | 'warning' | 'error';
}
