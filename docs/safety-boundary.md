# Safety Boundary

ReliefQueue is a human-reviewed crisis-intake and coordination aid for synthetic disaster reports. It can organize reports and suggest next steps. It does not replace dispatch authority, rescue confirmation, field verification, legal review, or emergency services.

## Allowed wording

ReliefQueue may say:

```text
AI/rules suggested priority
needs human review
possible duplicate
location confidence
assignment suggestion
assignment pending coordinator approval
masked contact relay stub
field update reported
public redacted export
```

## Forbidden wording

ReliefQueue must not say:

```text
auto-dispatched
confirmed rescued
confirmed safe
guaranteed location
AI rescued the person
AI verified the emergency
worker definitely reached victim
```

## Human-in-loop rule

ReliefQueue can suggest urgency, need type, missing information, duplicate group, operation zone, assignment candidate, reply draft, and public redacted summary.

A human coordinator/operator approves final priority, assignment, field instruction, public communication, case closure, and any rescue/relief status.

## Public/private export boundary

Private operator exports are for internal review only and may include raw synthetic report text, synthetic contact-like fixture fields, assignment internals, missing information, location clues, and operator notes. They must be labelled as private and must not be shared publicly.

Public exports are allowlist-based. Public case rows may include safe fields such as case id, public reference, safe summary, urgency, need type, people-count bucket, vulnerable-category flags, operation zone, location confidence, safe missing-field labels, duplicate cluster id/size, human-review-required flag, public status, and synthetic-fixture marker.

Public exports must not include raw report text, full private names, raw phone numbers, email-like contacts, exact private addresses, worker private contacts, assignment internals, internal notes, API keys, tokens, secrets, unredacted media, or unnecessary medical detail.

## Field-worker minimization

Field workers should see only what they need for the authorized task:

```text
case id
safe summary
priority label
need type
people count
vulnerable category flag
zone or landmark clue
location confidence
coordinator instruction
masked contact action
status update buttons
```

They should not see raw contacts, raw private messages, unnecessary medical detail, or cases outside their authorized zone/assignment.

## Current validation commands

```bash
make privacy-check
make security-check
make no-secrets
make field-smoke
```
