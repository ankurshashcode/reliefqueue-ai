---
type: "runbook"
title: "Local AI review on OCI"
description: "Atomic local Ollama review workflow for this repository."
tags:
  - "ollama"
  - "oci"
  - "review"
  - "operator-workflow"
timestamp: "20260704T054304Z"
---

# Local AI review on OCI

Use the atomic flow. Generate a packet, inspect it, then run the smallest review profile first.

```bash
make local-ai-context TASK=general-review
make local-ai-inspect
OLLAMA_MODEL=qwen2.5-coder:7b make local-ai-run-latest-small
```

From a parent directory, use copy-paste-safe `make -C` commands:

```bash
make -C /absolute/path/to/repo local-ai-context TASK=general-review
make -C /absolute/path/to/repo local-ai-inspect
OLLAMA_MODEL=qwen2.5-coder:7b make -C /absolute/path/to/repo local-ai-run-latest-small
```

Do not start with the full profile on CPU-only OCI. Move from `small` to `medium` only after the small output is useful.
