import { Link } from '../routing';
import { FieldTopNav } from '../components/FieldTopNav';
import { MapPin, ClipboardList, AlertTriangle, PlusCircle } from 'lucide-react';

export const FieldMyWorkScreen = () => {
  return (
    <div className="pt-16 pb-20 px-4 md:px-10 max-w-2xl mx-auto w-full">
      <FieldTopNav title="ReliefQueue" />
      
      <div className="my-6">
        <h2 className="text-2xl font-bold text-on-background mb-1">My Work Dashboard</h2>
        <p className="text-lg text-on-surface-variant">Field Coordinator Dashboard</p>
      </div>

      <div className="flex flex-col gap-4">
        {/* Current Zone Card */}
        <div className="bg-surface-container-high rounded-xl p-6 flex flex-col justify-between border-2 border-transparent">
          <div className="flex items-center gap-2 mb-4">
            <MapPin className="text-secondary" />
            <h3 className="text-xl font-bold text-on-surface">Current Zone</h3>
          </div>
          <p className="text-2xl font-bold text-primary mb-1">Zone A — West Sector</p>
          <p className="text-base text-on-surface-variant">Active deployment area. Conditions reported nominal.</p>
        </div>

        {/* Task Summary Quick Stats */}
        <Link to="/field/my-cases" className="bg-primary-container text-on-primary-container rounded-xl p-6 flex flex-col items-center justify-center border-2 border-primary-fixed-dim hover:bg-primary transition-colors cursor-pointer text-center">
          <ClipboardList size={36} className="mb-2" />
          <span className="text-3xl font-bold block">14</span>
          <span className="text-sm uppercase tracking-wider mt-1 block font-bold">Assigned Tasks</span>
        </Link>

        {/* Priority Alerts */}
        <div className="bg-error-container text-on-error-container rounded-xl p-6 border-2 border-error flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-start md:items-center gap-3">
            <AlertTriangle className="text-error mt-1 md:mt-0 flex-shrink-0" />
            <div>
              <h4 className="text-xl font-bold">1 critical case needs coordinator review</h4>
              <p className="text-base">Medical transport support flagged in West Sector.</p>
            </div>
          </div>
          <Link to="/field/cases/RQ-1042" className="bg-error text-on-error text-sm px-6 h-12 rounded-full font-bold whitespace-nowrap hover:opacity-90 active:scale-95 transition-all w-full md:w-auto flex items-center justify-center">
            Review Now
          </Link>
        </div>

        {/* Primary Action Area */}
        <div className="mt-6 flex flex-col gap-4">
          <Link to="/field/new-request" className="w-full bg-primary text-on-primary text-sm h-16 rounded-xl flex items-center justify-center gap-2 border-2 border-primary font-bold hover:opacity-90 transition-opacity active:scale-[0.98]">
            <PlusCircle />
            New Relief Request
          </Link>
          <Link to="/field/my-cases" className="w-full bg-surface-container text-primary text-sm h-16 rounded-xl flex items-center justify-center gap-2 border-2 border-primary font-bold hover:bg-surface-variant transition-colors active:scale-[0.98]">
            <ClipboardList />
            View Assigned Cases
          </Link>
        </div>
      </div>
    </div>
  );
};
