# Operations Reference

This document holds advanced commands that are useful to maintainers and operators but are not part of the main hackathon narrative.

## Find the right command

```bash
make change-guide
make operator
make operator-search QUERY="test live integration"
make operator-scope ACTION=phase01_live_stack
```

Use `operator-scope` before commands that touch host packages, Docker, live services, generated reports, or provider calls.

## Deterministic demo and exports

```bash
make run-demo-local
make export-report
make privacy-check
make clean-reports
```

Generated evidence is written under `reports/latest/`.

## Product surfaces

```bash
make portal-urls
make view-dashboard
make view-field
make view-field-mobile
```

Routine product checks:

```bash
make dashboard-build
make dashboard-smoke
make field-smoke
make product-smoke
make product-complete-smoke
```

## Optional live stack

The optional local stack provides PostGIS, Redis, and NATS integration proof. It is not required for the public demo.

```bash
make live-stack-up
make live-health
make live-stack-down
```

Always clean up after a drill.

## Stateful mutation drill

Proves create/read/update/delete behavior, spatial queries, queue recovery, retry/replay, duplicate suppression, and cleanup against synthetic state.

```bash
make live-stack-up
make live-stateful-mutation-drill-profile PROFILE=urban_flood
make live-stack-down
```

List profiles:

```bash
make live-stateful-mutation-drill-profiles
```

Evidence:

```text
reports/latest/live_integrations/stateful-mutation/live_stateful_mutation_drill.json
```

## Logistics asset drill

Proves synthetic needs, inventory, reservation, dispatch, delivery, return monitoring, reallocation review, queue recovery, and cleanup.

```bash
make live-stack-up
make live-logistics-asset-drill-profile PROFILE=urban_flood
make live-stack-down
```

List profiles:

```bash
make live-logistics-asset-profiles
```

Evidence:

```text
reports/latest/live_integrations/logistics-assets/live_logistics_asset_drill.json
```

## Volunteer surge drill

Proves synthetic walk-up volunteer registration, deduplication, review queues, worker recovery, and cleanup. It does not send real messages or store raw phone numbers.

```bash
make live-stack-up
make live-volunteer-surge-drill-profile PROFILE=urban_flood VERBOSE_FLAGS=-v
make live-stack-down
```

Verbosity:

```text
no flag   routine PASS/FAIL
-v        operator summary
-vv       reviewer evidence
-vvv      debug and cleanup proof
```

Evidence:

```text
reports/latest/live_integrations/volunteer-surge/live_volunteer_surge_drill.json
```

Real outreach remains blocked until lawful authority, consent, provider integration, approved templates, rate limits, opt-out handling, human supervision, audit, and retention rules exist.

## Trusted-host infrastructure proof

Run on a trusted laptop or Ubuntu/Debian-style host:

```bash
make phase01-host-preflight
make phase01-live-proof
make phase01-live-clean
```

Inspect guarded host setup before accepting changes:

```bash
make operator-scope ACTION=phase01_host_setup
```

Run setup only with explicit approval:

```bash
printf 'YES\n' | make phase01-host-setup
```

The setup path must not install packages, change groups, or start services without `YES`.

## AI checks

Offline/degraded checks:

```bash
make ai-endpoint-smoke AI_MODE=mock
make bad-ai-endpoint-smoke
make no-secrets
```

AMD evidence checks:

```bash
make amd-quality-offline-validation
RELIEFQUEUE_CONFIRM_LIVE_AMD=YES AI_MODE=openai_compatible make amd-quality-live-validation
```

The live command may make provider calls. Use synthetic data only and review [amd-evidence.md](amd-evidence.md) first.

## Submission evidence

```bash
make submission-pack
make submission-final-gate
```

The final gate removes provider credentials and uses the deterministic path. It proves reproducibility and safety, not current provider connectivity.

Deployment checks:

```bash
RELIEFQUEUE_PUBLIC_URL=https://your-public-url.example make submission-public-check
RELIEFQUEUE_PUBLIC_URL=https://your-public-url.example \
RELIEFQUEUE_CONFIRM_LIVE_AMD=YES make submission-live-amd-check
```
