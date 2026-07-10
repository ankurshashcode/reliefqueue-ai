# Living Guide

ReliefQueue documentation is intentionally small. The repository should explain itself through commands first, with Markdown kept only where it preserves current safety boundaries, implementation-process rules, or pilot-readiness context.

## First command

```bash
make operator
```

Use search when you remember the situation but not the command:

```bash
make operator-search QUERY="test live integration"
make operator-search QUERY="check privacy export"
make operator-search QUERY="set up docker on OCI"
```

Use scope before running anything that touches Docker, host packages, generated reports, or review packets:

```bash
make operator-scope ACTION=phase01_host_setup
make operator-scope ACTION=phase01_live_proof
```

## Retained docs

```text
README.md                         current entrypoint
docs/living-guide.md              this guide
docs/safety-boundary.md           product, privacy, field, and export boundaries
docs/ai-boundary.md               optional AI/provider boundary
docs/pilot-readiness.md           pilot checklist, risks, field SOP, and production gaps

docs/project-knowledge/           durable local-AI context used by local-ai commands
```

## Docs that should not come back

Avoid adding internal runbooks or handoff notes as living docs. If a command is useful, register it in `src/reliefqueue/operator_catalog.py`. If a fact is safety-critical, put it in `docs/safety-boundary.md`. Future implementation inputs should stay outside this public repository until they become shipped product behavior.

## Drift check

```bash
make docs-check
```

The check fails when stale planning wording returns, when removed internal runbooks reappear, or when retained docs are no longer discoverable from README or this guide.
