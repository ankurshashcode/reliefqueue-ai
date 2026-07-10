#!/usr/bin/env python3
"""Suggest docs and validation gates for the current ReliefQueue change."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def changed_files() -> list[str]:
    explicit = os.environ.get("PATHS", "").strip()
    if explicit:
        return [p for p in explicit.split() if p]
    commands = [
        ["git", "diff", "--name-only"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    files: set[str] = set()
    for cmd in commands:
        try:
            out = subprocess.check_output(cmd, cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
        except Exception:
            continue
        files.update(line.strip() for line in out.splitlines() if line.strip())
    return sorted(files)


def add(mapping: dict[str, set[str]], key: str, *values: str) -> None:
    mapping.setdefault(key, set()).update(values)


def main() -> int:
    files = changed_files()
    docs: dict[str, set[str]] = {}
    checks: dict[str, set[str]] = {}

    add(docs, "always", "README.md", "docs/index.md")
    add(checks, "always", "make public-ship-check", "git diff --check")

    if not files:
        print("CHANGE_GUIDE=NO_LOCAL_CHANGES")
        print("Suggested baseline checks:")
        for check in sorted(checks["always"]):
            print(f"- {check}")
        print("Use PATHS='dashboard/src/main.jsx docs/pilot-readiness.md' make change-guide for planned edits.")
        return 0

    for rel in files:
        if rel.startswith("dashboard/"):
            add(docs, "dashboard", "README.md", "docs/safety-boundary.md")
            add(checks, "dashboard", "make dashboard-build", "make dashboard-smoke", "make field-smoke", "make product-smoke")
        if rel.startswith("src/") or rel.startswith("tests/"):
            add(docs, "runtime", "docs/safety-boundary.md", "docs/pilot-readiness.md")
            add(checks, "runtime", "make test")
        if rel.startswith("docs/") or rel == "README.md":
            add(docs, "docs", "docs/living-guide.md", "docs/index.md")
            add(checks, "docs", "make docs-index-check", "make public-ship-check")
        if rel == "Makefile" or rel.startswith("scripts/"):
            add(docs, "commands", "docs/index.md", "docs/living-guide.md")
            add(checks, "commands", "make change-guide", "make docs-index-check", "make public-ship-check")
        if any(token in rel.lower() for token in ["ai", "model", "review", "audit", "public", "export", "field"]):
            add(docs, "safety", "docs/safety-boundary.md")
            add(checks, "safety", "make field-smoke", "make product-smoke", "make public-ship-check")

    print("CHANGE_GUIDE=PASS")
    print("Changed files:")
    for rel in files:
        print(f"- {rel}")
    print("\nRelevant docs:")
    for value in sorted(set().union(*docs.values())):
        print(f"- {value}")
    print("\nSuggested checks:")
    for value in sorted(set().union(*checks.values())):
        print(f"- {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
