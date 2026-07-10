"""Small repository secret scanner used by local validation.

The scanner intentionally reports only file locations and rule names. It never
returns or prints the matched secret value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SecretFinding:
    """A possible secret location without the sensitive value."""

    path: str
    line: int
    rule: str


_ASSIGNMENT_RE = re.compile(
    r"(?i)\b[A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\b\s*[:=]\s*[\"']?([^\"'\s#]+)"
)
_PROVIDER_KEY_RE = re.compile(r"\b(?:sk|fw|fireworks)-[A-Za-z0-9_\-]{16,}\b")

_SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "reports/latest/field",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "var",
}
_TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".csv",
    ".env",
    ".example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsonl",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
_PLACEHOLDER_VALUES = {
    "",
    "<redacted>",
    "<redacted-api-key>",
    "changeme",
    "change-me",
    "dummy",
    "example",
    "fake",
    "local-dev-only",
    "not_applicable",
    "placeholder",
    "redacted",
    "test",
    "test-key",
    "your-key-here",
}


def scan_for_secrets(root: Path) -> list[SecretFinding]:
    """Return possible secret locations under *root* without exposing values."""

    root = root.resolve()
    findings: list[SecretFinding] = []
    for path in _iter_candidate_files(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root).as_posix()
        for line_number, line in enumerate(lines, start=1):
            if _line_has_real_secret_assignment(line) or _line_has_provider_key(line):
                findings.append(SecretFinding(path=rel, line=line_number, rule="secret-assignment"))
    return findings


def _iter_candidate_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in _SKIP_PARTS for part in rel_parts):
            continue
        if path.name.endswith((".pyc", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tar.gz")):
            continue
        if path.suffix not in _TEXT_SUFFIXES and not path.name.startswith(".env"):
            continue
        yield path


def _line_has_real_secret_assignment(line: str) -> bool:
    match = _ASSIGNMENT_RE.search(line)
    if not match:
        return False
    value = match.group(1).strip().strip("'\"")
    return _looks_like_real_secret(value)


def _line_has_provider_key(line: str) -> bool:
    if "<redacted" in line.lower() or "test-key" in line.lower():
        return False
    return bool(_PROVIDER_KEY_RE.search(line))


def _looks_like_real_secret(value: str) -> bool:
    normalized = value.strip().strip("'\"").lower()
    if normalized in _PLACEHOLDER_VALUES:
        return False
    if normalized.startswith(("<", "${")):
        return False
    if len(value) < 12:
        return False
    if _PROVIDER_KEY_RE.search(value):
        return True
    has_letter = any(char.isalpha() for char in value)
    has_digit = any(char.isdigit() for char in value)
    return len(value) >= 20 and has_letter and has_digit
