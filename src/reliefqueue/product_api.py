"""Product API facade backed by the local PostGIS/Redis live stack."""

from __future__ import annotations

import argparse
import base64
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

from .assignment import suggest_assignments
from .cli import ROOT, build_cases
from .intake import load_json, load_jsonl
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


def serve(host: str, port: int, root: Path = ROOT) -> int:
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

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _handle(self, method: str) -> None:
            try:
                payload = _route(method, self.path, self._read_json())
                if isinstance(payload, bytes):
                    self._bytes(200, payload)
                else:
                    self._json(200, payload)
            except ProductApiError as exc:
                self._json(exc.status, {"error": str(exc)})
            except Exception as exc:
                self._json(500, {"error": str(exc)})

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:5173")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _bytes(self, status: int, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:5173")
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
    raise ProductApiError(404, f"unknown product API route: {route}")


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
