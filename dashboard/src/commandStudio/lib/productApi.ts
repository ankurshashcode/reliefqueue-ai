import { isApiConfigured, config } from './publicConfig';
import { actionLog } from './actionLog';

async function fetchWithFallback<T>(endpoint: string, options: RequestInit, fallbackData: T, actionName: string, actionType: any): Promise<T> {
  if (isApiConfigured()) {
    try {
      actionLog.add(actionName, actionType, 'Success', { endpoint, options });
      const res = await fetch(`${config.apiOrigin}${endpoint}`, options);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json() as T;
    } catch (err: any) {
      actionLog.add(`${actionName} - Failed`, actionType, 'Error', { error: err.message });
      console.error('API Error, falling back to local demo data:', err);
    }
  }
  
  // Local Demo Fallback
  actionLog.add(actionName, actionType, 'Local Demo Fallback', { endpoint });
  return fallbackData;
}

export const productApi = {
  getOverview: () => fetchWithFallback('/api/product/command/overview', {}, { cases: 1248 }, 'Get Overview', 'API Call'),
  normalizeMessage: (payload: any) => fetchWithFallback('/api/product/messaging/webhook', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }, { 
    normalized: true, 
    source: payload.source,
    urgency: 'Medium',
    needType: 'General',
    human_review_required: true 
  }, 'Normalize Message', 'Normalization'),
  getAdvisory: (caseId: string, idempotencyKey: string) => fetchWithFallback('/api/product/command/ai-advisory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id: caseId, idempotency_key: idempotencyKey })
  }, {
    case_id: caseId,
    safe_summary: 'Locally generated safe summary placeholder.',
    missing_info_questions: ['What is the exact location?'],
    reply_draft: 'We received your report. A coordinator will review it.',
    operator_note: 'Demo mode: this is a local fallback advisory.',
    warnings: ['Location confidence is low.'],
    ai_status: 'Local Demo',
    ai_provider: 'fallback',
    human_review_required: true
  }, 'Request AI Advisory', 'Advisory Gen'),
};
