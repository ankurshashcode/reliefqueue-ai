"""Batch demo runner and reporting for Slice 05."""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .ai import AIConfig, FORBIDDEN_WORDING, apply_ai_enrichment
from .assignment import suggest_assignments
from .fixture_expander import expand_seed_fixture_file
from .intake import load_json, load_jsonl, validate_reports
from .privacy import public_export_has_forbidden_content, redact_public_case
from .reports import build_summary, write_outputs
from .validation import render_validation_markdown


BATCH_REQUIRED_FILES = [
    "summary.json",
    "cases.jsonl",
    "validation.md",
    "zone_summary.csv",
    "field_assignment_candidates.jsonl",
    "public_redacted_cases.jsonl",
    "batch_metrics.json",
    "batch_story.md",
]

STORY_FORBIDDEN_PHRASES = [
    "production-tested",
    "crore scale",
    "real rescue dispatch",
    "guaranteed throughput",
]


def batch_dir(root: Path, count: int) -> Path:
    return root / "reports" / f"batch-{count}" / "latest"


def batch_input_path(root: Path, count: int) -> Path:
    return root / "reports" / f"batch-{count}" / "input.jsonl"


def run_batch_demo(root: Path, *, count: int, seed: int = 42, report_dir: Path | None = None) -> int:
    from .cli import build_cases

    output_dir = report_dir or batch_dir(root, count)
    input_path = batch_input_path(root, count)
    expanded = expand_seed_fixture_file(
        root / "fixtures" / "reliefqueue_seed_reports.jsonl",
        count=count,
        seed=seed,
        out_path=input_path,
    )
    validate_reports(expanded)
    zones = load_json(root / "fixtures" / "operation_zones.json")
    workers = load_json(root / "fixtures" / "field_workers.json")
    started = time.perf_counter()
    cases = build_cases(expanded, zones)
    ai_config = AIConfig.from_env()
    ai_report = apply_ai_enrichment(cases, ai_config)
    suggestions = suggest_assignments(cases, workers)
    runtime_seconds = max(time.perf_counter() - started, 0.000001)
    errors, notes = validate_batch_outputs(expanded, cases, suggestions)
    summary = build_summary(cases, suggestions, public_redaction_passed=not errors, ai_report=ai_report)
    summary["run_id"] = f"slice05-batch-{count}-seed-{seed}"
    validation = render_validation_markdown(errors, notes, summary, ai_report)
    validation += render_batch_validation_section(count, cases, suggestions, ai_report, errors)
    written_summary = write_outputs(output_dir, cases, suggestions, validation, zones, ai_report)
    written_summary["run_id"] = summary["run_id"]
    written_summary["input_count"] = len(expanded)
    written_summary["case_count"] = len(cases)
    (output_dir / "summary.json").write_text(json.dumps(written_summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    metrics = build_batch_metrics(
        run_id=summary["run_id"],
        input_count=len(expanded),
        cases=cases,
        suggestions=suggestions,
        runtime_seconds=runtime_seconds,
        ai_report=ai_report,
        public_redaction_passed=not any(error.startswith("public") for error in errors),
        validation_passed=not errors,
    )
    (output_dir / "batch_metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "batch_story.md").write_text(render_batch_story(metrics), encoding="utf-8")
    if errors:
        print(f"Batch demo generated reports with validation FAIL: {len(errors)} errors")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Batch demo generated {count} synthetic reports in {output_dir}")
    print("Validation PASS")
    return 0


def validate_batch_outputs(
    reports: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    if len(cases) != len(reports):
        errors.append(f"case count {len(cases)} does not match input count {len(reports)}")
    public_rows = [redact_public_case(case) for case in cases]
    errors.extend(public_export_has_forbidden_content(public_rows, [], [r"\+91[0-9]{10}", r"synthetic-contact"]))
    public_text = json.dumps(public_rows, ensure_ascii=False).lower()
    for phrase in FORBIDDEN_WORDING:
        if phrase in public_text:
            errors.append(f"public export contains forbidden wording: {phrase}")
    notes.append(f"checked {len(cases)} synthetic batch cases")
    notes.append(f"assignment_candidate_rows: {len(suggestions)}")
    return errors, notes


def build_batch_metrics(
    *,
    run_id: str,
    input_count: int,
    cases: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    runtime_seconds: float,
    ai_report: dict[str, Any],
    public_redaction_passed: bool,
    validation_passed: bool,
) -> dict[str, Any]:
    ai_status_counts = Counter(case.get("ai_status", "not_requested") for case in cases)
    duplicate_clusters = {case.get("duplicate_cluster_id") for case in cases if case.get("duplicate_cluster_id")}
    zone_counts = Counter(case.get("operation_zone_id") or "unknown" for case in cases)
    return {
        "run_id": run_id,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "input_count": input_count,
        "processed_count": len(cases),
        "runtime_seconds": round(runtime_seconds, 6),
        "cases_per_second": round(len(cases) / runtime_seconds, 3) if runtime_seconds else 0,
        "reports_per_minute": round((len(cases) / runtime_seconds) * 60, 3) if runtime_seconds else 0,
        "ai_mode": ai_report.get("mode", "none"),
        "ai_success_count": ai_status_counts.get("success", 0),
        "ai_failure_count": sum(ai_status_counts.get(status, 0) for status in ["timeout", "failed_validation", "provider_error"]),
        "ai_skip_count": sum(ai_status_counts.get(status, 0) for status in ["not_requested", "skipped_missing_env", "fallback_used"]),
        "urgency_counts": dict(sorted(Counter(case["urgency"] for case in cases).items())),
        "need_type_counts": dict(sorted(Counter(case["need_type"] for case in cases).items())),
        "zone_counts": dict(sorted(zone_counts.items())),
        "missing_info_count": sum(1 for case in cases if case.get("missing_fields")),
        "duplicate_cluster_count": len(duplicate_clusters),
        "duplicate_case_count": sum(1 for case in cases if case.get("duplicate_cluster_id")),
        "assignment_ready_count": sum(1 for case in cases if case.get("assignment_ready")),
        "assignment_candidate_count": len(suggestions),
        "public_redaction_passed": public_redaction_passed,
        "validation_passed": validation_passed,
        "error_count": 0 if validation_passed else 1,
    }


def render_batch_validation_section(
    count: int,
    cases: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    ai_report: dict[str, Any],
    errors: list[str],
) -> str:
    missing_info_count = sum(1 for case in cases if case.get("missing_fields"))
    duplicate_clusters = {case.get("duplicate_cluster_id") for case in cases if case.get("duplicate_cluster_id")}
    duplicate_case_count = sum(1 for case in cases if case.get("duplicate_cluster_id"))
    ai_status_counts = dict(sorted(Counter(case.get("ai_status", "not_requested") for case in cases).items()))
    return "\n".join(
        [
            "",
            "## Batch Operator Summary",
            "",
            f"- requested_input_count: {count}",
            f"- processed_case_count: {len(cases)}",
            f"- redaction_status: {'PASS' if not any(error.startswith('public') for error in errors) else 'FAIL'}",
            f"- missing_info_count: {missing_info_count}",
            f"- duplicate_cluster_count: {len(duplicate_clusters)}",
            f"- duplicate_case_count: {duplicate_case_count}",
            f"- assignment_candidate_count: {len(suggestions)}",
            f"- ai_mode: {ai_report.get('mode', 'none')}",
            f"- ai_status_counts: {ai_status_counts}",
            "- ai_failure_diagnostics: status counts only; provider errors and private report text are not written to the public export",
            "",
        ]
    )


def render_batch_story(metrics: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Slice 05 Batch Story",
            "",
            "This is a synthetic local batch demo. It expands the checked seed fixtures into generated records and processes them on the same deterministic pipeline used by the local demo.",
            "",
            f"The run processed {metrics['processed_count']} cases from {metrics['input_count']} synthetic inputs in AI mode `{metrics['ai_mode']}`. The measured local runtime is reported only for this sandbox run, not as hardware capacity guidance.",
            "",
            "Real crises can create bursty intake from SMS, web, social, mocked voice transcripts, and mocked OCR notes. ReliefQueue's current processing shape is queue and batch friendly because each report becomes a case record, zone metrics, assignment candidates, and redacted public output without requiring AI for safety-critical fields.",
            "",
            "The AI adapter is advisory and can later point at an OpenAI-compatible self-hosted vLLM endpoint. AMD/ROCm/vLLM is a target inference path for future self-hosted burst inference, but it is not required for this local demo and no AMD hardware throughput is claimed here.",
            "",
            "Human coordinator review remains mandatory for priority, assignment, public communication, and closure. Privacy redaction remains required before any public export.",
            "",
        ]
    )


def batch_report(root: Path) -> int:
    missing: list[str] = []
    for count in [100, 500]:
        directory = batch_dir(root, count)
        for name in BATCH_REQUIRED_FILES:
            if not (directory / name).exists():
                missing.append(str((directory / name).relative_to(root)))
    if missing:
        print("Missing batch report files:")
        for path in missing:
            print(f"- {path}")
        return 1
    for count in [100, 500]:
        metrics = json.loads((batch_dir(root, count) / "batch_metrics.json").read_text(encoding="utf-8"))
        print(
            f"batch-{count}: processed={metrics['processed_count']} ai_mode={metrics['ai_mode']} "
            f"redaction={metrics['public_redaction_passed']} validation={metrics['validation_passed']}"
        )
    optional = batch_dir(root, 5000) / "batch_metrics.json"
    if optional.exists():
        metrics = json.loads(optional.read_text(encoding="utf-8"))
        print(
            f"batch-5000: processed={metrics['processed_count']} ai_mode={metrics['ai_mode']} "
            f"redaction={metrics['public_redaction_passed']} validation={metrics['validation_passed']}"
        )
    return 0


def story_has_overclaim(path: Path) -> bool:
    text = path.read_text(encoding="utf-8").lower()
    return any(phrase in text for phrase in STORY_FORBIDDEN_PHRASES)
