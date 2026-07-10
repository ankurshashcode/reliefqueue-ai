#!/usr/bin/env python3
"""Validate that ReliefQueue docs stay current, small, and discoverable."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DOCS = {
    "docs/living-guide.md",
    "docs/safety-boundary.md",
    "docs/ai-boundary.md",
    "docs/pilot-readiness.md",
    "docs/Codex_Input_Guidelines.md",
}
PROJECT_KNOWLEDGE_PREFIX = "docs/project-knowledge/"
REMOVED_DOCS = {
    "INITIAL-COMMIT-NOTES.md",
    "docs/00_GLOBAL_RULES.md",
    "docs/01_SLICE_DETERMINISTIC_BACKBONE.md",
    "docs/SLICE01_OPERATOR_RUNBOOK.md",
    "docs/SLICE02_DASHBOARD_RUNBOOK.md",
    "docs/SLICE03_FIELD_WORKER_RUNBOOK.md",
    "docs/SLICE04_AI_ADAPTER_RUNBOOK.md",
    "docs/SLICE05_BATCH_BURST_RUNBOOK.md",
    "docs/SLICE05_HANDOFF.md",
    "docs/cost-and-risk-list.md",
    "docs/field-operations-sop-draft.md",
    "docs/inference-fallback-runbook.md",
    "docs/inference-openai-compatible.md",
    "docs/inference-vllm-amd-readiness.md",
    "docs/pilot-partner-feedback-plan.md",
    "docs/pilot-readiness-checklist.md",
    "docs/privacy-legal-review-checklist.md",
    "docs/production-architecture-gap-list.md",
    "docs/public-private-exports.md",
}
STALE_PHRASES = (
    "intentionally a skeleton",
    "does not include the Slice 01 implementation yet",
    "Codex should implement the deterministic pipeline",
    "This repository starts with the Slice 01 reference documents",
    "Slice 01 implementation should build",
    "Important docs",
)
README_REQUIRED_SNIPPETS = (
    "make operator",
    "make operator-search",
    "make operator-scope",
    "make docs-check",
    "docs/living-guide.md",
    "docs/safety-boundary.md",
    "docs/ai-boundary.md",
    "docs/pilot-readiness.md",
    "docs/Codex_Input_Guidelines.md",
)


def main() -> int:
    errors: list[str] = []
    for rel in sorted(REQUIRED_DOCS):
        if not (ROOT / rel).exists():
            errors.append(f"missing required living doc: {rel}")
    for rel in sorted(REMOVED_DOCS):
        if (ROOT / rel).exists():
            errors.append(f"obsolete doc should be removed or consolidated: {rel}")
    readme = _read("README.md")
    for snippet in README_REQUIRED_SNIPPETS:
        if snippet not in readme:
            errors.append(f"README missing discoverable reference: {snippet}")
    scanned_paths = [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]
    for rel_path in scanned_paths:
        rel = rel_path.relative_to(ROOT).as_posix()
        if rel == "docs/Codex_Input_Guidelines.md":
            continue
        lowered = _read(rel).lower()
        for phrase in STALE_PHRASES:
            if phrase.lower() in lowered:
                errors.append(f"stale wording in {rel}: {phrase}")
    docs = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "docs").rglob("*.md"))
    living_guide = _read("docs/living-guide.md")
    for rel in docs:
        if rel.startswith(PROJECT_KNOWLEDGE_PREFIX) or rel == "docs/Codex_Input_Guidelines.md":
            continue
        if rel not in readme and rel not in living_guide:
            errors.append(f"doc is not discoverable from README or living guide: {rel}")
    if errors:
        print(f"Docs check FAIL: {len(errors)} issue(s)")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Docs check PASS: living docs are current and discoverable.")
    return 0


def _read(rel: str) -> str:
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
