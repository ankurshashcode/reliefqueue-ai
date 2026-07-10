export const config = {
  // @ts-ignore
  apiOrigin: import.meta.env.VITE_RELIEFQUEUE_PUBLIC_API_ORIGIN || '',
  // @ts-ignore
  demoMode: import.meta.env.VITE_RELIEFQUEUE_DEMO_MODE !== 'false',
  // @ts-ignore
  featureAmdImpact: import.meta.env.VITE_RELIEFQUEUE_FEATURE_AMD_IMPACT === 'true',
  // @ts-ignore
  featureLiveApi: import.meta.env.VITE_RELIEFQUEUE_FEATURE_LIVE_API === 'true',
};

export function isApiConfigured() {
  return config.apiOrigin !== '';
}
