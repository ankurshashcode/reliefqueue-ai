# AMD and vLLM Evidence

This document defines what ReliefQueue can truthfully claim about AMD execution.

## Evidence model

ReliefQueue keeps three evidence planes separate:

| Plane | Meaning | Source |
| --- | --- | --- |
| Historical evidence | A frozen campaign that was previously verified | `fixtures/amd_evidence_campaign_v1.json` |
| Live runtime | Whether the deployed backend is currently configured and reachable | `/api/product/amd/capability` |
| Current request | Proof returned for one live request | `/api/ai/live-verification` or `/api/ai/burst-verification` |

Historical evidence does not prove that the current deployment is connected. Runtime configuration does not prove that a particular request reached the provider. Only current-request evidence can verify the current request.

## Verified historical campaign

Campaign: `reliefqueue-amd-eval-v1`

| Item | Value |
| --- | --- |
| Scope | Historical verified campaign |
| Type | Staged composite |
| Uniform prompt run | No |
| Provider | AMD Developer Cloud |
| Accelerator | AMD Instinct MI300X |
| Runtime | vLLM 0.23.0+rocm723 |
| Served model | `reliefqueue-amd` |
| Underlying model | `Qwen/Qwen2.5-7B-Instruct` |
| Direct vLLM endpoint | Yes |
| Application fallback exercised | No |

Final resolved quality:

| Metric | Result |
| --- | --- |
| Cases evaluated/resolved | 24/24 |
| Case mix | 8 single reports, 8 complex dossiers, 8 adversarial cases |
| Overall pass rate | 100% |
| Normalized JSON validity | 100% |
| Strict raw JSON validity | 95.83% |
| Nonce binding | 100% |
| Source coverage | 100% |
| Average semantic completeness | 90.65% |
| Review-required outputs | 24 |
| Provider errors | 0 |
| Fallbacks | 0 |
| Median latency | 1133.662 ms |
| P95 latency | 1741.063 ms |
| Maximum latency | 2086.16 ms |
| Average completion throughput | 225.975 tokens/s |

One case, `single-002`, contained trailing text after a recoverable JSON object. It passed normalized JSON validation but not strict raw JSON validation. This is why the strict rate is 95.83%, not 100%.

## Campaign stages

The campaign was intentionally iterative:

1. **Baseline and load:** exposed output-budget truncation while collecting concurrency and GPU evidence.
2. **Calibration:** removed truncation and tightened compact structured output.
3. **Semantic repair:** improved per-source accounting and operational tags for targeted cases.
4. **Final closure:** corrected the last oxygen/medical tagging omission.

The final 24-case result selects the resolved evidence for each case across these stages. It must not be described as one uniform prompt run.

## Live verification contract

A response may display **VERIFIED LIVE** only when all applicable checks pass:

- the provider transport succeeds;
- a provider request identifier is present;
- the response is bound to the request challenge nonce;
- the structured advisory validates;
- no deterministic fallback was used;
- the input was explicitly confirmed as synthetic;
- `human_review_required` remains true.

A configured endpoint, a successful health check, or historical evidence alone is not enough.

## Workload modes

The public AMD Impact surface supports:

- single incident;
- complex dossier;
- bounded burst workload of up to 24 synthetic reports.

Public routes enforce input-size, concurrency, per-client, and global budgets. Credentials remain server-side.

## Reproduce the checks

Offline evidence validation makes no provider calls:

```bash
make amd-quality-offline-validation
```

A trusted live validation requires explicit consent and server-side provider configuration:

```bash
RELIEFQUEUE_CONFIRM_LIVE_AMD=YES \
AI_MODE=openai_compatible \
make amd-quality-live-validation
```

Check a deployed app without provider calls:

```bash
RELIEFQUEUE_PUBLIC_URL=https://your-public-url.example \
make submission-public-check
```

Run the separate live deployment proof:

```bash
RELIEFQUEUE_PUBLIC_URL=https://your-public-url.example \
RELIEFQUEUE_CONFIRM_LIVE_AMD=YES \
make submission-live-amd-check
```

## Claim boundary

Supported claim:

> AMD Instinct MI300X with vLLM made concurrent, structured humanitarian analysis operationally practical and measurable for the verified ReliefQueue campaign.

Unsupported claims:

- every product action or page view used AMD;
- the deterministic advisory is live inference;
- historical evidence proves current connectivity;
- AMD is the only hardware capable of processing the workload;
- the model made final relief or dispatch decisions.

The underlying-model name comes from the ReliefQueue deployment configuration and final-gate evidence. The final OpenAI-compatible response directly verified the served model name, not the underlying-model provenance.
