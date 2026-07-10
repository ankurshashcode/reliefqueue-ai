import { useState } from 'react';
import { useNavigate, useParams } from '../routing';
import { FieldTopNav } from '../components/FieldTopNav';
import { useAppContext } from '../contexts/AppContext';
import { Camera, Mic, Save, CloudOff } from 'lucide-react';
import { cn } from '../lib/utils';
import { FieldOfflineBanner } from '../components/FieldOfflineBanner';

export const FieldNoteScreen = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { networkStatus, addToSyncQueue, showToast, addNote } = useAppContext();
  
  const [noteType, setNoteType] = useState('General Note');
  const [noteText, setNoteText] = useState('');

  const handleSave = () => {
    if (!noteText.trim()) {
      showToast('Please enter some text for the note.');
      return;
    }

    if (networkStatus === 'offline') {
      addToSyncQueue({ type: 'Field Note', caseId: id!, details: { type: noteType, text: noteText } });
      showToast('Note saved locally for sync.');
    } else {
      addNote(id!, { type: noteType, text: noteText });
      showToast('Note submitted for coordinator review.');
    }
    navigate(`/field/cases/${id}`);
  };

  return (
    <div className="pt-16 pb-10 px-4 md:px-10 max-w-3xl mx-auto w-full flex flex-col h-screen">
      <FieldTopNav title={`Add Note — ${id}`} showBack={true} />
      
      <div className="flex flex-col gap-1 my-6">
        <h2 className="text-2xl md:text-3xl font-bold">Add Field Note</h2>
        <p className="text-lg text-on-surface-variant">Notes are submitted for coordinator review.</p>
      </div>

      <div className="flex flex-col gap-4 flex-grow">
        {/* Type Selector */}
        <div className="flex gap-2 mb-2 overflow-x-auto pb-2 hide-scrollbar">
          {['General Note', 'Needs Assessment', 'Hazard Report'].map(type => (
            <button 
              key={type}
              onClick={() => setNoteType(type)}
              className={cn(
                "px-5 py-3 rounded-full whitespace-nowrap text-base font-bold border-2 active:scale-95 transition-all shadow-sm",
                noteType === type ? "bg-primary-container text-on-primary-container border-primary" : "bg-surface text-on-surface border-outline-variant hover:bg-surface-container-low"
              )}
            >
              {type}
            </button>
          ))}
        </div>

        {/* Large Text Area */}
        <div className="relative flex-grow flex flex-col min-h-[250px] shadow-sm">
          <label className="text-sm font-bold text-on-surface-variant mb-1 absolute -top-3 left-4 bg-background px-2 z-10">Note Details</label>
          <textarea 
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            className="w-full h-full flex-grow bg-surface p-5 pt-6 rounded-xl border-2 border-outline-variant focus:border-primary focus:outline-none text-xl resize-none shadow-sm" 
            placeholder="Enter field observation. Avoid private contact details."
          />
          
          <div className="absolute bottom-5 right-5 flex gap-3">
            <button 
              onClick={() => showToast("Attachment placeholder created.")}
              className="w-16 h-16 bg-surface-container-high border-2 border-outline-variant text-on-surface rounded-full flex items-center justify-center hover:bg-surface-variant shadow-sm active:scale-95 transition-transform"
            >
              <Camera size={28} />
            </button>
            <button 
              onClick={() => showToast("Attachment placeholder created.")}
              className="w-16 h-16 bg-primary text-on-primary rounded-full flex items-center justify-center hover:bg-primary-container shadow-md active:scale-95 transition-transform"
            >
              <Mic size={28} />
            </button>
          </div>
        </div>
      </div>

      <div className="mt-auto pt-6 flex flex-col gap-4 pb-8">
        {networkStatus === 'offline' && (
          <FieldOfflineBanner message="Offline — note will be saved locally and synced when connection is restored." />
        )}
        <button 
          onClick={handleSave}
          className="w-full h-16 bg-primary text-on-primary text-xl font-bold rounded-xl flex items-center justify-center gap-3 hover:opacity-90 shadow-md active:scale-[0.98] border-2 border-primary"
        >
          <Save size={24} />
          {networkStatus === 'offline' ? 'Save Note Offline' : 'Save Note'}
        </button>
      </div>
    </div>
  );
};
