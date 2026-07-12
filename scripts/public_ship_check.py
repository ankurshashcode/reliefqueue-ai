#!/usr/bin/env python3
"""Public-facing hygiene checks for ReliefQueue.

The check intentionally scans public surfaces, not every private implementation detail.
It avoids matching normal programming constructs such as JavaScript `.slice(...)`.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ["README.md", "docs", "dashboard/src", "dashboard/scripts"]
FORBIDDEN = [
    ("private guidelines doc", re.compile(r"Codex_Input_Guidelines", re.I)),
    ("internal sandbox name", re.compile(r"\bDaytona\b", re.I)),
    ("internal implementation assistant name", re.compile(r"\bCodex\b", re.I)),
    ("internal slice planning wording", re.compile(r"slice[- ](?:history|planning|runbook|notes?)", re.I)),
    ("internal phase path wording", re.compile(r"\bphase_\d+", re.I)),
]
IMPLEMENTATION_DETAIL_REWRITES = [
    ("database implementation detail", re.compile(r"\bPostGIS\b", re.I)),
    ("queue implementation detail", re.compile(r"\bRedis Streams\b|\bNATS\b", re.I)),
]
ALLOWLIST = [
    re.compile(r"scripts/public_ship_check\.py"),
    re.compile(r"docs/index\.md"),
    # Internal engineering/testing runbook retained for reproducibility; it is
    # not judge-facing product or submission copy.
    re.compile(r"docs/testing/website-testing\.md"),
]
CODE_ALLOWLIST_PATTERNS = [
    re.compile(r"\.slice\s*\("),
    re.compile(r"\bslice\s*[:=]"),
]


def iter_files() -> list[Path]:
    files: list[Path] = []
    for item in SCAN_DIRS:
        path = ROOT / item
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and child.suffix.lower() in {".md", ".js", ".jsx", ".ts", ".tsx", ".mjs"}:
                    files.append(child)
    return sorted(set(files))


def is_allowed(rel: str, line: str) -> bool:
    if any(pattern.search(rel) for pattern in ALLOWLIST):
        return True
    if rel.startswith("dashboard/") and any(pattern.search(line) for pattern in CODE_ALLOWLIST_PATTERNS):
        return True
    return False


def main() -> int:
    failures: list[str] = []
    for path in iter_files():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if is_allowed(rel, line):
                continue
            for label, pattern in FORBIDDEN:
                if pattern.search(line):
                    failures.append(f"{rel}:{lineno}: {label}: {line.strip()}")
            # These terms may remain in private implementation code, but not public docs.
            if rel == "README.md" or rel.startswith("docs/"):
                for label, pattern in IMPLEMENTATION_DETAIL_REWRITES:
                    if pattern.search(line):
                        failures.append(f"{rel}:{lineno}: {label}: {line.strip()}")
    if failures:
        print("PUBLIC_SHIP_CHECK=FAIL")
        for failure in failures:
            print(failure)
        return 2
    print("PUBLIC_SHIP_CHECK=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
