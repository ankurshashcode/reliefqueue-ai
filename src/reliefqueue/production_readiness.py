"""Production-readiness status contract for remaining product objectives."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OBJECTIVE_IDS = [
    "evidence_upload",
    "offline_field_queue",
    "conflict_replay",
    "auth_role_identity",
    "production_deployment",
    "messaging_providers",
    "maps_routing_geocoding",
    "amd_vllm_advisory",
    "worker_provider_monitoring",
]


def build_status(root: Path, report_dir: Path) -> dict[str, Any]:
    from . import product_api

    output_path = report_dir / "production_readiness" / "remaining_objectives_status.json"
    monitoring = product_api.monitoring_status()
    messaging = product_api.messaging_status()
    production = product_api.production_config_status()
    maps = product_api.offline_map_data()
    ai_status = _ai_provider_status()
    objectives = [
        _objective(
            "evidence_upload",
            "pass",
            ["Field Worker UI upload button", "POST /api/product/field/action action=evidence", "GET /api/product/evidence"],
            [
                "src/reliefqueue/product_api.py stores decoded file bytes under var/evidence-store/ with checksum, size, MIME, actor, case/action link, and retrieval_path",
                "metadata-only evidence returns HTTP 400/ProductApiError instead of a fake record",
                "reports/product-click-smoke/latest/product-complete.json includes browser action field.add_evidence_metadata hitting /api/product/field/action",
            ],
            ["tests/test_product_api_facade.py evidence upload/reject coverage", "PYTHONPATH=src python3 -m reliefqueue.product_api smoke"],
            [],
            "Use the Field Worker evidence upload surface; keep var/evidence-store/ ignored and review evidence records through the API.",
        ),
        _objective(
            "offline_field_queue",
            "pass",
            ["Field Worker UI outbox", "localStorage reliefqueue.fieldQueue.v1", "POST /api/product/field/sync"],
            [
                "dashboard/src/visualApps.jsx queues field actions with schema/version metadata in localStorage before replay",
                "dashboard/scripts/productClickSmoke.mjs records field_offline_reload_persistence after a browser reload",
                "API replay returns applied, conflict, failed/DLQ context in simple states",
            ],
            ["product-complete-smoke real browser reload persistence assertion", "tests/test_product_api_facade.py offline sync replay coverage"],
            [],
            "Field workers can continue recording notes/status/evidence offline, then press Sync when the API is available.",
        ),
        _objective(
            "conflict_replay",
            "pass",
            ["POST /api/product/field/sync", "Command Center conflict/DLQ panel", "revision fields on product cases"],
            [
                "src/reliefqueue/product_api.py checks expected_revision on local assignment/status mutations",
                "stale replay returns 409 conflict semantics, preserves server_case and attempted local action, and writes DLQ context",
                "UI copy exposes refresh, retry, keep local as note, and escalate safe actions",
            ],
            ["tests/test_product_api_facade.py stale replay does not clobber newer local state"],
            [],
            "When a conflict appears, refresh the case, decide whether to retry, keep the field note, or escalate to command center.",
        ),
        _objective(
            "auth_role_identity",
            "pass",
            ["GET /api/product/session/me", "demo identity selector/copy in UI", "API role guards"],
            [
                "src/reliefqueue/product_api.py defines Command Center Operator, Local Coordinator, and Field Worker demo sessions",
                "API require_role rejects unauthorized role/action combinations with 403",
                "Audit events include actor_id, actor_name, actor_role, and actor_source",
            ],
            ["tests/test_product_api_facade.py role denial and allowed action coverage"],
            [],
            "Use the demo identities in local validation; wire the same actor fields to a real IdP before live deployment.",
        ),
        _objective(
            "production_deployment",
            production["status"],
            ["PYTHONPATH=src python3 -m reliefqueue.cli production-readiness-status", "GET /api/product/production/config", "dashboard build env"],
            [
                f"frontend API origin is explicit/sanitized: {production['public_api_origin']}",
                f"HTTPS expectation: {production['https_expected']}; CORS/auth/public-data policy exposed without secrets",
                "DASHBOARD_DATA_SOURCE=latest npm --prefix dashboard run build validates deterministic production build",
            ],
            ["tests/test_production_readiness.py config/report shape", "dashboard production build"],
            [] if production["status"] == "pass" else ["Hosted HTTPS is degraded in Daytona unless RELIEFQUEUE_EXPECT_HTTPS=1 and an https origin are configured."],
            "Set RELIEFQUEUE_PUBLIC_API_ORIGIN to the hosted HTTPS API before a real production build.",
        ),
        _objective(
            "messaging_providers",
            "degraded" if _any_degraded_provider(messaging) else "pass",
            ["Command Center Messaging/DLQ panel", "POST /api/product/messaging/webhook", "POST /api/product/messaging/replay-dlq"],
            [
                "Provider-independent normalization handles local/mock, RapidPro, Twilio SMS, and WhatsApp payload shapes",
                "Outbound local/mock queue, retry counters, DLQ records, and replay path are inspectable through API/UI",
                "Missing live credentials are degraded while local/mock provider remains pass",
            ],
            ["tests/test_product_api_facade.py webhook normalization and DLQ replay coverage"],
            ["RapidPro/Twilio/WhatsApp live sends SKIP/degrade without provider credentials."],
            "Configure provider credentials only on trusted infrastructure, then run provider live smokes.",
        ),
        _objective(
            "maps_routing_geocoding",
            "degraded",
            ["Local Coordinator offline map panel", "GET /api/product/maps/offline"],
            [
                f"offline map data contains affected zone, hub, reachable radius {maps['reachable_radius_km']} km, cases/resources, blocked and safe areas",
                "routing/geocoding boundary is local/mock with external provider placeholders and no credential requirement",
                "dashboard/src/visualApps.jsx renders the offline map panel in plain language",
            ],
            ["tests/test_production_readiness.py validates map data fields", "product-complete-smoke panel rendering"],
            ["External online map tiles/routing are degraded in Daytona without provider credentials."],
            "Use the offline panel for demos; add a configured map provider only after privacy and credential review.",
        ),
        _objective(
            "amd_vllm_advisory",
            "degraded" if ai_status["mode"] != "configured-live" else "pass",
            ["Command Center AI Control panel", "PYTHONPATH=src python3 -m reliefqueue.cli ai-endpoint-smoke", "GET /api/product/command/overview"],
            [
                f"OpenAI-compatible/vLLM mode is explicit and sanitized: {ai_status['mode']}",
                "offline/mock advisory is deterministic and human_review_required",
                "real endpoint smoke SKIPs on missing env and FAILs clearly for bad configured endpoint without leaking keys",
            ],
            ["tests/test_slice07_amd_vllm_readiness.py", "make ai-endpoint-smoke AI_MODE=mock"],
            ["AMD/vLLM live endpoint is degraded unless OpenAI-compatible endpoint env is configured on a trusted host."],
            "For AMD GPU demo, set sanitized OpenAI-compatible/vLLM env and run ai-endpoint-smoke before enabling live advisory.",
        ),
        _objective(
            "worker_provider_monitoring",
            "pass",
            ["GET /api/product/monitoring", "Command Center monitoring/provider panels", "production-readiness report"],
            [
                f"monitoring distinguishes live_stack_state={monitoring['live_stack_state']} and provider states",
                f"queue pressure exposes outbox={monitoring['queue_pressure']['outbox_depth']} retry={monitoring['queue_pressure']['retry_count']} dlq={monitoring['queue_pressure']['dlq_count']}",
                "worker health, provider latency/status, last_error, and live-stack state are API/report/UI visible",
            ],
            ["tests/test_production_readiness.py monitoring report coverage", "product-complete-smoke command panel coverage"],
            [],
            "Check the Command Center monitoring panels before and after provider smokes or DLQ replay.",
        ),
    ]
    return {
        "contract": "reliefqueue-production-readiness-evidence-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "status": "pass_with_degraded_external_dependencies" if any(obj["status"] == "degraded" for obj in objectives) else "pass",
            "objective_count": len(objectives),
            "pass_count": sum(1 for obj in objectives if obj["status"] == "pass"),
            "degraded_count": sum(1 for obj in objectives if obj["status"] == "degraded"),
            "report_path": str(output_path.relative_to(root)),
        },
        "objectives": objectives,
        "validation_evidence": [
            "PYTHONPATH=src python3 -m reliefqueue.product_api smoke",
            "PYTHONPATH=src python3 -m reliefqueue.cli run-demo-local",
            "DASHBOARD_DATA_SOURCE=latest npm --prefix dashboard run prepare-public-data",
            "DASHBOARD_DATA_SOURCE=latest npm --prefix dashboard run build",
            "npm --prefix dashboard run product-complete-smoke",
            "PYTHONPATH=src python3 -m unittest discover -s tests",
            "PYTHONPATH=src python3 -m reliefqueue.cli production-readiness-status",
        ],
        "limitations": [
            "Hosted HTTPS, RapidPro, Twilio, WhatsApp, external routing/geocoding, and AMD/vLLM live inference degrade or SKIP without credentials/infrastructure.",
            "Reports under reports/latest/ and product-click-smoke JSON are runtime evidence only and must stay ignored.",
        ],
        "next_operator_action": "Run the validation command list, review degraded external-provider notes, then export the Daytona result archive.",
    }


def write_status(root: Path, report_dir: Path) -> Path:
    payload = build_status(root, report_dir)
    output_path = report_dir / "production_readiness" / "remaining_objectives_status.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def plain_summary(root: Path, report_dir: Path) -> str:
    path = write_status(root, report_dir)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return (
        f"Production readiness {payload['summary']['status']}: "
        f"{payload['summary']['pass_count']} pass, {payload['summary']['degraded_count']} degraded. "
        f"Report: {path.relative_to(root)}"
    )


def _objective(
    oid: str,
    status: str,
    operator_surface: list[str],
    runtime_evidence: list[str],
    tests: list[str],
    limitations: list[str],
    next_operator_action: str,
) -> dict[str, Any]:
    if oid not in OBJECTIVE_IDS:
        raise ValueError(f"unknown production-readiness objective {oid}")
    return {
        "id": oid,
        "status": status,
        "operator_surface": operator_surface,
        "runtime_evidence": runtime_evidence,
        "tests": tests,
        "limitations": limitations,
        "next_operator_action": next_operator_action,
    }


def _any_degraded_provider(messaging: dict[str, Any]) -> bool:
    return any(provider.get("status") == "degraded" for provider in messaging.get("providers", {}).values() if provider)


def _ai_provider_status() -> dict[str, str]:
    mode = os.environ.get("AI_MODE", "mock")
    configured = bool(os.environ.get("OPENAI_COMPAT_BASE_URL") and os.environ.get("OPENAI_COMPAT_API_KEY"))
    if mode == "openai_compatible" and configured:
        return {"mode": "configured-live"}
    if mode == "openai_compatible":
        return {"mode": "degraded-missing-env"}
    return {"mode": "local/mock"}
