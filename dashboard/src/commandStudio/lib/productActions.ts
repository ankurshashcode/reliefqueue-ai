export function actionKey(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export async function postProduct<T>(endpoint: string, payload: Record<string, unknown>, fallback: T): Promise<T> {
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json() as T;
  } catch (error) {
    console.warn(`ReliefQueue product action fallback for ${endpoint}`, error);
    return fallback;
  }
}
