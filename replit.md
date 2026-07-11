# ReliefQueue AI

Synthetic disaster-relief coordination demo: a Python crisis-intake/triage
backbone (`src/reliefqueue`) plus a React/Vite dashboard (`dashboard/`)
covering the Command Center, Field Coordinator, and Local Coordinator
surfaces. The project is imported from GitHub and is command-led — most
workflows are driven through the `Makefile` (`make change-guide` for the
operator catalog).

## Live AMD Verification Endpoint

`POST /api/ai/live-verification` — contacts the real AMD Developer Cloud vLLM endpoint
with synthetic humanitarian input and returns verifiable evidence:
- `verified_live`, `fallback_used`, `human_review_required` (always true)
- `provider`, `runtime`, `accelerator`, `served_model`, `underlying_model`
- `request_id`, `verified_at`, `latency_ms`, token counts
- `synthetic_input`, `generated_advisory`
- Never exposes the API key or private data

The AMD Impact page (`/dashboard/amd-impact`) has a **Run Live AMD Verification** button
that calls this endpoint and shows VERIFIED LIVE / LIVE VERIFICATION FAILED inline.
AI Control (`/dashboard` → AI Control) shows the real active model and makes Test Connection
call the backend. Judge Demo Walkthrough Step 3 runs a real AMD inference inline.

Tests for this endpoint: `tests/test_live_verification.py` (31 tests).

## Running on Replit

A single Python process serves both the built dashboard and the JSON
product API facade from one origin, bound to `0.0.0.0:$PORT` (defaults to
5000 when `$PORT` is unset):

- `make replit-build` — builds `dashboard/dist` (generates the deterministic
  local demo data first).
- `make replit-run` — starts the combined server (this is the configured
  `replit-run` workflow / Run button command). It auto-runs
  `make replit-build` first if `dashboard/dist` is missing, so a fresh
  import/clone works with just this one command.
- `make replit-smoke` — boots the server on a scratch port and checks
  `/healthz`, the `/api/product/*` facade, SPA fallback routes, and that
  unknown static assets 404.

Preview routes once the workflow is running:
- `/dashboard`, `/dashboard/assignments`, `/dashboard/amd-impact`, etc.
- `/field/my-work`, `/field/my-cases?worker_id=worker-alpha-boat`, `/field/cases/RQ-1042`, `/field/outbox`
- `/local-coordinator`
- `/internal/classic-dashboard` (internal debug view)
- `GET /healthz` — plain JSON health check

The server (`src/reliefqueue/product_api.py`, `serve()`) statically serves
`dashboard/dist`, answers `/api/product/*` from the same origin, and falls
back to `dashboard/dist/index.html` for the SPA route prefixes above (the
frontend does its own client-side routing based on `window.location`).
Unmatched files with an extension (e.g. `/no-such-asset.js`) return a plain
404 instead of the SPA shell.

This is the existing deterministic **local demo facade** — case data,
assignments, and messaging are in-memory/mocked, not backed by a real
database, queue, or AI provider. It resets whenever the server restarts.
Nothing beyond this facade (PostGIS, Redis, NATS, auth, AI credentials) is
required for it to run.

The published app exposes one web port only. Browser API calls are same-origin, so no CORS configuration is required. Optional cross-origin development can set `RELIEFQUEUE_CORS_ORIGINS` to a comma-separated allowlist.

User navigation is integrated in the product UI:
- the complete Command Center sidebar remains available;
- each role header provides a workspace switcher for Command Center, Field Coordinator, and Local Coordinator;
- Field Coordinator has persistent My Work, My Cases, Outbox, and Help navigation;
- case detail is reached by selecting a case card;
- Capability Map consumes `/healthz` and `/api/product/command/overview` and shows human-readable runtime status instead of linking users to raw JSON.

## Project structure (do not restructure without asking)

- `src/reliefqueue/` — Python backend: intake, triage, assignment, product
  API facade, live-stack integrations (optional, off by default).
- `dashboard/` — Vite + React dashboard, built to `dashboard/dist/` (not
  committed; rebuild with `make replit-build` / `make dashboard-build`).
- `Makefile` — canonical entry point for nearly every workflow; run
  `make change-guide` before non-trivial changes.
- `tests/`, `fixtures/`, `schemas/`, `docs/` — Python test suite, demo
  fixtures, DB schema, and living documentation.

## User preferences

- Preserve the existing UI, all routes, the 36 mapped product actions, print
  surfaces, and accessibility/offline behavior exactly as implemented — no
  frontend redesign.
- Keep the deployment as a single deterministic public demo: no Docker,
  database, queue, auth, or paid AI credentials required to run it.
