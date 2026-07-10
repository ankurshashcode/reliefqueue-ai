"""Shared operator-facing console formatting helpers.

These helpers keep local make-command output readable at every verbosity level.
They do not decide safety policy; command modules still provide the report data.
The highest verbosity prints the full captured report/context object exactly as
stored by the command. Secrets should therefore be avoided at the report source,
not masked later by this renderer.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

MAX_VERBOSE_LEVEL = 4


def clamp_verbose(value: Any) -> int:
    """Normalize argparse -v counts to the supported 0..4 range."""
    try:
        count = int(value or 0)
    except (TypeError, ValueError):
        count = 0
    return max(0, min(count, MAX_VERBOSE_LEVEL))


def yes_no(value: Any) -> str:
    return "yes" if bool(value) else "no"


def true_false(value: Any) -> str:
    return "true" if bool(value) else "false"


def status_text(value: Any) -> str:
    text = str(value or "UNKNOWN").upper()
    if text in {"PASS", "OK", "READY"}:
        return "PASS"
    if text in {"SKIP", "SKIPPED"}:
        return "SKIP"
    if text in {"FAIL", "FAILED", "ERROR"}:
        return "FAIL"
    if text in {"REFUSED", "BLOCKED", "BLOCKED_AS_EXPECTED"}:
        return "BLOCKED AS EXPECTED"
    return text


def title_from_id(value: Any) -> str:
    text = str(value or "unknown").replace("_", " ").replace("-", " ").strip()
    if not text:
        return "Unknown"
    return " ".join(part.capitalize() for part in text.split())


def short_text(value: Any, limit: int = 96) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def list_text(values: Iterable[Any], *, empty: str = "none") -> str:
    rendered = [str(value) for value in values if str(value)]
    return ", ".join(rendered) if rendered else empty


def section(lines: list[str], title: str) -> None:
    if lines and lines[-1] != "":
        lines.append("")
    lines.append(f"{title}:")


def bullet(lines: list[str], text: str, indent: int = 0) -> None:
    prefix = "  " * indent + "- "
    lines.append(prefix + text)


def key_value(lines: list[str], key: str, value: Any, indent: int = 0) -> None:
    bullet(lines, f"{key}: {value}", indent=indent)


def json_lines(payload: Any) -> list[str]:
    return json.dumps(payload, indent=2, sort_keys=True, default=str).splitlines()


def full_json_section(lines: list[str], title: str, payload: Any) -> None:
    section(lines, title)
    lines.append("```json")
    lines.extend(json_lines(payload))
    lines.append("```")


def verbosity_help() -> str:
    return "Increase output detail. Use -v, -vv, -vvv, or -vvvv for full captured JSON diagnostics."
