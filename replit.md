# ReliefQueue AI on Replit

ReliefQueue is imported from GitHub and deployed as one web service. A Python process serves the built React/Vite dashboard and the same-origin JSON product API.

## Run commands

```bash
make replit-build
make replit-run
```

`make replit-run` builds `dashboard/dist` automatically when it is missing.

Validation:

```bash
make replit-smoke
make replit-navigation-smoke
```

Health endpoint:

```text
GET /api/health  ->  {"status":"ok"}
```

## Public surfaces

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

Unknown static assets return 404. SPA route prefixes fall back to `dashboard/dist/index.html`.

## Runtime boundary

The deterministic demo needs no Docker, database, queue, authentication service, or AI credential. Its in-memory demo state resets when the process restarts.

Live AMD analysis is optional and uses server-side OpenAI-compatible provider settings. The UI must not claim current AMD execution until a current request passes verification. Historical evidence remains available separately.

Never expose API keys, private endpoints, real incident data, or personal/medical identifiers in browser code or public evidence.

## Project structure

```text
src/reliefqueue/   Python product API and workflows
dashboard/         React/Vite interface
fixtures/          Synthetic inputs and frozen evidence
scripts/           Deployment and validation tools
tests/             Repository tests
```

Use `make change-guide` before non-trivial changes and keep the single-origin deployment contract unless the task explicitly changes it.
