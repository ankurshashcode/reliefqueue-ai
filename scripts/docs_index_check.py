#!/usr/bin/env python3
"""Check that public docs remain discoverable and avoid private process wording."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md",
    "docs/index.md",
    "docs/living-guide.md",
    "docs/safety-boundary.md",
    "docs/pilot-readiness.md",
]
FORBIDDEN_DOC_PATTERNS = [
    re.compile(r"Codex_Input_Guidelines", re.I),
    re.compile(r"\bDaytona\b", re.I),
    re.compile(r"\bCodex\b", re.I),
    re.compile(r"slice[- ](?:history|planning|runbook|notes?)", re.I),
    re.compile(r"\bphase_\d+", re.I),
]


def main() -> int:
    failures: list[str] = []
    for rel in REQUIRED:
        path = ROOT / rel
        if not path.exists():
            failures.append(f"missing required doc: {rel}")

    index = ROOT / "docs/index.md"
    if index.exists():
        text = index.read_text(encoding="utf-8")
        for rel in REQUIRED:
            if rel == "docs/index.md":
                continue
            if rel not in text:
                failures.append(f"docs/index.md does not reference {rel}")

    for rel in ["README.md", "docs/index.md", "docs/living-guide.md", "docs/pilot-readiness.md", "docs/safety-boundary.md"]:
        path = ROOT / rel
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            for pattern in FORBIDDEN_DOC_PATTERNS:
                if pattern.search(line):
                    failures.append(f"{rel}:{lineno}: private process wording: {line.strip()}")

    if failures:
        print("DOCS_INDEX_CHECK=FAIL")
        for item in failures:
            print(item)
        return 2
    print("DOCS_INDEX_CHECK=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
