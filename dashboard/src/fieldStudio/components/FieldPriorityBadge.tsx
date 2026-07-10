import { cn } from '../lib/utils';
import { Case } from '../types';

export const FieldPriorityBadge = ({ priority }: { priority: Case['priority'] }) => {
  return (
    <span className={cn(
      "text-xs px-2 py-1 rounded font-bold uppercase border-2",
      priority === 'Urgent' ? "bg-error text-on-error border-error" : 
      priority === 'High' ? "bg-secondary-container text-on-secondary-container border-secondary" :
      "bg-surface-variant text-on-surface-variant border-outline-variant"
    )}>
      {priority}
    </span>
  );
};
