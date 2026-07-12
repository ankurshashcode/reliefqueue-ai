import { Activity, CheckCircle, Clock, Database, RefreshCw, Server, ShieldAlert, TriangleAlert } from 'lucide-react';
import type { AmdCapabilityPayload, CurrentRequestPlane } from '../lib/amdEvidence';

interface Props {
  capability: AmdCapabilityPayload | null;
  loading: boolean;
  error: string | null;
  currentRequest?: CurrentRequestPlane | null;
  onRefresh?: () => void;
}

function requestStatus(request: CurrentRequestPlane | null | undefined) {
  if (!request?.attempted) return { label: 'Not attempted on this screen', tone: 'slate' } as const;
  if (request.pending) return { label: 'Verification in progress', tone: 'blue' } as const;
  if (request.verified_live) return { label: 'Verified live for this request', tone: 'green' } as const;
  if (request.fallback_used) return { label: 'Fallback used — not verified live', tone: 'amber' } as const;
  if (request.provider_error) return { label: 'Provider error — not verified live', tone: 'red' } as const;
  return { label: 'Attempted — verification incomplete', tone: 'amber' } as const;
}

function toneClasses(tone: 'slate' | 'blue' | 'green' | 'amber' | 'red') {
  return {
    slate: 'bg-slate-100 text-slate-700 border-slate-200',
    blue: 'bg-blue-50 text-blue-800 border-blue-200',
    green: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    amber: 'bg-amber-50 text-amber-800 border-amber-200',
    red: 'bg-red-50 text-red-800 border-red-200',
  }[tone];
}

export function AmdEvidenceSummary({ capability, loading, error, currentRequest, onRefresh }: Props) {
  const campaign = capability?.historical_evidence || null;
  const quality = campaign?.final_resolved_quality || null;
  const runtime = capability?.live_runtime || null;
  const request = currentRequest || capability?.current_request || null;
  const requestView = requestStatus(request);

  return (
    <section
      data-testid="amd-evidence-summary"
      className="mb-8 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
    >
      <div className="flex flex-col gap-3 border-b border-slate-200 bg-slate-50 px-5 py-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h3 className="flex items-center gap-2 font-bold text-slate-900">
            <Database className="h-4 w-4 text-rq-primary" /> AMD Evidence Planes
          </h3>
          <p className="mt-1 text-xs text-slate-500">
            Historical verified evidence, current runtime configuration, and the latest request result are intentionally separate.
          </p>
        </div>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            data-action-id="amd.refresh_evidence"
            className="inline-flex items-center gap-2 self-start rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-60"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh evidence status
          </button>
        )}
      </div>

      {loading && !capability && (
        <div className="px-5 py-6 text-sm text-slate-500">Loading verified AMD evidence…</div>
      )}

      {error && (
        <div className="mx-5 mt-5 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800" data-testid="amd-evidence-error">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Evidence API unavailable: {error}. No historical or live claim is inferred.</span>
        </div>
      )}

      {capability && campaign && quality && runtime && (
        <div className="grid grid-cols-1 gap-4 p-5 xl:grid-cols-3">
          <article className="rounded-xl border border-blue-200 bg-blue-50/60 p-4" data-testid="amd-historical-plane">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h4 className="flex items-center gap-2 text-sm font-bold text-blue-950">
                <CheckCircle className="h-4 w-4 text-blue-700" /> Historical verified campaign
              </h4>
              <span className="rounded border border-blue-200 bg-white px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-blue-800">
                Frozen evidence
              </span>
            </div>
            <div className="text-2xl font-black text-blue-950" data-testid="amd-historical-resolved">
              {quality.cases_resolved} / {quality.cases_evaluated} resolved
            </div>
            <div className="mt-1 text-xs font-semibold text-blue-800" data-testid="amd-historical-scope">
              Staged composite · not a uniform production-prompt run
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-blue-950">
              <dt>Source coverage</dt><dd className="text-right font-bold">{quality.source_coverage_rate_pct}%</dd>
              <dt>Nonce binding</dt><dd className="text-right font-bold">{quality.nonce_binding_rate_pct}%</dd>
              <dt>Normalized JSON</dt><dd className="text-right font-bold">{quality.normalized_json_rate_pct}%</dd>
              <dt>Strict raw JSON</dt><dd className="text-right font-bold">{quality.strict_raw_json_rate_pct}%</dd>
              <dt>Provider errors</dt><dd className="text-right font-bold">{quality.provider_error_count}</dd>
              <dt>Direct-endpoint fallback</dt><dd className="text-right font-bold">{quality.fallback_count}</dd>
            </dl>
            <p className="mt-3 text-[11px] leading-relaxed text-blue-800">
              One raw response contained trailing text after a recoverable JSON object. The historical campaign exercised the direct vLLM endpoint, not the application fallback path.
            </p>
          </article>

          <article className="rounded-xl border border-slate-200 bg-slate-50 p-4" data-testid="amd-current-runtime-plane">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h4 className="flex items-center gap-2 text-sm font-bold text-slate-900">
                <Server className="h-4 w-4 text-slate-600" /> Current runtime configuration
              </h4>
              <span className={`rounded border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${runtime.configured ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-slate-200 bg-white text-slate-600'}`}>
                {runtime.configured ? 'Configured only' : 'Not configured'}
              </span>
            </div>
            <div className="text-sm font-black text-slate-900" data-testid="amd-current-runtime-status">
              {runtime.configured ? 'Configured — not live verified by this read-only check' : 'Not configured in this process'}
            </div>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-slate-700">
              <dt>Provider</dt><dd className="text-right font-semibold">{runtime.configured ? runtime.provider || 'Reported by server' : 'Not claimed'}</dd>
              <dt>Accelerator</dt><dd className="text-right font-semibold">{runtime.configured ? runtime.accelerator || 'Reported by server' : 'Not claimed'}</dd>
              <dt>Runtime</dt><dd className="text-right font-semibold">{runtime.configured ? runtime.runtime || 'Reported by server' : 'Not claimed'}</dd>
              <dt>Served model</dt><dd className="text-right font-semibold">{runtime.configured ? runtime.served_model || 'Not reported' : 'Not claimed'}</dd>
              <dt>Endpoint present</dt><dd className="text-right font-semibold">{runtime.endpoint_present ? 'Yes' : 'No'}</dd>
              <dt>API key present</dt><dd className="text-right font-semibold">{runtime.api_key_present ? 'Yes (value hidden)' : 'No'}</dd>
            </dl>
            <p className="mt-3 text-[11px] leading-relaxed text-slate-500">{runtime.note}</p>
          </article>

          <article className="rounded-xl border border-slate-200 bg-white p-4" data-testid="amd-current-request-plane">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h4 className="flex items-center gap-2 text-sm font-bold text-slate-900">
                <Activity className="h-4 w-4 text-slate-600" /> Current request result
              </h4>
              <span className={`rounded border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${toneClasses(requestView.tone)}`}>
                Per request
              </span>
            </div>
            <div className={`rounded-lg border px-3 py-2 text-sm font-black ${toneClasses(requestView.tone)}`} data-testid="amd-current-request-status">
              {requestView.label}
            </div>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-slate-700">
              <dt>Request ID</dt><dd className="truncate text-right font-semibold">{request?.request_id || '—'}</dd>
              <dt>Verified at</dt><dd className="text-right font-semibold">{request?.verified_at || '—'}</dd>
              <dt>Latency</dt><dd className="text-right font-semibold">{request?.latency_ms != null ? `${request.latency_ms} ms` : '—'}</dd>
              <dt>Fallback used</dt><dd className="text-right font-semibold">{request?.fallback_used == null ? '—' : request.fallback_used ? 'Yes' : 'No'}</dd>
              <dt>Human Review</dt><dd data-testid="amd-human-review-status" className="text-right font-semibold">Required</dd>
            </dl>
            <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-relaxed text-slate-500">
              <Clock className="mt-0.5 h-3 w-3 shrink-0" /> {request?.note || 'A live provider claim is created only after a nonce-bound request completes.'}
            </p>
            {request?.provider_error && (
              <p className="mt-2 flex items-start gap-1.5 rounded border border-red-200 bg-red-50 p-2 text-[11px] text-red-800">
                <ShieldAlert className="mt-0.5 h-3 w-3 shrink-0" /> {request.provider_error}
              </p>
            )}
          </article>
        </div>
      )}
    </section>
  );
}
