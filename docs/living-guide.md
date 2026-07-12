# Living Documentation Guide

ReliefQueue documentation is split by audience:

- `README.md`, `HACKATHON.md`, and `docs/amd-evidence.md` are judge-facing.
- `docs/development.md`, `docs/operations.md`, safety, AI, and pilot files are technical references.
- `docs/project-knowledge/` contains maintainer-only references.

## Rules

1. Keep the README focused on the product, demo, AMD contribution, safety, and fastest local run.
2. Put submission copy and walkthrough details in `HACKATHON.md`.
3. Put exact benchmark scope and claim limits in `docs/amd-evidence.md`.
4. Put long command sequences in `docs/operations.md`, not the README.
5. Put safety-critical wording in the safety or AI boundary files.
6. Prefer a checked command or test over prose that can drift.
7. Remove obsolete planning notes instead of preserving multiple versions.

## Command discovery

```bash
make change-guide
make operator
make operator-search QUERY="test live integration"
make operator-scope ACTION=phase01_live_stack
```

## Drift check

After documentation edits, run `git diff --check`, review changed links, and confirm that judge-facing claims still match the product.
