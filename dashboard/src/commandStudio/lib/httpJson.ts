export async function readJsonResponse<T>(response: Response, context: string): Promise<T> {
  const contentType = (response.headers.get('content-type') || '').toLowerCase();
  const body = await response.text();

  if (!body.trim()) {
    throw new Error(`${context}: backend returned an empty response (HTTP ${response.status}).`);
  }

  if (!contentType.includes('application/json')) {
    const localHint = response.url.includes(':5173')
      ? ' The local dashboard API proxy is not connected to the Product API.'
      : '';
    throw new Error(`${context}: backend returned non-JSON content (HTTP ${response.status}).${localHint}`);
  }

  let payload: any;
  try {
    payload = JSON.parse(body);
  } catch {
    throw new Error(`${context}: backend returned malformed JSON (HTTP ${response.status}).`);
  }

  if (!response.ok) {
    throw new Error(String(payload?.error || payload?.message || `${context} failed with HTTP ${response.status}`));
  }

  return payload as T;
}
