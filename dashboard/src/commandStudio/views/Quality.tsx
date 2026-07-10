import React, { useState } from 'react';
import { AlertCircle, FileSearch, Filter, ShieldCheck, UploadCloud, EyeOff, Camera, FileText, Bot } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { DetailDrawer } from '../components/Shared';
import { AIAdvisoryDrawer } from '../components/AIAdvisoryDrawer';

const MOCK_REVIEWS = [
  { id: 'RQ-8924-A', tags: [{label: 'Uncertain', color: 'amber'}, {label: 'Urgent', color: 'red'}], time: '10 mins ago', desc: 'Medical Evacuation request missing exact coordinate precision. AI generated wide search radius.', meta: 'Pending manual validation of coordinates.', type: 'advisory' },
  { id: 'RQ-8925-B', tags: [{label: 'Possible Duplicate', color: 'blue'}], time: '45 mins ago', desc: 'Supply Route Clearance request highly similar to RQ-8812. AI suggests merging.', meta: 'Match Confidence: 92%', type: 'advisory' },
  { id: 'RQ-8926-C', tags: [{label: 'Redaction Review', color: 'slate'}], time: '1 hour ago', desc: 'Generator Fuel Drop summary generated for public export. Review redaction of sensitive asset locations.', meta: 'Contains: Facility Alpha coordinates.', type: 'redaction',
    content: "The generator fuel drop at Facility Alpha [REDACTED_COORD] was successful. Awaiting secondary transport."
  },
  { id: 'RQ-8927-D', tags: [{label: 'Evidence Review', color: 'emerald'}], time: '2 hours ago', desc: 'Flood photo submitted by field unit Beta. Review for PII before attaching to public situation report.', meta: 'Image Analysis: Contains 2 faces (blurred by AI).', type: 'evidence' },
];

export function Quality() {
  const { addLog, showToast } = useApp();
  const [selectedReviewId, setSelectedReviewId] = useState<string | null>(null);
  const [filter, setFilter] = useState('ALL');
  const [advisoryOpen, setAdvisoryOpen] = useState(false);

  const selectedReview = MOCK_REVIEWS.find(r => r.id === selectedReviewId);

  const handleAction = (action: string) => {
    addLog(`Quality Review Action`, `Applied '${action}' to ${selectedReview?.id}`);
    showToast(`Action '${action}' logged locally.`, 'success');
    setSelectedReviewId(null);
  };

  const filteredReviews = MOCK_REVIEWS.filter(r => {
    if (filter === 'ALL') return true;
    if (filter === 'URGENT') return r.tags.some((t: any) => t.label === 'Urgent');
    if (filter === 'DUPLICATE') return r.tags.some((t: any) => t.label === 'Possible Duplicate');
    if (filter === 'REDACTION') return r.tags.some((t: any) => t.label === 'Redaction Review');
    if (filter === 'EVIDENCE') return r.tags.some((t: any) => t.label === 'Evidence Review');
    return true;
  });

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto h-full flex flex-col overflow-hidden">
      <div className="mb-6 flex-shrink-0">
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900">Quality & Evidence Queue</h1>
        <p className="text-slate-500 mt-1 md:mt-2 text-sm md:text-base">Review uncertain cases, duplicate candidates, redactions, and field evidence before public export or coordinator approval.</p>
        
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 md:gap-4 mt-6">
          <StatBox label="Pending Reviews" value="25" onClick={() => setFilter('ALL')} active={filter === 'ALL'} />
          <StatBox label="Urgent Review" value="6" color="text-rq-red" onClick={() => setFilter('URGENT')} active={filter === 'URGENT'} />
          <StatBox label="Possible Duplicates" value="5" color="text-rq-primary" onClick={() => setFilter('DUPLICATE')} active={filter === 'DUPLICATE'} />
          <StatBox label="Redaction Needed" value="13" color="text-slate-600" onClick={() => setFilter('REDACTION')} active={filter === 'REDACTION'} />
          <StatBox label="Evidence Triage" value="1" color="text-emerald-600" onClick={() => setFilter('EVIDENCE')} active={filter === 'EVIDENCE'} />
        </div>
      </div>

      <div className="flex-1 flex gap-6 min-h-0">
        {/* Full width list (Detail is a Drawer on all sizes to keep list full width on desktop) */}
        <div className="w-full flex flex-col gap-3 overflow-y-auto pr-2 pb-8">
           {filteredReviews.map(r => (
             <ReviewRow 
               key={r.id}
               review={r}
               selected={selectedReviewId === r.id}
               onClick={() => setSelectedReviewId(r.id)}
             />
           ))}
           {filteredReviews.length === 0 && (
             <div className="text-center text-slate-500 py-8">No reviews match the current filter.</div>
           )}
        </div>
      </div>

      <DetailDrawer
        isOpen={!!selectedReview}
        onClose={() => setSelectedReviewId(null)}
        title={selectedReview?.type === 'evidence' ? "Evidence Packet Review" : "Review Item"}
      >
        {selectedReview && (
          <div className="flex flex-col h-full gap-6">
            <div>
              <h2 className="text-2xl font-bold text-slate-900">{selectedReview.id}</h2>
              <p className="text-xs text-slate-500 mt-1 font-mono uppercase tracking-wider font-bold">AI Advisory Only • Human Review Required</p>
              
              <div className="flex gap-2 mt-4">
                {selectedReview.tags.map((tag: any, idx: number) => (
                  <span key={idx} className={`px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider rounded border
                    ${tag.color === 'amber' ? 'bg-amber-100 text-amber-800 border-amber-200' : 
                      tag.color === 'red' ? 'bg-red-100 text-red-800 border-red-200' : 
                      tag.color === 'emerald' ? 'bg-emerald-100 text-emerald-800 border-emerald-200' : 
                      tag.color === 'slate' ? 'bg-slate-100 text-slate-800 border-slate-200' :
                      'bg-blue-100 text-blue-800 border-blue-200'
                    }`}
                  >
                    {tag.label}
                  </span>
                ))}
              </div>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
               <h4 className="font-semibold text-slate-900 mb-2 flex items-center gap-2">
                 <FileSearch className="w-4 h-4 text-slate-500" /> Assessment Detail
               </h4>
               <p className="text-sm text-slate-700">{selectedReview.desc}</p>
               <div className="mt-3 pt-3 border-t border-slate-200">
                 <span className="text-xs font-mono text-slate-500 block mb-1">METADATA</span>
                 <p className="text-sm font-semibold text-slate-800">{selectedReview.meta}</p>
               </div>
            </div>

            {selectedReview.type === 'redaction' && (
              <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-inner">
                <h4 className="font-semibold text-slate-900 mb-2 flex items-center gap-2">
                  <FileText className="w-4 h-4 text-rq-primary" /> Redacted Document Preview
                </h4>
                <div className="bg-slate-50 p-3 rounded text-sm text-slate-800 font-serif leading-relaxed border border-slate-100">
                   "The generator fuel drop at Facility Alpha <span className="bg-black text-black select-none px-1">[REDACTED_COORD]</span> was successful. Awaiting secondary transport."
                </div>
              </div>
            )}

            {selectedReview.type === 'evidence' && (
              <div className="bg-slate-100 border border-slate-200 rounded-lg overflow-hidden relative">
                <div className="aspect-video bg-slate-200 flex items-center justify-center">
                  <Camera className="w-12 h-12 text-slate-400" />
                  <div className="absolute inset-0 bg-slate-900/10 flex items-center justify-center">
                     <span className="bg-slate-900/80 text-white px-3 py-1 rounded-full text-xs font-mono">Image Preview (Demo)</span>
                  </div>
                </div>
                <div className="p-3 bg-white border-t border-slate-200 text-xs text-slate-600 font-mono flex items-center justify-between">
                  <span>AI Pre-processing: Blur applied to 2 detected faces.</span>
                  <button onClick={() => handleAction('Toggle Blur')} className="text-rq-primary hover:underline font-bold">Toggle Blur</button>
                </div>
              </div>
            )}

            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3">
              <EyeOff className="w-5 h-5 text-amber-600 mt-0.5 shrink-0" />
              <div>
                <h4 className="font-bold text-amber-900 text-sm">Public / Private Export Boundary</h4>
                <p className="text-xs text-amber-800 mt-1">Ensure sensitive infrastructure locations and PII are redacted before approving for public summary export.</p>
              </div>
            </div>

            <div className="mt-auto pt-6 flex flex-col gap-3">
               {selectedReview.type !== 'evidence' && selectedReview.type !== 'redaction' && (
                 <>
                   <button onClick={() => setAdvisoryOpen(true)} className="w-full bg-slate-900 hover:bg-slate-800 text-white py-3 rounded-lg text-sm font-semibold transition-colors shadow-sm flex items-center justify-center gap-2">
                     <Bot className="w-4 h-4" /> Request AI Advisory
                   </button>
                   <button onClick={() => handleAction('Request Info')} className="w-full bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 py-3 rounded-lg text-sm font-semibold transition-colors shadow-sm">
                     Request Missing Info
                   </button>
                   <button onClick={() => handleAction('Mark Possible Duplicate')} className="w-full bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 py-3 rounded-lg text-sm font-semibold transition-colors shadow-sm">
                     Mark as Possible Duplicate
                   </button>
                   <button onClick={() => handleAction('Needs Coordinator Review')} className="w-full bg-rq-primary hover:bg-rq-primary-hover text-white py-3 rounded-lg text-sm font-semibold transition-colors shadow-sm mt-2">
                     Needs Coordinator Review
                   </button>
                 </>
               )}
               {selectedReview.type === 'evidence' && (
                 <>
                   <button onClick={() => handleAction('Reject Evidence')} className="w-full bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 py-3 rounded-lg text-sm font-semibold transition-colors shadow-sm">
                     Reject Evidence (Contains PII/Sensitive)
                   </button>
                   <button onClick={() => handleAction('Approve Evidence')} className="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-3 rounded-lg text-sm font-semibold transition-colors shadow-sm mt-2">
                     Approve for Public Case File
                   </button>
                 </>
               )}
               {selectedReview.type === 'redaction' && (
                 <button onClick={() => handleAction('Approve Public Summary')} className="w-full bg-slate-800 hover:bg-slate-900 text-white py-3 rounded-lg text-sm font-semibold transition-colors shadow-sm flex items-center justify-center gap-2 mt-2">
                   <ShieldCheck className="w-4 h-4" /> Approve Redaction for Export
                 </button>
               )}
            </div>
          </div>
        )}
      </DetailDrawer>

      {selectedReview && (
        <AIAdvisoryDrawer
          isOpen={advisoryOpen}
          onClose={() => setAdvisoryOpen(false)}
          caseId={selectedReview.id}
          data={{
            summary: selectedReview.desc,
            priority: 'Unknown',
            needType: 'Review',
            locationConfidence: 'Low'
          }}
        />
      )}
    </div>
  );
}

function StatBox({ label, value, color, onClick, active }: any) {
  return (
    <div onClick={onClick} className={`bg-white border rounded-lg p-3 md:p-4 shadow-sm cursor-pointer hover:shadow transition-shadow ${active ? 'ring-2 ring-rq-primary border-rq-primary bg-blue-50/20' : 'border-slate-200'}`}>
      <div className={`text-2xl md:text-3xl font-bold ${color || 'text-slate-900'}`}>{value}</div>
      <div className="text-[10px] md:text-xs font-mono text-slate-500 uppercase tracking-wider mt-1 md:mt-2">{label}</div>
    </div>
  );
}

function ReviewRow({ review, selected, onClick }: any) {
  return (
    <div onClick={onClick} className={`bg-white border rounded-lg p-4 md:p-5 flex flex-col md:flex-row md:items-start justify-between gap-4 shadow-sm cursor-pointer transition-all ${
      selected ? 'border-rq-primary ring-1 ring-rq-primary/50 bg-blue-50/30' : 'border-slate-200 hover:border-slate-300 hover:shadow'
    }`}>
      <div className="flex-1">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="font-bold text-slate-900 text-sm md:text-base mr-2">{review.id}</span>
          {review.tags.map((tag: any, idx: number) => (
            <span key={idx} className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded border
              ${tag.color === 'amber' ? 'bg-amber-100 text-amber-800 border-amber-200' : 
                tag.color === 'red' ? 'bg-red-100 text-red-800 border-red-200' : 
                tag.color === 'slate' ? 'bg-slate-100 text-slate-800 border-slate-200' :
                tag.color === 'emerald' ? 'bg-emerald-100 text-emerald-800 border-emerald-200' :
                'bg-blue-100 text-blue-800 border-blue-200'
              }`}
            >
              {tag.label}
            </span>
          ))}
        </div>
        <p className="text-sm text-slate-600 line-clamp-2 md:line-clamp-1">{review.desc}</p>
        <p className="text-[10px] md:text-xs font-mono text-slate-400 mt-2">{review.time} • AI Suggestion requires review</p>
      </div>
      <div className="shrink-0 flex items-center justify-end">
        <span className="text-sm font-medium text-rq-primary underline">Review Packet</span>
      </div>
    </div>
  );
}
