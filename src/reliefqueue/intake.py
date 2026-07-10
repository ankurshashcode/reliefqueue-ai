"""Fixture loading and validation."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import SOURCE_CHANNELS, WORKER_STATUSES


class ValidationError(ValueError):
    """Raised when deterministic fixture validation fails."""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValidationError(f"{path}:{line_number}: row must be an object")
        rows.append(row)
    return rows


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_unique(items: list[dict[str, Any]], key: str, label: str) -> None:
    seen: set[str] = set()
    for item in items:
        value = item.get(key)
        if not value:
            raise ValidationError(f"{label} missing {key}")
        if value in seen:
            raise ValidationError(f"{label} duplicate {key}: {value}")
        seen.add(value)


def _validate_timestamp(value: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"invalid received_at: {value}") from exc


def validate_reports(reports: list[dict[str, Any]]) -> None:
    _require_unique(reports, "report_id", "report")
    for report in reports:
        report_id = report["report_id"]
        if not str(report.get("text", "")).strip():
            raise ValidationError(f"report {report_id} missing text")
        channel = report.get("source_channel")
        if channel not in SOURCE_CHANNELS:
            raise ValidationError(f"report {report_id} invalid source_channel: {channel}")
        received_at = report.get("received_at")
        if received_at:
            _validate_timestamp(str(received_at))


def validate_zones(zones: list[dict[str, Any]]) -> None:
    _require_unique(zones, "zone_id", "zone")
    for zone in zones:
        zone_id = zone["zone_id"]
        if not str(zone.get("zone_name", "")).strip():
            raise ValidationError(f"zone {zone_id} missing zone_name")
        identifiers = []
        identifiers.extend(zone.get("landmarks") or [])
        identifiers.extend(zone.get("aliases") or [])
        if zone.get("ward_or_village"):
            identifiers.append(zone["ward_or_village"])
        if not any(str(value).strip() for value in identifiers):
            raise ValidationError(f"zone {zone_id} missing location identifiers")


def validate_workers(workers: list[dict[str, Any]]) -> None:
    _require_unique(workers, "worker_id", "worker")
    for worker in workers:
        worker_id = worker["worker_id"]
        if not worker.get("authorized_zone_ids"):
            raise ValidationError(f"worker {worker_id} missing authorized_zone_ids")
        if worker.get("current_status") not in WORKER_STATUSES:
            raise ValidationError(f"worker {worker_id} invalid status")
        if not worker.get("skills"):
            raise ValidationError(f"worker {worker_id} missing skills")
        if int(worker.get("current_active_cases", 0)) > int(worker.get("capacity_active_cases", 0)):
            raise ValidationError(f"worker {worker_id} is over capacity")


def validate_fixture_bundle(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    reports = load_jsonl(root / "fixtures" / "reliefqueue_seed_reports.jsonl")
    zones = load_json(root / "fixtures" / "operation_zones.json")
    workers = load_json(root / "fixtures" / "field_workers.json")
    validate_reports(reports)
    validate_zones(zones)
    validate_workers(workers)
    return reports, zones, workers
