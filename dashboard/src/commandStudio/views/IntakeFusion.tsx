import { useState } from 'react';
import { useApp } from '../context/AppContext';
import { Filter, Bot, Link as LinkIcon, AlertTriangle, ShieldAlert, FileText, Share2, Check, Smartphone, MessageSquare } from 'lucide-react';
import { productApi } from '../lib/productApi';

const RAW_MESSAGES = [
  { id: 'RM-001', provider: 'RapidPro', source: '+123***89', text: 'help we are stuck in flooded basement 3 ppl need boat soon', time: '10:42 AM', confidence: 'Medium', external_id: 'RP-992' },
  { id: 'RM-002', provider: 'WhatsApp', source: 'whatsapp:+55***', text: 'Medical emergency at the community center, asthma attack no inhaler', time: '10:45 AM', confidence: 'High', external_id: 'WA-102' },
  { id: 'RM-003', provider: 'local_mock', source: 'demo_user', text: 'Tree fell on car on main st, looks bad but driver is out', time: '10:50 AM', confidence: 'High', external_id: 'LM-005' },
];

export function IntakeFusion() {
  const { addLog, showToast } = useApp();
  const [normalizedMsg, setNormalizedMsg] = useState<any | null>(null);
  const [selectedRaw, setSelectedRaw] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleNormalize = async (msg: any) => {
    setLoading(true);
    setSelectedRaw(msg.id);
    const result = await productApi.normalizeMessage(msg);
    setNormalizedMsg({ ...result, original: msg });
    setLoading(false);
    showToast('Message normalized.', 'success');
  };

  const handleAction = (actionName: string) => {
    addLog(actionName, 'Quality', 'Success', { ref: normalizedMsg?.original?.id });
    showToast(`${actionName} applied.`, 'success');
    setNormalizedMsg(null);
    setSelectedRaw(null);
  };

  return (
    <div className="p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto h-full flex flex-col overflow-hidden">
      <div className="mb-6 flex-shrink-0">
        <h2 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">AI Intake Fusion</h2>
        <p className="text-slate-500 mt-1 md:mt-2 text-sm md:text-base">Normalize messy multi-source inbound reports into structured incident candidates.</p>
      </div>

      <div className="flex-1 flex flex-col md:flex-row gap-6 overflow-hidden">
        {/* Left: Raw Messages */}
        <div className="w-full md:w-1/2 lg:w-1/3 flex flex-col gap-4 overflow-y-auto pr-2">
          <h3 className="font-bold text-slate-700 tracking-wider text-xs border-b border-slate-200 pb-2">Raw Inbound Queue</h3>
          {RAW_MESSAGES.map(msg => (
            <div key={msg.id} className={`bg-white border rounded-lg p-4 shadow-sm transition-all ${selectedRaw === msg.id ? 'ring-2 ring-rq-primary border-rq-primary bg-blue-50/10' : 'border-slate-200 hover:border-slate-300'}`}>
              <div className="flex justify-between items-start mb-2">
                <span className="inline-flex items-center gap-1.5 px-2 py-1 bg-slate-100 text-slate-600 rounded text-[10px] font-mono font-bold">
                  {msg.provider === 'WhatsApp' ? <MessageSquare className="w-3 h-3" /> : <Smartphone className="w-3 h-3" />}
                  {msg.provider}
                </span>
                <span className="text-xs text-slate-400 font-mono">{msg.time}</span>
              </div>
              <p className="text-sm text-slate-800 mb-3 italic">"{msg.text}"</p>
              <div className="flex justify-between items-center mt-3 pt-3 border-t border-slate-100">
                <span className="text-[10px] font-mono text-slate-400">ID: {msg.external_id}</span>
                <button 
                  onClick={() => handleNormalize(msg)}
                  disabled={loading && selectedRaw === msg.id}
                  className="px-3 py-1.5 bg-rq-primary text-white text-xs font-medium rounded hover:bg-rq-primary-hover disabled:opacity-50 flex items-center gap-2"
                >
                  <Bot className="w-3.5 h-3.5" /> Normalize
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Right: AI Extraction & Actions */}
        <div className="w-full md:w-1/2 lg:w-2/3 bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
          <div className="p-4 border-b border-slate-200 bg-slate-50">
            <h3 className="font-bold text-slate-900 flex items-center gap-2">
              <FileText className="w-5 h-5 text-rq-primary" /> Extraction & Normalization
            </h3>
          </div>
          <div className="flex-1 p-6 overflow-y-auto">
            {!normalizedMsg && !loading && (
               <div className="h-full flex flex-col items-center justify-center text-slate-400">
                 <Bot className="w-12 h-12 mb-4 opacity-20" />
                 <p>Select a raw message to normalize.</p>
               </div>
            )}
            {loading && (
              <div className="h-full flex flex-col items-center justify-center text-slate-400">
                 <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-rq-primary mb-4"></div>
                 <p>Normalizing via Webhook API / Local fallback...</p>
               </div>
            )}
            {normalizedMsg && !loading && (
              <div className="space-y-6 max-w-2xl">
                <div>
                  <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Original Payload</h4>
                  <div className="bg-slate-100 p-3 rounded font-mono text-xs text-slate-600">
                    Source: {normalizedMsg.original.source} <br/>
                    Provider: {normalizedMsg.original.provider} <br/>
                    Text: {normalizedMsg.original.text}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="border border-slate-200 p-3 rounded-lg">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider font-bold block mb-1">Suggested Urgency</span>
                    <span className="text-sm font-semibold text-amber-600">{normalizedMsg.urgency}</span>
                  </div>
                  <div className="border border-slate-200 p-3 rounded-lg">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider font-bold block mb-1">Need Type</span>
                    <span className="text-sm font-semibold text-slate-800">{normalizedMsg.needType}</span>
                  </div>
                </div>

                <div className="bg-blue-50/50 p-4 rounded-lg border border-blue-100">
                  <h4 className="text-xs font-bold text-blue-800 uppercase tracking-wider mb-2 flex items-center gap-1">
                    <AlertTriangle className="w-4 h-4" /> Missing Information
                  </h4>
                  <p className="text-sm text-blue-900">Precise location is missing. Exact number of people is unclear.</p>
                </div>

                <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 p-3 rounded border border-amber-200">
                  <ShieldAlert className="w-4 h-4 shrink-0" />
                  <span><strong>Human Review Required:</strong> Review redaction and intent before creating a Review Packet.</span>
                </div>
              </div>
            )}
          </div>
          {normalizedMsg && !loading && (
            <div className="p-4 border-t border-slate-200 bg-slate-50 flex flex-wrap gap-3">
               <button onClick={() => handleAction('Run AMD/vLLM Advisory')} className="px-4 py-2 bg-slate-900 text-white rounded font-medium text-sm hover:bg-slate-800 flex items-center gap-2">
                 <Bot className="w-4 h-4" /> Run AMD/vLLM Advisory
               </button>
               <button onClick={() => handleAction('Create Review Packet')} className="px-4 py-2 bg-rq-primary text-white rounded font-medium text-sm hover:bg-rq-primary-hover flex items-center gap-2">
                 <Check className="w-4 h-4" /> Create Review Packet
               </button>
               <button onClick={() => handleAction('Request Missing Info')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded font-medium text-sm hover:bg-slate-50 flex items-center gap-2">
                 <Share2 className="w-4 h-4" /> Request Missing Info
               </button>
               <button onClick={() => handleAction('Link as Possible Duplicate')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded font-medium text-sm hover:bg-slate-50 flex items-center gap-2">
                 <LinkIcon className="w-4 h-4" /> Link as Possible Duplicate
               </button>
               <button onClick={() => handleAction('Keep Separate')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded font-medium text-sm hover:bg-slate-50 flex items-center gap-2">
                 Keep Separate
               </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
