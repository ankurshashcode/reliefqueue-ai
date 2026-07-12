export interface AmdDeploymentEvidence {
  provider: string;
  accelerator: string;
  runtime: string;
  served_model: string;
  underlying_model: string | null;
  underlying_model_provenance?: string;
}

export interface AmdResolvedQuality {
  cases_evaluated: number;
  cases_resolved: number;
  overall_pass_rate_pct: number;
  normalized_json_rate_pct: number;
  strict_raw_json_rate_pct: number;
  strict_raw_json_anomaly_case_ids: string[];
  nonce_binding_rate_pct: number;
  source_coverage_rate_pct: number;
  semantic_completeness_avg_pct: number;
  review_required_output_count: number;
  provider_error_count: number;
  fallback_count: number;
  completion_tokens_per_second_avg: number;
  latency_ms_p50: number;
  latency_ms_p95: number;
  latency_ms_max: number;
}

export interface AmdHistoricalCampaign {
  schema_version: string;
  campaign_id: string;
  campaign_label: string;
  campaign_type: 'staged_composite' | string;
  uniform_prompt_run: boolean;
  direct_vllm_endpoint_only: boolean;
  application_fallback_exercised: boolean;
  generated_at_utc: string;
  deployment: AmdDeploymentEvidence;
  final_resolved_quality: AmdResolvedQuality;
  case_mix: {
    single_report: number;
    complex_dossier: number;
    adversarial: number;
  };
  limitations: string[];
}

export interface AmdRuntimePlane {
  status: string;
  configured: boolean;
  live_request_verified: boolean;
  provider: string | null;
  accelerator: string | null;
  runtime: string | null;
  served_model: string | null;
  underlying_model: string | null;
  endpoint_present: boolean;
  api_key_present: boolean;
  human_review_required: boolean;
  fallback_available: boolean;
  note: string;
}

export interface CurrentRequestPlane {
  attempted: boolean;
  pending?: boolean;
  verified_live: boolean;
  fallback_used: boolean | null;
  provider_error: string | null;
  request_id?: string | null;
  verified_at?: string | null;
  latency_ms?: number | null;
  served_model?: string | null;
  underlying_model?: string | null;
  note?: string;
}

export interface AmdCapabilityPayload {
  status: string;
  historical_evidence: AmdHistoricalCampaign;
  live_runtime: AmdRuntimePlane;
  current_request: CurrentRequestPlane;
}

export async function fetchAmdCapability(): Promise<AmdCapabilityPayload> {
  const response = await fetch('/api/product/amd/capability', { cache: 'no-store' });
  if (!response.ok) throw new Error(`AMD capability HTTP ${response.status}`);
  const payload = await response.json() as AmdCapabilityPayload;
  if (payload?.status !== 'ok' || !payload?.historical_evidence || !payload?.live_runtime) {
    throw new Error('AMD capability response is incomplete');
  }
  return payload;
}

export function pendingCurrentRequest(note = 'Live verification request is in progress.'): CurrentRequestPlane {
  return {
    attempted: true,
    pending: true,
    verified_live: false,
    fallback_used: null,
    provider_error: null,
    note,
  };
}

export function currentRequestFromLiveResult(result: any): CurrentRequestPlane {
  return {
    attempted: true,
    pending: false,
    verified_live: result?.verified_live === true && result?.fallback_used === false,
    fallback_used: typeof result?.fallback_used === 'boolean' ? result.fallback_used : null,
    provider_error: result?.error ? String(result.error) : null,
    request_id: result?.request_id ? String(result.request_id) : null,
    verified_at: result?.verified_at ? String(result.verified_at) : null,
    latency_ms: typeof result?.latency_ms === 'number' ? result.latency_ms : null,
    served_model: result?.served_model ? String(result.served_model) : null,
    underlying_model: result?.underlying_model ? String(result.underlying_model) : null,
    note: result?.verification_failure_reason
      ? String(result.verification_failure_reason)
      : result?.verified_live === true && result?.fallback_used === false
        ? 'Nonce-bound provider response verified live for this request.'
        : result?.fallback_used === true
          ? 'A deterministic/local fallback was used; this request is not live AMD evidence.'
          : 'The request did not establish verified-live AMD status.',
  };
}

export function currentRequestFromBurstResult(result: any): CurrentRequestPlane {
  const verified = result?.verified_live === true
    && Number(result?.fallback_responses || 0) === 0
    && Number(result?.failed || 0) === 0;
  return {
    attempted: true,
    pending: false,
    verified_live: verified,
    fallback_used: Number(result?.fallback_responses || 0) > 0,
    provider_error: Number(result?.failed || 0) > 0 ? `${result.failed} burst case(s) failed` : null,
    request_id: result?.batch_id ? String(result.batch_id) : null,
    verified_at: result?.completed_at ? String(result.completed_at) : null,
    latency_ms: typeof result?.median_latency_ms === 'number' ? result.median_latency_ms : null,
    served_model: result?.served_model ? String(result.served_model) : null,
    underlying_model: result?.model_metadata?.underlying_model ? String(result.model_metadata.underlying_model) : null,
    note: verified
      ? 'Burst completed without fallback and was verified live for this request set.'
      : 'Burst results are not counted as verified live when any case fails or uses fallback.',
  };
}

export function buildReviewerNotes(
  capability: AmdCapabilityPayload | null,
  currentRequest: CurrentRequestPlane | null,
): string {
  if (!capability) {
    return [
      'ReliefQueue AMD/vLLM evidence is unavailable from the current Product API.',
      'Human review remains required.',
    ].join('\n');
  }
  const campaign = capability.historical_evidence;
  const quality = campaign.final_resolved_quality;
  const runtime = capability.live_runtime;
  const request = currentRequest || capability.current_request;
  return [
    `Historical campaign: ${campaign.campaign_id}`,
    `Campaign type: ${campaign.campaign_type} (uniform prompt run: ${campaign.uniform_prompt_run})`,
    `Resolved cases: ${quality.cases_resolved}/${quality.cases_evaluated}`,
    `Source coverage: ${quality.source_coverage_rate_pct}%`,
    `Nonce binding: ${quality.nonce_binding_rate_pct}%`,
    `Normalized JSON: ${quality.normalized_json_rate_pct}%`,
    `Strict raw JSON: ${quality.strict_raw_json_rate_pct}%`,
    `Historical provider: ${campaign.deployment.provider}`,
    `Historical accelerator: ${campaign.deployment.accelerator}`,
    `Historical runtime: ${campaign.deployment.runtime}`,
    `Historical served model: ${campaign.deployment.served_model}`,
    `Current runtime: ${runtime.configured ? 'configured but not live-verified by the read-only status endpoint' : 'not configured in this process'}`,
    `Current request: ${request?.attempted ? (request.verified_live ? 'verified live' : request.pending ? 'in progress' : 'not verified live') : 'not attempted'}`,
    `Application fallback exercised by historical campaign: ${campaign.application_fallback_exercised}`,
    'Human review: required',
  ].join('\n');
}
