# Safety and Privacy Boundary

ReliefQueue is a human-reviewed coordination aid for synthetic or approved disaster-response data. It does not replace emergency services, dispatch authority, field verification, medical judgment, legal review, or incident command.

## What the system may do

ReliefQueue may:

- summarize an incident safely;
- suggest urgency, need type, and missing information;
- flag possible duplicates;
- suggest an operation zone or assignment candidate;
- draft a reply or redacted public summary;
- record a field update as reported;
- show confidence and uncertainty explicitly.

## What the system must not claim

ReliefQueue must not claim:

- automatic dispatch;
- confirmed rescue or safety;
- guaranteed location;
- AI verification of an emergency;
- confirmed field-worker arrival;
- final medical, legal, or operational authority.

## Human authority

A human coordinator or authorized operator approves:

- final priority;
- assignment and field instruction;
- public communication;
- case closure;
- any rescue, safety, or relief-status statement.

AI output always remains review-required.

## Public and private data

Private operator evidence may contain raw synthetic report text, fixture contact-like fields, assignment internals, location clues, and operator notes. It must stay private.

Public exports are allowlist-based. They may contain safe identifiers, safe summaries, urgency and need labels, people-count buckets, vulnerability flags, zones, location confidence, safe missing-field labels, duplicate-group information, public status, human-review flags, and synthetic-data markers.

Public outputs must exclude:

- raw reports and private messages;
- direct phone or email details;
- full private names and exact private addresses;
- unnecessary medical detail;
- worker private contacts and internal notes;
- credentials, tokens, or environment dumps;
- unredacted media.

## Field-worker minimization

Field workers receive only the context needed for an authorized task: safe summary, priority, need type, people count, vulnerability flag, zone/landmark clue, location confidence, coordinator instruction, masked contact action, and status controls.

They must not receive unrelated cases, raw contacts, raw private messages, or unnecessary sensitive detail.

## Synthetic-data rule

The public demo and live AMD routes accept synthetic demonstration data only. Do not submit real names, phone numbers, exact addresses, medical identifiers, or live emergency reports.

## Validation

```bash
make privacy-check
make security-check
make no-secrets
make field-smoke
make public-ship-check
```
