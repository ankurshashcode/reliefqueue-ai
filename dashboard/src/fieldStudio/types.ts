export type NetworkStatus = 'online' | 'slow' | 'offline' | 'syncing';

export interface Case {
  id: string;
  zone: string;
  title: string;
  priority: 'Urgent' | 'High' | 'Normal';
  needType: string;
  peopleCount: number;
  vulnerabilityFlag?: string;
  landmarkClue: string;
  locationConfidence: string;
  coordinatorInstruction?: string;
  safeNeedLabels: string[];
  status: 'Pending' | 'In Progress' | 'Needs Assistance' | 'Complete' | 'Paused';
  timestamp: string;
}

export interface SyncItem {
  id: string;
  type: 'Status Update' | 'Field Note' | 'Evidence Metadata' | 'New Request';
  caseId: string;
  timestamp: string;
  details?: any;
}

export interface FieldNote {
  id: string;
  type: string;
  text: string;
  timestamp: string;
  author: string;
}
