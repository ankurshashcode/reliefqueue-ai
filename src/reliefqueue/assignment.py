"""Field assignment candidate suggestions; no dispatch is performed."""

from __future__ import annotations

from typing import Any

from .models import normalize_text


def assignment_ready(case: dict[str, Any]) -> bool:
    return bool(
        case.get("operation_zone_id")
        and case.get("need_type") not in {"unknown", "information_request", "missing_location_info"}
        and "location" not in case.get("missing_fields", [])
    )


def _worker_available(worker: dict[str, Any]) -> bool:
    return (
        worker.get("current_status") == "available"
        and int(worker.get("current_active_cases", 0)) < int(worker.get("capacity_active_cases", 0))
    )


def _score_worker(case: dict[str, Any], worker: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    skills = set(worker.get("skills") or [])
    required = set(case.get("required_skills") or [])
    matches = sorted(required & skills)
    if matches:
        score += len(matches) * 10
        reasons.append("skill match: " + ", ".join(matches))
    n = normalize_text(case.get("raw_text_private") or "")
    if ("flood_rescue" in required or "boat" in n or "water" in n or "paani" in n) and (
        worker.get("can_cross_flood_water") or worker.get("transport") == "boat"
    ):
        score += 30
        reasons.append("flood/boat capable")
    if case.get("need_type") == "medical" and (
        worker.get("can_handle_medical_cases") or "medical_first_response" in skills
    ):
        score += 30
        reasons.append("medical capable")
    if "child" in case.get("vulnerable_flags", []) and worker.get("can_handle_children_cases"):
        score += 10
        reasons.append("child support capable")
    spare = int(worker.get("capacity_active_cases", 0)) - int(worker.get("current_active_cases", 0))
    score += spare
    return score, reasons


def suggest_assignments(cases: list[dict[str, Any]], workers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for case in cases:
        if not case.get("assignment_ready"):
            continue
        candidates = []
        for worker in workers:
            if not _worker_available(worker):
                continue
            if case.get("operation_zone_id") not in set(worker.get("authorized_zone_ids") or []):
                continue
            score, reasons = _score_worker(case, worker)
            if score <= 0:
                continue
            candidates.append((score, worker, reasons))
        candidates.sort(key=lambda item: (-item[0], item[1]["worker_id"]))
        for rank, (score, worker, reasons) in enumerate(candidates[:3], start=1):
            suggestions.append(
                {
                    "case_id": case["case_id"],
                    "source_report_id": case["source_report_id"],
                    "operation_zone_id": case.get("operation_zone_id"),
                    "required_skills": list(case.get("required_skills") or []),
                    "candidate_worker_id": worker["worker_id"],
                    "candidate_display_name_safe": worker["display_name_safe"],
                    "match_reasons": reasons,
                    "constraint_warnings": [],
                    "rank": rank,
                    "assignment_status": "suggested_not_dispatched",
                    "score": score,
                    # Backward-compatible aliases for simple tests/operator grep.
                    "worker_id": worker["worker_id"],
                    "display_name_safe": worker["display_name_safe"],
                    "reasons": reasons,
                }
            )
    return suggestions
