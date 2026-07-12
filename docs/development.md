# Development and Deployment

This is the technical setup reference. Start with `README.md` for the product and judge story.

## Repository structure

```text
src/reliefqueue/      Python intake, triage, exports, API, and optional integrations
dashboard/            React/TypeScript/Vite role workspaces
fixtures/             Synthetic reports and frozen AMD evidence
schemas/              Data and integration schemas
scripts/              Validation, evidence, deployment, and submission tools
tests/                Repository contract and behavior tests
docs/                 Living documentation
reports/               Generated local evidence; ignored by Git
```

## Local setup

Requirements: Python 3.11+ and Node.js.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
npm --prefix dashboard ci
npm --prefix dashboard exec playwright install chromium
```

## Run the product

Generate deterministic demo data:

```bash
make run-demo-local
```

Start the interactive dashboard:

```bash
AI_MODE=mock make dashboard
```

Key local routes are printed by the launcher. The common routes are:

```text
/dashboard?source=latest
/dashboard/assignments
/dashboard/amd-impact
/dashboard/capability-map
/field/my-work
/field/my-cases?worker_id=worker-alpha-boat
/field/outbox
/local-coordinator?source=latest
```

## Replit deployment

The public deployment uses one Python process and one web port. It serves:

- the built dashboard from `dashboard/dist`;
- the JSON product API from the same origin;
- SPA fallback for Command Center, Field Coordinator, and Local Coordinator routes;
- `GET /api/health` for health checks.

Commands:

```bash
make replit-build
make replit-run
make replit-smoke
make replit-navigation-smoke
```

Unknown static assets return 404 instead of the SPA shell.

## Validation matrix

| Change | Minimum validation |
| --- | --- |
| Python behavior | `make test` |
| Dashboard UI | `npm --prefix dashboard run build` and `npm --prefix dashboard run product-complete-smoke` |
| Public export/privacy | `make privacy-check` and `make security-check` |
| Submission | `make submission-final-gate` |
| Deployed URL | `RELIEFQUEUE_PUBLIC_URL=... make submission-public-check` |
| Live AMD | Explicit trusted run of `submission-live-amd-check` |

Useful full sequence:

```bash
make test
npm --prefix dashboard run build
npm --prefix dashboard run product-complete-smoke
make privacy-check
make submission-final-gate
```

## Provider configuration

The deterministic product needs no external provider. The public demo can remain available in deterministic mode while the paid AMD GPU endpoint is stopped.

Live inference uses the provider-independent OpenAI-compatible adapter. Credentials are server-side only.

### AMD/vLLM deployment

```bash
AI_MODE=openai_compatible
OPENAI_COMPAT_BASE_URL=https://protected-vllm-host.example/v1
OPENAI_COMPAT_API_KEY=server-secret
OPENAI_COMPAT_MODEL=reliefqueue-amd

AI_PROVIDER_LABEL="AMD Developer Cloud"
AI_ACCELERATOR_LABEL="AMD Instinct MI300X"
AI_RUNTIME_LABEL="vLLM 0.23.0+rocm723"
OPENAI_COMPAT_UNDERLYING_MODEL="Qwen/Qwen2.5-7B-Instruct"

AI_RESPONSE_FORMAT=json_object
AI_SEND_PRIVATE_TEXT=false
```

### Connect a judge-supplied inference server

ReliefQueue can use any model exposed through an **OpenAI-compatible Chat Completions endpoint**. Other proprietary protocols require an adapter.

Configure:

```bash
AI_MODE=openai_compatible
OPENAI_COMPAT_BASE_URL=https://your-inference-host/v1
OPENAI_COMPAT_API_KEY=your-secret
OPENAI_COMPAT_MODEL=your-served-model

AI_PROVIDER_LABEL="Judge-supplied inference server"
AI_ACCELERATOR_LABEL="Judge-managed hardware"
AI_RUNTIME_LABEL="OpenAI-compatible inference API"
OPENAI_COMPAT_UNDERLYING_MODEL="your-underlying-model"

AI_TIMEOUT_SECONDS=60
AI_MAX_RETRIES=1
AI_MAX_BATCH_SIZE=16
AI_RESPONSE_FORMAT=json_object
AI_SEND_PRIVATE_TEXT=false
AI_HTTP_USER_AGENT="ReliefQueueAI/0.1 OpenAICompatibleClient"
```

ReliefQueue sends:

```text
POST <OPENAI_COMPAT_BASE_URL>/chat/completions
```

The server must return the normal OpenAI-compatible response shape containing `choices[0].message.content`. The model should return the structured JSON requested by the prompt.

If the server rejects the OpenAI `response_format` field, use:

```bash
AI_RESPONSE_FORMAT=none
```

Test before opening the product:

```bash
make ai-endpoint-smoke
make dashboard
```

For a Replit remix, add the same variables under **Secrets**, then run:

```bash
make replit-build
make replit-run
```

A judge cannot replace credentials inside the published ReliefQueue deployment. Provider credentials must never be placed in frontend variables, source files, screenshots, or public evidence.

The provider, accelerator, runtime, and underlying-model labels must describe the connected server truthfully. A non-AMD endpoint proves adapter portability; it is not current AMD execution.

## Generated artifacts

Generated outputs live under `reports/` and are not source-controlled. Clean them with:

```bash
make clean-reports
```

The authoritative historical AMD fixture is tracked at:

```text
fixtures/amd_evidence_campaign_v1.json
```

## Advanced infrastructure

Optional PostGIS, Redis, NATS, mutation, logistics, volunteer, and host-proof workflows are documented in [operations.md](operations.md). They are not required for the public deterministic demo.
