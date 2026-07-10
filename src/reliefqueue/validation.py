"""Expected behavior contract checks and validation report rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .intake import load_json
from .privacy import public_export_has_forbidden_content, redact_public_case


def validate_expected_behavior(root: Path, reports: list[dict[str, Any]], cases: list[dict[str, Any]], suggestions: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    contract = load_json(root / "fixtures" / "slice1_expected_behavior.json")
    errors: list[str] = []
    notes: list[str] = []
    by_report = {case["source_report_id"]: case for case in cases}
    if len(reports) < int(contract["minimum_report_count"]):
        errors.append("fewer reports than contract minimum")
    if contract["must_create_case_for_every_report"] and len(cases) != len(reports):
        errors.append("case count does not match report count")
    for group in contract["must_detect_duplicate_report_groups"]:
        cluster_ids = {by_report[report_id]["duplicate_cluster_id"] for report_id in group}
        if len(cluster_ids) != 1 or "" in cluster_ids:
            errors.append(f"duplicate group not detected: {group}")
    for report_id, zone_id in contract["must_tag_known_zones"].items():
        if by_report[report_id].get("operation_zone_id") != zone_id:
            errors.append(f"{report_id} expected zone {zone_id}, got {by_report[report_id].get('operation_zone_id')}")
    for report_id in contract["must_not_mark_assignment_ready"]:
        if by_report[report_id].get("assignment_ready"):
            errors.append(f"{report_id} should not be assignment ready")
    for report_id in contract["must_have_red_or_review_high_attention"]:
        if by_report[report_id].get("urgency") not in {"RED", "REVIEW"}:
            errors.append(f"{report_id} should be RED or REVIEW")
    for report_id, flags in contract["must_include_vulnerable_flags"].items():
        actual = set(by_report[report_id].get("vulnerable_flags") or [])
        missing = set(flags) - actual
        if missing:
            errors.append(f"{report_id} missing vulnerable flags: {sorted(missing)}")
    bad_workers = {row["worker_id"] for row in suggestions if row["worker_id"] in {"worker-epsilon-offline", "worker-delta-food"}}
    if bad_workers:
        errors.append(f"unavailable workers suggested: {sorted(bad_workers)}")
    unknown_location_case_ids = {case["case_id"] for case in cases if not case.get("operation_zone_id")}
    bad_unknown = [row for row in suggestions if row["case_id"] in unknown_location_case_ids]
    if bad_unknown:
        errors.append("unknown-location cases received assignment candidates")
    public_rows = [redact_public_case(case) for case in cases]
    errors.extend(
        public_export_has_forbidden_content(
            public_rows,
            contract["public_export_forbidden_fields"],
            contract["public_export_forbidden_patterns"],
        )
    )
    notes.append(f"checked {len(cases)} cases against Slice 01 contract")
    return errors, notes


def render_validation_markdown(
    errors: list[str],
    notes: list[str],
    summary: dict[str, Any] | None = None,
    ai_report: dict[str, Any] | None = None,
) -> str:
    status = "PASS" if not errors else "FAIL"
    ai_mode = (summary or {}).get("ai_mode", "none")
    ai_counts = (summary or {}).get("ai_status_counts", {})
    lines = [
        "# ReliefQueue Validation",
        "",
        f"status: {status}",
        f"ai_mode: {ai_mode}",
        "assignment_status: suggested_not_dispatched",
        "",
        "This report is for private operator review. Public output is a separate redacted allowlist file.",
        "",
    ]
    if summary:
        lines.extend(
            [
                "## Summary",
                "",
                f"- total_cases: {summary.get('total_cases')}",
                f"- assignment_ready_cases: {summary.get('assignment_ready_cases')}",
                f"- human_review_required_cases: {summary.get('human_review_required_cases')}",
                f"- ai_success_count: {summary.get('ai_success_count', 0)}",
                f"- ai_failure_count: {summary.get('ai_failure_count', 0)}",
                f"- ai_skip_count: {summary.get('ai_skip_count', 0)}",
                "",
            ]
        )
    lines.extend(["## AI Adapter", ""])
    lines.extend(
        [
            f"- mode: {ai_mode}",
            f"- statuses: {ai_counts}",
            f"- redacted_endpoint: {(summary or {}).get('ai_redacted_endpoint', 'not_applicable')}",
            f"- fallback_behavior: {(summary or {}).get('ai_fallback_behavior', 'deterministic case data is preserved')}",
        ]
    )
    if ai_report:
        lines.append(f"- health: {ai_report.get('health', {})}")
    lines.extend(
        [
            "- limitations: AI output is advisory, validated before use, and does not confirm rescue, safety, dispatch, location, or emergency verification.",
            "- limitations: Public exports remain allowlisted and do not include raw AI prompts, raw private text, contact details, exact private addresses, worker phones, or secrets.",
            "",
        ]
    )
    lines.extend(["## Contract Checks", ""])
    if errors:
        lines.extend(f"- FAIL: {error}" for error in errors)
    else:
        lines.append("- PASS: all required Slice 01 invariants passed")
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in notes)
    lines.extend(
        [
            "- AI is optional and safe-degrades to deterministic records.",
            "- Assignment candidates are suggestions only; no dispatch is performed.",
            "- Public redacted cases exclude raw report text, private contact fields, media notes, and worker private contacts.",
            "",
        ]
    )
    return "\n".join(lines)
