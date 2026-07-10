"""Stable duplicate grouping."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from .models import normalize_text


def duplicate_key_for(case: dict[str, Any]) -> str:
    n = normalize_text(" ".join([case.get("location_clue") or "", case.get("raw_text_private") or ""]))
    if "school" in n and ("3" in n or "three" in n):
        topic = "school-3"
    elif "hanuman" in n or "mandir" in n:
        topic = "hanuman"
    elif "bridge" in n:
        topic = "bridge"
    elif "river" in n:
        topic = "river"
    elif "clinic" in n:
        topic = "clinic"
    elif "warehouse" in n:
        topic = "warehouse"
    else:
        topic = "general"
    vulnerable = ",".join(case.get("vulnerable_flags") or [])
    return "|".join([str(case.get("operation_zone_id") or "unknown"), case["need_type"], vulnerable, topic])


def apply_duplicate_groups(cases: list[dict[str, Any]]) -> None:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        key = duplicate_key_for(case)
        case["duplicate_key"] = key
        buckets[key].append(case)
    for key, grouped in buckets.items():
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
        cluster_id = f"dup-{digest}" if len(grouped) > 1 else ""
        for case in grouped:
            case["duplicate_cluster_id"] = cluster_id
            case["duplicate_cluster_size"] = len(grouped)
