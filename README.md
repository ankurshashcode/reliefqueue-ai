# ReliefQueue AI

**Human-reviewed disaster-relief coordination, with deterministic workflows and optional AMD-accelerated AI analysis.**

[Live application](https://reliefqueue-ai--ankurshashcode.replit.app) · [Hackathon submission guide](HACKATHON.md) · [Verified AMD evidence](docs/amd-evidence.md)

ReliefQueue AI turns fragmented disaster reports into a structured relief queue. It helps coordinators review urgency, identify missing information and likely duplicates, group incidents by operation zone, propose assignments, track field updates, and prepare redacted public summaries.

The public demo uses synthetic or replayed scenarios. AI output is advisory only. A human remains responsible for priority, assignment, field instructions, public communication, and case closure.

## Why it matters

Disaster response teams often receive incomplete, duplicated, and rapidly changing reports through multiple channels. ReliefQueue provides one reviewable workflow for:

- crisis intake and triage;
- duplicate and missing-information review;
- zone and assignment coordination;
- field-worker task updates and offline outbox handling;
- redacted public reporting;
- optional structured analysis through AMD Developer Cloud and vLLM.

## Judge demo

Open the [live application](https://reliefqueue-ai--ankurshashcode.replit.app) and select **Judge Demo Walkthrough**.

The walkthrough demonstrates:

1. intake of a synthetic incident report;
2. deterministic queue and assignment support;
3. optional live AMD analysis with explicit synthetic-data consent;
4. historical AMD campaign evidence and current-request verification;
5. handoff to the Field Coordinator workspace;
6. human-review and privacy boundaries.

Useful routes:

| Surface | Route |
| --- | --- |
| Command Center | `/dashboard?source=latest` |
| AI Intake | `/dashboard/intake` |
| Assignments | `/dashboard/assignments` |
| AMD Impact | `/dashboard/amd-impact` |
| Capability Map | `/dashboard/capability-map` |
| Field Coordinator | `/field/my-work` |
| Local Coordinator | `/local-coordinator?source=latest` |

See [HACKATHON.md](HACKATHON.md) for the copy-ready submission text and full judge script.

## How it works

```text
Synthetic reports
      │
      ▼
Deterministic Python intake and triage
      │
      ├── safe summaries, urgency suggestions, missing fields, duplicates
      ├── operation zones and assignment candidates
      └── public/private export boundary
      │
      ▼
React/Vite role workspaces
      ├── Command Center
      ├── Field Coordinator
      └── Local Coordinator
      │
      └── optional, consent-gated live AI request
              ▼
      AMD Developer Cloud → AMD Instinct MI300X → vLLM
```

The deployed demo uses one origin: the Python product API serves the built dashboard and JSON endpoints. The deterministic workflow remains usable when no AI provider is configured.

## AMD and vLLM

ReliefQueue separates three kinds of evidence:

- **Historical evidence:** a frozen, verified AMD/vLLM campaign.
- **Live runtime status:** whether the deployed API is currently configured for a provider.
- **Current-request proof:** evidence returned only after a successful live request.

Verified historical campaign:

| Item | Result |
| --- | --- |
| Platform | AMD Developer Cloud |
| Accelerator | AMD Instinct MI300X |
| Runtime | vLLM 0.23.0+rocm723 |
| Served model | `reliefqueue-amd` |
| Underlying model | `Qwen/Qwen2.5-7B-Instruct` |
| Case mix | 8 single reports, 8 complex dossiers, 8 adversarial cases |
| Resolved | 24/24 |
| Normalized JSON | 100% |
| Nonce binding | 100% |
| Source coverage | 100% |
| Strict raw JSON | 95.83% |
| Fallbacks | 0 |
| Human review required | 24/24 |

This was a staged composite evidence campaign, not one uniform production-prompt benchmark. The project does not claim that no other hardware or model could process the same input.

Full metrics, limitations, and reproduction commands are in [docs/amd-evidence.md](docs/amd-evidence.md).

## Connect your own inference server

The public demo may use deterministic mode when the paid AMD GPU endpoint is stopped. Judges can independently test the AI adapter by cloning or remixing the repository and connecting any model served through an **OpenAI-compatible Chat Completions API**.

Configure these server-side variables:

```bash
AI_MODE=openai_compatible
OPENAI_COMPAT_BASE_URL=https://your-inference-host/v1
OPENAI_COMPAT_API_KEY=your-secret
OPENAI_COMPAT_MODEL=your-served-model

AI_PROVIDER_LABEL="Judge-supplied inference server"
AI_ACCELERATOR_LABEL="Judge-managed hardware"
AI_RUNTIME_LABEL="OpenAI-compatible inference API"
OPENAI_COMPAT_UNDERLYING_MODEL="your-underlying-model"

AI_RESPONSE_FORMAT=json_object
AI_SEND_PRIVATE_TEXT=false
```

Then verify and run:

```bash
make ai-endpoint-smoke
make dashboard
```

ReliefQueue calls `POST <OPENAI_COMPAT_BASE_URL>/chat/completions` and expects `choices[0].message.content`. Use `AI_RESPONSE_FORMAT=none` if the server rejects the OpenAI `response_format` option.

Judges cannot change credentials on the published deployment; they must use their own clone or remix. A non-AMD server demonstrates adapter portability and must not be presented as current AMD execution. Full setup details are in [docs/development.md](docs/development.md#connect-a-judge-supplied-inference-server).

## Safety and privacy

ReliefQueue may suggest urgency, duplicates, missing information, zones, assignments, and reply drafts. It must not claim automatic dispatch, confirmed rescue, confirmed safety, guaranteed location, or AI verification of an emergency.

Public exports are allowlist-based and exclude raw report text, direct contact details, exact private addresses, internal notes, unnecessary medical details, credentials, and unredacted media. Field workers receive only the information needed for their assigned task.

See [docs/safety-boundary.md](docs/safety-boundary.md) and [docs/ai-boundary.md](docs/ai-boundary.md).

## Run locally

Requirements: Python 3.11+ and Node.js.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
npm --prefix dashboard ci

make run-demo-local
AI_MODE=mock make dashboard
```

The dashboard command prints the local URL. Generated demo reports are written under `reports/latest/` and are ignored by Git.

For the single-process deployment used on Replit:

```bash
make replit-build
make replit-run
```

## Validate

```bash
make test
npm --prefix dashboard run build
npm --prefix dashboard run product-complete-smoke
make privacy-check
make submission-final-gate
```

Check a deployed URL without making provider calls:

```bash
RELIEFQUEUE_PUBLIC_URL=https://your-public-url.example make submission-public-check
```

Run the separate, opt-in live AMD proof only with synthetic input and trusted server-side credentials:

```bash
RELIEFQUEUE_PUBLIC_URL=https://your-public-url.example \
RELIEFQUEUE_CONFIRM_LIVE_AMD=YES make submission-live-amd-check
```

## Technical and operator references

| Document | Purpose |
| --- | --- |
| [HACKATHON.md](HACKATHON.md) | Submission copy, judging narrative, and walkthrough |
| [docs/amd-evidence.md](docs/amd-evidence.md) | Verified campaign, live-proof rules, and limitations |
| [docs/development.md](docs/development.md) | Setup, architecture, deployment, and validation |
| [docs/operations.md](docs/operations.md) | Advanced drills, live-stack proof, and generated evidence |
| [docs/safety-boundary.md](docs/safety-boundary.md) | Human-review, privacy, field, and export rules |
| [docs/ai-boundary.md](docs/ai-boundary.md) | Deterministic fallback and provider boundary |
| [docs/pilot-readiness.md](docs/pilot-readiness.md) | Work required before real-world use |
| [docs/index.md](docs/index.md) | Complete documentation map |

Advanced host proof remains available through:

```bash
make phase01-host-preflight
make phase01-live-proof
make phase01-live-clean
```

Discover less-common commands through the operator catalog:

```bash
make operator
make operator-search QUERY="test live integration"
make operator-scope ACTION=phase01_live_stack
```
