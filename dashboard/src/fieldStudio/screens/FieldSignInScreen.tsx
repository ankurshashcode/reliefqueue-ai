import { useNavigate } from '../routing';
import { useAppContext } from '../contexts/AppContext';

export const FieldSignInScreen = () => {
  const navigate = useNavigate();

  return (
    <section className="w-full max-w-md bg-surface border border-outline-variant rounded-xl p-6 flex flex-col gap-8 shadow-sm m-auto mt-12 md:mt-24">
      <div className="flex flex-col items-center text-center gap-2">
        <div className="w-16 h-16 bg-primary-container text-on-primary-container rounded-xl flex items-center justify-center mb-2 border border-primary-container">
          <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-primary">ReliefQueue Field Sign In</h1>
        <p className="text-sm text-on-surface-variant">Assignment coordination starting... Select your assigned field role to continue.</p>
      </div>

      <div className="flex flex-col gap-4">
        <label className="relative flex items-center p-4 border rounded-lg cursor-pointer bg-surface-container-high border-primary">
          <input type="radio" name="role" value="coordinator" defaultChecked className="sr-only peer" />
          <div className="flex-1 flex items-center gap-4">
            <div className="flex flex-col">
              <span className="font-bold text-on-surface text-lg">Field Coordinator</span>
              <span className="text-sm text-on-surface-variant">Manage deployments & logistics</span>
            </div>
          </div>
        </label>

        <label className="relative flex items-center p-4 border border-outline-variant rounded-lg cursor-pointer hover:bg-surface-container-low opacity-50">
          <input type="radio" name="role" value="volunteer" disabled className="sr-only peer" />
          <div className="flex-1 flex items-center gap-4">
            <div className="flex flex-col">
              <span className="font-bold text-on-surface text-lg">Volunteer</span>
              <span className="text-sm text-on-surface-variant">On-the-ground tasks</span>
            </div>
          </div>
        </label>

        <button 
          onClick={() => navigate('/field/my-work')}
          className="mt-4 w-full h-12 bg-primary text-on-primary font-bold rounded-lg hover:bg-primary-container transition-colors flex items-center justify-center gap-2"
        >
          CONTINUE
        </button>
      </div>
    </section>
  );
};
