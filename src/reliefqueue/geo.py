"""Operation-zone tagging by deterministic text matching."""

from __future__ import annotations

from typing import Any

from .models import normalize_text


def tag_zone(report: dict[str, Any], zones: list[dict[str, Any]]) -> dict[str, Any]:
    text = " ".join(
        str(report.get(field, ""))
        for field in ("location_hint_optional", "text")
        if report.get(field) is not None
    )
    n = normalize_text(text)
    best: tuple[int, dict[str, Any] | None, str, str] = (0, None, "", "unknown")
    for zone in zones:
        identifiers: list[tuple[str, str]] = []
        identifiers.extend((value, "landmark") for value in zone.get("landmarks", []))
        identifiers.extend((value, "landmark") for value in zone.get("aliases", []))
        if zone.get("ward_or_village"):
            identifiers.append((zone["ward_or_village"], "ward_or_village"))
        if zone.get("district"):
            identifiers.append((zone["district"], "district"))
        for phrase, scope in identifiers:
            normalized = normalize_text(phrase)
            if normalized and normalized in n:
                score = len(normalized)
                if scope == "landmark":
                    score += 100
                elif scope == "ward_or_village":
                    score += 40
                if score > best[0]:
                    best = (score, zone, phrase, scope)
    if best[1] is None:
        return {
            "location_clue": str(report.get("location_hint_optional") or "").strip(),
            "geo_scope_type": "unknown",
            "geo_confidence": "unknown",
            "operation_zone_id": None,
        }
    confidence = "high" if best[3] == "landmark" else "medium"
    return {
        "location_clue": str(report.get("location_hint_optional") or best[2]).strip(),
        "geo_scope_type": best[3],
        "geo_confidence": confidence,
        "operation_zone_id": best[1]["zone_id"],
    }
