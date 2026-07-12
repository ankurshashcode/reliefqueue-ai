# ReliefQueue AI

> ReliefQueue AI is presented as a public disaster-relief coordination workflow: field teams use simple role-scoped screens, local coordinators manage zones and assignments, and command-center operators use the portal for safe runtime changes and audit review.

ReliefQueue AI is a synthetic crisis-intake and coordination system. It turns disaster-style reports into a human-reviewed relief queue with safe summaries, urgency suggestions, missing-information flags, duplicate groups, operation-zone tags, assignment candidates, public redacted exports, and optional live infrastructure proof.

The repository is command-led. Start with the operator catalog to run the public relief workflow:

```bash
make change-guide
make operator
make operator-search QUERY="test live integration"
make operator-scope ACTION=phase01_live_stack
```

Before changing code or docs: `make change-guide`.

## Common operator paths

### Run the deterministic local demo

```bash
make run-demo-local
make export-report
make privacy-check
```

Generated demo outputs are written under `reports/latest/`. They are synthetic, but private operator files may still contain raw demo report text and contact-like fixture fields. Clean generated reports with:

```bash
make clean-reports
```

### Check dashboard and field-worker views

For a fresh checkout, install deterministic Python and dashboard dependencies once:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
npm --prefix dashboard ci
npm --prefix dashboard exec playwright install chromium
```

Then run the product checks:

```bash
make dashboard-build
make dashboard-smoke
make field-smoke
make visual-port-smoke
make messaging-channel-smoke
```

For an interactive local product stack, run:

```bash
AI_MODE=mock make dashboard
```

Expected local routes on the printed Vite port include:

```text
/dashboard?source=latest
/dashboard/assignments
/dashboard/amd-impact
/field/my-work
/field/my-cases?worker_id=worker-alpha-boat
/field/cases/RQ-1042
/field/outbox
/local-coordinator?source=latest
```

The command-center portal includes a Messaging Channels panel for local SMS, WhatsApp, and voice helpline flow review:

```text
/dashboard
```


### Offline and efficiency design

The Field Coordinator keeps pending updates in a versioned localStorage outbox and disables network replay while offline, avoiding repeated failed sync attempts until connectivity returns. Command Center and role-specific screens are loaded as separate production chunks, reducing the initial JavaScript required for each route. Printed case, assignment, outbox, and AMD-impact views support low-connectivity handoff without exposing raw private intake text or secrets.

Validate these boundaries with:

```bash
npm --prefix dashboard run build
npm --prefix dashboard run website:readiness
npm --prefix dashboard run product-complete-smoke
make test
AI_MODE=mock make ai-endpoint-smoke
```

### Run stateful live mutation drill

After the live stack is up, this proves real create/read/update/delete plus meaningful spatial and queue-resilience behavior against synthetic geospatial store and queue service state:

```bash
make live-stack-up
make live-stateful-mutation-drill
make live-stack-down
```

For operator-friendly evidence on the console, run the verbose target:

```bash
make live-stack-up
make live-stateful-mutation-drill-verbose
make live-stack-down
```

For a named role-aware scenario profile, run:

```bash
make live-stack-up
make live-stateful-mutation-drill-profile PROFILE=urban_flood
make live-stack-down
```

List all built-in profiles first:

```bash
make live-stateful-mutation-drill-profiles
```

The profile library covers recent disaster patterns where ReliefQueue can help coordinate urgent field intake: urban/river/flash flooding, coastal cyclones and storm surge, earthquake response, tsunami evacuation, wildfire evacuation and smoke-health support, drought and food-security support, disease/WASH outbreaks, displacement reception, winter storms, volcanic ashfall, dam-breach evacuation, chemical release, power outage critical-needs response, crowd/mass-casualty triage, monsoon drain failure, and crop-loss food-security response.

The local coordinator owns field choices such as hub point, affected zone, reachable radius, priority needs, and case locations. The command center operator owns safe runtime controls exposed through operator commands or the portal, such as sync policy, retry policy, workload controls, and review-safe replay.

Detailed mode prints the selected public scenario, role ownership, coordinator field config, case and zone tables, location assignment evidence, relief-hub radius evidence, distance-to-hub/nearest-case evidence, safe-area exclusion, cleanup counts, command-center runtime config, queue health, worker recovery proof, retry/replay evidence, and duplicate suppression evidence.

The main evidence report is:

```text
reports/latest/live_integrations/stateful-mutation/live_stateful_mutation_drill.json
```

The event-transport connector remains a connectivity proof until durable operations messaging is wired.

### Run logistics asset coordination drill

After the live stack is up, this proves ReliefQueue can coordinate synthetic team logistics needs, inventory assets, reservations, dispatch timelines, delivery, return due monitoring, reallocation review, queue service recovery, and cleanup:

```bash
make live-stack-up
make live-logistics-asset-drill-profile PROFILE=urban_flood
make live-stack-down
```

List the role-aware logistics profiles first:

```bash
make live-logistics-asset-profiles
```

The local coordinator owns disaster-specific field needs: field teams, asset needs, hub context, delivery points, needed-by timelines, and return expectations. The command center operator owns safe runtime controls exposed through operator commands or the portal: reservation pressure, sync/retry policy, worker recovery settings, replay review, and stale-return monitoring.

The main evidence report is:

```text
reports/latest/live_integrations/logistics-assets/live_logistics_asset_drill.json
```

### Run volunteer surge coordination drill

After the live stack is up, this proves ReliefQueue can register walk-up volunteers encountered by field workers or the coordinator, keep phone-presence outreach as a dry-run call-center review queue, deduplicate repeated volunteer events, recover a crashed onboarding worker, and clean up synthetic volunteer state:

```bash
make live-stack-up
make live-volunteer-surge-drill-profile PROFILE=urban_flood VERBOSE_FLAGS=-v
make live-stack-down
```

Use verbosity intentionally:

```text
no flag        routine validation / CI-friendly PASS or FAIL
-v             quick operator summary
-vv            demo/story evidence for reviewers
-vvv           debug/cleanup proof, including queue service final state
```

Increase evidence detail with `VERBOSE_FLAGS=-vv` or `VERBOSE_FLAGS=-vvv`. Direct CLI commands also accept `-v`, `-vv`, and `-vvv`:

```bash
PYTHONPATH=src python3 -m reliefqueue.cli live-volunteer-surge-drill -vv
```

The drill does **not** send real messages, poll real phones, store raw phone numbers, or assign volunteers without coordinator review. Mass phone-presence polling remains gated until there is lawful authority, provider integration, opt-out/rate-limit controls, approved templates, human-supervised call-center handling, and a retention policy.

The main evidence report is:

```text
reports/latest/live_integrations/volunteer-surge/live_volunteer_surge_drill.json
```

### Prove implementation milestone live infrastructure

Use this path on a trusted host such as your laptop or an OCI Ubuntu/Debian-style VM:

```bash
make phase01-host-preflight
make phase01-live-proof
make phase01-live-clean
```

If host preflight reports Docker/Compose is missing or unusable, inspect the scope first:

```bash
make operator-scope ACTION=phase01_host_setup
```

Then run guarded setup only when you accept the host changes:

```bash
printf 'YES
' | make phase01-host-setup
```

The setup command is intentionally guarded. It should not install packages, modify groups, or start services without explicit `YES`.

### Check AI/provider boundary

AI is optional and advisory. Offline/mock validation remains the default:

```bash
make ai-endpoint-smoke AI_MODE=mock
make bad-ai-endpoint-smoke
make no-secrets
```

Configured real endpoint smoke is allowed only with sanitized diagnostics and review-required AI output.

### Judge-facing live AMD challenge mode

The public AMD Impact route supports three explicitly synthetic, human-reviewed workloads:

```text
/dashboard/amd-impact
Single incident | Complex dossier | Burst workload (up to 24 reports)
```

The live path is `POST /api/ai/live-verification` and `POST /api/ai/burst-verification`. The ordinary Command Center workflow advisory is a deterministic product demonstration and must not be presented as live AMD inference. A response is labelled **VERIFIED LIVE** only after provider transport succeeds, the challenge nonce is echoed, structured output passes validation, no fallback is used, and human review remains required.

Configure the deployed backend with server-side secrets; never expose these values to browser code:

```text
AI_MODE=openai_compatible
OPENAI_COMPAT_BASE_URL=https://<private-or-protected-vllm-host>/v1
OPENAI_COMPAT_API_KEY=<deployment-secret>
OPENAI_COMPAT_MODEL=reliefqueue-amd
AI_PROVIDER_LABEL=AMD Developer Cloud
AI_ACCELERATOR_LABEL=AMD Instinct MI300X
AI_RUNTIME_LABEL=vLLM 0.23.0
```

The public judge mode applies bounded input, concurrency, per-client, and global request budgets. Inputs must be synthetic and contain no real personal or medical identifiers. The correct claim is that AMD MI300X plus vLLM makes concurrent structured analysis operationally practical and measurable; the project does not claim that no other hardware or model could process the same input.

Run the reusable evaluator offline by default, or opt into a bounded trusted live run:

```bash
make amd-quality-offline-validation
RELIEFQUEUE_CONFIRM_LIVE_AMD=YES AI_MODE=openai_compatible make amd-quality-live-validation
```

After public deployment, verify ordinary routes without provider calls, then run the separate opt-in live AMD proof:

```bash
RELIEFQUEUE_PUBLIC_URL=https://your-public-url.example make submission-public-check
RELIEFQUEUE_PUBLIC_URL=https://your-public-url.example \
RELIEFQUEUE_CONFIRM_LIVE_AMD=YES make submission-live-amd-check
```

### Submission package and final gate

```bash
make submission-pack
make submission-final-gate
```

The final gate intentionally removes provider credentials and forces mock mode, so it proves product safety and reproducibility—not current AMD endpoint availability. The separate `submission-live-amd-check` is the deployment-time proof of real provider execution. Generated reports remain local artifacts and are not source-controlled; the frozen authoritative campaign is `fixtures/amd_evidence_campaign_v1.json`.

## Safety boundary

ReliefQueue may suggest urgency, duplicates, operation zones, missing information, assignment candidates, reply drafts, and public redacted summaries.

ReliefQueue must not claim auto-dispatch, confirmed rescue, confirmed safety, guaranteed location, AI-verified emergency status, or field-worker arrival. A human coordinator approves priority, assignment, field instructions, public communication, and closure.

Public exports and field-worker views must not expose raw contact details, raw report text, full private names, exact private addresses, unnecessary medical details, worker private contacts, secrets, or unredacted media.

## Living reference docs

The primary guide is the operator catalog. Retained docs are intentionally few:

```text
docs/living-guide.md              how docs stay useful and discoverable
docs/safety-boundary.md           product, privacy, field-worker, and export boundaries
docs/ai-boundary.md               optional AI/OpenAI-compatible/vLLM boundary
docs/pilot-readiness.md           pilot, risk, privacy/legal, field SOP, and production gaps
docs/project-knowledge/           small local-AI knowledge layer used by local-ai commands
```

Check that the docs remain current and discoverable:

```bash
make docs-check
```

## Repository fixtures

```text
fixtures/reliefqueue_seed_reports.jsonl
fixtures/operation_zones.json
fixtures/field_workers.json
```

## Validation baseline

```bash
make test
make operator-catalog-check
make docs-check
make privacy-check
make integration-smoke
```

## Local portals

Print the local command-center and field mobile URLs:

```bash
make portal-urls
```

Run the command-center portal:

```bash
make view-dashboard
```

Run the field mobile view:

```bash
make view-field
```

For a phone or Android emulator, use:

```bash
make view-field-mobile
```

For the docs map and maintainer guidance, see `docs/index.md` and run `make change-guide` before starting a change.
