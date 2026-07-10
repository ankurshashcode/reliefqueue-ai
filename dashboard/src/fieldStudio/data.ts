import { Case } from './types';

export const INITIAL_CASES: Case[] = [
  {
    id: 'RQ-1042',
    zone: 'Zone A — West Sector',
    title: 'Medical Evacuation Required',
    priority: 'Urgent',
    needType: 'Medical transport',
    peopleCount: 1,
    vulnerabilityFlag: 'Elderly resident',
    landmarkClue: 'West High School Shelter — Gymnasium, Section C',
    locationConfidence: 'Approximate — landmark based',
    coordinatorInstruction: 'Approach via north gate. Main road may be flooded. Report status before moving the person.',
    safeNeedLabels: ['Medication support flagged', 'Potable water (2 Gallons)', 'Power Bank for CPAP'],
    status: 'Pending',
    timestamp: '10 min ago',
  },
  {
    id: 'RQ-1045',
    zone: 'Zone A',
    title: 'Emergency Rations Depot A',
    priority: 'High',
    needType: 'Food',
    peopleCount: 50,
    landmarkClue: 'Shelter Depot A',
    locationConfidence: 'High (Visual Confirmation)',
    safeNeedLabels: ['Food'],
    status: 'Pending',
    timestamp: '45 min ago',
  }
];
