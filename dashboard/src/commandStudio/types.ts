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
