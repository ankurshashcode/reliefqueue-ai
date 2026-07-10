---
type: "architecture"
title: "AI context workflow"
description: "How temporary AI packets and durable project knowledge work together."
tags:
  - "architecture"
  - "local-ai"
  - "okf"
  - "context"
timestamp: "20260704T054304Z"
---

# AI context workflow

This repository uses two layers:

1. `var/ai-context/` — temporary, ignored packets for one review or run.
2. `docs/project-knowledge/` — durable, git-tracked project memory.

The `local-ai-context` command automatically includes project knowledge in each review packet and appends a factual log entry. This keeps the workflow useful even if the operator forgets about the knowledge layer.

## Rule

If a fact will matter tomorrow, keep it in `docs/project-knowledge/`. If it is only a one-run artifact, keep it in `var/ai-context/`.
