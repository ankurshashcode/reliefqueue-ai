import { Link } from '../routing';
import { Case } from '../types';
import { FieldPriorityBadge } from './FieldPriorityBadge';

export const FieldCaseCard = ({ caseData }: { caseData: Case }) => {
  return (
    <Link data-action-id="field.open_case_detail" to={`/field/cases/${caseData.id}`} className="bg-surface border-b-2 border-outline-variant p-4 flex flex-col md:flex-row gap-4 min-h-[72px] cursor-pointer hover:bg-surface-container-low transition-colors block">
      <div className="flex-1">
        <div className="flex items-start justify-between mb-2">
          <div className="flex gap-2 items-center">
            <FieldPriorityBadge priority={caseData.priority} />
            <span className="text-base font-bold text-on-surface">#{caseData.id}</span>
          </div>
          <span className="text-xs text-on-surface-variant font-bold">{caseData.timestamp}</span>
        </div>
        <h3 className="text-xl font-bold text-on-background mb-1">{caseData.title}</h3>
        <p className="text-lg text-on-surface-variant mb-3 line-clamp-2">Need: {caseData.needType} | {caseData.landmarkClue}</p>
        
        <div className="flex flex-wrap gap-2 items-center">
          {caseData.safeNeedLabels.slice(0, 1).map((label, idx) => (
             <span key={idx} className="bg-surface-variant text-on-surface text-xs px-2 py-1 rounded flex items-center gap-1 font-bold border border-outline-variant">
               {label}
             </span>
          ))}
          <span className="text-xs text-on-surface-variant flex items-center gap-1 font-bold">
            {caseData.zone}
          </span>
        </div>
      </div>
      
      <div className="md:w-[200px] flex flex-col justify-center mt-4 md:mt-0">
        <div className="bg-primary text-on-primary text-sm w-full h-12 flex items-center justify-center rounded-lg border-2 border-primary font-bold hover:opacity-90 transition-opacity active:scale-[0.98]">
          RESPOND
        </div>
      </div>
    </Link>
  );
};
