# ReliefQueue docs map

This repository should be understandable from the UI, make targets, and a small set of public docs. Prefer changing code names, command output, or validation checks before adding another long document.

## Start here

| Need | Use | Why |
| --- | --- | --- |
| Run or demo ReliefQueue | `README.md` and `make portal-urls` | Quick public entry point and local portal URLs. |
| See the web/mobile portals | `make view-dashboard`, `make view-field`, or `make view-field-mobile` | Starts the local dashboard and prints the command-center and field URLs. |
| Decide whether to add or remove docs | `docs/living-guide.md` | Keeps docs small and avoids stale process notes. |
| Change AI, triage, dispatch wording, privacy, or public exports | `docs/safety-boundary.md` | Safety and human-review rules belong here. |
| Prepare for a pilot or public demo | `docs/pilot-readiness.md` | Readiness state, constraints, and remaining gaps. |
| Decide which checks/docs apply to your current edits | `make change-guide` | Reads changed files and suggests relevant docs and validation gates. |

Before changing code or docs: `make change-guide`.

## Daily maintainer flow

```bash
make change-guide
make test
make dashboard-build
make dashboard-smoke
make field-smoke
make product-smoke
make public-ship-check
```

For small documentation-only edits, `make docs-index-check` and `make public-ship-check` are usually the minimum checks.

## Documentation rule

Keep public docs about the product and operator workflow. Keep private sandbox/process guidance outside this repository. If a rule is important enough to preserve, prefer a repo-owned make check so future maintainers do not need to remember it manually.
