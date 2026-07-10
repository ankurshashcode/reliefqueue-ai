import { useNavigate } from '../routing';
import { FieldTopNav } from '../components/FieldTopNav';
import { Send, MapPin, Minus, Plus } from 'lucide-react';
import { useAppContext } from '../contexts/AppContext';
import { useState } from 'react';

export const FieldNewRequestScreen = () => {
  const navigate = useNavigate();
  const { networkStatus, addToSyncQueue, showToast } = useAppContext();
  
  const [count, setCount] = useState(1);
  const [need, setNeed] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (networkStatus === 'offline') {
      addToSyncQueue({ type: 'New Request', caseId: 'NEW' });
      showToast('Request queued locally for sync.');
    } else {
      showToast('Request submitted for coordinator review.');
    }
    navigate(-1);
  };

  return (
    <div className="pt-16 pb-20 px-4 md:px-10 max-w-2xl mx-auto w-full">
      <FieldTopNav title="New Relief Request" showBack={true} />
      
      <div className="my-6 flex items-center">
        <h1 className="text-2xl md:text-3xl font-bold">New Request</h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6 bg-surface-container-lowest p-6 rounded-xl border-2 border-outline-variant shadow-sm">
        
        <div className="space-y-2">
          <label className="block text-base font-bold text-on-surface">Location & Landmark Clues</label>
          <div className="relative">
            <span className="absolute inset-y-0 left-0 flex items-center pl-4 pointer-events-none">
              <MapPin className="text-outline" size={20} />
            </span>
            <input type="text" placeholder="Approximate location / landmark clue" required className="w-full bg-surface-container h-16 pl-12 pr-4 rounded-lg border-2 border-outline focus:border-primary text-lg" />
          </div>
          <div className="mt-3 space-y-2">
            <label className="block text-sm font-bold text-on-surface-variant">Location Confidence</label>
            <select className="w-full bg-surface-container h-14 px-4 rounded-lg border-2 border-outline focus:border-primary text-base font-bold">
              <option value="high">High (Visual Confirmation)</option>
              <option value="medium">Approximate — landmark based</option>
              <option value="low">Low (Rough Guess)</option>
            </select>
          </div>
        </div>

        <div className="space-y-2">
          <label className="block text-base font-bold text-on-surface">Reporter tag / masked ID optional</label>
          <input type="text" placeholder="Enter masked tag if available" className="w-full bg-surface-container h-16 px-4 rounded-lg border-2 border-outline focus:border-primary text-lg" />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="block text-base font-bold text-on-surface">Affected Count</label>
            <div className="flex items-center h-16 bg-surface-container rounded-lg border-2 border-outline focus-within:border-primary overflow-hidden">
              <button type="button" onClick={() => setCount(Math.max(1, count - 1))} className="h-full w-16 flex items-center justify-center bg-surface-variant hover:bg-surface-dim border-r-2 border-outline transition-colors active:scale-95">
                <Minus size={20} />
              </button>
              <input type="number" min="1" value={count} onChange={(e) => setCount(parseInt(e.target.value) || 1)} className="w-full h-full text-center bg-transparent text-xl font-bold border-none focus:ring-0" />
              <button type="button" onClick={() => setCount(count + 1)} className="h-full w-16 flex items-center justify-center bg-surface-variant hover:bg-surface-dim border-l-2 border-outline transition-colors active:scale-95">
                <Plus size={20} />
              </button>
            </div>
          </div>

          <div className="space-y-2">
            <label className="block text-base font-bold text-on-surface">Need Type / Critical Need</label>
            <select required value={need} onChange={e => setNeed(e.target.value)} className="w-full bg-surface-container h-16 px-4 rounded-lg border-2 border-outline focus:border-primary text-lg font-bold">
              <option value="" disabled>Select priority...</option>
              <option value="medical">Medical</option>
              <option value="food">Food</option>
              <option value="shelter">Shelter</option>
              <option value="water">Water</option>
              <option value="power">Power</option>
            </select>
          </div>
        </div>

        <div className="space-y-2">
          <label className="block text-base font-bold text-on-surface">Additional Situation Details</label>
          <textarea rows={3} placeholder="Safe summary of conditions..." className="w-full bg-surface-container p-4 rounded-lg border-2 border-outline focus:border-primary text-lg resize-none" />
        </div>

        <div className="pt-6 border-t-2 border-outline-variant">
          <button type="submit" className="w-full h-16 bg-primary text-on-primary text-xl font-bold rounded-lg border-2 border-primary hover:bg-primary-container active:scale-[0.98] flex items-center justify-center gap-2 shadow-sm transition-transform">
            <Send size={24} />
            {networkStatus === 'offline' ? 'Queue for Sync' : 'Submit for Review'}
          </button>
          <p className="text-center mt-4 text-sm font-bold text-on-surface-variant">
            Coordinator review required before assignment.
          </p>
        </div>

      </form>
    </div>
  );
};
