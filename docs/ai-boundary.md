# AI Boundary

AI in ReliefQueue is optional, advisory, and review-required. The deterministic workflow must remain available when no provider is configured or when a provider fails.

## Deterministic default

Safe local checks:

```bash
make ai-endpoint-smoke AI_MODE=mock
make bad-ai-endpoint-smoke
make no-secrets
```

`AI_MODE=none` and `AI_MODE=mock` must remain usable. Missing provider configuration should produce a clear offline, skipped, or degraded state—not a false live claim.

## Provider boundary

ReliefQueue uses an OpenAI-compatible adapter so the workflow is not tied to one model vendor. Secrets are supplied through server-side environment variables and must never appear in browser code, logs, public exports, or screenshots.

Diagnostics may expose sanitized provider labels, model labels, status classes, latency, token counts, parsed-key summaries, and validation reasons. They must not expose credentials, full environments, or private report text.

## Output contract

Provider output must:

- pass strict schema and semantic checks;
- preserve source coverage for dossier inputs;
- remain bound to the request challenge where live verification is used;
- state that human review is required;
- never overwrite deterministic dispatch, rescue, safety, closure, or verified-location fields.

## AMD/vLLM path

ReliefQueue has a verified historical campaign on AMD Developer Cloud using AMD Instinct MI300X and vLLM. That evidence is documented in [amd-evidence.md](amd-evidence.md).

The ordinary workflow advisory is deterministic and must not be described as live AMD inference. A current request is live only when its request-level verification contract passes.

## Failure and fallback

When AI is unavailable, slow, malformed, incomplete, or unsafe:

1. keep the deterministic queue result;
2. show the provider limitation clearly;
3. do not label the request verified;
4. do not hide fallback use;
5. keep human review required.

Provider failure must not block local demos, privacy checks, field workflows, public exports, or deterministic submission validation.
