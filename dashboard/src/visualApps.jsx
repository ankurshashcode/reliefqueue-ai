import React from 'react';
import CommandStudioApp from './commandStudio/App';
import FieldStudioApp from './fieldStudio/App';
import './commandStudio/index.css';
import './fieldStudio/index.css';
import './visualApps.css';

const pathToView = {
  '/dashboard': 'overview',
  '/dashboard/overview': 'overview',
  '/dashboard/map': 'map',
  '/dashboard/assignments': 'assignments',
  '/dashboard/workload': 'workload',
  '/dashboard/field-sync': 'sync',
  '/dashboard/scenario': 'scenario',
  '/dashboard/ai-control': 'aicontrol',
  '/dashboard/quality': 'quality',
  '/dashboard/audit': 'audit',
  '/dashboard/intake': 'intake',
  '/dashboard/incident-links': 'links',
  '/dashboard/amd-impact': 'amd',
  '/dashboard/capability-map': 'capabilities'
};

export function VisualCommandCenterApp() {
  return <CommandStudioApp initialView={pathToView[window.location.pathname] || 'overview'} />;
}

export function VisualFieldCoordinatorApp() {
  return <FieldStudioApp initialPath={window.location.pathname} />;
}

export function VisualLocalCoordinatorApp() {
  return <CommandStudioApp initialView="overview" />;
}

export function InternalClassicDebugNotice() {
  return <CommandStudioApp initialView="capabilities" />;
}
