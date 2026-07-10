---
type: "runbook"
title: "Validation commands"
description: "Repository-specific validation commands that should be captured in local AI context packets."
tags:
  - "validation"
  - "operator-workflow"
  - "local-ai"
timestamp: "20260704T054304Z"
---

# Validation commands

Prefer a real repository-specific validation command. Do not assume every repo has `make test`.

## Discovery

```bash
grep -nE '^[a-zA-Z0-9_.-]+:' Makefile
```

## Usage

```bash
AI_CONTEXT_VALIDATE_COMMAND='<repo-specific-command>' make local-ai-context TASK=general-review
```

## Known-good commands

Add commands here when they are confirmed for this repository.
