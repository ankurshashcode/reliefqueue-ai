"""Small shared constants and helpers for Slice 01 records."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any


URGENCY_VALUES = {"RED", "AMBER", "GREEN", "REVIEW"}
NEED_TYPES = {
    "rescue",
    "medical",
    "food_water",
    "shelter",
    "evacuation",
    "missing_location_info",
    "information_request",
    "unknown",
}
WORKER_STATUSES = {"available", "busy", "offline", "resting"}
SOURCE_CHANNELS = {
    "sms",
    "whatsapp",
    "web",
    "social",
    "voice_transcript_mock",
    "image_ocr_mock",
    "unknown",
}


def stable_case_id(report_id: str) -> str:
    digest = hashlib.sha1(report_id.encode("utf-8")).hexdigest()[:10]
    return f"case-{digest}"


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value).lower()
    value = re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def unique_sorted(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})


def json_ready(record: dict[str, Any]) -> dict[str, Any]:
    return {key: record[key] for key in sorted(record)}
