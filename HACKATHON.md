# ReliefQueue AI — Hackathon Submission

This file contains copy-ready submission text and the recommended judge walkthrough. Technical operations are kept in `docs/` so the submission story stays focused.

## Submission title

**ReliefQueue AI — Human-Reviewed Disaster Coordination on AMD**

## Short description

ReliefQueue AI turns fragmented disaster reports into a human-reviewed relief queue, combining deterministic crisis coordination with optional AMD MI300X and vLLM analysis for fast, structured, verifiable decision support.

## Long description

ReliefQueue AI helps disaster-response teams convert fragmented reports into a structured, reviewable relief queue. The system creates safe summaries, suggests urgency and need categories, flags missing information and possible duplicates, groups incidents by operation zone, proposes assignments, supports field-worker updates, and produces redacted public summaries.

The product is designed around a strict human-in-the-loop boundary. AI and rules provide decision support; they do not dispatch responders, confirm rescue or safety, verify an emergency, or close a case. The public demo uses synthetic or replayed disaster scenarios, and live provider requests require explicit confirmation that the input is synthetic.

ReliefQueue combines a deterministic Python crisis-intake backbone with React/Vite workspaces for Command Center, Field Coordinator, and Local Coordinator roles. The deterministic path remains available without external AI, which makes the demo reproducible and supports degraded or low-connectivity operation. Field updates can wait in a local outbox until connectivity returns.

For accelerated structured analysis, ReliefQueue integrates an OpenAI-compatible vLLM endpoint deployed on AMD Developer Cloud with an AMD Instinct MI300X GPU. A frozen 24-case staged campaign covered single reports, complex multi-source dossiers, and adversarial inputs. The final resolved evidence recorded 24/24 passing cases, 100% normalized JSON, 100% nonce binding, 100% source coverage, no provider errors, no fallback, and human review required for every output. Current live requests are labeled verified only after transport, nonce, schema, fallback, and review checks pass.

ReliefQueue demonstrates how GPU-accelerated inference can support concurrent, structured humanitarian analysis while preserving truthful evidence, deterministic fallback, privacy controls, and human authority.

## The problem

Emergency reports arrive through calls, messages, forms, and field updates. They can be incomplete, duplicated, contradictory, and difficult to prioritize. Coordinators need a common operating picture without allowing an AI system to overstate certainty or make uncontrolled decisions.

## The solution

ReliefQueue provides:

- structured intake from synthetic incident reports;
- safe summaries and urgency suggestions;
- missing-information and duplicate review;
- operation-zone and assignment support;
- role-specific Command Center, Field Coordinator, and Local Coordinator workspaces;
- offline-aware field update handling;
- public/private export separation;
- optional AMD/vLLM structured analysis with request-level proof;
- permanent human review for consequential actions.

## What is innovative

1. **Deterministic first, AI optional.** The relief workflow remains usable and testable without a provider.
2. **Evidence planes are separated.** Historical benchmark evidence, runtime configuration, and current-request proof are never presented as the same thing.
3. **Live verification is challenge-bound.** A request is verified only when the response is bound to its nonce, validates structurally, uses no fallback, and remains review-required.
4. **Role and privacy boundaries are product features.** Field workers see minimized task context; public exports use an allowlist.
5. **The demo is operational, not just a model prompt.** Intake, assignment, field handoff, audit, offline outbox, and redacted reporting are connected in one workflow.

## How AMD GPUs are used

ReliefQueue sends explicitly synthetic humanitarian workloads to an OpenAI-compatible vLLM service deployed on AMD Developer Cloud. The verified campaign used:

- AMD Instinct MI300X;
- vLLM 0.23.0+rocm723;
- served model `reliefqueue-amd`;
- underlying model `Qwen/Qwen2.5-7B-Instruct`.

The GPU path produces compact structured advisories for single incidents, complex dossiers, and bounded burst workloads. ReliefQueue records request identifiers, latency and token metrics, nonce binding, structured-output validity, source coverage, fallback status, and the mandatory human-review flag.

The claim is operational practicality and measurable structured inference on AMD hardware—not hardware exclusivity.

## Judge-supplied inference server

The AMD GPU endpoint may be stopped outside scheduled demonstrations to control cost. The deterministic product remains runnable.

Judges can clone or remix the repository and point ReliefQueue to any model exposed through an OpenAI-compatible Chat Completions endpoint. They provide the endpoint URL, API key, served model, and truthful provider/runtime/hardware labels as server-side variables, then run `make ai-endpoint-smoke` and `make dashboard`.

A judge-supplied non-AMD endpoint demonstrates the portable adapter. Only a currently verified AMD request may be described as current AMD execution. See [docs/development.md](docs/development.md#connect-a-judge-supplied-inference-server).

## Verified evidence

| Metric | Result |
| --- | --- |
| Cases resolved | 24/24 |
| Case mix | 8 single, 8 dossier, 8 adversarial |
| Overall pass rate | 100% |
| Normalized JSON | 100% |
| Strict raw JSON | 95.83% |
| Nonce binding | 100% |
| Source coverage | 100% |
| Provider errors | 0 |
| Fallbacks | 0 |
| Review-required outputs | 24/24 |
| Median latency | 1133.662 ms |
| P95 latency | 1741.063 ms |
| Average completion throughput | 225.975 tokens/s |

Read the exact scope and limitations in [docs/amd-evidence.md](docs/amd-evidence.md).

## Five-minute judge walkthrough

### 1. Open the product

Open the live application and select **Judge Demo Walkthrough**.

### 2. Show deterministic intake

Submit or load the supplied synthetic incident. Point out the safe summary, missing-information flags, need and urgency suggestions, and the handoff into the queue.

Say: “This first advisory is deterministic workflow support. It is not being presented as live AMD inference.”

### 3. Show assignment and human control

Open the assignment for `RQ-1042`. Show the proposed assignment, coordinator approval boundary, and audit-oriented action flow.

### 4. Show AMD evidence

Open **AMD Impact** and **Capability Map**. Explain the three evidence planes:

- frozen historical campaign;
- current runtime configuration;
- current-request verification.

Run live analysis only when the deployment is configured and the synthetic-data confirmation is selected. A failure remains visible and must not be relabeled as verified.

### 5. Show complex and burst modes

Demonstrate the complex dossier and bounded burst inputs. Explain that source coverage, structured output, unique request/nonce evidence, fallback status, and review-required output are checked.

### 6. Show field handoff

Open the Field Coordinator task. Show minimized case context, status/note actions, and offline outbox behavior.

### 7. Close with safety

Say: “ReliefQueue supports coordinators; it does not auto-dispatch, confirm rescue, or replace emergency services. Every consequential output remains under human review.”

## Architecture and stack

- Python 3.11+ deterministic intake, triage, export, and product API;
- React 19, TypeScript, Vite, and Tailwind CSS role workspaces;
- Playwright browser checks and product click-smoke coverage;
- optional PostGIS, Redis, and NATS integration proof;
- AMD Developer Cloud, AMD Instinct MI300X, and vLLM for live structured analysis;
- single-origin Replit deployment for the public demo.

## Public links

- Application: `https://reliefqueue-ai--ankurshashcode.replit.app`
- Source: `https://github.com/ankurshashcode/reliefqueue-ai`

Add the final public video and slide-deck links here before submission.

## Suggested tags

`AMD` · `AMD Instinct MI300X` · `vLLM` · `AI for Good` · `Disaster Response` · `Human in the Loop` · `Crisis Coordination` · `React` · `Python`

## Honest limitations

- The public scenarios and evidence inputs are synthetic or replayed, not live emergency data.
- The verified 24-case result is a staged composite campaign, not a single uniform production-prompt benchmark.
- The deterministic public workflow is not proof that every request used AMD.
- Current live AMD status must be established by current-request verification.
- Authentication, legal approval, data-retention policy, production messaging consent, and operational governance are still required before real incident use.
