import { Link } from '../routing';
import { FieldTopNav } from '../components/FieldTopNav';
import { useAppContext } from '../contexts/AppContext';
import { Plus, Filter } from 'lucide-react';
import { FieldCaseCard } from '../components/FieldCaseCard';

export const FieldCaseListScreen = () => {
  const { cases, showToast } = useAppContext();

  const handleFilterClick = () => {
    showToast("Filter applied");
  };

  return (
    <div data-result-id="field.case-list" className="pt-16 pb-20 px-4 md:px-10 max-w-4xl mx-auto w-full" aria-live="polite">
      <FieldTopNav title="Assigned Cases" />
      
      <div className="py-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-on-background">Zone A — West Sector</h1>
          <p className="text-base text-on-surface-variant mt-1">Active Cases: {cases.length}</p>
        </div>
        <Link to="/field/new-request" className="bg-primary text-on-primary text-sm px-6 h-12 flex items-center justify-center gap-2 rounded-lg border-2 border-primary w-full md:w-auto hover:bg-primary-container font-bold hover:text-on-primary-container transition-colors shadow-sm">
          <Plus size={20} />
          NEW CASE
        </Link>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-4 mb-2 hide-scrollbar px-1">
        <button onClick={handleFilterClick} className="bg-surface text-on-surface font-bold text-sm px-4 py-2 rounded-full whitespace-nowrap border-2 border-outline-variant hover:bg-surface-container-low active:scale-95 transition-all">Priority: All</button>
        <button onClick={handleFilterClick} className="bg-surface text-on-surface font-bold text-sm px-4 py-2 rounded-full whitespace-nowrap border-2 border-outline-variant hover:bg-surface-container-low active:scale-95 transition-all">Task: All</button>
        <button onClick={handleFilterClick} className="bg-surface text-on-surface font-bold text-sm px-4 py-2 rounded-full whitespace-nowrap border-2 border-outline-variant flex items-center gap-1 hover:bg-surface-container-low active:scale-95 transition-all">
          <Filter size={16} />
          More Filters
        </button>
      </div>

      <div className="flex flex-col gap-0 border-t-2 border-outline-variant">
        {cases.map((c) => (
          <FieldCaseCard key={c.id} caseData={c} />
        ))}
      </div>
    </div>
  );
};
