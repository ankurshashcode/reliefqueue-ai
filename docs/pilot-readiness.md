# Pilot Readiness

This file consolidates the pilot checklist, production gap list, privacy/legal review prompts, field SOP draft, cost/risk notes, and partner feedback plan. It is a planning reference, not proof that ReliefQueue is production-ready.

## Pilot gate

Before any real-world pilot, confirm:

```text
synthetic/sanitized data only unless legal approval exists
public/private export boundary reviewed
field-worker minimization reviewed
human coordinator remains final authority
no auto-dispatch or rescue-confirmation claims
host/live infrastructure proof recorded on the target machine
operator can run make operator-search for common situations
```

## Production gaps

ReliefQueue still needs explicit production work before real incident use:

```text
production geospatial data store with a migration plan
production queue/event client workflows
provider-specific messaging consent and audit model
controlled authentication and authorization
incident data retention/deletion policy
legal/privacy review
field-worker SOP approval
observability and backup/restore hardening
load, failover, and degraded-mode drills
```

## Field SOP draft

Field workers should receive minimized case context, follow coordinator instructions, use masked contact paths where available, and report status updates without making rescue/safety claims that the system cannot verify.

The current mobile experience is a browser/PWA field portal. A native wrapper should remain future work unless background sync, push notification, camera, or offline storage constraints prove that the browser path is not enough for the pilot environment.

## Partner feedback prompts

Ask pilot reviewers:

```text
Is the operator flow understandable?
Are public exports safe enough for sharing after review?
Are field-worker views minimal but useful?
Which missing fields block action most often?
Which live integrations should be prioritized next?
What wording feels too strong or unsafe?
```

## Cost and risk notes

Prefer local deterministic checks and mock AI for routine validation. Use real AI/provider, live messaging, or larger infrastructure only when the operator value is clear and the privacy boundary is understood.

Track risks by whether they affect safety, privacy, maintainability, host setup, cost, or pilot trust.
