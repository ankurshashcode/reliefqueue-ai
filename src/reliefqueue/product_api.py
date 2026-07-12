"""Product API facade backed by the local PostGIS/Redis live stack."""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import json
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .amd_quality import (
    SAFE_METADATA,
    WORKLOAD_COMPLETION_BUDGETS,
    BurstParseError,
    ContextBudgetError,
    build_cross_case_repair_prompt,
    build_cross_case_synthesis_prompt,
    build_dossier_reasoning_ledger,
    build_dossier_repair_prompt,
    build_dossier_incident_supplement_prompt,
    dossier_incident_supplement_required,
    build_model_metadata,
    build_workload_prompt,
    cross_case_semantic_issues,
    dossier_semantic_issues,
    enforce_context_budget,
    normalize_cross_case_synthesis,
    normalize_dossier_incident_supplement,
    normalize_structured_output,
    parsed_preview,
    reconcile_provider_dossier_outputs,
    reconcile_provider_incident_supplement,
    parse_burst_input,
    sanitize_text,
    synthesize_burst,
)
from .amd_evidence import amd_capability_payload, public_amd_evidence_payload
from .ai import AIConfig, OpenAICompatibleAdapter
from .assignment import suggest_assignments
from .cli import ROOT, build_cases
from .intake import load_json, load_jsonl
from .judge_rate_limit import (
    LIVE_AMD_DEFAULT_MAX_BODY_BYTES,
    LIVE_AMD_MAX_CASES,
    LIVE_AMD_ROUTES,
    consume_live_amd_budget,
    positive_env_int,
)
from .live_integrations import _postgres_execute, _postgres_query, _redis_command, _redis_xgroup_create, _sql_literal

DEFAULT_DSN = "postgresql://reliefqueue:reliefqueue@127.0.0.1:54329/reliefqueue"
DEFAULT_REDIS_URL = "redis://127.0.0.1:63799/0"
TIMEOUT = 8.0
REDIS_TTL_SECONDS = "900"
EVIDENCE_STORE = ROOT / "var" / "evidence-store"


_LOCAL_CASES: list[dict[str, Any]] = [
    {
        "case_id": "RQ-1042",
        "title": "Boat evacuation request near Sector 7",
        "safe_summary": "Boat evacuation request near Sector 7 with medical support needed.",
        "urgency": "RED",
        "need_type": "rescue_medical",
        "status": "open",
        "operation_zone_id": "north-embankment",
        "location_clue": "Sector 7 north embankment",
        "people_count": 5,
        "assigned_worker_id": None,
        "coordinates": {"lon": 77.02, "lat": 28.03},
        "revision": 1,
    },
    {
        "case_id": "RQ-1077",
        "title": "Insulin delivery for elderly resident",
        "safe_summary": "Medication delivery needs cold bag handoff confirmation.",
        "urgency": "AMBER",
        "need_type": "medicine",
        "status": "assigned",
        "operation_zone_id": "relief-hub-west",
        "location_clue": "Relief hub west lane 4",
        "people_count": 1,
        "assigned_worker_id": "worker-alpha-boat",
        "coordinates": {"lon": 77.05, "lat": 28.04},
        "revision": 1,
    },
    {
        "case_id": "RQ-1105",
        "title": "Shelter capacity check after rain surge",
        "safe_summary": "Local coordinator review needed for shelter capacity.",
        "urgency": "REVIEW",
        "need_type": "shelter",
        "status": "review",
        "operation_zone_id": "school-shelter-b",
        "location_clue": "School shelter B",
        "people_count": 43,
        "assigned_worker_id": None,
        "coordinates": {"lon": 77.07, "lat": 28.02},
        "revision": 1,
    },
]
_LOCAL_OUTBOX: list[dict[str, Any]] = []
_LOCAL_AUDIT: list[dict[str, Any]] = []
_LOCAL_DLQ: list[dict[str, Any]] = []
_LOCAL_EVIDENCE: list[dict[str, Any]] = []
_LOCAL_AI: dict[str, Any] = {"status": "not_requested", "human_review_required": True}
_LOCAL_IDEMPOTENCY: dict[str, Any] = {}
_LOCAL_SCENARIO: dict[str, Any] = {
    "profile": "Urban flood pilot",
    "zone": "North embankment and Ward 13",
    "hub": "Relief hub west",
    "radius_km": 4,
    "priority_needs": ["rescue", "medicine", "water"],
    "blocked_safe_areas": "Ward 13 east road blocked; school shelter marked safe",
}

IDENTITIES: dict[str, dict[str, str]] = {
    "command-operator": {
        "actor_id": "command-operator",
        "name": "Command Center Operator",
        "role": "command_center_operator",
        "source": "demo_session",
    },
    "local-coordinator": {
        "actor_id": "local-coordinator",
        "name": "Local Coordinator",
        "role": "local_coordinator",
        "source": "demo_session",
    },
    "worker-alpha-boat": {
        "actor_id": "worker-alpha-boat",
        "name": "Team Alpha Boat",
        "role": "field_worker",
        "source": "demo_session",
    },
}

ROLE_ACTIONS: dict[str, set[str]] = {
    "command_center_operator": {
        "assign_case",
        "status_update",
        "message_queued",
        "drill_recorded",
        "ai_advisory",
        "dlq_replay",
        "monitoring_read",
    },
    "local_coordinator": {"scenario_update", "monitoring_read", "map_read"},
    "field_worker": {"field_case_read", "status_update", "evidence_upload", "field_sync"},
}


class ProductApiError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def product_postgis_dsn() -> str:
    return os.environ.get("RELIEFQUEUE_POSTGIS_DSN") or DEFAULT_DSN


def product_redis_url() -> str:
    return os.environ.get("RELIEFQUEUE_REDIS_URL") or DEFAULT_REDIS_URL


def init_product_live_state(root: Path = ROOT) -> dict[str, Any]:
    dsn = product_postgis_dsn()
    schema = (root / "schemas" / "product_live_schema.sql").read_text(encoding="utf-8")
    _postgres_execute(dsn, [schema], TIMEOUT)

    reports = load_jsonl(root / "fixtures" / "reliefqueue_seed_reports.jsonl")
    zones = load_json(root / "fixtures" / "operation_zones.json")
    workers = load_json(root / "fixtures" / "field_workers.json")
    cases = build_cases(reports, zones)
    suggestions = suggest_assignments(cases, workers)

    statements: list[str] = []
    for worker in workers:
        statements.append(
            """
            INSERT INTO product_workers(worker_id, display_name_safe, authorized_zone_ids, skills, current_status)
            VALUES ({worker_id}, {display_name}, {zones}::jsonb, {skills}::jsonb, {status})
            ON CONFLICT (worker_id) DO UPDATE SET
              display_name_safe = EXCLUDED.display_name_safe,
              authorized_zone_ids = EXCLUDED.authorized_zone_ids,
              skills = EXCLUDED.skills,
              current_status = EXCLUDED.current_status,
              updated_at = now();
            """.format(
                worker_id=_sql_literal(worker["worker_id"]),
                display_name=_sql_literal(worker["display_name_safe"]),
                zones=_sql_literal(json.dumps(worker.get("authorized_zone_ids", []))),
                skills=_sql_literal(json.dumps(worker.get("skills", []))),
                status=_sql_literal(worker.get("current_status", "available")),
            )
        )
    for index, case in enumerate(cases):
        point = _point_for_case(case, index)
        statements.append(
            """
            INSERT INTO product_cases(
              case_id, source_report_id, title, safe_summary, urgency, need_type,
              status, operation_zone_id, location_clue, people_count, geom
            )
            VALUES (
              {case_id}, {source_report_id}, {title}, {safe_summary}, {urgency}, {need_type},
              'open', {zone}, {location}, {people_count},
              ST_SetSRID(ST_MakePoint({lon}, {lat}), 4326)
            )
            ON CONFLICT (case_id) DO UPDATE SET
              safe_summary = EXCLUDED.safe_summary,
              urgency = EXCLUDED.urgency,
              need_type = EXCLUDED.need_type,
              operation_zone_id = EXCLUDED.operation_zone_id,
              location_clue = EXCLUDED.location_clue,
              people_count = EXCLUDED.people_count,
              geom = EXCLUDED.geom,
              updated_at = now();
            """.format(
                case_id=_sql_literal(case["case_id"]),
                source_report_id=_sql_literal(case["source_report_id"]),
                title=_sql_literal(_title_for_case(case)),
                safe_summary=_sql_literal(case["safe_summary"]),
                urgency=_sql_literal(case["urgency"]),
                need_type=_sql_literal(case["need_type"]),
                zone=_sql_literal(case.get("operation_zone_id") or "unknown"),
                location=_sql_literal(case.get("location_clue") or ""),
                people_count="NULL" if case.get("people_count") is None else str(int(case["people_count"])),
                lon=77.0 + (index % 7) * 0.01,
                lat=28.0 + (index % 5) * 0.01,
            )
        )
    for suggestion in suggestions:
        worker_id = suggestion.get("candidate_worker_id") or suggestion.get("worker_id")
        if not worker_id:
            continue
        statements.append(
            """
            INSERT INTO product_assignments(case_id, worker_id, assignment_status, assigned_by, idempotency_key)
            VALUES ({case_id}, {worker_id}, 'candidate', 'seed', {idem})
            ON CONFLICT (idempotency_key) DO NOTHING;
            """.format(
                case_id=_sql_literal(suggestion["case_id"]),
                worker_id=_sql_literal(worker_id),
                idem=_sql_literal(f"seed-{suggestion['case_id']}-{worker_id}"),
            )
        )
    _postgres_execute(dsn, statements, TIMEOUT)

    redis_url = product_redis_url()
    _ensure_group(redis_url, "product:outbox", "product-workers")
    _ensure_group(redis_url, "product:ai-advisory", "product-ai")
    return {"status": "PASS", "cases": len(cases), "workers": len(workers), "backend": "postgis+redis"}


def command_overview() -> dict[str, Any]:
    try:
        return _command_overview_live()
    except Exception:
        return _local_command_overview()


def _command_overview_live() -> dict[str, Any]:
    rows = _postgres_query(
        product_postgis_dsn(),
        """
        SELECT
          COUNT(*),
          COUNT(*) FILTER (WHERE urgency = 'RED'),
          COUNT(*) FILTER (WHERE status IN ('open','assigned','acknowledged','in_progress')),
          COUNT(*) FILTER (WHERE assigned_worker_id IS NULL),
          COUNT(*) FILTER (WHERE urgency = 'REVIEW')
        FROM product_cases;
        """,
        TIMEOUT,
    )[0]
    return {
        "contract": "reliefqueue-product-api/v1",
        "summary": {
            "total_cases": int(rows[0] or 0),
            "critical_cases": int(rows[1] or 0),
            "active_cases": int(rows[2] or 0),
            "unassigned_cases": int(rows[3] or 0),
            "human_review": int(rows[4] or 0),
        },
        "cases": list_cases(limit=12)["cases"],
        "health": system_health(),
        "paid_integrations": {
            "sms": "disabled_demo_local_only",
            "push": "disabled_demo_local_only",
            "call": "disabled_demo_local_only",
            "maps": "disabled_demo_local_only",
        },
        "ai": latest_ai_advisory(),
    }


def list_cases(limit: int = 50) -> dict[str, Any]:
    try:
        return _list_cases_live(limit)
    except Exception:
        return {"cases": [dict(row) for row in _LOCAL_CASES[:limit]]}


def _list_cases_live(limit: int = 50) -> dict[str, Any]:
    rows = _postgres_query(
        product_postgis_dsn(),
        f"""
        SELECT case_id, title, safe_summary, urgency, need_type, status, operation_zone_id,
               location_clue, COALESCE(people_count::text, ''), COALESCE(assigned_worker_id, ''),
               COALESCE(ST_X(geom)::text, ''), COALESCE(ST_Y(geom)::text, '')
        FROM product_cases
        ORDER BY CASE urgency WHEN 'RED' THEN 1 WHEN 'AMBER' THEN 2 WHEN 'REVIEW' THEN 3 ELSE 4 END, created_at
        LIMIT {int(limit)};
        """,
        TIMEOUT,
    )
    return {"cases": [_case_from_row(row) for row in rows]}


def field_my_cases(worker_id: str) -> dict[str, Any]:
    try:
        return _field_my_cases_live(worker_id)
    except Exception:
        cases = [dict(row) for row in _LOCAL_CASES if row.get("assigned_worker_id") in {None, worker_id}]
        return {
            "worker_id": worker_id,
            "cases": cases,
            "sync": {"state": "online", "pending": len(_LOCAL_OUTBOX), "offline_queue_supported": True},
            "paid_integrations": {
                "push": "disabled_demo_local_only",
                "sms": "disabled_demo_local_only",
                "call": "disabled_demo_local_only",
                "map_tiles": "disabled_demo_local_only",
            },
        }


def _field_my_cases_live(worker_id: str) -> dict[str, Any]:
    rows = _postgres_query(
        product_postgis_dsn(),
        """
        SELECT c.case_id, c.title, c.safe_summary, c.urgency, c.need_type, c.status, c.operation_zone_id,
               c.location_clue, COALESCE(c.people_count::text, ''), COALESCE(c.assigned_worker_id, ''),
               COALESCE(ST_X(c.geom)::text, ''), COALESCE(ST_Y(c.geom)::text, '')
        FROM product_cases c
        LEFT JOIN product_assignments a ON a.case_id = c.case_id
        WHERE c.assigned_worker_id = {worker_id}
           OR (a.worker_id = {worker_id} AND a.assignment_status IN ('candidate','active'))
        ORDER BY CASE c.urgency WHEN 'RED' THEN 1 WHEN 'AMBER' THEN 2 ELSE 3 END, c.created_at
        LIMIT 20;
        """.format(worker_id=_sql_literal(worker_id)),
        TIMEOUT,
    )
    outbox_depth = _redis_command(product_redis_url(), ["XLEN", f"product:field:{worker_id}:pending"])
    return {
        "worker_id": worker_id,
        "cases": [_case_from_row(row) for row in rows],
        "sync": {"state": "online", "pending": int(outbox_depth or 0), "offline_queue_supported": True},
        "paid_integrations": {
            "push": "disabled_demo_local_only",
            "sms": "disabled_demo_local_only",
            "call": "disabled_demo_local_only",
            "map_tiles": "disabled_demo_local_only",
        },
    }


def resolve_actor(actor_id: str | None, fallback: str = "command-operator") -> dict[str, str]:
    return dict(IDENTITIES.get(actor_id or fallback) or IDENTITIES[fallback])


def require_role(actor: dict[str, str], action: str) -> None:
    if action not in ROLE_ACTIONS.get(actor.get("role", ""), set()):
        raise ProductApiError(403, f"{actor.get('role', 'unknown')} is not authorized for {action}")


def assign_case(case_id: str, worker_id: str, actor_id: str, idempotency_key: str, expected_revision: int | None = None) -> dict[str, Any]:
    actor = resolve_actor(actor_id)
    require_role(actor, "assign_case")
    try:
        return _assign_case_live(case_id, worker_id, actor["actor_id"], idempotency_key)
    except ProductApiError:
        raise
    except Exception:
        key = f"assignment:{idempotency_key}"
        if key in _LOCAL_IDEMPOTENCY:
            return {"status": "duplicate", "case": dict(_local_get_case(case_id)), "idempotency_key": idempotency_key}
        case = _local_get_case(case_id)
        _check_revision(case, expected_revision, {"worker_id": worker_id, "action": "assign_case", "actor": actor})
        _LOCAL_IDEMPOTENCY[key] = True
        case["assigned_worker_id"] = worker_id
        case["status"] = "assigned"
        case["revision"] = int(case.get("revision") or 1) + 1
        _local_audit(actor, "assign_case", case_id, {"worker_id": worker_id, "idempotency_key": idempotency_key})
        return {"status": "assigned", "case": dict(case), "idempotency_key": idempotency_key, "actor": actor}


def _assign_case_live(case_id: str, worker_id: str, actor_id: str, idempotency_key: str) -> dict[str, Any]:
    if not _claim_idempotency(idempotency_key, "assignment"):
        return {"status": "duplicate", "case": get_case(case_id), "idempotency_key": idempotency_key}
    rows = _postgres_query(
        product_postgis_dsn(),
        """
        UPDATE product_cases
        SET assigned_worker_id = {worker_id}, status = 'assigned', updated_at = now()
        WHERE case_id = {case_id} AND (assigned_worker_id IS NULL OR assigned_worker_id = {worker_id})
        RETURNING case_id, COALESCE(assigned_worker_id, ''), status;
        """.format(case_id=_sql_literal(case_id), worker_id=_sql_literal(worker_id)),
        TIMEOUT,
    )
    if not rows:
        raise ProductApiError(409, "case is already assigned to another worker")
    _postgres_execute(
        product_postgis_dsn(),
        [
            """
            INSERT INTO product_assignments(case_id, worker_id, assignment_status, assigned_by, idempotency_key)
            VALUES ({case_id}, {worker_id}, 'active', {actor_id}, {idem})
            ON CONFLICT (idempotency_key) DO NOTHING;
            INSERT INTO product_audit_events(actor_id, action, case_id, detail, idempotency_key)
            VALUES ({actor_id}, 'assign_case', {case_id}, {detail}::jsonb, {audit_idem})
            ON CONFLICT (idempotency_key) DO NOTHING;
            """.format(
                case_id=_sql_literal(case_id),
                worker_id=_sql_literal(worker_id),
                actor_id=_sql_literal(actor_id),
                idem=_sql_literal(idempotency_key),
                detail=_sql_literal(json.dumps({"worker_id": worker_id})),
                audit_idem=_sql_literal(f"audit-{idempotency_key}"),
            )
        ],
        TIMEOUT,
    )
    _redis_command(product_redis_url(), ["XADD", "product:outbox", "*", "type", "assignment", "case_id", case_id, "worker_id", worker_id])
    return {"status": "assigned", "case": get_case(case_id), "idempotency_key": idempotency_key}


def update_status(case_id: str, status: str, actor_id: str, note: str, idempotency_key: str, expected_revision: int | None = None) -> dict[str, Any]:
    actor = resolve_actor(actor_id, fallback=actor_id if actor_id in IDENTITIES else "worker-alpha-boat")
    require_role(actor, "status_update")
    try:
        return _update_status_live(case_id, status, actor["actor_id"], note, idempotency_key)
    except Exception:
        key = f"status:{idempotency_key}"
        if key in _LOCAL_IDEMPOTENCY:
            return {"status": "duplicate", "case": dict(_local_get_case(case_id)), "idempotency_key": idempotency_key}
        case = _local_get_case(case_id)
        _check_revision(case, expected_revision, {"status": status, "note": note, "action": "status_update", "actor": actor})
        _LOCAL_IDEMPOTENCY[key] = True
        case["status"] = status
        case["revision"] = int(case.get("revision") or 1) + 1
        _LOCAL_OUTBOX.append({"type": "status", "case_id": case_id, "status": status, "actor": actor})
        _local_audit(actor, "status_update", case_id, {"status": status, "note": note, "idempotency_key": idempotency_key})
        return {"status": "updated", "case": dict(case), "idempotency_key": idempotency_key, "actor": actor}


def _update_status_live(case_id: str, status: str, actor_id: str, note: str, idempotency_key: str) -> dict[str, Any]:
    if not _claim_idempotency(idempotency_key, "status"):
        return {"status": "duplicate", "case": get_case(case_id), "idempotency_key": idempotency_key}
    _postgres_execute(
        product_postgis_dsn(),
        [
            """
            UPDATE product_cases SET status = {status}, updated_at = now() WHERE case_id = {case_id};
            INSERT INTO product_status_history(case_id, actor_id, status, note, idempotency_key)
            VALUES ({case_id}, {actor_id}, {status}, {note}, {idem})
            ON CONFLICT (idempotency_key) DO NOTHING;
            INSERT INTO product_audit_events(actor_id, action, case_id, detail, idempotency_key)
            VALUES ({actor_id}, 'status_update', {case_id}, {detail}::jsonb, {audit_idem})
            ON CONFLICT (idempotency_key) DO NOTHING;
            """.format(
                case_id=_sql_literal(case_id),
                status=_sql_literal(status),
                actor_id=_sql_literal(actor_id),
                note=_sql_literal(note),
                idem=_sql_literal(idempotency_key),
                detail=_sql_literal(json.dumps({"status": status, "note": note})),
                audit_idem=_sql_literal(f"audit-{idempotency_key}"),
            )
        ],
        TIMEOUT,
    )
    _redis_command(product_redis_url(), ["XADD", f"product:field:{actor_id}:pending", "*", "type", "status", "case_id", case_id, "status", status])
    return {"status": "updated", "case": get_case(case_id), "idempotency_key": idempotency_key}


def send_message(case_id: str, channel: str, body: str, idempotency_key: str, actor_id: str = "command-operator", provider: str = "local_mock") -> dict[str, Any]:
    actor = resolve_actor(actor_id)
    require_role(actor, "message_queued")
    try:
        return _send_message_live(case_id, channel, body, idempotency_key)
    except Exception:
        key = f"message:{idempotency_key}"
        if key in _LOCAL_IDEMPOTENCY:
            return {
                "status": "duplicate",
                "message_id": _LOCAL_IDEMPOTENCY[key],
                "paid_integration_state": "disabled_demo_local_only",
            }
        message_id = str(len(_LOCAL_OUTBOX) + 1)
        _LOCAL_IDEMPOTENCY[key] = message_id
        outbound = {"type": "message", "case_id": case_id, "channel": channel, "body": body, "message_id": message_id, "provider": provider, "attempts": 0, "state": "pending"}
        _LOCAL_OUTBOX.append(outbound)
        _local_audit(actor, "message_queued", case_id, {"message_id": message_id, "channel": channel, "provider": provider})
        return {"status": "queued_local_only", "message_id": message_id, "provider": provider, "paid_integration_state": "disabled_demo_local_only"}


def _send_message_live(case_id: str, channel: str, body: str, idempotency_key: str) -> dict[str, Any]:
    if not _claim_idempotency(idempotency_key, "message"):
        rows = _postgres_query(product_postgis_dsn(), f"SELECT message_id::text FROM product_message_outbox WHERE idempotency_key = {_sql_literal(idempotency_key)};", TIMEOUT)
        return {"status": "duplicate", "message_id": rows[0][0] if rows else None, "paid_integration_state": "disabled_demo_local_only"}
    rows = _postgres_query(
        product_postgis_dsn(),
        """
        INSERT INTO product_message_outbox(case_id, channel, body, idempotency_key)
        VALUES ({case_id}, {channel}, {body}, {idem})
        ON CONFLICT (idempotency_key) DO UPDATE SET body = product_message_outbox.body
        RETURNING message_id::text;
        """.format(case_id=_sql_literal(case_id), channel=_sql_literal(channel), body=_sql_literal(body), idem=_sql_literal(idempotency_key)),
        TIMEOUT,
    )
    _redis_command(product_redis_url(), ["XADD", "product:outbox", "*", "type", "message", "case_id", case_id, "channel", channel])
    return {"status": "queued_local_only", "message_id": rows[0][0], "paid_integration_state": "disabled_demo_local_only"}


def add_evidence(case_id: str, worker_id: str, metadata: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    actor = resolve_actor(worker_id, fallback="worker-alpha-boat")
    require_role(actor, "evidence_upload")
    file_b64 = str(metadata.get("file_base64") or "")
    if not file_b64:
        raise ProductApiError(400, "metadata-only evidence is incomplete; file_base64 is required")
    try:
        file_bytes = base64.b64decode(file_b64, validate=True)
    except Exception as exc:
        raise ProductApiError(400, "invalid evidence file_base64") from exc
    if not file_bytes:
        raise ProductApiError(400, "empty evidence file upload is incomplete")
    try:
        return _add_evidence_live(case_id, worker_id, metadata, idempotency_key)
    except Exception:
        key = f"evidence:{idempotency_key}"
        if key in _LOCAL_IDEMPOTENCY:
            existing = next((item for item in _LOCAL_EVIDENCE if item.get("idempotency_key") == idempotency_key), {})
            return {"status": "duplicate", "evidence": existing}
        _LOCAL_IDEMPOTENCY[key] = True
        record = _store_evidence(case_id, actor, metadata, file_bytes, idempotency_key)
        _LOCAL_OUTBOX.append({"type": "evidence", "case_id": case_id, "actor": actor, "sha256": record["sha256"], "state": "stored"})
        _local_audit(actor, "evidence_upload", case_id, {"sha256": record["sha256"], "size": record["size"], "idempotency_key": idempotency_key})
        return {"status": "stored", "evidence": record}


def _add_evidence_live(case_id: str, worker_id: str, metadata: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    if not _claim_idempotency(idempotency_key, "evidence"):
        return {"status": "duplicate", "redaction_state": "metadata_only_no_binary_upload"}
    file_bytes = base64.b64decode(str(metadata.get("file_base64")), validate=True)
    actor = resolve_actor(worker_id, fallback="worker-alpha-boat")
    record = _store_evidence(case_id, actor, metadata, file_bytes, idempotency_key)
    sha = record["sha256"]
    _postgres_execute(
        product_postgis_dsn(),
        [
            """
            INSERT INTO product_evidence_metadata(case_id, worker_id, media_type, file_name, sha256, idempotency_key)
            VALUES ({case_id}, {worker_id}, {media_type}, {file_name}, {sha}, {idem})
            ON CONFLICT (idempotency_key) DO NOTHING;
            """.format(
                case_id=_sql_literal(case_id),
                worker_id=_sql_literal(worker_id),
                media_type=_sql_literal(str(metadata.get("media_type") or "note")),
                file_name=_sql_literal(str(metadata.get("file_name") or "field-note.txt")),
                sha=_sql_literal(sha),
                idem=_sql_literal(idempotency_key),
            )
        ],
        TIMEOUT,
    )
    return {"status": "stored", "evidence": record}


def run_drill(idempotency_key: str) -> dict[str, Any]:
    try:
        return _run_drill_live(idempotency_key)
    except Exception:
        result = {"name": "local command drill", "case_count": len(_LOCAL_CASES), "deterministic": True}
        _local_audit(resolve_actor("command-operator"), "drill_recorded", None, {"result": result, "idempotency_key": idempotency_key})
        return {"status": "recorded", "result": result}


def _run_drill_live(idempotency_key: str) -> dict[str, Any]:
    result = {"name": "local command drill", "case_count": command_overview()["summary"]["total_cases"], "deterministic": True}
    _postgres_execute(
        product_postgis_dsn(),
        [
            """
            INSERT INTO product_drill_history(drill_type, result, idempotency_key)
            VALUES ('command_center_deterministic', {result}::jsonb, {idem})
            ON CONFLICT (idempotency_key) DO NOTHING;
            """.format(result=_sql_literal(json.dumps(result)), idem=_sql_literal(idempotency_key))
        ],
        TIMEOUT,
    )
    return {"status": "recorded", "result": result}


def request_ai_advisory(case_id: str | None, idempotency_key: str) -> dict[str, Any]:
    global _LOCAL_AI
    try:
        return _request_ai_advisory_live(case_id, idempotency_key)
    except Exception:
        key = f"ai:{idempotency_key}"
        if key in _LOCAL_IDEMPOTENCY:
            return dict(_LOCAL_AI) | {"status": "duplicate"}
        _LOCAL_IDEMPOTENCY[key] = True
        case = _local_get_case(case_id or _LOCAL_CASES[0]["case_id"])
        _LOCAL_AI = {
            "job_id": "ai-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:16],
            "case_id": case["case_id"],
            "status": "completed",
            "summary": f"Review {case['case_id']} with urgency {case['urgency']} and current status {case['status']}.",
            "recommendation": "Advisory only: coordinator review required before dispatch or public messaging.",
            "human_review_required": True,
            "model_detail": "local mock; optional OpenAI-compatible endpoint not configured",
        }
        _local_audit(resolve_actor("command-operator"), "ai_advisory", case["case_id"], {"job_id": _LOCAL_AI["job_id"]})
        return dict(_LOCAL_AI)


def _request_ai_advisory_live(case_id: str | None, idempotency_key: str) -> dict[str, Any]:
    if not _claim_idempotency(idempotency_key, "ai"):
        return latest_ai_advisory() | {"status": "duplicate"}
    job_id = "ai-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]
    case = get_case(case_id) if case_id else list_cases(limit=1)["cases"][0]
    summary = f"Review {case['case_id']} with urgency {case['urgency']} and current status {case['status']}."
    recommendation = "Advisory only: prioritize coordinator review before dispatch or public messaging."
    _postgres_execute(
        product_postgis_dsn(),
        [
            """
            INSERT INTO product_ai_advisory_jobs(job_id, case_id, status, provider_mode, idempotency_key)
            VALUES ({job_id}, {case_id}, 'completed', 'mock-openai-compatible-vllm-ready', {idem})
            ON CONFLICT (idempotency_key) DO UPDATE SET status = 'completed', updated_at = now();
            INSERT INTO product_ai_advisory_results(job_id, summary, recommendation, human_review_required, model_detail)
            VALUES ({job_id}, {summary}, {recommendation}, true, 'mock default; optional AMD Developer Cloud vLLM/OpenAI-compatible endpoint')
            ON CONFLICT (job_id) DO UPDATE SET summary = EXCLUDED.summary, recommendation = EXCLUDED.recommendation;
            """.format(
                job_id=_sql_literal(job_id),
                case_id="NULL" if case_id is None else _sql_literal(case_id),
                idem=_sql_literal(idempotency_key),
                summary=_sql_literal(summary),
                recommendation=_sql_literal(recommendation),
            )
        ],
        TIMEOUT,
    )
    _redis_command(product_redis_url(), ["XADD", "product:ai-advisory", "*", "job_id", job_id, "case_id", case["case_id"]])
    return latest_ai_advisory()


def sync_field(worker_id: str, updates: list[dict[str, Any]]) -> dict[str, Any]:
    actor = resolve_actor(worker_id, fallback="worker-alpha-boat")
    require_role(actor, "field_sync")
    try:
        return _sync_field_live(worker_id, updates)
    except Exception:
        applied = []
        conflicts = []
        for update in updates:
            case_id = str(update.get("case_id") or _LOCAL_CASES[0]["case_id"])
            try:
                if update.get("action") == "evidence":
                    applied.append(add_evidence(case_id, worker_id, dict(update.get("metadata") or {}), str(update.get("idempotency_key") or _stable_key("sync-evidence", worker_id, case_id))))
                else:
                    applied.append(update_status(case_id, str(update.get("status") or "in_progress"), worker_id, str(update.get("note") or ""), str(update.get("idempotency_key") or _stable_key("sync-status", worker_id, case_id)), _optional_int(update.get("expected_revision"))))
            except ProductApiError as exc:
                if exc.status != 409:
                    raise
                conflict = {"status": "conflict", "case_id": case_id, "attempted": update, "server_case": get_case(case_id), "safe_actions": ["refresh", "retry", "keep local as note", "escalate"], "error": str(exc)}
                conflicts.append(conflict)
                _LOCAL_DLQ.append({"type": "conflict_replay", "actor": actor, "case_id": case_id, "context": conflict, "created_at": time.time()})
        _LOCAL_OUTBOX.clear()
        _local_audit(actor, "field_sync", None, {"updates": len(updates), "conflicts": len(conflicts)})
        return {"status": "conflict" if conflicts else "synced", "applied": applied, "conflicts": conflicts, "dlq": list(_LOCAL_DLQ[-5:]), "cases": field_my_cases(worker_id)["cases"]}


def _sync_field_live(worker_id: str, updates: list[dict[str, Any]]) -> dict[str, Any]:
    applied = []
    for update in updates:
        case_id = str(update.get("case_id") or "")
        idem = str(update.get("idempotency_key") or _stable_key("sync", worker_id, case_id, json.dumps(update, sort_keys=True)))
        action = str(update.get("action") or "status")
        if action == "evidence":
            applied.append(add_evidence(case_id, worker_id, dict(update.get("metadata") or {}), idem))
        else:
            applied.append(update_status(case_id, str(update.get("status") or "in_progress"), worker_id, str(update.get("note") or ""), idem, _optional_int(update.get("expected_revision"))))
    _redis_command(product_redis_url(), ["DEL", f"product:field:{worker_id}:pending"])
    return {"status": "synced", "applied": applied, "cases": field_my_cases(worker_id)["cases"]}


def system_health() -> dict[str, Any]:
    try:
        return _system_health_live()
    except Exception:
        return {
            "postgis": "LOCAL_MOCK",
            "redis": "LOCAL_MOCK",
            "outbox_depth": len(_LOCAL_OUTBOX),
            "ai_queue_depth": 1 if _LOCAL_AI.get("job_id") else 0,
            "worker_mode": "deterministic in-process local facade",
            "retry_count": sum(int(item.get("attempts") or 0) for item in _LOCAL_OUTBOX),
            "dlq_count": len(_LOCAL_DLQ),
            "provider_mode": "local/mock",
            "provider_status": "degraded" if not os.environ.get("TWILIO_ACCOUNT_SID") else "configured-live",
            "last_error": _LOCAL_DLQ[-1]["context"]["error"] if _LOCAL_DLQ else None,
        }


def _system_health_live() -> dict[str, Any]:
    redis_url = product_redis_url()
    return {
        "postgis": "PASS",
        "redis": "PASS" if _redis_command(redis_url, ["PING"]) == "PONG" else "FAIL",
        "outbox_depth": int(_redis_command(redis_url, ["XLEN", "product:outbox"]) or 0),
        "ai_queue_depth": int(_redis_command(redis_url, ["XLEN", "product:ai-advisory"]) or 0),
        "worker_mode": "stateless handlers with Redis outbox/replay",
        "retry_count": 0,
        "dlq_count": 0,
        "provider_mode": "configured-live" if os.environ.get("TWILIO_ACCOUNT_SID") else "local/mock",
        "provider_status": "configured-live" if os.environ.get("TWILIO_ACCOUNT_SID") else "degraded",
        "last_error": None,
    }


def latest_ai_advisory() -> dict[str, Any]:
    try:
        return _latest_ai_advisory_live()
    except Exception:
        return dict(_LOCAL_AI)


def _latest_ai_advisory_live() -> dict[str, Any]:
    rows = _postgres_query(
        product_postgis_dsn(),
        """
        SELECT j.job_id, COALESCE(j.case_id, ''), j.status, r.summary, r.recommendation,
               r.human_review_required::text, r.model_detail
        FROM product_ai_advisory_jobs j
        JOIN product_ai_advisory_results r ON r.job_id = j.job_id
        ORDER BY j.updated_at DESC
        LIMIT 1;
        """,
        TIMEOUT,
    )
    if not rows:
        return {"status": "not_requested", "human_review_required": True}
    row = rows[0]
    return {
        "job_id": row[0],
        "case_id": row[1],
        "status": row[2],
        "summary": row[3],
        "recommendation": row[4],
        "human_review_required": row[5] == "true",
        "model_detail": row[6],
    }


def get_case(case_id: str | None) -> dict[str, Any]:
    try:
        return _get_case_live(case_id)
    except Exception:
        return dict(_local_get_case(case_id))


def _get_case_live(case_id: str | None) -> dict[str, Any]:
    if not case_id:
        raise ProductApiError(400, "case_id is required")
    rows = _postgres_query(
        product_postgis_dsn(),
        """
        SELECT case_id, title, safe_summary, urgency, need_type, status, operation_zone_id,
               location_clue, COALESCE(people_count::text, ''), COALESCE(assigned_worker_id, ''),
               COALESCE(ST_X(geom)::text, ''), COALESCE(ST_Y(geom)::text, '')
        FROM product_cases WHERE case_id = {case_id};
        """.format(case_id=_sql_literal(case_id)),
        TIMEOUT,
    )
    if not rows:
        raise ProductApiError(404, "case not found")
    return _case_from_row(rows[0])


def product_api_smoke(root: Path = ROOT, live_required: bool = False) -> int:
    try:
        try:
            init_product_live_state(root)
        except Exception:
            if live_required:
                raise
        overview = command_overview()
        worker_id = "worker-alpha-boat"
        first_case = _select_smoke_case(overview["cases"], worker_id)
        smoke_run = _stable_key("smoke", str(os.getpid()), str(time.time_ns()), first_case)
        assign_key = f"{smoke_run}-assign"
        status_key = f"{smoke_run}-status"
        message_key = f"{smoke_run}-message"
        sync_key = f"{smoke_run}-sync"
        ai_key = f"{smoke_run}-ai"
        drill_key = f"{smoke_run}-drill"
        evidence_key = f"{smoke_run}-evidence"
        assigned = assign_case(first_case, worker_id, "command-operator", assign_key)
        duplicate_assign = assign_case(first_case, worker_id, "command-operator", assign_key)
        status = update_status(first_case, "in_progress", worker_id, "smoke retry", status_key)
        duplicate_status = update_status(first_case, "complete", worker_id, "smoke retry", status_key)
        message = send_message(first_case, "sms", "Local demo message; paid integration disabled.", message_key)
        duplicate_message = send_message(first_case, "sms", "duplicate", message_key)
        evidence = add_evidence(
            first_case,
            worker_id,
            {"media_type": "text/plain", "file_name": "smoke-note.txt", "file_base64": base64.b64encode(b"field evidence smoke").decode()},
            evidence_key,
        )
        sync = sync_field(worker_id, [{"case_id": first_case, "status": "acknowledged", "idempotency_key": sync_key}])
        ai = request_ai_advisory(first_case, ai_key)
        drill = run_drill(drill_key)
        try:
            audit_rows = _postgres_query(product_postgis_dsn(), "SELECT COUNT(*)::text FROM product_audit_events;", TIMEOUT)
            audit_count = int(audit_rows[0][0] or 0)
        except Exception:
            audit_count = len(_LOCAL_AUDIT)
        checks = [
            ("overview", overview["summary"]["total_cases"] > 0),
            ("assign", assigned["status"] == "assigned" and duplicate_assign["status"] == "duplicate"),
            ("status_idempotency", status["status"] == "updated" and duplicate_status["status"] == "duplicate"),
            ("message_idempotency", message["message_id"] == duplicate_message["message_id"]),
            ("evidence_upload", evidence["status"] == "stored" and evidence["evidence"]["size"] > 0),
            ("offline_sync", sync["status"] == "synced"),
            ("ai_review_required", ai.get("human_review_required") is True),
            ("drill", drill["result"]["deterministic"] is True),
            ("audit", audit_count > 0),
        ]
    except Exception as exc:
        if live_required:
            print(f"product live-stack smoke FAIL: {exc}")
            return 1
        print(f"product api smoke FAIL: {exc}")
        return 1
    failed = [name for name, ok in checks if not ok]
    if failed:
        print("product api smoke FAIL: " + ", ".join(failed))
        return 1
    print("product api smoke PASS")
    for name, _ok in checks:
        print(f"- PASS {name}")
    return 0


def action_map_check(root: Path = ROOT) -> int:
    path = root / "acceptance" / "product_action_map.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"product action map FAIL: missing {path.relative_to(root)}")
        return 1
    if payload.get("contract") != "reliefqueue-product-action-map/v1":
        print("product action map FAIL: bad contract")
        return 1
    dashboard_src = root / "dashboard" / "src"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(dashboard_src.rglob("*"))
        if path.is_file() and path.suffix in {".js", ".jsx", ".ts", ".tsx"}
    )
    failures: list[str] = []
    actions = payload.get("actions")
    if not isinstance(actions, list):
        actions = [action for surface in payload.get("surfaces", []) for action in surface.get("actions", [])]
    for action in actions:
        selector = action.get("selector")
        action_id = action.get("action_id") or str(selector or "").replace('data-action-id="', "").rstrip('"')
        selector_value = str(selector or "").replace("[data-action-id=\"", "").rstrip("\"]").replace('data-action-id="', "").rstrip('"')
        if not selector or (selector not in source and selector_value not in source and action_id not in source):
            failures.append(f"stale selector {selector}")
        if "provider_status" in action:
            provider_status = action.get("provider_status")
            if provider_status not in {"local_state", "local_mock", "navigation", "panel", "paid_disabled", "informational"}:
                failures.append(f"unknown provider_status {action_id}: {provider_status}")
            if not action.get("result_selector"):
                failures.append(f"missing result selector {action_id}")
            if not isinstance(action.get("test_coverage"), list) or not action.get("test_coverage"):
                failures.append(f"missing test coverage {action_id}")
            continue
        behavior = action.get("behavior")
        if behavior not in {"navigate", "state_update", "api_mutation", "api_query", "paid_disabled"}:
            failures.append(f"unknown behavior {selector}: {behavior}")
        if behavior in {"api_mutation", "api_query"} and not action.get("api"):
            failures.append(f"missing api {selector}")
    if failures:
        print("product action map FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("product action map PASS")
    print(f"- checked {len(actions)} mapped actions")
    return 0


DASHBOARD_DIST = ROOT / "dashboard" / "dist"

# Client-side routed SPA path prefixes. Any GET that doesn't match a static
# file under dashboard/dist and doesn't start with /api/ or /healthz falls
# back to index.html so the dashboard's own router can render the route.
SPA_ROUTE_PREFIXES = (
    "/dashboard",
    "/field",
    "/local-coordinator",
    "/internal/classic-dashboard",
)



def _require_live_amd_synthetic_confirmation(route: str, body: dict[str, Any]) -> None:
    """Protect public live-provider routes without constraining internal Python callers."""

    normalized = route.rstrip("/")
    if normalized == "/api/ai/live-verification":
        user_text = str(body.get("text") or "").strip()
        if user_text and body.get("synthetic_confirmed") is not True:
            raise ProductApiError(400, "Confirm synthetic demonstration data before live provider processing")
        return
    if normalized == "/api/ai/burst-verification" and body.get("synthetic_confirmed") is not True:
        raise ProductApiError(400, "Confirm every report is synthetic demonstration data before live provider processing")

def serve(host: str, port: int, root: Path = ROOT) -> int:
    cors_origins = {
        origin.strip()
        for origin in os.environ.get("RELIEFQUEUE_CORS_ORIGINS", "").split(",")
        if origin.strip()
    }

    try:
        init_product_live_state(root)
    except Exception as exc:
        print(f"ReliefQueue product API using deterministic local facade: {exc}")

    dist_dir = root / "dashboard" / "dist"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            route = parsed.path.rstrip("/") or "/"
            if route == "/healthz":
                self._json(200, {"status": "ok"})
                return
            if route.startswith("/api/product/"):
                self._handle("GET")
                return
            self._serve_static(parsed.path)

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def do_OPTIONS(self) -> None:  # noqa: N802
            route = urlparse(self.path).path.rstrip("/")
            origin = self.headers.get("Origin", "")
            if not route.startswith("/api/product/"):
                self.send_error(404, "Not found")
                return
            if not origin or origin not in cors_origins:
                self.send_error(403, "CORS origin not allowed")
                return
            self.send_response(204)
            self._cors_headers()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _cors_headers(self) -> None:
            origin = self.headers.get("Origin", "")
            if origin and origin in cors_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

        def _handle(self, method: str) -> None:
            try:
                body = self._read_json()
                route = urlparse(self.path).path.rstrip("/")
                if method == "POST" and route in LIVE_AMD_ROUTES:
                    _require_live_amd_synthetic_confirmation(route, body)
                    forwarded = self.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
                    client_key = forwarded or str(self.client_address[0])
                    budget = consume_live_amd_budget(client_key, route, body)
                    if not budget["allowed"]:
                        self._json(
                            429,
                            {
                                "error": "Live AMD judge-demo request budget reached. Retry later.",
                                "rate_limit_scope": budget.get("scope"),
                                "estimated_provider_call_cost": budget["cost"],
                                "retry_after_seconds": budget["retry_after_seconds"],
                                "human_review_required": True,
                            },
                            headers={"Retry-After": str(budget["retry_after_seconds"])},
                        )
                        return
                payload = _route(method, self.path, body)
                if isinstance(payload, bytes):
                    self._bytes(200, payload)
                else:
                    self._json(200, payload)
            except ProductApiError as exc:
                self._json(exc.status, {"error": str(exc)})
            except json.JSONDecodeError:
                self._json(400, {"error": "Request body must be valid JSON"})
            except Exception as exc:
                self._json(500, {"error": str(exc)})

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                return {}
            max_bytes = positive_env_int("RELIEFQUEUE_MAX_JSON_BODY_BYTES", LIVE_AMD_DEFAULT_MAX_BODY_BYTES)
            if max_bytes and length > max_bytes:
                raise ProductApiError(413, f"Request body exceeds {max_bytes} bytes")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ProductApiError(400, "Request body must be a JSON object")
            return payload

        def _json(self, status: int, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._cors_headers()
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _bytes(self, status: int, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/octet-stream")
            self._cors_headers()
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _serve_static(self, raw_path: str) -> None:
            if not dist_dir.is_dir():
                self._json(
                    503,
                    {
                        "error": "dashboard build not found; run `make replit-build` "
                        "(or `make dashboard-build`) before serving."
                    },
                )
                return
            url_path = unquote(urlparse(raw_path).path)
            relative = url_path.lstrip("/")
            requested = (dist_dir / relative).resolve() if relative else dist_dir / "index.html"
            is_asset_request = "." in Path(relative).name
            try:
                requested.relative_to(dist_dir.resolve())
            except ValueError:
                self.send_error(404, "Not found")
                return
            if requested.is_file():
                self._send_file(requested)
                return
            if is_asset_request:
                self.send_error(404, "Not found")
                return
            if url_path == "/" or any(
                url_path == prefix or url_path.startswith(prefix + "/") for prefix in SPA_ROUTE_PREFIXES
            ):
                self._send_file(dist_dir / "index.html")
                return
            self.send_error(404, "Not found")

        def _send_file(self, file_path: Path) -> None:
            content_type, _ = mimetypes.guess_type(str(file_path))
            raw = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(raw)))
            if file_path.name == "index.html":
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"ReliefQueue product API: http://{host}:{port}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        thread.join()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "smoke", "live-smoke", "action-map-check", "serve"])
    parser.add_argument("--host", default=os.environ.get("RELIEFQUEUE_PRODUCT_API_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(
            os.environ.get("PORT")
            or os.environ.get("RELIEFQUEUE_PRODUCT_API_PORT")
            or "5000"
        ),
    )
    args = parser.parse_args(argv)
    if args.command == "init":
        print(json.dumps(init_product_live_state(), indent=2))
        return 0
    if args.command == "smoke":
        return product_api_smoke()
    if args.command == "live-smoke":
        return product_api_smoke(live_required=True)
    if args.command == "action-map-check":
        return action_map_check()
    return serve(args.host, args.port)


def _route(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    parsed = urlparse(path)
    query = parse_qs(parsed.query)
    route = parsed.path.rstrip("/")
    if method == "GET" and route == "/api/product/command/overview":
        return command_overview()
    if method == "GET" and route == "/api/product/amd/evidence":
        return public_amd_evidence_payload()
    if method == "GET" and route == "/api/product/amd/capability":
        return amd_capability_payload()
    if method == "GET" and route == "/api/product/session/me":
        return {"session": resolve_actor(query.get("actor_id", ["command-operator"])[0]), "available_identities": list(IDENTITIES.values())}
    if method == "GET" and route == "/api/product/monitoring":
        return monitoring_status()
    if method == "GET" and route == "/api/product/production/config":
        return production_config_status()
    if method == "GET" and route == "/api/product/messaging/status":
        return messaging_status()
    if method == "GET" and route == "/api/product/maps/offline":
        return offline_map_data()
    if method == "GET" and route == "/api/product/evidence":
        return {"evidence": list(_LOCAL_EVIDENCE)}
    if method == "GET" and route.startswith("/api/product/evidence/"):
        parts = route.split("/")
        if len(parts) >= 6:
            return retrieve_evidence(parts[4], parts[5])
    if method == "GET" and route == "/api/product/command/cases":
        return list_cases()
    if method == "GET" and route == "/api/product/field/my-cases":
        return field_my_cases(query.get("worker_id", ["worker-alpha-boat"])[0])
    if method == "POST" and route == "/api/product/command/assign":
        return assign_case(body["case_id"], body["worker_id"], body.get("actor_id", "command-operator"), body["idempotency_key"], _optional_int(body.get("expected_revision")))
    if method == "POST" and route == "/api/product/command/status":
        return update_status(body["case_id"], body["status"], body.get("actor_id", "command-operator"), body.get("note", ""), body["idempotency_key"], _optional_int(body.get("expected_revision")))
    if method == "POST" and route == "/api/product/command/message":
        return send_message(body["case_id"], body.get("channel", "sms"), body.get("body", ""), body["idempotency_key"], body.get("actor_id", "command-operator"), body.get("provider", "local_mock"))
    if method == "POST" and route == "/api/product/messaging/webhook":
        return normalize_inbound_webhook(body.get("provider", "local_mock"), body.get("payload", body))
    if method == "POST" and route == "/api/product/messaging/replay-dlq":
        return replay_dlq(body.get("actor_id", "command-operator"))
    if method == "POST" and route == "/api/product/command/drill":
        return run_drill(body["idempotency_key"])
    if method == "POST" and route == "/api/product/command/ai-advisory":
        return request_ai_advisory(body.get("case_id"), body["idempotency_key"])
    if method == "POST" and route == "/api/product/field/action":
        if body.get("action") == "evidence":
            return add_evidence(body["case_id"], body.get("worker_id", "worker-alpha-boat"), body.get("metadata", {}), body["idempotency_key"])
        return update_status(body["case_id"], body.get("status", "in_progress"), body.get("worker_id", "worker-alpha-boat"), body.get("note", ""), body["idempotency_key"], _optional_int(body.get("expected_revision")))
    if method == "POST" and route == "/api/product/field/sync":
        return sync_field(body.get("worker_id", "worker-alpha-boat"), body.get("updates", []))
    if method == "GET" and route == "/api/product/local/scenario":
        return local_scenario()
    if method == "GET" and route == "/api/product/local/cases":
        return {"cases": list_cases(limit=20)["cases"]}
    if method == "GET" and route == "/api/product/local/workers":
        return local_workers()
    if method == "POST" and route == "/api/product/local/scenario":
        return update_local_scenario(body)
    if method == "POST" and route == "/api/ai/live-verification":
        return live_verification(body)
    if method == "POST" and route == "/api/ai/burst-parse":
        try:
            return parsed_preview(str(body.get("text") or body.get("raw") or ""))
        except BurstParseError as exc:
            raise ProductApiError(400, str(exc)) from exc
    if method == "POST" and route == "/api/ai/burst-verification":
        return burst_verification(body)
    raise ProductApiError(404, f"unknown product API route: {route}")


BURST_MAX_CASES = LIVE_AMD_MAX_CASES
BURST_VALID_CONCURRENCY = {1, 2, 4, 6, 8}


def live_verification(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST /api/ai/live-verification — bounded real inference for judge evidence.

    Structured single/dossier calls bind a fresh nonce into the provider prompt.
    A result is VERIFIED LIVE only when provider transport succeeded, provider
    JSON was used for the displayed analysis, the nonce was echoed exactly, and
    the completion was not truncated.
    """

    import datetime as _dt

    body = body or {}
    user_text = str(body.get("text") or "").strip()

    config = AIConfig.from_env()
    verified_at = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if config.mode != "openai_compatible":
        metadata = build_model_metadata(served_model=config.model, verified_at=verified_at)
        return {
            "status": "failed",
            "verified_live": False,
            **{key: metadata.get(key) for key in ["provider", "runtime", "accelerator", "served_model", "underlying_model"]},
            "model_metadata": metadata,
            "request_id": None,
            "challenge_nonce": None,
            "nonce_sent_to_provider": False,
            "nonce_echoed_by_provider": False,
            "verification_bound_to_nonce": False,
            "provider_response_received": False,
            "analysis_source": "none",
            "verified_at": verified_at,
            "latency_ms": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "fallback_used": True,
            "human_review_required": True,
            "synthetic_input": None,
            "generated_advisory": None,
            "warnings": ["AI_MODE is not openai_compatible; live verification requires the AMD endpoint to be configured."],
            "error": f"AI_MODE={config.mode!r}; set AI_MODE=openai_compatible and configure OPENAI_COMPAT_* to enable live verification.",
        }

    adapter = OpenAICompatibleAdapter(config)
    workload_mode = str(body.get("workload_mode") or body.get("mode") or "single")
    if workload_mode in {"complex", "dossier"}:
        workload_mode = "complex_dossier"

    if user_text and workload_mode in {"single", "complex_dossier"}:
        try:
            result = _structured_workload_verification(
                adapter,
                user_text,
                workload_mode,
                "JUDGE-SINGLE" if workload_mode == "single" else "JUDGE-DOSSIER",
                synthetic_confirmed=bool((body or {}).get("synthetic_confirmed")),
            )
        except ContextBudgetError as exc:
            result = _amd_quality_failure(str(exc), user_text, served_model=config.model)
    elif user_text:
        result = adapter.verify_user_input(user_text, case_id="JUDGE-SINGLE")
        result["provider_response_received"] = bool(result.get("verified_live"))
        result["analysis_source"] = "provider" if result.get("verified_live") else "none"
        result["nonce_sent_to_provider"] = False
        result["nonce_echoed_by_provider"] = False
        result["verification_bound_to_nonce"] = False
        result["model_metadata"] = _model_metadata(result, verified_at=verified_at)
    else:
        result = adapter.live_verify()
        result["challenge_nonce"] = None
        result["provider_response_received"] = bool(result.get("verified_live"))
        result["analysis_source"] = "provider" if result.get("verified_live") else "none"
        result["nonce_sent_to_provider"] = False
        result["nonce_echoed_by_provider"] = False
        result["verification_bound_to_nonce"] = False
        result["model_metadata"] = _model_metadata(result, verified_at=verified_at)

    result["verified_at"] = verified_at
    if isinstance(result.get("model_metadata"), dict):
        result["model_metadata"]["verified_at"] = verified_at
    return result


def _structured_workload_verification(
    adapter: OpenAICompatibleAdapter,
    user_text: str,
    workload_mode: str,
    case_id: str,
    *,
    synthetic_confirmed: bool = True,
) -> dict[str, Any]:
    import datetime as _dt

    def _utc_now() -> str:
        return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _normalize_call(
        call_result: dict[str, Any],
        nonce: str,
        budget: dict[str, Any],
    ) -> dict[str, Any]:
        transport_verified = bool(call_result.get("verified_live")) and not bool(call_result.get("fallback_used"))
        raw_content = str(call_result.get("raw_content") or call_result.get("generated_advisory") or "")
        structured, warnings, source = normalize_structured_output(
            workload_mode,
            raw_content,
            sanitized,
            case_id,
        )
        nonce_echoed = source in {"provider", "provider_incomplete"} and str(
            structured.get("challenge_nonce") or ""
        ) == nonce
        truncated = call_result.get("finish_reason") == "length"
        semantic_issues = (
            dossier_semantic_issues(structured, sanitized)
            if workload_mode == "complex_dossier" and source in {"provider", "provider_incomplete"}
            else []
        )
        semantic_complete = not semantic_issues
        if semantic_issues and source == "provider":
            source = "provider_incomplete"
            warnings.append(
                "Provider JSON failed deterministic dossier completeness checks; result is not VERIFIED LIVE."
            )
        return {
            "transport_verified": transport_verified,
            "structured": structured,
            "warnings": warnings,
            "analysis_source": source,
            "nonce": nonce,
            "nonce_echoed": nonce_echoed,
            "truncated": truncated,
            "semantic_issues": semantic_issues,
            "semantic_complete": semantic_complete,
            "budget": budget,
            "result": call_result,
        }

    sanitized = sanitize_text(user_text)
    deterministic_prompt_support = (
        build_dossier_reasoning_ledger(sanitized)
        if workload_mode == "complex_dossier"
        else None
    )
    budget_key = "complex_dossier" if workload_mode == "complex_dossier" else "single"
    requested_tokens = WORKLOAD_COMPLETION_BUDGETS[budget_key]

    initial_nonce = os.urandom(8).hex()
    initial_messages = build_workload_prompt(
        workload_mode,
        sanitized,
        case_id,
        initial_nonce,
    )
    initial_budget = enforce_context_budget(
        initial_messages[-1]["content"],
        requested_tokens,
    )
    initial_result = adapter.complete_messages(
        initial_messages,
        max_tokens=requested_tokens,
    )
    initial_call = _normalize_call(initial_result, initial_nonce, initial_budget)
    calls = [initial_call]

    selected = initial_call
    repair_attempted = False
    repair_succeeded = False
    repair_reason: list[str] = []
    repair_evidence: dict[str, Any] | None = None
    repair_rounds = 0
    incident_supplement_attempted = False
    incident_supplement_succeeded = False
    incident_supplement_evidence: dict[str, Any] | None = None

    should_repair = (
        workload_mode == "complex_dossier"
        and initial_call["transport_verified"]
        and (
            initial_call["analysis_source"] != "provider"
            or not initial_call["nonce_echoed"]
            or initial_call["truncated"]
            or not initial_call["semantic_complete"]
        )
    )
    if should_repair:
        repair_attempted = True
        repair_rounds = 1
        repair_reason = list(initial_call["semantic_issues"])
        if initial_call["analysis_source"] == "local_safe_fallback":
            repair_reason.append("initial provider output was not valid structured JSON")
        if not initial_call["nonce_echoed"]:
            repair_reason.append("initial provider output did not echo the challenge nonce")
        if initial_call["truncated"]:
            repair_reason.append("initial provider output was truncated")

        repair_nonce = os.urandom(8).hex()
        repair_messages = build_dossier_repair_prompt(
            sanitized,
            initial_call["structured"],
            list(dict.fromkeys(repair_reason)),
            repair_nonce,
        )
        repair_tokens = WORKLOAD_COMPLETION_BUDGETS["complex_dossier_repair"]
        repair_budget = enforce_context_budget(
            repair_messages[-1]["content"],
            repair_tokens,
        )
        repair_result = adapter.complete_messages(
            repair_messages,
            max_tokens=repair_tokens,
        )
        repair_call = _normalize_call(repair_result, repair_nonce, repair_budget)
        calls.append(repair_call)

        provider_reconciliation: dict[str, Any] | None = None
        if (
            initial_call["analysis_source"] in {"provider", "provider_incomplete"}
            and repair_call["analysis_source"] in {"provider", "provider_incomplete"}
            and repair_call["transport_verified"]
            and repair_call["nonce_echoed"]
            and not repair_call["truncated"]
        ):
            reconciled, provider_reconciliation = reconcile_provider_dossier_outputs(
                initial_call["structured"],
                repair_call["structured"],
                source_text=sanitized,
            )
            reconciled_issues = dossier_semantic_issues(reconciled, sanitized)
            reconciled_complete = (
                not provider_reconciliation["missing_core_fields"]
                and not reconciled_issues
            )
            repair_call = dict(repair_call)
            repair_call["structured"] = reconciled
            repair_call["semantic_issues"] = reconciled_issues
            repair_call["semantic_complete"] = reconciled_complete
            repair_call["analysis_source"] = (
                "provider" if reconciled_complete else "provider_incomplete"
            )
            repair_call["provider_reconciliation"] = provider_reconciliation
            repair_call["warnings"] = list(repair_call["warnings"]) + [
                "Initial and repair AMD provider JSON were reconciled without "
                "adding local operational conclusions."
            ]
            calls[-1] = repair_call

        repair_succeeded = (
            repair_call["transport_verified"]
            and repair_call["analysis_source"] == "provider"
            and repair_call["nonce_echoed"]
            and not repair_call["truncated"]
            and repair_call["semantic_complete"]
        )

        if (
            not repair_succeeded
            and provider_reconciliation is not None
            and dossier_incident_supplement_required(
                repair_call["semantic_issues"],
                provider_reconciliation,
            )
        ):
            incident_supplement_attempted = True
            repair_rounds = 2
            supplement_nonce = os.urandom(8).hex()
            supplement_messages = (
                build_dossier_incident_supplement_prompt(
                    sanitized,
                    repair_call["structured"],
                    repair_call["semantic_issues"],
                    provider_reconciliation,
                    supplement_nonce,
                )
            )
            supplement_tokens = WORKLOAD_COMPLETION_BUDGETS[
                "complex_dossier_incident_supplement"
            ]
            supplement_budget = enforce_context_budget(
                supplement_messages[-1]["content"],
                supplement_tokens,
            )
            supplement_result = adapter.complete_messages(
                supplement_messages,
                max_tokens=supplement_tokens,
            )
            supplement_transport_verified = bool(
                supplement_result.get("verified_live")
            ) and not bool(supplement_result.get("fallback_used"))
            supplement_raw = str(
                supplement_result.get("raw_content")
                or supplement_result.get("generated_advisory")
                or ""
            )
            (
                supplement_record,
                supplement_warnings,
                supplement_source,
            ) = normalize_dossier_incident_supplement(supplement_raw)
            supplement_nonce_echoed = (
                supplement_source in {"provider", "provider_incomplete"}
                and str(supplement_record.get("challenge_nonce") or "")
                == supplement_nonce
            )
            supplement_truncated = (
                supplement_result.get("finish_reason") == "length"
            )

            supplement_reconciliation: dict[str, Any] | None = None
            supplement_structured = repair_call["structured"]
            supplement_issues = list(repair_call["semantic_issues"])
            supplement_complete = False
            if (
                supplement_transport_verified
                and supplement_source
                in {"provider", "provider_incomplete"}
                and supplement_nonce_echoed
                and not supplement_truncated
            ):
                (
                    supplement_structured,
                    supplement_reconciliation,
                ) = reconcile_provider_incident_supplement(
                    repair_call["structured"],
                    supplement_record,
                    sanitized,
                    provider_reconciliation,
                )
                supplement_issues = dossier_semantic_issues(
                    supplement_structured,
                    sanitized,
                )
                supplement_complete = (
                    bool(
                        supplement_reconciliation.get(
                            "complete_source_partition"
                        )
                    )
                    and not supplement_issues
                )
                supplement_source = (
                    "provider"
                    if supplement_complete
                    else "provider_incomplete"
                )
                provider_reconciliation = dict(provider_reconciliation)
                provider_reconciliation[
                    "provider_incident_supplement"
                ] = supplement_reconciliation

            supplement_call = {
                "transport_verified": supplement_transport_verified,
                "structured": supplement_structured,
                "warnings": list(supplement_warnings)
                + [
                    "A targeted AMD provider incident supplement was "
                    "requested after the full repair left only an "
                    "incident-count miss."
                ],
                "analysis_source": supplement_source,
                "nonce": supplement_nonce,
                "nonce_echoed": supplement_nonce_echoed,
                "truncated": supplement_truncated,
                "semantic_issues": supplement_issues,
                "semantic_complete": supplement_complete,
                "budget": supplement_budget,
                "result": supplement_result,
                "provider_reconciliation": provider_reconciliation,
            }
            calls.append(supplement_call)

            incident_supplement_succeeded = (
                supplement_call["transport_verified"]
                and supplement_call["analysis_source"] == "provider"
                and supplement_call["nonce_echoed"]
                and not supplement_call["truncated"]
                and supplement_call["semantic_complete"]
            )
            incident_supplement_evidence = {
                "request_id": supplement_result.get("request_id"),
                "challenge_nonce": supplement_nonce,
                "verified_live": incident_supplement_succeeded,
                "analysis_source": supplement_call["analysis_source"],
                "nonce_echoed_by_provider": (
                    supplement_call["nonce_echoed"]
                ),
                "semantic_completeness": (
                    supplement_call["semantic_complete"]
                ),
                "semantic_issues": supplement_call["semantic_issues"],
                "finish_reason": supplement_result.get("finish_reason"),
                "latency_ms": supplement_result.get("latency_ms"),
                "prompt_tokens": supplement_result.get("prompt_tokens"),
                "completion_tokens": supplement_result.get(
                    "completion_tokens"
                ),
                "total_tokens": supplement_result.get("total_tokens"),
                "provider_incident_supplement": (
                    supplement_reconciliation
                ),
            }
            if supplement_call["analysis_source"] in {
                "provider",
                "provider_incomplete",
            }:
                repair_call = supplement_call

            repair_succeeded = (
                repair_call["transport_verified"]
                and repair_call["analysis_source"] == "provider"
                and repair_call["nonce_echoed"]
                and not repair_call["truncated"]
                and repair_call["semantic_complete"]
            )

        repair_evidence = {
            "request_id": repair_result.get("request_id"),
            "challenge_nonce": repair_nonce,
            "verified_live": repair_succeeded,
            "analysis_source": repair_call["analysis_source"],
            "nonce_echoed_by_provider": repair_call["nonce_echoed"],
            "semantic_completeness": repair_call["semantic_complete"],
            "semantic_issues": repair_call["semantic_issues"],
            "finish_reason": repair_result.get("finish_reason"),
            "latency_ms": repair_result.get("latency_ms"),
            "prompt_tokens": repair_result.get("prompt_tokens"),
            "completion_tokens": repair_result.get("completion_tokens"),
            "total_tokens": repair_result.get("total_tokens"),
            "provider_reconciliation": provider_reconciliation,
            "repair_rounds": repair_rounds,
            "incident_supplement_attempted": (
                incident_supplement_attempted
            ),
            "incident_supplement_succeeded": (
                incident_supplement_succeeded
            ),
            "incident_supplement_evidence": (
                incident_supplement_evidence
            ),
        }
        # Prefer provider-authored repaired content, even when incomplete. A
        # malformed targeted supplement never replaces the fuller reconciled
        # provider dossier.
        if repair_call["analysis_source"] in {
            "provider",
            "provider_incomplete",
        }:
            selected = repair_call

    selected_result = dict(selected["result"])
    structured = selected["structured"]
    analysis_source = selected["analysis_source"]
    verified_at = _utc_now()
    verified_live = (
        selected["transport_verified"]
        and analysis_source == "provider"
        and selected["nonce_echoed"]
        and not selected["truncated"]
        and selected["semantic_complete"]
    )

    request_ids = [
        str(call["result"].get("request_id"))
        for call in calls
        if call["result"].get("request_id")
    ]
    provider_prompt_tokens = sum(int(call["result"].get("prompt_tokens") or 0) for call in calls)
    provider_completion_tokens = sum(int(call["result"].get("completion_tokens") or 0) for call in calls)
    provider_total_tokens = sum(int(call["result"].get("total_tokens") or 0) for call in calls)
    provider_latency_ms = sum(int(call["result"].get("latency_ms") or 0) for call in calls)

    selected_result.update(
        {
            "verified_live": verified_live,
            "provider_transport_verified_live": selected["transport_verified"],
            "provider_response_received": any(call["transport_verified"] for call in calls),
            "fallback_used": bool(selected_result.get("fallback_used"))
            or analysis_source == "local_safe_fallback",
            "analysis_source": analysis_source,
            "challenge_nonce": selected["nonce"],
            "nonce_sent_to_provider": True,
            "nonce_echoed_by_provider": selected["nonce_echoed"],
            "verification_bound_to_nonce": selected["nonce_echoed"],
            "case_id": case_id,
            "original_input": user_text,
            "sanitized_input": sanitized,
            "synthetic_input": sanitized,
            "synthetic_text_sent": True,
            "synthetic_input_confirmed": synthetic_confirmed,
            "private_text_sent": False,
            "secret_values_exposed": False,
            "workload_mode": workload_mode,
            "verified_at": verified_at,
            "context_budget": selected["budget"],
            "structured_output": structured,
            "normalized_structured_record": structured,
            "compact_json": structured,
            "source_evidence_mapping": _source_evidence_mapping(sanitized, structured),
            "operational_analysis": _operational_analysis(structured),
            "generated_advisory": str(structured.get("situation_summary") or "") or None,
            "provider_call_count": len(calls),
            "provider_request_ids": request_ids,
            "provider_prompt_tokens": provider_prompt_tokens,
            "provider_completion_tokens": provider_completion_tokens,
            "provider_total_tokens": provider_total_tokens,
            "provider_latency_ms": provider_latency_ms,
            "semantic_completeness": selected["semantic_complete"],
            "semantic_issues": selected["semantic_issues"],
            "repair_attempted": repair_attempted,
            "repair_succeeded": repair_succeeded,
            "repair_rounds": repair_rounds,
            "incident_supplement_attempted": (
                incident_supplement_attempted
            ),
            "incident_supplement_succeeded": (
                incident_supplement_succeeded
            ),
            "repair_reason": list(dict.fromkeys(repair_reason)),
            "repair_evidence": repair_evidence,
            "provider_reconciliation": selected.get("provider_reconciliation"),
            "deterministic_prompt_support": (
                {
                    "source_report_count": deterministic_prompt_support.get("source_report_count"),
                    "calculation_candidate_count": len(
                        deterministic_prompt_support.get("calculation_candidates") or []
                    ),
                    "conflict_update_signal_count": len(
                        deterministic_prompt_support.get("conflict_update_source_ids") or []
                    ),
                    "support_type": "source_ledger_and_arithmetic_anchors",
                    "final_analysis_source": analysis_source,
                }
                if deterministic_prompt_support
                else None
            ),
        }
    )
    selected_result["request_settings"] = dict(selected_result.get("request_settings") or {}) | {
        "single_completion_max_tokens": WORKLOAD_COMPLETION_BUDGETS["single"],
        "complex_dossier_completion_max_tokens": WORKLOAD_COMPLETION_BUDGETS["complex_dossier"],
        "complex_dossier_repair_max_tokens": WORKLOAD_COMPLETION_BUDGETS["complex_dossier_repair"],
        "complex_dossier_incident_supplement_max_tokens": WORKLOAD_COMPLETION_BUDGETS[
            "complex_dossier_incident_supplement"
        ],
        "burst_case_completion_max_tokens": WORKLOAD_COMPLETION_BUDGETS["burst_case"],
        "cross_case_synthesis_completion_max_tokens": WORKLOAD_COMPLETION_BUDGETS["cross_case_synthesis"],
        "cross_case_synthesis_repair_max_tokens": WORKLOAD_COMPLETION_BUDGETS["cross_case_synthesis_repair"],
        "selected_completion_max_tokens": int(
            selected.get("budget", {}).get(
                "requested_completion_tokens",
                requested_tokens,
            )
        ),
        "silent_truncation_allowed": False,
        "maximum_semantic_repair_calls": (
            2 if workload_mode == "complex_dossier" else 0
        ),
        "provider_response_reconciliation_enabled": workload_mode == "complex_dossier",
    }
    selected_result["model_metadata"] = _model_metadata(selected_result, verified_at=verified_at)
    selected_result["warnings"] = (
        list(selected_result.get("warnings") or [])
        + list(selected["warnings"])
    )
    if repair_attempted:
        if incident_supplement_attempted:
            selected_result["warnings"].append(
                "Two bounded AMD repair calls were used: one full dossier "
                "rewrite and one targeted provider incident supplement."
            )
        else:
            selected_result["warnings"].append(
                "One bounded AMD semantic-repair pass was used because the "
                "first dossier response was incomplete."
            )
    if analysis_source == "local_safe_fallback":
        selected_result["warnings"].append(
            "Displayed structured analysis is local safe fallback, not AMD-generated analysis."
        )
    if analysis_source == "provider_incomplete":
        selected_result["warnings"].append(
            "AMD returned structured JSON, but required operational sections or source coverage remain incomplete; result is not VERIFIED LIVE."
        )
    if analysis_source in {"provider", "provider_incomplete"} and not selected["nonce_echoed"]:
        selected_result["warnings"].append(
            "Provider response did not echo the prompt nonce; result is not labelled VERIFIED LIVE."
        )
        selected_result["verification_failure_reason"] = "provider_nonce_missing_or_mismatched"
    if selected["truncated"]:
        selected_result["verified_live"] = False
        selected_result["warnings"].append(
            "Provider output was truncated; result is not labelled VERIFIED LIVE."
        )
        selected_result["verification_failure_reason"] = "provider_output_truncated"
    if selected["semantic_issues"]:
        selected_result["verified_live"] = False
        selected_result["verification_failure_reason"] = "provider_semantic_completeness_failed"
    selected_result["warnings"] = list(dict.fromkeys(selected_result["warnings"]))
    return selected_result



def _amd_quality_failure(error: str, user_text: str, *, served_model: str | None = None) -> dict[str, Any]:
    import datetime as _dt

    sanitized = sanitize_text(user_text)
    verified_at = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    metadata = build_model_metadata(served_model=served_model, verified_at=verified_at)
    return {
        "status": "failed",
        "verified_live": False,
        **{key: metadata.get(key) for key in ["provider", "runtime", "accelerator", "served_model", "underlying_model"]},
        "model_metadata": metadata,
        "request_id": None,
        "challenge_nonce": None,
        "nonce_sent_to_provider": False,
        "nonce_echoed_by_provider": False,
        "verification_bound_to_nonce": False,
        "provider_response_received": False,
        "analysis_source": "none",
        "verified_at": verified_at,
        "latency_ms": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "fallback_used": True,
        "human_review_required": True,
        "synthetic_input": sanitized,
        "original_input": user_text,
        "sanitized_input": sanitized,
        "synthetic_text_sent": False,
        "private_text_sent": False,
        "secret_values_exposed": False,
        "generated_advisory": None,
        "structured_output": None,
        "warnings": ["Validation failed before provider call."],
        "error": error,
    }


def _model_metadata(result: dict[str, Any], *, verified_at: str | None = None) -> dict[str, Any]:
    return build_model_metadata(
        served_model=str(result.get("served_model") or "") or None,
        served_model_from_provider=bool(result.get("served_model_from_provider")),
        provider=str(result.get("provider") or "") or None,
        runtime=str(result.get("runtime") or "") or None,
        accelerator=str(result.get("accelerator") or "") or None,
        underlying_model=str(result.get("underlying_model") or "") or None,
        verified_at=verified_at or result.get("verified_at"),
    )


def _source_evidence_mapping(sanitized: str, structured: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def add(field: str, evidence: Any, value: Any, confidence: str = "medium") -> None:
        if value is None or value == "" or value == []:
            return
        if isinstance(evidence, (dict, list)):
            evidence_text = json.dumps(evidence, ensure_ascii=False)
        else:
            evidence_text = str(evidence or sanitized[:240])
        if isinstance(value, (dict, list)):
            value_text = json.dumps(value, ensure_ascii=False)
        else:
            value_text = str(value)
        rows.append(
            {
                "field": field,
                "source_evidence": evidence_text[:500],
                "normalized_value": value_text[:900],
                "confidence": confidence,
            }
        )

    add("situation_summary", sanitized[:300], structured.get("situation_summary"), "medium")
    incidents = structured.get("consolidated_incidents")
    if isinstance(incidents, list):
        for index, incident in enumerate(incidents[:6], start=1):
            if not isinstance(incident, dict):
                add(f"consolidated_incident_{index}", sanitized[:300], incident)
                continue
            evidence = {
                "source_ids": incident.get("source_ids") or [],
                "evidence": incident.get("evidence") or [],
            }
            add(f"consolidated_incident_{index}", evidence, incident, str(incident.get("confidence") or "medium"))
    else:
        facts = structured.get("critical_facts") or []
        for index, fact in enumerate(facts[:6] if isinstance(facts, list) else [facts], start=1):
            add(f"critical_fact_{index}", sanitized[:300], fact)

    for field in [
        "contradictions",
        "superseded_updates",
        "unverified_claims",
        "resource_implications",
        "resource_gaps",
        "capacity_pressure",
        "route_and_access_analysis",
        "route_constraints",
    ]:
        add(field, structured.get(field), structured.get(field), "medium")
    return rows[:14]


def _operational_analysis(structured: dict[str, Any]) -> dict[str, Any]:
    return {
        "priorities": structured.get("recommended_priorities") or structured.get("prioritized_operational_plan") or [],
        "contradictions": structured.get("contradictions") or [],
        "routes": structured.get("route_and_access_analysis") or structured.get("route_constraints") or [],
        "resources": structured.get("resource_implications") or structured.get("resource_gaps") or [],
        "capacity_pressure": structured.get("capacity_pressure") or [],
        "review_questions": structured.get("coordinator_questions") or structured.get("missing_information_questions") or [],
        "human_review_required": True,
    }


def burst_verification(body: dict[str, Any]) -> dict[str, Any]:
    """POST /api/ai/burst-verification — per-case AMD analysis plus AMD synthesis."""

    import datetime as _dt

    reports_raw = body.get("reports", [])
    raw_text = body.get("text") or body.get("raw")
    concurrency = int(body.get("concurrency", 4))

    if raw_text and not reports_raw:
        try:
            reports_raw = [{"id": case.id, "text": case.text} for case in parse_burst_input(str(raw_text))]
        except BurstParseError as exc:
            raise ProductApiError(400, str(exc)) from exc
    if not isinstance(reports_raw, list) or len(reports_raw) == 0:
        raise ProductApiError(400, "reports must be a non-empty array or text must contain parseable burst input")
    if len(reports_raw) > BURST_MAX_CASES:
        raise ProductApiError(400, f"Too many cases: {len(reports_raw)} exceeds maximum of {BURST_MAX_CASES}")
    if concurrency not in BURST_VALID_CONCURRENCY:
        raise ProductApiError(400, f"concurrency must be one of {sorted(BURST_VALID_CONCURRENCY)}")

    config = AIConfig.from_env()
    if config.mode != "openai_compatible":
        raise ProductApiError(400, f"AI_MODE={config.mode!r}; burst verification requires openai_compatible mode with AMD endpoint configured")

    adapter = OpenAICompatibleAdapter(config)
    batch_id = "batch-" + hashlib.sha256(f"{time.time()}:{os.urandom(8).hex()}".encode()).hexdigest()[:12]
    started_at = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    normalized: list[dict[str, Any]] = []
    for i, report in enumerate(reports_raw):
        if isinstance(report, str):
            normalized.append({"case_id": f"case-{i + 1:02d}", "text": report})
        elif isinstance(report, dict):
            normalized.append({"case_id": str(report.get("id") or f"case-{i + 1:02d}"), "text": str(report.get("text") or "")})
        else:
            raise ProductApiError(400, f"Invalid report format at index {i}: expected string or object with 'text'")
    try:
        for rep in normalized:
            rep["sanitized_text"] = sanitize_text(rep["text"])
            rep["context_budget"] = enforce_context_budget(rep["sanitized_text"], WORKLOAD_COMPLETION_BUDGETS["burst_case"])
    except ContextBudgetError as exc:
        raise ProductApiError(400, str(exc)) from exc

    overall_start = time.time()

    def run_one(rep: dict[str, Any]) -> dict[str, Any]:
        nonce = os.urandom(8).hex()
        messages = build_workload_prompt("burst_case", rep["sanitized_text"], rep["case_id"], nonce)
        result = adapter.complete_messages(messages, max_tokens=WORKLOAD_COMPLETION_BUDGETS["burst_case"])
        provider_transport_verified = bool(result.get("verified_live")) and not bool(result.get("fallback_used"))
        raw_content = str(result.get("raw_content") or result.get("generated_advisory") or "")
        structured, warnings, analysis_source = normalize_structured_output("burst_case", raw_content, rep["sanitized_text"], rep["case_id"])
        nonce_echoed = analysis_source == "provider" and str(structured.get("challenge_nonce") or "") == nonce
        truncated = result.get("finish_reason") == "length"
        verified_live = provider_transport_verified and analysis_source == "provider" and nonce_echoed and not truncated
        verified_at = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        result.update(
            {
                "case_id": rep["case_id"],
                "verified_live": verified_live,
                "provider_transport_verified_live": provider_transport_verified,
                "provider_response_received": provider_transport_verified,
                "fallback_used": bool(result.get("fallback_used")) or analysis_source == "local_safe_fallback",
                "analysis_source": analysis_source,
                "challenge_nonce": nonce,
                "nonce_sent_to_provider": True,
                "nonce_echoed_by_provider": nonce_echoed,
                "verification_bound_to_nonce": nonce_echoed,
                "verified_at": verified_at,
                "original_input": rep["text"],
                "sanitized_input": rep["sanitized_text"],
                "synthetic_text_sent": True,
                "synthetic_input_confirmed": bool(body.get("synthetic_confirmed")),
                "private_text_sent": False,
                "secret_values_exposed": False,
                "context_budget": rep["context_budget"],
                "structured_output": structured,
                "normalized_structured_record": structured,
                "compact_json": structured,
                "source_evidence_mapping": _source_evidence_mapping(rep["sanitized_text"], structured),
                "operational_analysis": _operational_analysis(structured),
                "generated_advisory": str(structured.get("situation_summary") or "") or None,
            }
        )
        result["request_settings"] = dict(result.get("request_settings") or {}) | {
            "burst_case_completion_max_tokens": WORKLOAD_COMPLETION_BUDGETS["burst_case"],
            "silent_truncation_allowed": False,
        }
        result["model_metadata"] = _model_metadata(result, verified_at=verified_at)
        result["warnings"] = list(result.get("warnings") or []) + warnings
        if analysis_source == "local_safe_fallback":
            result["warnings"].append("Displayed case analysis is local safe fallback, not AMD-generated analysis.")
        if analysis_source == "provider_incomplete":
            result["warnings"].append("AMD returned structured JSON, but required case sections were incomplete; case is not VERIFIED LIVE.")
        if analysis_source in {"provider", "provider_incomplete"} and not nonce_echoed:
            result["warnings"].append("Provider did not echo the prompt nonce; case is not VERIFIED LIVE.")
        if truncated:
            result["verified_live"] = False
            result["warnings"].append("Provider output was truncated; case is not VERIFIED LIVE.")
        return result

    case_results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(run_one, r): r for r in normalized}
        for future in concurrent.futures.as_completed(futures):
            try:
                case_results.append(future.result())
            except Exception as exc:
                rep = futures[future]
                case_results.append(
                    {
                        "case_id": rep["case_id"],
                        "status": "failed",
                        "verified_live": False,
                        "provider_response_received": False,
                        "analysis_source": "none",
                        "fallback_used": True,
                        "human_review_required": True,
                        "error": str(exc),
                        "challenge_nonce": None,
                        "nonce_sent_to_provider": False,
                        "nonce_echoed_by_provider": False,
                        "verification_bound_to_nonce": False,
                        "request_id": None,
                        "verified_at": _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "latency_ms": None,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "total_tokens": None,
                        "generated_advisory": None,
                        "warnings": [str(exc)],
                    }
                )

    case_results.sort(key=lambda r: str(r.get("case_id", "")))

    def _normalize_synthesis_call(
        call_result: dict[str, Any],
        nonce: str,
        budget: dict[str, Any],
    ) -> dict[str, Any]:
        transport_verified = bool(call_result.get("verified_live")) and not bool(call_result.get("fallback_used"))
        structured, warnings, source = normalize_cross_case_synthesis(
            str(call_result.get("raw_content") or call_result.get("generated_advisory") or ""),
            case_results,
        )
        nonce_echoed = source in {"provider", "provider_incomplete"} and str(
            structured.get("challenge_nonce") or ""
        ) == nonce
        truncated = call_result.get("finish_reason") == "length"
        semantic_issues = (
            cross_case_semantic_issues(structured, case_results)
            if source in {"provider", "provider_incomplete"}
            else []
        )
        if semantic_issues and source == "provider":
            source = "provider_incomplete"
            warnings.append(
                "Provider cross-case JSON failed deterministic safety/completeness checks."
            )
        return {
            "result": call_result,
            "structured": structured,
            "warnings": warnings,
            "analysis_source": source,
            "nonce": nonce,
            "nonce_echoed": nonce_echoed,
            "truncated": truncated,
            "semantic_issues": semantic_issues,
            "semantic_complete": not semantic_issues,
            "transport_verified": transport_verified,
            "budget": budget,
        }

    synthesis_started = time.time()
    synthesis_nonce = os.urandom(8).hex()
    synthesis_messages = build_cross_case_synthesis_prompt(case_results, synthesis_nonce)
    synthesis_budget = enforce_context_budget(
        synthesis_messages[-1]["content"],
        WORKLOAD_COMPLETION_BUDGETS["cross_case_synthesis"],
    )
    initial_synthesis_result = adapter.complete_messages(
        synthesis_messages,
        max_tokens=WORKLOAD_COMPLETION_BUDGETS["cross_case_synthesis"],
    )
    initial_synthesis_call = _normalize_synthesis_call(
        initial_synthesis_result,
        synthesis_nonce,
        synthesis_budget,
    )
    synthesis_calls = [initial_synthesis_call]
    selected_synthesis = initial_synthesis_call
    synthesis_repair_attempted = False
    synthesis_repair_succeeded = False
    synthesis_repair_reason = list(initial_synthesis_call["semantic_issues"])

    should_repair_synthesis = (
        initial_synthesis_call["transport_verified"]
        and (
            initial_synthesis_call["analysis_source"] != "provider"
            or not initial_synthesis_call["nonce_echoed"]
            or initial_synthesis_call["truncated"]
            or not initial_synthesis_call["semantic_complete"]
        )
    )
    if should_repair_synthesis:
        synthesis_repair_attempted = True
        if initial_synthesis_call["analysis_source"] == "local_safe_fallback":
            synthesis_repair_reason.append("initial synthesis was not valid structured JSON")
        if not initial_synthesis_call["nonce_echoed"]:
            synthesis_repair_reason.append("initial synthesis did not echo the challenge nonce")
        if initial_synthesis_call["truncated"]:
            synthesis_repair_reason.append("initial synthesis was truncated")

        repair_nonce = os.urandom(8).hex()
        repair_messages = build_cross_case_repair_prompt(
            case_results,
            initial_synthesis_call["structured"],
            list(dict.fromkeys(synthesis_repair_reason)),
            repair_nonce,
        )
        repair_tokens = WORKLOAD_COMPLETION_BUDGETS["cross_case_synthesis_repair"]
        repair_budget = enforce_context_budget(
            repair_messages[-1]["content"],
            repair_tokens,
        )
        repair_result = adapter.complete_messages(
            repair_messages,
            max_tokens=repair_tokens,
        )
        repair_call = _normalize_synthesis_call(
            repair_result,
            repair_nonce,
            repair_budget,
        )
        synthesis_calls.append(repair_call)
        synthesis_repair_succeeded = (
            repair_call["transport_verified"]
            and repair_call["analysis_source"] == "provider"
            and repair_call["nonce_echoed"]
            and not repair_call["truncated"]
            and repair_call["semantic_complete"]
        )
        if repair_call["analysis_source"] in {"provider", "provider_incomplete"}:
            selected_synthesis = repair_call

    synthesis_result = selected_synthesis["result"]
    synthesis = selected_synthesis["structured"]
    synthesis_source = selected_synthesis["analysis_source"]
    synthesis_nonce = selected_synthesis["nonce"]
    synthesis_nonce_echoed = selected_synthesis["nonce_echoed"]
    synthesis_truncated = selected_synthesis["truncated"]
    synthesis_semantic_issues = selected_synthesis["semantic_issues"]
    synthesis_transport_verified = selected_synthesis["transport_verified"]
    synthesis_verified = (
        synthesis_transport_verified
        and synthesis_source == "provider"
        and synthesis_nonce_echoed
        and not synthesis_truncated
        and not synthesis_semantic_issues
    )
    synthesis_verified_at = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    synthesis_request_ids = [
        str(call["result"].get("request_id"))
        for call in synthesis_calls
        if call["result"].get("request_id")
    ]
    synthesis_provider_prompt_tokens = sum(
        int(call["result"].get("prompt_tokens") or 0) for call in synthesis_calls
    )
    synthesis_provider_completion_tokens = sum(
        int(call["result"].get("completion_tokens") or 0) for call in synthesis_calls
    )
    synthesis_provider_total_tokens = sum(
        int(call["result"].get("total_tokens") or 0) for call in synthesis_calls
    )
    synthesis_evidence = {
        "status": synthesis_result.get("status"),
        "verified_live": synthesis_verified,
        "provider_transport_verified_live": synthesis_transport_verified,
        "provider_response_received": any(call["transport_verified"] for call in synthesis_calls),
        "private_text_sent": False,
        "secret_values_exposed": False,
        "synthetic_text_sent": True,
        "synthetic_input_confirmed": bool(body.get("synthetic_confirmed")),
        "analysis_source": synthesis_source,
        "fallback_used": bool(synthesis_result.get("fallback_used")) or synthesis_source == "local_safe_fallback",
        "request_id": synthesis_result.get("request_id"),
        "provider_request_ids": synthesis_request_ids,
        "provider_call_count": len(synthesis_calls),
        "challenge_nonce": synthesis_nonce,
        "nonce_sent_to_provider": True,
        "nonce_echoed_by_provider": synthesis_nonce_echoed,
        "verification_bound_to_nonce": synthesis_nonce_echoed,
        "verified_at": synthesis_verified_at,
        "latency_ms": synthesis_result.get("latency_ms") or round((time.time() - synthesis_started) * 1000),
        "prompt_tokens": synthesis_result.get("prompt_tokens"),
        "completion_tokens": synthesis_result.get("completion_tokens"),
        "total_tokens": synthesis_result.get("total_tokens"),
        "provider_prompt_tokens": synthesis_provider_prompt_tokens,
        "provider_completion_tokens": synthesis_provider_completion_tokens,
        "provider_total_tokens": synthesis_provider_total_tokens,
        "finish_reason": synthesis_result.get("finish_reason"),
        "context_budget": selected_synthesis["budget"],
        "semantic_completeness": not synthesis_semantic_issues,
        "semantic_issues": synthesis_semantic_issues,
        "repair_attempted": synthesis_repair_attempted,
        "repair_succeeded": synthesis_repair_succeeded,
        "repair_reason": list(dict.fromkeys(synthesis_repair_reason)),
        "warnings": list(synthesis_result.get("warnings") or []) + list(selected_synthesis["warnings"]),
        "model_metadata": _model_metadata(synthesis_result, verified_at=synthesis_verified_at),
        "human_review_required": True,
    }
    if synthesis_repair_attempted:
        synthesis_evidence["warnings"].append(
            "One bounded AMD semantic-repair pass was used because the first cross-case synthesis was incomplete or unsafe."
        )
    if synthesis_source == "local_safe_fallback":
        synthesis_evidence["warnings"].append(
            "Displayed cross-case synthesis is local safe fallback, not AMD-generated synthesis."
        )
    if synthesis_source == "provider_incomplete":
        synthesis_evidence["warnings"].append(
            "AMD returned cross-case JSON, but required synthesis sections or safety checks remain incomplete; synthesis is not VERIFIED LIVE."
        )
    if synthesis_source in {"provider", "provider_incomplete"} and not synthesis_nonce_echoed:
        synthesis_evidence["warnings"].append(
            "Provider did not echo the synthesis nonce; synthesis is not VERIFIED LIVE."
        )
    if synthesis_truncated:
        synthesis_evidence["warnings"].append(
            "Provider synthesis was truncated; synthesis is not VERIFIED LIVE."
        )
    if synthesis_semantic_issues:
        synthesis_evidence["verification_failure_reason"] = "provider_semantic_completeness_failed"
    synthesis_evidence["warnings"] = list(dict.fromkeys(synthesis_evidence["warnings"]))

    total_elapsed = round((time.time() - overall_start) * 1000)
    completed_at = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    succeeded = sum(1 for r in case_results if r.get("verified_live") is True and not r.get("fallback_used"))
    failed_count = len(case_results) - succeeded
    fallback_responses = sum(1 for r in case_results if r.get("fallback_used"))
    latencies = sorted(r["latency_ms"] for r in case_results if r.get("latency_ms") is not None)
    median_latency = latencies[len(latencies) // 2] if latencies else None
    p95_latency = latencies[max(0, int(len(latencies) * 0.95) - 1)] if latencies else None
    case_prompt_tokens = sum(r.get("prompt_tokens") or 0 for r in case_results)
    case_completion_tokens = sum(r.get("completion_tokens") or 0 for r in case_results)
    case_total_tokens = sum(r.get("total_tokens") or 0 for r in case_results)
    synthesis_prompt_tokens = synthesis_provider_prompt_tokens
    synthesis_completion_tokens = synthesis_provider_completion_tokens
    synthesis_total_tokens = synthesis_provider_total_tokens
    provider_prompt_tokens = case_prompt_tokens + synthesis_prompt_tokens
    provider_completion_tokens = case_completion_tokens + synthesis_completion_tokens
    provider_total_tokens = case_total_tokens + synthesis_total_tokens
    throughput = round(len(case_results) / max(total_elapsed / 1000, 0.001), 2)
    metadata = _model_metadata(synthesis_result if synthesis_transport_verified else (case_results[0] if case_results else {}), verified_at=completed_at)
    batch_verified = succeeded == len(case_results) and synthesis_verified
    batch_fallback = fallback_responses > 0 or bool(synthesis_evidence.get("fallback_used"))

    return {
        "status": "ok" if batch_verified else "partial",
        "verified_live": batch_verified,
        "fallback_used": batch_fallback,
        "batch_id": batch_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "submitted": len(normalized),
        "parsed": len(normalized),
        "succeeded": succeeded,
        "failed": failed_count,
        "live_amd_responses": succeeded,
        "live_provider_calls_succeeded": succeeded + sum(
            1 for call in synthesis_calls if call["transport_verified"]
        ),
        "provider_call_count": len(normalized) + len(synthesis_calls),
        "provider_request_ids": [
            *[
                str(case.get("request_id"))
                for case in case_results
                if case.get("request_id")
            ],
            *synthesis_request_ids,
        ],
        "synthesis_call_count": len(synthesis_calls),
        "fallback_responses": fallback_responses,
        "total_elapsed_ms": total_elapsed,
        "median_latency_ms": median_latency,
        "p95_latency_ms": p95_latency,
        # Backward-compatible case-analysis totals. Existing API/tests define
        # these three fields as the sum of per-case results only.
        "prompt_tokens": case_prompt_tokens,
        "completion_tokens": case_completion_tokens,
        "total_tokens": case_total_tokens,
        # Additional transparent accounting for the separate AMD synthesis call.
        "synthesis_prompt_tokens": synthesis_prompt_tokens,
        "synthesis_completion_tokens": synthesis_completion_tokens,
        "synthesis_total_tokens": synthesis_total_tokens,
        "provider_prompt_tokens": provider_prompt_tokens,
        "provider_completion_tokens": provider_completion_tokens,
        "provider_total_tokens": provider_total_tokens,
        "approximate_throughput_rps": throughput,
        "active_model": metadata.get("underlying_model") or metadata.get("served_model") or "not reported",
        "served_model": metadata.get("served_model"),
        "runtime": metadata.get("runtime"),
        "accelerator": metadata.get("accelerator"),
        "model_metadata": metadata,
        "request_settings": {
            "single_completion_max_tokens": WORKLOAD_COMPLETION_BUDGETS["single"],
            "complex_dossier_completion_max_tokens": WORKLOAD_COMPLETION_BUDGETS["complex_dossier"],
            "burst_case_completion_max_tokens": WORKLOAD_COMPLETION_BUDGETS["burst_case"],
            "cross_case_synthesis_completion_max_tokens": WORKLOAD_COMPLETION_BUDGETS["cross_case_synthesis"],
            "cross_case_synthesis_repair_max_tokens": WORKLOAD_COMPLETION_BUDGETS["cross_case_synthesis_repair"],
            "maximum_cross_case_semantic_repair_calls": 1,
            "concurrency": concurrency,
            "silent_truncation_allowed": False,
        },
        "parsed_preview": [{"id": r["case_id"], "text": r["text"][:180]} for r in normalized],
        "cross_case_synthesis": synthesis,
        "cross_case_evidence": synthesis_evidence,
        "synthetic_text_sent": True,
        "synthetic_input_confirmed": bool(body.get("synthetic_confirmed")),
        "private_text_sent": False,
        "secret_values_exposed": False,
        "human_review_required": True,
        "cases": case_results,
    }

def local_scenario() -> dict[str, Any]:
    return {"status": "loaded", "scenario": dict(_LOCAL_SCENARIO), "audit": list(_LOCAL_AUDIT[-6:])}


def update_local_scenario(update: dict[str, Any]) -> dict[str, Any]:
    actor = resolve_actor(str(update.get("actor_id") or "local-coordinator"), fallback="local-coordinator")
    require_role(actor, "scenario_update")
    field_name = str(update.get("field") or "profile")
    value = update.get("value")
    if field_name not in _LOCAL_SCENARIO:
        raise ProductApiError(400, f"unknown local scenario field: {field_name}")
    _LOCAL_SCENARIO[field_name] = value
    _local_audit(actor, "scenario_update", None, {"field": field_name, "value": value})
    return {"status": "updated", "scenario": dict(_LOCAL_SCENARIO), "audit": list(_LOCAL_AUDIT[-6:])}


def local_workers() -> dict[str, Any]:
    return {
        "workers": [
            {"worker_id": "worker-alpha-boat", "status": "online", "zone": "north-embankment", "last_sync": "2 min ago"},
            {"worker_id": "medical-runner-2", "status": "slow link", "zone": "relief-hub-west", "last_sync": "8 min ago"},
            {"worker_id": "shelter-desk", "status": "offline", "zone": "school-shelter-b", "last_sync": "24 min ago"},
        ]
    }


def _local_get_case(case_id: str | None) -> dict[str, Any]:
    if not case_id:
        raise ProductApiError(400, "case_id is required")
    for case in _LOCAL_CASES:
        if case["case_id"] == case_id:
            return case
    raise ProductApiError(404, "case not found")


def _local_audit(actor: dict[str, str] | str, action: str, case_id: str | None, detail: dict[str, Any]) -> None:
    actor_record = resolve_actor(actor) if isinstance(actor, str) else dict(actor)
    _LOCAL_AUDIT.append({"actor": actor_record, "actor_id": actor_record["actor_id"], "actor_name": actor_record["name"], "actor_role": actor_record["role"], "actor_source": actor_record["source"], "action": action, "case_id": case_id, "detail": detail, "created_at": time.time()})


def _local_command_overview() -> dict[str, Any]:
    return {
        "contract": "reliefqueue-product-api/v1",
        "summary": {
            "total_cases": len(_LOCAL_CASES),
            "critical_cases": sum(1 for case in _LOCAL_CASES if case["urgency"] == "RED"),
            "active_cases": sum(1 for case in _LOCAL_CASES if case["status"] in {"open", "assigned", "acknowledged", "in_progress"}),
            "unassigned_cases": sum(1 for case in _LOCAL_CASES if not case.get("assigned_worker_id")),
            "human_review": sum(1 for case in _LOCAL_CASES if case["urgency"] == "REVIEW"),
        },
        "cases": [dict(row) for row in _LOCAL_CASES],
        "health": system_health(),
        "paid_integrations": {
            "sms": "disabled_demo_local_only",
            "push": "disabled_demo_local_only",
            "call": "disabled_demo_local_only",
            "maps": "disabled_demo_local_only",
        },
        "ai": dict(_LOCAL_AI),
        "monitoring": monitoring_status(),
    }


def _select_smoke_case(cases: list[dict[str, Any]], worker_id: str) -> str:
    for case in cases:
        if case.get("assigned_worker_id") in {None, "", worker_id}:
            return str(case["case_id"])
    if not cases:
        raise ProductApiError(500, "no seeded product cases available for smoke validation")
    return str(cases[0]["case_id"])


def _case_from_row(row: list[str | None]) -> dict[str, Any]:
    return {
        "case_id": row[0],
        "title": row[1],
        "safe_summary": row[2],
        "urgency": row[3],
        "need_type": row[4],
        "status": row[5],
        "operation_zone_id": row[6],
        "location_clue": row[7],
        "people_count": int(row[8]) if row[8] else None,
        "assigned_worker_id": row[9] or None,
        "coordinates": {"lon": float(row[10]) if row[10] else None, "lat": float(row[11]) if row[11] else None},
        "revision": 1,
    }


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _check_revision(case: dict[str, Any], expected_revision: int | None, attempted: dict[str, Any]) -> None:
    if expected_revision is None:
        return
    current = int(case.get("revision") or 1)
    if expected_revision != current:
        context = {"case_id": case["case_id"], "expected_revision": expected_revision, "current_revision": current, "attempted": attempted, "server_case": dict(case)}
        _LOCAL_DLQ.append({"type": "revision_conflict", "case_id": case["case_id"], "context": context, "created_at": time.time()})
        raise ProductApiError(409, f"revision conflict for {case['case_id']}: expected {expected_revision}, current {current}")


def _store_evidence(case_id: str, actor: dict[str, str], metadata: dict[str, Any], file_bytes: bytes, idempotency_key: str) -> dict[str, Any]:
    sha = hashlib.sha256(file_bytes).hexdigest()
    original = str(metadata.get("file_name") or "field-evidence.bin")
    suffix = Path(original).suffix or mimetypes.guess_extension(str(metadata.get("media_type") or "")) or ".bin"
    directory = EVIDENCE_STORE / case_id
    directory.mkdir(parents=True, exist_ok=True)
    object_path = directory / f"{sha}{suffix}"
    object_path.write_bytes(file_bytes)
    mime_type = str(metadata.get("mime_type") or metadata.get("media_type") or mimetypes.guess_type(original)[0] or "application/octet-stream")
    try:
        storage_path = str(object_path.relative_to(ROOT))
    except ValueError:
        storage_path = str(object_path)
    record = {
        "case_id": case_id,
        "action": str(metadata.get("action") or "field_evidence_upload"),
        "file_name": original,
        "mime_type": mime_type,
        "size": len(file_bytes),
        "sha256": sha,
        "actor": actor,
        "idempotency_key": idempotency_key,
        "storage_path": storage_path,
        "retrieval_path": f"/api/product/evidence/{case_id}/{sha}",
        "created_at": time.time(),
    }
    _LOCAL_EVIDENCE.append(record)
    return record


def retrieve_evidence(case_id: str, sha256: str) -> bytes:
    for record in _LOCAL_EVIDENCE:
        if record.get("case_id") == case_id and record.get("sha256") == sha256:
            path = ROOT / str(record["storage_path"])
            return path.read_bytes()
    raise ProductApiError(404, "evidence object not found")


def normalize_inbound_webhook(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    provider = provider.lower()
    if provider == "rapidpro":
        normalized = {"provider": "rapidpro", "from": payload.get("contact", {}).get("urn") or payload.get("from"), "text": payload.get("text") or payload.get("message"), "external_id": payload.get("message_id") or payload.get("id")}
    elif provider == "twilio_sms":
        normalized = {"provider": "twilio_sms", "from": payload.get("From"), "text": payload.get("Body"), "external_id": payload.get("MessageSid")}
    elif provider == "whatsapp":
        normalized = {"provider": "whatsapp", "from": payload.get("From") or payload.get("contacts", [{}])[0].get("wa_id"), "text": payload.get("Body") or payload.get("messages", [{}])[0].get("text", {}).get("body"), "external_id": payload.get("MessageSid") or payload.get("messages", [{}])[0].get("id")}
    else:
        normalized = {"provider": "local_mock", "from": payload.get("from", "local"), "text": payload.get("text", ""), "external_id": payload.get("id", _stable_key(json.dumps(payload, sort_keys=True)))}
    normalized["status"] = "normalized"
    return normalized


def messaging_status() -> dict[str, Any]:
    credentials = {
        "rapidpro": bool(os.environ.get("RAPIDPRO_API_TOKEN")),
        "twilio_sms": bool(os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN")),
        "whatsapp": bool(os.environ.get("WHATSAPP_ACCESS_TOKEN")),
        "local_mock": True,
    }
    providers = {
        name: {"mode": "configured-live" if ready and name != "local_mock" else "local/mock", "status": "pass" if ready else "degraded", "credentials_present": ready}
        for name, ready in credentials.items()
    }
    return {"providers": providers, "outbox": list(_LOCAL_OUTBOX[-10:]), "dlq": list(_LOCAL_DLQ[-10:])}


def replay_dlq(actor_id: str) -> dict[str, Any]:
    actor = resolve_actor(actor_id)
    require_role(actor, "dlq_replay")
    count = len(_LOCAL_DLQ)
    _LOCAL_DLQ.clear()
    _local_audit(actor, "dlq_replay", None, {"replayed": count})
    return {"status": "replayed_local_mock", "replayed": count}


def offline_map_data() -> dict[str, Any]:
    cases = list_cases(limit=20)["cases"]
    return {
        "status": "pass",
        "mode": "local/mock",
        "scenario": dict(_LOCAL_SCENARIO),
        "hub": {"name": _LOCAL_SCENARIO["hub"], "lon": 77.05, "lat": 28.04},
        "affected_zone": {"name": _LOCAL_SCENARIO["zone"], "bounds": [[77.0, 28.0], [77.09, 28.0], [77.09, 28.08], [77.0, 28.08]]},
        "reachable_radius_km": _LOCAL_SCENARIO["radius_km"],
        "blocked_areas": [{"name": "Ward 13 east road", "reason": "blocked"}],
        "safe_areas": [{"name": "School shelter B", "reason": "marked safe"}],
        "cases": cases,
        "resources": local_workers()["workers"],
        "provider_boundary": {"routing": "local straight-line placeholder", "geocoding": "fixture coordinates; external providers degraded without credentials"},
    }


def production_config_status() -> dict[str, Any]:
    public_origin = os.environ.get("RELIEFQUEUE_PUBLIC_API_ORIGIN") or os.environ.get("VITE_RELIEFQUEUE_PUBLIC_API_ORIGIN") or "http://127.0.0.1:8765"
    https_expected = os.environ.get("RELIEFQUEUE_EXPECT_HTTPS", "0") == "1"
    return {
        "status": "pass" if (not https_expected or public_origin.startswith("https://")) else "degraded",
        "public_api_origin": public_origin,
        "https_expected": https_expected,
        "cors_mode": "explicit localhost/dev origin" if "127.0.0.1" in public_origin else "configured origin",
        "auth_mode": "demo session identity boundary",
        "public_data_policy": "dashboard/public reports are generated, sanitized, and ignored",
        "secrets": "not exposed",
    }


def monitoring_status() -> dict[str, Any]:
    health = system_health()
    return {
        "status": "pass",
        "live_stack_state": "local/mock" if health.get("postgis") == "LOCAL_MOCK" else "configured-live",
        "worker_health": local_workers()["workers"],
        "queue_pressure": {"outbox_depth": health.get("outbox_depth", 0), "retry_count": health.get("retry_count", 0), "dlq_count": health.get("dlq_count", 0)},
        "provider_status": messaging_status()["providers"],
        "latency_ms": {"local_mock": 1},
        "last_error": health.get("last_error"),
    }


def _claim_idempotency(key: str, scope: str) -> bool:
    claimed = _redis_command(product_redis_url(), ["SET", f"product:idem:{scope}:{key}", "seen", "NX", "EX", REDIS_TTL_SECONDS])
    return claimed == "OK"


def _title_for_case(case: dict[str, Any]) -> str:
    location = case.get("location_clue") or case.get("operation_zone_id") or "case"
    return f"{case.get('need_type', 'need').replace('_', ' ').title()} at {location}"


def _point_for_case(case: dict[str, Any], index: int) -> tuple[float, float]:
    del case
    return (77.0 + (index % 7) * 0.01, 28.0 + (index % 5) * 0.01)


def _stable_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def _ensure_group(redis_url: str, stream: str, group: str) -> None:
    try:
        _redis_xgroup_create(redis_url, stream, group)
    except RuntimeError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


if __name__ == "__main__":
    raise SystemExit(main())


# BEGIN RELIEFQUEUE AMD DOSSIER PROVIDER RECONCILIATION PART 5
# Two provider-authored dossier calls may be reconciled; no local operational conclusions are generated.
# END RELIEFQUEUE AMD DOSSIER PROVIDER RECONCILIATION PART 5
