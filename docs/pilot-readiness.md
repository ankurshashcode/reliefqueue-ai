# Pilot Readiness

ReliefQueue is a hackathon prototype and coordination demo. This document lists work required before real incident use; it is not a production-readiness claim.

## Required pilot gate

Before any real-world pilot, confirm:

- legal authority and approved data handling;
- authentication, authorization, and role access;
- incident-data retention and deletion policy;
- approved field-worker and coordinator procedures;
- messaging consent, opt-out, rate-limit, and audit controls;
- reviewed public/private export rules;
- human authority for priority, assignment, communication, and closure;
- backup, restore, monitoring, load, failover, and degraded-mode evidence;
- training and escalation paths for operators and partners.

## Current gaps

Production work still includes:

- durable geospatial and queue infrastructure with migrations;
- controlled identity and access management;
- production messaging and masked-contact providers;
- privacy, legal, security, and humanitarian-governance review;
- observability, alerting, retention, backup, and disaster recovery;
- verified field-device behavior under poor connectivity;
- incident-specific load, failover, and operational exercises.

## Field operating rule

Field workers should receive minimized task context, follow coordinator instructions, use approved contact channels, and report observed status without making rescue or safety claims that have not been verified by authorized personnel.

## Partner review questions

- Is the coordinator flow understandable under time pressure?
- Are field views minimal but sufficient?
- Which missing fields most often block action?
- Is the public export safe after review?
- Which integrations produce the most operational value?
- Which wording feels too strong, unclear, or unsafe?

Prefer deterministic and synthetic validation until the legal, privacy, operational, and partner boundaries are approved.
