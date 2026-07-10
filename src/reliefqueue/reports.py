"""Report file writers for Slice 01."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import json_ready
from .privacy import public_export_has_forbidden_content, redact_public_case


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(json_ready(row), ensure_ascii=False) + "\n")


def write_outputs(
    report_dir: Path,
    cases: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    validation_markdown: str,
    zones: list[dict[str, Any]] | None = None,
    ai_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    public_cases = [redact_public_case(case) for case in cases]
    public_errors = public_export_has_forbidden_content(public_cases, [], [])
    summary = build_summary(cases, suggestions, public_redaction_passed=not public_errors, ai_report=ai_report)
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_jsonl(report_dir / "cases.jsonl", cases)
    write_jsonl(report_dir / "field_assignment_candidates.jsonl", suggestions)
    write_jsonl(report_dir / "public_redacted_cases.jsonl", public_cases)
    write_zone_summary(report_dir / "zone_summary.csv", cases, suggestions, zones or [])
    (report_dir / "validation.md").write_text(validation_markdown, encoding="utf-8")
    return summary


def build_summary(
    cases: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    *,
    public_redaction_passed: bool = True,
    ai_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    urgency_counts = Counter(case["urgency"] for case in cases)
    need_counts = Counter(case["need_type"] for case in cases)
    zone_counts = Counter(case.get("operation_zone_id") or "unknown" for case in cases)
    duplicate_case_count = sum(1 for case in cases if case.get("duplicate_cluster_id"))
    duplicate_clusters = {case.get("duplicate_cluster_id") for case in cases if case.get("duplicate_cluster_id")}
    missing_info_count = sum(1 for case in cases if case.get("missing_fields"))
    assignment_ready_count = sum(1 for case in cases if case.get("assignment_ready"))
    ai_status_counts = Counter(case.get("ai_status", "not_requested") for case in cases)
    ai_mode = (ai_report or {}).get("mode") or "none"
    summary = {
        "run_id": "slice01-demo-local",
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "input_count": len(cases),
        "case_count": len(cases),
        "urgency_counts": dict(sorted(urgency_counts.items())),
        "need_type_counts": dict(sorted(need_counts.items())),
        "missing_info_count": missing_info_count,
        "duplicate_cluster_count": len(duplicate_clusters),
        "duplicate_case_count": duplicate_case_count,
        "zone_tagged_count": sum(1 for case in cases if case.get("operation_zone_id")),
        "assignment_ready_count": assignment_ready_count,
        "assignment_candidate_count": len(suggestions),
        "public_redaction_passed": public_redaction_passed,
        "ai_mode": ai_mode,
        "ai_status_counts": dict(sorted(ai_status_counts.items())),
        "ai_success_count": ai_status_counts.get("success", 0),
        "ai_failure_count": sum(
            count
            for status, count in ai_status_counts.items()
            if status in {"timeout", "failed_validation", "provider_error"}
        ),
        "ai_skip_count": sum(
            count
            for status, count in ai_status_counts.items()
            if status in {"not_requested", "skipped_missing_env", "fallback_used"}
        ),
        "ai_redacted_endpoint": (ai_report or {}).get("redacted_endpoint", "not_applicable"),
        "ai_fallback_behavior": (ai_report or {}).get(
            "fallback_behavior",
            "deterministic case data is preserved when AI is disabled",
        ),
        # Extra operator-friendly compatibility fields.
        "report_label": "PRIVATE_OPERATOR_EXPORT_DO_NOT_SHARE_PUBLICLY",
        "assignment_status": "suggested_not_dispatched",
        "total_cases": len(cases),
        "assignment_ready_cases": assignment_ready_count,
        "assignment_candidate_rows": len(suggestions),
        "human_review_required_cases": sum(1 for case in cases if case.get("human_review_required")),
        "zone_counts": dict(sorted(zone_counts.items())),
    }
    return summary


def write_zone_summary(
    path: Path,
    cases: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    zones: list[dict[str, Any]],
) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[case.get("operation_zone_id") or "unknown"].append(case)
    zone_names = {zone["zone_id"]: zone["zone_name"] for zone in zones}
    candidate_counts = Counter(row.get("operation_zone_id") or "unknown" for row in suggestions)
    fieldnames = [
        "operation_zone_id",
        "zone_name",
        "case_count",
        "red_count",
        "amber_count",
        "green_count",
        "review_count",
        "missing_location_count",
        "assignment_ready_count",
        "assignment_candidate_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for zone_id in sorted(grouped):
            rows = grouped[zone_id]
            writer.writerow(
                {
                    "operation_zone_id": zone_id,
                    "zone_name": zone_names.get(zone_id, "Unknown / untagged"),
                    "case_count": len(rows),
                    "red_count": sum(1 for row in rows if row["urgency"] == "RED"),
                    "amber_count": sum(1 for row in rows if row["urgency"] == "AMBER"),
                    "green_count": sum(1 for row in rows if row["urgency"] == "GREEN"),
                    "review_count": sum(1 for row in rows if row["urgency"] == "REVIEW"),
                    "missing_location_count": sum(1 for row in rows if "location" in row.get("missing_fields", [])),
                    "assignment_ready_count": sum(1 for row in rows if row.get("assignment_ready")),
                    "assignment_candidate_count": candidate_counts[zone_id],
                }
            )
