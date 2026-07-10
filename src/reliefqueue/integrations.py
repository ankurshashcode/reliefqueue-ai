"""Offline-safe integration boundary commands."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tarfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .ai import AIConfig
from .assignment import suggest_assignments
from .exports import PHONE_RE, SECRET_RE, UNSAFE_WORDING_RE
from .intake import load_json, load_jsonl, validate_fixture_bundle
from .privacy import PRIVATE_FIELD_NAMES, redact_public_case
from .reports import write_jsonl


INTEGRATION_COMMANDS = [
    "integrations-status",
    "export-postgis-seed",
    "queue-smoke",
    "field-form-export",
    "messaging-exchange-smoke",
    "masked-contact-smoke",
    "observability-smoke",
    "live-integrations-status",
]

OPTIONAL_INTEGRATIONS = {
    "postgis": ["POSTGIS_DSN"],
    "redis_streams": ["REDIS_URL"],
    "nats_jetstream": ["NATS_URL"],
    "rapidpro": ["RAPIDPRO_API_URL", "RAPIDPRO_API_TOKEN"],
    "twilio_sms": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"],
    "whatsapp": ["WHATSAPP_API_URL", "WHATSAPP_ACCESS_TOKEN"],
    "masked_contact_provider": ["MASKED_CONTACT_PROVIDER", "MASKED_CONTACT_API_KEY"],
}

PUBLIC_SCAN_SUFFIXES = {".json", ".jsonl", ".csv", ".xml", ".md", ".txt"}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_report_dir(report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)


def _load_demo_data(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    from .cli import build_cases

    reports, zones, workers = validate_fixture_bundle(root)
    cases_path = root / "reports" / "latest" / "cases.jsonl"
    if cases_path.exists():
        cases = load_jsonl(cases_path)
    else:
        cases = build_cases(reports, zones)
    return cases, zones, workers, suggest_assignments(cases, workers)


def _env_state(keys: list[str]) -> dict[str, Any]:
    present = [key for key in keys if os.environ.get(key)]
    missing = [key for key in keys if not os.environ.get(key)]
    if present and not missing:
        status = "configured"
    elif present:
        status = "partial"
    else:
        status = "skipped_missing_env"
    return {
        "status": status,
        "present_keys": present,
        "missing_keys": missing,
        "secret_values_printed": False,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def integrations_status(root: Path, report_dir: Path) -> int:
    ensure_report_dir(report_dir)
    ai_config = AIConfig.from_env()
    integrations = {name: _env_state(keys) for name, keys in OPTIONAL_INTEGRATIONS.items()}
    payload = {
        "created_at": utc_now(),
        "mode": "offline_safe_status_only",
        "secret_values_printed": False,
        "ai": {
            "mode": ai_config.mode,
            "endpoint_status": "configured" if ai_config.mode != "openai_compatible" or not ai_config.missing_openai_env() else "skipped_missing_env",
            "missing_keys": ai_config.missing_openai_env() if ai_config.mode == "openai_compatible" else [],
            "redacted_endpoint": ai_config.redacted_endpoint() if ai_config.mode == "openai_compatible" else "not_applicable",
        },
        "integrations": integrations,
        "local_boundaries": INTEGRATION_COMMANDS,
        "claims": [
            "offline readiness check only",
            "no provider calls",
            "human review remains required before assignments or public communication",
        ],
    }
    _write_json(report_dir / "integrations_status.json", payload)
    print(f"Integrations status PASS: wrote {report_dir / 'integrations_status.json'}")
    print("Secrets: not printed")
    configured = [name for name, state in integrations.items() if state["status"] == "configured"]
    skipped = [name for name, state in integrations.items() if state["status"] == "skipped_missing_env"]
    print(f"Configured: {', '.join(configured) if configured else 'none'}")
    print(f"Skipped missing env: {', '.join(skipped) if skipped else 'none'}")
    return 0


def export_postgis_seed(root: Path, report_dir: Path) -> int:
    ensure_report_dir(report_dir)
    cases, zones, _workers, _assignments = _load_demo_data(root)
    out_dir = report_dir / "postgis_seed"
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    zone_names = {zone["zone_id"]: zone["zone_name"] for zone in zones}
    rows = [_postgis_case_row(case, zone_names) for case in cases]
    fields = [
        "case_id",
        "public_case_ref",
        "operation_zone_id",
        "zone_name",
        "location_clue",
        "geo_scope_type",
        "geo_confidence",
        "need_type",
        "urgency",
        "people_count_bucket",
        "vulnerable_category_flags",
        "missing_fields_safe",
        "human_review_required",
        "created_from_synthetic_fixture",
    ]
    with (out_dir / "cases_seed.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})
    write_jsonl(out_dir / "cases_seed.jsonl", rows)
    schema_sql = _postgis_schema_sql()
    (out_dir / "schema.sql").write_text(schema_sql, encoding="utf-8")
    manifest = {
        "created_at": utc_now(),
        "boundary": "postgis_seed_export",
        "db_required": False,
        "files": ["schema.sql", "cases_seed.csv", "cases_seed.jsonl"],
        "record_counts": {"cases": len(rows), "zones": len(zones)},
        "privacy": _privacy_scan(out_dir),
        "known_limitations": [
            "No live database connection is attempted.",
            "Point geometry is intentionally omitted until approved coordinates exist.",
            "Location is a zone/landmark clue with confidence, not a guaranteed location.",
        ],
    }
    _write_json(out_dir / "manifest.json", manifest)
    _write_scale_status(report_dir)
    if not manifest["privacy"]["passed"]:
        print("PostGIS seed export FAIL: privacy scan found issues.")
        return 1
    print(f"PostGIS seed export PASS: wrote {out_dir}")
    return 0


def _postgis_case_row(case: dict[str, Any], zone_names: dict[str, str]) -> dict[str, Any]:
    public = redact_public_case(case)
    return {
        "case_id": public["case_id"],
        "public_case_ref": public["public_case_ref"],
        "operation_zone_id": public["operation_zone_id"],
        "zone_name": zone_names.get(str(public["operation_zone_id"] or ""), ""),
        "location_clue": case.get("location_clue"),
        "geo_scope_type": case.get("geo_scope_type"),
        "geo_confidence": public["geo_confidence"],
        "need_type": public["need_type"],
        "urgency": public["urgency"],
        "people_count_bucket": public["people_count_bucket"],
        "vulnerable_category_flags": "|".join(public["vulnerable_category_flags"] or []),
        "missing_fields_safe": "|".join(public["missing_fields_safe"] or []),
        "human_review_required": public["human_review_required"],
        "created_from_synthetic_fixture": public["created_from_synthetic_fixture"],
    }


def _postgis_schema_sql() -> str:
    return "\n".join(
        [
            "-- ReliefQueue synthetic PostGIS seed boundary. No private raw report text or contacts.",
            "CREATE TABLE IF NOT EXISTS reliefqueue_case_seed (",
            "  case_id text PRIMARY KEY,",
            "  public_case_ref text NOT NULL,",
            "  operation_zone_id text,",
            "  zone_name text,",
            "  location_clue text,",
            "  geo_scope_type text,",
            "  geo_confidence text,",
            "  need_type text,",
            "  urgency text,",
            "  people_count_bucket text,",
            "  vulnerable_category_flags text,",
            "  missing_fields_safe text,",
            "  human_review_required boolean,",
            "  created_from_synthetic_fixture boolean",
            ");",
            "CREATE INDEX IF NOT EXISTS reliefqueue_case_seed_zone_idx ON reliefqueue_case_seed(operation_zone_id);",
            "",
        ]
    )


def queue_smoke(root: Path, report_dir: Path) -> int:
    ensure_report_dir(report_dir)
    cases, _zones, _workers, _assignments = _load_demo_data(root)
    out_dir = report_dir / "queue_smoke"
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    enqueued = []
    for index, case in enumerate(cases[:5], start=1):
        enqueued.append(
            {
                "stream": "reliefqueue.intake.v1",
                "message_id": f"msg-{index:04d}",
                "job_id": f"job-{index:04d}",
                "job_type": "case_boundary_review",
                "case_id": case["case_id"],
                "attempt": 0,
                "max_attempts": 2,
                "payload": _queue_payload(case),
            }
        )
    processed, retry, dead = _consume_queue(enqueued)
    write_jsonl(out_dir / "enqueued_jobs.jsonl", enqueued)
    write_jsonl(out_dir / "processed_jobs.jsonl", processed)
    write_jsonl(out_dir / "retry_jobs.jsonl", retry)
    write_jsonl(out_dir / "dead_letter_jobs.jsonl", dead)
    status = {
        "created_at": utc_now(),
        "queue_shape": "redis-streams-or-nats-jetstream-compatible",
        "input_stream": "reliefqueue.intake.v1",
        "consumer_group": "local-boundary-smoke",
        "enqueued": len(enqueued),
        "processed": len(processed),
        "retry_pending": len(retry),
        "dead_lettered": len(dead),
        "privacy": _privacy_scan(out_dir),
    }
    _write_json(out_dir / "queue_status.json", status)
    shutil.copy2(out_dir / "queue_status.json", report_dir / "queue_status.json")
    shutil.copy2(out_dir / "dead_letter_jobs.jsonl", report_dir / "failed_jobs.jsonl")
    _write_scale_status(report_dir)
    if not status["privacy"]["passed"]:
        print("Queue smoke FAIL: privacy scan found issues.")
        return 1
    print(f"Queue smoke PASS: processed={len(processed)} retry={len(retry)} dead_lettered={len(dead)}")
    return 0


def _queue_payload(case: dict[str, Any]) -> dict[str, Any]:
    public = redact_public_case(case)
    return {
        "case_id": public["case_id"],
        "operation_zone_id": public["operation_zone_id"],
        "need_type": public["need_type"],
        "urgency": public["urgency"],
        "missing_fields_safe": public["missing_fields_safe"],
        "location_confidence": public["geo_confidence"],
        "human_review_required": public["human_review_required"],
    }


def _consume_queue(jobs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    processed: list[dict[str, Any]] = []
    retry: list[dict[str, Any]] = []
    dead: list[dict[str, Any]] = []
    for index, job in enumerate(jobs):
        row = {key: value for key, value in job.items() if key != "payload"}
        row["case_id"] = job["case_id"]
        if index == 1:
            retry_job = dict(row)
            retry_job.update({"attempt": 1, "status": "retry_pending", "failure_class": "transient_consumer_error"})
            retry.append(retry_job)
            processed.append({**row, "attempt": 2, "status": "processed_after_retry", "latency_ms": 14})
        elif index == 3:
            dead.append(
                {
                    **row,
                    "attempt": 2,
                    "status": "dead_lettered",
                    "failure_class": "schema_validation_failed",
                    "retryable": False,
                    "private_payload_written": False,
                }
            )
        else:
            processed.append({**row, "attempt": 1, "status": "processed", "latency_ms": 8 + index})
    return processed, retry, dead


def field_form_export(root: Path, report_dir: Path) -> int:
    ensure_report_dir(report_dir)
    cases, _zones, workers, assignments = _load_demo_data(root)
    out_dir = report_dir / "field_form_package"
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    assignment_by_case = {row["case_id"]: row for row in assignments}
    rows = [_field_form_row(case, assignment_by_case.get(case["case_id"])) for case in cases if case.get("assignment_ready")]
    if not rows:
        rows = [_field_form_row(case, None) for case in cases[:3]]
    fields = list(rows[0])
    with (out_dir / "case_review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    write_jsonl(out_dir / "case_review.jsonl", rows)
    form = _field_form_xml(fields)
    (out_dir / "odk_case_review_form.xml").write_text(form, encoding="utf-8")
    worker_rows = [
        {
            "worker_id": worker["worker_id"],
            "display_name_safe": worker["display_name_safe"],
            "authorized_zone_ids": "|".join(worker.get("authorized_zone_ids") or []),
            "skills": "|".join(worker.get("skills") or []),
            "current_status": worker.get("current_status"),
        }
        for worker in workers
    ]
    write_jsonl(out_dir / "workers_minimized.jsonl", worker_rows)
    manifest = {
        "created_at": utc_now(),
        "boundary": "odk_kobo_field_form_export",
        "files": ["odk_case_review_form.xml", "case_review.csv", "case_review.jsonl", "workers_minimized.jsonl"],
        "record_counts": {"cases": len(rows), "workers": len(worker_rows)},
        "privacy": _privacy_scan(out_dir),
    }
    _write_json(out_dir / "manifest.json", manifest)
    _write_scale_status(report_dir)
    if not manifest["privacy"]["passed"]:
        print("Field form export FAIL: privacy scan found issues.")
        return 1
    print(f"Field form export PASS: wrote {out_dir}")
    return 0


def _field_form_row(case: dict[str, Any], assignment: dict[str, Any] | None) -> dict[str, Any]:
    public = redact_public_case(case)
    return {
        "case_id": public["case_id"],
        "safe_summary": public["safe_summary"],
        "priority_label": public["urgency"],
        "need_type": public["need_type"],
        "people_count_bucket": public["people_count_bucket"],
        "vulnerable_category_flags": "|".join(public["vulnerable_category_flags"] or []),
        "operation_zone_id": public["operation_zone_id"],
        "landmark_clue": case.get("location_clue"),
        "location_confidence": public["geo_confidence"],
        "coordinator_instruction": "Review task details; report field update only.",
        "masked_contact_action": "request_masked_relay_if_needed",
        "assignment_status": (assignment or {}).get("assignment_status") or "assignment_pending_coordinator_approval",
        "status_options": "reached_area|needs_more_info|unable_to_access|completed_review",
    }


def _field_form_xml(fields: list[str]) -> str:
    body = "\n".join(f"      <input ref=\"/{field}\"><label>{field}</label></input>" for field in fields)
    return "\n".join(
        [
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
            "<h:html xmlns:h=\"http://www.w3.org/1999/xhtml\" xmlns=\"http://www.w3.org/2002/xforms\">",
            "  <h:head><h:title>ReliefQueue Field Review</h:title></h:head>",
            "  <h:body>",
            body,
            "  </h:body>",
            "</h:html>",
            "",
        ]
    )


def messaging_exchange_smoke(root: Path, report_dir: Path) -> int:
    ensure_report_dir(report_dir)
    cases, _zones, _workers, _assignments = _load_demo_data(root)
    out_dir = report_dir / "messaging_exchange"
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    selected = cases[:3]
    inbound = []
    outbound = []
    for index, case in enumerate(selected, start=1):
        session_id = _stable_token("msg-session", case["case_id"])
        inbound.append(
            {
                "provider": "local-workflow-stub",
                "workflow": "rapidpro-whatsapp-sms-compatible",
                "message_id": f"in-{index:04d}",
                "case_id": case["case_id"],
                "session_id": session_id,
                "language": case.get("language_hint") or "unknown",
                "redacted_text": _message_redacted_text(case),
                "missing_info": case.get("missing_fields") or [],
            }
        )
        outbound.extend(_outbound_messages(case, session_id, index))
    write_jsonl(out_dir / "inbound_messages.jsonl", inbound)
    write_jsonl(out_dir / "outbound_messages.jsonl", outbound)
    manifest = {
        "created_at": utc_now(),
        "boundary": "rapidpro_whatsapp_sms_exchange",
        "provider_calls": 0,
        "record_counts": {"inbound": len(inbound), "outbound": len(outbound)},
        "privacy": _privacy_scan(out_dir),
    }
    _write_json(out_dir / "manifest.json", manifest)
    _write_scale_status(report_dir)
    if not manifest["privacy"]["passed"]:
        print("Messaging exchange smoke FAIL: privacy scan found issues.")
        return 1
    print(f"Messaging exchange smoke PASS: inbound={len(inbound)} outbound={len(outbound)}")
    return 0


def _message_redacted_text(case: dict[str, Any]) -> str:
    need = str(case.get("need_type") or "support")
    zone = str(case.get("operation_zone_id") or "unknown zone")
    return f"Redacted synthetic report requesting {need} near {zone}; private contact and raw text withheld."


def _outbound_messages(case: dict[str, Any], session_id: str, index: int) -> list[dict[str, Any]]:
    missing = case.get("missing_fields") or []
    messages = [
        {
            "provider": "local-workflow-stub",
            "message_id": f"out-{index:04d}-ack",
            "case_id": case["case_id"],
            "session_id": session_id,
            "language": case.get("language_hint") or "unknown",
            "template": "acknowledgement",
            "redacted_body": "We received your report. A coordinator will review it before any field action.",
            "requires_human_approval": True,
        }
    ]
    if missing:
        messages.append(
            {
                "provider": "local-workflow-stub",
                "message_id": f"out-{index:04d}-missing",
                "case_id": case["case_id"],
                "session_id": session_id,
                "language": case.get("language_hint") or "unknown",
                "template": "missing_info_follow_up",
                "missing_info": [field for field in missing if field != "contact_possible"],
                "redacted_body": "Please share the nearest landmark, people count, or need type if available. Do not send private medical detail.",
                "requires_human_approval": True,
            }
        )
    return messages


def masked_contact_smoke(root: Path, report_dir: Path) -> int:
    ensure_report_dir(report_dir)
    cases, _zones, _workers, assignments = _load_demo_data(root)
    out_dir = report_dir / "masked_contact"
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    case = next((row for row in cases if row.get("reporter_phone_private_optional")), cases[0])
    assignment = next((row for row in assignments if row["case_id"] == case["case_id"]), {})
    session = {
        "created_at": utc_now(),
        "provider": "local-no-network-masked-contact",
        "provider_calls": 0,
        "case_id": case["case_id"],
        "proxy_session_id": _stable_token("proxy", case["case_id"]),
        "contact_route": "masked_relay_stub",
        "participant_a_ref": _stable_token("reporter", case["case_id"]),
        "participant_b_ref": assignment.get("candidate_worker_id") or "coordinator-review-desk",
        "private_number_revealed": False,
        "status": "session_stub_created",
    }
    audit = [
        {
            "event_id": _stable_token("audit", session["proxy_session_id"]),
            "created_at": utc_now(),
            "event_type": "masked_contact_session_stub_created",
            "case_id": case["case_id"],
            "proxy_session_id": session["proxy_session_id"],
            "private_number_revealed": False,
        }
    ]
    _write_json(out_dir / "masked_contact_session.json", session)
    write_jsonl(out_dir / "masked_contact_audit.jsonl", audit)
    manifest = {
        "created_at": utc_now(),
        "boundary": "provider_neutral_masked_contact",
        "files": ["masked_contact_session.json", "masked_contact_audit.jsonl"],
        "privacy": _privacy_scan(out_dir),
    }
    _write_json(out_dir / "manifest.json", manifest)
    _write_scale_status(report_dir)
    if not manifest["privacy"]["passed"]:
        print("Masked contact smoke FAIL: privacy scan found issues.")
        return 1
    print(f"Masked contact smoke PASS: proxy_session_id={session['proxy_session_id']}")
    return 0


def observability_smoke(root: Path, report_dir: Path) -> int:
    ensure_report_dir(report_dir)
    started = time.perf_counter()
    cases, _zones, _workers, _assignments = _load_demo_data(root)
    summary = load_json(report_dir / "summary.json") if (report_dir / "summary.json").exists() else {}
    integrations_path = report_dir / "integrations_status.json"
    integrations = load_json(integrations_path) if integrations_path.exists() else {"integrations": {}}
    queue_status = load_json(report_dir / "queue_status.json") if (report_dir / "queue_status.json").exists() else {}
    privacy_status = "pass" if _integration_privacy_status(report_dir) else "needs_review"
    metrics = {
        "created_at": utc_now(),
        "queue_depth": int(queue_status.get("enqueued", 0)) - int(queue_status.get("processed", 0)),
        "processed_count": int(queue_status.get("processed", 0)),
        "failure_count": int(queue_status.get("dead_lettered", 0)),
        "latency_sample_ms": [8, 11, 14],
        "batch_throughput_cases_per_minute": summary.get("reports_per_minute") or None,
        "case_count": len(cases),
        "privacy_check_status": privacy_status,
        "ai_mode": summary.get("ai_mode") or AIConfig.from_env().mode,
        "integration_status_counts": dict(Counter(state.get("status") for state in integrations.get("integrations", {}).values())),
        "provider_calls": 0,
    }
    events = [
        {"event_type": "queue_depth_sampled", "value": metrics["queue_depth"], "created_at": utc_now()},
        {"event_type": "privacy_boundary_checked", "value": privacy_status, "created_at": utc_now()},
        {"event_type": "integration_status_sampled", "value": metrics["integration_status_counts"], "created_at": utc_now()},
    ]
    metrics["local_runtime_seconds"] = round(time.perf_counter() - started, 6)
    _write_json(report_dir / "observability_metrics.json", metrics)
    write_jsonl(report_dir / "observability_events.jsonl", events)
    _write_scale_status(report_dir)
    print(f"Observability smoke PASS: wrote {report_dir / 'observability_metrics.json'}")
    return 0


def live_integrations_status(root: Path, report_dir: Path) -> int:
    ensure_report_dir(report_dir)
    checks = []
    for name, keys in OPTIONAL_INTEGRATIONS.items():
        state = _env_state(keys)
        checks.append(
            {
                "integration": name,
                "status": "SKIP" if state["status"] == "skipped_missing_env" else "CONFIG_CHECK_ONLY",
                "missing_keys": state["missing_keys"],
                "present_keys": state["present_keys"],
                "network_call_attempted": False,
                "secret_values_printed": False,
            }
        )
    payload = {
        "created_at": utc_now(),
        "mode": "live_readiness_config_check_only",
        "checks": checks,
        "note": "This command does not connect to providers; absent env vars skip cleanly.",
    }
    _write_json(report_dir / "live_integrations_status.json", payload)
    print(f"Live integrations status PASS: wrote {report_dir / 'live_integrations_status.json'}")
    for check in checks:
        print(f"- {check['integration']}: {check['status']}")
    return 0


def integration_smoke(root: Path, report_dir: Path) -> int:
    ensure_report_dir(report_dir)
    results = []
    commands = [
        ("integrations-status", integrations_status),
        ("export-postgis-seed", export_postgis_seed),
        ("queue-smoke", queue_smoke),
        ("field-form-export", field_form_export),
        ("messaging-exchange-smoke", messaging_exchange_smoke),
        ("masked-contact-smoke", masked_contact_smoke),
        ("observability-smoke", observability_smoke),
        ("live-integrations-status", live_integrations_status),
    ]
    for name, func in commands:
        started = time.perf_counter()
        code = func(root, report_dir)
        results.append({"command": name, "status": "PASS" if code == 0 else "FAIL", "exit_code": code, "runtime_seconds": round(time.perf_counter() - started, 6)})
    summary = {
        "created_at": utc_now(),
        "boundary": "scale_integration_smoke",
        "results": results,
        "pass_count": sum(1 for result in results if result["status"] == "PASS"),
        "fail_count": sum(1 for result in results if result["status"] == "FAIL"),
        "skip_count": _live_skip_count(report_dir),
        "provider_calls": 0,
        "result_archive_path": str(report_dir / "scale_integration_result.tar.gz"),
        "fallback_archive_path": str(report_dir / "scale_integration_fallback.tar.gz"),
    }
    _write_json(report_dir / "integration_smoke_summary.json", summary)
    _write_scale_status(report_dir)
    _write_archives(report_dir)
    if summary["fail_count"]:
        print(f"Integration smoke FAIL: {summary['fail_count']} command(s) failed.")
        return 1
    print(f"Integration smoke PASS: {summary['pass_count']} local boundary command(s) passed.")
    print(f"Result archive: {report_dir / 'scale_integration_result.tar.gz'}")
    print(f"Fallback archive: {report_dir / 'scale_integration_fallback.tar.gz'}")
    return 0


def _live_skip_count(report_dir: Path) -> int:
    path = report_dir / "live_integrations_status.json"
    if not path.exists():
        return 0
    payload = load_json(path)
    return sum(1 for check in payload.get("checks", []) if check.get("status") == "SKIP")


def _write_scale_status(report_dir: Path) -> None:
    gates = {
        "integrations_status": (report_dir / "integrations_status.json").exists(),
        "postgis_seed": (report_dir / "postgis_seed" / "manifest.json").exists(),
        "queue_smoke": (report_dir / "queue_smoke" / "queue_status.json").exists(),
        "field_form_export": (report_dir / "field_form_package" / "manifest.json").exists(),
        "messaging_exchange": (report_dir / "messaging_exchange" / "manifest.json").exists(),
        "masked_contact": (report_dir / "masked_contact" / "manifest.json").exists(),
        "observability": (report_dir / "observability_metrics.json").exists(),
        "live_integrations_status": (report_dir / "live_integrations_status.json").exists(),
    }
    payload = {
        "created_at": utc_now(),
        "status": "PASS" if all(gates.values()) else "PARTIAL",
        "gates": {name: "PASS" if ready else "MISSING" for name, ready in gates.items()},
        "provider_calls": 0,
        "human_review_required": True,
        "archives": {
            "result": str(report_dir / "scale_integration_result.tar.gz"),
            "fallback": str(report_dir / "scale_integration_fallback.tar.gz"),
        },
    }
    _write_json(report_dir / "scale_integration_status.json", payload)


def _write_archives(report_dir: Path) -> None:
    include_names = [
        "integrations_status.json",
        "integration_smoke_summary.json",
        "scale_integration_status.json",
        "live_integrations_status.json",
        "observability_metrics.json",
        "observability_events.jsonl",
        "queue_status.json",
        "failed_jobs.jsonl",
        "postgis_seed",
        "queue_smoke",
        "field_form_package",
        "messaging_exchange",
        "masked_contact",
    ]
    result_archive = report_dir / "scale_integration_result.tar.gz"
    with tarfile.open(result_archive, "w:gz") as tar:
        for name in include_names:
            path = report_dir / name
            if path.exists():
                tar.add(path, arcname=f"reports/latest/{name}")
    fallback_archive = report_dir / "scale_integration_fallback.tar.gz"
    with tarfile.open(fallback_archive, "w:gz") as tar:
        for name in ["scale_integration_status.json", "integration_smoke_summary.json", "integrations_status.json"]:
            path = report_dir / name
            if path.exists():
                tar.add(path, arcname=f"reports/latest/{name}")


def _integration_privacy_status(report_dir: Path) -> bool:
    paths = [
        report_dir / "postgis_seed",
        report_dir / "queue_smoke",
        report_dir / "field_form_package",
        report_dir / "messaging_exchange",
        report_dir / "masked_contact",
        report_dir / "public",
    ]
    existing = [path for path in paths if path.exists()]
    if not existing:
        return False
    return all(_privacy_scan(path).get("passed") for path in existing)


def _stable_token(prefix: str, value: str) -> str:
    digest = hashlib.sha256(f"{prefix}:{value}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _privacy_scan(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    for item in sorted(path.rglob("*") if path.is_dir() else [path]):
        if not item.is_file() or item.suffix.lower() not in PUBLIC_SCAN_SUFFIXES:
            continue
        text = item.read_text(encoding="utf-8", errors="ignore")
        lowered = text.lower()
        for field_name in PRIVATE_FIELD_NAMES:
            if field_name.lower() in lowered:
                errors.append(f"{item.name}: private field marker {field_name}")
        if PHONE_RE.search(text):
            errors.append(f"{item.name}: phone-like value")
        if SECRET_RE.search(text):
            errors.append(f"{item.name}: secret-like value")
        if UNSAFE_WORDING_RE.search(text):
            errors.append(f"{item.name}: unsafe wording")
    return {"passed": not errors, "errors": errors, "files_scanned": len([item for item in path.rglob('*') if item.is_file()]) if path.is_dir() else 1}
