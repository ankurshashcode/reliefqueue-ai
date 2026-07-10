# AI Boundary

AI use in ReliefQueue is optional, advisory, and review-required. Deterministic local behavior must remain available when no provider is configured.

## Default modes

```bash
make ai-endpoint-smoke AI_MODE=mock
make bad-ai-endpoint-smoke
make no-secrets
```

`AI_MODE=none` and `AI_MODE=mock` must remain safe local paths. Missing external provider configuration should be a clear SKIP/degraded PASS, not a hidden failure.

## OpenAI-compatible endpoint boundary

Real provider smoke may be run with an OpenAI-compatible endpoint only when secrets are passed through environment variables and logs redact secret values. Diagnostics should show sanitized endpoint/model, HTTP/provider failure class, parsed JSON keys when available, and validation reason. Do not print the full shell environment or private report text.

AI output must be a flat advisory object that passes strict validation. Successful provider output must still set human review required and must not overwrite deterministic dispatch, rescue, safety, closure, or verified-location fields.

## AMD/vLLM readiness

The boundary is provider-independent: models should be replaceable per job. Local/self-hosted vLLM on AMD hardware is a future deployment option, not a requirement for deterministic demos.

Keep the adapter compatible with OpenAI-style chat/completion endpoints where practical, but do not add provider-specific assumptions to the crisis workflow.

## Fallback rule

If AI is unavailable, slow, malformed, or unsafe, ReliefQueue keeps the deterministic queue output and reports the AI limitation clearly. Operators should still be able to run demos, privacy checks, dashboard checks, and live infrastructure proof without real AI.
