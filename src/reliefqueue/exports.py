"""Public/private export packaging for Slice 06."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .intake import load_json, load_jsonl
from .privacy import PRIVATE_FIELD_NAMES, PUBLIC_CASE_FIELDS, PUBLIC_VULNERABLE_FLAGS, redact_public_case
from .reports import write_jsonl


PRIVATE_LABELS = ["PRIVATE_OPERATOR_EXPORT", "DO_NOT_SHARE_PUBLICLY", "SYNTHETIC_DEMO_DATA"]
PUBLIC_LABELS = ["PUBLIC_REDACTED_EXPORT", "SYNTHETIC_DEMO_DATA", "ALLOWLISTED_FIELDS_ONLY"]
PUBLIC_DIR_NAME = "public"
PRIVATE_DIR_NAME = "private"

PRIVATE_CSV_FIELDS = [
    "export_labels",
    "case_id",
    "source_report_id",
    "source_channel",
    "raw_text_private",
    "safe_summary",
    "urgency",
    "need_type",
    "people_count",
    "vulnerable_flags",
    "missing_fields",
    "operation_zone_id",
    "geo_confidence",
    "location_clue",
    "reporter_name_private_optional",
    "reporter_phone_private_optional",
    "media_note_private_optional",
    "human_review_required",
    "assignment_ready",
    "privacy_level",
    "created_from_synthetic_fixture",
]

PUBLIC_FORBIDDEN_FIELD_NAMES = sorted(PRIVATE_FIELD_NAMES | {"assignment_candidates", "assignment_candidates_full"})
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{8,}\d)(?!\w)")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
SECRET_RE = re.compile(
    r"\b(?:sk|rk|api|key|token|secret|bearer|fireworks|openai)[-_]?[A-Za-z0-9]{12,}\b|"
    r"\b(?:api[_-]?key|token|secret|authorization)\s*[:=]\s*['\"]?[A-Za-z0-9_.\-]{8,}",
    re.IGNORECASE,
)
UNSAFE_WORDING_RE = re.compile(
    r"(?i)\b(?:confirmed\s+rescued|confirmed\s+safe|auto[-\s]?dispatched|dispatched|"
    r"guaranteed\s+location|ai\s+rescued|ai\s+verified|definitely\s+reached)\b"
)
PRIVATE_MARKERS = ["PRIVATE_OPERATOR_EXPORT", "DO_NOT_SHARE_PUBLICLY"]
PRIVATE_ADDRESS_MARKERS = [
    "private address",
    "exact private address",
    "full address private",
    "home address private",
]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def export_private(report_dir: Path) -> dict[str, Any]:
    cases = _load_required_jsonl(report_dir / "cases.jsonl")
    assignments = _load_optional_jsonl(report_dir / "field_assignment_candidates.jsonl")
    out_dir = report_dir / PRIVATE_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)

    labeled_cases = [_with_private_labels(row) for row in cases]
    labeled_assignments = [_with_private_labels(row) for row in assignments]
    write_jsonl(out_dir / "operator_cases.jsonl", labeled_cases)
    _write_private_cases_csv(out_dir / "operator_cases.csv", labeled_cases)
    write_jsonl(out_dir / "assignment_candidates.jsonl", labeled_assignments)

    files = ["operator_cases.jsonl", "operator_cases.csv", "assignment_candidates.jsonl"]
    manifest = _manifest(
        report_dir=report_dir,
        export_type="private",
        files=files,
        record_counts={
            "operator_cases": len(cases),
            "assignment_candidates": len(assignments),
        },
        labels=PRIVATE_LABELS,
        redaction_passed=None,
    )
    (out_dir / "export_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _append_export_validation_section(report_dir, private_manifest=manifest, public_manifest=None, redaction=None)
    return manifest


def export_public(report_dir: Path) -> dict[str, Any]:
    cases = _load_required_jsonl(report_dir / "cases.jsonl")
    zones = _load_zones(report_dir)
    out_dir = report_dir / PUBLIC_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)

    public_cases = []
    for case in cases:
        with_zone = dict(case)
        with_zone["zone_name_optional"] = zones.get(str(case.get("operation_zone_id") or ""), "")
        public_cases.append(redact_public_case(with_zone))

    write_jsonl(out_dir / "redacted_cases.jsonl", public_cases)
    _write_zone_summary_public(out_dir / "zone_summary_public.csv", public_cases, zones)
    _write_need_type_summary(out_dir / "need_type_summary_public.csv", public_cases)
    _write_missing_info_summary(out_dir / "missing_info_summary_public.csv", public_cases)
    audit_count = _write_public_audit_summary(report_dir, out_dir)

    files = [
        "redacted_cases.jsonl",
        "zone_summary_public.csv",
        "need_type_summary_public.csv",
        "missing_info_summary_public.csv",
    ]
    if audit_count is not None:
        files.append("field_audit_summary_public.jsonl")
    manifest = _manifest(
        report_dir=report_dir,
        export_type="public",
        files=files,
        record_counts={
            "redacted_cases": len(public_cases),
            "source_cases": len(cases),
            "field_audit_summary": audit_count or 0,
        },
        labels=PUBLIC_LABELS,
        redaction_passed=False,
    )
    (out_dir / "export_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    result = validate_public_exports(report_dir)
    manifest["redaction_passed"] = result["passed"]
    (out_dir / "export_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _append_export_validation_section(report_dir, private_manifest=None, public_manifest=manifest, redaction=result)
    return manifest


def validate_public_exports(report_dir: Path) -> dict[str, Any]:
    out_dir = report_dir / PUBLIC_DIR_NAME
    if not out_dir.exists():
        return {"passed": False, "errors": [f"missing public export directory: {out_dir}"]}
    private_names = _known_private_fixture_names(report_dir)
    errors: list[str] = []
    for path in sorted(out_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name == "redacted_cases.jsonl":
            errors.extend(_validate_public_case_rows(path))
        errors.extend(_scan_file_for_leaks(path, private_names))
    return {"passed": not errors, "errors": errors}


def _validate_public_case_rows(path: Path) -> list[str]:
    errors: list[str] = []
    allowed = set(PUBLIC_CASE_FIELDS)
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{line_number}: invalid JSON: {exc}")
            continue
        extra = sorted(set(row) - allowed)
        missing = sorted(allowed - set(row))
        if extra:
            errors.append(f"{path}:{line_number}: non-allowlisted keys: {extra}")
        if missing:
            errors.append(f"{path}:{line_number}: missing allowlisted keys: {missing}")
        flags = row.get("vulnerable_category_flags") or []
        bad_flags = sorted(set(flags) - PUBLIC_VULNERABLE_FLAGS)
        if bad_flags:
            errors.append(f"{path}:{line_number}:key=vulnerable_category_flags forbidden flags: {bad_flags}")
    return errors


def _scan_file_for_leaks(path: Path, private_names: set[str]) -> list[str]:
    errors: list[str] = []
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = line
            errors.extend(_scan_value(path, line_number, "$", payload, private_names))
        return errors
    if suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return [f"{path}:1: invalid JSON: {exc}"]
        return _scan_value(path, 1, "$", payload, private_names)
    if suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_number, row in enumerate(reader, start=2):
                errors.extend(_scan_value(path, row_number, "$", row, private_names))
        return errors
    return errors


def _scan_value(path: Path, line_number: int, key_path: str, value: Any, private_names: set[str]) -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = _normalize_marker(str(key))
            for forbidden in PUBLIC_FORBIDDEN_FIELD_NAMES:
                if _normalize_marker(forbidden) == normalized_key:
                    errors.append(f"{path}:{line_number}:key={key_path}.{key}: forbidden field name")
            errors.extend(_scan_value(path, line_number, f"{key_path}.{key}", child, private_names))
        return errors
    if isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_scan_value(path, line_number, f"{key_path}[{index}]", child, private_names))
        return errors
    text = str(value)
    lowered = text.lower()
    if PHONE_RE.search(text):
        errors.append(f"{path}:{line_number}:key={key_path}: phone-like value")
    if EMAIL_RE.search(text):
        errors.append(f"{path}:{line_number}:key={key_path}: email-like value")
    if SECRET_RE.search(text):
        errors.append(f"{path}:{line_number}:key={key_path}: secret-like value")
    if UNSAFE_WORDING_RE.search(text):
        errors.append(f"{path}:{line_number}:key={key_path}: unsafe wording")
    for marker in PRIVATE_MARKERS:
        if marker.lower() in lowered:
            errors.append(f"{path}:{line_number}:key={key_path}: private marker {marker}")
    for marker in PRIVATE_ADDRESS_MARKERS:
        if marker in lowered:
            errors.append(f"{path}:{line_number}:key={key_path}: private address marker")
    for name in private_names:
        if name and name.lower() in lowered:
            errors.append(f"{path}:{line_number}:key={key_path}: known private fixture name {name}")
    return errors


def _manifest(
    *,
    report_dir: Path,
    export_type: str,
    files: list[str],
    record_counts: dict[str, int],
    labels: list[str],
    redaction_passed: bool | None,
) -> dict[str, Any]:
    summary_path = report_dir / "summary.json"
    summary = load_json(summary_path) if summary_path.exists() else {}
    manifest: dict[str, Any] = {
        "export_id": f"{export_type}-{summary.get('run_id') or 'unknown-run'}-{utc_now()}",
        "created_at": utc_now(),
        "source_run_id": summary.get("run_id") or "unknown-run",
        "export_type": export_type,
        "files": files,
        "record_counts": record_counts,
        "labels": labels,
        "known_limitations": [
            "Synthetic demo data only.",
            "Human coordinator review remains required before field action or public communication.",
            "Public exports are aggregate or allowlisted records and omit raw text, private contact details, exact addresses, worker contacts, and secrets.",
        ],
    }
    if redaction_passed is not None:
        manifest["redaction_passed"] = redaction_passed
    return manifest


def _with_private_labels(row: dict[str, Any]) -> dict[str, Any]:
    labeled = dict(row)
    labeled["export_labels"] = PRIVATE_LABELS
    labeled["private_export_warning"] = "PRIVATE_OPERATOR_EXPORT DO_NOT_SHARE_PUBLICLY SYNTHETIC_DEMO_DATA"
    return labeled


def _write_private_cases_csv(path: Path, cases: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRIVATE_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for case in cases:
            row = dict(case)
            for key, value in row.items():
                if isinstance(value, (list, dict)):
                    row[key] = json.dumps(value, ensure_ascii=False)
            row["export_labels"] = "|".join(PRIVATE_LABELS)
            writer.writerow(row)


def _write_zone_summary_public(path: Path, cases: list[dict[str, Any]], zones: dict[str, str]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[str(case.get("operation_zone_id") or "unknown")].append(case)
    fieldnames = [
        "operation_zone_id",
        "zone_name_optional",
        "case_count",
        "red_count",
        "amber_count",
        "green_count",
        "review_count",
        "human_review_required_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for zone_id in sorted(grouped):
            rows = grouped[zone_id]
            writer.writerow(
                {
                    "operation_zone_id": zone_id,
                    "zone_name_optional": zones.get(zone_id, ""),
                    "case_count": len(rows),
                    "red_count": sum(1 for row in rows if row["urgency"] == "RED"),
                    "amber_count": sum(1 for row in rows if row["urgency"] == "AMBER"),
                    "green_count": sum(1 for row in rows if row["urgency"] == "GREEN"),
                    "review_count": sum(1 for row in rows if row["urgency"] == "REVIEW"),
                    "human_review_required_count": sum(1 for row in rows if row["human_review_required"]),
                }
            )


def _write_need_type_summary(path: Path, cases: list[dict[str, Any]]) -> None:
    counts = Counter(str(case.get("need_type") or "unknown") for case in cases)
    _write_count_csv(path, ["need_type", "case_count"], "need_type", counts)


def _write_missing_info_summary(path: Path, cases: list[dict[str, Any]]) -> None:
    counts: Counter[str] = Counter()
    for case in cases:
        fields = case.get("missing_fields_safe") or []
        if not fields:
            counts["none"] += 1
        for field in fields:
            counts[str(field)] += 1
    _write_count_csv(path, ["missing_field_safe", "case_count"], "missing_field_safe", counts)


def _write_count_csv(path: Path, fieldnames: list[str], label_field: str, counts: Counter[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for label, count in sorted(counts.items()):
            writer.writerow({label_field: label, "case_count": count})


def _write_public_audit_summary(report_dir: Path, out_dir: Path) -> int | None:
    audit_path = report_dir / "field_audit_demo.jsonl"
    if not audit_path.exists():
        return None
    rows = _load_optional_jsonl(audit_path)
    safe_rows = []
    for row in rows:
        safe_rows.append(
            {
                "event_type": row.get("event_type") or "unknown",
                "case_id": row.get("case_id") or "",
                "created_from_synthetic_fixture": True,
                "sync_state": row.get("sync_state") or "",
            }
        )
    write_jsonl(out_dir / "field_audit_summary_public.jsonl", safe_rows)
    return len(safe_rows)


def _append_export_validation_section(
    report_dir: Path,
    *,
    private_manifest: dict[str, Any] | None,
    public_manifest: dict[str, Any] | None,
    redaction: dict[str, Any] | None,
) -> None:
    path = report_dir / "validation.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# ReliefQueue Validation\n"
    private_manifest = private_manifest or _load_manifest(report_dir / PRIVATE_DIR_NAME / "export_manifest.json")
    public_manifest = public_manifest or _load_manifest(report_dir / PUBLIC_DIR_NAME / "export_manifest.json")
    section = [
        "",
        "## Slice 06 Public/Private Exports",
        "",
    ]
    if private_manifest:
        section.extend(
            [
                f"- private_exports_created: {', '.join(private_manifest['files'])}",
                "- private_export_labels: PRIVATE_OPERATOR_EXPORT, DO_NOT_SHARE_PUBLICLY, SYNTHETIC_DEMO_DATA",
            ]
        )
    if public_manifest:
        section.extend(
            [
                f"- public_exports_created: {', '.join(public_manifest['files'])}",
                f"- redaction_validator_result: {'PASS' if public_manifest.get('redaction_passed') else 'FAIL'}",
                "- can_be_shared: reports/latest/public/ after human review",
                "- must_not_be_shared: reports/latest/private/, raw case records, raw text, private contacts, exact addresses, worker contacts, provider errors, secrets, or internal notes",
                "- known_limitations: synthetic demo data; public rows are not a live public data portal; outputs do not confirm rescue, safety, dispatch, or location verification",
            ]
        )
        urgency_counts = Counter(case.get("urgency") for case in _load_optional_jsonl(report_dir / "cases.jsonl"))
        if urgency_counts:
            section.append(f"- urgency_summary_counts: {dict(sorted(urgency_counts.items()))}")
    if redaction and redaction.get("errors"):
        section.extend(f"- redaction_error: {error}" for error in redaction["errors"])
    section.append("")
    marker = "## Slice 06 Public/Private Exports"
    if marker in existing:
        existing = existing.split(marker)[0].rstrip()
    path.write_text(existing.rstrip() + "\n" + "\n".join(section), encoding="utf-8")


def _known_private_fixture_names(report_dir: Path) -> set[str]:
    names: set[str] = set()
    fixture_path = _repo_root_for(report_dir) / "fixtures" / "reliefqueue_seed_reports.jsonl"
    for path in [fixture_path, report_dir / "cases.jsonl"]:
        if not path.exists():
            continue
        for row in _load_optional_jsonl(path):
            for key in ["reporter_name_private_optional", "reporter_name_private"]:
                value = str(row.get(key) or "").strip()
                if value:
                    names.add(value)
    return names


def _load_zones(report_dir: Path) -> dict[str, str]:
    zones: dict[str, str] = {}
    fixture_zones = _repo_root_for(report_dir) / "fixtures" / "operation_zones.json"
    if fixture_zones.exists():
        for row in load_json(fixture_zones):
            zones[str(row.get("zone_id") or "")] = str(row.get("zone_name") or "")
    zone_summary = report_dir / "zone_summary.csv"
    if zone_summary.exists():
        with zone_summary.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                zones[str(row.get("operation_zone_id") or "")] = str(row.get("zone_name") or "")
    return zones


def _load_required_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"missing required source file: {path}")
    return load_jsonl(path)


def _load_optional_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return load_jsonl(path)


def _normalize_marker(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_json(path)


def _repo_root_for(report_dir: Path) -> Path:
    resolved = report_dir.resolve()
    for candidate in [resolved, *resolved.parents]:
        if (candidate / "fixtures").exists() and (candidate / "src").exists():
            return candidate
    return resolved.parents[1]
